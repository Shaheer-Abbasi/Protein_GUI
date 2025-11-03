import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel, QComboBox, QHBoxLayout, QLineEdit, QFileDialog, QGroupBox
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFont

from core.mmseqs_runner import MMseqsWorker


class MMseqsPage(QWidget):
    """MMseqs2 analysis page widget"""
    back_requested = pyqtSignal()  # Signal to go back to home page
    
    def __init__(self):
        super().__init__()
        self.mmseqs_worker = None
        self.init_ui()
    
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
        
        # Input section
        self.input_label = QLabel("Enter protein sequence:")
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Paste your amino acid sequence here (single letter codes)...")
        self.input_text.setMaximumHeight(100)
        
        # Database and options selection group
        options_group = QGroupBox("Search Options")
        options_group_layout = QVBoxLayout()
        
        # Database path
        db_layout = QHBoxLayout()
        db_label = QLabel("Database Path:")
        self.db_path = QLineEdit()
        self.db_path.setPlaceholderText("Path to MMseqs2 database (required)")
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_database_path)
        
        db_layout.addWidget(db_label)
        db_layout.addWidget(self.db_path)
        db_layout.addWidget(self.browse_button)
        
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
        info_label = QLabel("ℹ️ MMseqs2 performs fast and sensitive protein sequence searches. Ensure you have a pre-built MMseqs2 database.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #5d6d7e; font-style: italic; padding: 5px; background-color: #e8f4f8; border-radius: 3px; margin-top: 5px;")
        
        # Add to group
        options_group_layout.addLayout(db_layout)
        options_group_layout.addLayout(sensitivity_layout)
        options_group_layout.addWidget(info_label)
        options_group.setLayout(options_group_layout)
        
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
        
        self.output_label = QLabel("Results:")
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        
        # Add widgets to layout
        layout.addLayout(header_layout)
        layout.addWidget(self.input_label)
        layout.addWidget(self.input_text)
        layout.addWidget(options_group)
        layout.addWidget(self.process_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.output_label)
        layout.addWidget(self.output_text)
        
        self.setLayout(layout)
    
    def browse_database_path(self):
        """Open file dialog to select database file"""
        database_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select MMseqs2 Database File",
            "",
            "All Files (*)"
        )
        if database_file:
            self.db_path.setText(database_file)
    
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
        
        # Check database path
        database_path = self.db_path.text().strip()
        if not database_path:
            self.output_text.setText("Error: Please specify a database path.")
            return
        
        # Check if pointing to FASTA file instead of MMseqs2 database
        if database_path.endswith(('.fasta', '.fa', '.faa', '.fasta.gz', '.fa.gz', '.faa.gz')):
            self.output_text.setText(
                "Error: You selected a FASTA file, but MMseqs2 requires a pre-built database.\n\n"
                "To create an MMseqs2 database from your FASTA file:\n\n"
                "1. Open PowerShell/Command Prompt\n"
                "2. Navigate to: C:\\Users\\abbas\\Downloads\\mmseqs-win64\\mmseqs\\bin\n"
                "3. Run: mmseqs createdb <path_to_fasta> <output_db_name>\n\n"
                "Example:\n"
                f"  mmseqs createdb \"{database_path}\" swissprot_db\n\n"
                "Then use the database path (without extension) in this field."
            )
            return
        
        if not os.path.exists(database_path):
            self.output_text.setText(f"Error: Database file not found: {database_path}")
            return
        
        # Get sensitivity setting
        sensitivity_text = self.sensitivity_combo.currentText()
        sensitivity = sensitivity_text.split(' - ')[0]
        
        # Disable button during search
        self.process_button.setEnabled(False)
        self.status_label.setText("Running MMseqs2 search... This may take a moment.")
        self.output_text.setText("Searching database with MMseqs2...\n\nPlease wait...")
        
        # Start MMseqs2 in background thread
        self.mmseqs_worker = MMseqsWorker(sequence, database_path, sensitivity)
        self.mmseqs_worker.finished.connect(self.on_mmseqs_finished)
        self.mmseqs_worker.error.connect(self.on_mmseqs_error)
        self.mmseqs_worker.start()
    
    def on_mmseqs_finished(self, results):
        """Handle MMseqs2 results"""
        self.output_text.setText(results)
        self.status_label.setText("Search complete!")
        self.process_button.setEnabled(True)
    
    def on_mmseqs_error(self, error_msg):
        """Handle MMseqs2 errors"""
        self.output_text.setText(f"Error running MMseqs2:\n\n{error_msg}")
        self.status_label.setText("Error occurred")
        self.process_button.setEnabled(True)
