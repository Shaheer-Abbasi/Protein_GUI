"""Nucleotide search dialog for NCBI GenBank database search"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QListWidget, QListWidgetItem,
                             QTextEdit, QMessageBox, QProgressBar, QGroupBox,
                             QComboBox)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont

from utils.ncbi_api import NCBIClient, NCBIAPIError


class NucleotideSearchWorker(QThread):
    """Worker thread for NCBI API calls to prevent UI freezing"""
    finished = pyqtSignal(list)  # List of search results
    sequence_fetched = pyqtSignal(dict)  # Single sequence result
    error = pyqtSignal(str)  # Error message
    
    def __init__(self, search_term: str, search_type: str):
        super().__init__()
        self.search_term = search_term
        self.search_type = search_type  # 'keyword', 'gene', or 'accession'
        self.client = NCBIClient()
    
    def run(self):
        try:
            if self.search_type == 'accession':
                # Direct lookup by accession
                result = self.client.get_sequence_by_accession(self.search_term)
                self.sequence_fetched.emit(result)
            elif self.search_type == 'gene':
                # Search by gene name
                results = self.client.search_by_gene(self.search_term, limit=25)
                self.finished.emit(results)
            else:
                # General keyword search
                results = self.client.search_nucleotide(self.search_term, limit=25)
                self.finished.emit(results)
        except NCBIAPIError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Unexpected error: {str(e)}")


class SequenceFetchWorker(QThread):
    """Worker thread to fetch a single sequence"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, accession: str):
        super().__init__()
        self.accession = accession
        self.client = NCBIClient()
    
    def run(self):
        try:
            result = self.client.get_sequence_by_accession(self.accession)
            self.finished.emit(result)
        except NCBIAPIError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Unexpected error: {str(e)}")


class NucleotideSearchDialog(QDialog):
    """
    Dialog for searching nucleotide sequences in NCBI GenBank
    
    Features:
    - Search by gene name, keyword, or accession
    - Non-blocking API calls (uses QThread)
    - Results preview
    - Sequence selection and loading
    """
    
    sequence_selected = pyqtSignal(str, dict)  # (sequence, metadata)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Nucleotide Database (NCBI GenBank)")
        self.resize(750, 650)
        
        self.search_results = []
        self.selected_sequence = None
        self.search_worker = None
        self.fetch_worker = None
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        
        # Search section
        search_group = QGroupBox("Search Options")
        search_layout = QVBoxLayout()
        
        # Search type selection
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Search by:"))
        
        self.search_type_combo = QComboBox()
        self.search_type_combo.addItems([
            "Gene Name",
            "Keyword/Description",
            "Accession Number"
        ])
        self.search_type_combo.currentIndexChanged.connect(self._on_search_type_changed)
        type_layout.addWidget(self.search_type_combo)
        type_layout.addStretch()
        
        search_layout.addLayout(type_layout)
        
        # Search input
        input_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter gene name (e.g., BRCA1, insulin)")
        self.search_input.returnPressed.connect(self._perform_search)
        
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._perform_search)
        self.search_button.setDefault(True)
        self.search_button.setStyleSheet("""
            QPushButton {
                background-color: #1e8449;
                color: white;
                padding: 8px 16px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #196f3d;
            }
        """)
        
        input_layout.addWidget(self.search_input)
        input_layout.addWidget(self.search_button)
        search_layout.addLayout(input_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.hide()
        search_layout.addWidget(self.progress_bar)
        
        # Examples
        self.examples_label = QLabel(
            '<i>Examples: "BRCA1", "insulin Homo sapiens", "cytochrome oxidase"</i>'
        )
        self.examples_label.setStyleSheet("color: #666;")
        search_layout.addWidget(self.examples_label)
        
        search_group.setLayout(search_layout)
        layout.addWidget(search_group)
        
        # Results section
        results_group = QGroupBox("Search Results")
        results_layout = QVBoxLayout()
        
        self.results_list = QListWidget()
        self.results_list.itemSelectionChanged.connect(self._on_result_selected)
        self.results_list.itemDoubleClicked.connect(self._fetch_selected_sequence)
        results_layout.addWidget(self.results_list)
        
        # Result count and fetch button
        result_action_layout = QHBoxLayout()
        self.result_count_label = QLabel("No search performed yet")
        self.result_count_label.setStyleSheet("color: #666; font-style: italic;")
        result_action_layout.addWidget(self.result_count_label)
        result_action_layout.addStretch()
        
        self.fetch_button = QPushButton("Fetch Sequence")
        self.fetch_button.setEnabled(False)
        self.fetch_button.clicked.connect(self._fetch_selected_sequence)
        self.fetch_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 6px 12px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        result_action_layout.addWidget(self.fetch_button)
        
        results_layout.addLayout(result_action_layout)
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        # Preview section
        preview_group = QGroupBox("Sequence Preview")
        preview_layout = QVBoxLayout()
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(120)
        self.preview_text.setFont(QFont("Courier New", 9))
        preview_layout.addWidget(self.preview_text)
        
        self.sequence_info_label = QLabel("")
        preview_layout.addWidget(self.sequence_info_label)
        
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.load_button = QPushButton("Load Sequence")
        self.load_button.clicked.connect(self._load_sequence)
        self.load_button.setEnabled(False)
        self.load_button.setStyleSheet("""
            QPushButton {
                background-color: #1e8449;
                color: white;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 13px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #196f3d;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _on_search_type_changed(self, index):
        """Update placeholder text based on search type"""
        if index == 0:  # Gene Name
            self.search_input.setPlaceholderText("Enter gene name (e.g., BRCA1, insulin)")
            self.examples_label.setText('<i>Examples: "BRCA1", "TP53", "hemoglobin beta"</i>')
        elif index == 1:  # Keyword
            self.search_input.setPlaceholderText("Enter keywords (e.g., insulin Homo sapiens)")
            self.examples_label.setText('<i>Examples: "insulin mRNA Homo sapiens", "16S ribosomal RNA E. coli"</i>')
        else:  # Accession
            self.search_input.setPlaceholderText("Enter accession number (e.g., NM_001301717)")
            self.examples_label.setText('<i>Examples: "NM_001301717", "NC_000001", "M12345"</i>')
    
    def _perform_search(self):
        """Perform nucleotide search"""
        search_term = self.search_input.text().strip()
        
        if not search_term:
            QMessageBox.warning(
                self,
                "Empty Search",
                "Please enter a gene name, keyword, or accession number to search."
            )
            return
        
        # Determine search type
        index = self.search_type_combo.currentIndex()
        if index == 0:
            search_type = 'gene'
        elif index == 1:
            search_type = 'keyword'
        else:
            search_type = 'accession'
        
        # Clear previous results
        self.results_list.clear()
        self.preview_text.clear()
        self.sequence_info_label.clear()
        self.load_button.setEnabled(False)
        self.fetch_button.setEnabled(False)
        self.search_results = []
        self.selected_sequence = None
        
        # Show progress
        self.progress_bar.show()
        self.search_button.setEnabled(False)
        self.result_count_label.setText("Searching NCBI GenBank...")
        
        # Start worker thread
        self.search_worker = NucleotideSearchWorker(search_term, search_type)
        self.search_worker.finished.connect(self._on_search_complete)
        self.search_worker.sequence_fetched.connect(self._on_sequence_fetched)
        self.search_worker.error.connect(self._on_search_error)
        self.search_worker.start()
    
    def _on_search_complete(self, results):
        """Handle search completion"""
        self.progress_bar.hide()
        self.search_button.setEnabled(True)
        
        if not results:
            self.result_count_label.setText("No results found")
            QMessageBox.information(
                self,
                "No Results",
                "No nucleotide sequences found matching your search.\n\n"
                "Try different keywords or check the spelling."
            )
            return
        
        self.search_results = results
        self.result_count_label.setText(f"Found {len(results)} result(s) - double-click to fetch sequence")
        
        # Populate results list
        for seq_info in results:
            accession = seq_info.get('accession', 'Unknown')
            title = seq_info.get('title', 'Unknown')
            organism = seq_info.get('organism', 'Unknown')
            length = seq_info.get('length', 0)
            mol_type = seq_info.get('mol_type', '')
            
            # Truncate title if too long
            if len(title) > 70:
                title = title[:67] + "..."
            
            item_text = f"{accession} ({length:,} bp)\n    {title}\n    {organism}"
            if mol_type:
                item_text += f" | {mol_type}"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, seq_info)
            self.results_list.addItem(item)
    
    def _on_sequence_fetched(self, result):
        """Handle direct accession lookup result"""
        self.progress_bar.hide()
        self.search_button.setEnabled(True)
        
        self.selected_sequence = result
        
        # Show sequence in preview
        sequence = result.get('sequence', '')
        if sequence:
            preview = sequence[:300]
            if len(sequence) > 300:
                preview += f"\n... ({len(sequence) - 300:,} more nucleotides)"
            
            self.preview_text.setPlainText(preview)
            
            accession = result.get('accession', 'Unknown')
            organism = result.get('organism', 'Unknown')
            mol_type = result.get('mol_type', 'Unknown')
            
            self.sequence_info_label.setText(
                f"<b>Accession:</b> {accession} | "
                f"<b>Length:</b> {len(sequence):,} bp | "
                f"<b>Organism:</b> {organism} | "
                f"<b>Type:</b> {mol_type}"
            )
            
            self.load_button.setEnabled(True)
            self.result_count_label.setText("Sequence ready to load")
    
    def _on_search_error(self, error_message):
        """Handle search error"""
        self.progress_bar.hide()
        self.search_button.setEnabled(True)
        self.result_count_label.setText("Search failed")
        
        QMessageBox.critical(
            self,
            "Search Failed",
            f"Failed to search NCBI database:\n\n{error_message}"
        )
    
    def _on_result_selected(self):
        """Handle result selection"""
        selected_items = self.results_list.selectedItems()
        
        if not selected_items:
            self.fetch_button.setEnabled(False)
            return
        
        self.fetch_button.setEnabled(True)
        
        # Show metadata preview (not full sequence yet)
        item = selected_items[0]
        seq_info = item.data(Qt.UserRole)
        
        title = seq_info.get('title', 'Unknown')
        organism = seq_info.get('organism', 'Unknown')
        length = seq_info.get('length', 0)
        accession = seq_info.get('accession', 'Unknown')
        
        self.preview_text.setPlainText(
            f"Accession: {accession}\n"
            f"Title: {title}\n"
            f"Organism: {organism}\n"
            f"Length: {length:,} bp\n\n"
            f"Click 'Fetch Sequence' or double-click to retrieve the full sequence."
        )
        self.sequence_info_label.setText("")
        self.load_button.setEnabled(False)
        self.selected_sequence = None
    
    def _fetch_selected_sequence(self):
        """Fetch the full sequence for the selected result"""
        selected_items = self.results_list.selectedItems()
        
        if not selected_items:
            return
        
        item = selected_items[0]
        seq_info = item.data(Qt.UserRole)
        accession = seq_info.get('accession', '')
        
        if not accession:
            return
        
        # Show progress
        self.progress_bar.show()
        self.fetch_button.setEnabled(False)
        self.result_count_label.setText(f"Fetching sequence {accession}...")
        
        # Fetch full sequence
        self.fetch_worker = SequenceFetchWorker(accession)
        self.fetch_worker.finished.connect(self._on_full_sequence_fetched)
        self.fetch_worker.error.connect(self._on_fetch_error)
        self.fetch_worker.start()
    
    def _on_full_sequence_fetched(self, result):
        """Handle full sequence fetch completion"""
        self.progress_bar.hide()
        self.fetch_button.setEnabled(True)
        self.result_count_label.setText(f"Found {len(self.search_results)} result(s)")
        
        self.selected_sequence = result
        
        # Show sequence preview
        sequence = result.get('sequence', '')
        if sequence:
            preview = sequence[:300]
            if len(sequence) > 300:
                preview += f"\n... ({len(sequence) - 300:,} more nucleotides)"
            
            self.preview_text.setPlainText(preview)
            
            accession = result.get('accession', 'Unknown')
            organism = result.get('organism', 'Unknown')
            mol_type = result.get('mol_type', 'Unknown')
            
            self.sequence_info_label.setText(
                f"<b>Accession:</b> {accession} | "
                f"<b>Length:</b> {len(sequence):,} bp | "
                f"<b>Organism:</b> {organism}"
            )
            
            self.load_button.setEnabled(True)
    
    def _on_fetch_error(self, error_message):
        """Handle sequence fetch error"""
        self.progress_bar.hide()
        self.fetch_button.setEnabled(True)
        self.result_count_label.setText(f"Found {len(self.search_results)} result(s)")
        
        QMessageBox.warning(
            self,
            "Fetch Failed",
            f"Failed to fetch sequence:\n\n{error_message}"
        )
    
    def _load_sequence(self):
        """Load selected sequence and close dialog"""
        if not self.selected_sequence:
            return
        
        sequence = self.selected_sequence.get('sequence', '')
        
        if not sequence:
            QMessageBox.warning(
                self,
                "No Sequence",
                "Selected entry has no sequence data available."
            )
            return
        
        # Emit signal with sequence and metadata
        metadata = {
            'accession': self.selected_sequence.get('accession', 'Unknown'),
            'title': self.selected_sequence.get('title', 'Unknown'),
            'organism': self.selected_sequence.get('organism', 'Unknown'),
            'mol_type': self.selected_sequence.get('mol_type', 'Unknown'),
            'source': 'genbank',
            'length': len(sequence)
        }
        
        self.sequence_selected.emit(sequence, metadata)
        self.accept()

