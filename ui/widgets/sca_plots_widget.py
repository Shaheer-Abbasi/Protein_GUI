"""
Matplotlib chart panel for built-in SCA results (2x3 subplot grid)
and a pop-out dialog for full-screen viewing.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QDialog, QScrollArea, QPushButton, QFrame,
)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QPixmap, QPainter

try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    FigureCanvas = None  # type: ignore[assignment,misc]
    MATPLOTLIB_AVAILABLE = False

from ui.theme import get_theme

SECTOR_COLORS = [
    "#4da6ff", "#ff6b6b", "#51cf66", "#ffd43b",
    "#cc5de8", "#ff922b", "#20c997", "#f06595",
]


def _draw_sca_plots(figure, results):
    """Render all six SCA subplots onto *figure*. Shared by inline and pop-out."""
    import numpy as np

    figure.clear()

    t = get_theme()
    bg = t.get("bg_primary")
    text_c = t.get("text_primary")
    muted_c = t.get("text_muted")
    accent = t.get("accent")
    border_c = t.get("border")
    figure.set_facecolor(bg)

    def _style_ax(ax, title=""):
        ax.set_facecolor(bg)
        ax.set_title(title, fontsize=11, fontweight="bold", pad=8, color=text_c)
        ax.tick_params(colors=muted_c, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(border_c)

    # (1,1) Conservation
    ax1 = figure.add_subplot(2, 3, 1)
    _style_ax(ax1, "Positional Conservation (KL)")
    ax1.bar(range(len(results.Di)), results.Di, width=1.0, color=accent, edgecolor="none")
    ax1.set_xlabel("Position", fontsize=9, color=muted_c)
    ax1.set_ylabel("D_i", fontsize=9, color=muted_c)

    # (1,2) SCA matrix heatmap
    ax2 = figure.add_subplot(2, 3, 2)
    _style_ax(ax2, "SCA Correlation Matrix")
    im = ax2.imshow(results.Csca, aspect="auto", cmap="inferno", interpolation="nearest")
    figure.colorbar(im, ax=ax2, fraction=0.046, pad=0.04)
    ax2.set_xlabel("Position", fontsize=9, color=muted_c)
    ax2.set_ylabel("Position", fontsize=9, color=muted_c)

    # (1,3) Eigenvalue spectrum
    ax3 = figure.add_subplot(2, 3, 3)
    _style_ax(ax3, "Eigenvalue Spectrum")
    n_show = min(50, len(results.eigenvalues))
    ax3.bar(range(n_show), results.eigenvalues[:n_show], color=accent, edgecolor="none", label="Observed")
    rand_95 = np.percentile(results.random_eigenvalues, 95, axis=0)[:n_show]
    ax3.fill_between(range(n_show), 0, rand_95, alpha=0.3, color="#ff6b6b", label="Random 95th %ile")
    ax3.axvline(results.kpos - 0.5, color="#ffd43b", ls="--", lw=1, label=f"k={results.kpos}")
    ax3.legend(fontsize=8, loc="upper right", framealpha=0.6)
    ax3.set_xlabel("Eigenmode", fontsize=9, color=muted_c)
    ax3.set_ylabel("Eigenvalue", fontsize=9, color=muted_c)

    # (2,1) Sector positions
    ax4 = figure.add_subplot(2, 3, 4)
    _style_ax(ax4, "Sector Positions")
    if results.sectors:
        for si, sector in enumerate(results.sectors):
            color = SECTOR_COLORS[si % len(SECTOR_COLORS)]
            ax4.barh(si, width=0, left=0)
            for pos in sector:
                ax4.barh(si, width=1, left=pos, height=0.6, color=color, edgecolor="none")
        ax4.set_yticks(range(len(results.sectors)))
        ax4.set_yticklabels([f"Sector {i+1}" for i in range(len(results.sectors))])
        ax4.set_xlabel("Position", fontsize=9, color=muted_c)
    else:
        ax4.text(0.5, 0.5, "No sectors identified", ha="center", va="center",
                 transform=ax4.transAxes, color=muted_c)

    # (2,2) Sequence similarity heatmap
    ax5 = figure.add_subplot(2, 3, 5)
    _style_ax(ax5, "Sequence Similarity")
    im5 = ax5.imshow(results.sim_matrix, aspect="auto", cmap="viridis", interpolation="nearest",
                     vmin=0, vmax=1)
    figure.colorbar(im5, ax=ax5, fraction=0.046, pad=0.04)
    ax5.set_xlabel("Sequence", fontsize=9, color=muted_c)
    ax5.set_ylabel("Sequence", fontsize=9, color=muted_c)

    # (2,3) Top eigenvector loadings
    ax6 = figure.add_subplot(2, 3, 6)
    _style_ax(ax6, f"Top {results.kpos} Eigenvector Loadings")
    for k in range(min(results.kpos, 4)):
        color = SECTOR_COLORS[k % len(SECTOR_COLORS)]
        loadings = __import__("numpy").abs(results.eigenvectors[:, k])
        ax6.plot(loadings, color=color, lw=0.8, alpha=0.8, label=f"EV {k+1}")
    ax6.legend(fontsize=8, loc="upper right", framealpha=0.6)
    ax6.set_xlabel("Position", fontsize=9, color=muted_c)
    ax6.set_ylabel("|Loading|", fontsize=9, color=muted_c)

    figure.tight_layout(pad=2.5, h_pad=3.5, w_pad=3.0)


class SCAChartsWidget(FigureCanvas if MATPLOTLIB_AVAILABLE else QWidget):
    """Six SCA charts rendered via matplotlib, themed to the app palette."""

    def __init__(self, parent=None):
        if MATPLOTLIB_AVAILABLE:
            self.figure = Figure(figsize=(14, 8), dpi=100)
            t = get_theme()
            self.figure.set_facecolor(t.get("bg_primary"))
            super().__init__(self.figure)
        else:
            super().__init__(parent)
            layout = QVBoxLayout(self)
            lbl = QLabel(
                "matplotlib is not installed.\n"
                "Install it with: pip install matplotlib"
            )
            lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl)

        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._has_data = False
        self._last_results = None

    def has_data(self) -> bool:
        return self._has_data

    def last_results(self):
        return self._last_results

    def plot_results(self, results):
        """Draw six subplots from an ``SCAResults`` object."""
        if not MATPLOTLIB_AVAILABLE:
            return
        self._last_results = results
        self._has_data = True
        _draw_sca_plots(self.figure, results)
        self.draw()

    def clear_plot(self):
        if MATPLOTLIB_AVAILABLE:
            self.figure.clear()
            self._has_data = False
            self._last_results = None
            self.draw()


class SCAChartsDialog(QDialog):
    """Non-modal pop-out window for SCA charts at full size."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SCA Analysis Charts")
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )
        self.resize(1200, 800)

        self._results = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()

        self.status_label = QLabel()
        self.status_label.setProperty("class", "muted")
        toolbar.addWidget(self.status_label, 1)

        self.export_btn = QPushButton("Export PNG...")
        self.export_btn.clicked.connect(self._export_png)
        toolbar.addWidget(self.export_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.hide)
        toolbar.addWidget(close_btn)

        root.addLayout(toolbar)

        # Scrollable canvas
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        if MATPLOTLIB_AVAILABLE:
            self._canvas_figure = Figure(figsize=(18, 10), dpi=120)
            t = get_theme()
            self._canvas_figure.set_facecolor(t.get("bg_primary"))
            self._canvas = FigureCanvas(self._canvas_figure)
            self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._canvas.setMinimumSize(1100, 700)
            self.scroll.setWidget(self._canvas)
        else:
            placeholder = QLabel("matplotlib is not installed.")
            placeholder.setAlignment(Qt.AlignCenter)
            self.scroll.setWidget(placeholder)
            self._canvas = None
            self._canvas_figure = None

        root.addWidget(self.scroll, 1)

    def showEvent(self, event):
        super().showEvent(event)
        settings = QSettings("SenLab", "ProteinGUI")
        geo = settings.value("sca_charts_dialog/geometry")
        if geo is not None:
            self.restoreGeometry(geo)

    def hideEvent(self, event):
        settings = QSettings("SenLab", "ProteinGUI")
        settings.setValue("sca_charts_dialog/geometry", self.saveGeometry())
        super().hideEvent(event)

    def plot_results(self, results):
        if not MATPLOTLIB_AVAILABLE or self._canvas_figure is None:
            return
        self._results = results
        _draw_sca_plots(self._canvas_figure, results)
        self._canvas.draw()
        backend = "GPU" if results.used_gpu else "CPU"
        self.status_label.setText(
            f"{results.n_seqs} sequences x {results.n_pos} positions  |  "
            f"k={results.kpos} significant eigenmodes  |  "
            f"Computed in {results.elapsed_seconds:.1f}s ({backend})"
        )

    def _export_png(self):
        if self._canvas is None or self._results is None:
            return
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getSaveFileName(
            self, "Export SCA Charts", "sca_charts.png",
            "PNG (*.png);;All Files (*.*)",
        )
        if not path:
            return
        self._canvas_figure.savefig(path, dpi=150, bbox_inches="tight")
        QMessageBox.information(self, "Export", f"Saved:\n{path}")
