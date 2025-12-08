import os
import time
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel, 
                             QComboBox, QHBoxLayout, QCheckBox, QLineEdit, QFileDialog, 
                             QGroupBox, QRadioButton, QButtonGroup, QMessageBox, QFrame, QDialog)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from core.db_definitions import NCBI_DATABASES
from core.blast_worker import BLASTWorker
from core.config_manager import get_config
from ui.dialogs.protein_search_dialog import ProteinSearchDialog
from ui.dialogs.cluster_selection_dialog import ClusterSelectionDialog
from ui.dialogs.clustering_config_dialog import ClusteringConfigDialog
from core.sequence_fetcher_worker import SequenceFetcherWorker
from core.temp_fasta_manager import get_temp_fasta_manager
from utils.fasta_parser import FastaParser, FastaParseError, validate_amino_acid_sequence
from utils.export_manager import ResultsExporter, ExportError, show_export_error, show_export_success

class BLASTPage(QWidget):
    """BLAST analysis page widget"""
    back_requested = pyqtSignal()  # Signal to go back to home page
    navigate_to_clustering = pyqtSignal(str, dict)  # fasta_path, clustering_params
    navigate_to_alignment = pyqtSignal(str)  # fasta_path for alignment
    
    def __init__(self):
        super().__init__()
        self.blast_worker = None
        self.search_start_time = None
        self.current_results_html = ""
        self.current_results_data = []  # Structured SearchHit objects
        self.current_query_info = {}
        self.current_database_path = ""  # For sequence fetching
        self.fasta_parser = FastaParser()
        self.exporter = ResultsExporter()
        self.loaded_sequences = []  # For multi-FASTA support
        self.current_sequence_metadata = {}
        self.init_ui()
    
    def init_ui(self):
        """Initialize the BLAST page UI"""
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
        
        page_title = QLabel("BLASTP Protein Search")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        page_title.setFont(title_font)
        page_title.setStyleSheet("color: #2c3e50;")
        
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
        self.search_radio = QRadioButton("Search Protein Database")
        
        self.paste_radio.setChecked(True)
        
        self.input_method_group.addButton(self.paste_radio, 1)
        self.input_method_group.addButton(self.upload_radio, 2)
        self.input_method_group.addButton(self.search_radio, 3)
        
        # Style radio buttons
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
        self.search_radio.setStyleSheet(radio_style)
        
        # Connect signals
        self.paste_radio.toggled.connect(self._on_input_method_changed)
        self.upload_radio.toggled.connect(self._on_input_method_changed)
        self.search_radio.toggled.connect(self._on_input_method_changed)
        
        method_buttons_layout.addWidget(self.paste_radio)
        method_buttons_layout.addWidget(self.upload_radio)
        method_buttons_layout.addWidget(self.search_radio)
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
        
        self.input_label = QLabel("Enter protein sequence:")
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Paste your amino acid sequence here (single letter codes)...")
        self.input_text.setMaximumHeight(100)
        self.input_text.textChanged.connect(self._update_sequence_counter)
        
        self.sequence_counter = QLabel("0 amino acids")
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
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
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
        
        # --- Search Database Section ---
        self.search_widget = QWidget()
        search_layout = QVBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 0)
        
        search_button_layout = QHBoxLayout()
        self.search_protein_button = QPushButton("🔍 Search Protein Database")
        self.search_protein_button.clicked.connect(self._open_protein_search)
        self.search_protein_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        
        self.protein_info_label = QLabel("Search AlphaFold/UniProt by protein name or UniProt ID")
        self.protein_info_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        
        search_button_layout.addWidget(self.search_protein_button)
        search_button_layout.addWidget(self.protein_info_label)
        search_button_layout.addStretch()
        
        search_layout.addLayout(search_button_layout)
        self.search_widget.setLayout(search_layout)
        self.search_widget.setVisible(False)
        
        # Add all input widgets to container
        self.input_container_layout.addWidget(self.paste_widget)
        self.input_container_layout.addWidget(self.upload_widget)
        self.input_container_layout.addWidget(self.search_widget)
        self.input_container.setLayout(self.input_container_layout)
        
        input_method_layout.addWidget(self.input_container)
        input_method_group.setLayout(input_method_layout)
        
        # Database selection group
        db_group = QGroupBox("Database Options")
        db_group_layout = QVBoxLayout()
        
        # Remote vs Local database selection
        source_layout = QHBoxLayout()
        self.remote_radio = QCheckBox("Use Remote NCBI Database")
        self.remote_radio.setChecked(True)  # Default to remote
        self.remote_radio.toggled.connect(self.on_database_source_changed)
        source_layout.addWidget(self.remote_radio)
        
        # Database selection
        db_layout = QVBoxLayout()
        db_header_layout = QHBoxLayout()
        db_label = QLabel("Database:")
        db_info_label = QLabel("Search or select from 40+ available databases")
        db_info_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        
        db_header_layout.addWidget(db_label)
        db_header_layout.addStretch()
        db_header_layout.addWidget(db_info_label)
        
        # Create database selection combobox
        self.db_combo = QComboBox()
        
        # Add key databases first for easy access
        key_databases = ['swissprot', 'nr', 'pdb', 'refseq_protein', 'nt', 'refseq_rna']
        for db in key_databases:
            if db in NCBI_DATABASES:
                self.db_combo.addItem(f"{db} - {NCBI_DATABASES[db]}")
        
        # Add remaining databases
        for db, desc in NCBI_DATABASES.items():
            if db not in key_databases:
                self.db_combo.addItem(f"{db} - {desc}")
        
        self.db_combo.setCurrentIndex(0)  # Default to first item (swissprot)
        self.db_combo.setMinimumHeight(30)
        self.db_combo.setToolTip("Select from available NCBI databases")
        self.db_combo.currentTextChanged.connect(self.on_database_changed)
        
        # Database description label
        self.db_description = QLabel()
        self.db_description.setWordWrap(True)
        self.db_description.setStyleSheet("color: #5d6d7e; font-style: italic; padding: 5px; background-color: #f8f9fa; border-radius: 3px; margin-top: 5px;")
        self.update_database_description()
        
        # Popular databases quick access
        popular_layout = QHBoxLayout()
        popular_label = QLabel("Popular:")
        popular_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        
        popular_buttons = []
        for db_name in ['swissprot', 'nr', 'pdb', 'refseq_protein']:
            btn = QPushButton(db_name)
            btn.setMaximumHeight(25)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #e8f4f8;
                    border: 1px solid #3498db;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 10px;
                    color: #2980b9;
                }
                QPushButton:hover {
                    background-color: #3498db;
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
        
        # Add to group
        db_group_layout.addLayout(source_layout)
        db_group_layout.addLayout(db_layout)
        db_group_layout.addLayout(local_db_layout)
        db_group.setLayout(db_group_layout)
        
        # Initially disable local database options
        self.on_database_source_changed()
        
        self.process_button = QPushButton("Run BLASTP Search")
        self.process_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
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
                background-color: #ecf0f1;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                background-color: transparent;
            }
        """)
        
        # Create stat boxes
        self.stat_hits = QLabel("—")
        self.stat_best_eval = QLabel("—")
        self.stat_avg_identity = QLabel("—")
        self.stat_search_time = QLabel("—")
        
        for stat_label in [self.stat_hits, self.stat_best_eval, self.stat_avg_identity, self.stat_search_time]:
            stat_label.setAlignment(Qt.AlignCenter)
            stat_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #27ae60;")
        
        # Create labels for stat descriptions
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
        self.summary_panel.hide()  # Hidden until we have results
        
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
                background-color: #16a085;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #138d75;
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
        
        # Cluster button
        self.cluster_button = QPushButton("📊 Cluster Results")
        self.cluster_button.setEnabled(False)
        cluster_button_style = """
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """
        self.cluster_button.setStyleSheet(cluster_button_style)
        self.cluster_button.clicked.connect(self._on_cluster_results)
        
        results_header_layout.addWidget(self.cluster_button)
        
        # Align button
        self.align_button = QPushButton("🧬 Align Results")
        self.align_button.setEnabled(False)
        align_button_style = """
            QPushButton {
                background-color: #1abc9c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #16a085;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """
        self.align_button.setStyleSheet(align_button_style)
        self.align_button.clicked.connect(self._on_align_results)
        
        results_header_layout.addWidget(self.align_button)
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setAcceptRichText(True)  # Enable HTML rendering
        
        # Add widgets to layout
        layout.addLayout(header_layout)
        layout.addWidget(input_method_group)
        layout.addWidget(db_group)
        layout.addWidget(self.process_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.summary_panel)  # Add summary panel
        layout.addLayout(results_header_layout)
        layout.addWidget(self.output_text)
        
        self.setLayout(layout)
    
    def _on_input_method_changed(self):
        """Handle input method radio button changes"""
        if self.paste_radio.isChecked():
            self.paste_widget.setVisible(True)
            self.upload_widget.setVisible(False)
            self.search_widget.setVisible(False)
        elif self.upload_radio.isChecked():
            self.paste_widget.setVisible(False)
            self.upload_widget.setVisible(True)
            self.search_widget.setVisible(False)
        elif self.search_radio.isChecked():
            self.paste_widget.setVisible(False)
            self.upload_widget.setVisible(False)
            self.search_widget.setVisible(True)
    
    def _update_sequence_counter(self):
        """Update the amino acid counter for pasted sequence"""
        text = self.input_text.toPlainText().strip().upper()
        # Remove whitespace
        clean_text = ''.join(c for c in text if c.isalpha())
        
        count = len(clean_text)
        self.sequence_counter.setText(f"{count} amino acids")
        
        # Validate and show warning colors
        if count == 0:
            self.sequence_counter.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        elif count < 10:
            self.sequence_counter.setStyleSheet("color: #e74c3c; font-size: 10px; font-weight: bold;")
        elif count > 10000:
            self.sequence_counter.setStyleSheet("color: #e67e22; font-size: 10px; font-weight: bold;")
        else:
            self.sequence_counter.setStyleSheet("color: #27ae60; font-size: 10px; font-weight: bold;")
    
    def _upload_fasta_file(self):
        """Open file dialog and load FASTA file"""
        filepath, _ = QFileDialog.getOpenFile(
            self,
            "Open FASTA File",
            "",
            "FASTA Files (*.fasta *.fa *.fna *.ffn *.faa *.frn);;All Files (*)"
        )
        
        if not filepath:
            return
        
        try:
            sequences = self.fasta_parser.parse_file(filepath)
            
            # Show warnings if any
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
                # Single sequence - load directly
                self.fasta_file_label.setText(f"✓ {filename} ({len(sequences[0].sequence)} aa)")
                self.fasta_sequence_selector.setVisible(False)
                
                # Populate input_text for compatibility with existing code
                self.input_text.setPlainText(sequences[0].sequence)
                self.current_sequence_metadata = {
                    'source': 'fasta_file',
                    'filename': filename,
                    'header': sequences[0].header,
                    'id': sequences[0].id
                }
            else:
                # Multiple sequences - show selector
                self.fasta_file_label.setText(f"✓ {filename} ({len(sequences)} sequences)")
                self.fasta_sequence_selector.clear()
                
                for seq in sequences:
                    self.fasta_sequence_selector.addItem(
                        f"{seq.id} ({len(seq.sequence)} aa)",
                        seq
                    )
                
                self.fasta_sequence_selector.setVisible(True)
                # Trigger selection of first sequence
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
    
    def _open_protein_search(self):
        """Open protein search dialog"""
        dialog = ProteinSearchDialog(self)
        dialog.sequence_selected.connect(self._on_protein_selected)
        dialog.exec_()
    
    def _on_protein_selected(self, sequence, metadata):
        """Handle protein selection from search dialog"""
        # Show confirmation
        reply = QMessageBox.question(
            self,
            "Load Sequence",
            f"Load sequence for {metadata.get('protein_name', 'Unknown')}?\n\n"
            f"UniProt ID: {metadata.get('uniprot_id', 'Unknown')}\n"
            f"Organism: {metadata.get('organism', 'Unknown')}\n"
            f"Length: {metadata.get('length', 0)} amino acids",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.input_text.setPlainText(sequence)
            self.current_sequence_metadata = metadata
            self.protein_info_label.setText(
                f"✓ Loaded: {metadata.get('protein_name', 'Unknown')} "
                f"({metadata.get('uniprot_id', 'Unknown')})"
            )
            self.protein_info_label.setStyleSheet("color: #27ae60; font-weight: bold;")
    
    def _export_results(self, format_type):
        """Export results to TSV or CSV"""
        if not self.current_results_html:
            QMessageBox.warning(
                self,
                "No Results",
                "No results available to export. Please run a search first."
            )
            return
        
        # Get default filename
        query_name = self.current_sequence_metadata.get('id', 'query')
        default_filename = self.exporter.get_default_filename('blast', query_name)
        
        # Show save dialog
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
            # Export results
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
        # Extract database name from "dbname - description" format
        current_db = current_text.split(' - ')[0] if ' - ' in current_text else current_text
        description = NCBI_DATABASES.get(current_db, "Database information not available")
        self.db_description.setText(f"📋 {description}")
    
    def on_database_source_changed(self):
        """Enable/disable local database options based on remote checkbox"""
        is_remote = self.remote_radio.isChecked()
        
        # Enable/disable local database widgets
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
        """Run BLASTP search in background thread"""
        sequence = self.input_text.toPlainText().strip().upper()
        
        # Basic validation
        if not sequence:
            self.output_text.setText("Please enter a protein sequence first.")
            return
        
        # Remove any whitespace or numbers
        sequence = ''.join(c for c in sequence if c.isalpha())
        
        # Check if it's a valid protein sequence (basic check)
        valid_aa = set('ACDEFGHIKLMNPQRSTVWY')
        if not all(c in valid_aa for c in sequence):
            self.output_text.setText("Error: Invalid amino acid sequence. Please use single-letter amino acid codes only.")
            return
        
        # Disable button during search
        self.process_button.setEnabled(False)
        self.status_label.setText("Running BLASTP search... This may take a minute.")
        self.output_text.setText("Searching NCBI database...\n\nPlease wait, this can take 30-60 seconds for remote searches.")
        
        # Get selected database and options
        database_text = self.db_combo.currentText()
        database = database_text.split(' - ')[0] if ' - ' in database_text else database_text
        use_remote = self.remote_radio.isChecked()
        local_db_path = self.local_db_path.text().strip()
        
        # Validate local database path if not using remote
        if not use_remote and not local_db_path:
            # Use default local database directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            default_db_dir = os.path.join(script_dir, 'blast_databases')
            if not os.path.exists(default_db_dir):
                self.output_text.setText(f"Error: Default database directory not found: {default_db_dir}\nPlease specify a custom database path or use remote database.")
                return
            local_db_path = ""  # Will use default
        
        # Start BLAST in background thread
        self.search_start_time = time.time()
        self.blast_worker = BLASTWorker(sequence, database, use_remote, local_db_path)
        self.blast_worker.finished.connect(self.on_blast_finished)
        self.blast_worker.error.connect(self.on_blast_error)
        self.blast_worker.start()
    
    def extract_stats_from_html(self, html_results):
        """Extract statistics from HTML results"""
        import re
        
        # Count hits
        hits_match = re.search(r'Found (\d+) significant alignment', html_results)
        total_hits = int(hits_match.group(1)) if hits_match else 0
        
        # Extract all E-values
        evalue_matches = re.findall(r'E-value:</span> <b[^>]*>([\d\.e\-+]+)</b>', html_results)
        best_evalue = min([float(e) for e in evalue_matches]) if evalue_matches else None
        
        # Extract all identity percentages
        identity_matches = re.findall(r'Identity:</span> <b[^>]*>\d+/\d+ \(([\d\.]+)%\)</b>', html_results)
        avg_identity = sum([float(i) for i in identity_matches]) / len(identity_matches) if identity_matches else 0
        
        return total_hits, best_evalue, avg_identity
    
    def update_summary_panel(self, total_hits, best_evalue, avg_identity, search_time):
        """Update the summary statistics panel"""
        self.stat_hits.setText(str(total_hits))
        
        if best_evalue is not None:
            if best_evalue < 1e-100:
                self.stat_best_eval.setText(f"{best_evalue:.1e}")
                self.stat_best_eval.setStyleSheet("font-size: 18px; font-weight: bold; color: #27ae60;")
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
            if avg_identity >= 70:
                self.stat_avg_identity.setStyleSheet("font-size: 18px; font-weight: bold; color: #27ae60;")
            elif avg_identity >= 50:
                self.stat_avg_identity.setStyleSheet("font-size: 18px; font-weight: bold; color: #f39c12;")
            else:
                self.stat_avg_identity.setStyleSheet("font-size: 18px; font-weight: bold; color: #e67e22;")
        else:
            self.stat_avg_identity.setText("N/A")
            self.stat_avg_identity.setStyleSheet("font-size: 18px; font-weight: bold; color: #95a5a6;")
        
        self.stat_search_time.setText(f"{search_time:.1f}s")
        
        self.summary_panel.show()
    
    def on_blast_finished(self, results_html, results_data):
        """Handle BLAST results"""
        search_time = time.time() - self.search_start_time if self.search_start_time else 0
        
        # Store results for export and clustering
        self.current_results_html = results_html
        self.current_results_data = results_data
        self.current_query_info = {
            'query_name': self.current_sequence_metadata.get('id', 'query'),
            'query_length': str(len(self.input_text.toPlainText().strip())),
            'database': self.db_combo.currentText().split(' - ')[0],
            'search_time': f"{search_time:.1f}s"
        }
        
        # Extract statistics and update summary panel
        total_hits, best_evalue, avg_identity = self.extract_stats_from_html(results_html)
        self.update_summary_panel(total_hits, best_evalue, avg_identity, search_time)
        
        # Display HTML results
        self.output_text.setHtml(results_html)
        self.status_label.setText("Search complete!")
        self.process_button.setEnabled(True)
        
        # Enable export and cluster buttons
        self.export_tsv_button.setEnabled(True)
        self.export_csv_button.setEnabled(True)
        self.cluster_button.setEnabled(len(results_data) >= 2)  # Need at least 2 for clustering
        self.align_button.setEnabled(len(results_data) >= 2)  # Need at least 2 for alignment
    
    def on_blast_error(self, error_msg):
        """Handle BLAST errors"""
        self.summary_panel.hide()
        self.output_text.setPlainText(f"Error running BLAST:\n\n{error_msg}")
        self.status_label.setText("Error occurred")
        self.process_button.setEnabled(True)
    
    def _on_cluster_results(self):
        """Handle cluster results button - orchestrate the clustering workflow"""
        if not self.current_results_data or len(self.current_results_data) < 2:
            QMessageBox.warning(
                self,
                "Insufficient Results",
                "Need at least 2 results for clustering."
            )
            return
        
        # Step 1: Show selection dialog
        selection_dialog = ClusterSelectionDialog(self.current_results_data, self)
        if selection_dialog.exec_() != QDialog.Accepted:
            return
        
        selected_hits = selection_dialog.get_selected_hits()
        if len(selected_hits) < 2:
            return
        
        # Step 2: Fetch sequences (with progress dialog)
        self._fetch_and_cluster(selected_hits)
    
    def _fetch_and_cluster(self, selected_hits):
        """Fetch sequences and proceed to clustering"""
        from PyQt5.QtWidgets import QProgressDialog
        
        # Determine database path for sequence fetching
        database_path = None
        if not self.remote_radio.isChecked():
            # Local database
            if self.local_db_path.text().strip():
                database_path = os.path.join(self.local_db_path.text().strip(), self.db_combo.currentText().split(' - ')[0])
            else:
                config = get_config()
                db_name = self.db_combo.currentText().split(' - ')[0]
                database_path = os.path.join(config.get_blast_db_dir(), db_name, db_name)
        
        # Create progress dialog
        progress = QProgressDialog("Fetching sequences...", "Cancel", 0, len(selected_hits), self)
        progress.setWindowTitle("Retrieving Sequences")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        
        # Create and start worker
        self.sequence_fetcher = SequenceFetcherWorker(selected_hits, database_path)
        self.sequence_fetcher.progress.connect(
            lambda current, total, status: progress.setValue(current)
        )
        self.sequence_fetcher.finished.connect(
            lambda successful, failed: self._on_sequences_fetched(successful, failed, progress)
        )
        progress.canceled.connect(self.sequence_fetcher.stop)
        
        self.sequence_fetcher.start()
    
    def _on_sequences_fetched(self, successful_hits, failed_hits, progress_dialog):
        """Handle completion of sequence fetching"""
        progress_dialog.close()
        
        # Step 3: Show clustering config dialog
        config_dialog = ClusteringConfigDialog(successful_hits, failed_hits, self)
        if config_dialog.exec_() != QDialog.Accepted:
            return
        
        clustering_params = config_dialog.get_parameters()
        final_hits = config_dialog.get_successful_hits()
        
        if len(final_hits) < 2:
            QMessageBox.warning(
                self,
                "Insufficient Sequences",
                "Need at least 2 sequences for clustering."
            )
            return
        
        # Step 4: Create temp FASTA
        try:
            temp_manager = get_temp_fasta_manager()
            fasta_path = temp_manager.create_temp_fasta(final_hits, prefix='blast_cluster_')
            
            # Step 5: Navigate to clustering page
            self.navigate_to_clustering.emit(fasta_path, clustering_params)
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Creating FASTA",
                f"Failed to create temporary FASTA file:\n\n{str(e)}"
            )
    
    def _on_align_results(self):
        """Handle align results button - orchestrate the alignment workflow"""
        if not self.current_results_data or len(self.current_results_data) < 2:
            QMessageBox.warning(
                self,
                "Insufficient Results",
                "Need at least 2 results for alignment."
            )
            return
        
        # Step 1: Show selection dialog (reuse clustering selection dialog)
        selection_dialog = ClusterSelectionDialog(self.current_results_data, self)
        selection_dialog.setWindowTitle("Select Sequences for Alignment")
        if selection_dialog.exec_() != QDialog.Accepted:
            return
        
        selected_hits = selection_dialog.get_selected_hits()
        if len(selected_hits) < 2:
            QMessageBox.warning(
                self,
                "Insufficient Selection",
                "Please select at least 2 sequences for alignment."
            )
            return
        
        # Step 2: Fetch sequences (with progress dialog)
        self._fetch_and_align(selected_hits)
    
    def _fetch_and_align(self, selected_hits):
        """Fetch sequences and proceed to alignment"""
        from PyQt5.QtWidgets import QProgressDialog
        
        # Determine database path for sequence fetching
        database_path = None
        if not self.remote_radio.isChecked():
            # Local database
            if self.local_db_path.text().strip():
                database_path = os.path.join(self.local_db_path.text().strip(), self.db_combo.currentText().split(' - ')[0])
            else:
                config = get_config()
                db_name = self.db_combo.currentText().split(' - ')[0]
                database_path = os.path.join(config.get_blast_db_dir(), db_name, db_name)
        
        # Create progress dialog
        progress = QProgressDialog("Fetching sequences for alignment...", "Cancel", 0, len(selected_hits), self)
        progress.setWindowTitle("Retrieving Sequences")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        
        # Create and start worker
        self.align_sequence_fetcher = SequenceFetcherWorker(selected_hits, database_path)
        self.align_sequence_fetcher.progress.connect(
            lambda current, total, status: progress.setValue(current)
        )
        self.align_sequence_fetcher.finished.connect(
            lambda successful, failed: self._on_align_sequences_fetched(successful, failed, progress)
        )
        progress.canceled.connect(self.align_sequence_fetcher.stop)
        
        self.align_sequence_fetcher.start()
    
    def _on_align_sequences_fetched(self, successful_hits, failed_hits, progress_dialog):
        """Handle completion of sequence fetching for alignment"""
        progress_dialog.close()
        
        # Check if we have enough sequences
        if len(successful_hits) < 2:
            failed_msg = ""
            if failed_hits:
                failed_msg = f"\n\nFailed to fetch {len(failed_hits)} sequences."
            QMessageBox.warning(
                self,
                "Insufficient Sequences",
                f"Need at least 2 sequences with successfully retrieved sequences for alignment.{failed_msg}"
            )
            return
        
        # Show summary if some failed
        if failed_hits:
            reply = QMessageBox.question(
                self,
                "Some Sequences Failed",
                f"Successfully fetched {len(successful_hits)} sequences.\n"
                f"Failed to fetch {len(failed_hits)} sequences.\n\n"
                "Do you want to proceed with the successful sequences?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        
        # Create temp FASTA
        try:
            temp_manager = get_temp_fasta_manager()
            fasta_path = temp_manager.create_temp_fasta(successful_hits, prefix='blast_align_')
            
            # Navigate to alignment page
            self.navigate_to_alignment.emit(fasta_path)
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Creating FASTA",
                f"Failed to create temporary FASTA file:\n\n{str(e)}"
            )