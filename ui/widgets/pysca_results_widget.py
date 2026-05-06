"""
pySCA notebook-style result figures in a pop-out dialog + compact strip on Alignment page.
"""

from __future__ import annotations

import os
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QPushButton,
    QScrollArea,
    QGroupBox,
    QMessageBox,
    QSizePolicy,
    QFrame,
    QDialog,
    QPlainTextEdit,
)
from PyQt5.QtCore import Qt, QSettings, pyqtSignal

try:
    import matplotlib

    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    FigureCanvas = None  # type: ignore[misc,assignment]
    MATPLOTLIB_AVAILABLE = False

from ui.theme import get_theme
from core.pysca_io import load_pysca_db, PySCAData
from core.pysca_sector_model import (
    merge_ics_to_sectors,
    default_sec_groups,
    validate_sec_groups,
    format_sec_groups_display,
    parse_sec_groups_literal,
    MergedSector,
)
from core.pysca_notebook_plots import (
    draw_conservation_figure,
    draw_csca_heatmap_figure,
    draw_eigen_spectrum_figure,
    draw_ev_ic_pairs_figure,
    draw_ic_distribution_figures,
    draw_two_panel_sector_matrices,
)


def _theme_dict() -> dict:
    t = get_theme()
    return {
        k: t.get(k)
        for k in (
            "bg_primary",
            "text_primary",
            "text_muted",
            "border",
            "accent",
            "error",
        )
    }


class _ScrollableFigureTab(QWidget):
    """Matplotlib canvas inside a scroll area with a readable minimum size."""

    _MIN_W, _MIN_H = 900, 480

    def __init__(self, parent=None):
        super().__init__(parent)
        self._canvas: Optional[FigureCanvas] = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._inner = QWidget()
        il = QVBoxLayout(self._inner)
        il.setContentsMargins(4, 4, 4, 4)
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)

    def set_figure(self, fig) -> None:
        if not MATPLOTLIB_AVAILABLE:
            return
        lay = self._inner.layout()
        if self._canvas is not None:
            lay.removeWidget(self._canvas)
            self._canvas.deleteLater()
            self._canvas = None
        self._canvas = FigureCanvas(fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._canvas.setMinimumSize(self._MIN_W, self._MIN_H)
        lay.addWidget(self._canvas)
        self._canvas.draw()


class PySCAResultsDialog(QDialog):
    """Non-modal window for pySCA figures and sector group editing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("pySCA results")
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )
        self.resize(1200, 800)

        self._data: Optional[PySCAData] = None
        self._sec_groups: List[List[int]] = []
        self._merged: List[MergedSector] = []
        self._user_sortpos: List[int] = []
        self._last_db_path: Optional[str] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        toolbar = QHBoxLayout()
        self._status_label = QLabel()
        self._status_label.setProperty("class", "muted")
        toolbar.addWidget(self._status_label, 1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.hide)
        toolbar.addWidget(close_btn)
        root.addLayout(toolbar)

        self._tabs = QTabWidget()
        self._fig_cons = _ScrollableFigureTab()
        self._fig_csca = _ScrollableFigureTab()
        self._fig_eigen = _ScrollableFigureTab()
        self._fig_evic = _ScrollableFigureTab()
        self._fig_icdist = _ScrollableFigureTab()
        self._fig_sector = _ScrollableFigureTab()

        self._tabs.addTab(self._fig_cons, "D_i")
        self._tabs.addTab(self._fig_csca, "C_sca")
        self._tabs.addTab(self._fig_eigen, "Eigenspectrum")
        self._tabs.addTab(self._fig_evic, "EV / IC")
        self._tabs.addTab(self._fig_icdist, "IC dist")
        self._tabs.addTab(self._fig_sector, "Sectors")
        root.addWidget(self._tabs, 1)

        edit_group = QGroupBox("Sector groups (sec_groups)")
        egl = QVBoxLayout()
        self._sector_text = QPlainTextEdit()
        self._sector_text.setPlaceholderText("([0], [1], [2], [3], ... )")
        self._sector_text.setProperty("class", "mono")
        self._sector_text.setMinimumHeight(88)
        self._sector_text.setMaximumHeight(140)
        egl.addWidget(self._sector_text)

        btn_row = QHBoxLayout()
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setProperty("class", "success")
        self._apply_btn.clicked.connect(self._apply_groups)
        self._reset_btn = QPushButton("Reset to ICs")
        self._reset_btn.setProperty("class", "secondary")
        self._reset_btn.clicked.connect(self._reset_groups)
        btn_row.addWidget(self._apply_btn)
        btn_row.addWidget(self._reset_btn)
        btn_row.addStretch()
        egl.addLayout(btn_row)
        edit_group.setLayout(egl)
        root.addWidget(edit_group)

    def showEvent(self, event):
        super().showEvent(event)
        settings = QSettings("SenLab", "ProteinGUI")
        geo = settings.value("pysca_results_dialog/geometry")
        if geo is not None:
            self.restoreGeometry(geo)

    def hideEvent(self, event):
        settings = QSettings("SenLab", "ProteinGUI")
        settings.setValue("pysca_results_dialog/geometry", self.saveGeometry())
        super().hideEvent(event)

    def load_db_path(self, path: str) -> bool:
        """Load a .db file and refresh all figures. Returns False on load error."""
        self._last_db_path = path
        self._data = None
        self._sec_groups = []
        self._merged = []
        self._user_sortpos = []
        self._sector_text.clear()
        try:
            self._data = load_pysca_db(path)
        except Exception as exc:
            QMessageBox.warning(self, "pySCA", f"Could not load .db file:\n{exc}")
            return False

        n_ic = len(self._data.Dsect.get("ics") or [])
        if n_ic == 0:
            QMessageBox.information(
                self,
                "pySCA",
                "Database loaded but no IC list found; sector editor disabled.",
            )
        self._sec_groups = default_sec_groups(n_ic)
        self._sector_text.setPlainText(format_sec_groups_display(self._sec_groups))
        self._refresh_all_figures()
        base = os.path.basename(path) if path else ""
        self._status_label.setText(f"{n_ic} ICs  |  {base}")
        return True

    def ensure_loaded(self, path: str) -> bool:
        """Load *path* if not already the active database, else keep state."""
        if (
            self._data is not None
            and self._last_db_path == path
            and path
            and os.path.isfile(path)
        ):
            return True
        return self.load_db_path(path)

    def show_raised(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _apply_groups(self) -> None:
        if self._data is None:
            return
        try:
            self._sec_groups = parse_sec_groups_literal(self._sector_text.toPlainText())
        except ValueError as e:
            QMessageBox.warning(self, "Sectors", str(e))
            return
        n_ic = len(self._data.Dsect.get("ics") or [])
        err = validate_sec_groups(n_ic, self._sec_groups)
        if err:
            QMessageBox.warning(self, "Sectors", err)
            return
        self._merged, self._user_sortpos = merge_ics_to_sectors(
            self._data.Dsect, self._sec_groups
        )
        self._refresh_sector_figure()

    def _reset_groups(self) -> None:
        if self._data is None:
            return
        n_ic = len(self._data.Dsect.get("ics") or [])
        self._sec_groups = default_sec_groups(n_ic)
        self._sector_text.setPlainText(format_sec_groups_display(self._sec_groups))
        self._merged, self._user_sortpos = merge_ics_to_sectors(
            self._data.Dsect, self._sec_groups
        )
        self._refresh_sector_figure()

    def _refresh_all_figures(self) -> None:
        if self._data is None or not MATPLOTLIB_AVAILABLE:
            return
        th = _theme_dict()
        dseq, dsca, dsect = self._data.Dseq, self._data.Dsca, self._data.Dsect

        fig1 = draw_conservation_figure(dseq, dsca, dsect, th)
        self._fig_cons.set_figure(fig1)

        fig2 = draw_csca_heatmap_figure(dsca, dsect, th)
        self._fig_csca.set_figure(fig2)

        fig3 = draw_eigen_spectrum_figure(dsca, dsect, th)
        self._fig_eigen.set_figure(fig3)

        fig4 = draw_ev_ic_pairs_figure(dsect, th)
        self._fig_evic.set_figure(fig4)

        fig5 = draw_ic_distribution_figures(dsect, th)
        self._fig_icdist.set_figure(fig5)

        self._merged, self._user_sortpos = merge_ics_to_sectors(dsect, self._sec_groups)
        self._refresh_sector_figure()

    def _refresh_sector_figure(self) -> None:
        if self._data is None or not MATPLOTLIB_AVAILABLE:
            return
        th = _theme_dict()
        fig6 = draw_two_panel_sector_matrices(
            self._data.Dsca,
            self._data.Dsect,
            th,
            self._user_sortpos,
            self._merged,
        )
        self._fig_sector.set_figure(fig6)


class PySCAResultsStripWidget(QWidget):
    """Compact row: status + button to reopen the results dialog."""

    open_results_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 0)
        self._label = QLabel()
        self._label.setProperty("class", "muted")
        self._label.setWordWrap(True)
        row.addWidget(self._label, 1)
        self._open_btn = QPushButton("Open results window")
        self._open_btn.clicked.connect(self.open_results_requested.emit)
        row.addWidget(self._open_btn)

    def set_status(self, text: str) -> None:
        self._label.setText(text)
