import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QStackedWidget
from ui.home_page import HomePage
from ui.blast_page import BLASTPage
from ui.mmseqs_page import MMseqsPage


class ProteinGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sen Lab - Protein Analysis Suite")
        self.setGeometry(100, 100, 900, 700)

        # --- Global app style (identical to your previous one)
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

        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.stacked = QStackedWidget()
        self.home_page = HomePage()
        self.blast_page = BLASTPage()
        self.mmseqs_page = MMseqsPage()

        self.stacked.addWidget(self.home_page)
        self.stacked.addWidget(self.blast_page)
        self.stacked.addWidget(self.mmseqs_page)
        layout.addWidget(self.stacked)

        # Page switching
        self.home_page.service_selected.connect(self.show_service_page)
        self.blast_page.back_requested.connect(self.show_home)
        self.mmseqs_page.back_requested.connect(self.show_home)

        self.show_home()

    def show_home(self):
        self.stacked.setCurrentWidget(self.home_page)
        self.setWindowTitle("Sen Lab - Protein Analysis Suite")

    def show_service_page(self, service):
        if service == "blast":
            self.stacked.setCurrentWidget(self.blast_page)
            self.setWindowTitle("Sen Lab - BLASTP Search")
        elif service == "mmseqs":
            self.stacked.setCurrentWidget(self.mmseqs_page)
            self.setWindowTitle("Sen Lab - MMseqs2 Search")


def main():
    app = QApplication(sys.argv)
    window = ProteinGUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
