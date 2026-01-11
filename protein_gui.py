import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QStackedWidget

from ui.home_page import HomePage
from ui.blast_page import BLASTPage
from ui.blastn_page import BLASTNPage
from ui.mmseqs_page import MMseqsPage
from ui.clustering_page import ClusteringPage
from ui.alignment_page import AlignmentPage
from ui.motif_search_page import MotifSearchPage


class ProteinGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sen Lab - Protein Analysis Suite")
        self.setGeometry(100, 100, 900, 700)
        self.setMinimumSize(800, 600)  # Enforce minimum size for usability
        
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
        self.blastn_page = BLASTNPage()
        self.mmseqs_page = MMseqsPage()
        self.clustering_page = ClusteringPage()
        self.alignment_page = AlignmentPage()
        self.motif_search_page = MotifSearchPage()
        
        # Add pages to stack
        self.stacked_widget.addWidget(self.home_page)
        self.stacked_widget.addWidget(self.blast_page)
        self.stacked_widget.addWidget(self.blastn_page)
        self.stacked_widget.addWidget(self.mmseqs_page)
        self.stacked_widget.addWidget(self.clustering_page)
        self.stacked_widget.addWidget(self.alignment_page)
        self.stacked_widget.addWidget(self.motif_search_page)
        
        # Connect signals
        self.home_page.service_selected.connect(self.show_service_page)
        self.blast_page.back_requested.connect(self.show_home_page)
        self.blastn_page.back_requested.connect(self.show_home_page)
        self.mmseqs_page.back_requested.connect(self.show_home_page)
        self.clustering_page.back_requested.connect(self.show_home_page)
        self.alignment_page.back_requested.connect(self.show_home_page)
        self.motif_search_page.back_requested.connect(self.show_home_page)
        
        # Connect clustering navigation signals
        self.blast_page.navigate_to_clustering.connect(self.show_clustering_with_fasta)
        self.mmseqs_page.navigate_to_clustering.connect(self.show_clustering_with_fasta)
        
        # Connect alignment navigation signals
        self.blast_page.navigate_to_alignment.connect(self.show_alignment_with_fasta)
        
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
        elif service == "blastn":
            self.stacked_widget.setCurrentWidget(self.blastn_page)
            self.setWindowTitle("Sen Lab - BLASTN Search")
        elif service == "mmseqs":
            self.stacked_widget.setCurrentWidget(self.mmseqs_page)
            self.setWindowTitle("Sen Lab - MMseqs2 Search")
        elif service == "clustering":
            self.stacked_widget.setCurrentWidget(self.clustering_page)
            self.setWindowTitle("Sen Lab - MMseqs2 Clustering")
        elif service == "alignment":
            self.stacked_widget.setCurrentWidget(self.alignment_page)
            self.setWindowTitle("Sen Lab - Sequence Alignment")
        elif service == "motif_search":
            self.stacked_widget.setCurrentWidget(self.motif_search_page)
            self.setWindowTitle("Sen Lab - Motif Search")
    
    def show_clustering_with_fasta(self, fasta_path: str, clustering_params: dict):
        """Show clustering page with pre-loaded FASTA and parameters"""
        # Load the FASTA into clustering page
        self.clustering_page.load_fasta_from_search(fasta_path, clustering_params)
        
        # Navigate to clustering page
        self.stacked_widget.setCurrentWidget(self.clustering_page)
        self.setWindowTitle("Sen Lab - MMseqs2 Clustering")
    
    def show_alignment_with_fasta(self, fasta_path: str):
        """Show alignment page with pre-loaded FASTA"""
        # Load the FASTA into alignment page
        self.alignment_page.load_sequences_from_search(fasta_path)
        
        # Navigate to alignment page
        self.stacked_widget.setCurrentWidget(self.alignment_page)
        self.setWindowTitle("Sen Lab - Sequence Alignment")

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
