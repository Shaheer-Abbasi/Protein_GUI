"""
Pairwise identity, hierarchical clustering, and reference-branch profiling for MSAs.

See plan: gap-aware identity, scipy linkage on distance = 1 - identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np

from utils.fasta_parser import FastaSequence

try:
    from scipy.cluster.hierarchy import fcluster, leaves_list, linkage
    from scipy.spatial.distance import squareform
except ImportError:  # pragma: no cover
    linkage = None  # type: ignore[assignment]
    squareform = None  # type: ignore[assignment]
    fcluster = None  # type: ignore[assignment]
    leaves_list = None  # type: ignore[assignment]

GAP_CHARS = set("-.*")

# Out-of-scope for v1 — memory / time guard
MAX_SEQUENCES = 5000

LINKAGE_METHODS = ("average", "complete", "single")


@dataclass
class MsaEncoding:
    """Aligned sequences as uint8 + gap mask (True = gap position)."""

    labels: List[str]
    headers: List[str]
    sequences: List[str]  # aligned, equal length
    encoded: np.ndarray  # (N, L) uint8; gaps stored as 0
    gap_mask: np.ndarray  # (N, L) bool


def sequences_to_msa(seqs: Sequence[FastaSequence]) -> Tuple[List[str], List[str], List[str]]:
    """Normalize headers, equal-length alignment with '-' padding."""
    labels = [s.id for s in seqs]
    raw_headers: List[str] = []
    for s in seqs:
        h = getattr(s, "header", None)
        if not h:
            raw_headers.append(f">{s.id}")
        else:
            raw_headers.append(h if h.startswith(">") else f">{h}")

    sequences = [s.sequence.replace(" ", "").upper() for s in seqs]
    if not sequences:
        return labels, raw_headers, []
    width = max(len(x) for x in sequences)
    sequences = [x.ljust(width, "-") for x in sequences]
    lengths = set(len(x) for x in sequences)
    if len(lengths) != 1:
        raise ValueError("Internal error: sequences not equal length after pad.")
    return labels, raw_headers, sequences


def encode_msa(sequences: Sequence[str]) -> Tuple[np.ndarray, np.ndarray]:
    """
    Map each column character to uint8. Gaps (- . *) and unknown map to gap_mask True.

    Identity uses only positions where both sequences are non-gap.
    """
    if not sequences:
        return np.zeros((0, 0), dtype=np.uint8), np.zeros((0, 0), dtype=bool)
    n = len(sequences)
    l = len(sequences[0])
    enc = np.zeros((n, l), dtype=np.uint8)
    gap = np.zeros((n, l), dtype=bool)
    for i, seq in enumerate(sequences):
        for j, c in enumerate(seq):
            ch = c.upper()
            if ch in GAP_CHARS or ch == " ":
                gap[i, j] = True
                enc[i, j] = 0
            else:
                enc[i, j] = ord(ch) & 0xFF
    return enc, gap


def build_msa_encoding(seqs: Sequence[FastaSequence]) -> MsaEncoding:
    labels, headers, sequences = sequences_to_msa(list(seqs))
    if not sequences:
        raise ValueError("No sequences in alignment.")
    enc, gap = encode_msa(sequences)
    return MsaEncoding(
        labels=labels,
        headers=headers,
        sequences=sequences,
        encoded=enc,
        gap_mask=gap,
    )


def compute_pairwise_identity(enc: np.ndarray, gap_mask: np.ndarray) -> np.ndarray:
    """
    Pairwise identity with pairwise gap exclusion (positions where either is gap ignored).

    identity(i,j) = matching non-gap columns / comparable non-gap columns
    Diagonal = 1.0
    """
    n, l = enc.shape
    out = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        out[i, i] = 1.0
        gi = gap_mask[i]
        si = enc[i]
        for j in range(i + 1, n):
            sj = enc[j]
            gj = gap_mask[j]
            valid = ~(gi | gj)
            cnt = int(np.count_nonzero(valid))
            if cnt == 0:
                v = 0.0
            else:
                same = (si == sj) & valid
                v = float(np.count_nonzero(same)) / float(cnt)
            out[i, j] = out[j, i] = v
    return out


def distance_from_identity(identity: np.ndarray) -> np.ndarray:
    """Symmetric distance matrix; diagonal stays 0."""
    d = 1.0 - np.asarray(identity, dtype=np.float64)
    np.fill_diagonal(d, 0.0)
    return d


def linkage_from_distance(D: np.ndarray, method: str = "average") -> np.ndarray:
    """Condensed linkage from full square distance matrix D (N x N)."""
    if linkage is None or squareform is None:
        raise RuntimeError("scipy is required for linkage.")
    if method not in LINKAGE_METHODS:
        raise ValueError(f"method must be one of {LINKAGE_METHODS}")
    d = np.asarray(D, dtype=np.float64)
    n = d.shape[0]
    if n < 2:
        return np.zeros((0, 4), dtype=np.float64)
    condensed = squareform(d, checks=False)
    return linkage(condensed, method=method)


def reference_branch_events(Z: np.ndarray, n: int, ref_idx: int) -> np.ndarray:
    """
    Each row: (merge_height, cluster_size) for merges where the new cluster contains ref.

    Returned array shape (k, 2), heights sorted ascending. Includes singleton state
    at height 0 with size 1 as first row for plotting.
    """
    if n <= 0:
        return np.zeros((0, 2))
    if n == 1:
        return np.array([[0.0, 1.0]], dtype=np.float64)

    z = np.asarray(Z, dtype=np.float64)
    rows = z.shape[0]
    if rows != n - 1:
        raise ValueError("Invalid linkage matrix shape.")

    contains = np.zeros(n + n - 1, dtype=bool)
    sizes = np.ones(n + n - 1, dtype=np.int64)
    contains[ref_idx] = True

    events: List[Tuple[float, int]] = [(0.0, 1)]

    for k in range(rows):
        a, b = int(z[k, 0]), int(z[k, 1])
        h = float(z[k, 2])
        new_id = n + k
        sz = int(z[k, 3])
        sizes[new_id] = sz
        merged = contains[a] or contains[b]
        contains[new_id] = merged
        if merged:
            events.append((h, sz))

    return np.array(events, dtype=np.float64)


def extract_cluster_members(Z: np.ndarray, threshold: float, ref_idx: int) -> np.ndarray:
    """
    Indices of sequences in the same cluster as ref at the given cophenetic-distance threshold.

    Uses scipy.fcluster criterion='distance' (same convention as dendrogram cut).
    """
    if fcluster is None:
        raise RuntimeError("scipy is required for fcluster.")
    z = np.asarray(Z)
    n = z.shape[0] + 1
    if n <= 1:
        return np.array([0], dtype=np.int64)
    labels = fcluster(z, t=threshold, criterion="distance")
    lab = labels[ref_idx]
    return np.where(labels == lab)[0]


def dendrogram_leaf_order(Z: np.ndarray) -> np.ndarray:
    """Leaf indices left-to-right for scipy dendrogram."""
    if leaves_list is None:
        raise RuntimeError("scipy is required.")
    if Z.size == 0:
        return np.array([0], dtype=np.int64)
    return np.asarray(leaves_list(Z), dtype=np.int64)


def fasta_subset(
    headers: Sequence[str],
    sequences: Sequence[str],
    indices: Sequence[int],
    keep_gaps: bool = True,
) -> str:
    """Build FASTA text for selected alignment rows."""
    lines: List[str] = []
    for i in indices:
        h = headers[i] if i < len(headers) else f">seq_{i}"
        if not h.startswith(">"):
            h = ">" + h.lstrip(">")
        seq = sequences[i]
        if not keep_gaps:
            seq = "".join(c for c in seq if c not in GAP_CHARS and c != " ")
        lines.append(h)
        for k in range(0, len(seq), 80):
            lines.append(seq[k : k + 80])
    return "\n".join(lines) + ("\n" if lines else "")


def run_phylo_analysis(
    seqs: Sequence[FastaSequence], method: str = "average"
) -> Tuple[MsaEncoding, np.ndarray, np.ndarray, np.ndarray]:
    """
    Parse MSA, compute identity, distance, linkage.

    Returns (encoding, identity, distance, Z).
    """
    if len(seqs) > MAX_SEQUENCES:
        raise ValueError(
            f"This version supports at most {MAX_SEQUENCES} sequences "
            f"(got {len(seqs)})."
        )
    if len(seqs) < 2:
        raise ValueError("Need at least two sequences for a phylogenetic tree.")

    msa = build_msa_encoding(seqs)
    ident = compute_pairwise_identity(msa.encoded, msa.gap_mask)
    dist = distance_from_identity(ident)
    z = linkage_from_distance(dist, method=method)
    return msa, ident, dist, z


def max_merge_height(Z: np.ndarray) -> float:
    if Z.size == 0:
        return 1.0
    return float(np.max(Z[:, 2]))
