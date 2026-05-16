"""Reference-free alignment quality metrics (FASTA MSAs)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np
from Bio import SeqIO


_GAP_CHARS = frozenset("-.")


def _seq_str_upper(record) -> str:
    return str(record.seq).upper()


@dataclass
class QualityMetrics:
    avg_pid: float
    gap_fraction: float
    mean_entropy: float


def _entropy_column(chars: np.ndarray) -> float:
    """Shannon entropy in bits over AA+gaps column distribution."""
    # chars as bytes / unicode length 1
    uniq, counts = np.unique(chars, return_counts=True)
    total = counts.sum()
    if total <= 0:
        return 0.0
    ent = 0.0
    for c in counts:
        if c <= 0:
            continue
        p = c / total
        ent -= p * math.log2(p)
    return float(ent)


def compute_quality(aligned_fasta_path: str, *, max_pairs: int = 500, seed: int = 42) -> QualityMetrics:
    """Compute average pairwise identity, gap fraction, and mean column entropy."""
    seqs = [_seq_str_upper(r) for r in SeqIO.parse(aligned_fasta_path, "fasta")]
    if not seqs:
        return QualityMetrics(avg_pid=float("nan"), gap_fraction=float("nan"), mean_entropy=float("nan"))

    lengths = {len(s) for s in seqs}
    if len(lengths) != 1:
        raise ValueError(
            "Aligned FASTA sequences must share one length for column-wise metrics "
            f"(found lengths {sorted(lengths)[:10]}…)."
        )

    n_seq = len(seqs)
    L = len(seqs[0])

    arr = np.array([list(s) for s in seqs], dtype="<U1")

    gap_frac_cols = []
    for j in range(L):
        col = arr[:, j]
        gaps = sum(1 for ch in col if ch in _GAP_CHARS or ch == "")
        gap_frac_cols.append(gaps / max(n_seq, 1))
    gap_fraction = float(np.mean(gap_frac_cols)) if gap_frac_cols else float("nan")

    ents = [_entropy_column(arr[:, j]) for j in range(L)]
    mean_entropy = float(np.mean(ents)) if ents else float("nan")

    rng = random.Random(seed)
    pairs_cap = min(max_pairs, n_seq * (n_seq - 1) // 2)
    if pairs_cap <= 0 or n_seq < 2:
        avg_pid = float("nan")
    else:
        ids = list(range(n_seq))
        pid_sum = 0.0
        sampled = 0
        seen = set()
        attempts = 0
        max_attempts = pairs_cap * 20
        while sampled < pairs_cap and attempts < max_attempts:
            attempts += 1
            i, k = rng.sample(ids, 2)
            if i > k:
                i, k = k, i
            key = (i, k)
            if key in seen:
                continue
            seen.add(key)
            a, b = seqs[i], seqs[k]
            matches = 0
            denom = 0
            for ca, cb in zip(a, b):
                ga = ca in _GAP_CHARS or ca == ""
                gb = cb in _GAP_CHARS or cb == ""
                if ga and gb:
                    continue
                if ga or gb:
                    denom += 1
                    continue
                denom += 1
                if ca == cb:
                    matches += 1
            pid_sum += matches / denom if denom > 0 else 0.0
            sampled += 1
        avg_pid = pid_sum / sampled if sampled > 0 else float("nan")

    return QualityMetrics(avg_pid=avg_pid, gap_fraction=gap_fraction, mean_entropy=mean_entropy)
