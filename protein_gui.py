import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QWidget, QTabWidget, QPushButton, QStatusBar, QLabel
)
from PyQt5.QtCore import Qt, QSize

from ui.theme import get_theme
from ui.icons import feather_icon, set_button_icon
from ui.home_page import HomePage
from ui.protein_search_page import ProteinSearchPage
from ui.blastn_page import BLASTNPage
from ui.clustering_page import ClusteringPage
from ui.alignment_page import AlignmentPage
from ui.motif_search_page import MotifSearchPage
from ui.database_downloads_page import DatabaseDownloadsPage
from ui.tools_page import ToolsPage

TAB_ICONS = [
    "home", "search", "search",
    "grid", "bar-chart-2", "filter", "tool", "database",
]


class ProteinGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sen Lab - Protein Analysis Suite")
        self.setGeometry(100, 100, 1100, 750)
        self.setMinimumSize(900, 600)

        self._theme = get_theme()
        self._theme.theme_changed.connect(self._on_theme_changed)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Tab widget (persistent navigation)
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.tabs.setIconSize(QSize(18, 18))

        # Create pages
        self.home_page = HomePage()
        self.protein_search_page = ProteinSearchPage()
        self.blastn_page = BLASTNPage()
        self.clustering_page = ClusteringPage()
        self.alignment_page = AlignmentPage()
        self.motif_search_page = MotifSearchPage()
        self.tools_page = ToolsPage()
        self.database_downloads_page = DatabaseDownloadsPage()

        # Add tabs with Feather icons
        self.tabs.addTab(self.home_page,               feather_icon("home", 18),           "Home")
        self.tabs.addTab(self.protein_search_page,     feather_icon("search", 18),         "Protein Search")
        self.tabs.addTab(self.blastn_page,              feather_icon("search", 18),         "BLASTN")
        self.tabs.addTab(self.clustering_page,          feather_icon("grid", 18),           "Clustering")
        self.tabs.addTab(self.alignment_page,           feather_icon("bar-chart-2", 18),    "Alignment")
        self.tabs.addTab(self.motif_search_page,        feather_icon("filter", 18),         "Motif Search")
        self.tabs.addTab(self.tools_page,               feather_icon("tool", 18),           "Tools")
        self.tabs.addTab(self.database_downloads_page,  feather_icon("database", 18),       "Databases")

        # Theme toggle integrated into the tab bar as a corner widget
        self._theme_btn = QPushButton()
        self._theme_btn.setCursor(Qt.PointingHandCursor)
        self._theme_btn.setToolTip("Toggle light/dark theme")
        self._theme_btn.clicked.connect(self._theme.toggle)
        self._theme_btn.setIconSize(QSize(16, 16))
        self._update_theme_button()
        self.tabs.setCornerWidget(self._theme_btn, Qt.TopRightCorner)

        root.addWidget(self.tabs)

        # Status bar with centered credit text
        status = QStatusBar()
        status.setSizeGripEnabled(True)
        self.setStatusBar(status)
        credit = QLabel("Made by the Sen Lab team")
        credit.setAlignment(Qt.AlignCenter)
        status.addWidget(credit, 1)

        # Connect home page card clicks to tab switches
        self.home_page.service_selected.connect(self._navigate_from_home)

        # Cross-page navigation signals
        self.protein_search_page.navigate_to_clustering.connect(self._show_clustering_with_fasta)
        self.protein_search_page.navigate_to_alignment.connect(self._show_alignment_with_fasta)

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _navigate_from_home(self, service: str):
        page_map = {
            "protein_search":     self.protein_search_page,
            "blastn":             self.blastn_page,
            "clustering":         self.clustering_page,
            "alignment":          self.alignment_page,
            "motif_search":       self.motif_search_page,
            "tools":              self.tools_page,
            "database_downloads": self.database_downloads_page,
        }
        page = page_map.get(service)
        if page:
            self.tabs.setCurrentWidget(page)

    def _on_tab_changed(self, index: int):
        titles = {
            0: "Sen Lab - Protein Analysis Suite",
            1: "Sen Lab - Protein Search",
            2: "Sen Lab - BLASTN Search",
            3: "Sen Lab - MMseqs2 Clustering",
            4: "Sen Lab - Sequence Alignment",
            5: "Sen Lab - Motif Search",
            6: "Sen Lab - Tools",
            7: "Sen Lab - Database Downloads",
        }
        self.setWindowTitle(titles.get(index, "Sen Lab"))

    def _show_clustering_with_fasta(self, fasta_path: str, clustering_params: dict):
        self.clustering_page.load_fasta_from_search(fasta_path, clustering_params)
        self.tabs.setCurrentWidget(self.clustering_page)

    def _show_alignment_with_fasta(self, fasta_path: str):
        self.alignment_page.load_sequences_from_search(fasta_path)
        self.tabs.setCurrentWidget(self.alignment_page)

    def _on_theme_changed(self, theme_name: str):
        self._update_theme_button()
        self._refresh_tab_icons()

    def _update_theme_button(self):
        t = self._theme
        is_dark = t.current_theme == "dark"
        icon_name = "sun" if is_dark else "moon"
        label = "Light" if is_dark else "Dark"
        self._theme_btn.setIcon(feather_icon(icon_name, 16, t.get("text_muted")))
        self._theme_btn.setText(label)
        self._theme_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.get('bg_secondary')};
                color: {t.get('text_muted')};
                border: none;
                border-bottom: 3px solid transparent;
                border-radius: 0px;
                padding: 10px 18px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {t.get('bg_hover')};
                color: {t.get('text_primary')};
            }}
            QPushButton:pressed {{
                background-color: {t.get('bg_selected')};
                color: {t.get('accent')};
                border-bottom: 3px solid {t.get('accent')};
            }}
        """)

    def _refresh_tab_icons(self):
        for i, icon_name in enumerate(TAB_ICONS):
            self.tabs.setTabIcon(i, feather_icon(icon_name, 18))


def main():
    try:
        app = QApplication(sys.argv)

        theme = get_theme()
        theme.apply(app)

        window = ProteinGUI()
        window.show()
        sys.exit(app.exec_())

    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
