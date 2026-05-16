"""Run tiered alignment benchmarks (default sizes: 2k / 5k / 100k / 500k)."""

from __future__ import annotations

import argparse
import datetime
import os

from core.array_backend import cuda_available
from core.tool_registry import ALIGNMENT_TOOL_IDS
from core.tool_runtime import get_tool_runtime

from benchmarks.alignment import (
    alignment_timeout,
    append_jsonl,
    effective_threads,
    run_one_alignment,
)
from benchmarks.datasets import subset_fasta
from benchmarks.runner import (
    collect_alignment_tool_versions,
    collect_system_metadata,
    dump_metadata_json,
    try_resolve_executable,
)

DEFAULT_TIER_SIZES = (2000, 5000, 100000, 500000)

ALL_TOOLS = ("clustalo", "mafft", "muscle", "famsa", "famsa_gpu", "twilight")
ULTRA_TOOLS = ("famsa", "famsa_gpu", "twilight")

ALL_TOOLS_THRESHOLD = 10_000


def parse_tiers(spec: str) -> list[int]:
    out = [int(x.strip()) for x in spec.split(",") if x.strip()]
    if not out:
        raise SystemExit("--tiers must have at least one positive integer.")
    if any(x <= 0 for x in out):
        raise SystemExit("--tiers values must be positive.")
    return out


def tools_for_size(n: int) -> tuple[str, ...]:
    """Sizes <= ALL_TOOLS_THRESHOLD use all tools; larger uses ultra-scale only."""
    if n <= ALL_TOOLS_THRESHOLD:
        return ALL_TOOLS
    return ULTRA_TOOLS


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Tiered alignment benchmark: sizes ≤10k use all tools; larger tiers use ultra-scale tools only.",
    )
    ap.add_argument(
        "--source",
        required=True,
        help="Source FASTA (e.g. benchmark_data/PF00005_raw.fasta)",
    )
    ap.add_argument(
        "--tiers",
        default=",".join(str(x) for x in DEFAULT_TIER_SIZES),
        help=f"Comma-separated tier sizes (default {','.join(map(str, DEFAULT_TIER_SIZES))})",
    )
    ap.add_argument("--threads", default="1,4,8", help="Comma-separated thread counts.")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument(
        "--work-dir",
        default=os.path.join("benchmark_runs", "tiered", "data"),
        help="Where subset FASTA files are written",
    )
    ap.add_argument(
        "--out-dir",
        default=os.path.join("benchmark_runs", "tiered"),
        help="Output directory (alignment.jsonl + metadata live here)",
    )
    ap.add_argument("--seed", type=int, default=42, help="Reservoir seed for all subsets")
    args = ap.parse_args()

    sizes = parse_tiers(args.tiers)
    thread_list = [int(x.strip()) for x in args.threads.split(",") if x.strip()]

    work_dir = os.path.abspath(args.work_dir)
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    src = os.path.abspath(args.source)
    if not os.path.isfile(src):
        raise SystemExit(f"Missing --source: {src}")

    out_abs = os.path.join(out_dir, "alignment.jsonl")
    meta_path = os.path.join(out_dir, "alignment_session_meta.json")

    rt = get_tool_runtime()
    versions = collect_alignment_tool_versions(list(ALIGNMENT_TOOL_IDS))
    meta = collect_system_metadata(versions)
    meta["tiered"] = {"tiers": list(sizes), "seed": args.seed, "source": src}
    dump_metadata_json(meta_path, meta)

    if os.path.isfile(out_abs):
        os.unlink(out_abs)

    ladder: list[tuple[int, str, int, tuple[str, ...]]] = []

    # Materialise subsets (tier field = 1-based index matching plan table)
    for ti, n in enumerate(sizes, start=1):
        label = f"tier{ti}_n{n}"
        dst = os.path.join(work_dir, f"{label}.fasta")
        wrote = subset_fasta(src, n, dst, seed=args.seed)
        tools = tools_for_size(n)
        ladder.append((ti, dst, wrote, tools))
        print(f"[prep] tier {ti} seq_count={wrote} -> {dst} tools={tools}")

    for tier_idx, path, n_seq, tools in ladder:
        for tool_id in tools:
            resolution, _exe = try_resolve_executable(tool_id)
            if resolution is None:
                print(f"[skip] tier {tier_idx} {tool_id}: not installed / not resolved.")
                continue
            if tool_id == "famsa_gpu" and not cuda_available():
                print(f"[skip] tier {tier_idx} famsa_gpu: CUDA / GPU not detected.")
                continue

            for threads in thread_list:
                eff_t = threads if threads > 0 else effective_threads(None)
                total_runs = args.warmup + args.repeats
                rep_record = 0
                for i in range(total_runs):
                    is_warmup = i < args.warmup
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    phase = "warmup" if is_warmup else f"rep {rep_record}"
                    timeout_s = alignment_timeout(tool_id, n_seq)
                    print(
                        f"[{ts}] [start] tier={tier_idx} {tool_id} n={n_seq} "
                        f"threads={eff_t} {phase} timeout={timeout_s:.0f}s",
                        flush=True,
                    )
                    if is_warmup:
                        run_one_alignment(
                            tool_id,
                            dataset_label=f"n{n_seq}",
                            seq_count=n_seq,
                            threads=eff_t,
                            repeat_idx=-1,
                            input_path=path,
                            resolution=resolution,
                            rt=rt,
                            tier=str(tier_idx),
                        )
                        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [done] warmup finished", flush=True)
                        continue
                    row = run_one_alignment(
                        tool_id,
                        dataset_label=f"n{n_seq}",
                        seq_count=n_seq,
                        threads=eff_t,
                        repeat_idx=rep_record,
                        input_path=path,
                        resolution=resolution,
                        rt=rt,
                        tier=str(tier_idx),
                    )
                    rep_record += 1
                    append_jsonl(out_abs, row)
                    tag = "OK" if row.get("exit_code") == 0 and not row.get("timed_out") else "FAIL"
                    ts2 = datetime.datetime.now().strftime("%H:%M:%S")
                    print(
                        f"[{ts2}] [{tag}] tier={tier_idx} {tool_id} n={n_seq} threads={eff_t} "
                        f"rep={row['repeat']} time={row['wall_seconds']:.2f}s",
                        flush=True,
                    )

    print(f"Wrote {out_abs}")
    print(f"Session metadata: {meta_path}")


if __name__ == "__main__":
    main()
