"""Capture a UI screenshot pack for manual/LLM-assisted review.

Run from the repository root:

    conda run -n bio_env python scripts/capture_ui_review_screenshots.py

Screenshots are written to test_artifacts/ui_review/. The script avoids external
tools, downloads, real file dialogs, and modal message boxes.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "protein_gui_test_cache"))
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "protein_gui_test_mpl"))

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import QSettings, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox, QScrollArea, QTabWidget  # noqa: E402

SAMPLE_PROTEIN = "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH"
SAMPLE_FASTA = (
    ">seq1 Example protein 1\n"
    "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH\n"
    ">seq2 Example protein 2\n"
    "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGDLST\n"
)

OUT_DIR = ROOT / "test_artifacts" / "ui_review"


def _configure_qt_settings() -> None:
    settings_dir = Path(tempfile.gettempdir()) / "protein_gui_review_qsettings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(settings_dir))
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(settings_dir))


def _patch_boundaries(sample_fasta: Path, export_path: Path) -> list[dict]:
    messages: list[dict] = []

    def record(kind):
        def _recorder(parent, title, text, *args, **kwargs):
            messages.append({"kind": kind, "title": title, "text": text})
            if kind == "question":
                return QMessageBox.No
            return QMessageBox.Ok

        return _recorder

    QMessageBox.warning = record("warning")
    QMessageBox.information = record("information")
    QMessageBox.critical = record("critical")
    QMessageBox.question = record("question")

    QFileDialog.getOpenFileName = lambda *args, **kwargs: (str(sample_fasta), "FASTA Files (*.fasta)")
    QFileDialog.getSaveFileName = lambda *args, **kwargs: (str(export_path), "All Files (*)")
    QFileDialog.getExistingDirectory = lambda *args, **kwargs: str(sample_fasta.parent)

    import ui.alignment_page as alignment_page
    import ui.clustering_page as clustering_page
    import ui.protein_search_page as protein_search_page
    import ui.tools_page as tools_page
    from core.tool_state import ToolStatus

    class FakeToolRuntime:
        def get_tool_status(self, tool_id):
            return ToolStatus(installed=True, source="review", executable_path=tool_id)

        def get_missing_tools_for_feature(self, feature_id):
            return []

        def get_installable_tools(self, tool_ids):
            return []

    fake_runtime = FakeToolRuntime()
    tools_page.get_tool_runtime = lambda: fake_runtime
    clustering_page.get_tool_runtime = lambda: fake_runtime

    protein_search_page.ProteinSearchPage.scan_installed_databases = lambda self: None
    protein_search_page.ProteinSearchPage._check_mmseqs_requirements = lambda self: None
    protein_search_page.ProteinSearchPage._ensure_feature_tools = (
        lambda self, feature_id, retry_callback: True
    )
    alignment_page.AlignmentPage.check_system_requirements = lambda self: None
    alignment_page.AlignmentPage._ensure_alignment_tools = lambda self: True
    alignment_page.AlignmentPage._run_builtin_sca = lambda self, silent=False: None
    alignment_page.is_pysca_installed = lambda: False
    alignment_page.check_pairwise_aligner = lambda: False
    clustering_page.ClusteringPage.check_system_requirements = lambda self: None
    clustering_page.ClusteringPage._ensure_clustering_tools = lambda self: True
    clustering_page.create_distribution_chart = (
        lambda stats, path: _write_placeholder_chart(path)
    )

    return messages


def _write_placeholder_chart(path: str):
    pixmap = QPixmap(900, 420)
    pixmap.fill(QColor("#ffffff"))
    painter = QPainter(pixmap)
    painter.fillRect(40, 80, 160, 260, QColor("#7c3aed"))
    painter.fillRect(240, 160, 160, 180, QColor("#2563eb"))
    painter.fillRect(440, 220, 160, 120, QColor("#16a34a"))
    painter.setPen(QColor("#111827"))
    painter.drawText(40, 40, "Cluster Distribution")
    painter.drawText(40, 380, "Review placeholder chart")
    painter.end()
    pixmap.save(path, "PNG")
    return True, path


def _save_widget(widget, name: str, width: int, height: int, app: QApplication, records: list[dict]) -> None:
    widget.show()
    app.processEvents()
    widget.resize(width, height)
    app.processEvents()
    app.processEvents()
    path = OUT_DIR / f"{name}_{width}x{height}.png"
    ok = widget.grab().save(str(path), "PNG")
    if not ok:
        raise RuntimeError(f"Failed to save screenshot: {path}")
    records.append({"name": name, "width": width, "height": height, "path": str(path.relative_to(ROOT))})


def _fake_search_hits():
    from utils.results_parser import SearchHit

    return [
        SearchHit(
            rank=1,
            accession="P12345",
            description="Fake hemoglobin hit [Homo sapiens]",
            evalue=1e-80,
            score=250.0,
            identity_percent=96.0,
            alignment_length=55,
            query_coverage=98.0,
            full_sequence=SAMPLE_PROTEIN,
            sequence_length=len(SAMPLE_PROTEIN),
            organism="Homo sapiens",
        ),
        SearchHit(
            rank=2,
            accession="Q67890",
            description="Fake globin-like protein [Mus musculus]",
            evalue=3e-40,
            score=180.0,
            identity_percent=78.0,
            alignment_length=52,
            query_coverage=90.0,
            full_sequence="MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGDLST",
            sequence_length=54,
            organism="Mus musculus",
        ),
    ]


def _capture_top_level_defaults(window, app: QApplication, records: list[dict]) -> None:
    tab_names = [
        "home",
        "protein_search",
        "blastn",
        "clustering",
        "alignment",
        "motif_search",
        "tools",
        "databases",
    ]
    for index, name in enumerate(tab_names):
        window.tabs.setCurrentIndex(index)
        _save_widget(window, f"default_{name}", 1100, 750, app, records)


def _capture_protein_results(window, app: QApplication, records: list[dict]) -> None:
    page = window.protein_search_page
    window.tabs.setCurrentWidget(page)
    page.input_text.setPlainText(SAMPLE_PROTEIN)
    page.search_start_time = 0
    page.current_results_html = "<html><body>fake protein results</body></html>"
    page._on_blast_finished(page.current_results_html, _fake_search_hits())
    for width, height in [(900, 600), (1100, 750), (1440, 900)]:
        _save_widget(window, "protein_results", width, height, app, records)


def _capture_blastn_results(window, app: QApplication, records: list[dict]) -> None:
    page = window.blastn_page
    window.tabs.setCurrentWidget(page)
    page.input_text.setPlainText("ATGGTGCTGTCTCCAGCCGACAAGACCAACGTCAAGGCCGCCTGG")
    page.search_start_time = 0
    page.current_results_html = "<html><body>fake nucleotide results</body></html>"
    page.on_blast_finished(page.current_results_html, _fake_search_hits())
    for width, height in [(900, 600), (1100, 750), (1440, 900)]:
        _save_widget(window, "blastn_results", width, height, app, records)


def _capture_tab_widget_pages(
    window,
    tab_widget: QTabWidget,
    prefix: str,
    app: QApplication,
    records: list[dict],
) -> None:
    for index in range(tab_widget.count()):
        title = "_".join(tab_widget.tabText(index).lower().replace("/", " ").split())
        tab_widget.setCurrentIndex(index)
        _save_widget(window, f"{prefix}_{title}", 1100, 750, app, records)


def _capture_alignment_viewer(app: QApplication, records: list[dict]) -> None:
    from ui.dialogs.alignment_viewer_dialog import AlignmentViewerDialog

    dialog = AlignmentViewerDialog()
    dialog.load_alignment(SAMPLE_FASTA)
    for width, height in [(960, 640), (1200, 800)]:
        _save_widget(dialog, "alignment_viewer", width, height, app, records)
    dialog.hide()


def _capture_alignment_results(window, app: QApplication, records: list[dict]) -> None:
    class FakeViewer:
        def load_alignment(self, content):
            return True

        def show(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass

    page = window.alignment_page
    page._ensure_alignment_viewer_dialog = lambda: FakeViewer()
    page.on_alignment_finished(SAMPLE_FASTA, "/tmp/review-alignment.fasta")
    window.tabs.setCurrentWidget(page)
    for width, height in [(900, 600), (1100, 750), (1440, 900)]:
        _save_widget(window, "alignment_results", width, height, app, records)
    _capture_tab_widget_pages(window, page.results_tabs, "alignment_tab", app, records)


def _capture_clustering_results(window, app: QApplication, records: list[dict]) -> None:
    page = window.clustering_page
    window.tabs.setCurrentWidget(page)
    page.on_clustering_finished(
        {
            "total_sequences": 2,
            "num_clusters": 1,
            "largest_cluster": 2,
            "avg_cluster_size": 2.0,
            "singletons": 0,
            "cluster_size_distribution": {2: 1},
            "clusters": {"seq1": ["seq1", "seq2"]},
        },
        "/tmp/review-representatives.fasta",
        "/tmp/review-clusters.tsv",
    )
    for width, height in [(900, 600), (1100, 750), (1440, 900)]:
        _save_widget(window, "clustering_results", width, height, app, records)
    _capture_tab_widget_pages(window, page.results_tabs, "clustering_tab", app, records)


def _capture_motif_results(window, app: QApplication, records: list[dict]) -> None:
    from core.motif_worker import ProteinRecord

    page = window.motif_search_page
    window.tabs.setCurrentWidget(page)
    record = ProteinRecord(
        seq=SAMPLE_PROTEIN,
        id="seq1",
        species="Homo sapiens",
        phylo=["Mammalia"],
        indices=[1, 12],
    )
    page.on_search_finished(
        {
            "motif": ["N", "~P", "ST"],
            "total_sequences": 1,
            "total_motifs": 2,
            "category_stats": {"Mammalia": {"count": 1, "motifs": 2}},
            "categories": {
                "Actinopterygii": [],
                "Mammalia": [record],
                "Aves": [],
                "Amphibia": [],
                "Other": [],
            },
        }
    )
    for width, height in [(900, 600), (1100, 750), (1440, 900)]:
        _save_widget(window, "motif_results", width, height, app, records)
    _capture_tab_widget_pages(window, page.results_tabs, "motif_tab", app, records)


def _capture_scrolled_states(window, app: QApplication, records: list[dict]) -> None:
    targets = [
        ("protein_search_scrolled", window.protein_search_page),
        ("blastn_scrolled", window.blastn_page),
        ("alignment_scrolled", window.alignment_page),
        ("clustering_scrolled", window.clustering_page),
        ("motif_search_scrolled", window.motif_search_page),
    ]
    for name, page in targets:
        window.tabs.setCurrentWidget(page)
        for scroll in page.findChildren(QScrollArea):
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        _save_widget(window, name, 1100, 750, app, records)


def _capture_dark_theme(window, app: QApplication, records: list[dict]) -> None:
    from ui.theme import get_theme

    theme = get_theme()
    theme.set_theme("dark")
    app.processEvents()
    for index, name in [(0, "home"), (1, "protein_search"), (4, "alignment_results"), (5, "motif_results")]:
        window.tabs.setCurrentIndex(index)
        _save_widget(window, f"dark_{name}", 1100, 750, app, records)
    theme.set_theme("light")
    app.processEvents()


def _capture_dialogs(app: QApplication, records: list[dict]) -> None:
    from ui.dialogs.chart_maximize_dialog import ChartMaximizeDialog
    from ui.dialogs.cluster_selection_dialog import ClusterSelectionDialog
    from ui.dialogs.clustering_config_dialog import ClusteringConfigDialog
    from ui.dialogs.nucleotide_search_dialog import NucleotideSearchDialog
    from ui.dialogs.protein_search_dialog import ProteinSearchDialog

    dialogs = []
    hits = _fake_search_hits()
    dialogs.append(("dialog_protein_search", ProteinSearchDialog()))
    dialogs.append(("dialog_nucleotide_search", NucleotideSearchDialog()))
    dialogs.append(("dialog_cluster_selection", ClusterSelectionDialog(hits)))
    dialogs.append(("dialog_clustering_config", ClusteringConfigDialog(hits, [hits[0]])))

    pixmap = QPixmap(900, 420)
    pixmap.fill(QColor("#ffffff"))
    painter = QPainter(pixmap)
    painter.fillRect(80, 80, 180, 260, QColor("#7c3aed"))
    painter.fillRect(330, 160, 180, 180, QColor("#2563eb"))
    painter.fillRect(580, 220, 180, 120, QColor("#16a34a"))
    painter.setPen(QColor("#111827"))
    painter.drawText(80, 40, "Cluster Distribution")
    painter.end()
    dialogs.append(("dialog_chart_maximize", ChartMaximizeDialog(pixmap, "Cluster Distribution Chart")))

    for name, dialog in dialogs:
        _save_widget(dialog, name, dialog.width(), dialog.height(), app, records)
        dialog.hide()


def _write_index(records: list[dict], messages: list[dict]) -> None:
    (OUT_DIR / "manifest.json").write_text(
        json.dumps({"screenshots": records, "messages": messages}, indent=2),
        encoding="utf-8",
    )
    lines = ["# UI Review Screenshots", ""]
    for record in records:
        rel = Path(record["path"]).name
        lines.append(f"## {record['name']} {record['width']}x{record['height']}")
        lines.append(f"![{record['name']}](./{rel})")
        lines.append("")
    if messages:
        lines.append("## Captured Messages")
        lines.append("```json")
        lines.append(json.dumps(messages, indent=2))
        lines.append("```")
    (OUT_DIR / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _write_contact_sheet(records: list[dict]) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return

    images = [ROOT / record["path"] for record in records]
    thumb_w, thumb_h = 360, 245
    pad = 18
    label_h = 28
    cols = 2
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new(
        "RGB",
        (cols * (thumb_w + pad) + pad, rows * (thumb_h + label_h + pad) + pad),
        "white",
    )
    draw = ImageDraw.Draw(sheet)

    for idx, image_path in enumerate(images):
        image = Image.open(image_path).convert("RGB")
        image.thumbnail((thumb_w, thumb_h), Image.LANCZOS)
        x = pad + (idx % cols) * (thumb_w + pad)
        y = pad + (idx // cols) * (thumb_h + label_h + pad)
        draw.text((x, y), image_path.name, fill=(0, 0, 0))
        sheet.paste(image, (x, y + label_h))

    sheet.save(OUT_DIR / "contact_sheet.png")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for child in OUT_DIR.iterdir():
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)

    sample_fasta = OUT_DIR / "sample.fasta"
    sample_fasta.write_text(SAMPLE_FASTA, encoding="utf-8")
    export_path = OUT_DIR / "export.tmp"

    _configure_qt_settings()
    app = QApplication.instance() or QApplication(["ui-review"])
    messages = _patch_boundaries(sample_fasta, export_path)

    from protein_gui import ProteinGUI

    from ui.theme import get_theme

    get_theme().apply(app)
    window = ProteinGUI()
    records: list[dict] = []

    _capture_top_level_defaults(window, app, records)
    _capture_protein_results(window, app, records)
    _capture_blastn_results(window, app, records)
    _capture_alignment_viewer(app, records)
    _capture_alignment_results(window, app, records)
    _capture_clustering_results(window, app, records)
    _capture_motif_results(window, app, records)
    _capture_scrolled_states(window, app, records)
    _capture_dialogs(app, records)
    _capture_dark_theme(window, app, records)

    window.close()
    app.processEvents()
    _write_index(records, messages)
    _write_contact_sheet(records)

    print(f"Captured {len(records)} screenshots in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
