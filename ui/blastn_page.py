"""BLASTN (Nucleotide BLAST) page for nucleotide sequence searches"""
import os
import time
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel, 
                             QComboBox, QHBoxLayout, QCheckBox, QLineEdit, QFileDialog, 
                             QGroupBox, QRadioButton, QButtonGroup, QMessageBox, QFrame, QDialog,
                             QSpinBox, QDoubleSpinBox)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from core.db_definitions import NUCLEOTIDE_DATABASES
from core.blastn_worker import BLASTNWorker
from core.config_manager import get_config
from utils.fasta_parser import FastaParser, FastaParseError
from utils.export_manager import ResultsExporter, ExportError, show_export_error, show_export_success


def validate_nucleotide_sequence(sequence):
    """Validate that sequence contains only valid nucleotide characters"""
    valid_chars = set('ATGCUNRYSWKMBDHV')  # IUPAC nucleotide codes
    sequence_upper = sequence.upper()
    invalid_chars = set(sequence_upper) - valid_chars
    return len(invalid_chars) == 0, invalid_chars


class BLASTNPage(QWidget):
    """BLASTN (Nucleotide BLAST) analysis page widget"""
    back_requested = pyqtSignal()
    navigate_to_alignment = pyqtSignal(str)  # fasta_path for alignment
    
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
        self.init_ui()
    
    def init_ui(self):
        """Initialize the BLASTN page UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Page header
        header_layout = QHBoxLayout()
        
        back_button = QPushButton("← Back to Home")
        back_button.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        back_button.clicked.connect(self.back_requested.emit)
        
        page_title = QLabel("🧬 BLASTN Nucleotide Search")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        page_title.setFont(title_font)
        page_title.setStyleSheet("color: #1e8449;")
        
        header_layout.addWidget(back_button)
        header_layout.addStretch()
        header_layout.addWidget(page_title)
        header_layout.addStretch()
        
        # Input Method Selection Group
        input_method_group = QGroupBox("Sequence Input Method")
        input_method_layout = QVBoxLayout()
        
        # Radio buttons for input method
        method_buttons_layout = QHBoxLayout()
        self.input_method_group = QButtonGroup()
        
        self.paste_radio = QRadioButton("Paste Sequence")
        self.upload_radio = QRadioButton("Upload FASTA File")
        
        self.paste_radio.setChecked(True)
        
        self.input_method_group.addButton(self.paste_radio, 1)
        self.input_method_group.addButton(self.upload_radio, 2)
        
        radio_style = """
            QRadioButton {
                font-size: 12px;
                font-weight: bold;
                padding: 5px;
            }
            QRadioButton::indicator {
                width: 15px;
                height: 15px;
            }
        """
        self.paste_radio.setStyleSheet(radio_style)
        self.upload_radio.setStyleSheet(radio_style)
        
        self.paste_radio.toggled.connect(self._on_input_method_changed)
        self.upload_radio.toggled.connect(self._on_input_method_changed)
        
        method_buttons_layout.addWidget(self.paste_radio)
        method_buttons_layout.addWidget(self.upload_radio)
        method_buttons_layout.addStretch()
        
        input_method_layout.addLayout(method_buttons_layout)
        
        # Container for different input widgets
        self.input_container = QFrame()
        self.input_container_layout = QVBoxLayout()
        self.input_container_layout.setContentsMargins(0, 10, 0, 0)
        
        # --- Paste Input Section ---
        self.paste_widget = QWidget()
        paste_layout = QVBoxLayout()
        paste_layout.setContentsMargins(0, 0, 0, 0)
        
        self.input_label = QLabel("Enter nucleotide sequence:")
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Paste your nucleotide sequence here (A, T, G, C, N)...")
        self.input_text.setMaximumHeight(100)
        self.input_text.textChanged.connect(self._update_sequence_counter)
        
        self.sequence_counter = QLabel("0 nucleotides")
        self.sequence_counter.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        
        paste_layout.addWidget(self.input_label)
        paste_layout.addWidget(self.input_text)
        paste_layout.addWidget(self.sequence_counter)
        self.paste_widget.setLayout(paste_layout)
        
        # --- Upload FASTA Section ---
        self.upload_widget = QWidget()
        upload_layout = QVBoxLayout()
        upload_layout.setContentsMargins(0, 0, 0, 0)
        
        upload_button_layout = QHBoxLayout()
        self.upload_fasta_button = QPushButton("📁 Choose FASTA File")
        self.upload_fasta_button.clicked.connect(self._upload_fasta_file)
        self.upload_fasta_button.setStyleSheet("""
            QPushButton {
                background-color: #1e8449;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #196f3d;
            }
        """)
        
        self.fasta_file_label = QLabel("No file selected")
        self.fasta_file_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        
        upload_button_layout.addWidget(self.upload_fasta_button)
        upload_button_layout.addWidget(self.fasta_file_label)
        upload_button_layout.addStretch()
        
        # Sequence selector for multi-FASTA
        self.fasta_sequence_selector = QComboBox()
        self.fasta_sequence_selector.setVisible(False)
        self.fasta_sequence_selector.currentIndexChanged.connect(self._on_fasta_sequence_selected)
        
        upload_layout.addLayout(upload_button_layout)
        upload_layout.addWidget(self.fasta_sequence_selector)
        upload_layout.addWidget(QLabel("FASTA format: Header line starts with '>', followed by sequence lines"))
        self.upload_widget.setLayout(upload_layout)
        self.upload_widget.setVisible(False)
        
        # Add all input widgets to container
        self.input_container_layout.addWidget(self.paste_widget)
        self.input_container_layout.addWidget(self.upload_widget)
        self.input_container.setLayout(self.input_container_layout)
        
        input_method_layout.addWidget(self.input_container)
        input_method_group.setLayout(input_method_layout)
        
        # Database selection group
        db_group = QGroupBox("Database Options")
        db_group_layout = QVBoxLayout()
        
        # Remote vs Local database selection
        source_layout = QHBoxLayout()
        self.remote_radio = QCheckBox("Use Remote NCBI Database")
        self.remote_radio.setChecked(True)
        self.remote_radio.toggled.connect(self.on_database_source_changed)
        source_layout.addWidget(self.remote_radio)
        
        # Database selection
        db_layout = QVBoxLayout()
        db_header_layout = QHBoxLayout()
        db_label = QLabel("Database:")
        db_info_label = QLabel("Nucleotide databases for BLASTN search")
        db_info_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        
        db_header_layout.addWidget(db_label)
        db_header_layout.addStretch()
        db_header_layout.addWidget(db_info_label)
        
        # Create database selection combobox
        self.db_combo = QComboBox()
        
        # Add key nucleotide databases first
        key_databases = ['nt', 'refseq_rna', 'refseq_genomic', 'est', '16S_ribosomal_RNA']
        for db in key_databases:
            if db in NUCLEOTIDE_DATABASES:
                self.db_combo.addItem(f"{db} - {NUCLEOTIDE_DATABASES[db]}")
        
        # Add remaining databases
        for db, desc in NUCLEOTIDE_DATABASES.items():
            if db not in key_databases:
                self.db_combo.addItem(f"{db} - {desc}")
        
        self.db_combo.setCurrentIndex(0)
        self.db_combo.setMinimumHeight(30)
        self.db_combo.setToolTip("Select from available NCBI nucleotide databases")
        self.db_combo.currentTextChanged.connect(self.on_database_changed)
        
        # Database description label
        self.db_description = QLabel()
        self.db_description.setWordWrap(True)
        self.db_description.setStyleSheet("color: #5d6d7e; font-style: italic; padding: 5px; background-color: #e8f6f3; border-radius: 3px; margin-top: 5px;")
        self.update_database_description()
        
        # Popular databases quick access
        popular_layout = QHBoxLayout()
        popular_label = QLabel("Popular:")
        popular_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        
        popular_buttons = []
        for db_name in ['nt', 'refseq_rna', 'refseq_genomic', '16S_ribosomal_RNA']:
            btn = QPushButton(db_name)
            btn.setMaximumHeight(25)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #e8f6f3;
                    border: 1px solid #1e8449;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 10px;
                    color: #1e8449;
                }
                QPushButton:hover {
                    background-color: #1e8449;
                    color: white;
                }
            """)
            btn.clicked.connect(lambda checked, db=db_name: self.db_combo.setCurrentText(db))
            popular_buttons.append(btn)
        
        popular_layout.addWidget(popular_label)
        for btn in popular_buttons:
            popular_layout.addWidget(btn)
        popular_layout.addStretch()
        
        db_layout.addLayout(db_header_layout)
        db_layout.addWidget(self.db_combo)
        db_layout.addWidget(self.db_description)
        db_layout.addLayout(popular_layout)
        
        # Local database path
        local_db_layout = QHBoxLayout()
        self.local_db_label = QLabel("Local DB Path:")
        self.local_db_path = QLineEdit()
        self.local_db_path.setPlaceholderText("Path to local database directory (optional)")
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_database_path)
        
        local_db_layout.addWidget(self.local_db_label)
        local_db_layout.addWidget(self.local_db_path)
        local_db_layout.addWidget(self.browse_button)
        
        db_group_layout.addLayout(source_layout)
        db_group_layout.addLayout(db_layout)
        db_group_layout.addLayout(local_db_layout)
        db_group.setLayout(db_group_layout)
        
        self.on_database_source_changed()
        
        # Advanced Settings Group
        advanced_group = QGroupBox("Advanced Settings")
        advanced_group_layout = QVBoxLayout()
        
        self.show_advanced_checkbox = QCheckBox("Show Advanced Options")
        self.show_advanced_checkbox.setStyleSheet("font-weight: bold;")
        self.show_advanced_checkbox.stateChanged.connect(self._toggle_advanced_options)
        
        self.advanced_options_widget = QWidget()
        advanced_options_layout = QVBoxLayout()
        advanced_options_layout.setContentsMargins(0, 10, 0, 0)
        
        # Row 1: Task and E-value
        row1_layout = QHBoxLayout()
        
        # BLAST task (algorithm)
        task_label = QLabel("Algorithm:")
        task_label.setMinimumWidth(100)
        self.task_combo = QComboBox()
        self.task_combo.addItems([
            "blastn (standard)",
            "blastn-short (short sequences)",
            "megablast (highly similar)",
            "dc-megablast (discontinuous)"
        ])
        self.task_combo.setToolTip("BLAST algorithm variant to use")
        self.task_combo.currentIndexChanged.connect(self._update_word_size)
        
        # E-value threshold
        evalue_label = QLabel("E-value:")
        evalue_label.setMinimumWidth(60)
        self.evalue_input = QDoubleSpinBox()
        self.evalue_input.setRange(1e-200, 1000)
        self.evalue_input.setDecimals(0)
        self.evalue_input.setValue(10)
        self.evalue_input.setToolTip("Expect value threshold for reporting matches")
        
        row1_layout.addWidget(task_label)
        row1_layout.addWidget(self.task_combo)
        row1_layout.addSpacing(20)
        row1_layout.addWidget(evalue_label)
        row1_layout.addWidget(self.evalue_input)
        row1_layout.addStretch()
        
        # Row 2: Max hits and Word size
        row2_layout = QHBoxLayout()
        
        max_targets_label = QLabel("Max Hits:")
        max_targets_label.setMinimumWidth(100)
        self.max_targets_input = QSpinBox()
        self.max_targets_input.setRange(1, 5000)
        self.max_targets_input.setValue(100)
        self.max_targets_input.setToolTip("Maximum number of aligned sequences to keep")
        
        word_size_label = QLabel("Word Size:")
        word_size_label.setMinimumWidth(80)
        self.word_size_input = QSpinBox()
        self.word_size_input.setRange(4, 64)
        self.word_size_input.setValue(11)
        self.word_size_input.setToolTip("Length of initial exact match (varies by algorithm)")
        
        row2_layout.addWidget(max_targets_label)
        row2_layout.addWidget(self.max_targets_input)
        row2_layout.addSpacing(20)
        row2_layout.addWidget(word_size_label)
        row2_layout.addWidget(self.word_size_input)
        row2_layout.addStretch()
        
        # Row 3: Match/Mismatch scores
        row3_layout = QHBoxLayout()
        
        reward_label = QLabel("Match Reward:")
        reward_label.setMinimumWidth(100)
        self.reward_input = QSpinBox()
        self.reward_input.setRange(1, 10)
        self.reward_input.setValue(2)
        self.reward_input.setToolTip("Reward for a nucleotide match")
        
        penalty_label = QLabel("Mismatch Penalty:")
        penalty_label.setMinimumWidth(110)
        self.penalty_input = QSpinBox()
        self.penalty_input.setRange(-10, -1)
        self.penalty_input.setValue(-3)
        self.penalty_input.setToolTip("Penalty for a nucleotide mismatch (negative value)")
        
        row3_layout.addWidget(reward_label)
        row3_layout.addWidget(self.reward_input)
        row3_layout.addSpacing(20)
        row3_layout.addWidget(penalty_label)
        row3_layout.addWidget(self.penalty_input)
        row3_layout.addStretch()
        
        # Row 4: Gap costs
        row4_layout = QHBoxLayout()
        
        gap_open_label = QLabel("Gap Open Cost:")
        gap_open_label.setMinimumWidth(100)
        self.gap_open_input = QSpinBox()
        self.gap_open_input.setRange(1, 50)
        self.gap_open_input.setValue(5)
        self.gap_open_input.setToolTip("Cost to open a gap")
        
        gap_extend_label = QLabel("Gap Extend:")
        gap_extend_label.setMinimumWidth(80)
        self.gap_extend_input = QSpinBox()
        self.gap_extend_input.setRange(1, 10)
        self.gap_extend_input.setValue(2)
        self.gap_extend_input.setToolTip("Cost to extend a gap")
        
        row4_layout.addWidget(gap_open_label)
        row4_layout.addWidget(self.gap_open_input)
        row4_layout.addSpacing(20)
        row4_layout.addWidget(gap_extend_label)
        row4_layout.addWidget(self.gap_extend_input)
        row4_layout.addStretch()
        
        # Row 5: Filters
        row5_layout = QHBoxLayout()
        
        self.dust_checkbox = QCheckBox("Filter Low Complexity (DUST)")
        self.dust_checkbox.setChecked(True)
        self.dust_checkbox.setToolTip("Mask low-complexity regions in query sequence")
        
        self.soft_masking_checkbox = QCheckBox("Soft Masking")
        self.soft_masking_checkbox.setChecked(False)
        self.soft_masking_checkbox.setToolTip("Use soft masking instead of hard masking")
        
        row5_layout.addWidget(self.dust_checkbox)
        row5_layout.addSpacing(20)
        row5_layout.addWidget(self.soft_masking_checkbox)
        row5_layout.addStretch()
        
        advanced_options_layout.addLayout(row1_layout)
        advanced_options_layout.addLayout(row2_layout)
        advanced_options_layout.addLayout(row3_layout)
        advanced_options_layout.addLayout(row4_layout)
        advanced_options_layout.addLayout(row5_layout)
        
        self.advanced_options_widget.setLayout(advanced_options_layout)
        self.advanced_options_widget.hide()
        
        advanced_group_layout.addWidget(self.show_advanced_checkbox)
        advanced_group_layout.addWidget(self.advanced_options_widget)
        advanced_group.setLayout(advanced_group_layout)
        
        # Run button
        self.process_button = QPushButton("Run BLASTN Search")
        self.process_button.setStyleSheet("""
            QPushButton {
                background-color: #1e8449;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #196f3d;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.process_button.clicked.connect(self.run_blast)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #7f8c8d; font-weight: bold;")
        
        # Summary statistics panel
        self.summary_panel = QWidget()
        summary_layout = QHBoxLayout()
        summary_layout.setContentsMargins(0, 10, 0, 10)
        
        self.summary_panel.setStyleSheet("""
            QWidget {
                background-color: #e8f6f3;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                background-color: transparent;
            }
        """)
        
        self.stat_hits = QLabel("—")
        self.stat_best_eval = QLabel("—")
        self.stat_avg_identity = QLabel("—")
        self.stat_search_time = QLabel("—")
        
        for stat_label in [self.stat_hits, self.stat_best_eval, self.stat_avg_identity, self.stat_search_time]:
            stat_label.setAlignment(Qt.AlignCenter)
            stat_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #1e8449;")
        
        hits_box = QVBoxLayout()
        hits_label = QLabel("Total Hits")
        hits_label.setAlignment(Qt.AlignCenter)
        hits_label.setStyleSheet("font-size: 11px; color: #7f8c8d;")
        hits_box.addWidget(self.stat_hits)
        hits_box.addWidget(hits_label)
        
        eval_box = QVBoxLayout()
        eval_label = QLabel("Best E-value")
        eval_label.setAlignment(Qt.AlignCenter)
        eval_label.setStyleSheet("font-size: 11px; color: #7f8c8d;")
        eval_box.addWidget(self.stat_best_eval)
        eval_box.addWidget(eval_label)
        
        identity_box = QVBoxLayout()
        identity_label = QLabel("Avg Identity")
        identity_label.setAlignment(Qt.AlignCenter)
        identity_label.setStyleSheet("font-size: 11px; color: #7f8c8d;")
        identity_box.addWidget(self.stat_avg_identity)
        identity_box.addWidget(identity_label)
        
        time_box = QVBoxLayout()
        time_label = QLabel("Search Time")
        time_label.setAlignment(Qt.AlignCenter)
        time_label.setStyleSheet("font-size: 11px; color: #7f8c8d;")
        time_box.addWidget(self.stat_search_time)
        time_box.addWidget(time_label)
        
        summary_layout.addLayout(hits_box)
        summary_layout.addSpacing(20)
        summary_layout.addLayout(eval_box)
        summary_layout.addSpacing(20)
        summary_layout.addLayout(identity_box)
        summary_layout.addSpacing(20)
        summary_layout.addLayout(time_box)
        
        self.summary_panel.setLayout(summary_layout)
        self.summary_panel.hide()
        
        # Results section with export buttons
        results_header_layout = QHBoxLayout()
        self.output_label = QLabel("Results:")
        results_header_layout.addWidget(self.output_label)
        results_header_layout.addStretch()
        
        # Export buttons
        self.export_tsv_button = QPushButton("📥 Export as TSV")
        self.export_csv_button = QPushButton("📥 Export as CSV")
        
        self.export_tsv_button.setEnabled(False)
        self.export_csv_button.setEnabled(False)
        
        export_button_style = """
            QPushButton {
                background-color: #1e8449;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #196f3d;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """
        self.export_tsv_button.setStyleSheet(export_button_style)
        self.export_csv_button.setStyleSheet(export_button_style)
        
        self.export_tsv_button.clicked.connect(lambda: self._export_results('tsv'))
        self.export_csv_button.clicked.connect(lambda: self._export_results('csv'))
        
        results_header_layout.addWidget(self.export_tsv_button)
        results_header_layout.addWidget(self.export_csv_button)
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setAcceptRichText(True)
        
        # Add widgets to layout
        layout.addLayout(header_layout)
        layout.addWidget(input_method_group)
        layout.addWidget(db_group)
        layout.addWidget(advanced_group)
        layout.addWidget(self.process_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.summary_panel)
        layout.addLayout(results_header_layout)
        layout.addWidget(self.output_text)
        
        self.setLayout(layout)
    
    def _on_input_method_changed(self):
        """Handle input method radio button changes"""
        if self.paste_radio.isChecked():
            self.paste_widget.setVisible(True)
            self.upload_widget.setVisible(False)
        elif self.upload_radio.isChecked():
            self.paste_widget.setVisible(False)
            self.upload_widget.setVisible(True)
    
    def _toggle_advanced_options(self, state):
        """Show/hide advanced options"""
        self.advanced_options_widget.setVisible(state == Qt.Checked)
    
    def _update_word_size(self):
        """Update word size based on selected task/algorithm"""
        # Default word sizes for each algorithm
        word_sizes = {
            0: 11,   # blastn
            1: 7,    # blastn-short
            2: 28,   # megablast
            3: 11,   # dc-megablast
        }
        task_idx = self.task_combo.currentIndex()
        if task_idx in word_sizes:
            self.word_size_input.setValue(word_sizes[task_idx])
    
    def _get_advanced_params(self):
        """Get advanced parameters as a dictionary"""
        task_map = {
            0: "blastn",
            1: "blastn-short",
            2: "megablast",
            3: "dc-megablast"
        }
        
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
        """Update the nucleotide counter for pasted sequence"""
        text = self.input_text.toPlainText().strip().upper()
        clean_text = ''.join(c for c in text if c.isalpha())
        
        count = len(clean_text)
        self.sequence_counter.setText(f"{count} nucleotides")
        
        if count == 0:
            self.sequence_counter.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        elif count < 10:
            self.sequence_counter.setStyleSheet("color: #e74c3c; font-size: 10px; font-weight: bold;")
        elif count > 50000:
            self.sequence_counter.setStyleSheet("color: #e67e22; font-size: 10px; font-weight: bold;")
        else:
            self.sequence_counter.setStyleSheet("color: #1e8449; font-size: 10px; font-weight: bold;")
    
    def _upload_fasta_file(self):
        """Open file dialog and load FASTA file"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open FASTA File",
            "",
            "FASTA Files (*.fasta *.fa *.fna *.ffn *.faa *.frn);;All Files (*)"
        )
        
        if not filepath:
            return
        
        try:
            sequences = self.fasta_parser.parse_file(filepath)
            
            if self.fasta_parser.has_warnings():
                warnings_text = "\n".join(self.fasta_parser.get_warnings())
                QMessageBox.warning(
                    self,
                    "FASTA Parsing Warnings",
                    f"File loaded with warnings:\n\n{warnings_text}"
                )
            
            self.loaded_sequences = sequences
            filename = os.path.basename(filepath)
            
            if len(sequences) == 1:
                self.fasta_file_label.setText(f"✓ {filename} ({len(sequences[0].sequence)} nt)")
                self.fasta_sequence_selector.setVisible(False)
                self.input_text.setPlainText(sequences[0].sequence)
                self.current_sequence_metadata = {
                    'source': 'fasta_file',
                    'filename': filename,
                    'header': sequences[0].header,
                    'id': sequences[0].id
                }
            else:
                self.fasta_file_label.setText(f"✓ {filename} ({len(sequences)} sequences)")
                self.fasta_sequence_selector.clear()
                
                for seq in sequences:
                    self.fasta_sequence_selector.addItem(
                        f"{seq.id} ({len(seq.sequence)} nt)",
                        seq
                    )
                
                self.fasta_sequence_selector.setVisible(True)
                self._on_fasta_sequence_selected(0)
            
        except FastaParseError as e:
            QMessageBox.critical(
                self,
                "FASTA Parsing Error",
                f"Failed to parse FASTA file:\n\n{str(e)}"
            )
            self.fasta_file_label.setText("No file selected")
    
    def _on_fasta_sequence_selected(self, index):
        """Handle selection of a sequence from multi-FASTA file"""
        if index < 0 or not self.loaded_sequences:
            return
        
        selected_seq = self.fasta_sequence_selector.itemData(index)
        if selected_seq:
            self.input_text.setPlainText(selected_seq.sequence)
            self.current_sequence_metadata = {
                'source': 'fasta_file',
                'header': selected_seq.header,
                'id': selected_seq.id
            }
    
    def _export_results(self, format_type):
        """Export results to TSV or CSV"""
        if not self.current_results_html:
            QMessageBox.warning(
                self,
                "No Results",
                "No results available to export. Please run a search first."
            )
            return
        
        query_name = self.current_sequence_metadata.get('id', 'query')
        default_filename = self.exporter.get_default_filename('blastn', query_name)
        
        ext = format_type.upper()
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            f"Save Results as {ext}",
            f"{default_filename}.{format_type}",
            f"{ext} Files (*.{format_type});;All Files (*)"
        )
        
        if not filepath:
            return
        
        try:
            success = self.exporter.export_blast_results(
                self.current_results_html,
                self.current_query_info,
                filepath,
                format_type
            )
            
            if success:
                show_export_success(self, filepath)
        
        except ExportError as e:
            show_export_error(self, e)
    
    def on_database_changed(self):
        """Update database description when selection changes"""
        self.update_database_description()
    
    def update_database_description(self):
        """Update the database description label"""
        current_text = self.db_combo.currentText()
        current_db = current_text.split(' - ')[0] if ' - ' in current_text else current_text
        description = NUCLEOTIDE_DATABASES.get(current_db, "Database information not available")
        self.db_description.setText(f"📋 {description}")
    
    def on_database_source_changed(self):
        """Enable/disable local database options based on remote checkbox"""
        is_remote = self.remote_radio.isChecked()
        self.local_db_label.setEnabled(not is_remote)
        self.local_db_path.setEnabled(not is_remote)
        self.browse_button.setEnabled(not is_remote)
    
    def browse_database_path(self):
        """Open file dialog to select database directory"""
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Select Database Directory",
            "",
            QFileDialog.ShowDirsOnly
        )
        if directory:
            self.local_db_path.setText(directory)
    
    def run_blast(self):
        """Run BLASTN search in background thread"""
        sequence = self.input_text.toPlainText().strip().upper()
        
        if not sequence:
            self.output_text.setText("Please enter a nucleotide sequence first.")
            return
        
        # Remove whitespace
        sequence = ''.join(c for c in sequence if c.isalpha())
        
        # Validate nucleotide sequence
        is_valid, invalid_chars = validate_nucleotide_sequence(sequence)
        if not is_valid:
            self.output_text.setText(
                f"Error: Invalid nucleotide sequence.\n\n"
                f"Found invalid characters: {', '.join(sorted(invalid_chars))}\n\n"
                f"Valid nucleotide codes: A, T, G, C, N, and IUPAC ambiguity codes (R, Y, S, W, K, M, B, D, H, V)"
            )
            return
        
        # Disable button during search
        self.process_button.setEnabled(False)
        self.status_label.setText("Running BLASTN search... This may take a minute.")
        self.output_text.setText("Searching NCBI database...\n\nPlease wait, this can take 30-60 seconds for remote searches.")
        
        # Get selected database and options
        database_text = self.db_combo.currentText()
        database = database_text.split(' - ')[0] if ' - ' in database_text else database_text
        use_remote = self.remote_radio.isChecked()
        local_db_path = self.local_db_path.text().strip()
        
        # Get advanced parameters
        advanced_params = self._get_advanced_params()
        
        # Start BLASTN in background thread
        self.search_start_time = time.time()
        self.blast_worker = BLASTNWorker(
            sequence, database, use_remote, local_db_path,
            advanced_params=advanced_params
        )
        self.blast_worker.finished.connect(self.on_blast_finished)
        self.blast_worker.error.connect(self.on_blast_error)
        self.blast_worker.start()
    
    def extract_stats_from_html(self, html_results):
        """Extract statistics from HTML results"""
        import re
        
        hits_match = re.search(r'Found (\d+) significant alignment', html_results)
        total_hits = int(hits_match.group(1)) if hits_match else 0
        
        evalue_matches = re.findall(r'E-value:</span> <b[^>]*>([\d\.e\-+]+)</b>', html_results)
        best_evalue = min([float(e) for e in evalue_matches]) if evalue_matches else None
        
        identity_matches = re.findall(r'Identity:</span> <b[^>]*>\d+/\d+ \(([\d\.]+)%\)</b>', html_results)
        avg_identity = sum([float(i) for i in identity_matches]) / len(identity_matches) if identity_matches else 0
        
        return total_hits, best_evalue, avg_identity
    
    def update_summary_panel(self, total_hits, best_evalue, avg_identity, search_time):
        """Update the summary statistics panel"""
        self.stat_hits.setText(str(total_hits))
        
        if best_evalue is not None:
            if best_evalue < 1e-100:
                self.stat_best_eval.setText(f"{best_evalue:.1e}")
                self.stat_best_eval.setStyleSheet("font-size: 18px; font-weight: bold; color: #1e8449;")
            elif best_evalue < 1e-10:
                self.stat_best_eval.setText(f"{best_evalue:.1e}")
                self.stat_best_eval.setStyleSheet("font-size: 18px; font-weight: bold; color: #f39c12;")
            else:
                self.stat_best_eval.setText(f"{best_evalue:.1e}")
                self.stat_best_eval.setStyleSheet("font-size: 18px; font-weight: bold; color: #e67e22;")
        else:
            self.stat_best_eval.setText("N/A")
            self.stat_best_eval.setStyleSheet("font-size: 18px; font-weight: bold; color: #95a5a6;")
        
        if avg_identity > 0:
            self.stat_avg_identity.setText(f"{avg_identity:.1f}%")
            if avg_identity >= 90:
                self.stat_avg_identity.setStyleSheet("font-size: 18px; font-weight: bold; color: #1e8449;")
            elif avg_identity >= 70:
                self.stat_avg_identity.setStyleSheet("font-size: 18px; font-weight: bold; color: #f39c12;")
            else:
                self.stat_avg_identity.setStyleSheet("font-size: 18px; font-weight: bold; color: #e67e22;")
        else:
            self.stat_avg_identity.setText("N/A")
            self.stat_avg_identity.setStyleSheet("font-size: 18px; font-weight: bold; color: #95a5a6;")
        
        self.stat_search_time.setText(f"{search_time:.1f}s")
        
        self.summary_panel.show()
    
    def on_blast_finished(self, results_html, results_data):
        """Handle BLASTN results"""
        search_time = time.time() - self.search_start_time if self.search_start_time else 0
        
        self.current_results_html = results_html
        self.current_results_data = results_data
        self.current_query_info = {
            'query_name': self.current_sequence_metadata.get('id', 'query'),
            'query_length': str(len(self.input_text.toPlainText().strip())),
            'database': self.db_combo.currentText().split(' - ')[0],
            'search_time': f"{search_time:.1f}s"
        }
        
        total_hits, best_evalue, avg_identity = self.extract_stats_from_html(results_html)
        self.update_summary_panel(total_hits, best_evalue, avg_identity, search_time)
        
        self.output_text.setHtml(results_html)
        self.status_label.setText("Search complete!")
        self.process_button.setEnabled(True)
        
        self.export_tsv_button.setEnabled(True)
        self.export_csv_button.setEnabled(True)
    
    def on_blast_error(self, error_msg):
        """Handle BLASTN errors"""
        self.summary_panel.hide()
        self.output_text.setPlainText(f"Error running BLASTN:\n\n{error_msg}")
        self.status_label.setText("Error occurred")
        self.process_button.setEnabled(True)

