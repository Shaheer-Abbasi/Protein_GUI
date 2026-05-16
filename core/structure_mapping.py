"""Map pySCA sector alignment columns -> PDB residues; build offline 3Dmol HTML."""

from __future__ import annotations

import base64
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from matplotlib import colors as mcolors

from core.pysca_sector_model import MergedSector


@dataclass(frozen=True)
class ResidueColor:
    chain: str
    resnum: int
    color: str  # "#RRGGBB"
    sector_idx: int


def palette_for_merged(merged: Sequence[MergedSector]) -> List[str]:
    """One hex colour per merged sector (stable from ``MergedSector.col`` as hue)."""
    out: List[str] = []
    for m in merged:
        h = float(m.col) % 1.0
        if h < 1e-6:
            h = 1e-6
        rgb = mcolors.hsv_to_rgb([h, 0.82, 0.92])
        out.append(mcolors.to_hex(rgb))
    return out


def _parse_ats_entry(entry: Any, default_chain: str) -> Tuple[str, Optional[int]]:
    """
    Infer (chain, residue_number) from a pySCA ``ats[i]`` label.

    Integers → ``(default_chain, n)``.
    Strings parsed heuristically for ``A71``-style labels.
    """
    if entry is None:
        return default_chain, None
    if isinstance(entry, (int, np.integer)):
        return default_chain, int(entry)

    raw = str(entry).strip().upper().replace(" ", "")
    if not raw:
        return default_chain, None

    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return default_chain, None
    n = int(digits)

    # Leading single letter then number: A45, B107
    if len(raw) >= 2 and raw[0].isalpha() and raw[1].isdigit():
        return raw[0].upper(), n

    return default_chain, n


def map_sector_position_lists_to_pdb(
    column_groups: Sequence[Sequence[int]],
    ats: Optional[Sequence[Any]],
    default_chain: str,
) -> List[ResidueColor]:
    """
    Interpret *column_groups* as manual sector definitions: each inner list holds
    alignment column indices mapped through ``ats`` like ``MergedSector.items``.
    """
    if not column_groups or ats is None:
        return []
    n = len(column_groups)
    merged: List[MergedSector] = []
    for i, g in enumerate(column_groups):
        items = sorted({int(x) for x in g})
        hue = min((i + 1) / max(n, 1), 0.999)
        merged.append(
            MergedSector(index=i, ic_indices=[i], items=items, col=hue),
        )
    return map_sector_positions_to_pdb(merged, ats, default_chain)


def map_pdb_residue_lists_to_colors(
    sector_residue_numbers: Sequence[Sequence[int]],
    chain: str,
) -> List[ResidueColor]:
    """
    Colour residues when each inner list already holds PDB residue numbers (same chain).

    Sector hues match the usual merged-sector palette (count-based).
    """
    if not sector_residue_numbers:
        return []
    n = len(sector_residue_numbers)
    ch = (chain or "A").strip() or "A"
    fake_for_palette = [
        MergedSector(index=i, ic_indices=[i], items=[], col=min((i + 1) / max(n, 1), 0.999))
        for i in range(n)
    ]
    pals = palette_for_merged(fake_for_palette)
    keyed: Dict[Tuple[str, int], ResidueColor] = {}
    for si, residues in enumerate(sector_residue_numbers):
        if si >= len(pals):
            break
        c = pals[si]
        for r in residues:
            keyed[(ch, int(r))] = ResidueColor(
                chain=ch, resnum=int(r), color=c, sector_idx=si,
            )
    return [keyed[k] for k in sorted(keyed)]


def map_sector_positions_to_pdb(
    merged: Sequence[MergedSector],
    ats: Optional[Sequence[Any]],
    default_chain: str,
) -> List[ResidueColor]:
    """Convert merged sector alignment column indices → residues to colour."""
    if not merged or ats is None:
        return []
    at_list = list(ats)
    dc = (default_chain or "A").strip() or "A"
    pals = palette_for_merged(merged)

    keyed: Dict[Tuple[str, int], ResidueColor] = {}
    for mi, sector in enumerate(merged):
        if mi >= len(pals):
            break
        col_hex = pals[mi]
        for col in sector.items:
            if col < 0 or col >= len(at_list):
                continue
            ch, resnum = _parse_ats_entry(at_list[col], dc)
            if resnum is None:
                continue
            keyed[(ch, resnum)] = ResidueColor(
                chain=ch, resnum=resnum, color=col_hex, sector_idx=sector.index
            )
    return [keyed[k] for k in sorted(keyed)]


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_JS = PROJECT_ROOT / "resources" / "js" / "3Dmol-min.js"

# Above this size, inline base64 inside setHtml / JSON can fail in QtWebEngine / JS.
INLINE_STRUCTURE_CHAR_LIMIT = 400_000


def bundled_3dmol_path() -> Path:
    if not BUNDLE_JS.is_file():
        raise FileNotFoundError(f"Bundled viewer script missing: {BUNDLE_JS}")
    return BUNDLE_JS.resolve()


def build_3dmol_html(
    structure_text: str,
    fmt: str,
    residues: Sequence[ResidueColor],
    focus_chain: str,
    *,
    representation: str = "cartoon",
) -> str:
    """
    Self-contained HTML referencing local ``resources/js/3Dmol-min.js`` via relative URL.

    *fmt* ``pdb`` or ``cif`` / ``mmcif``.
    """
    bundled_3dmol_path()
    fmt_lc = fmt.lower().strip()
    mol_fmt = "mmcif" if fmt_lc == "cif" else "pdb"
    pdb_b64 = base64.b64encode(structure_text.encode("utf-8")).decode("ascii")

    residues_json = json.dumps(
        [
            {"chain": r.chain, "resi": r.resnum, "color": r.color, "sector": r.sector_idx}
            for r in residues
        ]
    )
    focus = (focus_chain or "A").strip() or "A"
    repr_key = representation.strip().lower()

    # Build JS with json.dumps for safe embedding
    js_lines = [
        "(function() {",
        "  var el = document.getElementById('viewport');",
        "  var viewer = null;",
        f"  var PDB_B64 = {json.dumps(pdb_b64)};",
        f"  var PDB_FMT = {json.dumps(mol_fmt)};",
        f"  var residueColors = {residues_json};",
        f"  var focusChain = {json.dumps(focus)};",
        f"  var representation = {json.dumps(repr_key)};",
        "  window.__STRUCTURE_VIEWER__ = {};",
        "  function buildViewer() {",
        "    var text = decodeURIComponent(Array.prototype.map.call(atob(PDB_B64), function(c) {",
        "      return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);",
        "    }).join(''));",
        "    viewer = $3Dmol.createViewer(el, { backgroundColor: '#111318' });",
        "    viewer.addModel(text, PDB_FMT);",
        "    viewer.setStyle({chain: focusChain}, { cartoon: { color: 'spectrum' } });",
        "    residueColors.forEach(function(c) {",
        "      var sel = { chain: String(c.chain), resi: c.resi };",
        "      if (representation === 'surface') {",
        "        viewer.setStyle(sel, { cartoon: { color: String(c.color) }, surface: { opacity: 0.75 } });",
        "      } else if (representation === 'cartoon+stick') {",
        "        viewer.setStyle(sel, { cartoon: { color: String(c.color) }, stick: { radius: 0.2 } });",
        "      } else {",
        "        viewer.setStyle(sel, { cartoon: { color: String(c.color) } });",
        "      }",
        "    });",
        "    viewer.zoomTo({chain: focusChain});",
        "    viewer.render();",
        "    window.__STRUCTURE_VIEWER__.viewer = viewer;",
        "    window.__STRUCTURE_VIEWER__.reset = function() {",
        "      if (!viewer) return;",
        "      viewer.zoomTo({chain: focusChain});",
        "      viewer.render();",
        "    };",
        "    window.__STRUCTURE_VIEWER__.pngURI = function() {",
        "      try { return viewer.pngURI(); } catch (e) { return null; }",
        "    };",
        "  }",
        "  window.addEventListener('load', function() {",
        "    if (typeof $3Dmol !== 'undefined') { try { buildViewer(); } catch (e) { console.error(e); } }",
        "  });",
        "})();",
    ]
    js_inline = "\n".join(js_lines)

    sectors: Dict[int, str] = {}
    for r in residues:
        if r.sector_idx not in sectors:
            sectors[r.sector_idx] = r.color

    if residues:
        legend_parts = ["<div><strong>Sectors</strong></div>"]
        for sid, c in sorted(sectors.items()):
            legend_parts.append(
                f'<div style="margin-top:4px">'
                f'<span style="display:inline-block;width:14px;height:14px;border-radius:4px;'
                f"background:{c};margin-right:8px;vertical-align:middle;"
                f'"></span>sector {sid}</div>'
            )
        legend_html = "".join(legend_parts)
    else:
        legend_html = "<div><strong>No sector mapping</strong></div>"

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        '<head><meta charset="utf-8"/>\n'
        "<style>\n"
        "  html, body { margin:0; height:100%; background:#111318; color:#cfd5dd; }\n"
        "  #viewport { width:100vw; height:100vh; position:relative; overflow:hidden; }\n"
        "  #legend { position:absolute; top:12px; left:12px; background:rgba(0,0,0,0.45);\n"
        "    padding:8px 10px; font:12px/1.35 system-ui, sans-serif; border-radius:6px;"
        " max-width:240px; }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f'<div id="legend">{legend_html}</div>\n'
        '<div id="viewport"></div>\n'
        '<script src="js/3Dmol-min.js"></script>\n'
        "<script>\n"
        f"{js_inline}\n"
        "</script>\n"
        "</body>\n"
        "</html>\n"
    )


def build_3dmol_html_sidecar(
    model_filename: str,
    fmt: str,
    residues: Sequence[ResidueColor],
    focus_chain: str,
    *,
    representation: str = "cartoon",
    script_src_uri: str,
) -> str:
    """
    HTML that loads the structure with ``fetch`` from a sibling file (same directory as
    ``index.html``). Avoids giant base64 strings for entries like large fibrinogen PDBs.

    *script_src_uri* must be a ``file://`` URL to ``3Dmol-min.js``.
    """
    bundled_3dmol_path()
    fmt_lc = fmt.lower().strip()
    mol_fmt = "mmcif" if fmt_lc == "cif" else "pdb"
    residues_json = json.dumps(
        [
            {"chain": r.chain, "resi": r.resnum, "color": r.color, "sector": r.sector_idx}
            for r in residues
        ]
    )
    focus = (focus_chain or "A").strip() or "A"
    repr_key = representation.strip().lower()
    script_attr = html.escape(script_src_uri, quote=True)
    js_lines = [
        "(function() {",
        "  var el = document.getElementById('viewport');",
        "  var viewer = null;",
        f"  var residueColors = {residues_json};",
        f"  var focusChain = {json.dumps(focus)};",
        f"  var representation = {json.dumps(repr_key)};",
        f"  var molFmt = {json.dumps(mol_fmt)};",
        f"  var modelRel = {json.dumps(model_filename)};",
        "  window.__STRUCTURE_VIEWER__ = {};",
        "  function startWithText(text) {",
        "    viewer = $3Dmol.createViewer(el, { backgroundColor: '#111318' });",
        "    viewer.addModel(text, molFmt);",
        "    viewer.setStyle({chain: focusChain}, { cartoon: { color: 'spectrum' } });",
        "    residueColors.forEach(function(c) {",
        "      var sel = { chain: String(c.chain), resi: c.resi };",
        "      if (representation === 'surface') {",
        "        viewer.setStyle(sel, { cartoon: { color: String(c.color) }, surface: { opacity: 0.75 } });",
        "      } else if (representation === 'cartoon+stick') {",
        "        viewer.setStyle(sel, { cartoon: { color: String(c.color) }, stick: { radius: 0.2 } });",
        "      } else {",
        "        viewer.setStyle(sel, { cartoon: { color: String(c.color) } });",
        "      }",
        "    });",
        "    viewer.zoomTo({chain: focusChain});",
        "    viewer.render();",
        "    window.__STRUCTURE_VIEWER__.viewer = viewer;",
        "    window.__STRUCTURE_VIEWER__.reset = function() {",
        "      if (!viewer) return;",
        "      viewer.zoomTo({chain: focusChain});",
        "      viewer.render();",
        "    };",
        "    window.__STRUCTURE_VIEWER__.pngURI = function() {",
        "      try { return viewer.pngURI(); } catch (e) { return null; }",
        "    };",
        "  }",
        "  window.addEventListener('load', function() {",
        "    if (typeof $3Dmol === 'undefined') return;",
        "    fetch(modelRel).then(function(r) {",
        "      if (!r.ok) throw new Error('Could not load structure file');",
        "      return r.text();",
        "    }).then(function(text) {",
        "      try { startWithText(text); } catch (e) { console.error(e); }",
        "    }).catch(function(e) { console.error(e); });",
        "  });",
        "})();",
    ]
    js_inline = "\n".join(js_lines)

    sectors: Dict[int, str] = {}
    for r in residues:
        if r.sector_idx not in sectors:
            sectors[r.sector_idx] = r.color

    if residues:
        legend_parts = ["<div><strong>Sectors</strong></div>"]
        for sid, c in sorted(sectors.items()):
            legend_parts.append(
                f'<div style="margin-top:4px">'
                f'<span style="display:inline-block;width:14px;height:14px;border-radius:4px;'
                f"background:{c};margin-right:8px;vertical-align:middle;"
                f'"></span>sector {sid}</div>'
            )
        legend_html = "".join(legend_parts)
    else:
        legend_html = "<div><strong>No sector mapping</strong></div>"

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        '<head><meta charset="utf-8"/>\n'
        "<style>\n"
        "  html, body { margin:0; height:100%; background:#111318; color:#cfd5dd; }\n"
        "  #viewport { width:100vw; height:100vh; position:relative; overflow:hidden; }\n"
        "  #legend { position:absolute; top:12px; left:12px; background:rgba(0,0,0,0.45);\n"
        "    padding:8px 10px; font:12px/1.35 system-ui, sans-serif; border-radius:6px;"
        " max-width:240px; }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f'<div id="legend">{legend_html}</div>\n'
        '<div id="viewport"></div>\n'
        f'<script src="{script_attr}"></script>\n'
        "<script>\n"
        f"{js_inline}\n"
        "</script>\n"
        "</body>\n"
        "</html>\n"
    )
