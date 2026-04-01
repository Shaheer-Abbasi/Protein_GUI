"""Tests for consensus flags and color resolution."""

from PyQt5.QtGui import QColor

from core.colorscheme_engine import (
    compute_consensus_flags,
    resolve_color,
    consensus_sequence,
)
from core.colorscheme_parser import ColorRule, ConsensusCondition


def test_consensus_all_alanine():
    conds = (ConsensusCondition("A", 85.0, frozenset("a")),)
    seqs = ["aa", "aa"]
    flags = compute_consensus_flags(seqs, conds)
    assert flags[0] == frozenset({"A"})
    assert flags[1] == frozenset({"A"})


def test_resolve_last_rule_wins():
    pal = {"CYAN": QColor(0, 255, 255), "PINK": QColor(255, 0, 255)}
    rules = (
        ColorRule("c", "CYAN", frozenset("%")),
        ColorRule("c", "PINK", frozenset("C")),
    )
    col = frozenset({"%", "C"})
    c = resolve_color("c", col, rules, pal)
    assert c is not None and c.green() < 100  # PINK not CYAN


def test_consensus_sequence_majority():
    s = consensus_sequence(["ABC", "ABD"])
    assert len(s) == 3
    assert s[0] == "A"
    assert s[1] == "B"
    assert s[2] in ("C", "D")
