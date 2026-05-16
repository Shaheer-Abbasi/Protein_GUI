"""FASTA helpers for benchmark datasets."""

from __future__ import annotations

import gzip
import os
import random
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord

# UniProt asks for a descriptive User-Agent (https://www.uniprot.org/help/api)
_DEFAULT_UA = "Protein_GUI-benchmarks/1.0 (https://github.com/; academic research)"


def count_sequences(fasta_path: str) -> int:
    """Return number of records in *fasta_path*."""
    n = 0
    for _ in SeqIO.parse(fasta_path, "fasta"):
        n += 1
    return n


def subset_fasta(
    fasta_path: str,
    n: int,
    out_path: str,
    *,
    seed: int = 42,
) -> int:
    """Uniform random sample of up to *n* sequences (single pass, **reservoir**).

    Safe for very large source FASTAs (e.g. multi-million UniProt family dumps)
    without loading all records into memory.

    Returns the number of sequences written.
    """
    if n <= 0:
        raise ValueError(f"Subset size must be positive, got {n}")

    rng = random.Random(seed)
    reservoir: list[SeqRecord] = []
    total = 0

    for rec in SeqIO.parse(fasta_path, "fasta"):
        total += 1
        if len(reservoir) < n:
            reservoir.append(rec)
        else:
            j = rng.randint(1, total)
            if j <= n:
                reservoir[j - 1] = rec

    k = len(reservoir)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    if not reservoir:
        Path(out_path).write_text("", encoding="utf-8")
        return 0

    SeqIO.write(reservoir, out_path, "fasta")
    return k


def prepare_size_ladder(
    fasta_path: str,
    sizes: Iterable[int | str],
    work_dir: str,
    *,
    seed: int = 42,
) -> list[tuple[str, str, int]]:
    """Materialise FASTA subsets for each ladder entry.

    Each entry is either a positive int (subset count) or the string ``\"full\"``.

    Returns ``[(label, path, seq_count), ...]`` where *label* is e.g. ``\"n50\"`` or ``\"full\"``.
    """
    os.makedirs(work_dir, exist_ok=True)
    src = Path(fasta_path).resolve()
    out: list[tuple[str, str, int]] = []

    for entry in sizes:
        if isinstance(entry, str):
            lab = entry.strip().lower()
            if lab != "full":
                raise ValueError(f"Unknown size token: {entry!r} (expected int or 'full')")
            dst = os.path.join(work_dir, "full.fasta")
            shutil.copy2(src, dst)
            nc = count_sequences(dst)
            out.append(("full", dst, nc))
            continue

        ni = int(entry)
        if ni <= 0:
            raise ValueError(f"Subset size must be positive, got {ni}")
        label = f"n{ni}"
        dst = os.path.join(work_dir, f"{label}.fasta")
        wrote = subset_fasta(str(src), ni, dst, seed=seed)
        out.append((label, dst, wrote))

    return out


def uniprot_pfam_stream_url(pfam_id: str) -> str:
    pid = pfam_id.strip().upper()
    if not pid.startswith("PF") or len(pid) < 3:
        raise ValueError(f"Invalid Pfam accession: {pfam_id!r}")
    q = f"(xref:pfam-{pid})"
    return "https://rest.uniprot.org/uniprotkb/stream?" + urllib.parse.urlencode(
        {"query": q, "format": "fasta", "compressed": "true"}
    )


def download_pfam_fasta(
    pfam_id: str,
    out_gz_path: str,
    *,
    force: bool = False,
    user_agent: str = _DEFAULT_UA,
    progress_every_bytes: int = 50 * 1024 * 1024,
) -> str:
    """Stream-download UniProt FASTA (gzip) for proteins matching *pfam_id*.

    Writes *out_gz_path* (``.fasta.gz``). Returns the path written.

    Uses the UniProt REST ``/uniprotkb/stream`` endpoint with ``compressed=true``.
    """
    out_gz_path = os.path.abspath(out_gz_path)
    if os.path.isfile(out_gz_path) and not force:
        return out_gz_path

    os.makedirs(os.path.dirname(out_gz_path) or ".", exist_ok=True)
    url = uniprot_pfam_stream_url(pfam_id)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})

    tmp = out_gz_path + ".part"
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            total = 0
            with open(tmp, "wb") as out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    total += len(chunk)
                    if progress_every_bytes and total % progress_every_bytes < len(chunk):
                        print(f"  ... downloaded {total / (1024**2):.1f} MiB", file=sys.stderr)
        os.replace(tmp, out_gz_path)
    except urllib.error.HTTPError as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise RuntimeError(f"UniProt HTTP {e.code}: {e.reason}. URL query may be invalid.") from e
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    print(f"Wrote {out_gz_path} ({os.path.getsize(out_gz_path) / (1024**2):.1f} MiB gzip)", file=sys.stderr)
    return out_gz_path


def decompress_gzip_to_fasta(
    gz_path: str,
    fasta_out: str,
    *,
    progress_every_bytes: int = 512 * 1024 * 1024,
) -> None:
    """Gunzip a ``.fasta.gz`` to plain FASTA (streaming)."""
    fasta_out = os.path.abspath(fasta_out)
    os.makedirs(os.path.dirname(fasta_out) or ".", exist_ok=True)
    tmp = fasta_out + ".part"
    total = 0
    next_report = progress_every_bytes if progress_every_bytes else 0
    with gzip.open(gz_path, "rb") as zf, open(tmp, "wb") as out:
        while True:
            chunk = zf.read(8 * 1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            total += len(chunk)
            if progress_every_bytes and total >= next_report:
                print(f"  ... wrote {total / (1024**2):.1f} MiB (raw FASTA)", file=sys.stderr)
                while total >= next_report:
                    next_report += progress_every_bytes
    os.replace(tmp, fasta_out)
    print(f"Wrote {fasta_out} ({os.path.getsize(fasta_out) / (1024**2):.1f} MiB)", file=sys.stderr)
