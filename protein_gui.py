import sys
import subprocess
import tempfile
import os
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, QPushButton, QLabel, QComboBox, QHBoxLayout, QCheckBox, QLineEdit, QFileDialog, QGroupBox, QStackedWidget, QFrame, QGridLayout
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QPixmap
from Bio.Blast import NCBIXML
from Bio import SeqIO
from io import StringIO

class BLASTWorker(QThread):
    """Worker thread to run BLAST without freezing the GUI"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, sequence, database, use_remote=True, local_db_path=""):
        super().__init__()
        self.sequence = sequence
        self.database = database
        self.use_remote = use_remote
        self.local_db_path = local_db_path
    
    def run(self):
        try:
            # Create temporary files for input and output
            with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as query_file:
                query_file.write(f">query\n{self.sequence}\n")
                query_path = query_file.name
            
            output_path = tempfile.mktemp(suffix='.xml')
            
            # Run BLASTP command with XML output for better parsing
            # blastp_path = r'C:\Users\18329\NCBI\ncbi-blast-2.17.0+-x64-win64.tar\ncbi-blast-2.17.0+-x64-win64\ncbi-blast-2.17.0+\bin\blastp.exe'
            blastp_path = r'C:\Users\abbas\Downloads\ncbi-blast-2.17.0+-x64-win64.tar\ncbi-blast-2.17.0+-x64-win64\ncbi-blast-2.17.0+\bin\blastp.exe'
            
            # Build command based on remote vs local database
            cmd = [
                blastp_path,
                '-query', query_path,
                '-outfmt', '5',  # XML format for Biopython parsing
                '-max_target_seqs', '10',  # Limit to top 10 hits
                '-out', output_path
            ]
            
            if self.use_remote:
                cmd.extend(['-remote', '-db', self.database])
            else:
                # For local database, use the full path
                if self.local_db_path:
                    # If user specified a custom path
                    local_db = os.path.join(self.local_db_path, self.database)
                else:
                    # Use default local database directory
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    local_db = os.path.join(script_dir, 'blast_databases', self.database)
                
                cmd.extend(['-db', local_db])
            
            # Execute BLAST
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # Parse results with Biopython
            parsed_results = self.parse_blast_xml(output_path)
            
            # Cleanup
            os.unlink(query_path)
            os.unlink(output_path)
            
            self.finished.emit(parsed_results)
            
        except subprocess.CalledProcessError as e:
            self.error.emit(f"BLAST error: {e.stderr}")
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")
    
    def parse_blast_xml(self, xml_file_path):
        """Parse BLAST XML output using Biopython"""
        try:
            with open(xml_file_path, 'r') as result_handle:
                blast_records = NCBIXML.parse(result_handle)
                
                formatted_results = []
                formatted_results.append("=" * 80)
                formatted_results.append("BLASTP SEARCH RESULTS")
                formatted_results.append("=" * 80)
                
                for blast_record in blast_records:
                    formatted_results.append(f"\nQuery: {blast_record.query}")
                    formatted_results.append(f"Query Length: {blast_record.query_length} amino acids")
                    formatted_results.append(f"Database: {blast_record.database}")
                    formatted_results.append(f"Number of sequences in database: {blast_record.database_sequences:,}")
                    formatted_results.append("\n" + "-" * 80)
                    
                    if blast_record.alignments:
                        formatted_results.append(f"Found {len(blast_record.alignments)} significant alignments:")
                        formatted_results.append("-" * 80)
                        
                        for i, alignment in enumerate(blast_record.alignments, 1):
                            formatted_results.append(f"\n#{i}. {alignment.title}")
                            formatted_results.append(f"Length: {alignment.length} amino acids")
                            
                            # Get the best HSP (High-scoring Segment Pair)
                            if alignment.hsps:
                                hsp = alignment.hsps[0]  # Best HSP
                                
                                formatted_results.append(f"\nBest Hit Statistics:")
                                formatted_results.append(f"  Score: {hsp.score} bits")
                                formatted_results.append(f"  E-value: {hsp.expect:.2e}")
                                formatted_results.append(f"  Identity: {hsp.identities}/{hsp.align_length} ({hsp.identities/hsp.align_length*100:.1f}%)")
                                formatted_results.append(f"  Positives: {hsp.positives}/{hsp.align_length} ({hsp.positives/hsp.align_length*100:.1f}%)")
                                formatted_results.append(f"  Gaps: {hsp.gaps}/{hsp.align_length} ({hsp.gaps/hsp.align_length*100:.1f}%)")
                                
                                # Show alignment
                                formatted_results.append(f"\nAlignment (Query: {hsp.query_start}-{hsp.query_end}, Subject: {hsp.sbjct_start}-{hsp.sbjct_end}):")
                                formatted_results.append(f"Query: {hsp.query}")
                                formatted_results.append(f"       {hsp.match}")
                                formatted_results.append(f"Sbjct: {hsp.sbjct}")
                                
                            formatted_results.append("-" * 60)
                    else:
                        formatted_results.append("No significant alignments found.")
                
                return "\n".join(formatted_results)
                
        except Exception as e:
            return f"Error parsing BLAST results: {str(e)}"


class HomePage(QWidget):
    """Home page widget with service selection"""
    service_selected = pyqtSignal(str)  # Signal to emit when a service is selected
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the home page UI"""
        layout = QVBoxLayout()
        layout.setSpacing(30)
        layout.setContentsMargins(50, 50, 50, 50)
        
        # Welcome section
        welcome_frame = QFrame()
        welcome_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        welcome_layout = QVBoxLayout(welcome_frame)
        
        # Title
        title_label = QLabel("Sen Lab - Protein Analysis Suite")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50; background: transparent;")
        
        # Subtitle
        subtitle_label = QLabel("Select a bioinformatics tool to analyze your protein sequences")
        subtitle_font = QFont()
        subtitle_font.setPointSize(12)
        subtitle_label.setFont(subtitle_font)
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet("color: #7f8c8d; background: transparent; margin-top: 10px;")
        
        welcome_layout.addWidget(title_label)
        welcome_layout.addWidget(subtitle_label)
        
        # Services section
        services_label = QLabel("Available Services:")
        services_font = QFont()
        services_font.setPointSize(16)
        services_font.setBold(True)
        services_label.setFont(services_font)
        services_label.setStyleSheet("color: #34495e; margin-top: 20px;")
        
        # Services grid
        services_frame = QFrame()
        services_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 2px solid #ecf0f1;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        services_layout = QGridLayout(services_frame)
        
        # BLAST service button
        blast_button = QPushButton("BLASTP Search")
        blast_button.setMinimumHeight(80)
        blast_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
        blast_button.clicked.connect(lambda: self.service_selected.emit("blast"))
        
        # BLAST description
        blast_desc = QLabel("Search protein sequences against NCBI databases\nto find homologous proteins and functional insights")
        blast_desc.setWordWrap(True)
        blast_desc.setStyleSheet("color: #7f8c8d; margin-top: 10px; background: transparent;")
        blast_desc.setAlignment(Qt.AlignCenter)
        
        # Add BLAST service to grid
        blast_container = QWidget()
        blast_container_layout = QVBoxLayout(blast_container)
        blast_container_layout.addWidget(blast_button)
        blast_container_layout.addWidget(blast_desc)
        
        services_layout.addWidget(blast_container, 0, 0)
        
        # Placeholder for future services
        placeholder_button = QPushButton("More Tools Coming Soon...")
        placeholder_button.setMinimumHeight(80)
        placeholder_button.setEnabled(False)
        placeholder_button.setStyleSheet("""
            QPushButton {
                background-color: #bdc3c7;
                color: #7f8c8d;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
            }
        """)
        
        placeholder_desc = QLabel("Additional bioinformatics tools\nwill be added in future updates")
        placeholder_desc.setWordWrap(True)
        placeholder_desc.setStyleSheet("color: #bdc3c7; margin-top: 10px; background: transparent;")
        placeholder_desc.setAlignment(Qt.AlignCenter)
        
        placeholder_container = QWidget()
        placeholder_container_layout = QVBoxLayout(placeholder_container)
        placeholder_container_layout.addWidget(placeholder_button)
        placeholder_container_layout.addWidget(placeholder_desc)
        
        services_layout.addWidget(placeholder_container, 0, 1)
        
        # Add everything to main layout
        layout.addWidget(welcome_frame)
        layout.addWidget(services_label)
        layout.addWidget(services_frame)
        layout.addStretch()  # Push content to top
        
        self.setLayout(layout)


class BLASTPage(QWidget):
    """BLAST analysis page widget"""
    back_requested = pyqtSignal()  # Signal to go back to home page
    
    def __init__(self):
        super().__init__()
        self.blast_worker = None
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
        db_layout = QHBoxLayout()
        db_label = QLabel("Database:")
        self.db_combo = QComboBox()
        self.db_combo.addItems(['swissprot', 'nr', 'pdb'])
        db_layout.addWidget(db_label)
        db_layout.addWidget(self.db_combo)
        db_layout.addStretch()
        
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
        
        self.output_label = QLabel("Results:")
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        
        # Add widgets to layout
        layout.addLayout(header_layout)
        layout.addWidget(self.input_label)
        layout.addWidget(self.input_text)
        layout.addWidget(db_group)
        layout.addWidget(self.process_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.output_label)
        layout.addWidget(self.output_text)
        
        self.setLayout(layout)
    
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
        database = self.db_combo.currentText()
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
        self.blast_worker = BLASTWorker(sequence, database, use_remote, local_db_path)
        self.blast_worker.finished.connect(self.on_blast_finished)
        self.blast_worker.error.connect(self.on_blast_error)
        self.blast_worker.start()
    
    def on_blast_finished(self, results):
        """Handle BLAST results"""
        self.output_text.setText(results)
        self.status_label.setText("Search complete!")
        self.process_button.setEnabled(True)
    
    def on_blast_error(self, error_msg):
        """Handle BLAST errors"""
        self.output_text.setText(f"Error running BLAST:\n\n{error_msg}")
        self.status_label.setText("Error occurred")
        self.process_button.setEnabled(True)


class ProteinGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sen Lab - Protein Analysis Suite")
        self.setGeometry(100, 100, 900, 700)
        
        # Set application style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8f9fa;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #dee2e6;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        
        # Create central widget and stacked layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create stacked widget for page management
        self.stacked_widget = QStackedWidget()
        
        # Create and add pages
        self.home_page = HomePage()
        self.blast_page = BLASTPage()
        
        # Add pages to stack
        self.stacked_widget.addWidget(self.home_page)
        self.stacked_widget.addWidget(self.blast_page)
        
        # Connect signals
        self.home_page.service_selected.connect(self.show_service_page)
        self.blast_page.back_requested.connect(self.show_home_page)
        
        # Add stacked widget to main layout
        main_layout.addWidget(self.stacked_widget)
        
        # Start with home page
        self.show_home_page()
    
    def show_home_page(self):
        """Show the home page"""
        self.stacked_widget.setCurrentWidget(self.home_page)
        self.setWindowTitle("Sen Lab - Protein Analysis Suite")
    
    def show_service_page(self, service):
        """Show the requested service page"""
        if service == "blast":
            self.stacked_widget.setCurrentWidget(self.blast_page)
            self.setWindowTitle("Sen Lab - BLASTP Search")
        # Add more services here in the future

def main():
    app = QApplication(sys.argv)
    window = ProteinGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()