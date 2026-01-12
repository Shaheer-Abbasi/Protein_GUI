from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, 
                             QGridLayout, QFrame, QScrollArea, QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont


class ServiceCard(QFrame):
    """A card widget for displaying a service button with description"""
    clicked = pyqtSignal()
    
    def __init__(self, title, description, color, hover_color, pressed_color, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            ServiceCard {{
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 10px;
            }}
            ServiceCard:hover {{
                border: 1px solid {color};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Button
        self.button = QPushButton(title)
        self.button.setMinimumHeight(60)
        self.button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.button.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color};
            }}
        """)
        self.button.clicked.connect(self.clicked.emit)
        
        # Description
        self.desc_label = QLabel(description)
        self.desc_label.setWordWrap(True)
        self.desc_label.setAlignment(Qt.AlignCenter)
        self.desc_label.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 11px;
                padding: 5px;
                background: transparent;
            }
        """)
        self.desc_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        layout.addWidget(self.button)
        layout.addWidget(self.desc_label)
        
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class HomePage(QWidget):
    """Home page widget with service selection"""
    service_selected = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the home page UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Scroll area for smaller screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        
        # Content widget
        content = QWidget()
        content.setStyleSheet("background-color: #f8f9fa;")
        layout = QVBoxLayout(content)
        layout.setSpacing(25)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # Welcome section
        welcome_frame = QFrame()
        welcome_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
            }
        """)
        welcome_layout = QVBoxLayout(welcome_frame)
        welcome_layout.setContentsMargins(30, 25, 30, 25)
        welcome_layout.setSpacing(8)
        
        # Title
        title_label = QLabel("Sen Lab - Protein Analysis Suite")
        title_font = QFont()
        title_font.setPointSize(22)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50; background: transparent;")
        
        # Subtitle
        subtitle_label = QLabel("Select a bioinformatics tool to analyze your sequences")
        subtitle_font = QFont()
        subtitle_font.setPointSize(11)
        subtitle_label.setFont(subtitle_font)
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet("color: #7f8c8d; background: transparent;")
        
        welcome_layout.addWidget(title_label)
        welcome_layout.addWidget(subtitle_label)
        
        # Services section header
        services_header = QLabel("Available Services")
        services_font = QFont()
        services_font.setPointSize(14)
        services_font.setBold(True)
        services_header.setFont(services_font)
        services_header.setStyleSheet("color: #34495e; background: transparent;")
        
        # Services grid
        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent;")
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(15)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create service cards
        services = [
            {
                "id": "blast",
                "title": "BLASTP Search",
                "desc": "Search protein sequences against NCBI databases to find homologous proteins",
                "color": "#3498db",
                "hover": "#2980b9", 
                "pressed": "#21618c",
                "row": 0, "col": 0
            },
            {
                "id": "blastn",
                "title": "BLASTN Search",
                "desc": "Search nucleotide sequences against NCBI databases for DNA/RNA homology",
                "color": "#1e8449",
                "hover": "#196f3d",
                "pressed": "#145a32",
                "row": 0, "col": 1
            },
            {
                "id": "mmseqs",
                "title": "MMseqs2 Search",
                "desc": "Fast and sensitive protein sequence searching using MMseqs2",
                "color": "#9b59b6",
                "hover": "#8e44ad",
                "pressed": "#7d3c98",
                "row": 1, "col": 0
            },
            {
                "id": "clustering",
                "title": "MMseqs2 Clustering",
                "desc": "Cluster protein sequences by similarity to group related sequences",
                "color": "#e67e22",
                "hover": "#d35400",
                "pressed": "#ba4a00",
                "row": 1, "col": 1
            },
            {
                "id": "alignment",
                "title": "Sequence Alignment",
                "desc": "Multiple sequence alignment using Clustal Omega with ClustalX visualization",
                "color": "#1abc9c",
                "hover": "#16a085",
                "pressed": "#149174",
                "row": 2, "col": 0
            },
            {
                "id": "motif_search",
                "title": "Motif Search",
                "desc": "Find glycosylation motifs in protein sequences with phylogeny-based visualization",
                "color": "#e91e63",
                "hover": "#c2185b",
                "pressed": "#ad1457",
                "row": 2, "col": 1
            },
            {
                "id": "database_downloads",
                "title": "Database Downloads",
                "desc": "Download and manage protein databases for BLAST and MMseqs2 searches",
                "color": "#00897b",
                "hover": "#00796b",
                "pressed": "#00695c",
                "row": 3, "col": 0
            },
        ]
        
        for svc in services:
            card = ServiceCard(
                svc["title"], 
                svc["desc"], 
                svc["color"], 
                svc["hover"], 
                svc["pressed"]
            )
            card.clicked.connect(lambda checked=False, sid=svc["id"]: self.service_selected.emit(sid))
            
            grid_layout.addWidget(card, svc["row"], svc["col"])
        
        # Assemble layout
        layout.addWidget(welcome_frame)
        layout.addWidget(services_header)
        layout.addWidget(grid_widget)
        layout.addStretch()
        
        scroll.setWidget(content)
        main_layout.addWidget(scroll)
