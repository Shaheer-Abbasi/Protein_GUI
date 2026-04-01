"""
Consensus flag computation and per-cell color resolution for XML color schemes.
"""

from __future__ import annotations

from typing import Iterable

from PyQt5.QtGui import QColor

from core.colorscheme_parser import ColorRule, ColorScheme, ConsensusCondition


GAP_CHARS = frozenset({".", "-", " "})


def compute_consensus_flags(
    sequences: list[str],
    conditions: Iterable[ConsensusCondition],
) -> list[frozenset[str]]:
    """
    For each column index, return the set of active consensus flag names (single-char strings).

    Non-gap positions are used for percentage denominators. Gaps are `.`, `-`, or space.
    """
    if not sequences:
        return []

    width = max(len(s) for s in sequences)
    conds = tuple(conditions)
    out: list[frozenset[str]] = []

    for col in range(width):
        column_chars: list[str] = []
        for seq in sequences:
            if col < len(seq):
                column_chars.append(seq[col].lower())
        non_gap = [c for c in column_chars if c not in GAP_CHARS]
        if not non_gap:
            out.append(frozenset())
            continue
        n = len(non_gap)
        active: set[str] = set()
        for c in conds:
            if not c.residue_chars:
                continue
            cnt = sum(1 for ch in non_gap if ch in c.residue_chars)
            pct = 100.0 * cnt / n
            if pct >= c.cutoff_percent:
                active.add(c.name)
        out.append(frozenset(active))

    return out


def resolve_color(
    residue: str,
    column_flags: frozenset[str],
    rules: Iterable[ColorRule],
    palette: dict[str, QColor],
) -> QColor | None:
    """
    Return the QColor for one cell. Later rules in the list override earlier ones when both match.
    """
    if not residue or residue in GAP_CHARS:
        return None
    r = residue.lower()
    chosen: QColor | None = None
    for rule in rules:
        if rule.residue != r:
            continue
        if not (rule.condition_flags & column_flags):
            continue
        c = palette.get(rule.color_name)
        if c is not None and c.isValid():
            chosen = QColor(c)
    return chosen


def build_column_colors(
    scheme: ColorScheme,
    sequences: list[str],
    column_flags: list[frozenset[str]] | None = None,
) -> list[list[QColor | None]]:
    """
    Precompute QColor | None for every cell (row-major). Gaps -> None (caller uses default).
    """
    if column_flags is None:
        column_flags = compute_consensus_flags(sequences, scheme.consensus_conditions)
    rows: list[list[QColor | None]] = []
    rules = scheme.color_rules
    pal = scheme.palette
    for seq in sequences:
        row: list[QColor | None] = []
        for col, ch in enumerate(seq):
            flags = column_flags[col] if col < len(column_flags) else frozenset()
            row.append(resolve_color(ch, flags, rules, pal))
        rows.append(row)
    return rows


def consensus_sequence(sequences: list[str]) -> str:
    """Majority (non-gap) residue per column, uppercased; ties favor higher count then letter order."""
    if not sequences:
        return ""
    width = max(len(s) for s in sequences)
    out: list[str] = []
    for col in range(width):
        counts: dict[str, int] = {}
        for seq in sequences:
            if col >= len(seq):
                continue
            raw = seq[col]
            if raw.lower() in GAP_CHARS:
                continue
            c = raw.upper()
            counts[c] = counts.get(c, 0) + 1
        if not counts:
            out.append("-")
        else:
            best = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
            out.append(best)
    return "".join(out)
