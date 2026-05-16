"""Unit tests for structure fetch helpers, sector→PDB mapping, and 3Dmol HTML builder."""

import pytest

from core.pysca_sector_model import MergedSector
from core.structure_fetch import validate_pdb_id
from core.structure_mapping import (
    ResidueColor,
    build_3dmol_html,
    map_pdb_residue_lists_to_colors,
    map_sector_position_lists_to_pdb,
    map_sector_positions_to_pdb,
    palette_for_merged,
)


def test_validate_pdb_id_normalizes():
    assert validate_pdb_id("1crn") == "1CRN"
    assert validate_pdb_id(" 8 A B c ") == "8ABC"
    assert validate_pdb_id("5p21") == "5P21"


def test_validate_pdb_id_rejects_bad():
    with pytest.raises(ValueError):
        validate_pdb_id("toolong")
    with pytest.raises(ValueError):
        validate_pdb_id("ab")


def test_palette_for_merged_hex_unique():
    m = [
        MergedSector(index=0, ic_indices=[0], items=[1, 2], col=0.15),
        MergedSector(index=1, ic_indices=[1], items=[3], col=0.65),
        MergedSector(index=2, ic_indices=[2], items=[4], col=0.92),
    ]
    pals = palette_for_merged(m)
    assert len(pals) == 3
    assert all(p.startswith("#") and len(p) == 7 for p in pals)
    assert len(set(pals)) == len(pals)


def test_map_sector_positions_to_pdb():
    merged = [
        MergedSector(index=0, ic_indices=[0], items=[0, 1], col=0.2),
        MergedSector(index=1, ic_indices=[1], items=[2], col=0.7),
    ]
    ats = ["A10", "B20", 30, "X99"]
    out = map_sector_positions_to_pdb(merged, ats, default_chain="Z")
    chains = {(r.chain, r.resnum) for r in out}
    assert ("A", 10) in chains
    assert ("B", 20) in chains
    assert ("Z", 30) in chains
    assert not any(r.resnum == 99 for r in out)


def test_map_sector_positions_empty_when_no_ats():
    merged = [MergedSector(index=0, ic_indices=[0], items=[0], col=0.2)]
    assert map_sector_positions_to_pdb(merged, None, "A") == []


def test_map_sector_position_lists_to_pdb():
    groups = [[0, 1], [2]]
    ats = ["A11", "A12", "A44"]
    out = map_sector_position_lists_to_pdb(groups, ats, "A")
    rs = {(r.resnum, r.sector_idx) for r in out}
    assert (11, 0) in rs and (12, 0) in rs and (44, 1) in rs


def test_map_pdb_residue_lists_to_colors():
    out = map_pdb_residue_lists_to_colors([[10, 11], [20]], "C")
    by_res = {(r.resnum, r.sector_idx) for r in out}
    assert by_res >= {(10, 0), (11, 0), (20, 1)}
    assert all(r.chain == "C" for r in out)


def test_build_3dmol_html_smoke(tmp_path, monkeypatch):
    """Ensure HTML references local bundle path and embeds payload."""
    import core.structure_mapping as sm

    fake_js = tmp_path / "3Dmol-min.js"
    fake_js.write_text("// stub", encoding="utf-8")
    monkeypatch.setattr(sm, "BUNDLE_JS", fake_js)

    html = build_3dmol_html(
        "HEADER    TEST\n",
        "pdb",
        [ResidueColor(chain="A", resnum=1, color="#ff0000", sector_idx=0)],
        "A",
        representation="cartoon",
    )
    assert "3Dmol-min.js" in html
    assert "viewport" in html
    assert "__STRUCTURE_VIEWER__" in html
    assert "focusChain" in html
    assert "setStyle" in html


def test_structure_viewer_widget_smoke_when_webengine_installed(qt_app):
    pytest.importorskip("PyQt5.QtWebEngineWidgets")
    from core.structure_mapping import bundled_3dmol_path
    from ui.widgets.structure_viewer_widget import StructureViewerWidget

    bundled_3dmol_path()

    w = StructureViewerWidget()
    assert w.has_viewer()
    w.set_structure("HEADER TEST\nEND\n", "pdb", "A")
    w.set_residue_colors(
        [ResidueColor(chain="A", resnum=1, color="#00ff00", sector_idx=0)]
    )
    w.set_representation("cartoon")


def test_build_3dmol_html_sidecar_smoke(tmp_path, monkeypatch):
    from pathlib import Path

    import core.structure_mapping as sm

    fake_js = tmp_path / "3Dmol-min.js"
    fake_js.write_text("// stub", encoding="utf-8")
    monkeypatch.setattr(sm, "BUNDLE_JS", fake_js)

    uri = Path(fake_js).resolve().as_uri()
    html = sm.build_3dmol_html_sidecar(
        "model.pdb",
        "pdb",
        [ResidueColor(chain="A", resnum=1, color="#ff0000", sector_idx=0)],
        "A",
        representation="cartoon",
        script_src_uri=uri,
    )
    assert "fetch" in html
    assert "model.pdb" in html
    assert uri in html
