import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QStackedWidget

from ui.home_page import HomePage
from ui.blast_page import BLASTPage
from ui.mmseqs_page import MMseqsPage


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
