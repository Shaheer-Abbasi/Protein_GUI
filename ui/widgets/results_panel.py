"""
Card-based accordion results panel for BLAST / MMseqs2 search hits.

Replaces the old QTextEdit HTML view with native Qt widgets.
Used by both blast_page.py and mmseqs_page.py.
"""
from typing import List, Dict, Optional, Callable
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QComboBox, QSizePolicy, QApplication,
    QToolButton, QGridLayout, QSpacerItem
)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize
from PyQt5.QtGui import QFont, QClipboard

from ui.theme import get_theme
from ui.icons import feather_icon, set_button_icon
from utils.results_parser import SearchHit


# ── colour helpers ────────────────────────────────────────────────────

def _evalue_color(evalue: float) -> str:
    t = get_theme()
    if evalue < 1e-50:
        return t.get("success")
    if evalue < 1e-10:
        return t.get("warning")
    return t.get("error")


def _identity_color(identity: float) -> str:
    t = get_theme()
    if identity >= 70:
        return t.get("success")
    if identity >= 40:
        return t.get("warning")
    return t.get("error")


def _format_evalue(ev: float) -> str:
    if ev == 0:
        return "0"
    if ev < 0.001:
        return f"{ev:.1e}"
    return f"{ev:.3f}"


# ── SummaryBar ────────────────────────────────────────────────────────

class SummaryBar(QFrame):
    """Compact strip showing query info and aggregate stats."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(24)

        self._labels: Dict[str, QLabel] = {}
        for key in ("tool", "query", "database", "hits", "best_evalue", "avg_identity", "time"):
            val = QLabel("--")
            val.setAlignment(Qt.AlignCenter)
            self._labels[key] = val

        self._add_stat(layout, "Tool",         self._labels["tool"])
        self._add_stat(layout, "Query",        self._labels["query"])
        self._add_stat(layout, "Database",     self._labels["database"])
        self._add_stat(layout, "Hits",         self._labels["hits"])
        self._add_stat(layout, "Best E-value", self._labels["best_evalue"])
        self._add_stat(layout, "Avg Identity", self._labels["avg_identity"])
        self._add_stat(layout, "Time",         self._labels["time"])
        layout.addStretch()

    @staticmethod
    def _add_stat(layout, title: str, value_label: QLabel):
        box = QVBoxLayout()
        box.setSpacing(2)
        tl = QLabel(title)
        tl.setProperty("class", "muted")
        tl.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet("font-weight: 700; font-size: 14px;")
        box.addWidget(value_label)
        box.addWidget(tl)
        layout.addLayout(box)

    def update_info(self, query_info: dict, hits: List[SearchHit]):
        self._labels["tool"].setText(query_info.get("tool", ""))
        self._labels["query"].setText(query_info.get("query_name", "query")[:30])
        self._labels["database"].setText(query_info.get("database", "")[:20])
        self._labels["hits"].setText(str(len(hits)))
        self._labels["time"].setText(query_info.get("search_time", ""))

        if hits:
            best = min(h.evalue for h in hits)
            self._labels["best_evalue"].setText(_format_evalue(best))
            self._labels["best_evalue"].setStyleSheet(
                f"font-weight:700; font-size:14px; color:{_evalue_color(best)};")
            avg_id = sum(h.identity_percent for h in hits) / len(hits)
            self._labels["avg_identity"].setText(f"{avg_id:.1f}%")
            self._labels["avg_identity"].setStyleSheet(
                f"font-weight:700; font-size:14px; color:{_identity_color(avg_id)};")


# ── HitCard ───────────────────────────────────────────────────────────

class HitCard(QFrame):
    """Collapsible card for a single search hit."""

    def __init__(self, hit: SearchHit, parent=None):
        super().__init__(parent)
        self.hit = hit
        self._expanded = False
        self.setProperty("class", "card")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(0)

        # ── collapsed header row ──
        self._header = QWidget()
        h = QHBoxLayout(self._header)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        self._chevron = QLabel()
        self._chevron.setFixedSize(16, 16)
        self._update_chevron()
        h.addWidget(self._chevron)

        rank_lbl = QLabel(f"#{hit.rank}")
        rank_lbl.setStyleSheet("font-weight:700; min-width:32px;")
        h.addWidget(rank_lbl)

        acc_lbl = QLabel(hit.accession)
        acc_lbl.setStyleSheet(f"font-weight:600; color:{get_theme().get('accent')};")
        acc_lbl.setToolTip("Click card to expand, right-click to copy accession")
        h.addWidget(acc_lbl)

        desc_text = hit.description[:80] + ("..." if len(hit.description) > 80 else "")
        desc_lbl = QLabel(desc_text)
        desc_lbl.setProperty("class", "muted")
        desc_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        h.addWidget(desc_lbl)

        if hit.organism and hit.organism != "Unknown":
            org_lbl = QLabel(hit.organism)
            org_lbl.setStyleSheet(
                f"background-color:{get_theme().get('bg_hover')}; "
                f"border-radius:4px; padding:2px 8px; font-size:11px; "
                f"color:{get_theme().get('text_secondary')};")
            h.addWidget(org_lbl)

        ev_lbl = QLabel(_format_evalue(hit.evalue))
        ev_lbl.setStyleSheet(f"font-weight:700; color:{_evalue_color(hit.evalue)};")
        ev_lbl.setToolTip("E-value")
        h.addWidget(ev_lbl)

        id_lbl = QLabel(f"{hit.identity_percent:.1f}%")
        id_lbl.setStyleSheet(f"font-weight:700; color:{_identity_color(hit.identity_percent)};")
        id_lbl.setToolTip("Identity")
        h.addWidget(id_lbl)

        root.addWidget(self._header)

        # ── expandable detail section ──
        self._detail = QWidget()
        self._detail.setVisible(False)
        d = QVBoxLayout(self._detail)
        d.setContentsMargins(28, 10, 0, 4)
        d.setSpacing(8)

        # full description
        if len(hit.description) > 80:
            full_desc = QLabel(hit.description)
            full_desc.setWordWrap(True)
            full_desc.setProperty("class", "muted")
            d.addWidget(full_desc)

        # stats grid
        stats = QGridLayout()
        stats.setHorizontalSpacing(24)
        stats.setVerticalSpacing(4)
        stat_items = [
            ("Score", f"{hit.score:.1f} bits"),
            ("E-value", _format_evalue(hit.evalue)),
            ("Identity", f"{hit.identity_percent:.1f}%"),
            ("Alignment Length", f"{hit.alignment_length} aa"),
            ("Query Coverage", f"{hit.query_coverage:.1f}%"),
            ("Subject Length", f"{hit.sequence_length} aa"),
        ]
        for i, (label, value) in enumerate(stat_items):
            sl = QLabel(label)
            sl.setProperty("class", "muted")
            sv = QLabel(value)
            sv.setStyleSheet("font-weight:600;")
            stats.addWidget(sl, i // 3, (i % 3) * 2)
            stats.addWidget(sv, i // 3, (i % 3) * 2 + 1)
        d.addLayout(stats)

        # action buttons
        actions = QHBoxLayout()
        actions.setSpacing(8)

        copy_acc_btn = QPushButton("Copy Accession")
        copy_acc_btn.setProperty("class", "secondary")
        set_button_icon(copy_acc_btn, "copy", 14)
        copy_acc_btn.clicked.connect(lambda: QApplication.clipboard().setText(hit.accession))
        actions.addWidget(copy_acc_btn)

        if hit.full_sequence:
            copy_seq_btn = QPushButton("Copy Sequence")
            copy_seq_btn.setProperty("class", "secondary")
            set_button_icon(copy_seq_btn, "copy", 14)
            copy_seq_btn.clicked.connect(
                lambda: QApplication.clipboard().setText(hit.full_sequence))
            actions.addWidget(copy_seq_btn)

        actions.addStretch()
        d.addLayout(actions)

        root.addWidget(self._detail)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle()
        super().mousePressEvent(event)

    def toggle(self):
        self._expanded = not self._expanded
        self._detail.setVisible(self._expanded)
        self._update_chevron()

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self._detail.setVisible(expanded)
        self._update_chevron()

    def _update_chevron(self):
        icon_name = "chevron-down" if self._expanded else "chevron-right"
        icon = feather_icon(icon_name, 14, get_theme().get("text_muted"))
        self._chevron.setPixmap(icon.pixmap(14, 14))


# ── SearchResultsPanel ────────────────────────────────────────────────

class SearchResultsPanel(QWidget):
    """
    Complete results view with summary bar, toolbar, and scrollable hit cards.

    Signals:
        export_requested(str)  -- "tsv" or "csv"
        cluster_requested()
        align_requested()
    """

    export_requested = pyqtSignal(str)
    cluster_requested = pyqtSignal()
    align_requested = pyqtSignal()

    def __init__(self, show_align_button=False, parent=None):
        super().__init__(parent)
        self._hits: List[SearchHit] = []
        self._cards: List[HitCard] = []
        self._show_align = show_align_button

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 8)
        root.setSpacing(10)

        # summary bar
        self.summary_bar = SummaryBar()
        self.summary_bar.setVisible(False)
        root.addWidget(self.summary_bar)

        # toolbar
        self._toolbar = QWidget()
        tb = QHBoxLayout(self._toolbar)
        tb.setContentsMargins(0, 4, 0, 4)
        tb.setSpacing(8)

        # sort
        sort_lbl = QLabel("Sort:")
        sort_lbl.setProperty("class", "muted")
        tb.addWidget(sort_lbl)
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["E-value (best first)", "Identity (highest first)", "Score (highest first)"])
        self._sort_combo.currentIndexChanged.connect(self._apply_sort)
        tb.addWidget(self._sort_combo)

        tb.addSpacing(12)

        # expand / collapse
        self._expand_btn = QPushButton("Expand All")
        self._expand_btn.setProperty("class", "secondary")
        set_button_icon(self._expand_btn, "chevron-down", 14)
        self._expand_btn.clicked.connect(lambda: self._set_all_expanded(True))
        tb.addWidget(self._expand_btn)

        self._collapse_btn = QPushButton("Collapse All")
        self._collapse_btn.setProperty("class", "secondary")
        set_button_icon(self._collapse_btn, "chevron-up", 14)
        self._collapse_btn.clicked.connect(lambda: self._set_all_expanded(False))
        tb.addWidget(self._collapse_btn)

        tb.addStretch()

        # action buttons
        self._export_tsv = QPushButton("Export TSV")
        set_button_icon(self._export_tsv, "download", 14, "#FFFFFF")
        self._export_tsv.clicked.connect(lambda: self.export_requested.emit("tsv"))
        tb.addWidget(self._export_tsv)

        self._export_csv = QPushButton("Export CSV")
        set_button_icon(self._export_csv, "download", 14, "#FFFFFF")
        self._export_csv.clicked.connect(lambda: self.export_requested.emit("csv"))
        tb.addWidget(self._export_csv)

        self._cluster_btn = QPushButton("Cluster")
        set_button_icon(self._cluster_btn, "layers", 14, "#FFFFFF")
        self._cluster_btn.clicked.connect(self.cluster_requested.emit)
        tb.addWidget(self._cluster_btn)

        if self._show_align:
            self._align_btn = QPushButton("Align")
            set_button_icon(self._align_btn, "bar-chart-2", 14, "#FFFFFF")
            self._align_btn.clicked.connect(self.align_requested.emit)
            tb.addWidget(self._align_btn)

        self._toolbar.setVisible(False)
        root.addWidget(self._toolbar)

        # scroll area for hit cards
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(0, 0, 8, 0)
        self._card_layout.setSpacing(6)
        self._card_layout.addStretch()

        self._scroll.setWidget(self._card_container)
        root.addWidget(self._scroll, 1)

        # placeholder when no results
        self._placeholder = QLabel("Run a search to see results here.")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setProperty("class", "muted")
        self._placeholder.setMinimumHeight(120)
        root.addWidget(self._placeholder)

        self.setVisible(False)

    # ── public API ────────────────────────────────────────────────

    def set_results(self, hits: List[SearchHit], query_info: dict):
        """Populate the panel with search results."""
        self._hits = list(hits)
        self._rebuild_cards()
        self.summary_bar.update_info(query_info, hits)

        has_results = len(hits) > 0
        self.setVisible(True)
        self.summary_bar.setVisible(has_results)
        self._toolbar.setVisible(has_results)
        self._scroll.setVisible(has_results)
        self._placeholder.setVisible(not has_results)

        self._cluster_btn.setEnabled(len(hits) >= 2)
        if self._show_align and hasattr(self, "_align_btn"):
            self._align_btn.setEnabled(len(hits) >= 2)

    def clear(self):
        """Remove all results."""
        self._hits = []
        self._rebuild_cards()
        self.setVisible(False)
        self.summary_bar.setVisible(False)
        self._toolbar.setVisible(False)
        self._scroll.setVisible(False)
        self._placeholder.setVisible(True)

    def get_hits(self) -> List[SearchHit]:
        return self._hits

    # ── internals ─────────────────────────────────────────────────

    def _rebuild_cards(self):
        for card in self._cards:
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        for hit in self._hits:
            card = HitCard(hit)
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)
            self._cards.append(card)

    def _apply_sort(self, index: int):
        if not self._hits:
            return
        if index == 0:
            self._hits.sort(key=lambda h: h.evalue)
        elif index == 1:
            self._hits.sort(key=lambda h: h.identity_percent, reverse=True)
        elif index == 2:
            self._hits.sort(key=lambda h: h.score, reverse=True)

        for i, hit in enumerate(self._hits):
            hit.rank = i + 1
        self._rebuild_cards()

    def _set_all_expanded(self, expanded: bool):
        for card in self._cards:
            card.set_expanded(expanded)
