"""
Unified Protein Search page - BLASTP and MMseqs2 search in one place.
"""
import os
import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel,
    QComboBox, QHBoxLayout, QCheckBox, QLineEdit, QFileDialog,
    QGroupBox, QRadioButton, QButtonGroup, QMessageBox, QFrame, QDialog,
    QSpinBox, QDoubleSpinBox, QScrollArea, QSplitter, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, QTimer, Qt

from ui.theme import get_theme
from ui.icons import feather_icon, set_button_icon
from ui.widgets.results_panel import SearchResultsPanel
from core.db_definitions import NCBI_DATABASES
from core.blast_worker import BLASTWorker
from core.mmseqs_runner import MMseqsWorker
from core.config_manager import get_config
from core.db_conversion_manager import DatabaseConversionManager
from core.db_conversion_worker import DatabaseConversionWorker
from core.wsl_utils import (
    is_wsl_available, check_mmseqs_installation,
    check_blastdbcmd_installation, get_platform_tool_install_hint,
)
from ui.dialogs.conversion_progress_dialog import ConversionProgressDialog
from ui.dialogs.protein_search_dialog import ProteinSearchDialog
from ui.dialogs.cluster_selection_dialog import ClusterSelectionDialog
from ui.dialogs.clustering_config_dialog import ClusteringConfigDialog
from core.sequence_fetcher_worker import SequenceFetcherWorker
from core.temp_fasta_manager import get_temp_fasta_manager
from utils.fasta_parser import FastaParser, FastaParseError, validate_amino_acid_sequence
from utils.export_manager import ResultsExporter, ExportError, show_export_error, show_export_success


class ProteinSearchPage(QWidget):
    back_requested = pyqtSignal()
    navigate_to_clustering = pyqtSignal(str, dict)
    navigate_to_alignment = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.blast_worker = None
        self.mmseqs_worker = None
        self.search_start_time = None
        self.current_results_html = ""
        self.current_results_data = []
        self.current_query_info = {}
        self.current_database_path = ""
        self.fasta_parser = FastaParser()
        self.exporter = ResultsExporter()
        self.loaded_sequences = []
        self.current_sequence_metadata = {}

        # MMseqs2-specific state
        self.conversion_manager = DatabaseConversionManager()
        self.conversion_dialogs = {}
        self.blast_db_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blast_databases")
        self.installed_databases = set()
        self.custom_blast_db_path = None

        self._init_ui()

        QTimer.singleShot(100, self.scan_installed_databases)
        QTimer.singleShot(500, self._check_mmseqs_requirements)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)

        # ── Top: input controls in scroll area ───────────────────
        input_scroll = QScrollArea()
        input_scroll.setWidgetResizable(True)
        input_scroll.setFrameShape(QFrame.NoFrame)

        input_widget = QWidget()
        form = QVBoxLayout(input_widget)
        form.setContentsMargins(28, 24, 28, 16)
        form.setSpacing(16)

        title = QLabel("Protein Search")
        title.setProperty("class", "title")
        form.addWidget(title)

        # ── Tool selector ────────────────────────────────────────
        tool_group = QGroupBox("Search Tool")
        tg = QHBoxLayout()
        self.tool_group = QButtonGroup()
        self.blast_radio = QRadioButton("BLASTP")
        self.mmseqs_radio = QRadioButton("MMseqs2")
        self.blast_radio.setChecked(True)
        self.tool_group.addButton(self.blast_radio, 0)
        self.tool_group.addButton(self.mmseqs_radio, 1)
        self.blast_radio.toggled.connect(self._on_tool_changed)
        tg.addWidget(self.blast_radio)
        tg.addWidget(self.mmseqs_radio)
        tg.addStretch()
        tool_group.setLayout(tg)
        form.addWidget(tool_group)

        # ── Sequence input (shared) ──────────────────────────────
        input_group = QGroupBox("Sequence Input")
        ig_layout = QVBoxLayout()

        method_row = QHBoxLayout()
        self.input_method_group = QButtonGroup()
        self.paste_radio = QRadioButton("Paste Sequence")
        self.upload_radio = QRadioButton("Upload FASTA File")
        self.search_radio = QRadioButton("Search Protein Database")
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
        self.input_text.setPlaceholderText("Paste your amino acid sequence here (single letter codes)...")
        self.input_text.setMinimumHeight(60)
        self.input_text.textChanged.connect(self._update_sequence_counter)
        self.sequence_counter = QLabel("0 amino acids")
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
        self.search_protein_button = QPushButton("Search Protein Database")
        set_button_icon(self.search_protein_button, "search", 14, "#FFFFFF")
        self.search_protein_button.clicked.connect(self._open_protein_search)
        self.protein_info_label = QLabel("Search AlphaFold/UniProt by protein name or UniProt ID")
        self.protein_info_label.setProperty("class", "muted")
        sb_row.addWidget(self.search_protein_button)
        sb_row.addWidget(self.protein_info_label)
        sb_row.addStretch()
        sw.addLayout(sb_row)
        self.search_widget.setVisible(False)

        ig_layout.addWidget(self.paste_widget)
        ig_layout.addWidget(self.upload_widget)
        ig_layout.addWidget(self.search_widget)
        input_group.setLayout(ig_layout)
        form.addWidget(input_group)

        # ── BLASTP database options ──────────────────────────────
        self.blast_db_group = QGroupBox("Database Options")
        dg = QVBoxLayout()

        src_row = QHBoxLayout()
        self.remote_radio = QCheckBox("Use Remote NCBI Database")
        self.remote_radio.setChecked(True)
        self.remote_radio.toggled.connect(self._on_blast_db_source_changed)
        src_row.addWidget(self.remote_radio)

        db_sel = QVBoxLayout()
        self.blast_db_combo = QComboBox()
        key_dbs = ["swissprot", "nr", "pdb", "refseq_protein"]
        for db in key_dbs:
            if db in NCBI_DATABASES:
                self.blast_db_combo.addItem(f"{db} - {NCBI_DATABASES[db]}")
        for db, desc in NCBI_DATABASES.items():
            if db not in key_dbs:
                self.blast_db_combo.addItem(f"{db} - {desc}")
        self.blast_db_combo.setCurrentIndex(0)
        self.blast_db_combo.currentTextChanged.connect(self._on_blast_db_changed)

        self.blast_db_description = QLabel()
        self.blast_db_description.setWordWrap(True)
        self.blast_db_description.setProperty("class", "muted")
        self._update_blast_db_description()

        db_sel.addWidget(self.blast_db_combo)
        db_sel.addWidget(self.blast_db_description)

        local_row = QHBoxLayout()
        self.local_db_label = QLabel("Local DB Path:")
        self.local_db_path = QLineEdit()
        self.local_db_path.setPlaceholderText("Path to local database directory (optional)")
        self.blast_browse_button = QPushButton("Browse")
        self.blast_browse_button.setProperty("class", "secondary")
        set_button_icon(self.blast_browse_button, "folder", 14)
        self.blast_browse_button.clicked.connect(self._browse_blast_db_path)
        local_row.addWidget(self.local_db_label)
        local_row.addWidget(self.local_db_path)
        local_row.addWidget(self.blast_browse_button)

        dg.addLayout(src_row)
        dg.addLayout(db_sel)
        dg.addLayout(local_row)
        self.blast_db_group.setLayout(dg)
        self._on_blast_db_source_changed()
        form.addWidget(self.blast_db_group)

        # ── BLASTP advanced settings ─────────────────────────────
        self.blast_adv_group = QGroupBox("Advanced Settings")
        ag = QVBoxLayout()

        self.show_advanced_checkbox = QCheckBox("Show Advanced Options")
        self.show_advanced_checkbox.stateChanged.connect(self._toggle_advanced_options)

        self.advanced_options_widget = QWidget()
        ao = QVBoxLayout(self.advanced_options_widget)
        ao.setContentsMargins(0, 8, 0, 0)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("E-value Threshold:"))
        self.evalue_input = QDoubleSpinBox()
        self.evalue_input.setRange(1e-200, 1000)
        self.evalue_input.setDecimals(0)
        self.evalue_input.setValue(10)
        self.evalue_input.setSpecialValueText("10")
        r1.addWidget(self.evalue_input)
        r1.addSpacing(16)
        r1.addWidget(QLabel("Max Hits:"))
        self.max_targets_input = QSpinBox()
        self.max_targets_input.setRange(1, 5000)
        self.max_targets_input.setValue(100)
        r1.addWidget(self.max_targets_input)
        r1.addStretch()
        ao.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Scoring Matrix:"))
        self.matrix_combo = QComboBox()
        self.matrix_combo.addItems([
            "BLOSUM62 (default)", "BLOSUM45 (distant)", "BLOSUM80 (close)",
            "PAM30 (close)", "PAM70 (distant)"
        ])
        self.matrix_combo.currentIndexChanged.connect(self._update_gap_costs)
        r2.addWidget(self.matrix_combo)
        r2.addSpacing(16)
        r2.addWidget(QLabel("Word Size:"))
        self.word_size_input = QSpinBox()
        self.word_size_input.setRange(2, 7)
        self.word_size_input.setValue(6)
        r2.addWidget(self.word_size_input)
        r2.addStretch()
        ao.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Gap Open Cost:"))
        self.gap_open_input = QSpinBox()
        self.gap_open_input.setRange(1, 50)
        self.gap_open_input.setValue(11)
        r3.addWidget(self.gap_open_input)
        r3.addSpacing(16)
        r3.addWidget(QLabel("Gap Extend:"))
        self.gap_extend_input = QSpinBox()
        self.gap_extend_input.setRange(1, 10)
        self.gap_extend_input.setValue(1)
        r3.addWidget(self.gap_extend_input)
        r3.addStretch()
        ao.addLayout(r3)

        r4 = QHBoxLayout()
        self.low_complexity_checkbox = QCheckBox("Filter Low Complexity (SEG)")
        self.low_complexity_checkbox.setChecked(True)
        self.soft_masking_checkbox = QCheckBox("Soft Masking")
        r4.addWidget(self.low_complexity_checkbox)
        r4.addSpacing(16)
        r4.addWidget(self.soft_masking_checkbox)
        r4.addStretch()
        ao.addLayout(r4)

        r5 = QHBoxLayout()
        r5.addWidget(QLabel("Composition Adjustment:"))
        self.comp_adj_combo = QComboBox()
        self.comp_adj_combo.addItems(["Conditional (default)", "No adjustment", "Unconditional"])
        r5.addWidget(self.comp_adj_combo)
        r5.addStretch()
        ao.addLayout(r5)

        self.advanced_options_widget.hide()
        ag.addWidget(self.show_advanced_checkbox)
        ag.addWidget(self.advanced_options_widget)
        self.blast_adv_group.setLayout(ag)
        form.addWidget(self.blast_adv_group)

        # ── MMseqs2 database options ─────────────────────────────
        self.mmseqs_db_group = QGroupBox("Database Options")
        og = QVBoxLayout()

        src_lbl = QLabel("Database Source:")
        src_lbl.setStyleSheet("font-weight:600;")
        self.mmseqs_db_source_group = QButtonGroup()
        self.ncbi_radio = QRadioButton("Use NCBI Database (from blast_databases folder)")
        self.custom_ncbi_radio = QRadioButton("Browse for NCBI Database (other location)")
        self.custom_mmseqs_radio = QRadioButton("Use Existing MMseqs2 Database")
        self.mmseqs_db_source_group.addButton(self.ncbi_radio, 0)
        self.mmseqs_db_source_group.addButton(self.custom_ncbi_radio, 1)
        self.mmseqs_db_source_group.addButton(self.custom_mmseqs_radio, 2)
        self.ncbi_radio.setChecked(True)
        for r in (self.ncbi_radio, self.custom_ncbi_radio, self.custom_mmseqs_radio):
            r.toggled.connect(self._on_mmseqs_db_source_changed)

        og.addWidget(src_lbl)
        og.addWidget(self.ncbi_radio)
        og.addWidget(self.custom_ncbi_radio)
        og.addWidget(self.custom_mmseqs_radio)

        # NCBI dropdown
        self.mmseqs_ncbi_layout = QVBoxLayout()
        dd_row = QHBoxLayout()
        dd_row.addWidget(QLabel("Select Database:"))
        self.mmseqs_db_combo = QComboBox()
        self.mmseqs_db_combo.setMinimumWidth(300)
        self.mmseqs_db_combo.currentTextChanged.connect(self._on_mmseqs_db_selection_changed)
        dd_row.addWidget(self.mmseqs_db_combo)
        dd_row.addStretch()

        self.mmseqs_db_status_label = QLabel()
        self.mmseqs_db_status_label.setWordWrap(True)
        self.mmseqs_db_status_label.setProperty("class", "muted")

        self._populate_mmseqs_db_dropdown()
        self.mmseqs_ncbi_layout.addLayout(dd_row)
        self.mmseqs_ncbi_layout.addWidget(self.mmseqs_db_status_label)

        # Custom NCBI
        self.custom_ncbi_layout = QHBoxLayout()
        self.custom_ncbi_path = QLineEdit()
        self.custom_ncbi_path.setPlaceholderText("Browse to BLAST database file (without extension)")
        self.browse_ncbi_button = QPushButton("Browse")
        self.browse_ncbi_button.setProperty("class", "secondary")
        set_button_icon(self.browse_ncbi_button, "folder", 14)
        self.browse_ncbi_button.clicked.connect(self._browse_ncbi_database_path)
        self.custom_ncbi_layout.addWidget(QLabel("BLAST Database:"))
        self.custom_ncbi_layout.addWidget(self.custom_ncbi_path)
        self.custom_ncbi_layout.addWidget(self.browse_ncbi_button)

        # Custom MMseqs2
        self.custom_mmseqs_layout = QHBoxLayout()
        self.custom_mmseqs_path = QLineEdit()
        self.custom_mmseqs_path.setPlaceholderText("Path to MMseqs2 database (required)")
        self.browse_mmseqs_button = QPushButton("Browse")
        self.browse_mmseqs_button.setProperty("class", "secondary")
        set_button_icon(self.browse_mmseqs_button, "folder", 14)
        self.browse_mmseqs_button.clicked.connect(self._browse_mmseqs_database_path)
        self.custom_mmseqs_layout.addWidget(QLabel("MMseqs2 Database:"))
        self.custom_mmseqs_layout.addWidget(self.custom_mmseqs_path)
        self.custom_mmseqs_layout.addWidget(self.browse_mmseqs_button)

        # Sensitivity
        sens_row = QHBoxLayout()
        sens_row.addWidget(QLabel("Sensitivity:"))
        self.sensitivity_combo = QComboBox()
        self.sensitivity_combo.addItems([
            "fast - Fast search (less sensitive)",
            "sensitive - Balanced speed and sensitivity (default)",
            "more-sensitive - More sensitive search",
            "very-sensitive - Very sensitive search (slower)",
        ])
        self.sensitivity_combo.setCurrentIndex(1)
        sens_row.addWidget(self.sensitivity_combo)
        sens_row.addStretch()

        self.mmseqs_info_label = QLabel(
            "First-time database selection will trigger auto-conversion to MMseqs2 format.")
        self.mmseqs_info_label.setWordWrap(True)
        self.mmseqs_info_label.setProperty("class", "muted")

        og.addLayout(self.mmseqs_ncbi_layout)
        og.addLayout(self.custom_ncbi_layout)
        og.addLayout(self.custom_mmseqs_layout)
        og.addLayout(sens_row)
        og.addWidget(self.mmseqs_info_label)
        self.mmseqs_db_group.setLayout(og)
        self._on_mmseqs_db_source_changed()
        self.mmseqs_db_group.setVisible(False)
        form.addWidget(self.mmseqs_db_group)

        # ── Run button + status ──────────────────────────────────
        self.process_button = QPushButton("Run BLASTP Search")
        self.process_button.setProperty("class", "success")
        set_button_icon(self.process_button, "play", 16, "#FFFFFF")
        self.process_button.setMinimumHeight(40)
        self.process_button.clicked.connect(self._run_search)
        form.addWidget(self.process_button)

        self.status_label = QLabel("Ready")
        self.status_label.setProperty("class", "muted")
        form.addWidget(self.status_label)

        input_scroll.setWidget(input_widget)
        splitter.addWidget(input_scroll)

        # ── Bottom: results panel ────────────────────────────────
        self.results_panel = SearchResultsPanel(show_align_button=True)
        self.results_panel.export_requested.connect(self._export_results)
        self.results_panel.cluster_requested.connect(self._on_cluster_results)
        self.results_panel.align_requested.connect(self._on_align_results)
        splitter.addWidget(self.results_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 500])

        root.addWidget(splitter)

    # ── Tool switching ───────────────────────────────────────────

    def _is_blast(self):
        return self.blast_radio.isChecked()

    def _on_tool_changed(self):
        blast = self._is_blast()
        self.blast_db_group.setVisible(blast)
        self.blast_adv_group.setVisible(blast)
        self.mmseqs_db_group.setVisible(not blast)
        label = "Run BLASTP Search" if blast else "Run MMseqs2 Search"
        self.process_button.setText(label)

    # ── Input method switching ───────────────────────────────────

    def _on_input_method_changed(self):
        self.paste_widget.setVisible(self.paste_radio.isChecked())
        self.upload_widget.setVisible(self.upload_radio.isChecked())
        self.search_widget.setVisible(self.search_radio.isChecked())

    def _toggle_advanced_options(self, state):
        self.advanced_options_widget.setVisible(state == Qt.Checked)

    def _update_gap_costs(self):
        gap_costs = {0: (11, 1), 1: (15, 2), 2: (10, 1), 3: (9, 1), 4: (10, 1)}
        idx = self.matrix_combo.currentIndex()
        if idx in gap_costs:
            self.gap_open_input.setValue(gap_costs[idx][0])
            self.gap_extend_input.setValue(gap_costs[idx][1])

    def _get_advanced_params(self):
        matrix_map = {0: "BLOSUM62", 1: "BLOSUM45", 2: "BLOSUM80", 3: "PAM30", 4: "PAM70"}
        comp_adj_map = {0: 2, 1: 0, 2: 1}
        return {
            "evalue": self.evalue_input.value(),
            "max_target_seqs": self.max_targets_input.value(),
            "matrix": matrix_map.get(self.matrix_combo.currentIndex(), "BLOSUM62"),
            "word_size": self.word_size_input.value(),
            "gap_open": self.gap_open_input.value(),
            "gap_extend": self.gap_extend_input.value(),
            "seg": "yes" if self.low_complexity_checkbox.isChecked() else "no",
            "soft_masking": self.soft_masking_checkbox.isChecked(),
            "comp_based_stats": comp_adj_map.get(self.comp_adj_combo.currentIndex(), 2),
        }

    def _update_sequence_counter(self):
        text = self.input_text.toPlainText().strip().upper()
        count = len("".join(c for c in text if c.isalpha()))
        self.sequence_counter.setText(f"{count} amino acids")
        t = get_theme()
        if count == 0:
            self.sequence_counter.setStyleSheet(f"color:{t.get('text_muted')};")
        elif count < 10:
            self.sequence_counter.setStyleSheet(f"color:{t.get('error')}; font-weight:600;")
        elif count > 10000:
            self.sequence_counter.setStyleSheet(f"color:{t.get('warning')}; font-weight:600;")
        else:
            self.sequence_counter.setStyleSheet(f"color:{t.get('success')}; font-weight:600;")

    # ── FASTA upload ─────────────────────────────────────────────

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
                self.fasta_file_label.setText(f"{filename} ({len(sequences[0].sequence)} aa)")
                self.fasta_sequence_selector.setVisible(False)
                self.input_text.setPlainText(sequences[0].sequence)
                self.current_sequence_metadata = {
                    "source": "fasta_file", "filename": filename,
                    "header": sequences[0].header, "id": sequences[0].id}
            else:
                self.fasta_file_label.setText(f"{filename} ({len(sequences)} sequences)")
                self.fasta_sequence_selector.clear()
                for seq in sequences:
                    self.fasta_sequence_selector.addItem(f"{seq.id} ({len(seq.sequence)} aa)", seq)
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
            self.current_sequence_metadata = {"source": "fasta_file", "header": seq.header, "id": seq.id}

    # ── Protein search dialog ────────────────────────────────────

    def _open_protein_search(self):
        dialog = ProteinSearchDialog(self)
        dialog.sequence_selected.connect(self._on_protein_selected)
        dialog.exec_()

    def _on_protein_selected(self, sequence, metadata):
        reply = QMessageBox.question(self, "Load Sequence",
            f"Load sequence for {metadata.get('protein_name', 'Unknown')}?\n\n"
            f"UniProt ID: {metadata.get('uniprot_id', 'Unknown')}\n"
            f"Organism: {metadata.get('organism', 'Unknown')}\n"
            f"Length: {metadata.get('length', 0)} amino acids",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.input_text.setPlainText(sequence)
            self.current_sequence_metadata = metadata
            self.protein_info_label.setText(
                f"Loaded: {metadata.get('protein_name', 'Unknown')} "
                f"({metadata.get('uniprot_id', 'Unknown')})")
            self.protein_info_label.setStyleSheet(
                f"color:{get_theme().get('success')}; font-weight:600;")

    # ── BLASTP database helpers ──────────────────────────────────

    def _on_blast_db_changed(self):
        self._update_blast_db_description()

    def _update_blast_db_description(self):
        text = self.blast_db_combo.currentText()
        db = text.split(" - ")[0] if " - " in text else text
        desc = NCBI_DATABASES.get(db, "Database information not available")
        self.blast_db_description.setText(desc)

    def _on_blast_db_source_changed(self):
        remote = self.remote_radio.isChecked()
        self.local_db_label.setEnabled(not remote)
        self.local_db_path.setEnabled(not remote)
        self.blast_browse_button.setEnabled(not remote)

    def _browse_blast_db_path(self):
        d = QFileDialog.getExistingDirectory(self, "Select Database Directory", "", QFileDialog.ShowDirsOnly)
        if d:
            self.local_db_path.setText(d)

    # ── MMseqs2 database helpers ─────────────────────────────────

    def _get_mmseqs_selected_db_name(self):
        text = self.mmseqs_db_combo.currentText()
        parts = text.split()
        return parts[-1] if parts else text

    def _get_mmseqs_current_db_name(self):
        if self.custom_mmseqs_radio.isChecked():
            p = self.custom_mmseqs_path.text()
            return os.path.basename(p) if p else "Custom MMseqs2 DB"
        if self.custom_ncbi_radio.isChecked():
            return self.custom_blast_db_path if self.custom_blast_db_path else "Custom NCBI DB"
        return self.mmseqs_db_combo.currentText().split(" (")[0] if self.mmseqs_db_combo.count() else "Unknown"

    def scan_installed_databases(self):
        self.installed_databases.clear()
        if not os.path.exists(self.blast_db_dir):
            return
        try:
            for item in os.listdir(self.blast_db_dir):
                folder = os.path.join(self.blast_db_dir, item)
                if os.path.isdir(folder):
                    if (os.path.exists(os.path.join(folder, item + ".phr")) or
                            os.path.exists(os.path.join(folder, item + ".00.phr"))):
                        self.installed_databases.add(item)
            if hasattr(self, "mmseqs_db_combo"):
                self._populate_mmseqs_db_dropdown()
        except Exception:
            pass

    def _populate_mmseqs_db_dropdown(self):
        self.mmseqs_db_combo.clear()
        key_dbs = ["swissprot", "nr", "pdb", "refseq_protein"]
        for db in key_dbs:
            if db in NCBI_DATABASES:
                icon = self._mmseqs_status_icon(db)
                self.mmseqs_db_combo.addItem(f"{icon} {db}")
        self.mmseqs_db_combo.insertSeparator(len(key_dbs))
        for db in sorted(NCBI_DATABASES.keys()):
            if db not in key_dbs:
                icon = self._mmseqs_status_icon(db)
                self.mmseqs_db_combo.addItem(f"{icon} {db}")
        if self.mmseqs_db_combo.count() > 0:
            self._update_mmseqs_db_status_label()

    def _mmseqs_status_icon(self, db_name: str) -> str:
        if self.conversion_manager.is_converted(db_name):
            return "[ready]"
        if self.conversion_manager.is_converting(db_name):
            return "[converting]"
        st = self.conversion_manager.get_database_status(db_name)
        if st["status"] == "failed":
            return "[failed]"
        if db_name in self.installed_databases:
            return "[installed]"
        return "[not installed]"

    def _update_mmseqs_db_status_label(self):
        db = self._get_mmseqs_selected_db_name()
        if not db:
            return
        t = get_theme()
        status = self.conversion_manager.get_database_status(db)
        if status["status"] == "converted":
            self.mmseqs_db_status_label.setText(
                f"{db} is ready to use (converted: {status.get('converted_date', '')[:10]})")
            self.mmseqs_db_status_label.setStyleSheet(f"color:{t.get('success')};")
        elif status["status"] == "converting":
            self.mmseqs_db_status_label.setText(f"{db} is currently being converted...")
            self.mmseqs_db_status_label.setStyleSheet(f"color:{t.get('warning')};")
        elif status["status"] == "failed":
            self.mmseqs_db_status_label.setText(
                f"{db} conversion failed: {status.get('error', 'Unknown')}")
            self.mmseqs_db_status_label.setStyleSheet(f"color:{t.get('error')};")
        else:
            desc = NCBI_DATABASES.get(db, "")
            if db in self.installed_databases:
                self.mmseqs_db_status_label.setText(
                    f"{db} installed but not converted. Will auto-convert on search.")
                self.mmseqs_db_status_label.setStyleSheet(f"color:{t.get('text_muted')};")
            else:
                self.mmseqs_db_status_label.setText(f"{db} not installed. {desc}")
                self.mmseqs_db_status_label.setStyleSheet(f"color:{t.get('warning')};")

    def _on_mmseqs_db_selection_changed(self):
        self._update_mmseqs_db_status_label()

    def _on_mmseqs_db_source_changed(self):
        is_ncbi = self.ncbi_radio.isChecked()
        is_cn = self.custom_ncbi_radio.isChecked()
        is_cm = self.custom_mmseqs_radio.isChecked()
        for i in range(self.mmseqs_ncbi_layout.count()):
            item = self.mmseqs_ncbi_layout.itemAt(i)
            if item.widget():
                item.widget().setVisible(is_ncbi)
            elif item.layout():
                for j in range(item.layout().count()):
                    w = item.layout().itemAt(j).widget()
                    if w:
                        w.setVisible(is_ncbi)
        for i in range(self.custom_ncbi_layout.count()):
            w = self.custom_ncbi_layout.itemAt(i).widget()
            if w:
                w.setVisible(is_cn)
        for i in range(self.custom_mmseqs_layout.count()):
            w = self.custom_mmseqs_layout.itemAt(i).widget()
            if w:
                w.setVisible(is_cm)

    def _check_mmseqs_requirements(self):
        t = get_theme()
        if not is_wsl_available():
            self.mmseqs_info_label.setText("Command execution environment not available.")
            self.mmseqs_info_label.setStyleSheet(f"color:{t.get('warning')};")
            return
        ok, ver, path = check_mmseqs_installation()
        if not ok:
            hint = get_platform_tool_install_hint("mmseqs")
            self.mmseqs_info_label.setText(f"MMseqs2 not found. {hint}")
            self.mmseqs_info_label.setStyleSheet(f"color:{t.get('warning')};")
            return
        bok, bver, bpath = check_blastdbcmd_installation()
        if not bok:
            hint = get_platform_tool_install_hint("blastdbcmd")
            self.mmseqs_info_label.setText(f"blastdbcmd not found. {hint}")
            self.mmseqs_info_label.setStyleSheet(f"color:{t.get('warning')};")
            return
        self.mmseqs_info_label.setText(
            f"MMseqs2 ready ({ver or 'installed'}). First-time DB selection triggers auto-conversion.")
        self.mmseqs_info_label.setStyleSheet(f"color:{t.get('success')};")

    def _browse_ncbi_database_path(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select BLAST Database File", "",
            "BLAST Protein DB (*.phr);;All Files (*)")
        if f:
            base = f.rsplit(".", 1)[0] if "." in f else f
            self.custom_ncbi_path.setText(base)
            self.custom_blast_db_path = base

    def _browse_mmseqs_database_path(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select MMseqs2 Database File", "", "All Files (*)")
        if f:
            self.custom_mmseqs_path.setText(f)

    # ── Database conversion (MMseqs2) ────────────────────────────

    def _start_database_conversion(self, db_name, blast_db_path=None):
        if self.conversion_manager.is_converting(db_name):
            QMessageBox.information(self, "Conversion In Progress",
                f"'{db_name}' is already being converted.")
            return
        if blast_db_path is None:
            blast_db_path = os.path.join(self.blast_db_dir, db_name, db_name)
        blast_dir = os.path.dirname(blast_db_path)
        if not os.path.exists(blast_dir):
            QMessageBox.critical(self, "Not Found", f"Directory not found: {blast_dir}")
            return
        if not os.path.exists(blast_db_path + ".phr"):
            QMessageBox.critical(self, "Not Found", f"Database files not found at: {blast_db_path}")
            return
        mmseqs_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mmseqs_databases")
        os.makedirs(mmseqs_dir, exist_ok=True)
        mmseqs_path = os.path.join(mmseqs_dir, db_name)
        self.conversion_manager.mark_converting(db_name, blast_db_path, mmseqs_path)
        dialog = ConversionProgressDialog(db_name, self)
        worker = DatabaseConversionWorker(db_name, blast_db_path, mmseqs_dir)
        dialog.set_worker(worker)
        worker.finished.connect(lambda n, p: self._on_conv_done(n, p, dialog))
        worker.error.connect(lambda n, e: self._on_conv_err(n, e, dialog))
        self.conversion_dialogs[db_name] = dialog
        worker.start()
        dialog.show()
        self._populate_mmseqs_db_dropdown()
        self._update_mmseqs_db_status_label()

    def _on_conv_done(self, name, path, dialog):
        self.conversion_manager.mark_converted(name, path)
        self._populate_mmseqs_db_dropdown()
        self._update_mmseqs_db_status_label()
        self.conversion_dialogs.pop(name, None)

    def _on_conv_err(self, name, error, dialog):
        self.conversion_manager.mark_failed(name, error)
        self._populate_mmseqs_db_dropdown()
        self._update_mmseqs_db_status_label()
        self.conversion_dialogs.pop(name, None)

    # ── Export ───────────────────────────────────────────────────

    def _export_results(self, fmt):
        if not self.current_results_html:
            QMessageBox.warning(self, "No Results", "No results available to export.")
            return
        tool_prefix = "blast" if self._is_blast() else "mmseqs"
        query_name = self.current_sequence_metadata.get("id", "query")
        default_fn = self.exporter.get_default_filename(tool_prefix, query_name)
        ext = fmt.upper()
        fp, _ = QFileDialog.getSaveFileName(self, f"Save Results as {ext}",
            f"{default_fn}.{fmt}", f"{ext} Files (*.{fmt});;All Files (*)")
        if not fp:
            return
        try:
            if self._is_blast():
                ok = self.exporter.export_blast_results(
                    self.current_results_html, self.current_query_info, fp, fmt)
            else:
                ok = self.exporter.export_mmseqs_results(
                    self.current_results_html, self.current_query_info, fp, fmt)
            if ok:
                show_export_success(self, fp)
        except ExportError as e:
            show_export_error(self, e)

    # ── Run search ───────────────────────────────────────────────

    def _validate_sequence(self):
        sequence = self.input_text.toPlainText().strip().upper()
        if not sequence:
            self.status_label.setText("Please enter a protein sequence first.")
            return None
        sequence = "".join(c for c in sequence if c.isalpha())
        valid_aa = set("ACDEFGHIKLMNPQRSTVWY")
        if not all(c in valid_aa for c in sequence):
            self.status_label.setText("Invalid amino acid sequence.")
            return None
        return sequence

    def _run_search(self):
        if self._is_blast():
            self._run_blast()
        else:
            self._run_mmseqs()

    def _run_blast(self):
        sequence = self._validate_sequence()
        if not sequence:
            return

        self.process_button.setEnabled(False)
        self.status_label.setText("Running BLASTP search... This may take a minute.")
        self.results_panel.clear()

        db_text = self.blast_db_combo.currentText()
        database = db_text.split(" - ")[0] if " - " in db_text else db_text
        use_remote = self.remote_radio.isChecked()
        local_path = self.local_db_path.text().strip()

        if not use_remote and not local_path:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            default_dir = os.path.join(script_dir, "blast_databases")
            if not os.path.exists(default_dir):
                self.status_label.setText("Default database directory not found.")
                self.process_button.setEnabled(True)
                return
            local_path = ""

        self.search_start_time = time.time()
        self.blast_worker = BLASTWorker(sequence, database, use_remote, local_path,
                                        advanced_params=self._get_advanced_params())
        self.blast_worker.finished.connect(self._on_blast_finished)
        self.blast_worker.error.connect(self._on_search_error)
        self.blast_worker.start()

    def _run_mmseqs(self):
        sequence = self._validate_sequence()
        if not sequence:
            return

        if self.ncbi_radio.isChecked():
            db_name = self._get_mmseqs_selected_db_name()
            if db_name not in self.installed_databases:
                QMessageBox.warning(self, "Database Not Installed",
                    f"'{db_name}' is not installed in:\n{self.blast_db_dir}")
                return
            if self.conversion_manager.is_converting(db_name):
                QMessageBox.information(self, "Conversion In Progress",
                    f"'{db_name}' is still being converted.")
                return
            if not self.conversion_manager.is_converted(db_name):
                reply = QMessageBox.question(self, "Database Not Converted",
                    f"Convert '{db_name}' to MMseqs2 format?\nThis takes a few minutes.",
                    QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self._start_database_conversion(db_name)
                return
            status = self.conversion_manager.get_database_status(db_name)
            database_path = status.get("converted_path")
            if not database_path or not os.path.exists(database_path):
                self.status_label.setText("Converted database not found. Try converting again.")
                return
        elif self.custom_ncbi_radio.isChecked():
            bp = self.custom_ncbi_path.text().strip()
            if not bp:
                self.status_label.setText("Please select a BLAST database.")
                return
            if not os.path.exists(bp + ".phr"):
                self.status_label.setText("BLAST database files not found.")
                return
            db_name = os.path.basename(bp)
            key = f"custom_{db_name}"
            if not self.conversion_manager.is_converted(key):
                reply = QMessageBox.question(self, "Convert Custom Database",
                    f"Convert '{db_name}' to MMseqs2 format?", QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self._start_database_conversion(key, bp)
                return
            status = self.conversion_manager.get_database_status(key)
            database_path = status.get("converted_path")
            if not database_path or not os.path.exists(database_path):
                self.status_label.setText("Converted database not found.")
                return
        else:
            database_path = self.custom_mmseqs_path.text().strip()
            if not database_path:
                self.status_label.setText("Please select a MMseqs2 database.")
                return
            if not os.path.exists(database_path):
                self.status_label.setText(f"Database not found: {database_path}")
                return

        sensitivity = self.sensitivity_combo.currentText().split(" - ")[0]
        self.process_button.setEnabled(False)
        self.status_label.setText("Running MMseqs2 search...")
        self.results_panel.clear()

        self.search_start_time = time.time()
        self.mmseqs_worker = MMseqsWorker(sequence, database_path, sensitivity)
        self.mmseqs_worker.finished.connect(self._on_mmseqs_finished)
        self.mmseqs_worker.error.connect(self._on_search_error)
        self.mmseqs_worker.start()

    def _on_blast_finished(self, results_html, results_data):
        elapsed = time.time() - self.search_start_time if self.search_start_time else 0
        self.current_results_html = results_html
        self.current_results_data = results_data
        self.current_query_info = {
            "tool": "BLASTP",
            "query_name": self.current_sequence_metadata.get("id", "query"),
            "query_length": str(len(self.input_text.toPlainText().strip())),
            "database": self.blast_db_combo.currentText().split(" - ")[0],
            "search_time": f"{elapsed:.1f}s",
        }
        self.results_panel.set_results(results_data, self.current_query_info)
        self.status_label.setText("Search complete!")
        self.process_button.setEnabled(True)

    def _on_mmseqs_finished(self, results_html, results_data):
        elapsed = time.time() - self.search_start_time if self.search_start_time else 0
        self.current_results_html = results_html
        self.current_results_data = results_data
        self.current_query_info = {
            "tool": "MMseqs2",
            "query_name": self.current_sequence_metadata.get("id", "query"),
            "query_length": str(len(self.input_text.toPlainText().strip())),
            "database": self._get_mmseqs_current_db_name(),
            "sensitivity": self.sensitivity_combo.currentText(),
            "search_time": f"{elapsed:.1f}s",
        }
        self.results_panel.set_results(results_data, self.current_query_info)
        self.status_label.setText("Search complete!")
        self.process_button.setEnabled(True)

    def _on_search_error(self, error_msg):
        self.results_panel.clear()
        self.status_label.setText(f"Error: {error_msg[:120]}")
        self.process_button.setEnabled(True)

    # ── Cluster / Align workflows ────────────────────────────────

    def _get_database_path_for_fetch(self):
        """Resolve the database path for sequence fetching (cluster/align workflows)."""
        if self._is_blast():
            if not self.remote_radio.isChecked():
                if self.local_db_path.text().strip():
                    return os.path.join(self.local_db_path.text().strip(),
                        self.blast_db_combo.currentText().split(" - ")[0])
                config = get_config()
                db_name = self.blast_db_combo.currentText().split(" - ")[0]
                return os.path.join(config.get_blast_db_dir(), db_name, db_name)
        return self.current_database_path

    def _on_cluster_results(self):
        if not self.current_results_data or len(self.current_results_data) < 2:
            QMessageBox.warning(self, "Insufficient Results", "Need at least 2 results for clustering.")
            return
        selection_dialog = ClusterSelectionDialog(self.current_results_data, self)
        if selection_dialog.exec_() != QDialog.Accepted:
            return
        selected = selection_dialog.get_selected_hits()
        if len(selected) < 2:
            return
        self._fetch_and_cluster(selected)

    def _fetch_and_cluster(self, selected_hits):
        from PyQt5.QtWidgets import QProgressDialog
        database_path = self._get_database_path_for_fetch()

        progress = QProgressDialog("Fetching sequences...", "Cancel", 0, len(selected_hits), self)
        progress.setWindowTitle("Retrieving Sequences")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        self.sequence_fetcher = SequenceFetcherWorker(selected_hits, database_path)
        self.sequence_fetcher.progress.connect(lambda c, t, s: progress.setValue(c))
        self.sequence_fetcher.finished.connect(
            lambda ok, fail: self._on_sequences_fetched(ok, fail, progress))
        progress.canceled.connect(self.sequence_fetcher.stop)
        self.sequence_fetcher.start()

    def _on_sequences_fetched(self, successful, failed, progress_dialog):
        progress_dialog.close()
        config_dialog = ClusteringConfigDialog(successful, failed, self)
        if config_dialog.exec_() != QDialog.Accepted:
            return
        params = config_dialog.get_parameters()
        final = config_dialog.get_successful_hits()
        if len(final) < 2:
            QMessageBox.warning(self, "Insufficient Sequences", "Need at least 2 sequences.")
            return
        try:
            prefix = "blast_cluster_" if self._is_blast() else "mmseqs_cluster_"
            fasta_path = get_temp_fasta_manager().create_temp_fasta(final, prefix=prefix)
            self.navigate_to_clustering.emit(fasta_path, params)
        except Exception as e:
            QMessageBox.critical(self, "Error Creating FASTA", str(e))

    def _on_align_results(self):
        if not self.current_results_data or len(self.current_results_data) < 2:
            QMessageBox.warning(self, "Insufficient Results", "Need at least 2 results for alignment.")
            return
        dialog = ClusterSelectionDialog(self.current_results_data, self)
        dialog.setWindowTitle("Select Sequences for Alignment")
        if dialog.exec_() != QDialog.Accepted:
            return
        selected = dialog.get_selected_hits()
        if len(selected) < 2:
            QMessageBox.warning(self, "Insufficient Selection", "Select at least 2 sequences.")
            return
        self._fetch_and_align(selected)

    def _fetch_and_align(self, selected_hits):
        from PyQt5.QtWidgets import QProgressDialog
        database_path = self._get_database_path_for_fetch()

        progress = QProgressDialog("Fetching sequences for alignment...", "Cancel", 0, len(selected_hits), self)
        progress.setWindowTitle("Retrieving Sequences")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        self.align_sequence_fetcher = SequenceFetcherWorker(selected_hits, database_path)
        self.align_sequence_fetcher.progress.connect(lambda c, t, s: progress.setValue(c))
        self.align_sequence_fetcher.finished.connect(
            lambda ok, fail: self._on_align_fetched(ok, fail, progress))
        progress.canceled.connect(self.align_sequence_fetcher.stop)
        self.align_sequence_fetcher.start()

    def _on_align_fetched(self, successful, failed, progress_dialog):
        progress_dialog.close()
        if len(successful) < 2:
            msg = ""
            if failed:
                msg = f"\n\nFailed to fetch {len(failed)} sequences."
            QMessageBox.warning(self, "Insufficient Sequences",
                f"Need at least 2 sequences for alignment.{msg}")
            return
        if failed:
            reply = QMessageBox.question(self, "Some Sequences Failed",
                f"Successfully fetched {len(successful)} sequences.\n"
                f"Failed to fetch {len(failed)} sequences.\n\nProceed?",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        try:
            prefix = "blast_align_" if self._is_blast() else "mmseqs_align_"
            fasta_path = get_temp_fasta_manager().create_temp_fasta(successful, prefix=prefix)
            self.navigate_to_alignment.emit(fasta_path)
        except Exception as e:
            QMessageBox.critical(self, "Error Creating FASTA", str(e))
