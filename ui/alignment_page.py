"""Sequence Alignment page - Multiple sequence alignment (several backends)."""
import os
import shutil
import tempfile
import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QLineEdit, QComboBox, QGroupBox, QTextEdit,
    QProgressBar, QMessageBox, QTabWidget, QRadioButton, QButtonGroup,
    QFrame, QSpinBox, QCheckBox, QSplitter, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, Qt, QTimer, QSettings

from ui.theme import get_theme
from ui.icons import feather_icon, set_button_icon
from core.tool_install_worker import ToolInstallWorker
from core.tool_runtime import get_tool_runtime
from core.tool_registry import alignment_feature_id_for_tool
from core.alignment_worker import (
    AlignmentWorker,
    SequenceAlignmentPrep,
    check_alignment_tool_installation,
    aligner_display_name,
    max_sequences_for_tool,
)
from ui.widgets.msa_viewer_widget import MSAViewerWidget, check_webengine_available


class AlignmentPage(QWidget):
    """Sequence alignment with Clustal Omega, MAFFT, MUSCLE, or FAMSA."""

    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.alignment_worker = None
        self.input_fasta_path = None
        self.output_alignment_path = None
        self.aligned_content = None
        self.loaded_sequences = []
        self.is_temp_fasta = False
        self.tool_install_worker = None
        self._pending_tool_action = None
        self._align_elapsed_timer = QTimer(self)
        self._align_elapsed_timer.setInterval(1000)
        self._align_elapsed_timer.timeout.connect(self._tick_alignment_elapsed)
        self._align_t0 = None
        self._align_status_base = ""
        self._init_ui()

        QTimer.singleShot(2000, self.check_system_requirements)

    def _init_ui(self):
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

        tool_row = QHBoxLayout()
        tool_row.addWidget(QLabel("Alignment tool:"))
        self.tool_combo = QComboBox()
        self.tool_combo.addItem("Clustal Omega", "clustalo")
        self.tool_combo.addItem("MAFFT", "mafft")
        self.tool_combo.addItem("MUSCLE", "muscle")
        self.tool_combo.addItem("FAMSA", "famsa")
        self.tool_combo.setToolTip("Choose the multiple sequence alignment program")
        tool_row.addWidget(self.tool_combo)
        tool_row.addStretch()
        pl.addLayout(tool_row)

        # Clustal Omega: iterations + full refinement
        self.clustalo_params_widget = QWidget()
        clustalo_pl = QVBoxLayout(self.clustalo_params_widget)
        clustalo_pl.setContentsMargins(0, 0, 0, 0)
        iter_row = QHBoxLayout()
        iter_row.addWidget(QLabel("Iterations:"))
        self.iter_spin = QSpinBox()
        self.iter_spin.setRange(0, 5)
        self.iter_spin.setValue(0)
        self.iter_spin.setToolTip("Number of combined iterations (0 = auto)")
        iter_row.addWidget(self.iter_spin)
        iter_row.addStretch()
        clustalo_pl.addLayout(iter_row)
        self.full_iter_checkbox = QCheckBox("Full iterative refinement")
        self.full_iter_checkbox.setToolTip("Use full iterative refinement (slower but more accurate)")
        clustalo_pl.addWidget(self.full_iter_checkbox)
        pl.addWidget(self.clustalo_params_widget)

        # MAFFT: alignment strategy
        self.mafft_params_widget = QWidget()
        mafft_pl = QVBoxLayout(self.mafft_params_widget)
        mafft_pl.setContentsMargins(0, 0, 0, 0)
        strat_row = QHBoxLayout()
        strat_row.addWidget(QLabel("MAFFT strategy:"))
        self.mafft_strategy_combo = QComboBox()
        self.mafft_strategy_combo.addItem("Auto", "auto")
        self.mafft_strategy_combo.addItem("L-INS-i (accurate, ≤200 seq)", "linsi")
        self.mafft_strategy_combo.addItem("G-INS-i", "ginsi")
        self.mafft_strategy_combo.addItem("E-INS-i", "einsi")
        self.mafft_strategy_combo.addItem("FFT-NS-2 (fast)", "fftns2")
        self.mafft_strategy_combo.setToolTip("Alignment strategy; L-INS-i is slow but accurate for few sequences")
        strat_row.addWidget(self.mafft_strategy_combo)
        strat_row.addStretch()
        mafft_pl.addLayout(strat_row)
        pl.addWidget(self.mafft_params_widget)
        self.mafft_params_widget.hide()

        # FAMSA: optional medoid tree (large sets)
        self.famsa_params_widget = QWidget()
        famsa_pl = QVBoxLayout(self.famsa_params_widget)
        famsa_pl.setContentsMargins(0, 0, 0, 0)
        self.famsa_medoid_checkbox = QCheckBox("Use medoid tree (recommended for very large sets)")
        self.famsa_medoid_checkbox.setToolTip("FAMSA --medoid-tree: faster, scalable guide tree for huge inputs")
        famsa_pl.addWidget(self.famsa_medoid_checkbox)
        pl.addWidget(self.famsa_params_widget)
        self.famsa_params_widget.hide()

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Output format:"))
        self.format_combo = QComboBox()
        fmt_row.addWidget(self.format_combo)
        fmt_row.addStretch()
        pl.addLayout(fmt_row)

        self.tool_combo.currentIndexChanged.connect(self._on_alignment_tool_changed)
        self._refresh_output_format_combo()

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

    def _selected_tool_id(self):
        return self.tool_combo.currentData() or "clustalo"

    def _refresh_output_format_combo(self):
        """Repopulate output formats based on the selected aligner."""
        tool_id = self._selected_tool_id()
        prev = self.format_combo.currentData()
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        if tool_id == "clustalo":
            self.format_combo.addItem("FASTA (aligned)", "fasta")
            self.format_combo.addItem("Clustal", "clustal")
            self.format_combo.addItem("MSF", "msf")
            self.format_combo.addItem("PHYLIP", "phylip")
            self.format_combo.addItem("Stockholm", "stockholm")
        elif tool_id == "mafft":
            self.format_combo.addItem("FASTA (aligned)", "fasta")
            self.format_combo.addItem("Clustal", "clustal")
        else:
            self.format_combo.addItem("FASTA (aligned)", "fasta")
        # Restore previous format if still valid
        idx = self.format_combo.findData(prev)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)
        else:
            self.format_combo.setCurrentIndex(0)
        self.format_combo.blockSignals(False)

    def _on_alignment_tool_changed(self):
        tool_id = self._selected_tool_id()
        self.clustalo_params_widget.setVisible(tool_id == "clustalo")
        self.mafft_params_widget.setVisible(tool_id == "mafft")
        self.famsa_params_widget.setVisible(tool_id == "famsa")
        self._refresh_output_format_combo()
        self.check_system_requirements()
        if self.input_fasta_path and os.path.exists(self.input_fasta_path):
            self.load_fasta_file(self.input_fasta_path, is_temp=self.is_temp_fasta)

    # ── System requirements ──────────────────────────────────────
    def check_system_requirements(self):
        runtime = get_tool_runtime()
        tool_id = self._selected_tool_id()
        name = aligner_display_name(tool_id)
        installed, _version, _path = check_alignment_tool_installation(tool_id)
        if not installed:
            self.warning_label.setText(
                f"{name} is not currently available. Use the Tools tab to install it, "
                "or click Run and the app will prompt to install it."
            )
            self.warning_label.show()
            self.run_button.setEnabled(bool(runtime.get_installable_tools([tool_id])))
            return

        self.warning_label.hide()
        # Run stays disabled until a valid FASTA is loaded (see load_fasta_file)
        if self.input_fasta_path and os.path.exists(self.input_fasta_path):
            max_seq = max_sequences_for_tool(tool_id)
            is_valid, _msg, _c = SequenceAlignmentPrep.validate_fasta_for_alignment(
                self.input_fasta_path, max_sequences=max_seq
            )
            self.run_button.setEnabled(is_valid)
        else:
            self.run_button.setEnabled(True)

    def _ensure_alignment_tools(self):
        runtime = get_tool_runtime()
        tool_id = self._selected_tool_id()
        feature_id = alignment_feature_id_for_tool(tool_id)
        missing = runtime.get_missing_tools_for_feature(feature_id)
        if not missing:
            return True

        name = aligner_display_name(tool_id)
        installable = runtime.get_installable_tools(missing)
        if installable:
            reply = QMessageBox.question(
                self,
                "Install Required Tools",
                f"Alignment requires {name}.\n\nInstall it now?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False
            self._pending_tool_action = self.run_alignment
            self.run_button.setEnabled(False)
            self.status_label.setText("Installing required tools...")
            self.tool_install_worker = ToolInstallWorker(installable)
            self.tool_install_worker.progress.connect(
                lambda current, total, status: self.status_label.setText(status)
            )
            self.tool_install_worker.install_finished.connect(self._on_tool_install_finished)
            self.tool_install_worker.error.connect(self._on_tool_install_error)
            self.tool_install_worker.finished.connect(self._on_tool_install_thread_finished)
            self.tool_install_worker.start()
            return False

        QMessageBox.warning(
            self,
            "Tool Missing",
            f"{name} is not available on this system and cannot be installed automatically here.",
        )
        return False

    def _on_tool_install_thread_finished(self):
        worker = self.sender()
        if worker is not self.tool_install_worker:
            return
        self.tool_install_worker = None

    def _on_tool_install_finished(self, _result):
        self.run_button.setEnabled(True)
        self.check_system_requirements()
        self.status_label.setText("Required tools installed.")
        pending = self._pending_tool_action
        self._pending_tool_action = None
        if pending is not None:
            pending()

    def _on_tool_install_error(self, error_msg):
        self.run_button.setEnabled(True)
        self._pending_tool_action = None
        self.status_label.setText("Tool installation failed.")
        QMessageBox.critical(self, "Tool Install Error", error_msg)

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

        max_seq = max_sequences_for_tool(self._selected_tool_id())
        is_valid, message, seq_count = SequenceAlignmentPrep.validate_fasta_for_alignment(
            file_path, max_sequences=max_seq
        )

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
        if not self._ensure_alignment_tools():
            return
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

                max_seq = max_sequences_for_tool(self._selected_tool_id())
                is_valid, message, seq_count = SequenceAlignmentPrep.validate_fasta_for_alignment(
                    temp_path, max_sequences=max_seq
                )
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
        tool_id = self._selected_tool_id()
        mafft_strategy = self.mafft_strategy_combo.currentData() or "auto"
        famsa_medoid = self.famsa_medoid_checkbox.isChecked()

        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.results_tabs.hide()

        self._align_t0 = time.monotonic()
        self._align_status_base = ""
        self._align_elapsed_timer.start()

        self.alignment_worker = AlignmentWorker(
            self.input_fasta_path,
            tool_id=tool_id,
            output_format=output_format,
            iterations=iterations,
            full_iter=full_iter,
            mafft_strategy=mafft_strategy,
            famsa_medoid_tree=famsa_medoid,
        )
        self.alignment_worker.progress.connect(self.on_progress)
        self.alignment_worker.finished.connect(self.on_alignment_finished)
        self.alignment_worker.error.connect(self.on_alignment_error)
        self.alignment_worker.start()

    def cancel_alignment(self):
        self._stop_alignment_elapsed_timer()
        if self.alignment_worker:
            self.alignment_worker.cancel()
            self.alignment_worker.terminate()
            self.alignment_worker.wait()

        self.status_label.setText("Alignment cancelled")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()

    def _stop_alignment_elapsed_timer(self):
        self._align_elapsed_timer.stop()
        self._align_t0 = None

    def _refresh_alignment_status_label(self):
        if self._align_t0 is None:
            return
        secs = int(time.monotonic() - self._align_t0)
        m, s = secs // 60, secs % 60
        base = self._align_status_base or "Working"
        self.status_label.setText(f"{base}   (elapsed {m}:{s:02d})")

    def _tick_alignment_elapsed(self):
        self._refresh_alignment_status_label()

    def on_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self._align_status_base = message
        self._refresh_alignment_status_label()

    def on_alignment_finished(self, aligned_content, output_path):
        self._stop_alignment_elapsed_timer()
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
        self._stop_alignment_elapsed_timer()
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
