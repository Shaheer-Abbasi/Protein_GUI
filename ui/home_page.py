from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGridLayout, QFrame
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont


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
        services_layout.setSpacing(20)  # Add spacing between grid cells
        services_layout.setContentsMargins(15, 15, 15, 15)  # Add margins inside the frame
        
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
        blast_container_layout.setContentsMargins(5, 5, 5, 5)
        blast_container_layout.setSpacing(8)
        blast_container_layout.addWidget(blast_button)
        blast_container_layout.addWidget(blast_desc)
        blast_container_layout.addStretch()
        
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
        mmseqs_container_layout.setContentsMargins(5, 5, 5, 5)
        mmseqs_container_layout.setSpacing(8)
        mmseqs_container_layout.addWidget(mmseqs_button)
        mmseqs_container_layout.addWidget(mmseqs_desc)
        mmseqs_container_layout.addStretch()
        
        services_layout.addWidget(mmseqs_container, 0, 1)
        
        # Clustering service button
        clustering_button = QPushButton("MMseqs2 Clustering")
        clustering_button.setMinimumHeight(80)
        clustering_button.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #d35400;
            }
            QPushButton:pressed {
                background-color: #ba4a00;
            }
        """)
        clustering_button.clicked.connect(lambda: self.service_selected.emit("clustering"))
        
        # Clustering description
        clustering_desc = QLabel("Cluster protein sequences by similarity\nto identify redundancy and group related sequences")
        clustering_desc.setWordWrap(True)
        clustering_desc.setStyleSheet("color: #7f8c8d; margin-top: 10px; background: transparent;")
        clustering_desc.setAlignment(Qt.AlignCenter)
        
        # Add Clustering service to grid
        clustering_container = QWidget()
        clustering_container_layout = QVBoxLayout(clustering_container)
        clustering_container_layout.setContentsMargins(5, 5, 5, 5)
        clustering_container_layout.setSpacing(8)
        clustering_container_layout.addWidget(clustering_button)
        clustering_container_layout.addWidget(clustering_desc)
        clustering_container_layout.addStretch()
        
        services_layout.addWidget(clustering_container, 1, 0)
        
        # Alignment service button
        alignment_button = QPushButton("Sequence Alignment")
        alignment_button.setMinimumHeight(80)
        alignment_button.setStyleSheet("""
            QPushButton {
                background-color: #1abc9c;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #16a085;
            }
            QPushButton:pressed {
                background-color: #149174;
            }
        """)
        alignment_button.clicked.connect(lambda: self.service_selected.emit("alignment"))
        
        # Alignment description
        alignment_desc = QLabel("Multiple sequence alignment using Clustal Omega\nwith interactive ClustalX-style visualization")
        alignment_desc.setWordWrap(True)
        alignment_desc.setStyleSheet("color: #7f8c8d; margin-top: 10px; background: transparent;")
        alignment_desc.setAlignment(Qt.AlignCenter)
        
        # Add Alignment service to grid
        alignment_container = QWidget()
        alignment_container_layout = QVBoxLayout(alignment_container)
        alignment_container_layout.setContentsMargins(5, 5, 5, 5)
        alignment_container_layout.setSpacing(8)
        alignment_container_layout.addWidget(alignment_button)
        alignment_container_layout.addWidget(alignment_desc)
        alignment_container_layout.addStretch()
        
        services_layout.addWidget(alignment_container, 1, 1)
        
        # Add everything to main layout
        layout.addWidget(welcome_frame)
        layout.addWidget(services_label)
        layout.addWidget(services_frame)
        layout.addStretch()  # Push content to top
        
        self.setLayout(layout)
