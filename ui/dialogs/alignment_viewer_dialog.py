"""
Resizable pop-out MSA viewer with XML color schemes (non-modal).
"""

from __future__ import annotations

import os
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QScrollArea,
    QFileDialog,
    QMessageBox,
    QCheckBox,
    QFrame,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QSettings, pyqtSlot
from PyQt5.QtGui import QPixmap, QPainter

from core.colorscheme_parser import (
    ColorScheme,
    bundled_colorschemes_dir,
    list_bundled_schemes,
    load_colorscheme,
)
from ui.widgets.msa_canvas import MSACanvas
from utils.fasta_parser import FastaParser, FastaParseError


class AlignmentViewerDialog(QDialog):
    """Non-modal alignment viewer; reuse one instance and call load_alignment."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alignment viewer")
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )
        self.resize(960, 640)

        self._fasta_text: str | None = None
        self._scheme: ColorScheme | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Color scheme:"))
        self.scheme_combo = QComboBox()
        self.scheme_combo.setMinimumWidth(220)
        self.scheme_combo.currentIndexChanged.connect(self._on_scheme_combo_changed)
        toolbar.addWidget(self.scheme_combo)

        self.load_custom_btn = QPushButton("Load custom…")
        self.load_custom_btn.clicked.connect(self._load_custom_scheme)
        toolbar.addWidget(self.load_custom_btn)

        toolbar.addSpacing(12)
        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setFixedWidth(36)
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        toolbar.addWidget(self.zoom_out_btn)

        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedWidth(36)
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        toolbar.addWidget(self.zoom_in_btn)

        self.zoom_label = QLabel()
        toolbar.addWidget(self.zoom_label)

        self.fit_btn = QPushButton("Fit width")
        self.fit_btn.clicked.connect(self._fit_width)
        toolbar.addWidget(self.fit_btn)

        self.consensus_check = QCheckBox("Consensus row")
        self.consensus_check.toggled.connect(self._on_consensus_toggled)
        toolbar.addWidget(self.consensus_check)

        toolbar.addStretch()

        self.export_png_btn = QPushButton("Export PNG…")
        self.export_png_btn.clicked.connect(self._export_png)
        toolbar.addWidget(self.export_png_btn)

        self.export_fasta_btn = QPushButton("Export FASTA…")
        self.export_fasta_btn.clicked.connect(self._export_fasta)
        toolbar.addWidget(self.export_fasta_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.hide)
        toolbar.addWidget(self.close_btn)

        root.addLayout(toolbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.canvas = MSACanvas()
        self.scroll.setWidget(self.canvas)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.scroll, 1)

        self.status = QLabel()
        self.status.setProperty("class", "muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.canvas.status_message.connect(self.status.setText)
        self.canvas.layout_changed.connect(self._refresh_zoom_label)

        self._populate_scheme_combo()
        self._apply_default_scheme()
        self._refresh_zoom_label()

    def showEvent(self, event):
        super().showEvent(event)
        settings = QSettings("SenLab", "ProteinGUI")
        geo = settings.value("alignment_viewer/geometry")
        if geo is not None:
            self.restoreGeometry(geo)

    def hideEvent(self, event):
        settings = QSettings("SenLab", "ProteinGUI")
        settings.setValue("alignment_viewer/geometry", self.saveGeometry())
        super().hideEvent(event)

    def closeEvent(self, event):
        settings = QSettings("SenLab", "ProteinGUI")
        settings.setValue("alignment_viewer/geometry", self.saveGeometry())
        super().closeEvent(event)

    def _bundled_scheme_paths(self) -> set[str]:
        base = bundled_colorschemes_dir()
        return {str(base / n) for n in list_bundled_schemes()}

    def _populate_scheme_combo(self):
        self.scheme_combo.blockSignals(True)
        self.scheme_combo.clear()
        base = bundled_colorschemes_dir()
        for name in list_bundled_schemes():
            self.scheme_combo.addItem(name, str(base / name))
        self.scheme_combo.blockSignals(False)

    def _apply_default_scheme(self):
        if self.scheme_combo.count() == 0:
            return
        self.scheme_combo.blockSignals(True)
        self.scheme_combo.setCurrentIndex(0)
        self.scheme_combo.blockSignals(False)
        path = self.scheme_combo.currentData()
        if path:
            try:
                self.set_color_scheme(path)
            except Exception:
                pass

    def _refresh_zoom_label(self):
        w, h = self.canvas.cell_size()
        self.zoom_label.setText(f"{int(w)}×{int(h)} px")

    def _zoom_in(self):
        self.canvas.zoom_by(1.1)

    def _zoom_out(self):
        self.canvas.zoom_by(1 / 1.1)

    @pyqtSlot(int)
    def _on_scheme_combo_changed(self, index: int):
        if index < 0:
            return
        data = self.scheme_combo.itemData(index)
        if not isinstance(data, str) or not os.path.isfile(data):
            return
        try:
            self.set_color_scheme(data)
        except Exception as e:
            QMessageBox.warning(self, "Color scheme", f"Could not load XML:\n{e}")

    def _strip_custom_scheme_items(self):
        bundled = self._bundled_scheme_paths()
        self.scheme_combo.blockSignals(True)
        for i in range(self.scheme_combo.count() - 1, -1, -1):
            p = self.scheme_combo.itemData(i)
            if isinstance(p, str) and p.endswith(".xml") and p not in bundled:
                self.scheme_combo.removeItem(i)
        self.scheme_combo.blockSignals(False)

    def _load_custom_scheme(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open color scheme XML",
            "",
            "XML Files (*.xml);;All Files (*.*)",
        )
        if not path:
            return
        try:
            load_colorscheme(path)
        except Exception as e:
            QMessageBox.warning(self, "Color scheme", f"Could not load XML:\n{e}")
            return

        self._strip_custom_scheme_items()
        self.scheme_combo.blockSignals(True)
        self.scheme_combo.insertItem(0, f"Custom: {Path(path).name}", path)
        self.scheme_combo.setCurrentIndex(0)
        self.scheme_combo.blockSignals(False)
        self.set_color_scheme(path)

    def set_color_scheme(self, xml_path: str | os.PathLike[str]) -> None:
        self._scheme = load_colorscheme(xml_path)
        self.canvas.set_color_scheme(self._scheme)

    def load_alignment(self, fasta_content: str) -> bool:
        """Parse FASTA text and display. Returns False on parse error."""
        self._fasta_text = fasta_content
        parser = FastaParser()
        try:
            seqs = parser.parse_string(fasta_content)
        except FastaParseError as e:
            QMessageBox.warning(self, "FASTA", str(e))
            return False
        if not seqs:
            QMessageBox.warning(self, "FASTA", "No sequences found.")
            return False
        rows = [(s.id, s.sequence.replace(" ", "")) for s in seqs]
        self.canvas.load_sequences(rows)
        self._refresh_zoom_label()
        self.status.setText(f"{len(rows)} sequences × {self.canvas.alignment_width()} columns")
        return True

    def load_alignment_file(self, path: str) -> bool:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            QMessageBox.warning(self, "File", str(e))
            return False
        return self.load_alignment(text)

    def _on_consensus_toggled(self, checked: bool):
        self.canvas.set_show_consensus(checked)

    def _fit_width(self):
        vw = self.scroll.viewport().width()
        self.canvas.fit_width_to_viewport(vw)

    def _export_png(self):
        if not self.canvas.row_count():
            QMessageBox.information(self, "Export", "No alignment to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", "alignment.png", "PNG (*.png);;All Files (*.*)"
        )
        if not path:
            return
        pm = QPixmap(self.canvas.size())
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        self.canvas.render(painter)
        painter.end()
        if not pm.save(path, "PNG"):
            QMessageBox.warning(self, "Export", "Failed to save PNG.")
        else:
            QMessageBox.information(self, "Export", f"Saved:\n{path}")

    def _export_fasta(self):
        if not self._fasta_text:
            QMessageBox.information(self, "Export", "No alignment loaded.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export FASTA", "alignment.fasta", "FASTA (*.fasta *.fa);;All Files (*.*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._fasta_text)
            QMessageBox.information(self, "Export", f"Saved:\n{path}")
        except OSError as e:
            QMessageBox.warning(self, "Export", str(e))
