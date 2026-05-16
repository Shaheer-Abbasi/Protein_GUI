"""Unit tests for core phylogenetic engine."""

import numpy as np
import pytest

from scipy.cluster.hierarchy import dendrogram

from core.phylo_engine import (
    compute_pairwise_identity,
    linkage_from_distance,
    extract_cluster_members,
    reference_branch_events,
    encode_msa,
)


def test_encode_msa_and_identity_basic():
    seqs = ["ACDEF", "AC-E-", "XX---"]
    enc, gap = encode_msa(seqs)
    assert enc.shape == (3, 5)
    assert gap[2, 2:].all()  # trailing gaps in third sequence
    I = compute_pairwise_identity(enc, gap)
    assert I[0, 0] == 1.0
    assert np.allclose(I, I.T)


def test_linkage_distance_and_fcluster():
    D = np.array(
        [
            [0.0, 0.2, 0.8],
            [0.2, 0.0, 0.5],
            [0.8, 0.5, 0.0],
        ]
    )
    Z = linkage_from_distance(D, method="average")
    assert Z.shape == (2, 4)
    memb = extract_cluster_members(Z, 0.4, ref_idx=0)
    assert set(memb.tolist()) == {0, 1}


def test_reference_branch_events_monotonic_sizes():
    rng = np.random.default_rng(0)
    n = 4
    D = rng.random((n, n))
    D = (D + D.T) / 2
    np.fill_diagonal(D, 0.0)
    Z = linkage_from_distance(D, method="average")
    ev = reference_branch_events(Z, n, ref_idx=1)
    assert ev.shape[0] >= 2
    assert ev[0, 0] == 0.0
    assert ev[0, 1] == 1.0


def test_dendrogram_smoke():
    pytest.importorskip("matplotlib.pyplot")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    D = np.array([[0, 0.1, 0.5], [0.1, 0, 0.3], [0.5, 0.3, 0]])
    Z = linkage_from_distance(D, method="average")
    fig, ax = plt.subplots()
    dendrogram(Z, ax=ax, labels=["a", "b", "c"])
    plt.close(fig)


def test_extract_singleton():
    Z = np.zeros((0, 4))
    memb = extract_cluster_members(Z, 0.0, 0)
    assert memb.tolist() == [0]

