"""Protein search dialog for AlphaFold/UniProt database search"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QListWidget, QListWidgetItem,
                             QTextEdit, QMessageBox, QProgressBar, QGroupBox)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont

from utils.alphafold_api import AlphaFoldClient, AlphaFoldAPIError


class ProteinSearchWorker(QThread):
    """Worker thread for API calls to prevent UI freezing"""
    finished = pyqtSignal(list)  # List of search results
    error = pyqtSignal(str)      # Error message
    
    def __init__(self, search_term: str, search_type: str):
        super().__init__()
        self.search_term = search_term
        self.search_type = search_type  # 'name' or 'id'
        self.client = AlphaFoldClient()
    
    def run(self):
        try:
            if self.search_type == 'id':
                # Direct lookup by UniProt ID
                result = self.client.get_protein_by_uniprot_id(self.search_term)
                # Wrap in list for consistent handling
                self.finished.emit([result])
            else:
                # Search by protein name
                results = self.client.search_protein_by_name(self.search_term, limit=20)
                self.finished.emit(results)
        except AlphaFoldAPIError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Unexpected error: {str(e)}")


class ProteinSearchDialog(QDialog):
    """
    Dialog for searching proteins in AlphaFold/UniProt databases
    
    Features:
    - Search by protein name or UniProt ID
    - Non-blocking API calls (uses QThread)
    - Results preview
    - Sequence selection and loading
    """
    
    sequence_selected = pyqtSignal(str, dict)  # (sequence, metadata)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Protein Database")
        self.resize(700, 600)
        
        self.search_results = []
        self.selected_protein = None
        self.worker = None
        
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
        
        self.search_by_name_radio = QPushButton("Protein Name")
        self.search_by_id_radio = QPushButton("UniProt ID")
        self.search_by_name_radio.setCheckable(True)
        self.search_by_id_radio.setCheckable(True)
        self.search_by_name_radio.setChecked(True)
        
        # Button group behavior
        self.search_by_name_radio.clicked.connect(lambda: self._set_search_type('name'))
        self.search_by_id_radio.clicked.connect(lambda: self._set_search_type('id'))
        
        type_layout.addWidget(self.search_by_name_radio)
        type_layout.addWidget(self.search_by_id_radio)
        type_layout.addStretch()
        search_layout.addLayout(type_layout)
        
        # Search input
        input_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter protein name (e.g., Hemoglobin) or UniProt ID (e.g., P69905)")
        self.search_input.returnPressed.connect(self._perform_search)
        
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._perform_search)
        self.search_button.setDefault(True)
        
        input_layout.addWidget(self.search_input)
        input_layout.addWidget(self.search_button)
        search_layout.addLayout(input_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.hide()
        search_layout.addWidget(self.progress_bar)
        
        # Examples
        examples_label = QLabel(
            '<i>Examples: "Insulin", "Hemoglobin", "P12345", "Q8W3K0"</i>'
        )
        examples_label.setStyleSheet("color: #666;")
        search_layout.addWidget(examples_label)
        
        search_group.setLayout(search_layout)
        layout.addWidget(search_group)
        
        # Results section
        results_group = QGroupBox("Search Results")
        results_layout = QVBoxLayout()
        
        self.results_list = QListWidget()
        self.results_list.itemSelectionChanged.connect(self._on_result_selected)
        results_layout.addWidget(self.results_list)
        
        # Result count label
        self.result_count_label = QLabel("No search performed yet")
        self.result_count_label.setStyleSheet("color: #666; font-style: italic;")
        results_layout.addWidget(self.result_count_label)
        
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        # Preview section
        preview_group = QGroupBox("Sequence Preview")
        preview_layout = QVBoxLayout()
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)
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
                background-color: #2ecc71;
                color: white;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #27ae60;
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
    
    def _set_search_type(self, search_type):
        """Update search type radio buttons"""
        if search_type == 'name':
            self.search_by_name_radio.setChecked(True)
            self.search_by_id_radio.setChecked(False)
            self.search_input.setPlaceholderText("Enter protein name (e.g., Hemoglobin)")
        else:
            self.search_by_name_radio.setChecked(False)
            self.search_by_id_radio.setChecked(True)
            self.search_input.setPlaceholderText("Enter UniProt ID (e.g., P69905)")
    
    def _perform_search(self):
        """Perform protein search"""
        search_term = self.search_input.text().strip()
        
        if not search_term:
            QMessageBox.warning(
                self,
                "Empty Search",
                "Please enter a protein name or UniProt ID to search."
            )
            return
        
        # Determine search type
        search_type = 'id' if self.search_by_id_radio.isChecked() else 'name'
        
        # Clear previous results
        self.results_list.clear()
        self.preview_text.clear()
        self.sequence_info_label.clear()
        self.load_button.setEnabled(False)
        self.search_results = []
        
        # Show progress
        self.progress_bar.show()
        self.search_button.setEnabled(False)
        self.result_count_label.setText("Searching...")
        
        # Start worker thread
        self.worker = ProteinSearchWorker(search_term, search_type)
        self.worker.finished.connect(self._on_search_complete)
        self.worker.error.connect(self._on_search_error)
        self.worker.start()
    
    def _on_search_complete(self, results):
        """Handle search completion"""
        self.progress_bar.hide()
        self.search_button.setEnabled(True)
        
        if not results:
            self.result_count_label.setText("No results found")
            QMessageBox.information(
                self,
                "No Results",
                "No proteins found matching your search.\n\n"
                "Please try a different search term or UniProt ID."
            )
            return
        
        self.search_results = results
        self.result_count_label.setText(f"Found {len(results)} result(s)")
        
        # Populate results list
        for protein in results:
            uniprot_id = protein.get('uniprot_id', 'Unknown')
            protein_name = protein.get('protein_name', 'Unknown protein')
            organism = protein.get('organism', 'Unknown organism')
            length = protein.get('length', len(protein.get('sequence', '')))
            
            item_text = f"{uniprot_id} - {protein_name}\n    {organism} ({length} aa)"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, protein)
            self.results_list.addItem(item)
    
    def _on_search_error(self, error_message):
        """Handle search error"""
        self.progress_bar.hide()
        self.search_button.setEnabled(True)
        self.result_count_label.setText("Search failed")
        
        QMessageBox.critical(
            self,
            "Search Failed",
            f"Failed to search protein database:\n\n{error_message}"
        )
    
    def _on_result_selected(self):
        """Handle result selection"""
        selected_items = self.results_list.selectedItems()
        
        if not selected_items:
            self.preview_text.clear()
            self.sequence_info_label.clear()
            self.load_button.setEnabled(False)
            return
        
        item = selected_items[0]
        protein = item.data(Qt.UserRole)
        
        self.selected_protein = protein
        
        # Show sequence preview
        sequence = protein.get('sequence', '')
        if sequence:
            # Show first 200 characters
            preview = sequence[:200]
            if len(sequence) > 200:
                preview += f"... ({len(sequence) - 200} more characters)"
            
            self.preview_text.setPlainText(preview)
            
            # Show info
            source = protein.get('source', 'unknown')
            self.sequence_info_label.setText(
                f"<b>Length:</b> {len(sequence)} amino acids | "
                f"<b>Source:</b> {source.upper()}"
            )
            
            self.load_button.setEnabled(True)
        else:
            self.preview_text.setPlainText("No sequence available")
            self.sequence_info_label.setText("")
            self.load_button.setEnabled(False)
    
    def _load_sequence(self):
        """Load selected sequence and close dialog"""
        if not self.selected_protein:
            return
        
        sequence = self.selected_protein.get('sequence', '')
        
        if not sequence:
            QMessageBox.warning(
                self,
                "No Sequence",
                "Selected protein has no sequence data available."
            )
            return
        
        # Emit signal with sequence and metadata
        metadata = {
            'uniprot_id': self.selected_protein.get('uniprot_id', 'Unknown'),
            'protein_name': self.selected_protein.get('protein_name', 'Unknown'),
            'organism': self.selected_protein.get('organism', 'Unknown'),
            'source': self.selected_protein.get('source', 'unknown'),
            'length': len(sequence)
        }
        
        self.sequence_selected.emit(sequence, metadata)
        self.accept()

