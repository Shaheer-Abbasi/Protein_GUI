from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGridLayout, QFrame
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from utils.hardware_utils import has_nvidia_gpu


class HomePage(QWidget):
    service_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(30)
        layout.setContentsMargins(50, 50, 50, 50)

        # Welcome frame
        welcome_frame = QFrame()
        welcome_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        welcome_layout = QVBoxLayout(welcome_frame)

        title = QLabel("Sen Lab - Protein Analysis Suite")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2c3e50;")

        subtitle = QLabel("Select a bioinformatics tool to analyze your protein sequences")
        subtitle.setFont(QFont("Arial", 12))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #7f8c8d; margin-top: 10px;")

        gpu_status = QLabel()
        gpu_status.setAlignment(Qt.AlignCenter)
        gpu_status.setFont(QFont("Arial", 10))
        if has_nvidia_gpu():
            gpu_status.setText("✅ GPU Detected (CUDA Available)")
            gpu_status.setStyleSheet("color: #27ae60;")
        else:
            gpu_status.setText("❌ No GPU Detected")
            gpu_status.setStyleSheet("color: #e74c3c;")

        welcome_layout.addWidget(title)
        welcome_layout.addWidget(subtitle)
        welcome_layout.addWidget(gpu_status)

        # Service cards
        services_label = QLabel("Available Services:")
        services_label.setFont(QFont("Arial", 16, QFont.Bold))
        services_label.setStyleSheet("color: #34495e; margin-top: 20px;")

        services_frame = QFrame()
        services_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 2px solid #ecf0f1;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        grid = QGridLayout(services_frame)

        # BLAST card
        blast_btn = QPushButton("BLASTP Search")
        blast_btn.setMinimumHeight(80)
        blast_btn.setStyleSheet("""
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
        """)
        blast_btn.clicked.connect(lambda: self.service_selected.emit("blast"))

        blast_desc = QLabel("Search protein sequences against NCBI databases\nto find homologs and functional insights")
        blast_desc.setAlignment(Qt.AlignCenter)
        blast_desc.setStyleSheet("color: #7f8c8d; margin-top: 10px;")

        blast_container = QWidget()
        v1 = QVBoxLayout(blast_container)
        v1.addWidget(blast_btn)
        v1.addWidget(blast_desc)
        grid.addWidget(blast_container, 0, 0)

        # MMseqs2 card
        mmseqs_btn = QPushButton("MMseqs2 Search")
        mmseqs_btn.setMinimumHeight(80)
        mmseqs_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        mmseqs_btn.clicked.connect(lambda: self.service_selected.emit("mmseqs"))

        mmseqs_desc = QLabel("Run local or high-performance MMseqs2 homology searches\non your machine")
        mmseqs_desc.setAlignment(Qt.AlignCenter)
        mmseqs_desc.setStyleSheet("color: #7f8c8d; margin-top: 10px;")

        mmseqs_container = QWidget()
        v2 = QVBoxLayout(mmseqs_container)
        v2.addWidget(mmseqs_btn)
        v2.addWidget(mmseqs_desc)
        grid.addWidget(mmseqs_container, 0, 1)

        layout.addWidget(welcome_frame)
        layout.addWidget(services_label)
        layout.addWidget(services_frame)
        layout.addStretch()
        self.setLayout(layout)
