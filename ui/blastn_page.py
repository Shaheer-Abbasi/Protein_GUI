"""BLASTN (Nucleotide BLAST) page for nucleotide sequence searches"""
import os
import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel,
    QComboBox, QHBoxLayout, QCheckBox, QLineEdit, QFileDialog,
    QGroupBox, QRadioButton, QButtonGroup, QMessageBox, QFrame, QDialog,
    QSpinBox, QDoubleSpinBox, QScrollArea, QSplitter, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from ui.theme import get_theme
from ui.icons import feather_icon, set_button_icon
from ui.widgets.results_panel import SearchResultsPanel
from core.db_definitions import (
    get_blastn_databases,
    get_default_blastn_database,
    is_remote_blastn_database_supported,
)
from core.blastn_worker import BLASTNWorker
from core.config_manager import get_config
from core.tool_install_worker import ToolInstallWorker
from core.tool_runtime import get_tool_runtime
from utils.fasta_parser import FastaParser, FastaParseError
from utils.export_manager import ResultsExporter, ExportError, show_export_error, show_export_success
from ui.dialogs.nucleotide_search_dialog import NucleotideSearchDialog


def validate_nucleotide_sequence(sequence):
    valid_chars = set('ATGCUNRYSWKMBDHV')
    sequence_upper = sequence.upper()
    invalid_chars = set(sequence_upper) - valid_chars
    return len(invalid_chars) == 0, invalid_chars


class BLASTNPage(QWidget):
    back_requested = pyqtSignal()
    navigate_to_alignment = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.blast_worker = None
        self.search_start_time = None
        self.current_results_html = ""
        self.current_results_data = []
        self.current_query_info = {}
        self.fasta_parser = FastaParser()
        self.exporter = ResultsExporter()
        self.loaded_sequences = []
        self.current_sequence_metadata = {}
        self.tool_install_worker = None
        self._pending_tool_action = None
        self._init_ui()

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

        title = QLabel("BLASTN Nucleotide Search")
        title.setProperty("class", "title")
        form.addWidget(title)

        # ── Input method ────────────────────────────────────────
        input_group = QGroupBox("Sequence Input")
        ig_layout = QVBoxLayout()

        method_row = QHBoxLayout()
        self.input_method_group = QButtonGroup()
        self.paste_radio = QRadioButton("Paste Sequence")
        self.upload_radio = QRadioButton("Upload FASTA File")
        self.search_radio = QRadioButton("Search NCBI Database")
        self.paste_radio.setChecked(True)
        self.input_method_group.addButton(self.paste_radio, 1)
        self.input_method_group.addButton(self.upload_radio, 2)
        self.input_method_group.addButton(self.search_radio, 3)
        for r in (self.paste_radio, self.upload_radio, self.search_radio):
            method_row.addWidget(r)
            r.toggled.connect(self._on_input_method_changed)
        method_row.addStretch()
        ig_layout.addLayout(method_row)

        # Paste widget
        self.paste_widget = QWidget()
        pw = QVBoxLayout(self.paste_widget)
        pw.setContentsMargins(0, 0, 0, 0)
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Paste your nucleotide sequence here (A, T, G, C, N)...")
        self.input_text.setMinimumHeight(60)
        self.input_text.textChanged.connect(self._update_sequence_counter)
        self.sequence_counter = QLabel("0 nucleotides")
        self.sequence_counter.setProperty("class", "muted")
        pw.addWidget(self.input_text)
        pw.addWidget(self.sequence_counter)

        # Upload widget
        self.upload_widget = QWidget()
        uw = QVBoxLayout(self.upload_widget)
        uw.setContentsMargins(0, 0, 0, 0)
        ub_row = QHBoxLayout()
        self.upload_fasta_button = QPushButton("Choose FASTA File")
        set_button_icon(self.upload_fasta_button, "folder", 14, "#FFFFFF")
        self.upload_fasta_button.clicked.connect(self._upload_fasta_file)
        self.fasta_file_label = QLabel("No file selected")
        self.fasta_file_label.setProperty("class", "muted")
        ub_row.addWidget(self.upload_fasta_button)
        ub_row.addWidget(self.fasta_file_label)
        ub_row.addStretch()
        self.fasta_sequence_selector = QComboBox()
        self.fasta_sequence_selector.setVisible(False)
        self.fasta_sequence_selector.currentIndexChanged.connect(self._on_fasta_sequence_selected)
        uw.addLayout(ub_row)
        uw.addWidget(self.fasta_sequence_selector)
        self.upload_widget.setVisible(False)

        # Search widget
        self.search_widget = QWidget()
        sw = QVBoxLayout(self.search_widget)
        sw.setContentsMargins(0, 0, 0, 0)
        sb_row = QHBoxLayout()
        self.search_db_button = QPushButton("Search NCBI GenBank")
        set_button_icon(self.search_db_button, "search", 14, "#FFFFFF")
        self.search_db_button.clicked.connect(self._open_nucleotide_search)
        self.search_info_label = QLabel("Search GenBank by gene name, accession, or keywords")
        self.search_info_label.setProperty("class", "muted")
        sb_row.addWidget(self.search_db_button)
        sb_row.addWidget(self.search_info_label)
        sb_row.addStretch()
        sw.addLayout(sb_row)
        self.search_widget.setVisible(False)

        ig_layout.addWidget(self.paste_widget)
        ig_layout.addWidget(self.upload_widget)
        ig_layout.addWidget(self.search_widget)
        input_group.setLayout(ig_layout)
        form.addWidget(input_group)

        # ── Database options ────────────────────────────────────
        db_group = QGroupBox("Database Options")
        dg = QVBoxLayout()

        src_row = QHBoxLayout()
        self.remote_radio = QCheckBox("Use Remote NCBI Database")
        self.remote_radio.setChecked(True)
        self.remote_radio.toggled.connect(self.on_database_source_changed)
        src_row.addWidget(self.remote_radio)

        db_sel = QVBoxLayout()
        self.db_combo = QComboBox()
        self.db_combo.currentTextChanged.connect(self.on_database_changed)

        self.db_description = QLabel()
        self.db_description.setWordWrap(True)
        self.db_description.setProperty("class", "muted")

        self.db_mode_hint = QLabel()
        self.db_mode_hint.setWordWrap(True)
        self.db_mode_hint.setProperty("class", "muted")

        db_sel.addWidget(self.db_combo)
        db_sel.addWidget(self.db_description)
        db_sel.addWidget(self.db_mode_hint)

        local_row = QHBoxLayout()
        self.local_db_label = QLabel("Local DB Path:")
        self.local_db_path = QLineEdit()
        self.local_db_path.setPlaceholderText("Path to local database directory (optional)")
        self.browse_button = QPushButton("Browse")
        self.browse_button.setProperty("class", "secondary")
        set_button_icon(self.browse_button, "folder", 14)
        self.browse_button.clicked.connect(self.browse_database_path)
        local_row.addWidget(self.local_db_label)
        local_row.addWidget(self.local_db_path)
        local_row.addWidget(self.browse_button)

        dg.addLayout(src_row)
        dg.addLayout(db_sel)
        dg.addLayout(local_row)
        db_group.setLayout(dg)
        self._populate_database_combo()
        self.on_database_source_changed()
        form.addWidget(db_group)

        # ── Advanced settings ───────────────────────────────────
        adv_group = QGroupBox("Advanced Settings")
        ag = QVBoxLayout()

        self.show_advanced_checkbox = QCheckBox("Show Advanced Options")
        self.show_advanced_checkbox.stateChanged.connect(self._toggle_advanced_options)

        self.advanced_options_widget = QWidget()
        ao = QVBoxLayout(self.advanced_options_widget)
        ao.setContentsMargins(0, 8, 0, 0)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Algorithm:"))
        self.task_combo = QComboBox()
        self.task_combo.addItems([
            "blastn (standard)", "blastn-short (short sequences)",
            "megablast (highly similar)", "dc-megablast (discontinuous)"
        ])
        self.task_combo.currentIndexChanged.connect(self._update_word_size)
        r1.addWidget(self.task_combo)
        r1.addSpacing(16)
        r1.addWidget(QLabel("E-value Threshold:"))
        self.evalue_input = QDoubleSpinBox()
        self.evalue_input.setRange(1e-200, 1000)
        self.evalue_input.setDecimals(0)
        self.evalue_input.setValue(10)
        r1.addWidget(self.evalue_input)
        r1.addStretch()
        ao.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Max Hits:"))
        self.max_targets_input = QSpinBox()
        self.max_targets_input.setRange(1, 5000)
        self.max_targets_input.setValue(100)
        r2.addWidget(self.max_targets_input)
        r2.addSpacing(16)
        r2.addWidget(QLabel("Word Size:"))
        self.word_size_input = QSpinBox()
        self.word_size_input.setRange(4, 64)
        self.word_size_input.setValue(11)
        r2.addWidget(self.word_size_input)
        r2.addStretch()
        ao.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Match Reward:"))
        self.reward_input = QSpinBox()
        self.reward_input.setRange(1, 10)
        self.reward_input.setValue(2)
        r3.addWidget(self.reward_input)
        r3.addSpacing(16)
        r3.addWidget(QLabel("Mismatch Penalty:"))
        self.penalty_input = QSpinBox()
        self.penalty_input.setRange(-10, -1)
        self.penalty_input.setValue(-3)
        r3.addWidget(self.penalty_input)
        r3.addStretch()
        ao.addLayout(r3)

        r4 = QHBoxLayout()
        r4.addWidget(QLabel("Gap Open Cost:"))
        self.gap_open_input = QSpinBox()
        self.gap_open_input.setRange(1, 50)
        self.gap_open_input.setValue(5)
        r4.addWidget(self.gap_open_input)
        r4.addSpacing(16)
        r4.addWidget(QLabel("Gap Extend:"))
        self.gap_extend_input = QSpinBox()
        self.gap_extend_input.setRange(1, 10)
        self.gap_extend_input.setValue(2)
        r4.addWidget(self.gap_extend_input)
        r4.addStretch()
        ao.addLayout(r4)

        r5 = QHBoxLayout()
        self.dust_checkbox = QCheckBox("Filter Low Complexity (DUST)")
        self.dust_checkbox.setChecked(True)
        self.soft_masking_checkbox = QCheckBox("Soft Masking")
        r5.addWidget(self.dust_checkbox)
        r5.addSpacing(16)
        r5.addWidget(self.soft_masking_checkbox)
        r5.addStretch()
        ao.addLayout(r5)

        self.advanced_options_widget.hide()
        ag.addWidget(self.show_advanced_checkbox)
        ag.addWidget(self.advanced_options_widget)
        adv_group.setLayout(ag)
        form.addWidget(adv_group)

        # Run / Cancel buttons + status
        btn_row = QHBoxLayout()
        self.process_button = QPushButton("Run BLASTN Search")
        self.process_button.setProperty("class", "success")
        set_button_icon(self.process_button, "play", 16, "#FFFFFF")
        self.process_button.setMinimumHeight(40)
        self.process_button.clicked.connect(self.run_blast)

        self.cancel_button = QPushButton("Cancel Search")
        self.cancel_button.setProperty("class", "danger")
        set_button_icon(self.cancel_button, "x", 14, "#FFFFFF")
        self.cancel_button.setMinimumHeight(40)
        self.cancel_button.clicked.connect(self._cancel_search)
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()

        btn_row.addWidget(self.process_button)
        btn_row.addWidget(self.cancel_button)
        btn_row.addStretch()
        form.addLayout(btn_row)

        self.status_label = QLabel("Ready")
        self.status_label.setProperty("class", "muted")
        form.addWidget(self.status_label)

        input_scroll.setWidget(input_widget)
        splitter.addWidget(input_scroll)

        # ── Bottom: results panel ────────────────────────────────
        self.results_panel = SearchResultsPanel(show_align_button=False)
        self.results_panel.export_requested.connect(self._export_results)
        splitter.addWidget(self.results_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 500])

        root.addWidget(splitter)

    # ── Input method switching ────────────────────────────────────

    def _on_input_method_changed(self):
        self.paste_widget.setVisible(self.paste_radio.isChecked())
        self.upload_widget.setVisible(self.upload_radio.isChecked())
        self.search_widget.setVisible(self.search_radio.isChecked())

    def _toggle_advanced_options(self, state):
        self.advanced_options_widget.setVisible(state == Qt.Checked)

    def _update_word_size(self):
        word_sizes = {0: 11, 1: 7, 2: 28, 3: 11}
        idx = self.task_combo.currentIndex()
        if idx in word_sizes:
            self.word_size_input.setValue(word_sizes[idx])

    def _get_advanced_params(self):
        task_map = {0: "blastn", 1: "blastn-short", 2: "megablast", 3: "dc-megablast"}
        return {
            'task': task_map.get(self.task_combo.currentIndex(), "blastn"),
            'evalue': self.evalue_input.value(),
            'max_target_seqs': self.max_targets_input.value(),
            'word_size': self.word_size_input.value(),
            'reward': self.reward_input.value(),
            'penalty': self.penalty_input.value(),
            'gap_open': self.gap_open_input.value(),
            'gap_extend': self.gap_extend_input.value(),
            'dust': 'yes' if self.dust_checkbox.isChecked() else 'no',
            'soft_masking': self.soft_masking_checkbox.isChecked()
        }

    def _update_sequence_counter(self):
        text = self.input_text.toPlainText().strip().upper()
        count = len(''.join(c for c in text if c.isalpha()))
        self.sequence_counter.setText(f"{count} nucleotides")
        t = get_theme()
        if count == 0:
            self.sequence_counter.setStyleSheet(f"color:{t.get('text_muted')};")
        elif count < 10:
            self.sequence_counter.setStyleSheet(f"color:{t.get('error')}; font-weight:600;")
        elif count > 50000:
            self.sequence_counter.setStyleSheet(f"color:{t.get('warning')}; font-weight:600;")
        else:
            self.sequence_counter.setStyleSheet(f"color:{t.get('success')}; font-weight:600;")

    # ── FASTA upload ──────────────────────────────────────────────

    def _upload_fasta_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open FASTA File", "",
            "FASTA Files (*.fasta *.fa *.fna *.ffn *.faa *.frn);;All Files (*)")
        if not filepath:
            return
        try:
            sequences = self.fasta_parser.parse_file(filepath)
            if self.fasta_parser.has_warnings():
                QMessageBox.warning(self, "FASTA Parsing Warnings",
                    f"File loaded with warnings:\n\n{chr(10).join(self.fasta_parser.get_warnings())}")
            self.loaded_sequences = sequences
            filename = os.path.basename(filepath)
            if len(sequences) == 1:
                self.fasta_file_label.setText(f"{filename} ({len(sequences[0].sequence)} nt)")
                self.fasta_sequence_selector.setVisible(False)
                self.input_text.setPlainText(sequences[0].sequence)
                self.current_sequence_metadata = {
                    'source': 'fasta_file', 'filename': filename,
                    'header': sequences[0].header, 'id': sequences[0].id}
            else:
                self.fasta_file_label.setText(f"{filename} ({len(sequences)} sequences)")
                self.fasta_sequence_selector.clear()
                for seq in sequences:
                    self.fasta_sequence_selector.addItem(f"{seq.id} ({len(seq.sequence)} nt)", seq)
                self.fasta_sequence_selector.setVisible(True)
                self._on_fasta_sequence_selected(0)
        except FastaParseError as e:
            QMessageBox.critical(self, "FASTA Parsing Error", f"Failed to parse FASTA file:\n\n{e}")
            self.fasta_file_label.setText("No file selected")

    def _on_fasta_sequence_selected(self, index):
        if index < 0 or not self.loaded_sequences:
            return
        seq = self.fasta_sequence_selector.itemData(index)
        if seq:
            self.input_text.setPlainText(seq.sequence)
            self.current_sequence_metadata = {
                'source': 'fasta_file', 'header': seq.header, 'id': seq.id}

    # ── Nucleotide search dialog ──────────────────────────────────

    def _open_nucleotide_search(self):
        dialog = NucleotideSearchDialog(self)
        dialog.sequence_selected.connect(self._on_nucleotide_selected)
        dialog.exec_()

    def _on_nucleotide_selected(self, sequence, metadata):
        accession = metadata.get('accession', 'Unknown')
        title = metadata.get('title', 'Unknown')
        organism = metadata.get('organism', 'Unknown')
        length = metadata.get('length', 0)
        display_title = title[:50] + "..." if len(title) > 50 else title
        reply = QMessageBox.question(self, "Load Sequence",
            f"Load nucleotide sequence?\n\n"
            f"Accession: {accession}\n"
            f"Title: {display_title}\n"
            f"Organism: {organism}\n"
            f"Length: {length:,} nucleotides",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.input_text.setPlainText(sequence)
            self.current_sequence_metadata = {
                'source': 'genbank', 'accession': accession,
                'title': title, 'organism': organism, 'id': accession}
            self.search_info_label.setText(f"Loaded: {accession} ({organism})")
            self.search_info_label.setStyleSheet(
                f"color:{get_theme().get('success')}; font-weight:600;")

    # ── Database helpers ──────────────────────────────────────────

    def on_database_changed(self):
        self.update_database_description()

    def update_database_description(self):
        text = self.db_combo.currentText()
        db = text.split(' - ')[0] if ' - ' in text else text
        desc = get_blastn_databases(self.remote_radio.isChecked()).get(
            db, "Database information not available"
        )
        self.db_description.setText(desc)

    def _populate_database_combo(self):
        use_remote = self.remote_radio.isChecked()
        databases = get_blastn_databases(use_remote)
        current_db = self.db_combo.currentData()

        self.db_combo.blockSignals(True)
        self.db_combo.clear()
        for db, desc in databases.items():
            self.db_combo.addItem(f"{db} - {desc}", db)

        target_db = current_db if current_db in databases else get_default_blastn_database(use_remote)
        index = self.db_combo.findData(target_db)
        if index >= 0:
            self.db_combo.setCurrentIndex(index)
        self.db_combo.blockSignals(False)
        self.update_database_description()

    def on_database_source_changed(self):
        remote = self.remote_radio.isChecked()
        self._populate_database_combo()
        self.local_db_label.setEnabled(not remote)
        self.local_db_path.setEnabled(not remote)
        self.browse_button.setEnabled(not remote)
        if remote:
            self.db_mode_hint.setText(
                "Remote BLASTN is slower and supports a smaller database list. "
                "For the best chance of a timely result, start with core_nt or use a local database."
            )
        else:
            self.db_mode_hint.setText(
                "Local BLASTN supports the full installed database set and is recommended for repeat searches."
            )

    def browse_database_path(self):
        d = QFileDialog.getExistingDirectory(self, "Select Database Directory", "",
            QFileDialog.ShowDirsOnly)
        if d:
            self.local_db_path.setText(d)

    # ── Export ────────────────────────────────────────────────────

    def _export_results(self, fmt):
        if not self.current_results_html:
            QMessageBox.warning(self, "No Results", "No results available to export.")
            return
        query_name = self.current_sequence_metadata.get('id', 'query')
        default_fn = self.exporter.get_default_filename('blastn', query_name)
        ext = fmt.upper()
        fp, _ = QFileDialog.getSaveFileName(self, f"Save Results as {ext}",
            f"{default_fn}.{fmt}", f"{ext} Files (*.{fmt});;All Files (*)")
        if not fp:
            return
        try:
            if self.exporter.export_blast_results(
                    self.current_results_html, self.current_query_info, fp, fmt):
                show_export_success(self, fp)
        except ExportError as e:
            show_export_error(self, e)

    # ── Run BLASTN ────────────────────────────────────────────────

    def _ensure_blastn_tools(self):
        runtime = get_tool_runtime()
        missing = runtime.get_missing_tools_for_feature("blastn")
        if not missing:
            return True

        installable = runtime.get_installable_tools(missing)
        if installable:
            reply = QMessageBox.question(
                self,
                "Install Required Tools",
                "BLASTN requires BLAST+.\n\nInstall it now?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False

            self._pending_tool_action = self.run_blast
            self.process_button.setEnabled(False)
            self.status_label.setText("Installing required tools...")
            self.tool_install_worker = ToolInstallWorker(installable)
            self.tool_install_worker.progress.connect(
                lambda current, total, status: self.status_label.setText(status)
            )
            self.tool_install_worker.finished.connect(self._on_tool_install_finished)
            self.tool_install_worker.error.connect(self._on_tool_install_error)
            self.tool_install_worker.start()
            return False

        QMessageBox.warning(
            self,
            "BLAST+ Missing",
            "BLASTN requires BLAST+ and it is not currently available on this system.",
        )
        return False

    def _on_tool_install_finished(self, _result):
        self.tool_install_worker = None
        self.process_button.setEnabled(True)
        self.status_label.setText("Required tools installed.")
        pending = self._pending_tool_action
        self._pending_tool_action = None
        if pending is not None:
            pending()

    def _on_tool_install_error(self, error_msg: str):
        self.tool_install_worker = None
        self.process_button.setEnabled(True)
        self._pending_tool_action = None
        self.status_label.setText("Tool installation failed.")
        QMessageBox.critical(self, "Tool Install Error", error_msg)

    def run_blast(self):
        if not self._ensure_blastn_tools():
            return
        sequence = self.input_text.toPlainText().strip().upper()
        if not sequence:
            self.status_label.setText("Please enter a nucleotide sequence first.")
            return
        sequence = ''.join(c for c in sequence if c.isalpha())
        is_valid, invalid_chars = validate_nucleotide_sequence(sequence)
        if not is_valid:
            self.status_label.setText(
                f"Invalid sequence: found characters {', '.join(sorted(invalid_chars))}")
            return

        db_text = self.db_combo.currentText()
        database = self.db_combo.currentData() or (db_text.split(' - ')[0] if ' - ' in db_text else db_text)
        use_remote = self.remote_radio.isChecked()
        if use_remote and not is_remote_blastn_database_supported(database):
            self.status_label.setText(
                "That database is not supported for remote BLASTN. Choose a supported remote database or use local mode."
            )
            return

        self.process_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        if use_remote:
            self.status_label.setText("Running remote BLASTN search... This may take several minutes.")
        else:
            self.status_label.setText("Running local BLASTN search...")
        self.results_panel.clear()
        local_path = self.local_db_path.text().strip()

        self.search_start_time = time.time()
        self.blast_worker = BLASTNWorker(
            sequence, database, use_remote, local_path,
            advanced_params=self._get_advanced_params())
        self.blast_worker.finished.connect(self.on_blast_finished)
        self.blast_worker.error.connect(self.on_blast_error)
        self.blast_worker.progress.connect(self._on_blast_progress)
        self.blast_worker.start()

    def _cancel_search(self):
        if self.blast_worker and self.blast_worker.isRunning():
            self.blast_worker.cancel()
            self.status_label.setText("Cancelling search...")
            self.cancel_button.setEnabled(False)

    def _on_blast_progress(self, message):
        self.status_label.setText(message)

    def on_blast_finished(self, results_html, results_data):
        elapsed = time.time() - self.search_start_time if self.search_start_time else 0
        self.current_results_html = results_html
        self.current_results_data = results_data
        self.current_query_info = {
            'tool': 'BLASTN',
            'query_name': self.current_sequence_metadata.get('id', 'query'),
            'query_length': str(len(self.input_text.toPlainText().strip())),
            'database': self.db_combo.currentText().split(' - ')[0],
            'search_time': f"{elapsed:.1f}s",
        }
        self.results_panel.set_results(results_data, self.current_query_info)
        self.status_label.setText("Search complete!")
        self.process_button.setEnabled(True)
        self.cancel_button.hide()
        self.cancel_button.setEnabled(False)

    def on_blast_error(self, error_msg):
        self.results_panel.clear()
        self.status_label.setText(f"Error: {error_msg[:120]}")
        self.process_button.setEnabled(True)
        self.cancel_button.hide()
        self.cancel_button.setEnabled(False)
