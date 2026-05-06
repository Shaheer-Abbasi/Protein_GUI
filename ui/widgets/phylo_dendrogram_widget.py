"""
Interactive dendrogram with threshold line (horizontal cut on distance scale).
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QSizePolicy, QScrollArea, QFrame
from PyQt5.QtCore import pyqtSignal

try:
    import matplotlib

    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from scipy.cluster.hierarchy import dendrogram

    HAVE_MPL = True
except ImportError:
    FigureCanvas = None  # type: ignore[misc,assignment]
    Figure = None  # type: ignore[misc,assignment]
    dendrogram = None  # type: ignore[assignment]
    HAVE_MPL = False


class PhyloDendrogramWidget(QWidget):
    """Scrollable dendrogram; click/drag to change distance threshold."""

    threshold_changed = pyqtSignal(float)

    _MIN_CANVAS = (900, 420)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._Z: Optional[np.ndarray] = None
        self._labels: List[str] = []
        self._ref_idx: int = 0
        self._threshold: float = 0.0
        self._theme: dict = {}
        self._fig = None
        self._ax = None
        self._canvas = None
        self._hline = None
        self._dragging = False
        self._ymax = 1.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        self._inner_layout = QVBoxLayout(inner)
        self._inner_layout.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(inner)
        lay.addWidget(scroll)

        if HAVE_MPL:
            self._fig = Figure(figsize=(11, 5.5), dpi=100)
            self._ax = self._fig.add_subplot(111)
            self._canvas = FigureCanvas(self._fig)
            self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._canvas.setMinimumSize(self._MIN_CANVAS[0], self._MIN_CANVAS[1])
            self._inner_layout.addWidget(self._canvas)
            self._canvas.mpl_connect("button_press_event", self._on_press)
            self._canvas.mpl_connect("button_release_event", self._on_release)
            self._canvas.mpl_connect("motion_notify_event", self._on_motion)

    def set_theme(self, theme: dict) -> None:
        self._theme = theme or {}
        if self._Z is not None:
            self._redraw()

    def set_data(
        self,
        Z: np.ndarray,
        labels: List[str],
        ref_idx: int,
        threshold: float,
    ) -> None:
        self._Z = np.asarray(Z)
        self._labels = list(labels)
        self._ref_idx = int(ref_idx)
        self._threshold = float(threshold)
        self._redraw()

    def set_threshold(self, t: float) -> None:
        self._threshold = float(t)
        if self._Z is not None:
            self._redraw()

    def _bg_fg(self):
        t = self._theme
        bg = t.get("bg_primary", "#0F1117")
        fg = t.get("text_primary", "#E5E8EB")
        muted = t.get("text_muted", "#6C7A89")
        border = t.get("border", "#2A2D3E")
        accent = t.get("accent", "#5DADE2")
        return bg, fg, muted, border, accent

    def _redraw(self) -> None:
        if not HAVE_MPL or self._ax is None or self._Z is None:
            return
        z = self._Z
        n = z.shape[0] + 1
        self._ax.clear()
        bg, fg, muted, border, accent = self._bg_fg()
        self._fig.patch.set_facecolor(bg)
        self._ax.set_facecolor(bg)
        if n < 2:
            self._ax.text(0.5, 0.5, "Need ≥2 sequences", ha="center", va="center", color=muted)
            self._canvas.draw_idle()
            return

        # Label colors: highlight reference leaf
        kwargs = {}
        try:
            lc = [muted] * len(self._labels)
            lc[self._ref_idx] = accent
            kwargs["label_colors"] = lc
        except Exception:
            pass

        dendrogram(
            z,
            labels=self._labels,
            ax=self._ax,
            color_threshold=self._threshold,
            above_threshold_color=muted if str(muted).startswith("#") else "#6C7A89",
            **kwargs,
        )
        self._ymax = float(self._ax.get_ylim()[1]) or 1.0
        if self._ymax <= 0:
            self._ymax = 1.0

        ref_label = self._labels[self._ref_idx] if self._labels else ""
        for tick in self._ax.xaxis.get_ticklabels():
            if tick.get_text() == ref_label:
                tick.set_color(accent)
                tick.set_fontweight("bold")
            else:
                tick.set_color(fg)

        self._hline = self._ax.axhline(
            y=self._threshold,
            color=accent,
            linewidth=2.0,
            linestyle="--",
            zorder=5,
        )
        self._ax.set_ylabel("Merge distance (1 − identity)", color=muted, fontsize=10)
        self._ax.set_xlabel("Sequence", color=muted, fontsize=10)
        self._ax.tick_params(colors=muted, labelsize=8)
        for spine in self._ax.spines.values():
            spine.set_color(border)
        self._ax.set_title("Hierarchical clustering (dendrogram)", color=fg, fontsize=12)
        self._fig.tight_layout()
        self._canvas.draw_idle()

    def _y_from_event(self, ydisp) -> Optional[float]:
        if self._ax is None or ydisp is None:
            return None
        inv = self._ax.transData.inverted()
        x0, y = inv.transform((0, ydisp))
        return float(np.clip(y, 0.0, self._ymax * 1.02))

    def _on_press(self, event):
        if event.inaxes != self._ax or event.ydata is None:
            return
        if self._hline is None:
            return
        # Start drag if near threshold line
        dy = abs(event.ydata - self._threshold)
        span = max(self._ymax, 1e-6)
        if dy < 0.03 * span or dy < 0.02:
            self._dragging = True
        elif event.inaxes == self._ax:
            # Click anywhere on axes sets threshold
            y = self._y_from_event(event.y)
            if y is not None:
                self._threshold = y
                self.threshold_changed.emit(self._threshold)
                self._redraw()

    def _on_release(self, event):
        self._dragging = False

    def _on_motion(self, event):
        if not self._dragging or event.inaxes != self._ax:
            return
        if event.ydata is None:
            return
        self._threshold = float(np.clip(event.ydata, 0.0, self._ymax * 1.02))
        self.threshold_changed.emit(self._threshold)
        self._redraw()
