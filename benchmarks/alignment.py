"""CLI driver: sweep alignment tools across FASTA subsets -> JSONL."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import uuid
from typing import Any

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord

from core.array_backend import cuda_available
from core.tool_registry import ALIGNMENT_TOOL_IDS
from core.tool_runtime import get_tool_runtime

from benchmarks.datasets import prepare_size_ladder
from benchmarks.quality import compute_quality
from benchmarks.runner import (
    TimedRunResult,
    argv_for_resolution,
    collect_alignment_tool_versions,
    collect_system_metadata,
    dump_metadata_json,
    timed_run,
    try_resolve_executable,
)


BASE_ALIGNMENT_TIMEOUT = 600
# Skip expensive `compute_quality` on very large alignments (memory / wall time).
QUALITY_MAX_SEQS = 50_000


def effective_threads(requested: int | None) -> int:
    if requested is not None and requested > 0:
        return int(requested)
    return max(1, min(8, (os.cpu_count() or 4)))


def alignment_timeout(tool_id: str, seq_count: int) -> float:
    """Wall-clock cap for subprocess; scales with *seq_count*, more aggressively past 10k."""
    base = BASE_ALIGNMENT_TIMEOUT
    if tool_id in ("famsa", "famsa_gpu"):
        # Short tiers stay responsive; Pfam ultra tiers need tens of hours on long proteins.
        if seq_count <= 5_000:
            return float(max(base, seq_count // 40 + 240))
        if seq_count <= 100_000:
            return float(max(3600.0 * 14, seq_count / 750.0 * 3600))
        # 500k+: allow multi-day heroic runs (still capped ~8 days).
        return float(min(691_200.0, max(3600.0 * 48, seq_count / 400.0 * 3600)))
    classical_mult = 5 if seq_count >= 10_000 else 3
    if tool_id == "mafft":
        return float(max(base, seq_count * classical_mult))
    if tool_id == "twilight":
        return float(max(base, seq_count * 2) * 2)
    # clustalo, muscle, fallback
    if tool_id in ("clustalo", "muscle"):
        mult = 5 if seq_count >= 10_000 else 2
        return float(max(base, seq_count * mult))
    return float(max(base, seq_count * 2))


def append_jsonl(path: str, obj: dict[str, Any]) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, default=str) + "\n")


def parse_sizes(spec: str) -> list[int | str]:
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    out: list[int | str] = []
    for p in parts:
        if p.lower() == "full":
            out.append("full")
        else:
            out.append(int(p))
    return out


def parse_int_list(spec: str) -> list[int]:
    return [int(x.strip()) for x in spec.split(",") if x.strip()]


def build_argv_clustalo(
    rt,
    resolution,
    input_native: str,
    output_native: str,
    threads: int,
) -> list[str]:
    inp = rt.prepare_path(resolution, input_native)
    outp = rt.prepare_path(resolution, output_native)
    cmd_parts = [
        "-i",
        inp,
        "-o",
        outp,
        "--outfmt=fasta",
        "--threads",
        str(threads),
        "--force",
        "--verbose",
    ]
    return argv_for_resolution(resolution, cmd_parts)


def build_argv_mafft(
    rt,
    resolution,
    input_native: str,
    threads: int,
) -> list[str]:
    inp = rt.prepare_path(resolution, input_native)
    cmd_parts = ["--auto", "--thread", str(threads), inp]
    return argv_for_resolution(resolution, cmd_parts)


def _detect_muscle_version(exe: str) -> int:
    """Return major version of muscle (3 or 5). Defaults to 5 on failure."""
    import subprocess as _sp
    try:
        out = _sp.run([exe, "-version"], capture_output=True, text=True, timeout=10, check=False)
        line = (out.stdout or out.stderr or "").strip()
        if "muscle v3" in line.lower() or "muscle 3" in line.lower():
            return 3
    except Exception:
        pass
    return 5


def build_argv_muscle(
    rt,
    resolution,
    input_native: str,
    output_native: str,
    threads: int,
) -> list[str]:
    inp = rt.prepare_path(resolution, input_native)
    outp = rt.prepare_path(resolution, output_native)
    ver = _detect_muscle_version(resolution.executable or "muscle")
    if ver == 3:
        cmd_parts = ["-in", inp, "-out", outp]
    else:
        cmd_parts = ["-align", inp, "-output", outp, "-threads", str(threads)]
    return argv_for_resolution(resolution, cmd_parts)


def build_argv_famsa(
    rt,
    resolution,
    input_native: str,
    output_native: str,
    threads: int,
) -> list[str]:
    inp = rt.prepare_path(resolution, input_native)
    outp = rt.prepare_path(resolution, output_native)
    cmd_parts = ["-t", str(threads), inp, outp]
    return argv_for_resolution(resolution, cmd_parts)


# TWILIGHT rejects -C outside 1..24 (runtime validation).
TWILIGHT_MAX_CPU_CORES = 24


def _materialize_twilight_safe_fasta(original_path: str) -> str:
    """Copy *original_path* with short Newick-safe IDs for FAMSA tree export + TWILIGHT.

    UniProt headers contain spaces/parens/colons that break Newick parsing when FAMSA
    embeds full titles as tip names. Sequential ``twilight_seq_000001`` IDs avoid that.
    """
    safe_path = original_path + ".twilight_safe.fasta"
    tree_path = safe_path + ".twilight_guide.nwk"
    need_write = True
    if os.path.isfile(safe_path) and os.path.isfile(original_path):
        if os.path.getmtime(safe_path) >= os.path.getmtime(original_path):
            need_write = False
    if need_write:
        try:
            os.unlink(tree_path)
        except OSError:
            pass
        out_recs: list[SeqRecord] = []
        for i, rec in enumerate(SeqIO.parse(original_path, "fasta"), start=1):
            nid = f"twilight_seq_{i:06d}"
            out_recs.append(SeqRecord(rec.seq, id=nid, description=""))
        parent = os.path.dirname(os.path.abspath(safe_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        SeqIO.write(out_recs, safe_path, "fasta")
    return safe_path


def _guide_tree_subprocess_timeout(seq_count: int) -> float:
    """Seconds for ``famsa -gt_export`` (NJ). Large *N* can exceed many hours."""
    if seq_count <= 5_000:
        return 14_400.0  # 4 h floor for noisy hosts
    if seq_count <= 100_000:
        return 172_800.0  # 48 h — short timeouts killed tier-2 Twilight before alignment
    return 691_200.0  # 192 h hero tier


def _ensure_guide_tree(input_fasta: str, threads: int, seq_count: int) -> tuple[str | None, str]:
    """Build FAMSA NJ guide tree for TWILIGHT. Returns ``(path, \"\")`` or ``(None, error)``.

    Drops cached ``*.twilight_guide.nwk`` if older than *input_fasta* so labels stay in sync.
    """
    tree_path = input_fasta + ".twilight_guide.nwk"
    if (
        os.path.isfile(tree_path)
        and os.path.getsize(tree_path) > 0
        and os.path.isfile(input_fasta)
        and os.path.getmtime(tree_path) >= os.path.getmtime(input_fasta)
    ):
        return tree_path, ""

    try:
        os.unlink(tree_path)
    except OSError:
        pass

    _res, famsa_exe = try_resolve_executable("famsa")
    if not famsa_exe:
        return None, "famsa not resolved (needed for TWILIGHT guide tree)"

    budget = _guide_tree_subprocess_timeout(seq_count)
    try:
        proc = subprocess.run(
            [
                famsa_exe,
                "-t",
                str(threads),
                "-gt",
                "nj",
                "-gt_export",
                input_fasta,
                tree_path,
            ],
            capture_output=True,
            timeout=budget,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return (
            None,
            f"famsa -gt_export timed out ({budget:.0f}s) building guide tree (try smaller tier or fewer threads)",
        )
    except Exception as exc:
        return None, f"famsa -gt_export error: {exc}"

    if proc.returncode != 0 or not (os.path.isfile(tree_path) and os.path.getsize(tree_path) > 0):
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()
        hint = err[:800] if err else "(no stderr)"
        return None, f"famsa -gt_export failed (exit {proc.returncode}): {hint}"

    return tree_path, ""


def build_argv_twilight(
    rt,
    resolution,
    input_native: str,
    output_native: str,
    threads: int,
    tree_path: str | None = None,
) -> list[str]:
    inp = rt.prepare_path(resolution, input_native)
    outp = rt.prepare_path(resolution, output_native)
    twilight_threads = max(1, min(int(threads), TWILIGHT_MAX_CPU_CORES))
    cmd_parts = ["-i", inp, "-o", outp, "-C", str(twilight_threads), "--type", "p", "--overwrite"]
    if tree_path and os.path.isfile(tree_path):
        cmd_parts.extend(["-t", rt.prepare_path(resolution, tree_path)])
    if cuda_available():
        cmd_parts.append("--gpu-index")
        cmd_parts.append("0")
    else:
        cmd_parts.append("--cpu-only")
    return argv_for_resolution(resolution, cmd_parts)


def run_one_alignment(
    tool_id: str,
    *,
    dataset_label: str,
    seq_count: int,
    threads: int,
    repeat_idx: int,
    input_path: str,
    resolution,
    rt,
    tier: str = "custom",
) -> dict[str, Any]:
    uid = uuid.uuid4().hex[:10]
    tmp_dir = tempfile.gettempdir()
    out_native = os.path.join(tmp_dir, f"bench_aln_{tool_id}_{uid}.fasta")

    argv: list[str]
    stdout_capture: str | None = None
    tree_err = ""

    if tool_id == "clustalo":
        argv = build_argv_clustalo(rt, resolution, input_path, out_native, threads)
    elif tool_id == "mafft":
        argv = build_argv_mafft(rt, resolution, input_path, threads)
        stdout_capture = os.path.join(tmp_dir, f"bench_mafft_{uid}.stdout.fasta")
    elif tool_id == "muscle":
        argv = build_argv_muscle(rt, resolution, input_path, out_native, threads)
    elif tool_id in ("famsa", "famsa_gpu"):
        argv = build_argv_famsa(rt, resolution, input_path, out_native, threads)
    elif tool_id == "twilight":
        safe_in = _materialize_twilight_safe_fasta(input_path)
        tree_path, tree_err = _ensure_guide_tree(safe_in, threads, seq_count)
        argv = (
            build_argv_twilight(rt, resolution, safe_in, out_native, threads, tree_path)
            if tree_path
            else []
        )
    else:
        raise ValueError(f"Unsupported alignment tool: {tool_id}")

    timeout = alignment_timeout(tool_id, seq_count)
    if tool_id == "twilight" and not argv:
        result = TimedRunResult(
            wall_seconds=0.0,
            peak_rss_mib=None,
            exit_code=1,
            stderr_snippet=(tree_err or "twilight: guide tree missing")[:500],
            timed_out=False,
        )
    else:
        result = timed_run(
            argv,
            timeout=timeout,
            stdout_path=stdout_capture,
        )

    aligned_path: str | None = None
    if tool_id == "mafft" and stdout_capture and os.path.isfile(stdout_capture):
        aligned_path = stdout_capture
    elif os.path.isfile(out_native):
        aligned_path = out_native

    row: dict[str, Any] = {
        "study": "alignment",
        "tool": tool_id,
        "dataset_label": dataset_label,
        "tier": tier,
        "seq_count": seq_count,
        "threads": threads,
        "repeat": repeat_idx,
        "wall_seconds": result.wall_seconds,
        "peak_rss_mib": result.peak_rss_mib,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "stderr_snippet": result.stderr_snippet,
    }
    if tool_id == "twilight":
        row["twilight_c_threads"] = max(1, min(int(threads), TWILIGHT_MAX_CPU_CORES))

    qual: dict[str, Any] = {}
    if (
        aligned_path
        and result.exit_code == 0
        and not result.timed_out
        and os.path.getsize(aligned_path) > 0
    ):
        if seq_count > QUALITY_MAX_SEQS:
            qual = {"quality_skipped": f"seq_count>{QUALITY_MAX_SEQS}"}
        else:
            try:
                q = compute_quality(aligned_path)
                qual = {
                    "avg_pid": q.avg_pid,
                    "gap_fraction": q.gap_fraction,
                    "mean_entropy": q.mean_entropy,
                }
            except Exception as exc:
                qual = {"quality_error": str(exc)}
    elif aligned_path is None and result.exit_code == 0:
        qual = {"quality_error": "no_alignment_output"}
    elif result.exit_code != 0 or result.timed_out:
        qual = {}

    row.update(qual)

    for p in (out_native, stdout_capture):
        if p and os.path.isfile(p):
            try:
                os.unlink(p)
            except OSError:
                pass

    return row


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark multiple sequence alignment tools.")
    ap.add_argument(
        "--input",
        default=os.path.join("resources", "sample_fasta", "gamma_phylogeny_sort_3.fasta"),
        help="Source FASTA path.",
    )
    ap.add_argument("--sizes", default="50,200,full", help="Comma-separated ints or full.")
    ap.add_argument(
        "--tools",
        default="clustalo,mafft,muscle,famsa,famsa_gpu,twilight",
        help="Comma-separated tool ids.",
    )
    ap.add_argument("--threads", default="1,4,8", help="Comma-separated thread counts.")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument(
        "--tier",
        default="custom",
        help='JSONL "tier" field for this run (default custom; use tiered harness for 1–4)',
    )
    ap.add_argument("--work-dir", default=os.path.join("benchmark_runs", "data"))
    ap.add_argument("--out", default=os.path.join("benchmark_runs", "alignment.jsonl"))
    args = ap.parse_args()

    sizes = parse_sizes(args.sizes)
    tools_requested = [t.strip() for t in args.tools.split(",") if t.strip()]
    thread_list = parse_int_list(args.threads)

    for tid in tools_requested:
        if tid not in ALIGNMENT_TOOL_IDS:
            raise SystemExit(f"Unknown alignment tool {tid!r}. Expected one of {ALIGNMENT_TOOL_IDS}.")

    ladder = prepare_size_ladder(os.path.abspath(args.input), sizes, os.path.abspath(args.work_dir))

    rt = get_tool_runtime()
    versions = collect_alignment_tool_versions(list(ALIGNMENT_TOOL_IDS))
    meta = collect_system_metadata(versions)
    meta_path = os.path.join(
        os.path.dirname(os.path.abspath(args.out)) or ".",
        "alignment_session_meta.json",
    )
    dump_metadata_json(meta_path, meta)

    out_abs = os.path.abspath(args.out)
    if os.path.isfile(out_abs):
        os.unlink(out_abs)

    for label, path, n_seq in ladder:
        for tool_id in tools_requested:
            resolution, _exe = try_resolve_executable(tool_id)
            if resolution is None:
                print(f"[skip] {tool_id}: not installed / not resolved.")
                continue
            if tool_id == "famsa_gpu" and not cuda_available():
                print("[skip] famsa_gpu: CUDA / GPU not detected (nvidia-smi).")
                continue

            for threads in thread_list:
                eff_t = threads if threads > 0 else effective_threads(None)
                total_runs = args.warmup + args.repeats
                rep_record = 0
                for i in range(total_runs):
                    is_warmup = i < args.warmup
                    if is_warmup:
                        run_one_alignment(
                            tool_id,
                            dataset_label=label,
                            seq_count=n_seq,
                            threads=eff_t,
                            repeat_idx=-1,
                            input_path=os.path.abspath(path),
                            resolution=resolution,
                            rt=rt,
                            tier=str(args.tier),
                        )
                        continue
                    row = run_one_alignment(
                        tool_id,
                        dataset_label=label,
                        seq_count=n_seq,
                        threads=eff_t,
                        repeat_idx=rep_record,
                        input_path=os.path.abspath(path),
                        resolution=resolution,
                        rt=rt,
                        tier=str(args.tier),
                    )
                    rep_record += 1
                    append_jsonl(out_abs, row)
                    tag = "OK" if row.get("exit_code") == 0 and not row.get("timed_out") else "FAIL"
                    print(
                        f"[{tag}] {tool_id} {label} threads={eff_t} rep={row['repeat']} "
                        f"time={row['wall_seconds']:.2f}s"
                    )

    print(f"Wrote {out_abs}")
    print(f"Session metadata: {meta_path}")


if __name__ == "__main__":
    main()
