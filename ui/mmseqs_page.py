import os
import time
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel, 
                             QComboBox, QHBoxLayout, QLineEdit, QFileDialog, QGroupBox, 
                             QRadioButton, QButtonGroup, QMessageBox, QFrame, QDialog)
from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont

from core.mmseqs_runner import MMseqsWorker
from core.db_definitions import NCBI_DATABASES
from core.db_conversion_manager import DatabaseConversionManager
from core.db_conversion_worker import DatabaseConversionWorker
from core.wsl_utils import is_wsl_available, check_mmseqs_installation, check_blastdbcmd_installation
from ui.dialogs.conversion_progress_dialog import ConversionProgressDialog
from ui.dialogs.protein_search_dialog import ProteinSearchDialog
from ui.dialogs.cluster_selection_dialog import ClusterSelectionDialog
from ui.dialogs.clustering_config_dialog import ClusteringConfigDialog
from core.sequence_fetcher_worker import SequenceFetcherWorker
from core.temp_fasta_manager import get_temp_fasta_manager
from utils.fasta_parser import FastaParser, FastaParseError
from utils.export_manager import ResultsExporter, ExportError, show_export_error, show_export_success


class MMseqsPage(QWidget):
    """MMseqs2 analysis page widget"""
    back_requested = pyqtSignal()  # Signal to go back to home page
    navigate_to_clustering = pyqtSignal(str, dict)  # fasta_path, clustering_params

    def __init__(self):
        super().__init__()
        self.mmseqs_worker = None
        self.conversion_manager = DatabaseConversionManager()
        self.conversion_dialogs = {}  # Track active conversion dialogs
        self.blast_db_dir = "E:\\Projects\\Protein-GUI\\blast_databases"
        self.installed_databases = set()  # Track which databases are installed
        self.custom_blast_db_path = None  # For user-selected BLAST database
        self.search_start_time = None
        self.current_results_html = ""
        self.current_results_data = []  # Structured SearchHit objects
        self.current_query_info = {}
        self.current_database_path = ""  # For sequence fetching
        self.fasta_parser = FastaParser()
        self.exporter = ResultsExporter()
        self.loaded_sequences = []
        self.current_sequence_metadata = {}
        self.init_ui()
        
        # Check WSL/MMseqs2 availability on startup
        QTimer.singleShot(500, self.check_system_requirements)
        # Scan for installed BLAST databases
        QTimer.singleShot(100, self.scan_installed_databases)

    def init_ui(self):
        """Initialize the MMseqs2 page UI"""
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

        page_title = QLabel("MMseqs2 Protein Search")
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
        
        # Database and options selection group
        options_group = QGroupBox("Database Options")
        options_group_layout = QVBoxLayout()
        
        # Database source selection
        source_layout = QVBoxLayout()
        source_label = QLabel("Database Source:")
        source_label_font = QFont()
        source_label_font.setBold(True)
        source_label.setFont(source_label_font)
        
        self.db_source_group = QButtonGroup()
        self.ncbi_radio = QRadioButton("Use NCBI Database (from blast_databases folder)")
        self.custom_ncbi_radio = QRadioButton("Browse for NCBI Database (other location)")
        self.custom_mmseqs_radio = QRadioButton("Use Existing MMseqs2 Database")
        
        self.db_source_group.addButton(self.ncbi_radio, 0)
        self.db_source_group.addButton(self.custom_ncbi_radio, 1)
        self.db_source_group.addButton(self.custom_mmseqs_radio, 2)
        self.ncbi_radio.setChecked(True)
        
        self.ncbi_radio.toggled.connect(self.on_db_source_changed)
        self.custom_ncbi_radio.toggled.connect(self.on_db_source_changed)
        self.custom_mmseqs_radio.toggled.connect(self.on_db_source_changed)
        
        source_layout.addWidget(source_label)
        source_layout.addWidget(self.ncbi_radio)
        source_layout.addWidget(self.custom_ncbi_radio)
        source_layout.addWidget(self.custom_mmseqs_radio)
        
        # NCBI database dropdown
        self.ncbi_db_layout = QVBoxLayout()
        
        db_dropdown_layout = QHBoxLayout()
        db_dropdown_label = QLabel("Select Database:")
        db_dropdown_label.setMinimumWidth(120)  # Fixed width for label
        db_dropdown_label.setMaximumWidth(120)
        
        self.db_combo = QComboBox()
        self.db_combo.setMinimumHeight(30)
        self.db_combo.setMinimumWidth(300)  # Set reasonable width
        
        self.db_combo.currentTextChanged.connect(self.on_database_selection_changed)
        
        db_dropdown_layout.addWidget(db_dropdown_label)
        db_dropdown_layout.addWidget(self.db_combo)
        db_dropdown_layout.addStretch()  # Push everything to the left
        
        # Database status label (create BEFORE populating dropdown)
        self.db_status_label = QLabel()
        self.db_status_label.setWordWrap(True)
        self.db_status_label.setStyleSheet("padding: 5px; background-color: #f8f9fa; border-radius: 3px; margin-top: 5px;")
        
        # Populate with NCBI databases and status (AFTER label is created)
        self.populate_database_dropdown()
        
        self.ncbi_db_layout.addLayout(db_dropdown_layout)
        self.ncbi_db_layout.addWidget(self.db_status_label)
        
        # Custom NCBI database path (for browsing to other locations)
        self.custom_ncbi_layout = QHBoxLayout()
        custom_ncbi_label = QLabel("BLAST Database:")
        custom_ncbi_label.setMinimumWidth(120)
        custom_ncbi_label.setMaximumWidth(120)
        self.custom_ncbi_path = QLineEdit()
        self.custom_ncbi_path.setPlaceholderText("Browse to BLAST database file (without extension)")
        self.browse_ncbi_button = QPushButton("Browse...")
        self.browse_ncbi_button.clicked.connect(self.browse_ncbi_database_path)
        
        self.custom_ncbi_layout.addWidget(custom_ncbi_label)
        self.custom_ncbi_layout.addWidget(self.custom_ncbi_path)
        self.custom_ncbi_layout.addWidget(self.browse_ncbi_button)
        
        # Custom MMseqs2 database path
        self.custom_mmseqs_layout = QHBoxLayout()
        custom_mmseqs_label = QLabel("MMseqs2 Database:")
        custom_mmseqs_label.setMinimumWidth(120)
        custom_mmseqs_label.setMaximumWidth(120)
        self.custom_mmseqs_path = QLineEdit()
        self.custom_mmseqs_path.setPlaceholderText("Path to MMseqs2 database (required)")
        self.browse_mmseqs_button = QPushButton("Browse...")
        self.browse_mmseqs_button.clicked.connect(self.browse_mmseqs_database_path)
        
        self.custom_mmseqs_layout.addWidget(custom_mmseqs_label)
        self.custom_mmseqs_layout.addWidget(self.custom_mmseqs_path)
        self.custom_mmseqs_layout.addWidget(self.browse_mmseqs_button)
        
        # Sensitivity selection
        sensitivity_layout = QHBoxLayout()
        sensitivity_label = QLabel("Sensitivity:")
        self.sensitivity_combo = QComboBox()
        self.sensitivity_combo.addItems([
            'fast - Fast search (less sensitive)',
            'sensitive - Balanced speed and sensitivity (default)',
            'more-sensitive - More sensitive search',
            'very-sensitive - Very sensitive search (slower)'
        ])
        self.sensitivity_combo.setCurrentIndex(1)  # Default to 'sensitive'
        self.sensitivity_combo.setMinimumHeight(30)
        
        sensitivity_layout.addWidget(sensitivity_label)
        sensitivity_layout.addWidget(self.sensitivity_combo)
        sensitivity_layout.addStretch()
        
        # Info label
        self.info_label = QLabel("ℹ️ MMseqs2 uses WSL Ubuntu. First-time database selection will trigger auto-conversion.")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #5d6d7e; font-style: italic; padding: 5px; background-color: #e8f4f8; border-radius: 3px; margin-top: 5px;")
        
        # Add to group
        options_group_layout.addLayout(source_layout)
        options_group_layout.addLayout(self.ncbi_db_layout)
        options_group_layout.addLayout(self.custom_ncbi_layout)
        options_group_layout.addLayout(self.custom_mmseqs_layout)
        options_group_layout.addLayout(sensitivity_layout)
        options_group_layout.addWidget(self.info_label)
        options_group.setLayout(options_group_layout)
        
        # Initially show/hide appropriate controls
        self.on_db_source_changed()
        
        self.process_button = QPushButton("Run MMseqs2 Search")
        self.process_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.process_button.clicked.connect(self.run_mmseqs)
        
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
            stat_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #8e44ad;")
        
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
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setAcceptRichText(True)  # Enable HTML rendering
        
        # Add widgets to layout
        layout.addLayout(header_layout)
        layout.addWidget(input_method_group)
        layout.addWidget(options_group)
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
        default_filename = self.exporter.get_default_filename('mmseqs', query_name)
        
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
            success = self.exporter.export_mmseqs_results(
                self.current_results_html,
                self.current_query_info,
                filepath,
                format_type
            )
            
            if success:
                show_export_success(self, filepath)
        
        except ExportError as e:
            show_export_error(self, e)
    
    def get_current_database_name(self):
        """Get the current database name for display"""
        if self.custom_mmseqs_radio.isChecked():
            path = self.custom_mmseqs_path.text()
            return os.path.basename(path) if path else "Custom MMseqs2 DB"
        elif self.custom_ncbi_radio.isChecked():
            if self.custom_blast_db_path:
                return self.custom_blast_db_path
            return "Custom NCBI DB"
        else:
            return self.db_combo.currentText().split(' (')[0] if hasattr(self, 'db_combo') else "Unknown"
    
    def scan_installed_databases(self):
        """Scan the blast_databases folder to find which databases are installed"""
        self.installed_databases.clear()
        
        if not os.path.exists(self.blast_db_dir):
            return
        
        try:
            # List all subdirectories in blast_databases
            for item in os.listdir(self.blast_db_dir):
                db_folder = os.path.join(self.blast_db_dir, item)
                if os.path.isdir(db_folder):
                    # Check if the database files exist
                    # Look for .phr file (may be named dbname.phr or dbname.00.phr for multi-volume)
                    db_file_single = os.path.join(db_folder, item + ".phr")
                    db_file_multi = os.path.join(db_folder, item + ".00.phr")
                    
                    if os.path.exists(db_file_single) or os.path.exists(db_file_multi):
                        self.installed_databases.add(item)
            
            print(f"Scanned blast_databases: Found {len(self.installed_databases)} installed databases")
            print(f"Installed: {sorted(self.installed_databases)}")
            
            # Refresh dropdown to show updated icons
            if hasattr(self, 'db_combo'):
                self.populate_database_dropdown()
        
        except Exception as e:
            print(f"Error scanning databases: {e}")

    def populate_database_dropdown(self):
        """Populate the database dropdown with NCBI databases and status indicators"""
        self.db_combo.clear()
        
        # Add key databases first
        key_databases = ['swissprot', 'nr', 'pdb', 'refseq_protein']
        
        for db in key_databases:
            if db in NCBI_DATABASES:
                status_icon = self.get_database_status_icon(db)
                self.db_combo.addItem(f"{status_icon} {db}")
        
        # Add separator
        self.db_combo.insertSeparator(len(key_databases))
        
        # Add remaining databases
        for db in sorted(NCBI_DATABASES.keys()):
            if db not in key_databases:
                status_icon = self.get_database_status_icon(db)
                self.db_combo.addItem(f"{status_icon} {db}")
        
        # Update status label for first database
        if self.db_combo.count() > 0:
            self.update_database_status_label()
    
    def get_database_status_icon(self, db_name):
        """Get status icon for a database
        
        Returns:
            str: Icon representing conversion and installation status
        """
        # Check if converted
        if self.conversion_manager.is_converted(db_name):
            return "✓"
        elif self.conversion_manager.is_converting(db_name):
            return "⟳"
        else:
            status = self.conversion_manager.get_database_status(db_name)
            if status["status"] == "failed":
                return "✗"
            
            # Check if BLAST database is installed
            if db_name in self.installed_databases:
                return "○"  # Installed but not converted
            else:
                return "⊘"  # Not installed
    
    def get_selected_database_name(self):
        """Extract database name from combo box selection"""
        text = self.db_combo.currentText()
        # Remove status icon and description
        parts = text.split()
        if len(parts) >= 2:
            return parts[1]  # Second part is the database name
        return text
    
    def update_database_status_label(self):
        """Update the database status label based on current selection"""
        db_name = self.get_selected_database_name()
        if not db_name or db_name == "":
            return
        
        status = self.conversion_manager.get_database_status(db_name)
        
        if status["status"] == "converted":
            self.db_status_label.setText(
                f"✓ <b>{db_name}</b> is ready to use<br>"
                f"<small>Converted: {status.get('converted_date', 'Unknown')[:10]}</small>"
            )
            self.db_status_label.setStyleSheet(
                "padding: 5px; background-color: #d5f4e6; border-radius: 3px; "
                "margin-top: 5px; color: #27ae60;"
            )
        elif status["status"] == "converting":
            self.db_status_label.setText(
                f"⟳ <b>{db_name}</b> is currently being converted<br>"
                f"<small>Please wait or use BLAST while conversion completes</small>"
            )
            self.db_status_label.setStyleSheet(
                "padding: 5px; background-color: #fff3cd; border-radius: 3px; "
                "margin-top: 5px; color: #856404;"
            )
        elif status["status"] == "failed":
            self.db_status_label.setText(
                f"✗ <b>{db_name}</b> conversion failed<br>"
                f"<small>{status.get('error', 'Unknown error')}</small><br>"
                f"<small>Click the search button to try again</small>"
            )
            self.db_status_label.setStyleSheet(
                "padding: 5px; background-color: #f8d7da; border-radius: 3px; "
                "margin-top: 5px; color: #721c24;"
            )
        else:
            desc = NCBI_DATABASES.get(db_name, "")
            
            # Check if database is installed
            if db_name in self.installed_databases:
                self.db_status_label.setText(
                    f"○ <b>{db_name}</b> installed but not converted<br>"
                    f"<small>{desc}</small><br>"
                    f"<small>Will auto-convert when you start a search</small>"
                )
                self.db_status_label.setStyleSheet(
                    "padding: 5px; background-color: #f8f9fa; border-radius: 3px; "
                    "margin-top: 5px; color: #5d6d7e;"
                )
            else:
                self.db_status_label.setText(
                    f"⊘ <b>{db_name}</b> not installed<br>"
                    f"<small>{desc}</small><br>"
                    f"<small>Download from NCBI or use 'Browse' to locate it</small>"
                )
                self.db_status_label.setStyleSheet(
                    "padding: 5px; background-color: #fff3cd; border-radius: 3px; "
                    "margin-top: 5px; color: #856404;"
                )
    
    def on_database_selection_changed(self):
        """Handle database selection change"""
        self.update_database_status_label()
    
    def on_db_source_changed(self):
        """Handle database source radio button change"""
        is_ncbi = self.ncbi_radio.isChecked()
        is_custom_ncbi = self.custom_ncbi_radio.isChecked()
        is_custom_mmseqs = self.custom_mmseqs_radio.isChecked()
        
        # Show/hide NCBI dropdown
        for i in range(self.ncbi_db_layout.count()):
            item = self.ncbi_db_layout.itemAt(i)
            if item.widget():
                item.widget().setVisible(is_ncbi)
            elif item.layout():
                for j in range(item.layout().count()):
                    w = item.layout().itemAt(j).widget()
                    if w:
                        w.setVisible(is_ncbi)
        
        # Show/hide custom NCBI browse
        for i in range(self.custom_ncbi_layout.count()):
            widget = self.custom_ncbi_layout.itemAt(i).widget()
            if widget:
                widget.setVisible(is_custom_ncbi)
        
        # Show/hide custom MMseqs2 browse
        for i in range(self.custom_mmseqs_layout.count()):
            widget = self.custom_mmseqs_layout.itemAt(i).widget()
            if widget:
                widget.setVisible(is_custom_mmseqs)
    
    def check_system_requirements(self):
        """Check if WSL and MMseqs2 are available"""
        if not is_wsl_available():
            self.info_label.setText(
                "⚠️ WSL not detected. MMseqs2 requires Windows Subsystem for Linux.\n"
                "Please use BLAST search or install WSL to use MMseqs2."
            )
            self.info_label.setStyleSheet(
                "color: #856404; font-style: italic; padding: 5px; "
                "background-color: #fff3cd; border-radius: 3px; margin-top: 5px;"
            )
            return
        
        # Check MMseqs2
        mmseqs_installed, mmseqs_version, mmseqs_path = check_mmseqs_installation()
        if not mmseqs_installed:
            self.info_label.setText(
                "⚠️ MMseqs2 not found in WSL. Please install MMseqs2 or use BLAST search.\n"
                "Installation: wget https://mmseqs.com/latest/mmseqs-linux-avx2.tar.gz"
            )
            self.info_label.setStyleSheet(
                "color: #856404; font-style: italic; padding: 5px; "
                "background-color: #fff3cd; border-radius: 3px; margin-top: 5px;"
            )
            return
        
        # Check blastdbcmd
        blast_installed, blast_version, blast_path = check_blastdbcmd_installation()
        if not blast_installed:
            self.info_label.setText(
                "⚠️ blastdbcmd not found in WSL. Required for database conversion.\n"
                "Installation: sudo apt install ncbi-blast+"
            )
            self.info_label.setStyleSheet(
                "color: #856404; font-style: italic; padding: 5px; "
                "background-color: #fff3cd; border-radius: 3px; margin-top: 5px;"
            )
            return
        
        # All good!
        self.info_label.setText(
            f"✓ MMseqs2 ready ({mmseqs_version or 'installed'}). "
            "First-time database selection will trigger auto-conversion."
        )
        self.info_label.setStyleSheet(
            "color: #27ae60; font-style: italic; padding: 5px; "
            "background-color: #d5f4e6; border-radius: 3px; margin-top: 5px;"
        )
    
    def browse_ncbi_database_path(self):
        """Browse for NCBI BLAST database in a custom location"""
        database_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select BLAST Database File (e.g., swissprot.phr)",
            "",
            "BLAST Protein DB (*.phr);;All Files (*)"
        )
        if database_file:
            # Remove the extension to get the base path
            base_path = database_file.rsplit('.', 1)[0] if '.' in database_file else database_file
            self.custom_ncbi_path.setText(base_path)
            # Store for later use
            self.custom_blast_db_path = base_path
    
    def browse_mmseqs_database_path(self):
        """Browse for existing MMseqs2 database"""
        database_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select MMseqs2 Database File",
            "",
            "All Files (*)"
        )
        if database_file:
            self.custom_mmseqs_path.setText(database_file)
    
    def start_database_conversion(self, db_name, blast_db_path=None):
        """Start converting a BLAST database to MMseqs2 format
        
        Args:
            db_name: Name of the database to convert
            blast_db_path: Optional custom path to BLAST database
        """
        # Check if already converting
        if self.conversion_manager.is_converting(db_name):
            QMessageBox.information(
                self,
                "Conversion In Progress",
                f"Database '{db_name}' is already being converted.\n\n"
                "Please wait for the conversion to complete."
            )
            return
        
        # Get BLAST database path
        if blast_db_path is None:
            # Use default path: BLAST databases are typically stored as db_name/db_name.ext
            blast_db_dir = self.blast_db_dir
            blast_db_path = os.path.join(blast_db_dir, db_name, db_name)
        else:
            # Use custom path provided by user
            blast_db_dir = os.path.dirname(blast_db_path)
        
        # Check if BLAST database exists
        if not os.path.exists(blast_db_dir):
            QMessageBox.critical(
                self,
                "BLAST Database Not Found",
                f"BLAST database directory not found:\n{blast_db_dir}\n\n"
                "Please ensure BLAST databases are installed."
            )
            return
        
        # Verify the database files exist (check for .phr file for protein databases)
        blast_db_check = blast_db_path + ".phr"
        if not os.path.exists(blast_db_check):
            QMessageBox.critical(
                self,
                "BLAST Database Files Not Found",
                f"BLAST database files not found at:\n{blast_db_path}\n\n"
                f"Expected files like:\n"
                f"  {db_name}.phr\n"
                f"  {db_name}.pin\n"
                f"  {db_name}.psq\n\n"
                "Please ensure the BLAST database is properly installed."
            )
            return
        
        # Output directory for MMseqs2 databases
        mmseqs_db_dir = "E:\\Projects\\Protein-GUI\\mmseqs_databases"
        os.makedirs(mmseqs_db_dir, exist_ok=True)
        
        # Mark as converting
        mmseqs_db_path = os.path.join(mmseqs_db_dir, db_name)
        self.conversion_manager.mark_converting(db_name, blast_db_path, mmseqs_db_path)
        
        # Create and show progress dialog
        progress_dialog = ConversionProgressDialog(db_name, self)
        
        # Create conversion worker
        worker = DatabaseConversionWorker(db_name, blast_db_path, mmseqs_db_dir)
        progress_dialog.set_worker(worker)
        
        # Connect worker signals
        worker.finished.connect(lambda name, path: self.on_conversion_finished(name, path, progress_dialog))
        worker.error.connect(lambda name, error: self.on_conversion_error(name, error, progress_dialog))
        
        # Store dialog reference
        self.conversion_dialogs[db_name] = progress_dialog
        
        # Start conversion
        worker.start()
        progress_dialog.show()
        
        # Refresh dropdown
        self.populate_database_dropdown()
        self.update_database_status_label()
    
    def on_conversion_finished(self, db_name, mmseqs_path, dialog):
        """Handle successful database conversion"""
        self.conversion_manager.mark_converted(db_name, mmseqs_path)
        
        # Refresh dropdown
        self.populate_database_dropdown()
        self.update_database_status_label()
        
        # Remove dialog reference
        if db_name in self.conversion_dialogs:
            del self.conversion_dialogs[db_name]
    
    def on_conversion_error(self, db_name, error_message, dialog):
        """Handle database conversion error"""
        self.conversion_manager.mark_failed(db_name, error_message)
        
        # Refresh dropdown
        self.populate_database_dropdown()
        self.update_database_status_label()
        
        # Remove dialog reference
        if db_name in self.conversion_dialogs:
            del self.conversion_dialogs[db_name]

    def run_mmseqs(self):
        """Run MMseqs2 search in background thread"""
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
        
        # Get database path based on source
        if self.ncbi_radio.isChecked():
            # Option 1: NCBI database from blast_databases folder
            db_name = self.get_selected_database_name()
            
            # Check if database is installed
            if db_name not in self.installed_databases:
                QMessageBox.warning(
                    self,
                    "Database Not Installed",
                    f"Database '{db_name}' is not installed in:\n{self.blast_db_dir}\n\n"
                    "Please either:\n"
                    "• Download and install the database to blast_databases folder\n"
                    "• Use 'Browse for NCBI Database' option to locate it elsewhere"
                )
                return
            
            # Check conversion status
            if self.conversion_manager.is_converting(db_name):
                QMessageBox.information(
                    self,
                    "Conversion In Progress",
                    f"Database '{db_name}' is still being converted.\n\n"
                    "Please wait for the conversion to complete, or use BLAST search instead."
                )
                return
            
            if not self.conversion_manager.is_converted(db_name):
                # Ask user if they want to convert
                reply = QMessageBox.question(
                    self,
                    "Database Not Converted",
                    f"Database '{db_name}' needs to be converted to MMseqs2 format.\n\n"
                    "This will:\n"
                    "• Extract sequences from the BLAST database\n"
                    "• Convert to MMseqs2 format\n"
                    "• Take a few minutes\n\n"
                    "Would you like to start the conversion now?",
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    self.start_database_conversion(db_name)
                return
            
            # Get converted database path
            status = self.conversion_manager.get_database_status(db_name)
            database_path = status.get("converted_path")
            
            if not database_path or not os.path.exists(database_path):
                self.output_text.setText(
                    f"Error: Converted database not found at: {database_path}\n\n"
                    "Please try converting the database again."
                )
                return
                
        elif self.custom_ncbi_radio.isChecked():
            # Option 2: Browse for NCBI database in custom location
            blast_db_path = self.custom_ncbi_path.text().strip()
            if not blast_db_path:
                self.output_text.setText("Error: Please browse and select a BLAST database.")
                return
            
            # Check if database files exist
            if not os.path.exists(blast_db_path + ".phr"):
                self.output_text.setText(
                    f"Error: BLAST database files not found at:\n{blast_db_path}\n\n"
                    "Please ensure you selected the correct database file."
                )
                return
            
            # Extract database name from path
            db_name = os.path.basename(blast_db_path)
            custom_db_key = f"custom_{db_name}"
            
            # Check if already converted
            if not self.conversion_manager.is_converted(custom_db_key):
                reply = QMessageBox.question(
                    self,
                    "Convert Custom Database",
                    f"Convert BLAST database '{db_name}' to MMseqs2 format?\n\n"
                    f"Source: {blast_db_path}\n\n"
                    "This will take a few minutes.",
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    self.start_database_conversion(custom_db_key, blast_db_path)
                return
            
            # Get converted database path
            status = self.conversion_manager.get_database_status(custom_db_key)
            database_path = status.get("converted_path")
            
            if not database_path or not os.path.exists(database_path):
                self.output_text.setText(
                    f"Error: Converted database not found.\n\n"
                    "Please try converting again."
                )
                return
                
        else:
            # Option 3: Use existing MMseqs2 database
            database_path = self.custom_mmseqs_path.text().strip()
            if not database_path:
                self.output_text.setText("Error: Please browse and select a MMseqs2 database.")
                return
            
            if not os.path.exists(database_path):
                self.output_text.setText(f"Error: Database file not found:\n{database_path}")
                return
        
        # Get sensitivity setting
        sensitivity_text = self.sensitivity_combo.currentText()
        sensitivity = sensitivity_text.split(' - ')[0]
        
        # Disable button during search
        self.process_button.setEnabled(False)
        self.status_label.setText("Running MMseqs2 search... This may take a moment.")
        self.output_text.setText("Searching database with MMseqs2...\n\nPlease wait...")
        
        # Start MMseqs2 in background thread
        self.search_start_time = time.time()
        self.mmseqs_worker = MMseqsWorker(sequence, database_path, sensitivity)
        self.mmseqs_worker.finished.connect(self.on_mmseqs_finished)
        self.mmseqs_worker.error.connect(self.on_mmseqs_error)
        self.mmseqs_worker.start()
    
    def extract_stats_from_html(self, html_results):
        """Extract statistics from HTML results"""
        import re
        
        # Count hits
        hits_match = re.search(r'Found (\d+) alignment', html_results)
        total_hits = int(hits_match.group(1)) if hits_match else 0
        
        # Extract all E-values
        evalue_matches = re.findall(r'E-value:</span> <b[^>]*>([\d\.e\-+]+)</b>', html_results)
        best_evalue = min([float(e) for e in evalue_matches]) if evalue_matches else None
        
        # Extract all identity percentages
        identity_matches = re.findall(r'Identity:</span> <b[^>]*>([\d\.]+)%</b>', html_results)
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

    def on_mmseqs_finished(self, results_html, results_data):
        """Handle MMseqs2 results"""
        search_time = time.time() - self.search_start_time if self.search_start_time else 0
        
        # Store results for export and clustering
        self.current_results_html = results_html
        self.current_results_data = results_data
        self.current_query_info = {
            'query_name': self.current_sequence_metadata.get('id', 'query'),
            'query_length': str(len(self.input_text.toPlainText().strip())),
            'database': self.get_current_database_name(),
            'sensitivity': self.sensitivity_combo.currentText(),
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
    
    def on_mmseqs_error(self, error_msg):
        """Handle MMseqs2 errors"""
        self.summary_panel.hide()
        self.output_text.setPlainText(f"Error running MMseqs2:\n\n{error_msg}")
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
        database_path = self.current_database_path
        
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
            fasta_path = temp_manager.create_temp_fasta(final_hits, prefix='mmseqs_cluster_')
            
            # Step 5: Navigate to clustering page
            self.navigate_to_clustering.emit(fasta_path, clustering_params)
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Creating FASTA",
                f"Failed to create temporary FASTA file:\n\n{str(e)}"
            )
