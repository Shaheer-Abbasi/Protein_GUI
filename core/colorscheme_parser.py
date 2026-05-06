"""
Parse professor-style <colorparam> XML into palette, consensus conditions, and color rules.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet

from PyQt5.QtGui import QColor


@dataclass(frozen=True)
class ConsensusCondition:
    """One consensus line: if enough column residues are in `residue_chars`, flag `name` is active."""

    name: str
    cutoff_percent: float
    residue_chars: FrozenSet[str]


@dataclass(frozen=True)
class ColorRule:
    """Color a residue when any listed consensus flag character is active in that column."""

    residue: str  # single lowercase letter
    color_name: str
    condition_flags: FrozenSet[str]  # each element is one character (e.g. "%", "t", "C")


@dataclass(frozen=True)
class ColorScheme:
    """Loaded color scheme: named colors, consensus definitions, and residue rules."""

    source_path: str
    palette: dict[str, QColor]
    consensus_conditions: tuple[ConsensusCondition, ...]
    color_rules: tuple[ColorRule, ...]


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def bundled_colorschemes_dir() -> Path:
    return _project_root() / "resources" / "colorschemes"


def list_bundled_schemes() -> list[str]:
    """Return sorted basenames of *.xml files in resources/colorschemes/."""
    d = bundled_colorschemes_dir()
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.glob("*.xml") if p.is_file())


def load_colorscheme(xml_path: str | os.PathLike[str]) -> ColorScheme:
    """
    Parse a <colorparam> XML file into a ColorScheme.

    Raises ValueError on missing sections or invalid data.
    """
    path = Path(xml_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))

    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "colorparam":
        raise ValueError(f"Expected root <colorparam>, got <{root.tag}>")

    palette: dict[str, QColor] = {}
    rgbindex = root.find("rgbindex")
    if rgbindex is None:
        raise ValueError("Missing <rgbindex>")
    for el in rgbindex.findall("color"):
        name = (el.get("name") or "").strip()
        if not name:
            continue
        r = int(el.get("red", "0"))
        g = int(el.get("green", "0"))
        b = int(el.get("blue", "0"))
        palette[name.upper()] = QColor(r, g, b)

    consensus_els = root.find("consensus")
    if consensus_els is None:
        raise ValueError("Missing <consensus>")
    conditions: list[ConsensusCondition] = []
    for el in consensus_els.findall("condition"):
        nm = el.get("name")
        if not nm:
            continue
        cutoff = float(el.get("cutoffpercent", "0"))
        residues = (el.get("residues") or "").lower()
        ch = frozenset(c for c in residues if c)
        conditions.append(ConsensusCondition(name=nm, cutoff_percent=cutoff, residue_chars=ch))

    rules_els = root.find("colorrules")
    if rules_els is None:
        raise ValueError("Missing <colorrules>")
    rules: list[ColorRule] = []
    for el in rules_els.findall("resrule"):
        res = (el.get("residue") or "").lower().strip()
        if len(res) != 1:
            continue
        cname = (el.get("colorname") or "").strip()
        cond_str = el.get("conditions") or ""
        flags = frozenset(c for c in cond_str if c)
        rules.append(ColorRule(residue=res, color_name=cname.upper(), condition_flags=flags))

    return ColorScheme(
        source_path=str(path.resolve()),
        palette=palette,
        consensus_conditions=tuple(conditions),
        color_rules=tuple(rules),
    )
