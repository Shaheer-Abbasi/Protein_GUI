"""
Custom-painted multiple sequence alignment grid (viewport-clipped).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QWidget, QSizePolicy, QApplication
from PyQt5.QtCore import Qt, pyqtSignal, QPointF
from PyQt5.QtGui import QPainter, QColor, QFont, QFontMetricsF, QPen, QWheelEvent, QMouseEvent

from core.colorscheme_engine import (
    GAP_CHARS,
    build_column_colors,
    compute_consensus_flags,
    consensus_sequence,
)
from core.colorscheme_parser import ColorScheme


def _luminance(c: QColor) -> float:
    r, g, b = c.redF(), c.greenF(), c.blueF()
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrasting_text_color(bg: QColor) -> QColor:
    return QColor(0, 0, 0) if _luminance(bg) > 0.55 else QColor(255, 255, 255)


class MSACanvas(QWidget):
    """Renders an MSA with optional consensus row; supports zoom and hover status."""

    status_message = pyqtSignal(str)
    layout_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._scheme: ColorScheme | None = None
        self._labels: list[str] = []
        self._sequences: list[str] = []
        self._display_labels: list[str] = []
        self._display_sequences: list[str] = []
        self._column_flags: list[frozenset[str]] = []
        self._cell_colors: list[list[QColor | None]] = []
        self._width = 0
        self._show_consensus = False

        self._cell_w = 14.0
        self._cell_h = 18.0
        self._label_pad = 8.0
        self._gap_bg = QColor(45, 45, 48)
        self._plain_bg = QColor(52, 52, 58)
        self._grid_pen = QPen(QColor(60, 60, 65))

        self._font = QFont("Menlo", 11)
        if not QFont("Menlo").exactMatch():
            self._font = QFont("Courier New", 11)
        self._fm = QFontMetricsF(self._font)

        self._hover_row = -1
        self._hover_col = -1

    def minimum_cell(self) -> float:
        return 8.0

    def maximum_cell(self) -> float:
        return 24.0

    def cell_size(self) -> tuple[float, float]:
        return (self._cell_w, self._cell_h)

    def set_cell_size(self, w: float, h: float | None = None):
        mn, mx = self.minimum_cell(), self.maximum_cell()
        self._cell_w = max(mn, min(mx, w))
        self._cell_h = max(mn, min(mx, h if h is not None else w * (18 / 14)))
        self._update_geometry()
        self.layout_changed.emit()
        self.update()

    def zoom_by(self, factor: float):
        self.set_cell_size(self._cell_w * factor, self._cell_h * factor)

    def set_show_consensus(self, show: bool):
        if show == self._show_consensus:
            return
        self._show_consensus = show
        self._rebuild_display_rows()
        self._recompute_colors()
        self._update_geometry()
        self.layout_changed.emit()
        self.update()

    def show_consensus(self) -> bool:
        return self._show_consensus

    def set_color_scheme(self, scheme: ColorScheme | None):
        self._scheme = scheme
        self._recompute_colors()
        self.update()

    def color_scheme(self) -> ColorScheme | None:
        return self._scheme

    def load_sequences(self, rows: list[tuple[str, str]]):
        """rows: (label, sequence); sequences are padded to common width."""
        self._labels = [r[0] for r in rows]
        self._sequences = [r[1] for r in rows]
        if self._sequences:
            w = max(len(s) for s in self._sequences)
            self._sequences = [s.ljust(w, "-") for s in self._sequences]
            self._width = w
        else:
            self._width = 0
        self._rebuild_display_rows()
        self._recompute_colors()
        self._update_geometry()
        self.layout_changed.emit()
        self.update()

    def clear(self):
        self._labels.clear()
        self._sequences.clear()
        self._display_labels.clear()
        self._display_sequences.clear()
        self._column_flags.clear()
        self._cell_colors.clear()
        self._width = 0
        self._update_geometry()
        self.layout_changed.emit()
        self.update()

    def alignment_width(self) -> int:
        return self._width

    def row_count(self) -> int:
        return len(self._display_sequences)

    def _rebuild_display_rows(self):
        if not self._sequences:
            self._display_labels = []
            self._display_sequences = []
            return
        if self._show_consensus:
            cons = consensus_sequence(self._sequences)
            self._display_labels = ["consensus"] + self._labels
            self._display_sequences = [cons] + self._sequences
        else:
            self._display_labels = list(self._labels)
            self._display_sequences = list(self._sequences)

    def _recompute_colors(self):
        if not self._display_sequences or self._scheme is None:
            self._column_flags = []
            self._cell_colors = []
            return
        base_seqs = self._sequences
        self._column_flags = compute_consensus_flags(
            base_seqs, self._scheme.consensus_conditions
        )
        self._cell_colors = build_column_colors(
            self._scheme, self._display_sequences, self._column_flags
        )

    def _label_column_width(self) -> float:
        if not self._display_labels:
            return 120.0
        mw = max(self._fm.horizontalAdvance(lbl) for lbl in self._display_labels)
        return float(mw) + self._label_pad * 2

    def _update_geometry(self):
        lw = self._label_column_width()
        rows = len(self._display_sequences)
        cols = self._width
        total_w = int(lw + cols * self._cell_w + 1)
        total_h = int(rows * self._cell_h + 1)
        self.setFixedSize(max(total_w, 200), max(total_h, 80))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setFont(self._font)

        rect = event.rect()
        painter.setClipRect(rect)

        lw = self._label_column_width()
        rows = len(self._display_sequences)
        cols = self._width

        r0 = max(0, int((rect.top()) / self._cell_h))
        r1 = min(rows, int((rect.bottom()) / self._cell_h) + 1)
        c0 = max(0, int((rect.left() - lw) / self._cell_w))
        c1 = min(cols, int((rect.right() - lw) / self._cell_w) + 1)

        # Label column background
        painter.fillRect(0, rect.top(), int(lw), rect.height(), QColor(35, 35, 38))

        for ri in range(r0, r1):
            y = ri * self._cell_h
            lbl = self._display_labels[ri]
            painter.setPen(QColor(200, 200, 205))
            painter.drawText(
                QPointF(self._label_pad, y + self._fm.ascent() + (self._cell_h - self._fm.height()) / 2),
                lbl,
            )

        for ri in range(r0, r1):
            y = int(ri * self._cell_h)
            seq = self._display_sequences[ri]
            for ci in range(c0, c1):
                x = int(lw + ci * self._cell_w)
                ch = seq[ci] if ci < len(seq) else "-"
                bg = None
                if ri < len(self._cell_colors) and ci < len(self._cell_colors[ri]):
                    bg = self._cell_colors[ri][ci]
                if bg is None:
                    cell_bg = self._gap_bg if ch.lower() in GAP_CHARS else self._plain_bg
                    painter.fillRect(x, y, int(self._cell_w) + 1, int(self._cell_h) + 1, cell_bg)
                    fg = QColor(180, 180, 185)
                else:
                    painter.fillRect(x, y, int(self._cell_w) + 1, int(self._cell_h) + 1, bg)
                    fg = _contrasting_text_color(bg)
                painter.setPen(self._grid_pen)
                painter.drawRect(x, y, int(self._cell_w), int(self._cell_h))
                painter.setPen(fg)
                painter.drawText(
                    QPointF(
                        x + (self._cell_w - self._fm.horizontalAdvance(ch)) / 2,
                        y + self._fm.ascent() + (self._cell_h - self._fm.height()) / 2,
                    ),
                    ch.upper() if ch.lower() not in GAP_CHARS else ch,
                )

    def wheelEvent(self, event: QWheelEvent):
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_by(1.1)
            elif delta < 0:
                self.zoom_by(1 / 1.1)
            event.accept()
            return
        super().wheelEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        lw = self._label_column_width()
        x, y = event.x(), event.y()
        if x < lw:
            self.status_message.emit("")
            super().mouseMoveEvent(event)
            return
        col = int((x - lw) / self._cell_w)
        row = int(y / self._cell_h)
        if (
            0 <= row < len(self._display_sequences)
            and 0 <= col < self._width
        ):
            self._hover_row = row
            self._hover_col = col
            lbl = self._display_labels[row]
            seq = self._display_sequences[row]
            ch = seq[col] if col < len(seq) else "-"
            flags = self._column_flags[col] if col < len(self._column_flags) else frozenset()
            flags_s = "".join(sorted(flags)) if flags else "—"
            pos1 = col + 1
            self.status_message.emit(
                f"Row: {lbl}  |  Column: {pos1}  |  Residue: {ch}  |  Active consensus flags: {flags_s}"
            )
        else:
            self.status_message.emit("")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.status_message.emit("")
        super().leaveEvent(event)

    def fit_width_to_viewport(self, viewport_width: int):
        """Set cell width so alignment fits (approximately) in viewport_width."""
        lw = self._label_column_width()
        avail = max(100, viewport_width - int(lw) - 4)
        if self._width <= 0:
            return
        w = avail / self._width
        self.set_cell_size(w, w * (18 / 14))
