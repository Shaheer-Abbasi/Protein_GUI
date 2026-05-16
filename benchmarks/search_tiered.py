"""Protein homology-search benchmarks.

Benchmarks BLASTP, MMseqs2 CPU, MMseqs2 GPU, and DIAMOND against FASTA-derived
target databases. The default mode samples one query sequence and builds one
target database so it matches the common "single FASTA query vs database" flow.
Database-build time is recorded separately from search time.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any

from Bio import SeqIO

from core.array_backend import cuda_available
from core.tool_runtime import get_tool_runtime

from benchmarks.datasets import count_sequences, subset_fasta
from benchmarks.runner import (
    TimedRunResult,
    argv_for_resolution,
    collect_search_tool_versions,
    collect_system_metadata,
    dump_metadata_json,
    timed_run,
    try_resolve_executable,
)


DEFAULT_TARGET_SIZE = "100000"
DEFAULT_TOOLS = ("blastp", "mmseqs", "mmseqs_gpu", "diamond")
MMSEQS_FORMAT = "query,target,pident,alnlen,qstart,qend,tstart,tend,evalue,bits"


@dataclass(frozen=True)
class TargetTier:
    label: str
    fasta_path: str
    seq_count: int


@dataclass(frozen=True)
class ToolSetup:
    ok: bool
    db_path: str | None
    wall_seconds: float
    stderr_snippet: str


def append_jsonl(path: str, obj: dict[str, Any]) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, default=str) + "\n")


def parse_target_sizes(spec: str) -> list[int | str]:
    out: list[int | str] = []
    for part in spec.split(","):
        token = part.strip().lower()
        if not token:
            continue
        if token == "full":
            out.append("full")
        else:
            n = int(token)
            if n <= 0:
                raise ValueError(f"Tier sizes must be positive, got {n}")
            out.append(n)
    if not out:
        raise ValueError("target sizes must include at least one value")
    return out


def sensitivity_value(name: str) -> str:
    mapping = {
        "fast": "4",
        "sensitive": "5.7",
        "more-sensitive": "7",
        "very-sensitive": "8.5",
    }
    return mapping.get(name, name)


def materialize_targets(source_fasta: str, tiers: list[int | str], work_dir: str, seed: int) -> list[TargetTier]:
    os.makedirs(work_dir, exist_ok=True)
    source_abs = os.path.abspath(source_fasta)
    out: list[TargetTier] = []
    for idx, tier in enumerate(tiers, start=1):
        single_target = len(tiers) == 1
        if tier == "full":
            label = "target_full" if single_target else f"tier{idx}_full"
            out.append(TargetTier(label=label, fasta_path=source_abs, seq_count=count_sequences(source_abs)))
            continue
        n = int(tier)
        stem = f"target_n{n}" if single_target else f"tier{idx}_n{n}"
        dst = os.path.join(work_dir, f"{stem}.fasta")
        wrote = subset_fasta(source_abs, n, dst, seed=seed)
        label = f"target_n{wrote}" if single_target else f"tier{idx}_n{wrote}"
        out.append(TargetTier(label=label, fasta_path=os.path.abspath(dst), seq_count=wrote))
    return out


def materialize_queries(source_fasta: str, query_size: int, work_dir: str, seed: int) -> tuple[str, int]:
    os.makedirs(work_dir, exist_ok=True)
    query_path = os.path.join(work_dir, f"query_n{query_size}.fasta")
    wrote = subset_fasta(os.path.abspath(source_fasta), query_size, query_path, seed=seed)
    if wrote <= 0:
        raise SystemExit("Query FASTA sample is empty.")
    return os.path.abspath(query_path), wrote


def blast_db_exists(prefix: str) -> bool:
    suffixes = (".pin", ".psq", ".phr", ".00.pin", ".00.psq", ".00.phr")
    return any(os.path.isfile(prefix + s) for s in suffixes)


def mmseqs_db_exists(prefix: str) -> bool:
    return os.path.exists(prefix + ".dbtype")


def diamond_db_exists(prefix: str) -> bool:
    return os.path.isfile(prefix + ".dmnd") or os.path.isfile(prefix)


def find_makeblastdb(blastp_exe: str | None) -> str | None:
    if blastp_exe:
        candidate = os.path.join(os.path.dirname(blastp_exe), "makeblastdb")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("makeblastdb")


def top_hit_accessions_tab(path: str, *, subject_col: int = 1, max_lines: int = 100) -> tuple[list[str], int]:
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
            if len(parts) > subject_col and len(hits) < max_lines:
                hits.append(parts[subject_col])
    return hits, total


def setup_blast_db(*, fasta_path: str, prefix: str, makeblastdb: str | None, timeout: float) -> ToolSetup:
    if blast_db_exists(prefix):
        return ToolSetup(True, prefix, 0.0, "")
    if not makeblastdb:
        return ToolSetup(False, None, 0.0, "makeblastdb not found")
    os.makedirs(os.path.dirname(prefix) or ".", exist_ok=True)
    result = timed_run(
        [makeblastdb, "-in", fasta_path, "-dbtype", "prot", "-out", prefix],
        timeout=timeout,
    )
    return ToolSetup(
        ok=result.exit_code == 0 and not result.timed_out and blast_db_exists(prefix),
        db_path=prefix if blast_db_exists(prefix) else None,
        wall_seconds=result.wall_seconds,
        stderr_snippet=result.stderr_snippet,
    )


def setup_mmseqs_db(*, mmseqs_res, rt, fasta_path: str, prefix: str, timeout: float) -> ToolSetup:
    if mmseqs_db_exists(prefix):
        return ToolSetup(True, prefix, 0.0, "")
    os.makedirs(os.path.dirname(prefix) or ".", exist_ok=True)
    argv = argv_for_resolution(
        mmseqs_res,
        ["createdb", rt.prepare_path(mmseqs_res, fasta_path), rt.prepare_path(mmseqs_res, prefix)],
    )
    result = timed_run(argv, timeout=timeout)
    return ToolSetup(
        ok=result.exit_code == 0 and not result.timed_out and mmseqs_db_exists(prefix),
        db_path=prefix if mmseqs_db_exists(prefix) else None,
        wall_seconds=result.wall_seconds,
        stderr_snippet=result.stderr_snippet,
    )


def setup_mmseqs_gpu_db(*, mmseqs_res, rt, cpu_prefix: str, gpu_prefix: str, timeout: float) -> ToolSetup:
    if mmseqs_db_exists(gpu_prefix):
        return ToolSetup(True, gpu_prefix, 0.0, "")
    if not mmseqs_db_exists(cpu_prefix):
        return ToolSetup(False, None, 0.0, "MMseqs CPU database missing before makepaddedseqdb")
    argv = argv_for_resolution(
        mmseqs_res,
        [
            "makepaddedseqdb",
            rt.prepare_path(mmseqs_res, cpu_prefix),
            rt.prepare_path(mmseqs_res, gpu_prefix),
        ],
    )
    result = timed_run(argv, timeout=timeout)
    return ToolSetup(
        ok=result.exit_code == 0 and not result.timed_out and mmseqs_db_exists(gpu_prefix),
        db_path=gpu_prefix if mmseqs_db_exists(gpu_prefix) else None,
        wall_seconds=result.wall_seconds,
        stderr_snippet=result.stderr_snippet,
    )


def setup_diamond_db(*, diamond_res, rt, fasta_path: str, prefix: str, timeout: float) -> ToolSetup:
    dmnd_path = prefix + ".dmnd"
    if os.path.isfile(dmnd_path):
        return ToolSetup(True, prefix, 0.0, "")
    os.makedirs(os.path.dirname(prefix) or ".", exist_ok=True)
    argv = argv_for_resolution(
        diamond_res,
        ["makedb", "--in", rt.prepare_path(diamond_res, fasta_path), "-d", rt.prepare_path(diamond_res, prefix)],
    )
    result = timed_run(argv, timeout=timeout)
    return ToolSetup(
        ok=result.exit_code == 0 and not result.timed_out and os.path.isfile(dmnd_path),
        db_path=prefix if os.path.isfile(dmnd_path) else None,
        wall_seconds=result.wall_seconds,
        stderr_snippet=result.stderr_snippet,
    )


def base_row(
    *,
    tool: str,
    target: TargetTier,
    query_count: int,
    repeat: int,
    threads: int,
    top_k: int,
    setup: ToolSetup,
) -> dict[str, Any]:
    return {
        "study": "search_tiered",
        "tool": tool,
        "target_label": target.label,
        "target_seq_count": target.seq_count,
        "query_count": query_count,
        "repeat": repeat,
        "threads": threads,
        "top_k": top_k,
        "setup_wall_seconds": setup.wall_seconds,
    }


def run_blastp(*, blast_res, rt, query_path: str, db_prefix: str, work_dir: str, threads: int, top_k: int, evalue: str, timeout: float) -> tuple[TimedRunResult, list[str], int]:
    out_tab = os.path.join(work_dir, f"blastp_{uuid.uuid4().hex[:8]}.tsv")
    argv = argv_for_resolution(
        blast_res,
        [
            "-query",
            rt.prepare_path(blast_res, query_path),
            "-db",
            rt.prepare_path(blast_res, db_prefix),
            "-num_threads",
            str(threads),
            "-evalue",
            evalue,
            "-max_target_seqs",
            str(top_k),
            "-outfmt",
            "6 qseqid sseqid pident length qstart qend sstart send evalue bitscore",
            "-out",
            rt.prepare_path(blast_res, out_tab),
        ],
    )
    result = timed_run(argv, timeout=timeout)
    ids, nlines = top_hit_accessions_tab(out_tab, max_lines=top_k)
    try:
        os.unlink(out_tab)
    except OSError:
        pass
    return result, ids, nlines


def run_mmseqs(*, mmseqs_res, rt, query_path: str, target_db: str, work_dir: str, threads: int, top_k: int, sensitivity: str, timeout: float, gpu: bool) -> tuple[TimedRunResult, list[str], int]:
    tmp = tempfile.mkdtemp(prefix="mmseqs_gpu_" if gpu else "mmseqs_", dir=work_dir)
    out_m8 = os.path.join(tmp, "results.m8")
    tmp_mm = os.path.join(tmp, "tmp")
    os.makedirs(tmp_mm, exist_ok=True)
    cmd_parts = [
        "easy-search",
        rt.prepare_path(mmseqs_res, query_path),
        rt.prepare_path(mmseqs_res, target_db),
        rt.prepare_path(mmseqs_res, out_m8),
        rt.prepare_path(mmseqs_res, tmp_mm),
        "--threads",
        str(threads),
        "--max-seqs",
        str(top_k),
        "--format-output",
        MMSEQS_FORMAT,
    ]
    if gpu:
        cmd_parts.extend(["--gpu", "1"])
    else:
        cmd_parts.extend(["-s", sensitivity_value(sensitivity)])
    result = timed_run(argv_for_resolution(mmseqs_res, cmd_parts), timeout=timeout)
    ids, nlines = top_hit_accessions_tab(out_m8, max_lines=top_k)
    shutil.rmtree(tmp, ignore_errors=True)
    return result, ids, nlines


def run_diamond(*, diamond_res, rt, query_path: str, db_prefix: str, work_dir: str, threads: int, top_k: int, evalue: str, sensitivity: str, timeout: float) -> tuple[TimedRunResult, list[str], int]:
    out_tab = os.path.join(work_dir, f"diamond_{uuid.uuid4().hex[:8]}.tsv")
    cmd_parts = [
        "blastp",
        "-q",
        rt.prepare_path(diamond_res, query_path),
        "-d",
        rt.prepare_path(diamond_res, db_prefix),
        "-o",
        rt.prepare_path(diamond_res, out_tab),
        "--outfmt",
        "6",
        "qseqid",
        "sseqid",
        "pident",
        "length",
        "qstart",
        "qend",
        "sstart",
        "send",
        "evalue",
        "bitscore",
        "--evalue",
        evalue,
        "--max-target-seqs",
        str(top_k),
        "--threads",
        str(threads),
    ]
    if sensitivity in {"sensitive", "more-sensitive", "very-sensitive", "ultra-sensitive"}:
        cmd_parts.append(f"--{sensitivity}")
    result = timed_run(argv_for_resolution(diamond_res, cmd_parts), timeout=timeout)
    ids, nlines = top_hit_accessions_tab(out_tab, max_lines=top_k)
    try:
        os.unlink(out_tab)
    except OSError:
        pass
    return result, ids, nlines


def result_row(row: dict[str, Any], result: TimedRunResult, ids: list[str], hit_lines: int) -> dict[str, Any]:
    row.update(
        {
            "wall_seconds": result.wall_seconds,
            "peak_rss_mib": result.peak_rss_mib,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "stderr_snippet": result.stderr_snippet,
            "hit_lines": hit_lines,
            "top_hit_accessions": ids,
        },
    )
    return row


def setup_failure_row(row: dict[str, Any], setup: ToolSetup) -> dict[str, Any]:
    row.update(
        {
            "wall_seconds": 0.0,
            "peak_rss_mib": None,
            "exit_code": 1,
            "timed_out": False,
            "stderr_snippet": setup.stderr_snippet or "tool setup failed",
            "hit_lines": 0,
            "top_hit_accessions": [],
            "error": "setup_failed",
        },
    )
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description="Single-query homology-search benchmark for BLASTP/MMseqs2/DIAMOND.")
    ap.add_argument("--source", required=True, help="Target FASTA source used to materialize the database.")
    ap.add_argument("--query-source", help="Query FASTA source (defaults to --source).")
    ap.add_argument(
        "--target-size",
        default=DEFAULT_TARGET_SIZE,
        help="Target database size to sample, or 'full' (default: 100000).",
    )
    ap.add_argument(
        "--target-tiers",
        default=None,
        help="Optional legacy comma-separated target sizes; overrides --target-size when provided.",
    )
    ap.add_argument("--query-size", type=int, default=1, help="Number of query sequences to sample (default: 1).")
    ap.add_argument("--tools", default=",".join(DEFAULT_TOOLS), help="Comma-separated: blastp,mmseqs,mmseqs_gpu,diamond.")
    ap.add_argument("--threads", type=int, default=0, help="0 = os.cpu_count().")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--warmup", type=int, default=0)
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--evalue", default="10")
    ap.add_argument("--sensitivity", default="sensitive", help="MMseqs CPU/DIAMOND sensitivity preset.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--setup-timeout", type=float, default=14_400)
    ap.add_argument("--search-timeout", type=float, default=7_200)
    ap.add_argument("--work-dir", default=os.path.join("benchmark_runs", "search_single", "data"))
    ap.add_argument("--out-dir", default=os.path.join("benchmark_runs", "search_single"))
    args = ap.parse_args()

    threads = args.threads if args.threads > 0 else max(1, (os.cpu_count() or 4))
    tools = [t.strip() for t in args.tools.split(",") if t.strip()]
    unknown = sorted(set(tools) - set(DEFAULT_TOOLS))
    if unknown:
        raise SystemExit(f"Unknown tool(s): {', '.join(unknown)}")

    os.makedirs(args.work_dir, exist_ok=True)
    os.makedirs(args.out_dir, exist_ok=True)
    out_jsonl = os.path.abspath(os.path.join(args.out_dir, "search.jsonl"))
    meta_path = os.path.abspath(os.path.join(args.out_dir, "search_session_meta.json"))
    if os.path.isfile(out_jsonl):
        os.unlink(out_jsonl)

    source = os.path.abspath(args.source)
    query_source = os.path.abspath(args.query_source or args.source)
    target_work = os.path.abspath(os.path.join(args.work_dir, "targets"))
    query_work = os.path.abspath(os.path.join(args.work_dir, "queries"))
    db_work = os.path.abspath(os.path.join(args.work_dir, "db"))
    scratch_work = os.path.abspath(os.path.join(args.work_dir, "scratch"))
    for path in (target_work, query_work, db_work, scratch_work):
        os.makedirs(path, exist_ok=True)

    target_spec = args.target_tiers or args.target_size
    targets = materialize_targets(source, parse_target_sizes(target_spec), target_work, args.seed)
    query_path, query_count = materialize_queries(query_source, args.query_size, query_work, args.seed + 1)

    rt = get_tool_runtime()
    blast_res, blast_exe = try_resolve_executable("blastp")
    mmseqs_res, _mmseqs_exe = try_resolve_executable("mmseqs")
    diamond_res, _diamond_exe = try_resolve_executable("diamond")
    makeblastdb = find_makeblastdb(blast_exe)

    meta = collect_system_metadata(collect_search_tool_versions())
    meta.update(
        {
            "source": source,
            "query_source": query_source,
            "query_path": query_path,
            "query_count": query_count,
            "target_size_spec": target_spec,
            "target_databases": [target.__dict__ for target in targets],
            "tools": tools,
            "threads": threads,
            "top_k": args.top_k,
            "evalue": args.evalue,
            "sensitivity": args.sensitivity,
            "notes": {
                "mmseqs_gpu": "Uses makepaddedseqdb target DB and easy-search --gpu 1.",
                "mmseqs_cpu": "Uses easy-search with -s sensitivity; GPU mode ignores -s by MMseqs2 design.",
            },
        },
    )
    dump_metadata_json(meta_path, meta)

    for target in targets:
        print(f"[prep] {target.label} seq_count={target.seq_count} fasta={target.fasta_path}", flush=True)
        tier_db_dir = os.path.join(db_work, target.label)
        os.makedirs(tier_db_dir, exist_ok=True)

        setups: dict[str, ToolSetup] = {}
        if "blastp" in tools:
            setups["blastp"] = (
                setup_blast_db(
                    fasta_path=target.fasta_path,
                    prefix=os.path.join(tier_db_dir, "blastdb"),
                    makeblastdb=makeblastdb,
                    timeout=args.setup_timeout,
                )
                if blast_res is not None
                else ToolSetup(False, None, 0.0, "blastp not resolved")
            )
        if "mmseqs" in tools or "mmseqs_gpu" in tools:
            setups["mmseqs"] = (
                setup_mmseqs_db(
                    mmseqs_res=mmseqs_res,
                    rt=rt,
                    fasta_path=target.fasta_path,
                    prefix=os.path.join(tier_db_dir, "mmseqs_db"),
                    timeout=args.setup_timeout,
                )
                if mmseqs_res is not None
                else ToolSetup(False, None, 0.0, "mmseqs not resolved")
            )
        if "mmseqs_gpu" in tools:
            if not cuda_available():
                setups["mmseqs_gpu"] = ToolSetup(False, None, 0.0, "CUDA GPU not detected")
            elif mmseqs_res is None:
                setups["mmseqs_gpu"] = ToolSetup(False, None, 0.0, "mmseqs not resolved")
            else:
                setups["mmseqs_gpu"] = setup_mmseqs_gpu_db(
                    mmseqs_res=mmseqs_res,
                    rt=rt,
                    cpu_prefix=os.path.join(tier_db_dir, "mmseqs_db"),
                    gpu_prefix=os.path.join(tier_db_dir, "mmseqs_db_gpu"),
                    timeout=args.setup_timeout,
                )
        if "diamond" in tools:
            setups["diamond"] = (
                setup_diamond_db(
                    diamond_res=diamond_res,
                    rt=rt,
                    fasta_path=target.fasta_path,
                    prefix=os.path.join(tier_db_dir, "diamond_db"),
                    timeout=args.setup_timeout,
                )
                if diamond_res is not None
                else ToolSetup(False, None, 0.0, "diamond not resolved")
            )

        for tool in tools:
            setup = setups.get(tool)
            if setup is None:
                setup = ToolSetup(False, None, 0.0, "tool setup unavailable")
            total = args.warmup + args.repeats
            rep_record = 0
            for i in range(total):
                is_warmup = i < args.warmup
                rep = -1 if is_warmup else rep_record
                phase = "warmup" if is_warmup else f"rep {rep_record}"
                print(
                    f"[{dt.datetime.now().strftime('%H:%M:%S')}] [start] {tool} "
                    f"{target.label} q={query_count} threads={threads} {phase}",
                    flush=True,
                )

                row = base_row(
                    tool=tool,
                    target=target,
                    query_count=query_count,
                    repeat=rep,
                    threads=threads,
                    top_k=args.top_k,
                    setup=setup,
                )
                if not setup.ok or not setup.db_path:
                    row = setup_failure_row(row, setup)
                elif tool == "blastp":
                    assert blast_res is not None
                    result, ids, nlines = run_blastp(
                        blast_res=blast_res,
                        rt=rt,
                        query_path=query_path,
                        db_prefix=setup.db_path,
                        work_dir=scratch_work,
                        threads=threads,
                        top_k=args.top_k,
                        evalue=args.evalue,
                        timeout=args.search_timeout,
                    )
                    row = result_row(row, result, ids, nlines)
                elif tool == "mmseqs":
                    assert mmseqs_res is not None
                    result, ids, nlines = run_mmseqs(
                        mmseqs_res=mmseqs_res,
                        rt=rt,
                        query_path=query_path,
                        target_db=setup.db_path,
                        work_dir=scratch_work,
                        threads=threads,
                        top_k=args.top_k,
                        sensitivity=args.sensitivity,
                        timeout=args.search_timeout,
                        gpu=False,
                    )
                    row = result_row(row, result, ids, nlines)
                elif tool == "mmseqs_gpu":
                    assert mmseqs_res is not None
                    result, ids, nlines = run_mmseqs(
                        mmseqs_res=mmseqs_res,
                        rt=rt,
                        query_path=query_path,
                        target_db=setup.db_path,
                        work_dir=scratch_work,
                        threads=threads,
                        top_k=args.top_k,
                        sensitivity=args.sensitivity,
                        timeout=args.search_timeout,
                        gpu=True,
                    )
                    row = result_row(row, result, ids, nlines)
                elif tool == "diamond":
                    assert diamond_res is not None
                    result, ids, nlines = run_diamond(
                        diamond_res=diamond_res,
                        rt=rt,
                        query_path=query_path,
                        db_prefix=setup.db_path,
                        work_dir=scratch_work,
                        threads=threads,
                        top_k=args.top_k,
                        evalue=args.evalue,
                        sensitivity=args.sensitivity,
                        timeout=args.search_timeout,
                    )
                    row = result_row(row, result, ids, nlines)
                else:
                    row = setup_failure_row(row, ToolSetup(False, None, 0.0, f"unknown tool: {tool}"))

                if not is_warmup:
                    rep_record += 1
                    append_jsonl(out_jsonl, row)
                tag = "OK" if row.get("exit_code") == 0 and not row.get("timed_out") else "FAIL"
                print(
                    f"[{dt.datetime.now().strftime('%H:%M:%S')}] [{tag}] {tool} "
                    f"{target.label} rep={rep} search_time={row['wall_seconds']:.2f}s "
                    f"setup_time={row['setup_wall_seconds']:.2f}s hits={row['hit_lines']}",
                    flush=True,
                )

    print(f"Wrote {out_jsonl}")
    print(f"Session metadata: {meta_path}")


if __name__ == "__main__":
    main()
