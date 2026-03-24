from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QFrame, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import get_theme, PAGE_ACCENTS
from ui.icons import feather_icon


class ServiceCard(QFrame):
    """Card widget for a service on the home page."""
    clicked = pyqtSignal()

    def __init__(self, title, description, accent, icon_name=None, parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        btn = QPushButton(title)
        btn.setMinimumHeight(54)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if icon_name:
            btn.setIcon(feather_icon(icon_name, 18, "#FFFFFF"))
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                padding: 14px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)
        btn.clicked.connect(self.clicked.emit)

        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setProperty("class", "muted")
        desc_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout.addWidget(btn)
        layout.addWidget(desc_lbl)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class HomePage(QWidget):
    """Home page with service selection cards."""
    service_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(24)
        layout.setContentsMargins(40, 36, 40, 36)

        t = get_theme()

        # Welcome banner
        banner = QFrame()
        banner.setProperty("class", "card")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(30, 24, 30, 24)
        banner_layout.setSpacing(8)

        title = QLabel("Sen Lab - Protein Analysis Suite")
        title.setProperty("class", "title")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("Select a bioinformatics tool to analyse your sequences")
        subtitle.setProperty("class", "muted")
        subtitle.setAlignment(Qt.AlignCenter)

        banner_layout.addWidget(title)
        banner_layout.addWidget(subtitle)

        # External tools: centered row above main services, visually separated
        tools_heading = QLabel("External command-line tools")
        tools_heading.setProperty("class", "heading")
        tools_heading.setAlignment(Qt.AlignCenter)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(0)
        tools_row.addStretch(1)
        tools_wrap = QWidget()
        tools_wrap.setMaximumWidth(520)
        tw_layout = QVBoxLayout(tools_wrap)
        tw_layout.setContentsMargins(0, 0, 0, 0)
        tools_accent = PAGE_ACCENTS.get("tools", t.get("accent"))
        tools_card = ServiceCard(
            "Tools",
            "Install BLAST+, MMseqs2, blastdbcmd, and Clustal Omega for searches, clustering, and alignment",
            tools_accent,
            "tool",
        )
        tools_card.clicked.connect(lambda: self.service_selected.emit("tools"))
        tw_layout.addWidget(tools_card)
        tools_row.addWidget(tools_wrap, alignment=Qt.AlignHCenter)
        tools_row.addStretch(1)

        section_divider = QFrame()
        section_divider.setFrameShape(QFrame.HLine)
        section_divider.setFrameShadow(QFrame.Sunken)

        # Section header
        section_header = QLabel("Available Services")
        section_header.setProperty("class", "heading")

        # Service cards grid
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(16)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        services = [
            ("protein_search", "Protein Search",     "Search protein sequences using BLASTP or MMseqs2 against local or remote databases", "search"),
            ("blastn",         "BLASTN Search",      "Search nucleotide sequences against NCBI databases for DNA/RNA homology",            "search"),
            ("clustering",     "MMseqs2 Clustering", "Cluster protein sequences by similarity to group related sequences",                 "grid"),
            ("alignment",      "Sequence Alignment", "Multiple sequence alignment using Clustal Omega with ClustalX visualisation",        "bar-chart-2"),
            ("motif_search",   "Motif Search",       "Find glycosylation motifs in protein sequences with visualisation",                  "filter"),
            ("database_downloads","Database Downloads","Download and manage protein databases for BLAST and MMseqs2 searches",             "database"),
        ]

        for idx, (sid, title_text, desc, icon) in enumerate(services):
            accent = PAGE_ACCENTS.get(sid.replace("_downloads", "").replace("_search", ""),
                                      t.get("accent"))
            card = ServiceCard(title_text, desc, accent, icon)
            card.clicked.connect(lambda _=False, s=sid: self.service_selected.emit(s))
            grid.addWidget(card, idx // 2, idx % 2)

        layout.addWidget(banner)
        layout.addSpacing(12)
        layout.addWidget(tools_heading)
        layout.addLayout(tools_row)
        layout.addSpacing(20)
        layout.addWidget(section_divider)
        layout.addSpacing(20)
        layout.addWidget(section_header)
        layout.addWidget(grid_widget)
        layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)
