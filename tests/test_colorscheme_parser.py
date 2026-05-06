"""Tests for XML color scheme loading."""

import tempfile
from pathlib import Path

from core.colorscheme_parser import (
    bundled_colorschemes_dir,
    list_bundled_schemes,
    load_colorscheme,
)


def test_list_bundled_schemes():
    names = list_bundled_schemes()
    assert "colprot_light-gp.xml" in names
    assert "colprot_light-gp1.xml" in names


def test_load_bundled_gp():
    path = bundled_colorschemes_dir() / "colprot_light-gp.xml"
    scheme = load_colorscheme(path)
    assert "RED" in scheme.palette
    assert scheme.palette["RED"].red() == 229
    assert len(scheme.consensus_conditions) > 0
    assert len(scheme.color_rules) > 0


def test_invalid_xml():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "bad.xml"
        p.write_text("<not_colorparam/>", encoding="utf-8")
        try:
            load_colorscheme(p)
        except ValueError as ex:
            assert "colorparam" in str(ex).lower()
        else:
            raise AssertionError("expected ValueError")
