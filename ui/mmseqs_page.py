from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel, QHBoxLayout, QLineEdit, QFileDialog
from PyQt5.QtCore import pyqtSignal
from core.mmseqs_runner import MMseqsRunner
from PyQt5.QtGui import QFont


class MMseqsPage(QWidget):
    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.runner = MMseqsRunner()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QHBoxLayout()
        back = QPushButton("← Back to Home")
        back.setStyleSheet("""
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
        back.clicked.connect(self.back_requested.emit)

        title = QLabel("MMseqs2 Search")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #2c3e50;")

        header.addWidget(back)
        header.addStretch()
        header.addWidget(title)
        header.addStretch()

        # Input
        seq_label = QLabel("Enter protein sequence:")
        self.seq_text = QTextEdit()
        self.seq_text.setPlaceholderText("Paste your amino acid sequence here (single letter codes)...")
        self.seq_text.setMaximumHeight(100)

        # Database input
        db_layout = QHBoxLayout()
        db_label = QLabel("Database Path:")
        self.db_path = QLineEdit()
        self.db_path.setPlaceholderText("Enter path to your MMseqs2 database folder...")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.select_db)
        db_layout.addWidget(db_label)
        db_layout.addWidget(self.db_path)
        db_layout.addWidget(browse)

        # Run button
        run_btn = QPushButton("Run MMseqs2 Search")
        run_btn.setStyleSheet("""
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
        """)
        run_btn.clicked.connect(self.run_mmseqs)

        # Output
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout.addLayout(header)
        layout.addWidget(seq_label)
        layout.addWidget(self.seq_text)
        layout.addLayout(db_layout)
        layout.addWidget(run_btn)
        layout.addWidget(self.output)

        self.setLayout(layout)

    def select_db(self):
        directory = QFileDialog.getExistingDirectory(self, "Select MMseqs2 Database Folder", "")
        if directory:
            self.db_path.setText(directory)

    def run_mmseqs(self):
        seq = self.seq_text.toPlainText().strip().upper()
        db = self.db_path.text().strip()
        if not seq:
            self.output.setText("Please enter a sequence first.")
            return
        if not db:
            self.output.setText("Please specify the database path.")
            return
        self.output.setText("Running MMseqs2 search...\n\nPlease wait...")
        result = self.runner.run_easy_search(seq, db)
        self.output.setText(result)
