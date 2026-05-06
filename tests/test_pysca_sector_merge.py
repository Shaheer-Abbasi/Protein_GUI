"""Tests for pySCA I/O, sector merge, and validation."""

import numpy as np
import pytest

from core.pysca_io import load_pysca_db
from core.pysca_sector_model import (
    merge_ics_to_sectors,
    default_sec_groups,
    validate_sec_groups,
    format_sec_groups_display,
    parse_sec_groups_literal,
)


class _U:
    def __init__(self, items, vec):
        self.items = items
        self.vec = vec


def test_default_sec_groups():
    assert default_sec_groups(0) == []
    assert default_sec_groups(3) == [[0], [1], [2]]


def test_format_sec_groups_display():
    assert format_sec_groups_display([]) == "()"
    assert format_sec_groups_display([[0], [1, 2]]) == "([0], [1, 2])"


def test_parse_sec_groups_literal():
    assert parse_sec_groups_literal("") == []
    assert parse_sec_groups_literal("   ") == []
    assert parse_sec_groups_literal("([0], [1])") == [[0], [1]]
    assert parse_sec_groups_literal("([0, 1], [2])") == [[0, 1], [2]]
    with pytest.raises(ValueError):
        parse_sec_groups_literal("{0: 1}")
    with pytest.raises(ValueError):
        parse_sec_groups_literal("([0], 'x')")


def test_parse_sec_groups_literal_validate_integration():
    groups = parse_sec_groups_literal("([0, 1], [2])")
    assert validate_sec_groups(3, groups) is None
    dup = parse_sec_groups_literal("([0], [0])")
    assert validate_sec_groups(2, dup) is not None


def test_validate_sec_groups():
    err = validate_sec_groups(2, [[0, 1], [0]])
    assert err is not None
    assert validate_sec_groups(3, [[0, 1], [2]]) is None
    err2 = validate_sec_groups(2, [[0, 1, 2]])
    assert "out of range" in (err2 or "")


def test_merge_ics_to_sectors():
    Dsect = {
        "kpos": 2,
        "ics": [
            _U([2, 0, 1], [0.3, 0.1, 0.2]),
            _U([3, 4], [0.0, 0.5]),
        ],
    }
    merged, sortpos = merge_ics_to_sectors(Dsect, [[0], [1]])
    assert len(merged) == 2
    # Vectors [0.3,0.1,0.2] at [2,0,1] -> argsort by vec -> [1,0,2] for positions
    assert merged[0].items == [0, 1, 2]
    assert set(sortpos) == {0, 1, 2, 3, 4}


def test_load_pysca_minimal_roundtrip(tmp_path):
    """Three-level dict (sequence/sca/sector) loads without error."""
    p = tmp_path / "t.db"
    data = {
        "sequence": {"Npos": 3, "Nseq": 2, "ats": ["A", "B", "C"]},
        "sca": {
            "Csca": np.eye(3),
            "Di": np.array([0.1, 0.2, 0.1]),
        },
        "sector": {
            "kpos": 1,
            "Vpica": np.random.randn(3, 1) * 0.01,
            "Vsca": np.random.randn(3, 1) * 0.01,
        },
    }
    import pickle

    with open(p, "wb") as f:
        pickle.dump(data, f)

    out = load_pysca_db(p)
    assert out.Dseq["Npos"] == 3
    assert out.Dsca["Csca"].shape == (3, 3)
    assert out.Dsect["kpos"] == 1


def test_draw_conservation_smoke():
    pytest.importorskip("matplotlib.pyplot")
    from core.pysca_notebook_plots import draw_conservation_figure

    th = {
        "bg_primary": "#0F1117",
        "text_primary": "#E5E8EB",
        "text_muted": "#6C7A89",
        "border": "#2A2D3E",
        "accent": "#5DADE2",
    }
    Dseq = {"Npos": 3, "ats": ["A", "B", "C"]}
    Dsca = {"Di": np.array([0.1, 0.2, 0.3])}
    Dsect = {}
    fig = draw_conservation_figure(Dseq, Dsca, Dsect, th)
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close(fig)
