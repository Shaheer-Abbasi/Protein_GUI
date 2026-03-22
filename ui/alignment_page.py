"""Sequence Alignment page - Multiple Sequence Alignment using Clustal Omega"""
import os
import shutil
import tempfile
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QLineEdit, QComboBox, QGroupBox, QTextEdit,
    QProgressBar, QMessageBox, QTabWidget, QRadioButton, QButtonGroup,
    QFrame, QSpinBox, QCheckBox, QSplitter, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, Qt, QTimer, QSettings
from PyQt5.QtGui import QFont

from ui.theme import get_theme
from ui.icons import feather_icon, set_button_icon
from core.wsl_utils import is_wsl_available, warmup_wsl, get_platform_tool_install_hint
from core.alignment_worker import (
    AlignmentWorker,
    check_clustalo_installation,
    SequenceAlignmentPrep
)
from ui.widgets.msa_viewer_widget import MSAViewerWidget, check_webengine_available
from utils.fasta_parser import FastaParser, FastaParseError


class AlignmentPage(QWidget):
    """Sequence Alignment page using Clustal Omega"""

    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.alignment_worker = None
        self.input_fasta_path = None
        self.output_alignment_path = None
        self.aligned_content = None
        self.loaded_sequences = []
        self.is_temp_fasta = False
        self._init_ui()

        QTimer.singleShot(100, lambda: warmup_wsl())
        QTimer.singleShot(2000, self.check_system_requirements)

    def _init_ui(self):
        t = get_theme()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)

        # ── Top: input controls in a scroll area ─────────────────
        input_scroll = QScrollArea()
        input_scroll.setWidgetResizable(True)
        input_scroll.setFrameShape(QFrame.NoFrame)

        input_widget = QWidget()
        form = QVBoxLayout(input_widget)
        form.setContentsMargins(28, 24, 28, 16)
        form.setSpacing(16)

        title = QLabel("Sequence Alignment")
        title.setProperty("class", "title")
        form.addWidget(title)

        # System requirements warning
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        form.addWidget(self.warning_label)

        # PyQtWebEngine warning
        self.webengine_warning = QLabel()
        self.webengine_warning.setWordWrap(True)
        if not check_webengine_available():
            self.webengine_warning.setText(
                "PyQtWebEngine is not installed. The alignment viewer is disabled.\n"
                "You can still run alignments and export results. To enable the viewer:\n"
                "pip install PyQtWebEngine"
            )
        else:
            self.webengine_warning.hide()
        form.addWidget(self.webengine_warning)

        # ── Input section ────────────────────────────────────────
        input_group = QGroupBox("Input Sequences")
        ig_layout = QVBoxLayout()

        method_row = QHBoxLayout()
        self.input_method_group = QButtonGroup()
        self.upload_radio = QRadioButton("Upload FASTA File")
        self.paste_radio = QRadioButton("Paste Sequences")
        self.upload_radio.setChecked(True)
        self.input_method_group.addButton(self.upload_radio, 1)
        self.input_method_group.addButton(self.paste_radio, 2)
        self.upload_radio.toggled.connect(self._on_input_method_changed)
        self.paste_radio.toggled.connect(self._on_input_method_changed)
        method_row.addWidget(self.upload_radio)
        method_row.addWidget(self.paste_radio)
        method_row.addStretch()
        ig_layout.addLayout(method_row)

        # Upload widget
        self.upload_widget = QWidget()
        upload_layout = QHBoxLayout(self.upload_widget)
        upload_layout.setContentsMargins(0, 8, 0, 0)
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("No file selected...")
        self.file_path_input.setReadOnly(True)
        browse_btn = QPushButton("Browse")
        set_button_icon(browse_btn, "folder", 14, "#FFFFFF")
        browse_btn.clicked.connect(self.browse_fasta_file)
        upload_layout.addWidget(self.file_path_input)
        upload_layout.addWidget(browse_btn)

        # Paste widget
        self.paste_widget = QWidget()
        paste_layout = QVBoxLayout(self.paste_widget)
        paste_layout.setContentsMargins(0, 8, 0, 0)
        paste_label = QLabel("Paste sequences in FASTA format:")
        self.paste_text = QTextEdit()
        self.paste_text.setPlaceholderText(
            ">sequence1\nMKTLLILAVVAAALA...\n"
            ">sequence2\nMKTLLILAVVAAALA...\n"
            ">sequence3\nMKTLLILAVV---LA..."
        )
        self.paste_text.setMaximumHeight(120)
        paste_layout.addWidget(paste_label)
        paste_layout.addWidget(self.paste_text)
        self.paste_widget.hide()

        ig_layout.addWidget(self.upload_widget)
        ig_layout.addWidget(self.paste_widget)

        self.file_info_label = QLabel()
        self.file_info_label.setProperty("class", "muted")
        ig_layout.addWidget(self.file_info_label)

        input_group.setLayout(ig_layout)
        form.addWidget(input_group)

        # ── Parameters section ───────────────────────────────────
        params_group = QGroupBox("Alignment Parameters")
        pl = QVBoxLayout()

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Output Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItem("FASTA (aligned)", "fasta")
        self.format_combo.addItem("Clustal", "clustal")
        self.format_combo.addItem("MSF", "msf")
        self.format_combo.addItem("PHYLIP", "phylip")
        self.format_combo.addItem("Stockholm", "stockholm")
        fmt_row.addWidget(self.format_combo)
        fmt_row.addStretch()
        pl.addLayout(fmt_row)

        iter_row = QHBoxLayout()
        iter_row.addWidget(QLabel("Iterations:"))
        self.iter_spin = QSpinBox()
        self.iter_spin.setRange(0, 5)
        self.iter_spin.setValue(0)
        self.iter_spin.setToolTip("Number of combined iterations (0 = auto)")
        iter_row.addWidget(self.iter_spin)
        iter_row.addStretch()
        pl.addLayout(iter_row)

        self.full_iter_checkbox = QCheckBox("Full iterative refinement")
        self.full_iter_checkbox.setToolTip("Use full iterative refinement (slower but more accurate)")
        pl.addWidget(self.full_iter_checkbox)

        params_group.setLayout(pl)
        form.addWidget(params_group)

        # ── Control buttons ──────────────────────────────────────
        ctrl_row = QHBoxLayout()

        self.save_fasta_button = QPushButton("Save Input FASTA")
        self.save_fasta_button.setProperty("class", "secondary")
        set_button_icon(self.save_fasta_button, "save", 14)
        self.save_fasta_button.clicked.connect(self._save_input_fasta)
        self.save_fasta_button.setVisible(False)

        self.run_button = QPushButton("Run Alignment")
        self.run_button.setProperty("class", "success")
        set_button_icon(self.run_button, "play", 16, "#FFFFFF")
        self.run_button.setMinimumHeight(40)
        self.run_button.clicked.connect(self.run_alignment)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("class", "danger")
        set_button_icon(self.cancel_button, "x", 14, "#FFFFFF")
        self.cancel_button.setMinimumHeight(40)
        self.cancel_button.clicked.connect(self.cancel_alignment)
        self.cancel_button.setEnabled(False)

        ctrl_row.addStretch()
        ctrl_row.addWidget(self.save_fasta_button)
        ctrl_row.addWidget(self.run_button)
        ctrl_row.addWidget(self.cancel_button)
        form.addLayout(ctrl_row)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        form.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setProperty("class", "muted")
        form.addWidget(self.status_label)

        input_scroll.setWidget(input_widget)
        splitter.addWidget(input_scroll)

        # ── Bottom: results tabs ─────────────────────────────────
        self.results_tabs = QTabWidget()
        self.results_tabs.hide()

        # Tab 1: Alignment Viewer
        viewer_tab = QWidget()
        vl = QVBoxLayout(viewer_tab)
        vl.setContentsMargins(0, 0, 0, 0)
        self.msa_viewer = MSAViewerWidget()
        self.msa_viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vl.addWidget(self.msa_viewer)
        self.results_tabs.addTab(viewer_tab, feather_icon("eye", 16), "Alignment Viewer")

        # Tab 2: Raw Alignment
        raw_tab = QWidget()
        rl = QVBoxLayout(raw_tab)
        rl.setContentsMargins(12, 12, 12, 12)
        self.raw_alignment_text = QTextEdit()
        self.raw_alignment_text.setReadOnly(True)
        self.raw_alignment_text.setProperty("class", "mono")
        self.raw_alignment_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        rl.addWidget(self.raw_alignment_text)
        self.results_tabs.addTab(raw_tab, feather_icon("file-text", 16), "Raw Alignment")

        # Tab 3: Export
        export_tab = QWidget()
        el = QVBoxLayout(export_tab)
        el.setContentsMargins(12, 12, 12, 12)
        el.setSpacing(12)

        el.addWidget(QLabel("Export the alignment in various formats:"))

        export_fasta_btn = QPushButton("Export as FASTA")
        export_fasta_btn.setProperty("class", "success")
        set_button_icon(export_fasta_btn, "download", 14, "#FFFFFF")
        export_fasta_btn.clicked.connect(lambda: self._export_alignment('fasta'))
        el.addWidget(export_fasta_btn)

        export_clustal_btn = QPushButton("Export as Clustal")
        export_clustal_btn.setProperty("class", "success")
        set_button_icon(export_clustal_btn, "download", 14, "#FFFFFF")
        export_clustal_btn.clicked.connect(lambda: self._export_alignment('clustal'))
        el.addWidget(export_clustal_btn)

        el.addStretch()
        self.results_tabs.addTab(export_tab, feather_icon("download", 16), "Export")

        splitter.addWidget(self.results_tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        settings = QSettings("SenLab", "ProteinGUI")
        if settings.contains("alignment_splitter"):
            splitter.restoreState(settings.value("alignment_splitter"))
        else:
            splitter.setSizes([350, 400])

        self.splitter = splitter
        splitter.splitterMoved.connect(self._save_splitter_state)

        root.addWidget(splitter)

    # ── Input method switching ───────────────────────────────────
    def _on_input_method_changed(self):
        if self.upload_radio.isChecked():
            self.upload_widget.show()
            self.paste_widget.hide()
        else:
            self.upload_widget.hide()
            self.paste_widget.show()

    # ── System requirements ──────────────────────────────────────
    def check_system_requirements(self):
        warmup_wsl()

        if not is_wsl_available():
            self.warning_label.setText(
                "Command execution environment not available.\n"
                "Please check your system setup to use this feature."
            )
            self.warning_label.show()
            self.run_button.setEnabled(False)
            return

        clustalo_installed, version, path = check_clustalo_installation()
        if not clustalo_installed:
            hint = get_platform_tool_install_hint('clustalo')
            self.warning_label.setText(
                f"Clustal Omega not found. Please install it to use alignment.\n{hint}"
            )
            self.warning_label.show()
            self.run_button.setEnabled(False)
            return

        self.warning_label.hide()

    # ── File browsing ────────────────────────────────────────────
    def browse_fasta_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select FASTA File", "",
            "FASTA Files (*.fasta *.fa *.faa);;All Files (*.*)"
        )
        if file_path:
            self.load_fasta_file(file_path)

    def load_fasta_file(self, file_path, is_temp=False):
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "File Not Found", f"File not found: {file_path}")
            return False

        is_valid, message, seq_count = SequenceAlignmentPrep.validate_fasta_for_alignment(file_path)

        self.input_fasta_path = file_path
        self.file_path_input.setText(file_path)
        self.is_temp_fasta = is_temp

        t = get_theme()
        if is_valid:
            self.file_info_label.setText(message)
            self.file_info_label.setStyleSheet(f"color: {t.get('success')}; font-style: italic;")
            self.run_button.setEnabled(True)
        else:
            self.file_info_label.setText(message)
            self.file_info_label.setStyleSheet(f"color: {t.get('error')}; font-style: italic;")
            self.run_button.setEnabled(False)

        self.save_fasta_button.setVisible(is_temp)
        return is_valid

    # ── Run alignment ────────────────────────────────────────────
    def run_alignment(self):
        if self.paste_radio.isChecked():
            paste_content = self.paste_text.toPlainText().strip()
            if not paste_content:
                QMessageBox.warning(self, "No Sequences", "Please paste sequences in FASTA format.")
                return

            try:
                fd, temp_path = tempfile.mkstemp(suffix='.fasta', prefix='alignment_input_')
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(paste_content)

                self.input_fasta_path = temp_path
                self.is_temp_fasta = True

                is_valid, message, seq_count = SequenceAlignmentPrep.validate_fasta_for_alignment(temp_path)
                if not is_valid:
                    QMessageBox.warning(self, "Invalid Sequences", message)
                    os.remove(temp_path)
                    return
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save sequences: {str(e)}")
                return

        if not self.input_fasta_path:
            QMessageBox.warning(self, "No File", "Please select a FASTA file first.")
            return

        output_format = self.format_combo.currentData()
        iterations = self.iter_spin.value()
        full_iter = self.full_iter_checkbox.isChecked()

        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.results_tabs.hide()

        self.alignment_worker = AlignmentWorker(
            self.input_fasta_path,
            output_format=output_format,
            iterations=iterations,
            full_iter=full_iter
        )
        self.alignment_worker.progress.connect(self.on_progress)
        self.alignment_worker.finished.connect(self.on_alignment_finished)
        self.alignment_worker.error.connect(self.on_alignment_error)
        self.alignment_worker.start()

    def cancel_alignment(self):
        if self.alignment_worker:
            self.alignment_worker.cancel()
            self.alignment_worker.terminate()
            self.alignment_worker.wait()

        self.status_label.setText("Alignment cancelled")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()

    def on_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def on_alignment_finished(self, aligned_content, output_path):
        self.aligned_content = aligned_content
        self.output_alignment_path = output_path

        if self.format_combo.currentData() == 'fasta':
            self.msa_viewer.load_alignment(aligned_content)
        else:
            self.msa_viewer.load_alignment_file(output_path)

        self.raw_alignment_text.setPlainText(aligned_content)

        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText("Alignment complete!")
        self.results_tabs.show()

    def on_alignment_error(self, error_msg):
        QMessageBox.critical(self, "Alignment Error", f"An error occurred:\n\n{error_msg}")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
        self.status_label.setText("Error occurred")

    # ── Export ───────────────────────────────────────────────────
    def _export_alignment(self, format_type):
        if not self.aligned_content:
            QMessageBox.warning(self, "No Alignment", "No alignment available to export.")
            return

        if self.format_combo.currentData() == format_type:
            content = self.aligned_content
        else:
            QMessageBox.information(
                self, "Format Conversion",
                f"To export in {format_type.upper()} format, please re-run the alignment "
                f"with '{format_type.upper()}' selected as the output format."
            )
            return

        ext_map = {'fasta': '.fasta', 'clustal': '.aln'}
        ext = ext_map.get(format_type, '.txt')

        file_path, _ = QFileDialog.getSaveFileName(
            self, f"Export Alignment as {format_type.upper()}",
            f"alignment{ext}",
            f"{format_type.upper()} Files (*{ext});;All Files (*.*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                QMessageBox.information(self, "Export Successful", f"Alignment exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")

    def _save_input_fasta(self):
        if not self.input_fasta_path or not os.path.exists(self.input_fasta_path):
            QMessageBox.warning(self, "No File", "No input FASTA file to save.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save FASTA File", "sequences.fasta",
            "FASTA Files (*.fasta *.fa);;All Files (*.*)"
        )

        if file_path:
            try:
                shutil.copy2(self.input_fasta_path, file_path)
                QMessageBox.information(self, "Save Successful", f"FASTA file saved to:\n{file_path}")
                self.input_fasta_path = file_path
                self.file_path_input.setText(file_path)
                self.is_temp_fasta = False
                self.save_fasta_button.setVisible(False)
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save:\n{str(e)}")

    def _save_splitter_state(self):
        settings = QSettings("SenLab", "ProteinGUI")
        settings.setValue("alignment_splitter", self.splitter.saveState())

    def load_sequences_from_search(self, fasta_path, source_info=None):
        """Load sequences from a search result (BLAST/MMseqs2)."""
        success = self.load_fasta_file(fasta_path, is_temp=True)

        if success:
            QMessageBox.information(
                self, "Sequences Loaded",
                "Sequences have been loaded for alignment.\n\n"
                "Click 'Save Input FASTA' to save permanently.\n"
                "Adjust parameters and click 'Run Alignment' when ready."
            )
