import os
import time
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel, QComboBox, QHBoxLayout, QCheckBox, QLineEdit, QFileDialog, QGroupBox
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from core.db_definitions import NCBI_DATABASES
from core.blast_worker import BLASTWorker

class BLASTPage(QWidget):
    """BLAST analysis page widget"""
    back_requested = pyqtSignal()  # Signal to go back to home page
    
    def __init__(self):
        super().__init__()
        self.blast_worker = None
        self.search_start_time = None
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
        
        # Input section
        self.input_label = QLabel("Enter protein sequence:")
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Paste your amino acid sequence here (single letter codes)...")
        self.input_text.setMaximumHeight(100)
        
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
        
        self.output_label = QLabel("Results:")
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setAcceptRichText(True)  # Enable HTML rendering
        
        # Add widgets to layout
        layout.addLayout(header_layout)
        layout.addWidget(self.input_label)
        layout.addWidget(self.input_text)
        layout.addWidget(db_group)
        layout.addWidget(self.process_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.summary_panel)  # Add summary panel
        layout.addWidget(self.output_label)
        layout.addWidget(self.output_text)
        
        self.setLayout(layout)
    
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
    
    def on_blast_finished(self, results):
        """Handle BLAST results"""
        search_time = time.time() - self.search_start_time if self.search_start_time else 0
        
        # Extract statistics and update summary panel
        total_hits, best_evalue, avg_identity = self.extract_stats_from_html(results)
        self.update_summary_panel(total_hits, best_evalue, avg_identity, search_time)
        
        # Display HTML results
        self.output_text.setHtml(results)
        self.status_label.setText("Search complete!")
        self.process_button.setEnabled(True)
    
    def on_blast_error(self, error_msg):
        """Handle BLAST errors"""
        self.summary_panel.hide()
        self.output_text.setPlainText(f"Error running BLAST:\n\n{error_msg}")
        self.status_label.setText("Error occurred")
        self.process_button.setEnabled(True)