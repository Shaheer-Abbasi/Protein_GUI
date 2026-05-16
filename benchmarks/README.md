# Comparative benchmarks (alignment + local protein search)

Standalone harness under `benchmarks/` that mirrors command-line shapes used by the GUI workers ([`core/alignment_worker.py`](../core/alignment_worker.py), BLAST/MMseqs/DIAMOND workers). Produces JSONL logs, aggregated CSV tables, matplotlib figures (PNG + PDF), and `report.md`.

## Dependencies

Uses the project virtualenv / same requirements as the app (`biopython`, `matplotlib`, `numpy` via SciPy stack). External binaries must be installed or resolved via **Tools** paths (`core.tool_runtime.get_tool_runtime`).

## Tiered alignment (defaults: 2k / 100k / 500k)

Pfam-scale runs use a **single pooled FASTA** (default **ABC transporter Pfam PF00005**, ~millions of UniProt matches) with **reproducible reservoir subsets** (`seed=42`).

| Tier | Default *N* | Tools |
|------|-------------|--------|
| 1 | 2,000 | clustalo, mafft, muscle, famsa, famsa_gpu, twilight |
| 2 | 100,000 | famsa, famsa_gpu, twilight |
| 3 | 500,000 | famsa, famsa_gpu, twilight |

Sizes **≤ 10,000** sequences run **all** listed tools; larger tiers run **ultra-scale** tools only (`famsa`, `famsa_gpu`, `twilight`). Override sizes with **`--tiers`** (comma-separated list).

### 1) Download the family (once)

Streams gzip from **UniProt REST** (no extra deps; `urllib`). File is large for PF00005; use **PF00069** or another family if you need a quicker smoke test.

```bash
python -m benchmarks.download_datasets --pfam-id PF00005 --out-dir benchmark_data
```

- Output: `benchmark_data/PF00005_raw.fasta.gz` and decompressed `benchmark_data/PF00005_raw.fasta`
- Existing gzip is **skipped** unless you pass `--force`
- `--skip-decompress` keeps only the `.gz`
- **User-Agent**: set in `benchmarks.datasets` (UniProt requests identify the client)

### 2) Run all tiers (one JSONL)

```bash
python -m benchmarks.run_tiered \
  --source benchmark_data/PF00005_raw.fasta \
  --threads 1,4,8 \
  --repeats 3 \
  --work-dir benchmark_runs/tiered/data \
  --out-dir benchmark_runs/tiered
```

- Writes `benchmark_runs/tiered/alignment.jsonl` — every row includes **`tier`** (`"1"`, `"2"`, …) plus the usual alignment fields.
- Default **`--tiers`** is `2000,100000,500000`; pass any comma-separated list (e.g. `--tiers 100` for a smoke test).
- **`famsa_gpu`** is skipped when CUDA is unavailable (same as the non-tiered driver).
- Large alignments (**> 50k sequences**): quality metrics are omitted with `quality_skipped` to avoid huge post-processing cost.

### 3) Aggregate (tier-aware figures + CSV)

```bash
python -m benchmarks.aggregate \
  --alignment benchmark_runs/tiered/alignment.jsonl \
  --outdir benchmark_runs/tiered/paper_figs
```

When `tier` is not only `"custom"`, bar charts are emitted **per tier**, e.g. `alignment_wall_threads_8_tier_3.png`. `alignment_summary.csv` includes a **`tier`** column.

## Remote GPU / large runs (RunPod, SSH, HPC)

- **Dataset**: clone the repo + venv on the GPU host and run `python -m benchmarks.download_datasets` there once; copy `benchmark_data/` onto persistent volume if the pod recycles.
- **Tools**: ensure `PATH` resolves FAMSA (GPU build), Twilight, etc., or configure the same executable resolution the GUI uses.
- **Smoke test on small family**: `--pfam-id PF00069` before committing to PF00005 download time / disk.
- **JSONL**: `scp`/`rsync` the completed `benchmark_runs/tiered/` directory back for aggregation on your laptop.

## Alignment sweep (classic harness)

Every JSONL row includes **`tier`**; the default standalone driver sets **`--tier custom`**.

From the repo root:

```bash
python -m benchmarks.alignment \
  --input resources/sample_fasta/gamma_phylogeny_sort_3.fasta \
  --sizes 50,200,full \
  --tools clustalo,mafft,muscle,famsa,twilight \
  --threads 1,4,8 \
  --repeats 3 \
  --warmup 1 \
  --tier custom \
  --work-dir benchmark_runs/data \
  --out benchmark_runs/alignment.jsonl
```

- **FAMSA GPU** (`famsa_gpu`) is skipped automatically when CUDA is not detected (`nvidia-smi`).
- Session metadata (host + tool versions): `benchmark_runs/alignment_session_meta.json` (tiered runner writes under `--out-dir`).

Metrics per row: wall time, sampled peak RSS (MiB), and optional reference-free alignment metrics (`avg_pid`, `gap_fraction`, `mean_entropy`) when the aligner exits cleanly.

## Local protein search

Requires a **local BLAST-formatted** database prefix (`*.phr` / `*.00.phr`) for `--db-type blast`. MMseqs benchmarks reuse the GUI pipeline: one-time BLAST→FASTA→`mmseqs createdb` conversion into `--work-dir/mmseqs_target_db` (not timed per query repeat). DIAMOND builds `<prefix>.dmnd` once via `blastdbcmd` + `diamond makedb` when missing.

```bash
python -m benchmarks.search \
  --query resources/sample_fasta/gamma_phylogeny_sort_3.fasta \
  --db /path/to/swissprot \
  --db-type blast \
  --tools blastp,mmseqs,mmseqs_gpu,diamond \
  --top-k 100 \
  --repeats 3 \
  --warmup 1 \
  --work-dir benchmark_runs/search_tmp \
  --out benchmark_runs/search.jsonl
```

Use `--db-type mmseqs` when `--db` already points at an MMseqs DB prefix (must have `.dbtype`). **MMseqs GPU** is skipped when CUDA is unavailable.

Search rows store `top_hit_accessions` for Jaccard overlap figures during aggregation.

## Aggregate CSV + figures + markdown

```bash
python -m benchmarks.aggregate \
  --alignment benchmark_runs/alignment.jsonl \
  --search benchmark_runs/search.jsonl \
  --outdir benchmark_runs/paper_figs
```

Either input may be omitted. Outputs:

- `alignment_summary.csv`, `search_summary.csv`
- PNG + PDF plots (wall time, peak RSS; alignment charts faceted **by tier** when present, alignment quality scatter, search heatmap)
- `report.md` embedding figure basenames

## Interpreting RSS numbers

Peak RSS is sampled during each subprocess via `/proc/<pid>/VmHWM` (Linux) or `ps` (macOS). Compare runs on the **same OS/hardware**; multi-process pipelines (MMseqs CPU: `createdb` + `search` + `convertalis`) report the **maximum** sampled RSS across steps and summed wall time.
