"""Reference-branch size vs merge-distance threshold (step plot)."""

from __future__ import annotations

from typing import Optional

import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QSizePolicy, QScrollArea, QFrame
from PyQt5.QtCore import pyqtSignal

try:
    import matplotlib

    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure

    HAVE_MPL = True
except ImportError:
    FigureCanvas = None  # type: ignore[misc,assignment]
    Figure = None  # type: ignore[misc,assignment]
    HAVE_MPL = False


class PhyloBranchProfileWidget(QWidget):
    """Step plot of (threshold, branch size) for the reference sequence cluster."""

    threshold_changed = pyqtSignal(float)

    _MIN_CANVAS = (700, 360)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events = np.zeros((0, 2))
        self._threshold = 0.0
        self._xmax = 1.0
        self._theme: dict = {}
        self._canvas = None
        self._ax = None
        self._fig = None
        self._vline = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(inner)
        lay.addWidget(scroll)

        if HAVE_MPL:
            self._fig = Figure(figsize=(9, 4.5), dpi=100)
            self._ax = self._fig.add_subplot(111)
            self._canvas = FigureCanvas(self._fig)
            self._canvas.setMinimumSize(self._MIN_CANVAS[0], self._MIN_CANVAS[1])
            self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            il.addWidget(self._canvas)
            self._canvas.mpl_connect("button_press_event", self._on_press)

    def set_theme(self, theme: dict) -> None:
        self._theme = theme or {}
        if len(self._events):
            self._redraw()

    def set_events(self, events: np.ndarray) -> None:
        """Nx2 array: [height, cluster_size] sorted by height."""
        self._events = np.asarray(events, dtype=np.float64)
        if self._events.size:
            self._xmax = float(max(self._events[:, 0].max(), 1e-6))
        else:
            self._xmax = 1.0
        self._redraw()

    def set_threshold(self, t: float) -> None:
        self._threshold = float(t)
        self._redraw()

    def _palette(self):
        t = self._theme
        return (
            t.get("bg_primary", "#0F1117"),
            t.get("text_primary", "#E5E8EB"),
            t.get("text_muted", "#6C7A89"),
            t.get("border", "#2A2D3E"),
            t.get("accent", "#5DADE2"),
        )

    def _redraw(self) -> None:
        if not HAVE_MPL or self._ax is None:
            return
        bg, fg, muted, border, accent = self._palette()
        self._ax.clear()
        self._fig.patch.set_facecolor(bg)
        self._ax.set_facecolor(bg)

        ev = self._events
        if ev.size == 0:
            self._ax.text(0.5, 0.5, "No events", ha="center", va="center", color=muted)
            self._canvas.draw_idle()
            return

        xs = ev[:, 0]
        ys = ev[:, 1]
        self._ax.step(xs, ys, where="post", color=accent, linewidth=2.0, label="Branch size")
        self._ax.fill_between(xs, ys, step="post", alpha=0.15, color=accent)

        self._ax.axvline(x=self._threshold, color=accent, linestyle="--", linewidth=2.0, alpha=0.9)

        self._ax.set_xlabel("Distance threshold (merge height)", color=muted, fontsize=10)
        self._ax.set_ylabel("Sequences in reference cluster", color=muted, fontsize=10)
        self._ax.set_title("Reference branch size vs threshold", color=fg, fontsize=12)
        self._ax.tick_params(colors=muted)
        for spine in self._ax.spines.values():
            spine.set_color(border)
        self._ax.set_xlim(0.0, max(self._xmax * 1.05, 0.01))
        self._fig.tight_layout()
        self._canvas.draw_idle()

    def _on_press(self, event):
        if event.inaxes != self._ax or event.xdata is None:
            return
        self._threshold = float(np.clip(event.xdata, 0.0, self._xmax * 1.02))
        self.threshold_changed.emit(self._threshold)
