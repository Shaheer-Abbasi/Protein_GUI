import sys
import subprocess
import tempfile
import os
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, QPushButton, QLabel, QComboBox, QHBoxLayout, QCheckBox, QLineEdit, QFileDialog, QGroupBox, QStackedWidget, QFrame, QGridLayout, QCompleter
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QStringListModel, QSortFilterProxyModel
from PyQt5.QtGui import QFont, QPixmap
from Bio.Blast import NCBIXML
from Bio import SeqIO
from io import StringIO

# Comprehensive NCBI BLAST databases with descriptions
NCBI_DATABASES = {
    # Protein databases
    'nr': 'Non-redundant protein sequences (all proteins)',
    'refseq_protein': 'Reference proteins (RefSeq)',
    'swissprot': 'UniProtKB/Swiss-Prot (curated protein sequences)',
    'pdb': 'Protein Data Bank proteins',
    'env_nr': 'Non-redundant protein sequences from environmental samples',
    'tsa_nr': 'Non-redundant protein sequences from transcriptome shotgun assembly',
    'pataa': 'Patent protein sequences',
    'pdbaa': 'PDB protein sequences (deprecated, use pdb)',
    
    # Nucleotide databases  
    'nt': 'Nucleotide collection (nt)',
    'refseq_rna': 'Reference RNA sequences',
    'refseq_genomic': 'Reference genomic sequences',
    'chromosome': 'RefSeq chromosome sequences',
    'tsa_nt': 'Transcriptome Shotgun Assembly nucleotides',
    'env_nt': 'Environmental nucleotide sequences',
    'wgs': 'Whole-genome shotgun sequences',
    'gss': 'Genome survey sequences',
    'est': 'Expressed sequence tags',
    'est_human': 'Human ESTs',
    'est_mouse': 'Mouse ESTs',
    'est_others': 'ESTs from organisms other than human and mouse',
    'htgs': 'High throughput genomic sequences',
    'patnt': 'Patent nucleotide sequences',
    'pdbnt': 'PDB nucleotide sequences',
    'dbsts': 'Database of sequence tagged sites',
    'landmark': 'Landmark database for BLAST',
    '16S_ribosomal_RNA': '16S ribosomal RNA sequences',
    'ITS_RefSeq_Fungi': 'Internal transcribed spacer region, fungi',
    '18S_fungal_sequences': '18S ribosomal RNA sequences, fungi',
    '28S_fungal_sequences': '28S ribosomal RNA sequences, fungi',
    'Betacoronavirus': 'Betacoronavirus sequences',
    
    # Organism-specific databases
    'ref_euk_rep_genomes': 'Representative eukaryotic genomes',
    'ref_prok_rep_genomes': 'Representative prokaryotic genomes',
    'ref_viroids_rep_genomes': 'Representative viroid genomes',
    'ref_viruses_rep_genomes': 'Representative viral genomes',
    
    # Specialized databases
    'cdd': 'Conserved Domain Database',
    'smart': 'Simple Modular Architecture Research Tool',
    'pfam': 'Protein families database',
    'kog': 'EuKaryotic Orthologous Groups',
    'cog': 'Clusters of Orthologous Groups',
    'prk': 'Protein clusters',
    'tigr': 'TIGRFAMs database',
    
    # Human genome databases
    'human_genomic': 'Human genomic sequences',
    'human_genome': 'Human genome',
    'mouse_genomic': 'Mouse genomic sequences',
    'mouse_genome': 'Mouse genome'
}

# Categories for better organization
DATABASE_CATEGORIES = {
    'Protein Databases': [
        'nr', 'refseq_protein', 'swissprot', 'pdb', 'env_nr', 'tsa_nr', 'pataa'
    ],
    'Nucleotide Databases': [
        'nt', 'refseq_rna', 'refseq_genomic', 'chromosome', 'tsa_nt', 'env_nt', 'wgs'
    ],
    'Specialized Sequences': [
        '16S_ribosomal_RNA', 'ITS_RefSeq_Fungi', '18S_fungal_sequences', 
        '28S_fungal_sequences', 'Betacoronavirus'
    ],
    'Genome Collections': [
        'ref_euk_rep_genomes', 'ref_prok_rep_genomes', 'ref_viroids_rep_genomes', 
        'ref_viruses_rep_genomes', 'human_genomic', 'mouse_genomic'
    ],
    'Domain/Family Databases': [
        'cdd', 'smart', 'pfam', 'kog', 'cog', 'prk', 'tigr'
    ],
    'Legacy/Other': [
        'est', 'est_human', 'est_mouse', 'est_others', 'htgs', 'patnt', 
        'pdbnt', 'dbsts', 'landmark', 'gss', 'pdbaa'
    ]
}


class SearchableComboBox(QComboBox):
    """A combobox with search/filter functionality"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        print("Creating SearchableComboBox...")
        
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        
        # Store all items for filtering
        self.all_items = []
        self.all_data = {}
        self._initializing = True
        
        # Create completer for auto-completion
        self.completer = QCompleter(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.setCompleter(self.completer)
        
        print("SearchableComboBox created successfully")
    
    def addItemWithData(self, text, data=None):
        """Add item with optional data"""
        try:
            self.all_items.append(text)
            if data:
                self.all_data[text] = data
            super().addItem(text)
        except Exception as e:
            print(f"Error adding item {text}: {e}")
    
    def setItems(self, items_dict):
        """Set items from dictionary {text: data}"""
        print(f"Setting {len(items_dict)} database items...")
        
        try:
            # Temporarily block signals during initialization
            self.blockSignals(True)
            
            self.clear()
            self.all_items.clear()
            self.all_data.clear()
            
            # Add items more safely
            for i, (text, data) in enumerate(items_dict.items()):
                if i % 10 == 0:  # Progress indicator
                    print(f"  Adding item {i+1}/{len(items_dict)}: {text}")
                
                self.all_items.append(text)
                self.all_data[text] = data
                super().addItem(text)
            
            print("Database items added successfully")
            
            # Update completer
            self.completer.setModel(QStringListModel(self.all_items))
            print("Completer model updated")
            
            # Re-enable signals and connect filtering
            self.blockSignals(False)
            self._initializing = False
            
            # Connect signals for filtering after initialization
            self.lineEdit().textChanged.connect(self.filter_items)
            print("Signals connected")
            
        except Exception as e:
            print(f"Error in setItems: {e}")
            import traceback
            traceback.print_exc()
    
    def filter_items(self, text):
        """Filter items based on text input"""
        # Skip filtering during initialization
        if getattr(self, '_initializing', False):
            return
            
        try:
            if not text:
                # Show all items if no filter text
                self.clear()
                for item in self.all_items:
                    super().addItem(item)
            else:
                # Filter items that contain the text (case-insensitive)
                self.clear()
                filtered_items = [item for item in self.all_items 
                                if text.lower() in item.lower() or 
                                   text.lower() in self.all_data.get(item, '').lower()]
                for item in filtered_items:
                    super().addItem(item)
        except Exception as e:
            print(f"Error in filter_items: {e}")
    
    def getCurrentData(self):
        """Get data for currently selected item"""
        current_text = self.currentText()
        return self.all_data.get(current_text, current_text)

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


class MMseqsWorker(QThread):
    """Worker thread to run MMseqs2 search without freezing the GUI"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, sequence, database_path, sensitivity="sensitive"):
        super().__init__()
        self.sequence = sequence
        self.database_path = database_path
        self.sensitivity = sensitivity
    
    def run(self):
        try:
            # Create temporary directory for MMseqs2 work
            temp_dir = tempfile.mkdtemp(prefix='mmseqs_')
            
            # Create query FASTA file
            query_fasta = os.path.join(temp_dir, 'query.fasta')
            with open(query_fasta, 'w') as f:
                f.write(f">query\n{self.sequence}\n")
            
            # MMseqs2 executable path
            # mmseqs_path = r'C:\Users\abbas\Downloads\mmseqs-win64\mmseqs\bin\mmseqs.exe'
            mmseqs_path = r'C:\Users\18329\MMSeqs2\mmseqs-win64\mmseqs\bin\mmseqs.exe'
            
            # Create MMseqs2 database from query
            query_db = os.path.join(temp_dir, 'queryDB')
            result_db = os.path.join(temp_dir, 'resultDB')
            tmp_folder = os.path.join(temp_dir, 'tmp')
            os.makedirs(tmp_folder, exist_ok=True)
            
            # Step 1: Create query database
            cmd_createdb = [mmseqs_path, 'createdb', query_fasta, query_db]
            result = subprocess.run(cmd_createdb, capture_output=True, text=True)
            if result.returncode != 0:
                self.error.emit(f"Error creating query database:\n{result.stderr}")
                return
            
            # Step 2: Run search (Windows-compatible, no bash scripts)
            cmd_search = [
                mmseqs_path, 'search',
                query_db,
                self.database_path,
                result_db,
                tmp_folder,
                '-s', self.get_sensitivity_value()
            ]
            
            result = subprocess.run(cmd_search, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                self.error.emit(f"MMseqs2 search error:\n{result.stderr}\n\nStdout:\n{result.stdout}")
                return
            
            # Step 3: Convert results to readable format
            output_file = os.path.join(temp_dir, 'results.m8')
            cmd_convertalis = [
                mmseqs_path, 'convertalis',
                query_db,
                self.database_path,
                result_db,
                output_file,
                '--format-output', 'query,target,pident,alnlen,mismatch,gapopen,qstart,qend,tstart,tend,evalue,bits'
            ]
            
            result = subprocess.run(cmd_convertalis, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                self.error.emit(f"Error converting results:\n{result.stderr}")
                return
            
            # Read and format results
            formatted_results = self.format_results(output_file, result.stdout, result.stderr)
            
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            self.finished.emit(formatted_results)
            
        except subprocess.TimeoutExpired:
            self.error.emit("MMseqs2 search timed out after 5 minutes.")
        except Exception as e:
            import traceback
            self.error.emit(f"Error: {str(e)}\n\n{traceback.format_exc()}")
    
    def get_sensitivity_value(self):
        """Convert sensitivity name to MMseqs2 parameter value"""
        sensitivity_map = {
            "fast": "4",
            "sensitive": "5.7",
            "more-sensitive": "7",
            "very-sensitive": "8.5"
        }
        return sensitivity_map.get(self.sensitivity, "5.7")
    
    def format_results(self, results_file, stdout, stderr):
        """Format MMseqs2 results for display"""
        formatted = []
        formatted.append("=" * 80)
        formatted.append("MMSEQS2 SEARCH RESULTS")
        formatted.append("=" * 80)
        formatted.append("")
        
        # Add any stdout/stderr information
        if stdout.strip():
            formatted.append("Search Information:")
            formatted.append(stdout.strip())
            formatted.append("")
        
        # Read and parse results file
        try:
            if os.path.exists(results_file) and os.path.getsize(results_file) > 0:
                with open(results_file, 'r') as f:
                    lines = f.readlines()
                
                if lines:
                    formatted.append(f"Found {len(lines)} alignment(s)")
                    formatted.append("-" * 80)
                    formatted.append("")
                    
                    # Header
                    formatted.append("Columns: Query | Target | Identity% | AlnLen | Mismatch | GapOpen | QStart | QEnd | TStart | TEnd | E-value | BitScore")
                    formatted.append("-" * 80)
                    
                    for i, line in enumerate(lines[:20], 1):  # Limit to top 20 hits
                        formatted.append(f"\n#{i}. {line.strip()}")
                        
                        # Parse the tab-separated values for better formatting
                        fields = line.strip().split('\t')
                        if len(fields) >= 12:
                            formatted.append(f"   Target: {fields[1]}")
                            formatted.append(f"   Identity: {fields[2]}%")
                            formatted.append(f"   Alignment Length: {fields[3]}")
                            formatted.append(f"   E-value: {fields[10]}")
                            formatted.append(f"   Bit Score: {fields[11]}")
                    
                    if len(lines) > 20:
                        formatted.append(f"\n... and {len(lines) - 20} more hits (showing top 20)")
                else:
                    formatted.append("No significant alignments found.")
            else:
                formatted.append("No results file generated or file is empty.")
                
        except Exception as e:
            formatted.append(f"Error reading results: {str(e)}")
        
        formatted.append("")
        formatted.append("=" * 80)
        
        return "\n".join(formatted)


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
        
        # MMseqs2 service button
        mmseqs_button = QPushButton("MMseqs2 Search")
        mmseqs_button.setMinimumHeight(80)
        mmseqs_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:pressed {
                background-color: #7d3c98;
            }
        """)
        mmseqs_button.clicked.connect(lambda: self.service_selected.emit("mmseqs"))
        
        # MMseqs2 description
        mmseqs_desc = QLabel("Fast and sensitive protein sequence searching\nusing MMseqs2 for homology detection")
        mmseqs_desc.setWordWrap(True)
        mmseqs_desc.setStyleSheet("color: #7f8c8d; margin-top: 10px; background: transparent;")
        mmseqs_desc.setAlignment(Qt.AlignCenter)
        
        # Add MMseqs2 service to grid
        mmseqs_container = QWidget()
        mmseqs_container_layout = QVBoxLayout(mmseqs_container)
        mmseqs_container_layout.addWidget(mmseqs_button)
        mmseqs_container_layout.addWidget(mmseqs_desc)
        
        services_layout.addWidget(mmseqs_container, 0, 1)
        
        # Placeholder for future services (moved to row 1)
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
        
        services_layout.addWidget(placeholder_container, 1, 0, 1, 2)  # Span 2 columns
        
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
        self.mmseqs_page = MMseqsPage()
        
        # Add pages to stack
        self.stacked_widget.addWidget(self.home_page)
        self.stacked_widget.addWidget(self.blast_page)
        self.stacked_widget.addWidget(self.mmseqs_page)
        
        # Connect signals
        self.home_page.service_selected.connect(self.show_service_page)
        self.blast_page.back_requested.connect(self.show_home_page)
        self.mmseqs_page.back_requested.connect(self.show_home_page)
        
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
        elif service == "mmseqs":
            self.stacked_widget.setCurrentWidget(self.mmseqs_page)
            self.setWindowTitle("Sen Lab - MMseqs2 Search")
        # Add more services here in the future

def main():
    try:
        app = QApplication(sys.argv)
        window = ProteinGUI()
        window.show()
        sys.exit(app.exec_())
        
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()