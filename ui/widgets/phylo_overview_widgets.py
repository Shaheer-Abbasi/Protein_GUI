"""Cluster size bar chart and identity heatmap for phylogenetic analysis."""

from __future__ import annotations

from typing import List, Optional

import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QSizePolicy, QScrollArea, QFrame

try:
    import matplotlib

    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from scipy.cluster.hierarchy import fcluster, leaves_list

    HAVE_MPL = True
except ImportError:
    FigureCanvas = None  # type: ignore[misc,assignment]
    Figure = None  # type: ignore[misc,assignment]
    fcluster = None  # type: ignore[assignment]
    leaves_list = None  # type: ignore[assignment]
    HAVE_MPL = False


class PhyloClusterSizesWidget(QWidget):
    """Horizontal bar chart of cluster sizes at a distance cut."""

    _MIN = (700, 320)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._Z: Optional[np.ndarray] = None
        self._thr: float = 0.0
        self._theme: dict = {}
        self._fig = self._ax = self._canvas = None
        lay = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        il = QVBoxLayout(inner)
        if HAVE_MPL:
            self._fig = Figure(figsize=(9, 4), dpi=100)
            self._ax = self._fig.add_subplot(111)
            self._canvas = FigureCanvas(self._fig)
            self._canvas.setMinimumSize(self._MIN[0], self._MIN[1])
            il.addWidget(self._canvas)
        scroll.setWidget(inner)
        lay.addWidget(scroll)

    def set_theme(self, theme: dict) -> None:
        self._theme = theme or {}
        if self._Z is not None:
            self.set_data(self._Z, self._thr)

    def set_data(self, Z: np.ndarray, threshold: float) -> None:
        self._Z = np.asarray(Z)
        self._thr = threshold
        if not HAVE_MPL or self._ax is None or fcluster is None:
            return
        z = self._Z
        n = z.shape[0] + 1
        self._ax.clear()
        bg = self._theme.get("bg_primary", "#0F1117")
        fg = self._theme.get("text_primary", "#E5E8EB")
        muted = self._theme.get("text_muted", "#6C7A89")
        border = self._theme.get("border", "#2A2D3E")
        accent = self._theme.get("accent", "#5DADE2")
        self._fig.patch.set_facecolor(bg)
        self._ax.set_facecolor(bg)
        if n < 2:
            self._ax.text(0.5, 0.5, "N/A", ha="center", va="center", color=muted)
        else:
            labs = fcluster(z, t=threshold, criterion="distance")
            uniq, counts = np.unique(labs, return_counts=True)
            order = np.argsort(-counts)
            counts = counts[order]
            y = np.arange(len(counts))
            self._ax.barh(y, counts, color=accent, edgecolor=border, height=0.65)
            self._ax.set_yticks(y)
            self._ax.set_yticklabels([f"C{i+1}" for i in range(len(counts))], color=muted, fontsize=8)
            self._ax.set_xlabel("Sequences in cluster", color=muted, fontsize=10)
            self._ax.set_title(
                f"Cluster sizes at threshold {threshold:.4f} ({len(uniq)} clusters)",
                color=fg,
                fontsize=11,
            )
        self._ax.tick_params(colors=muted)
        for spine in self._ax.spines.values():
            spine.set_color(border)
        self._fig.tight_layout()
        self._canvas.draw_idle()


class PhyloIdentityHeatmapWidget(QWidget):
    """Heatmap of pairwise identity (optionally leaf-ordered)."""

    _MIN = (700, 400)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._I: Optional[np.ndarray] = None
        self._labels: List[str] = []
        self._Z: Optional[np.ndarray] = None
        self._theme: dict = {}
        self._fig = self._ax = self._canvas = None
        lay = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        il = QVBoxLayout(inner)
        if HAVE_MPL:
            self._fig = Figure(figsize=(8, 7), dpi=100)
            self._ax = self._fig.add_subplot(111)
            self._canvas = FigureCanvas(self._fig)
            self._canvas.setMinimumSize(self._MIN[0], self._MIN[1])
            il.addWidget(self._canvas)
        scroll.setWidget(inner)
        lay.addWidget(scroll)

    def set_theme(self, theme: dict) -> None:
        self._theme = theme or {}
        if self._I is not None:
            self.set_data(self._I, self._labels, self._Z)

    def set_data(self, identity: np.ndarray, labels: List[str], Z: np.ndarray) -> None:
        self._I = np.asarray(identity)
        self._labels = list(labels)
        self._Z = np.asarray(Z) if Z.size else None
        if not HAVE_MPL or self._ax is None:
            return
        I = self._I
        n = I.shape[0]
        self._ax.clear()
        bg = self._theme.get("bg_primary", "#0F1117")
        fg = self._theme.get("text_primary", "#E5E8EB")
        muted = self._theme.get("text_muted", "#6C7A89")
        border = self._theme.get("border", "#2A2D3E")
        self._fig.patch.set_facecolor(bg)
        self._ax.set_facecolor(bg)
        if n == 0:
            self._ax.text(0.5, 0.5, "No data", ha="center", va="center", color=muted)
            self._canvas.draw_idle()
            return

        order = np.arange(n)
        if (
            self._Z is not None
            and getattr(self._Z, "size", 0) > 0
            and leaves_list is not None
        ):
            order = np.asarray(leaves_list(self._Z))

        I2 = I[np.ix_(order, order)]
        lab2 = [labels[i] for i in order]
        im = self._ax.imshow(I2, vmin=0, vmax=1, cmap="inferno", aspect="equal")
        cb = self._fig.colorbar(im, ax=self._ax, fraction=0.046, pad=0.04)
        cb.ax.yaxis.set_tick_params(color=muted)
        cb.outline.set_edgecolor(border)
        if n <= 40:
            self._ax.set_xticks(np.arange(n))
            self._ax.set_xticklabels(lab2, rotation=90, fontsize=6, color=muted)
            self._ax.set_yticks(np.arange(n))
            self._ax.set_yticklabels(lab2, fontsize=6, color=muted)
        else:
            self._ax.set_xticks([])
            self._ax.set_yticks([])
        self._ax.set_title("Pairwise identity (leaf order)", color=fg, fontsize=11)
        self._fig.tight_layout()
        self._canvas.draw_idle()
