import sys
import subprocess
import tempfile
import os
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, QPushButton, QLabel, QComboBox, QHBoxLayout, QCheckBox, QLineEdit, QFileDialog, QGroupBox
from PyQt5.QtCore import QThread, pyqtSignal
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
            blastp_path = r'C:\Users\18329\NCBI\ncbi-blast-2.17.0+-x64-win64.tar\ncbi-blast-2.17.0+-x64-win64\ncbi-blast-2.17.0+\bin\blastp.exe'
            
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


class ProteinGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sen Lab - Protein Sequence Analysis Tool")
        self.setGeometry(100, 100, 800, 600)
        self.blast_worker = None
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create widgets
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
        self.process_button.clicked.connect(self.run_blast)
        
        self.status_label = QLabel("Ready")
        
        self.output_label = QLabel("Results:")
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        
        # Add widgets to layout
        layout.addWidget(self.input_label)
        layout.addWidget(self.input_text)
        layout.addWidget(db_group)
        layout.addWidget(self.process_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.output_label)
        layout.addWidget(self.output_text)
    
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

def main():
    app = QApplication(sys.argv)
    window = ProteinGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()