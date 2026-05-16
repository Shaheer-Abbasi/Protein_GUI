"""Embedded 3D structure viewer (3Dmol.js in QWebEngineView when available)."""

from __future__ import annotations

import base64
import html as html_module
import re
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence

from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.structure_mapping import (
    INLINE_STRUCTURE_CHAR_LIMIT,
    ResidueColor,
    build_3dmol_html,
    build_3dmol_html_sidecar,
    bundled_3dmol_path,
)

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineSettings
except ImportError:
    QWebEngineSettings = None  # type: ignore[misc, assignment]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

WEBENGINE_INSTALL_CMD = "pip install PyQtWebEngine"


def resources_base_url() -> QUrl:
    resources = (_PROJECT_ROOT / "resources").resolve()
    return QUrl.fromLocalFile(str(resources) + "/")


try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView

    _WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None  # type: ignore[misc, assignment]
    _WEBENGINE_AVAILABLE = False


class _PlaceholderWithCopy(QWidget):
    """Explains missing WebEngine and offers one-click clipboard copy."""

    def __init__(self, body: str, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        lab = QLabel(body)
        lab.setProperty("class", "muted")
        lab.setWordWrap(True)
        outer.addWidget(lab)
        bt = QPushButton("Copy install command")
        bt.clicked.connect(self._copy)
        outer.addWidget(bt)

    def _copy(self) -> None:
        QApplication.clipboard().setText(WEBENGINE_INSTALL_CMD)


class StructureViewerWidget(QWidget):
    """3Dmol viewer with representation selector, reset, and PNG export."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._web: Optional[QWebEngineView] = None
        self._plain: Optional[str] = None
        self._fmt: str = "pdb"
        self._chain: str = "A"
        self._residues: List[ResidueColor] = []
        self._representation: str = "cartoon"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Style:"))
        self._repr_combo = QComboBox()
        self._repr_combo.addItems(["cartoon", "cartoon+stick", "surface"])
        self._repr_combo.currentTextChanged.connect(self._on_repr_changed)
        bar.addWidget(self._repr_combo)

        self._reset_btn = QPushButton("Reset view")
        self._reset_btn.clicked.connect(self._on_reset)
        bar.addWidget(self._reset_btn)

        self._png_btn = QPushButton("Export PNG…")
        self._png_btn.clicked.connect(self._on_export_png)
        bar.addWidget(self._png_btn)
        bar.addStretch()
        root.addLayout(bar)

        self._body: QWidget
        if not _WEBENGINE_AVAILABLE:
            self._body = _PlaceholderWithCopy(
                "3D structure view requires PyQtWebEngine. "
                "Use “Copy install command”, then paste in a terminal."
            )
        else:
            try:
                bundled_3dmol_path()
            except FileNotFoundError:
                miss = QLabel(
                    "Bundled 3Dmol script missing (resources/js/3Dmol-min.js)."
                )
                miss.setProperty("class", "muted")
                miss.setWordWrap(True)
                self._body = miss
            else:
                self._web = QWebEngineView(self)
                self._body = self._web
                if QWebEngineSettings is not None:
                    s = self._web.settings()
                    try:
                        wa = QWebEngineSettings.WebAttribute
                        s.setAttribute(wa.LocalContentCanAccessFileUrls, True)
                        s.setAttribute(wa.LocalContentCanAccessRemoteUrls, True)
                    except Exception:
                        pass

        self._temp_view_dir: Optional[str] = None

        root.addWidget(self._body, 1)

    def has_viewer(self) -> bool:
        return self._web is not None

    def _teardown_sidecar_dir(self) -> None:
        if self._temp_view_dir and Path(self._temp_view_dir).is_dir():
            shutil.rmtree(self._temp_view_dir, ignore_errors=True)
        self._temp_view_dir = None

    def _reload_html(self) -> None:
        if not self._web or self._plain is None:
            return
        try:
            if len(self._plain) > INLINE_STRUCTURE_CHAR_LIMIT:
                self._reload_html_sidecar()
            else:
                self._teardown_sidecar_dir()
                h = build_3dmol_html(
                    self._plain,
                    self._fmt,
                    self._residues,
                    self._chain,
                    representation=self._representation,
                )
                self._web.setHtml(h, resources_base_url())
        except Exception as exc:
            self._teardown_sidecar_dir()
            msg = html_module.escape(str(exc))
            self._web.setHtml(
                "<html><body style='background:#111318;color:#f88;padding:12px;'>"
                f"Could not build 3D view: {msg}</body></html>"
            )

    def _reload_html_sidecar(self) -> None:
        self._teardown_sidecar_dir()
        d = tempfile.mkdtemp(prefix="senlab_struct_view_")
        self._temp_view_dir = d
        ext = ".cif" if self._fmt.lower().strip() == "cif" else ".pdb"
        model_name = f"structure{ext}"
        mp = Path(d) / model_name
        mp.write_text(self._plain, encoding="utf-8", errors="replace")
        script_uri = bundled_3dmol_path().as_uri()
        body = build_3dmol_html_sidecar(
            model_name,
            self._fmt,
            self._residues,
            self._chain,
            representation=self._representation,
            script_src_uri=script_uri,
        )
        idx = Path(d) / "index.html"
        idx.write_text(body, encoding="utf-8")
        self._web.load(QUrl.fromLocalFile(str(idx.resolve())))

    def _on_repr_changed(self, text: str) -> None:
        self._representation = (text or "cartoon").strip().lower()
        self._reload_html()

    # --- Planned public API ---
    def set_structure(self, pdb_text: str, fmt: str, focus_chain: str) -> None:
        """Load PDB/mmCIF text; keeps current residue colouring until overwritten."""
        self._plain = pdb_text
        self._fmt = fmt
        self._chain = (focus_chain or "A").strip() or "A"
        self._reload_html()

    def set_residue_colors(self, residues: Sequence[ResidueColor]) -> None:
        """Update sector / residue colouring for the loaded structure."""
        self._residues = list(residues)
        self._reload_html()

    def set_representation(self, name: str) -> None:
        """cartoon | cartoon+stick | surface."""
        rep = (name or "cartoon").strip().lower()
        self._representation = rep
        idx = self._repr_combo.findText(rep)
        if idx >= 0:
            self._repr_combo.blockSignals(True)
            self._repr_combo.setCurrentIndex(idx)
            self._repr_combo.blockSignals(False)
        self._reload_html()

    def clear(self) -> None:
        self._teardown_sidecar_dir()
        self._plain = None
        self._residues = []
        if self._web:
            self._web.setHtml(
                "<html><body style='background:#111318;color:#aaa;padding:12px;'>"
                "No structure loaded.</body></html>"
            )

    def _on_reset(self) -> None:
        if not self._web:
            return
        self._web.page().runJavaScript(
            "window.__STRUCTURE_VIEWER__ && window.__STRUCTURE_VIEWER__.reset "
            "&& window.__STRUCTURE_VIEWER__.reset();"
        )

    def _on_export_png(self) -> None:
        if not self._web:
            QMessageBox.information(self, "Export", "Web engine viewer is not available.")
            return

        def _save(uri) -> None:
            if not uri or not isinstance(uri, str):
                QMessageBox.warning(self, "Export", "Could not capture the 3D view.")
                return
            m = re.match(r"data:image/png;base64,(.+)", uri)
            if not m:
                QMessageBox.warning(self, "Export", "Unexpected image data from viewer.")
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "Save structure image", "structure.png", "PNG (*.png)"
            )
            if not path:
                return
            try:
                Path(path).write_bytes(base64.b64decode(m.group(1)))
            except OSError as e:
                QMessageBox.warning(self, "Export", f"Could not save file:\n{e}")
                return
            QMessageBox.information(self, "Export", f"Saved:\n{path}")

        self._web.page().runJavaScript(
            "window.__STRUCTURE_VIEWER__ && window.__STRUCTURE_VIEWER__.pngURI "
            "&& window.__STRUCTURE_VIEWER__.pngURI();",
            _save,
        )
