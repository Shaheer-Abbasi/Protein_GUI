"""Download Pfam-aligned UniProt FASTA dumps for alignment benchmarks."""

from __future__ import annotations

import argparse
import os
import sys

from benchmarks.datasets import (
    count_sequences,
    decompress_gzip_to_fasta,
    download_pfam_fasta,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Download a Pfam family's UniProt FASTA (streaming gzip) for benchmarks.",
    )
    ap.add_argument("--pfam-id", default="PF00005", help="Pfam accession (default PF00005, ABC transporter)")
    ap.add_argument(
        "--out-dir",
        default="benchmark_data",
        help='Output directory (default "benchmark_data/")',
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if gzip output already exists",
    )
    ap.add_argument(
        "--skip-decompress",
        action="store_true",
        help="Keep only the .fasta.gz file (no gunzip step)",
    )
    args = ap.parse_args()

    pid = args.pfam_id.strip().upper()
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    base = f"{pid}_raw"
    gz_path = os.path.join(out_dir, f"{base}.fasta.gz")
    fasta_path = os.path.join(out_dir, f"{base}.fasta")

    print(f"Pfam {pid} -> {gz_path}", file=sys.stderr)
    download_pfam_fasta(pid, gz_path, force=args.force)

    if not args.skip_decompress:
        need_decompress = args.force or not os.path.isfile(fasta_path)
        if not need_decompress:
            print(f"FASTA already exists: {fasta_path} (use --force to re-gunzip)", file=sys.stderr)
        else:
            print("Decompressing...", file=sys.stderr)
            decompress_gzip_to_fasta(gz_path, fasta_path)
        nc = count_sequences(fasta_path)
        print(f"Sequences in {fasta_path}: {nc}", file=sys.stderr)
    else:
        print("Skipped decompress (--skip-decompress).", file=sys.stderr)

    print("Done.")
    print(f"gzip:   {gz_path}")
    if not args.skip_decompress:
        print(f"fasta:  {fasta_path}")


if __name__ == "__main__":
    main()
