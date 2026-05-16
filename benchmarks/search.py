"""CLI driver: benchmark local protein search (blastp / MMseqs2 / DIAMOND) -> JSONL."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Any

from Bio import SeqIO

from core.array_backend import cuda_available
from core.tool_runtime import get_tool_runtime

from benchmarks.runner import (
    argv_for_resolution,
    collect_search_tool_versions,
    collect_system_metadata,
    dump_metadata_json,
    timed_run,
    try_resolve_executable,
)


def append_jsonl(path: str, obj: dict[str, Any]) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, default=str) + "\n")


def blast_db_exists(prefix: str) -> bool:
    return os.path.isfile(prefix + ".phr") or os.path.isfile(prefix + ".00.phr")


def sensitivity_value(name: str) -> str:
    mapping = {
        "fast": "4",
        "sensitive": "5.7",
        "more-sensitive": "7",
        "very-sensitive": "8.5",
    }
    return mapping.get(name, "5.7")


def top_hit_accessions_tab(path: str, *, subject_col: int, max_lines: int) -> tuple[list[str], int]:
    """Parse tabular output; return (first *max_lines* subject accessions, total_line_count)."""
    hits: list[str] = []
    total = 0
    if not os.path.isfile(path):
        return hits, total
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            total += 1
            if len(parts) <= subject_col:
                continue
            acc = parts[subject_col].strip()
            if acc and len(hits) < max_lines:
                hits.append(acc)
    return hits, total


def resolve_blastdbcmd_exe(rt, blast_resolution) -> str | None:
    """Locate blastdbcmd next to blastp when possible."""
    if blast_resolution and blast_resolution.executable:
        cand = os.path.join(os.path.dirname(blast_resolution.executable), "blastdbcmd")
        if os.path.isfile(cand):
            return cand
    return shutil.which("blastdbcmd")


def ensure_mmseqs_db_from_blast(
    blast_prefix: str,
    mmseqs_dest_prefix: str,
    *,
    rt,
    mmseqs_res,
    blast_resolution,
) -> tuple[float, str | None]:
    """Extract FASTA via blastdbcmd + ``mmseqs createdb``. Returns (setup_wall_seconds, error_or_none)."""
    blastcmd = resolve_blastdbcmd_exe(rt, blast_resolution)
    if not blastcmd:
        return 0.0, "blastdbcmd not found (needed for BLAST→MMseqs conversion)"

    fasta_native = mmseqs_dest_prefix + "_extract.fasta"
    if os.path.isdir(mmseqs_dest_prefix):
        shutil.rmtree(mmseqs_dest_prefix, ignore_errors=True)
    parent = os.path.dirname(mmseqs_dest_prefix)
    if parent:
        os.makedirs(parent, exist_ok=True)

    t0 = time.monotonic()
    ext = subprocess.run(
        [
            blastcmd,
            "-db",
            blast_prefix,
            "-entry",
            "all",
            "-out",
            fasta_native,
        ],
        capture_output=True,
        text=True,
        timeout=3600,
        check=False,
    )
    if ext.returncode != 0:
        return time.monotonic() - t0, (ext.stderr or "blastdbcmd failed").strip()
    if not os.path.isfile(fasta_native) or os.path.getsize(fasta_native) == 0:
        return time.monotonic() - t0, "blastdbcmd produced empty FASTA"

    argv_db = argv_for_resolution(
        mmseqs_res,
        [
            "createdb",
            rt.prepare_path(mmseqs_res, fasta_native),
            rt.prepare_path(mmseqs_res, mmseqs_dest_prefix),
        ],
    )
    cr = timed_run(argv_db, timeout=7200)
    wall = time.monotonic() - t0
    try:
        os.unlink(fasta_native)
    except OSError:
        pass
    if cr.exit_code != 0:
        return wall, cr.stderr_snippet or "mmseqs createdb failed"
    return wall, None


def ensure_dmnd_from_blast(
    blast_prefix: str,
    tmp_dir: str,
    *,
    rt,
    diamond_res,
    blast_resolution,
) -> tuple[str | None, float, str | None]:
    """Return (.dmnd path or None, setup_wall_seconds, error)."""
    dmnd_path = blast_prefix + ".dmnd"
    if os.path.isfile(dmnd_path):
        return dmnd_path, 0.0, None
    if not blast_db_exists(blast_prefix):
        return None, 0.0, f"No BLAST database at {blast_prefix}"

    blastcmd = resolve_blastdbcmd_exe(rt, blast_resolution)
    if not blastcmd:
        return None, 0.0, "blastdbcmd not found"

    os.makedirs(tmp_dir, exist_ok=True)
    fasta_path = os.path.join(tmp_dir, "dmnd_extract.fasta")
    t0 = time.monotonic()
    ext = subprocess.run(
        [blastcmd, "-entry", "all", "-db", blast_prefix, "-out", fasta_path],
        capture_output=True,
        text=True,
        timeout=3600,
        check=False,
    )
    if ext.returncode != 0:
        return None, time.monotonic() - t0, (ext.stderr or "blastdbcmd failed").strip()
    if not os.path.isfile(fasta_path) or os.path.getsize(fasta_path) == 0:
        return None, time.monotonic() - t0, "empty FASTA from blastdbcmd"

    dmnd_tool = rt.prepare_path(diamond_res, dmnd_path)
    fasta_tool = rt.prepare_path(diamond_res, fasta_path)
    argv = argv_for_resolution(diamond_res, ["makedb", "--in", fasta_tool, "-d", dmnd_tool])
    mk = timed_run(argv, timeout=7200)
    wall = time.monotonic() - t0
    try:
        os.unlink(fasta_path)
    except OSError:
        pass
    if mk.exit_code != 0:
        return None, wall, mk.stderr_snippet or "diamond makedb failed"
    if not os.path.isfile(dmnd_path):
        return None, wall, "diamond makedb did not produce .dmnd"
    return dmnd_path, wall, None


def run_mmseqs_cpu_pipeline(
    *,
    mmseqs_res,
    rt,
    query_native: str,
    target_db_native: str,
    tmp_native: str,
    sensitivity: str,
    threads: int,
    top_k: int,
    timeout_search: float,
) -> tuple[float, float | None, str | None, list[str], int, str]:
    """Returns wall_total, peak_rss_mib_max, stderr_snippet, top_ids, hit_lines, error."""
    os.makedirs(tmp_native, exist_ok=True)
    query_db = os.path.join(tmp_native, "queryDB")
    result_db = os.path.join(tmp_native, "resultDB")
    tmp_mm = os.path.join(tmp_native, "tmp_mmseqs")
    os.makedirs(tmp_mm, exist_ok=True)
    out_m8 = os.path.join(tmp_native, "results.m8")

    q_in = rt.prepare_path(mmseqs_res, query_native)
    q_db = rt.prepare_path(mmseqs_res, query_db)
    res_db = rt.prepare_path(mmseqs_res, result_db)
    tmp_tool = rt.prepare_path(mmseqs_res, tmp_mm)
    tgt_db = rt.prepare_path(mmseqs_res, target_db_native)
    out_tool = rt.prepare_path(mmseqs_res, out_m8)

    peak_max = None
    stderr_bits: list[str] = []

    steps = [
        (["createdb", q_in, q_db], 120.0),
        (
            [
                "search",
                q_db,
                tgt_db,
                res_db,
                tmp_tool,
                "-s",
                sensitivity_value(sensitivity),
                "--threads",
                str(threads),
            ],
            timeout_search,
        ),
        (
            [
                "convertalis",
                q_db,
                tgt_db,
                res_db,
                out_tool,
                "--format-output",
                "query,target,theader,pident,alnlen,mismatch,gapopen,qstart,qend,tstart,tend,evalue,bits",
            ],
            600.0,
        ),
    ]

    wall_total = 0.0
    for cmd_parts, tout in steps:
        argv = argv_for_resolution(mmseqs_res, cmd_parts)
        r = timed_run(argv, timeout=tout)
        wall_total += r.wall_seconds
        if r.peak_rss_mib is not None:
            peak_max = max(peak_max or 0.0, r.peak_rss_mib)
        stderr_bits.append(r.stderr_snippet[:200])
        if r.exit_code != 0 or r.timed_out:
            err = "; ".join(stderr_bits)
            return wall_total, peak_max, err, [], 0, "mmseqs_step_failed"

    ids, nlines = top_hit_accessions_tab(out_m8, subject_col=1, max_lines=top_k)
    snippet = "; ".join(stderr_bits)[:500]
    return wall_total, peak_max, snippet, ids, nlines, ""


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark local protein search tools.")
    ap.add_argument("--query", required=True, help="Query FASTA (first record used like GUI workers).")
    ap.add_argument("--db", required=True, help="Database prefix path (BLAST) or MMseqs DB.")
    ap.add_argument(
        "--db-type",
        choices=("blast", "mmseqs"),
        default="blast",
        help="Interpret --db as BLAST prefix or existing MMseqs DB.",
    )
    ap.add_argument("--tools", default="blastp,mmseqs,mmseqs_gpu,diamond", help="Comma-separated.")
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--threads", type=int, default=0, help="0 = os.cpu_count().")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--sensitivity", default="sensitive", help="MMseqs -s preset name.")
    ap.add_argument("--work-dir", default=os.path.join("benchmark_runs", "search_tmp"))
    ap.add_argument("--out", default=os.path.join("benchmark_runs", "search.jsonl"))
    args = ap.parse_args()

    threads = args.threads if args.threads > 0 else max(1, (os.cpu_count() or 4))
    tools_requested = [t.strip() for t in args.tools.split(",") if t.strip()]

    rt = get_tool_runtime()
    versions = collect_search_tool_versions()
    meta = collect_system_metadata(versions)
    meta["db_type"] = args.db_type
    meta["blast_db"] = os.path.abspath(args.db)
    meta_path = os.path.join(os.path.dirname(os.path.abspath(args.out)) or ".", "search_session_meta.json")
    dump_metadata_json(meta_path, meta)

    query_src = os.path.abspath(args.query)
    work_root = os.path.abspath(args.work_dir)
    os.makedirs(work_root, exist_ok=True)

    records = list(SeqIO.parse(query_src, "fasta"))
    if not records:
        raise SystemExit("Query FASTA has no sequences.")
    query_single = os.path.join(work_root, "bench_query_single.fasta")
    SeqIO.write(records[0], query_single, "fasta")

    blast_prefix = os.path.abspath(args.db)
    mmseqs_target = blast_prefix

    mmseqs_res, _ = try_resolve_executable("mmseqs")
    blast_res, _ = try_resolve_executable("blastp")
    diamond_res, _ = try_resolve_executable("diamond")

    needs_mmseqs_conversion = args.db_type == "blast" and any(
        t in tools_requested for t in ("mmseqs", "mmseqs_gpu")
    )

    if args.db_type == "blast":
        if not blast_db_exists(blast_prefix):
            raise SystemExit(f"BLAST database files not found for prefix:\n  {blast_prefix}")
        if needs_mmseqs_conversion:
            if mmseqs_res is None:
                print("[skip] mmseqs/mmseqs_gpu: MMseqs2 not available.")
            else:
                mmseqs_cached = os.path.join(work_root, "mmseqs_target_db")
                err_msg = None
                if not os.path.exists(mmseqs_cached + ".dbtype"):
                    prep_wall, err_msg = ensure_mmseqs_db_from_blast(
                        blast_prefix,
                        mmseqs_cached,
                        rt=rt,
                        mmseqs_res=mmseqs_res,
                        blast_resolution=blast_res,
                    )
                    meta["mmseqs_prep_wall_seconds"] = prep_wall
                    dump_metadata_json(meta_path, meta)
                if os.path.exists(mmseqs_cached + ".dbtype"):
                    mmseqs_target = mmseqs_cached
                elif err_msg:
                    print(f"[warn] MMseqs DB preparation failed: {err_msg}")

    elif args.db_type == "mmseqs":
        mmseqs_target = blast_prefix
        if not os.path.exists(mmseqs_target + ".dbtype"):
            raise SystemExit(
                f"MMseqs database not found at prefix (missing .dbtype):\n  {mmseqs_target}"
            )

    dmnd_path: str | None = None
    if "diamond" in tools_requested and args.db_type == "blast":
        if diamond_res is None:
            pass
        else:
            dmnd_path, dmnd_prep_wall, derr = ensure_dmnd_from_blast(
                blast_prefix,
                os.path.join(work_root, "diamond_build"),
                rt=rt,
                diamond_res=diamond_res,
                blast_resolution=blast_res,
            )
            meta["diamond_prep_wall_seconds"] = dmnd_prep_wall
            dump_metadata_json(meta_path, meta)
            if derr:
                print(f"[warn] DIAMOND DB preparation failed: {derr}")
                dmnd_path = None

    out_abs = os.path.abspath(args.out)
    if os.path.isfile(out_abs):
        os.unlink(out_abs)

    def run_blastp_repeat(rep_idx: int) -> dict[str, Any]:
        resolution = blast_res
        assert resolution is not None and resolution.executable
        out_tab = os.path.join(work_root, f"blastp_{uuid.uuid4().hex[:8]}.tsv")
        q_tool = rt.prepare_path(resolution, query_single)
        db_tool = rt.prepare_path(resolution, blast_prefix)
        o_tool = rt.prepare_path(resolution, out_tab)
        cmd_parts = [
            "-query",
            q_tool,
            "-db",
            db_tool,
            "-num_threads",
            str(threads),
            "-max_target_seqs",
            str(args.top_k),
            "-outfmt",
            "6 qseqid sseqid evalue bitscore",
            "-out",
            o_tool,
        ]
        argv = argv_for_resolution(resolution, cmd_parts)
        r = timed_run(argv, timeout=3600)
        ids, nlines = top_hit_accessions_tab(out_tab, subject_col=1, max_lines=args.top_k)
        try:
            os.unlink(out_tab)
        except OSError:
            pass
        return {
            "study": "search",
            "tool": "blastp",
            "repeat": rep_idx,
            "threads": threads,
            "top_k": args.top_k,
            "wall_seconds": r.wall_seconds,
            "peak_rss_mib": r.peak_rss_mib,
            "exit_code": r.exit_code,
            "timed_out": r.timed_out,
            "stderr_snippet": r.stderr_snippet,
            "hit_lines": nlines,
            "top_hit_accessions": ids,
        }

    def run_mmseqs_cpu_repeat(rep_idx: int) -> dict[str, Any]:
        assert mmseqs_res is not None
        tmp = tempfile.mkdtemp(prefix="bench_mmseqs_", dir=work_root)
        try:
            wall, peak, snippet, ids, nlines, err = run_mmseqs_cpu_pipeline(
                mmseqs_res=mmseqs_res,
                rt=rt,
                query_native=query_single,
                target_db_native=mmseqs_target,
                tmp_native=tmp,
                sensitivity=args.sensitivity,
                threads=threads,
                top_k=args.top_k,
                timeout_search=1800,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return {
            "study": "search",
            "tool": "mmseqs",
            "repeat": rep_idx,
            "threads": threads,
            "top_k": args.top_k,
            "wall_seconds": wall,
            "peak_rss_mib": peak,
            "exit_code": 0 if not err else 1,
            "timed_out": False,
            "stderr_snippet": snippet,
            "hit_lines": nlines,
            "top_hit_accessions": ids,
            "error": err or None,
        }

    def run_mmseqs_gpu_repeat(rep_idx: int) -> dict[str, Any]:
        assert mmseqs_res is not None
        tmp = tempfile.mkdtemp(prefix="bench_mmseqs_gpu_", dir=work_root)
        try:
            out_m8 = os.path.join(tmp, "results.m8")
            tmp_mm = os.path.join(tmp, "tmp")
            os.makedirs(tmp_mm, exist_ok=True)
            q_tool = rt.prepare_path(mmseqs_res, query_single)
            db_tool = rt.prepare_path(mmseqs_res, mmseqs_target)
            out_tool = rt.prepare_path(mmseqs_res, out_m8)
            tmp_tool = rt.prepare_path(mmseqs_res, tmp_mm)
            cmd_parts = [
                "easy-search",
                q_tool,
                db_tool,
                out_tool,
                tmp_tool,
                "--search-type",
                "1",
                "-s",
                sensitivity_value(args.sensitivity),
                "--max-seqs",
                str(args.top_k),
                "--format-output",
                "query,target,theader,pident,alnlen,mismatch,gapopen,qstart,qend,tstart,tend,evalue,bits",
                "--threads",
                str(threads),
                "--gpu",
                "1",
            ]
            argv = argv_for_resolution(mmseqs_res, cmd_parts)
            r = timed_run(argv, timeout=3600)
            ids, nlines = top_hit_accessions_tab(out_m8, subject_col=1, max_lines=args.top_k)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return {
            "study": "search",
            "tool": "mmseqs_gpu",
            "repeat": rep_idx,
            "threads": threads,
            "top_k": args.top_k,
            "wall_seconds": r.wall_seconds,
            "peak_rss_mib": r.peak_rss_mib,
            "exit_code": r.exit_code,
            "timed_out": r.timed_out,
            "stderr_snippet": r.stderr_snippet,
            "hit_lines": nlines,
            "top_hit_accessions": ids,
        }

    def run_diamond_repeat(rep_idx: int) -> dict[str, Any]:
        assert diamond_res is not None and dmnd_path
        out_tab = os.path.join(work_root, f"diamond_{uuid.uuid4().hex[:8]}.tsv")
        q_tool = rt.prepare_path(diamond_res, query_single)
        d_tool = rt.prepare_path(diamond_res, dmnd_path)
        o_tool = rt.prepare_path(diamond_res, out_tab)
        cmd_parts = [
            "blastp",
            "-q",
            q_tool,
            "-d",
            d_tool,
            "-o",
            o_tool,
            "--outfmt",
            "6",
            "qseqid",
            "sseqid",
            "stitle",
            "pident",
            "length",
            "mismatch",
            "gapopen",
            "qstart",
            "qend",
            "sstart",
            "send",
            "evalue",
            "bitscore",
            "--evalue",
            "10",
            "--max-target-seqs",
            str(args.top_k),
            "--threads",
            str(threads),
        ]
        argv = argv_for_resolution(diamond_res, cmd_parts)
        r = timed_run(argv, timeout=3600)
        ids, nlines = top_hit_accessions_tab(out_tab, subject_col=1, max_lines=args.top_k)
        try:
            os.unlink(out_tab)
        except OSError:
            pass
        return {
            "study": "search",
            "tool": "diamond",
            "repeat": rep_idx,
            "threads": threads,
            "top_k": args.top_k,
            "wall_seconds": r.wall_seconds,
            "peak_rss_mib": r.peak_rss_mib,
            "exit_code": r.exit_code,
            "timed_out": r.timed_out,
            "stderr_snippet": r.stderr_snippet,
            "hit_lines": nlines,
            "top_hit_accessions": ids,
        }

    runners = {
        "blastp": ("blastp", run_blastp_repeat),
        "mmseqs": ("mmseqs", run_mmseqs_cpu_repeat),
        "mmseqs_gpu": ("mmseqs_gpu", run_mmseqs_gpu_repeat),
        "diamond": ("diamond", run_diamond_repeat),
    }

    for tool in tools_requested:
        if tool not in runners:
            print(f"[skip] unknown tool {tool!r}")
            continue
        label, runner_fn = runners[tool]

        if tool == "blastp":
            if blast_res is None:
                print("[skip] blastp not available.")
                continue
        elif tool == "mmseqs":
            if mmseqs_res is None:
                print("[skip] mmseqs not available.")
                continue
            if not os.path.exists(mmseqs_target + ".dbtype"):
                print("[skip] mmseqs: MMseqs database missing (.dbtype).")
                continue
        elif tool == "mmseqs_gpu":
            if mmseqs_res is None:
                print("[skip] mmseqs_gpu: MMseqs2 not available.")
                continue
            if not cuda_available():
                print("[skip] mmseqs_gpu: CUDA GPU not detected (nvidia-smi).")
                continue
            if not os.path.exists(mmseqs_target + ".dbtype"):
                print("[skip] mmseqs_gpu: MMseqs database missing (.dbtype).")
                continue
        elif tool == "diamond":
            if diamond_res is None:
                print("[skip] diamond not available.")
                continue
            if dmnd_path is None:
                print("[skip] diamond: no .dmnd database.")
                continue

        total = args.warmup + args.repeats
        rep_out = 0
        for i in range(total):
            if i < args.warmup:
                runner_fn(-1)
                continue
            row = runner_fn(rep_out)
            rep_out += 1
            append_jsonl(out_abs, row)
            tag = "OK" if row.get("exit_code") == 0 and not row.get("timed_out") else "FAIL"
            print(
                f"[{tag}] {label} rep={row['repeat']} time={row['wall_seconds']:.2f}s "
                f"hits={row.get('hit_lines')}"
            )

    print(f"Wrote {out_abs}")
    print(f"Session metadata: {meta_path}")


if __name__ == "__main__":
    main()
