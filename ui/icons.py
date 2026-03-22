"""
Load Feather SVG icons from ui/feather/ and return QIcon objects.
"""
import os

from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtCore import QByteArray, Qt, QRectF, QSize
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QPushButton

from .theme import get_theme


FEATHER_DIR = os.path.join(os.path.dirname(__file__), "feather")
_icon_cache = {}


def _clear_cache():
    """Clear the icon cache. Called when theme changes."""
    global _icon_cache
    _icon_cache = {}


def _get_resolved_color(color: str = None) -> str:
    """Return the color to use. If None, use theme's text_primary."""
    if color is not None:
        return color
    return get_theme().get("text_primary")


def feather_icon(name: str, size: int = 16, color: str = None) -> QIcon:
    """
    Load a Feather SVG icon and return it as a QIcon.

    Args:
        name: Icon name (without .svg extension)
        size: Icon size in pixels
        color: Stroke color. If None, uses theme's text_primary.

    Returns:
        QIcon with the rendered icon, or empty QIcon if file doesn't exist.
    """
    resolved_color = _get_resolved_color(color)
    cache_key = (name, size, resolved_color)

    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    path = os.path.join(FEATHER_DIR, f"{name}.svg")
    if not os.path.exists(path):
        return QIcon()

    try:
        with open(path, "r", encoding="utf-8") as f:
            svg_str = f.read()

        # Replace stroke="currentColor" (or stroke='currentColor') with the specified color
        if 'stroke="currentColor"' in svg_str:
            svg_str = svg_str.replace('stroke="currentColor"', f'stroke="{resolved_color}"')
        elif "stroke='currentColor'" in svg_str:
            svg_str = svg_str.replace("stroke='currentColor'", f"stroke='{resolved_color}'")

        svg_bytes = QByteArray(svg_str.encode("utf-8"))
        renderer = QSvgRenderer(svg_bytes)

        if not renderer.isValid():
            return QIcon()

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()

        icon = QIcon(pixmap)
        _icon_cache[cache_key] = icon
        return icon
    except Exception:
        return QIcon()


def feather_icon_path(name: str, size: int = 16, color: str = None) -> str:
    """
    Render a Feather icon to a temporary PNG and return its file path.
    Useful for QSS `image: url(...)` properties.
    """
    import tempfile
    resolved_color = _get_resolved_color(color)
    cache_key = ("path", name, size, resolved_color)

    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    path = os.path.join(FEATHER_DIR, f"{name}.svg")
    if not os.path.exists(path):
        return ""

    try:
        with open(path, "r", encoding="utf-8") as f:
            svg_str = f.read()

        if 'stroke="currentColor"' in svg_str:
            svg_str = svg_str.replace('stroke="currentColor"', f'stroke="{resolved_color}"')
        elif "stroke='currentColor'" in svg_str:
            svg_str = svg_str.replace("stroke='currentColor'", f"stroke='{resolved_color}'")

        svg_bytes = QByteArray(svg_str.encode("utf-8"))
        renderer = QSvgRenderer(svg_bytes)
        if not renderer.isValid():
            return ""

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix=f"feather_{name}_")
        pixmap.save(tmp.name, "PNG")
        tmp.close()

        _icon_cache[cache_key] = tmp.name
        return tmp.name
    except Exception:
        return ""


def set_button_icon(button: QPushButton, icon_name: str, size: int = 16, color: str = None):
    """
    Set both the icon and icon size on a QPushButton.

    Args:
        button: The QPushButton to configure
        icon_name: Feather icon name (without .svg extension)
        size: Icon size in pixels
        color: Stroke color. If None, uses theme's text_primary.
    """
    icon = feather_icon(icon_name, size=size, color=color)
    button.setIcon(icon)
    sizes = icon.availableSizes()
    button.setIconSize(sizes[0] if sizes else QSize(size, size))


# Clear cache when theme changes
get_theme().theme_changed.connect(_clear_cache)
