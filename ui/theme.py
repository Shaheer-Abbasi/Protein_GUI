"""
Centralized theme system for the Protein Analysis Suite.

Provides light/dark palettes, platform-aware fonts, per-page accent colors,
and a global QSS stylesheet so individual pages never need inline styles.
"""
import sys
import tempfile
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, pyqtSignal, Qt, QPointF
from PyQt5.QtGui import QFont, QFontDatabase, QPixmap, QPainter, QColor, QPolygonF


_arrow_cache = {}


def _make_arrow_icon(direction: str, color: str, size: int = 10) -> str:
    """Render a small triangle arrow PNG and return its file path."""
    cache_key = (direction, color, size)
    if cache_key in _arrow_cache:
        return _arrow_cache[cache_key]

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)

    m = size * 0.2
    if direction == "up":
        tri = QPolygonF([
            QPointF(size / 2, m),
            QPointF(size - m, size - m),
            QPointF(m, size - m),
        ])
    else:
        tri = QPolygonF([
            QPointF(m, m),
            QPointF(size - m, m),
            QPointF(size / 2, size - m),
        ])

    painter.drawPolygon(tri)
    painter.end()

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix=f"arrow_{direction}_")
    pixmap.save(tmp.name, "PNG")
    tmp.close()
    _arrow_cache[cache_key] = tmp.name
    return tmp.name


def _platform_ui_font():
    if sys.platform == "darwin":
        return '"SF Pro Display", "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif'
    return '"Inter", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'


def _platform_mono_font():
    if sys.platform == "darwin":
        return '"JetBrains Mono", Menlo, "SF Mono", Monaco, monospace'
    return '"JetBrains Mono", Consolas, "Courier New", monospace'


LIGHT = {
    "bg_primary":    "#F7F8FA",
    "bg_secondary":  "#FFFFFF",
    "bg_card":       "#FFFFFF",
    "bg_input":      "#FFFFFF",
    "bg_hover":      "#EBF5FB",
    "bg_selected":   "#D6EAF8",

    "text_primary":  "#1C2833",
    "text_secondary":"#2C3E50",
    "text_muted":    "#7F8C8D",
    "text_on_accent":"#FFFFFF",

    "border":        "#D5D8DC",
    "border_light":  "#E8EAED",

    "accent":        "#5DADE2",
    "accent_hover":  "#3498DB",
    "accent_pressed":"#2E86C1",

    "success":       "#27AE60",
    "success_bg":    "#D5F5E3",
    "warning":       "#F39C12",
    "warning_bg":    "#FEF9E7",
    "error":         "#E74C3C",
    "error_bg":      "#FADBD8",

    "scrollbar_bg":  "#EAECEE",
    "scrollbar_handle":"#BDC3C7",
}

DARK = {
    "bg_primary":    "#1A1D23",
    "bg_secondary":  "#22262E",
    "bg_card":       "#2A2E36",
    "bg_input":      "#2A2E36",
    "bg_hover":      "#1B3A4B",
    "bg_selected":   "#1A4971",

    "text_primary":  "#E5E8EB",
    "text_secondary":"#ABB2B9",
    "text_muted":    "#6C7A89",
    "text_on_accent":"#FFFFFF",

    "border":        "#3B4048",
    "border_light":  "#31363F",

    "accent":        "#5DADE2",
    "accent_hover":  "#85C1E9",
    "accent_pressed":"#3498DB",

    "success":       "#2ECC71",
    "success_bg":    "#1A3C2A",
    "warning":       "#F5B041",
    "warning_bg":    "#3D3017",
    "error":         "#E74C3C",
    "error_bg":      "#3D1A1A",

    "scrollbar_bg":  "#2A2E36",
    "scrollbar_handle":"#4A5058",
}

PAGE_ACCENTS = {
    "home":        "#5DADE2",
    "blast":       "#3498DB",
    "blastn":      "#1E8449",
    "mmseqs":      "#9B59B6",
    "clustering":  "#E67E22",
    "alignment":   "#1ABC9C",
    "motif":       "#E91E63",
    "tools":       "#607D8B",
    "database":    "#00897B",
}


class ThemeManager(QObject):
    """Singleton that manages the application theme."""

    theme_changed = pyqtSignal(str)  # emits "light" or "dark"

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            instance = super().__new__(cls)
            QObject.__init__(instance)
            instance._theme = "light"
            instance._palette = LIGHT.copy()
            instance._app = None
            cls._instance = instance
        return cls._instance

    def __init__(self):
        pass

    @property
    def current_theme(self) -> str:
        return self._theme

    def get(self, key: str) -> str:
        return self._palette.get(key, "")

    def page_accent(self, page_id: str) -> str:
        return PAGE_ACCENTS.get(page_id, self._palette["accent"])

    def toggle(self):
        new = "dark" if self._theme == "light" else "light"
        self.set_theme(new)

    def set_theme(self, theme: str):
        self._theme = theme
        self._palette = DARK.copy() if theme == "dark" else LIGHT.copy()
        _arrow_cache.clear()
        if self._app:
            self._apply_qss(self._app)
        self.theme_changed.emit(theme)

    def apply(self, app: QApplication):
        self._app = app
        app.setStyle("Fusion")
        self._apply_qss(app)

    def _apply_qss(self, app: QApplication):
        p = self._palette
        ui_font = _platform_ui_font()
        mono_font = _platform_mono_font()

        qss = f"""
        /* ── Global ─────────────────────────────────────── */
        * {{
            font-family: {ui_font};
            font-size: 13px;
        }}

        QMainWindow {{
            background-color: {p['bg_primary']};
        }}

        QWidget {{
            background-color: {p['bg_primary']};
            color: {p['text_primary']};
        }}

        /* ── Tab Widget ─────────────────────────────────── */
        QTabWidget::pane {{
            border: none;
            background-color: {p['bg_primary']};
        }}

        QTabBar {{
            background-color: {p['bg_secondary']};
        }}

        QTabBar::tab {{
            background-color: {p['bg_secondary']};
            color: {p['text_muted']};
            padding: 10px 18px;
            border: none;
            border-bottom: 3px solid transparent;
            font-weight: 600;
            font-size: 12px;
        }}

        QTabBar::tab:selected {{
            color: {p['accent']};
            border-bottom: 3px solid {p['accent']};
            background-color: {p['bg_primary']};
        }}

        QTabBar::tab:hover:!selected {{
            color: {p['text_primary']};
            background-color: {p['bg_hover']};
        }}

        /* ── Group Box ──────────────────────────────────── */
        QGroupBox {{
            font-weight: 600;
            font-size: 13px;
            border: 1px solid {p['border']};
            border-radius: 6px;
            margin-top: 16px;
            padding: 24px 16px 16px 16px;
            background-color: {p['bg_card']};
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 2px 8px;
            color: {p['text_secondary']};
        }}

        /* ── Buttons ────────────────────────────────────── */
        QPushButton {{
            background-color: {p['accent']};
            color: {p['text_on_accent']};
            border: 2px solid transparent;
            border-radius: 6px;
            padding: 8px 18px;
            font-weight: 600;
            font-size: 13px;
        }}

        QPushButton:hover {{
            background-color: {p['accent_hover']};
            border-color: {p['accent_pressed']};
        }}

        QPushButton:pressed {{
            background-color: {p['accent_pressed']};
            padding: 9px 18px 7px 18px;
        }}

        QPushButton:disabled {{
            background-color: {p['border']};
            color: {p['text_muted']};
        }}

        QPushButton[class="secondary"] {{
            background-color: {p['bg_card']};
            color: {p['text_secondary']};
            border: 1px solid {p['border']};
        }}

        QPushButton[class="secondary"]:hover {{
            background-color: {p['bg_hover']};
            border-color: {p['accent']};
            color: {p['accent']};
        }}

        QPushButton[class="secondary"]:pressed {{
            background-color: {p['bg_selected']};
            border-color: {p['accent_pressed']};
        }}

        QPushButton[class="success"] {{
            background-color: {p['success']};
        }}

        QPushButton[class="success"]:hover {{
            background-color: #229954;
            border-color: #1E8449;
        }}

        QPushButton[class="success"]:pressed {{
            background-color: #1E8449;
            padding: 9px 18px 7px 18px;
        }}

        QPushButton[class="danger"] {{
            background-color: {p['error']};
        }}

        QPushButton[class="danger"]:hover {{
            background-color: #C0392B;
            border-color: #A93226;
        }}

        QPushButton[class="danger"]:pressed {{
            background-color: #A93226;
            padding: 9px 18px 7px 18px;
        }}

        /* ── Inputs ─────────────────────────────────────── */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {p['bg_input']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            border-radius: 6px;
            padding: 6px 10px;
            selection-background-color: {p['accent']};
            selection-color: {p['text_on_accent']};
        }}

        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border-color: {p['accent']};
        }}

        QTextEdit[readOnly="true"] {{
            background-color: {p['bg_card']};
        }}

        QTextEdit[class="mono"] {{
            font-family: {mono_font};
            font-size: 12px;
            background-color: {p['bg_card']};
        }}

        /* ── Combo Box ──────────────────────────────────── */
        QComboBox {{
            background-color: {p['bg_input']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            border-radius: 6px;
            padding: 6px 10px;
            min-height: 28px;
        }}

        QComboBox:hover {{
            border-color: {p['accent']};
        }}

        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {p['bg_card']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            selection-background-color: {p['bg_selected']};
            selection-color: {p['text_primary']};
        }}

        /* ── Spin Boxes ─────────────────────────────────── */
        QSpinBox, QDoubleSpinBox {{
            background-color: {p['bg_input']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            border-radius: 6px;
            padding: 4px 8px;
            min-height: 24px;
        }}

        QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {p['accent']};
        }}

        QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 20px;
            border-left: 1px solid {p['border']};
            border-top-right-radius: 5px;
            background-color: {p['bg_secondary']};
        }}

        QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{
            background-color: {p['bg_hover']};
        }}

        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 20px;
            border-left: 1px solid {p['border']};
            border-bottom-right-radius: 5px;
            background-color: {p['bg_secondary']};
        }}

        QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
            background-color: {p['bg_hover']};
        }}

        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
            image: url({_make_arrow_icon("up", p['text_secondary'])});
            width: 10px;
            height: 10px;
        }}

        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            image: url({_make_arrow_icon("down", p['text_secondary'])});
            width: 10px;
            height: 10px;
        }}

        /* ── Radio / Check ──────────────────────────────── */
        QRadioButton, QCheckBox {{
            color: {p['text_primary']};
            spacing: 8px;
            padding: 4px 2px;
            font-size: 13px;
        }}

        QRadioButton::indicator, QCheckBox::indicator {{
            width: 16px;
            height: 16px;
        }}

        /* ── Scroll Area ────────────────────────────────── */
        QScrollArea {{
            border: none;
            background-color: {p['bg_primary']};
        }}

        QScrollBar:vertical {{
            background: {p['scrollbar_bg']};
            width: 10px;
            border-radius: 5px;
            margin: 0;
        }}

        QScrollBar::handle:vertical {{
            background: {p['scrollbar_handle']};
            min-height: 30px;
            border-radius: 5px;
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}

        QScrollBar:horizontal {{
            background: {p['scrollbar_bg']};
            height: 10px;
            border-radius: 5px;
            margin: 0;
        }}

        QScrollBar::handle:horizontal {{
            background: {p['scrollbar_handle']};
            min-width: 30px;
            border-radius: 5px;
        }}

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}

        /* ── Splitter ───────────────────────────────────── */
        QSplitter::handle {{
            background-color: {p['border_light']};
        }}

        QSplitter::handle:vertical {{
            height: 4px;
        }}

        QSplitter::handle:horizontal {{
            width: 4px;
        }}

        /* ── Table ──────────────────────────────────────── */
        QTableWidget {{
            background-color: {p['bg_card']};
            alternate-background-color: {p['bg_primary']};
            color: {p['text_primary']};
            gridline-color: {p['border_light']};
            border: 1px solid {p['border']};
            border-radius: 6px;
            selection-background-color: {p['bg_selected']};
        }}

        QTableWidget::item {{
            padding: 4px 8px;
        }}

        QHeaderView::section {{
            background-color: {p['bg_secondary']};
            color: {p['text_secondary']};
            border: none;
            border-bottom: 1px solid {p['border']};
            padding: 6px 8px;
            font-weight: 600;
        }}

        /* ── Progress Bar ───────────────────────────────── */
        QProgressBar {{
            background-color: {p['bg_primary']};
            border: 1px solid {p['border']};
            border-radius: 4px;
            text-align: center;
            color: {p['text_primary']};
            height: 20px;
        }}

        QProgressBar::chunk {{
            background-color: {p['accent']};
            border-radius: 3px;
        }}

        /* ── Labels ─────────────────────────────────────── */
        QLabel {{
            background-color: transparent;
            color: {p['text_primary']};
            padding: 1px 0;
        }}

        QLabel[class="muted"] {{
            color: {p['text_muted']};
            font-size: 11px;
        }}

        QLabel[class="heading"] {{
            font-size: 16px;
            font-weight: 600;
            color: {p['text_secondary']};
            padding: 4px 0;
        }}

        QLabel[class="title"] {{
            font-size: 20px;
            font-weight: 700;
            color: {p['text_primary']};
            padding: 6px 0;
        }}

        /* ── Status Bar ─────────────────────────────────── */
        QStatusBar {{
            background-color: {p['bg_secondary']};
            color: {p['text_muted']};
            border-top: 1px solid {p['border_light']};
            padding: 4px 12px;
            font-size: 11px;
        }}

        QStatusBar QLabel {{
            color: {p['text_muted']};
            font-size: 11px;
        }}

        /* ── Frames ─────────────────────────────────────── */
        QFrame[class="card"] {{
            background-color: {p['bg_card']};
            border: 1px solid {p['border_light']};
            border-radius: 8px;
        }}

        QFrame[class="card"]:hover {{
            border-color: {p['accent']};
        }}

        /* ── Tool Tip ───────────────────────────────────── */
        QToolTip {{
            background-color: {p['bg_card']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            padding: 6px;
            border-radius: 4px;
            font-size: 12px;
        }}

        /* ── Message Box ────────────────────────────────── */
        QMessageBox {{
            background-color: {p['bg_secondary']};
        }}

        QMessageBox QLabel {{
            color: {p['text_primary']};
        }}
        """
        app.setStyleSheet(qss)


def get_theme() -> ThemeManager:
    """Return the singleton ThemeManager instance."""
    return ThemeManager()
