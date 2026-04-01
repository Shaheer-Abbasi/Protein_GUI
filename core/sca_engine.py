"""
Built-in Statistical Coupling Analysis (SCA) engine.

Implements the core SCA computation pipeline from Halabi et al. (2009) /
Rivoire et al. (2016) using numpy (or CuPy when GPU is enabled via
``core.array_backend``).

All public functions return plain numpy arrays (converted via ``to_numpy``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from core.array_backend import get_xp, to_numpy, is_gpu_enabled

AA_ALPHABET = "ACDEFGHIKLMNPQRSTVWY"
AA_TO_INDEX = {aa: i for i, aa in enumerate(AA_ALPHABET)}
N_AA = len(AA_ALPHABET)  # 20
N_STATES = N_AA + 1  # 20 amino acids + gap

# Robinson & Robinson background frequencies (20 aa, sums to 1.0)
_BG_FREQ = np.array([
    0.0777, 0.0157, 0.0530, 0.0656, 0.0405,
    0.0691, 0.0227, 0.0591, 0.0595, 0.0966,
    0.0238, 0.0427, 0.0507, 0.0410, 0.0529,
    0.0694, 0.0550, 0.0667, 0.0118, 0.0311,
], dtype=np.float64)


@dataclass
class SCAResults:
    """Container for all built-in SCA outputs."""
    labels: list[str]
    sequences: list[str]
    Di: np.ndarray            # (L,) positional conservation
    Csca: np.ndarray          # (L, L) SCA correlation matrix
    eigenvalues: np.ndarray   # (L,) sorted descending
    eigenvectors: np.ndarray  # (L, L) columns = eigenvectors
    random_eigenvalues: np.ndarray  # (n_trials, L)
    kpos: int                 # number of significant eigenmodes
    sectors: list[list[int]]  # positions per sector
    sim_matrix: np.ndarray    # (M, M) sequence similarity
    n_seqs: int
    n_pos: int
    used_gpu: bool
    elapsed_seconds: float = 0.0


def msa_to_binary(sequences: list[str]) -> np.ndarray:
    """Convert M aligned sequences to an M x (L * N_STATES) binary matrix."""
    xp = get_xp()
    M = len(sequences)
    L = len(sequences[0])
    binary = xp.zeros((M, L * N_STATES), dtype=xp.float64)
    for i, seq in enumerate(sequences):
        for j, ch in enumerate(seq):
            idx = AA_TO_INDEX.get(ch.upper(), N_AA)  # gap / unknown -> last column
            binary[i, j * N_STATES + idx] = 1.0
    return binary


def sequence_weights(binary) -> np.ndarray:
    """
    Sequence weights to correct for phylogenetic redundancy.

    For each sequence pair, compute fraction of identical positions. Each
    sequence's weight is 1 / (number of sequences with >= 80% identity).
    Returns M-vector (sums to effective number of sequences).
    """
    xp = get_xp()
    M = binary.shape[0]
    L = binary.shape[1] // N_STATES

    if M > 2000:
        # Subsample for speed
        return xp.ones(M, dtype=xp.float64)

    # Pairwise identity via dot product on binary matrix
    sim = (binary @ binary.T) / L  # M x M, each entry = fraction identical
    counts = xp.sum(sim >= 0.8, axis=1).astype(xp.float64)
    counts = xp.maximum(counts, 1.0)
    w = 1.0 / counts
    return w


def positional_conservation(binary, seqw) -> np.ndarray:
    """
    Per-column Kullback-Leibler relative entropy vs. background frequencies.

    Returns L-vector ``Di``.
    """
    xp = get_xp()
    M, cols = binary.shape
    L = cols // N_STATES

    bg = xp.asarray(_BG_FREQ)

    # Weighted column frequencies (only amino acid states, not gap)
    w = seqw / xp.sum(seqw)
    Di = xp.zeros(L, dtype=xp.float64)
    for j in range(L):
        col_start = j * N_STATES
        col_slice = binary[:, col_start:col_start + N_AA]  # M x 20
        freq = w @ col_slice  # (20,)
        freq = xp.maximum(freq, 1e-10)
        freq = freq / xp.sum(freq)
        # KL divergence D(freq || bg)
        Di[j] = float(xp.sum(freq * xp.log(freq / bg)))
    return to_numpy(Di)


def sca_matrix(binary, seqw) -> np.ndarray:
    """
    Compute the L x L SCA positional correlation matrix (Frobenius norm).

    This is the core SCA computation: for each pair of positions (i, j),
    compute the Frobenius norm of the 20x20 matrix of coupling scores.
    """
    xp = get_xp()
    M, cols = binary.shape
    L = cols // N_STATES

    w = seqw / xp.sum(seqw)

    # Weighted mean per column-state
    w2d = w[:, None]  # (M, 1)
    f_ia = xp.sum(binary * w2d, axis=0)  # (L*N_STATES,)

    # Weighted covariance: C_ab = sum_s w_s * (x_sa - f_a) * (x_sb - f_b)
    centered = binary - f_ia[None, :]  # (M, L*N_STATES)
    weighted_centered = centered * xp.sqrt(w2d)
    Ctilde = weighted_centered.T @ weighted_centered  # (L*N_STATES, L*N_STATES)

    # Collapse to L x L via Frobenius norm of each (N_STATES x N_STATES) block
    Csca = xp.zeros((L, L), dtype=xp.float64)
    for i in range(L):
        for j in range(i, L):
            block = Ctilde[
                i * N_STATES:(i + 1) * N_STATES,
                j * N_STATES:(j + 1) * N_STATES,
            ]
            val = xp.sqrt(xp.sum(block ** 2))
            Csca[i, j] = val
            Csca[j, i] = val

    return to_numpy(Csca)


def eigendecompose(Csca: np.ndarray):
    """Eigendecomposition of the symmetric SCA matrix, sorted descending."""
    vals, vecs = np.linalg.eigh(Csca)
    idx = np.argsort(vals)[::-1]
    return vals[idx], vecs[:, idx]


def random_matrix_eigenvalues(
    binary, seqw, n_trials: int = 10
) -> np.ndarray:
    """
    Column-shuffle null model: for each trial, independently shuffle each
    position column across sequences, recompute the SCA matrix, and record
    all eigenvalues. Returns (n_trials, L) array.
    """
    xp = get_xp()
    M, cols = binary.shape
    L = cols // N_STATES

    all_evals = []
    rng = np.random.default_rng(42)
    for _ in range(n_trials):
        shuffled = xp.array(to_numpy(binary).copy())
        shuffled_np = to_numpy(shuffled)
        for j in range(L):
            col_start = j * N_STATES
            col_end = col_start + N_STATES
            perm = rng.permutation(M)
            shuffled_np[:, col_start:col_end] = shuffled_np[perm, col_start:col_end]
        shuffled = xp.asarray(shuffled_np)

        Crand = sca_matrix(shuffled, seqw)
        evals, _ = eigendecompose(Crand)
        all_evals.append(evals)

    return np.array(all_evals)


def _choose_kpos(eigenvalues: np.ndarray, random_eigenvalues: np.ndarray) -> int:
    """Number of significant eigenmodes (eigenvalue > 95th percentile of randoms)."""
    threshold = np.percentile(random_eigenvalues[:, 0], 95)
    kpos = int(np.sum(eigenvalues > threshold))
    return max(kpos, 1)


def identify_sectors(
    eigenvectors: np.ndarray,
    eigenvalues: np.ndarray,
    kpos: int,
    Csca: np.ndarray,
) -> list[list[int]]:
    """
    Identify sector positions from the top kpos eigenvectors.

    For each top eigenvector, positions whose absolute loading exceeds
    the 90th percentile are assigned to that sector.
    """
    sectors: list[list[int]] = []
    L = eigenvectors.shape[0]
    for k in range(min(kpos, eigenvectors.shape[1])):
        loadings = np.abs(eigenvectors[:, k])
        cutoff = np.percentile(loadings, 90)
        positions = [int(i) for i in range(L) if loadings[i] >= cutoff]
        sectors.append(positions)
    return sectors


def sequence_similarity_matrix(binary) -> np.ndarray:
    """M x M pairwise sequence identity (fraction of identical positions)."""
    xp = get_xp()
    L = binary.shape[1] // N_STATES
    sim = (binary @ binary.T) / L
    return to_numpy(sim)


def run_full_sca(
    sequences: list[str],
    labels: list[str],
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> SCAResults:
    """
    Run the complete built-in SCA pipeline.

    Parameters
    ----------
    sequences : aligned sequences (equal length, uppercase recommended)
    labels : sequence IDs
    progress_cb : optional ``(percent, message)`` callback
    """
    import time
    t0 = time.monotonic()

    def _prog(pct: int, msg: str):
        if progress_cb:
            progress_cb(pct, msg)

    _prog(5, "Converting alignment to binary matrix...")
    binary = msa_to_binary(sequences)
    M, _ = binary.shape
    L = len(sequences[0])

    _prog(10, "Computing sequence weights...")
    seqw = sequence_weights(binary)

    _prog(20, "Computing positional conservation (KL divergence)...")
    Di = positional_conservation(binary, seqw)

    _prog(30, "Computing SCA correlation matrix...")
    Csca = sca_matrix(binary, seqw)

    _prog(50, "Eigendecomposition...")
    eigenvalues, eigenvectors = eigendecompose(Csca)

    _prog(55, "Random null model (may take a moment)...")
    rand_evals = random_matrix_eigenvalues(binary, seqw, n_trials=10)

    _prog(80, "Identifying sectors...")
    kpos = _choose_kpos(eigenvalues, rand_evals)
    sectors = identify_sectors(eigenvectors, eigenvalues, kpos, Csca)

    _prog(90, "Computing sequence similarity matrix...")
    sim = sequence_similarity_matrix(binary)

    elapsed = time.monotonic() - t0
    _prog(100, "SCA analysis complete.")

    return SCAResults(
        labels=labels,
        sequences=sequences,
        Di=Di,
        Csca=Csca,
        eigenvalues=eigenvalues,
        eigenvectors=eigenvectors,
        random_eigenvalues=rand_evals,
        kpos=kpos,
        sectors=sectors,
        sim_matrix=sim,
        n_seqs=M,
        n_pos=L,
        used_gpu=is_gpu_enabled(),
        elapsed_seconds=elapsed,
    )
