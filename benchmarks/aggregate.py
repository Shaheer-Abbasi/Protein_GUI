"""Aggregate benchmark JSONL logs into CSV summaries, figures (PNG/PDF), and report.md."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from statistics import mean, median, pstdev
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

NUMERIC_FIELDS_ALIGNMENT = ("wall_seconds", "peak_rss_mib", "avg_pid", "gap_fraction", "mean_entropy")
NUMERIC_FIELDS_SEARCH = ("wall_seconds", "peak_rss_mib", "hit_lines")


def read_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def safe_mean(vals: list[float]) -> float | None:
    v = [x for x in vals if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not v:
        return None
    return float(mean(v))


def safe_median(vals: list[float]) -> float | None:
    v = [x for x in vals if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not v:
        return None
    return float(median(v))


def safe_std(vals: list[float]) -> float | None:
    v = [x for x in vals if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if len(v) < 2:
        return None
    return float(pstdev(v))


def tier_plot_sort_key(label: str) -> tuple[int, str]:
    """Sort tier labels numeric-first (\"1\"\u2026\"4\"), then lexical for \"custom\"/other."""
    if label.isdigit():
        return (0, f"{int(label):06d}")
    return (1, label)


def summarize_alignment(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r.get("study") != "alignment":
            continue
        if r.get("exit_code") != 0 or r.get("timed_out"):
            continue
        tier = str(r.get("tier", "custom"))
        key = (str(r["tool"]), str(r["dataset_label"]), tier, int(r["threads"]))
        groups[key].append(r)

    summary: list[dict[str, Any]] = []
    for (tool, ds_label, tier, threads), items in sorted(groups.items()):
        row: dict[str, Any] = {
            "tool": tool,
            "dataset_label": ds_label,
            "tier": tier,
            "threads": threads,
            "n": len(items),
            "seq_count": items[0].get("seq_count"),
        }
        for field in NUMERIC_FIELDS_ALIGNMENT:
            vals = []
            for it in items:
                if field not in it:
                    continue
                try:
                    vals.append(float(it[field]))
                except (TypeError, ValueError):
                    pass
            row[f"{field}_mean"] = safe_mean(vals)
            row[f"{field}_median"] = safe_median(vals)
            row[f"{field}_std"] = safe_std(vals)
        summary.append(row)
    return summary


def summarize_search(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r.get("study") != "search":
            continue
        if r.get("exit_code") != 0 or r.get("timed_out"):
            continue
        key = (str(r["tool"]), int(r["threads"]))
        groups[key].append(r)

    summary: list[dict[str, Any]] = []
    for (tool, threads), items in sorted(groups.items()):
        row: dict[str, Any] = {"tool": tool, "threads": threads, "n": len(items)}
        for field in NUMERIC_FIELDS_SEARCH:
            vals = []
            for it in items:
                if field not in it:
                    continue
                try:
                    vals.append(float(it[field]))
                except (TypeError, ValueError):
                    pass
            row[f"{field}_mean"] = safe_mean(vals)
            row[f"{field}_median"] = safe_median(vals)
            row[f"{field}_std"] = safe_std(vals)
        summary.append(row)
    return summary


def write_csv(path: str, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def plot_alignment_bars(
    summary: list[dict[str, Any]],
    *,
    metric: str,
    threads_val: int,
    out_png: str,
    out_pdf: str,
    title_suffix: str,
    tier_filter: str | None = None,
) -> bool:
    sub_all = summary
    if tier_filter is not None:
        sub_all = [r for r in sub_all if str(r.get("tier", "custom")) == tier_filter]

    sub = [r for r in sub_all if int(r["threads"]) == threads_val]
    if not sub:
        return False
    datasets = sorted({r["dataset_label"] for r in sub}, key=lambda x: (len(x), x))
    tools = sorted({r["tool"] for r in sub})

    x = range(len(datasets))
    n_tools = max(len(tools), 1)
    width = 0.8 / n_tools

    fig, ax = plt.subplots(figsize=(max(6, len(datasets) * 1.2), 4))
    for ti, tool in enumerate(tools):
        heights = []
        errs = []
        for ds in datasets:
            cell = next(
                (r for r in sub if r["tool"] == tool and r["dataset_label"] == ds),
                None,
            )
            key_mean = f"{metric}_mean"
            key_std = f"{metric}_std"
            if cell and cell.get(key_mean) is not None:
                heights.append(cell[key_mean])
                errs.append(cell.get(key_std) or 0)
            else:
                heights.append(0)
                errs.append(0)
        offset = (ti - (n_tools - 1) / 2.0) * width
        pos = [xi + offset for xi in x]
        ax.bar(pos, heights, width=width * 0.9, yerr=errs, label=tool, capsize=2)

    ax.set_xticks(list(x))
    ax.set_xticklabels(datasets, rotation=15, ha="right")
    ax.set_ylabel(metric.replace("_", " "))
    ttl = f"Alignment benchmark ({title_suffix}, threads={threads_val})"
    if tier_filter is not None:
        ttl += f", tier={tier_filter}"
    ax.set_title(ttl)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(out_png, dpi=300)
    fig.savefig(out_pdf)
    plt.close(fig)
    return True


def plot_alignment_quality_scatter(summary: list[dict[str, Any]], out_png: str, out_pdf: str) -> bool:
    xs = []
    ys = []
    sizes = []
    labels = []
    for r in summary:
        wm = r.get("wall_seconds_mean")
        pm = r.get("avg_pid_mean")
        sc = r.get("seq_count") or 1
        if wm is None or pm is None:
            continue
        xs.append(wm)
        ys.append(pm)
        sizes.append(max(10, min(300, sc / 5)))
        tiers = str(r.get("tier", "custom"))
        labels.append(f'{r["tool"]}/{tiers}/{r["dataset_label"]}/t{r["threads"]}')

    if not xs:
        return False

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(xs, ys, s=sizes, alpha=0.65, edgecolors="k", linewidths=0.3)
    ax.set_xlabel("Mean wall time (s)")
    ax.set_ylabel("Mean avg pairwise identity")
    ax.set_title("Alignment quality vs speed (bubble ~ seq count; tier in legend label)")
    fig.tight_layout()
    fig.savefig(out_png, dpi=300)
    fig.savefig(out_pdf)
    plt.close(fig)
    return True


def plot_search_bars(summary: list[dict[str, Any]], metric: str, out_png: str, out_pdf: str) -> bool:
    sub = sorted(summary, key=lambda r: r["tool"])
    if not sub:
        return False
    tools = [r["tool"] for r in sub]
    key_mean = f"{metric}_mean"
    key_std = f"{metric}_std"
    heights = [r.get(key_mean) or 0 for r in sub]
    errs = [r.get(key_std) or 0 for r in sub]

    fig, ax = plt.subplots(figsize=(max(5, len(tools)), 4))
    ax.bar(tools, heights, yerr=errs, capsize=3, color="#4c72b0")
    ax.set_ylabel(metric.replace("_", " "))
    ax.set_title("Local protein search benchmark")
    fig.tight_layout()
    fig.savefig(out_png, dpi=300)
    fig.savefig(out_pdf)
    plt.close(fig)
    return True


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    u = len(a | b)
    if u == 0:
        return 1.0
    return len(a & b) / u


def search_jaccard_matrix(rows: list[dict[str, Any]]) -> tuple[list[str], list[list[float]]]:
    ok = [r for r in rows if r.get("study") == "search" and r.get("exit_code") == 0 and not r.get("timed_out")]
    by_tool_rep: dict[str, dict[int, set[str]]] = defaultdict(dict)
    for r in ok:
        tool = str(r["tool"])
        rep = int(r["repeat"])
        ids = r.get("top_hit_accessions") or []
        by_tool_rep[tool][rep] = set(ids)

    tools = sorted(by_tool_rep)
    reps = sorted({rep for mp in by_tool_rep.values() for rep in mp})
    n = len(tools)
    mat = [[1.0 if i == j else float("nan") for j in range(n)] for i in range(n)]

    for i, t1 in enumerate(tools):
        for j, t2 in enumerate(tools):
            if i >= j:
                continue
            scores: list[float] = []
            for rep in reps:
                a = by_tool_rep[t1].get(rep)
                b = by_tool_rep[t2].get(rep)
                if not a or not b:
                    continue
                scores.append(jaccard(a, b))
            v = mean(scores) if scores else float("nan")
            mat[i][j] = v
            mat[j][i] = v

    return tools, mat


def plot_search_heatmap(tools: list[str], mat: list[list[float]], out_png: str, out_pdf: str) -> bool:
    if len(tools) < 2:
        return False

    arr = np.asarray(mat, dtype=float)
    arr_disp = np.ma.masked_invalid(arr)

    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(arr_disp, vmin=0, vmax=1, cmap="viridis")
    ax.set_xticks(range(len(tools)))
    ax.set_yticks(range(len(tools)))
    ax.set_xticklabels(tools, rotation=35, ha="right")
    ax.set_yticklabels(tools)
    ax.set_title("Mean Jaccard overlap of top-hit accessions")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out_png, dpi=300)
    fig.savefig(out_pdf)
    plt.close(fig)
    return True


def write_report(
    out_md: str,
    *,
    alignment_csv: str | None,
    search_csv: str | None,
    figures: list[str],
):
    lines = ["# Comparative benchmark summary\n"]
    if alignment_csv:
        lines.append(f"- Alignment summary CSV: `{alignment_csv}`\n")
    if search_csv:
        lines.append(f"- Search summary CSV: `{search_csv}`\n")
    lines.append("\n## Figures\n")
    for figp in figures:
        base = os.path.basename(figp)
        lines.append(f"![{base}]({base})\n")
    os.makedirs(os.path.dirname(out_md) or ".", exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.writelines(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Aggregate benchmark JSONL into CSV + figures.")
    ap.add_argument("--alignment", help="Path to alignment.jsonl")
    ap.add_argument("--search", help="Path to search.jsonl")
    ap.add_argument("--outdir", default=os.path.join("benchmark_runs", "paper_figs"))
    args = ap.parse_args()

    if not args.alignment and not args.search:
        raise SystemExit("Provide at least one of --alignment or --search.")

    os.makedirs(args.outdir, exist_ok=True)
    figures_rel: list[str] = []

    alignment_summary: list[dict[str, Any]] = []
    search_summary: list[dict[str, Any]] = []
    search_rows: list[dict[str, Any]] = []

    if args.alignment:
        a_rows = read_jsonl(args.alignment)
        alignment_summary = summarize_alignment(a_rows)
        afields = [
            "tool",
            "dataset_label",
            "tier",
            "threads",
            "n",
            "seq_count",
        ]
        for fld in NUMERIC_FIELDS_ALIGNMENT:
            afields.extend([f"{fld}_mean", f"{fld}_median", f"{fld}_std"])
        acsv = os.path.join(args.outdir, "alignment_summary.csv")
        write_csv(acsv, afields, alignment_summary)

        thread_vals = sorted({int(r["threads"]) for r in alignment_summary})
        tiers_seen = sorted({str(r["tier"]) for r in alignment_summary}, key=tier_plot_sort_key)
        facet_by_tier = not (tiers_seen == ["custom"])
        for tv in thread_vals:
            tier_loop = tiers_seen if facet_by_tier else [None]
            for tier_opt in tier_loop:
                tier_filter = str(tier_opt) if facet_by_tier else None
                suffix = f"_tier_{tier_opt}" if facet_by_tier else ""
                base = os.path.join(args.outdir, f"alignment_wall_threads_{tv}{suffix}")
                if plot_alignment_bars(
                    alignment_summary,
                    metric="wall_seconds",
                    threads_val=tv,
                    out_png=base + ".png",
                    out_pdf=base + ".pdf",
                    title_suffix="wall time",
                    tier_filter=tier_filter,
                ):
                    figures_rel.append(os.path.basename(base + ".png"))
                base2 = os.path.join(args.outdir, f"alignment_peak_rss_threads_{tv}{suffix}")
                if plot_alignment_bars(
                    alignment_summary,
                    metric="peak_rss_mib",
                    threads_val=tv,
                    out_png=base2 + ".png",
                    out_pdf=base2 + ".pdf",
                    title_suffix="peak RSS",
                    tier_filter=tier_filter,
                ):
                    figures_rel.append(os.path.basename(base2 + ".png"))

        qpng = os.path.join(args.outdir, "alignment_quality_vs_speed.png")
        qpdf = os.path.join(args.outdir, "alignment_quality_vs_speed.pdf")
        if plot_alignment_quality_scatter(alignment_summary, qpng, qpdf):
            figures_rel.append(os.path.basename(qpng))

    if args.search:
        search_rows = read_jsonl(args.search)
        search_summary = summarize_search(search_rows)
        sfields = ["tool", "threads", "n"]
        for fld in NUMERIC_FIELDS_SEARCH:
            sfields.extend([f"{fld}_mean", f"{fld}_median", f"{fld}_std"])
        scsv = os.path.join(args.outdir, "search_summary.csv")
        write_csv(scsv, sfields, search_summary)

        sw = os.path.join(args.outdir, "search_wall_seconds")
        if plot_search_bars(search_summary, "wall_seconds", sw + ".png", sw + ".pdf"):
            figures_rel.append(os.path.basename(sw + ".png"))
        sr = os.path.join(args.outdir, "search_peak_rss_mib")
        if plot_search_bars(search_summary, "peak_rss_mib", sr + ".png", sr + ".pdf"):
            figures_rel.append(os.path.basename(sr + ".png"))

        tools, mat = search_jaccard_matrix(search_rows)
        hj = os.path.join(args.outdir, "search_hit_jaccard")
        if plot_search_heatmap(tools, mat, hj + ".png", hj + ".pdf"):
            figures_rel.append(os.path.basename(hj + ".png"))

    report_path = os.path.join(args.outdir, "report.md")
    write_report(
        report_path,
        alignment_csv=os.path.join(args.outdir, "alignment_summary.csv") if args.alignment else None,
        search_csv=os.path.join(args.outdir, "search_summary.csv") if args.search else None,
        figures=sorted(set(figures_rel)),
    )

    print(f"Wrote outputs under {args.outdir}")
    print(report_path)


if __name__ == "__main__":
    main()
