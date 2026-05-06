"""Deterministic UI layout and resize checks for result screens and pop-outs."""
from pathlib import Path

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QPushButton, QWidget

from tests.test_ui_e2e import SAMPLE_FASTA, SAMPLE_PROTEIN
from tests.test_ui_workflows import workflow_boundaries, workflow_window


VIEWPORTS = [(900, 600), (1100, 750), (1440, 900)]


@pytest.fixture
def ui_artifact_dir(tmp_path):
    path = tmp_path / "ui_artifacts"
    path.mkdir()
    return path


def _button_text(button):
    return " ".join(button.text().split())


def _buttons_by_text(parent, text):
    return [
        button
        for button in parent.findChildren(QPushButton)
        if _button_text(button) == text
    ]


def _assert_widget_has_size(widget, min_width=24, min_height=20):
    assert widget.width() >= min_width, f"{widget!r} width is {widget.width()}"
    assert widget.height() >= min_height, f"{widget!r} height is {widget.height()}"


def _assert_widget_inside_ancestor(widget: QWidget, ancestor: QWidget):
    top_left = widget.mapTo(ancestor, widget.rect().topLeft())
    bottom_right = widget.mapTo(ancestor, widget.rect().bottomRight())
    bounds = ancestor.rect()
    assert bounds.contains(top_left), f"{widget!r} top-left {top_left} outside {bounds}"
    assert bounds.contains(bottom_right), f"{widget!r} bottom-right {bottom_right} outside {bounds}"


def _assert_button_usable(button, ancestor):
    assert button.isVisible(), f"{_button_text(button)!r} is not visible"
    assert button.isEnabled(), f"{_button_text(button)!r} is not enabled"
    _assert_widget_has_size(button)
    _assert_widget_inside_ancestor(button, ancestor)


def _save_screenshot(widget, artifact_dir, name):
    path = artifact_dir / f"{name}.png"
    assert widget.grab().save(str(path), "PNG")
    assert path.exists()
    assert path.stat().st_size > 0
    return path


def test_alignment_viewer_dialog_resizes_and_toolbar_buttons_work(
    qt_app,
    workflow_boundaries,
    ui_artifact_dir,
):
    from ui.dialogs.alignment_viewer_dialog import AlignmentViewerDialog

    dialog = AlignmentViewerDialog()
    assert dialog.load_alignment(SAMPLE_FASTA)
    dialog.show()
    qt_app.processEvents()

    critical_buttons = [
        dialog.load_custom_btn,
        dialog.zoom_out_btn,
        dialog.zoom_in_btn,
        dialog.fit_btn,
        dialog.export_png_btn,
        dialog.export_fasta_btn,
        dialog.close_btn,
    ]

    for width, height in VIEWPORTS:
        dialog.resize(width, height)
        qt_app.processEvents()

        assert dialog.canvas.row_count() == 2
        assert dialog.canvas.alignment_width() == len(SAMPLE_PROTEIN)
        _assert_widget_has_size(dialog.scroll.viewport(), min_width=320, min_height=220)
        _assert_widget_has_size(dialog.canvas, min_width=300, min_height=36)

        for button in critical_buttons:
            _assert_button_usable(button, dialog)

        _save_screenshot(dialog, ui_artifact_dir, f"alignment_viewer_{width}x{height}")

    old_cell = dialog.canvas.cell_size()[0]
    QTest.mouseClick(dialog.zoom_in_btn, Qt.LeftButton)
    qt_app.processEvents()
    assert dialog.canvas.cell_size()[0] > old_cell

    QTest.mouseClick(dialog.zoom_out_btn, Qt.LeftButton)
    qt_app.processEvents()
    QTest.mouseClick(dialog.fit_btn, Qt.LeftButton)
    qt_app.processEvents()
    assert dialog.canvas.cell_size()[0] >= dialog.canvas.minimum_cell()

    QTest.mouseClick(dialog.consensus_check, Qt.LeftButton)
    qt_app.processEvents()
    assert dialog.canvas.show_consensus() is True
    assert dialog.canvas.row_count() == 3

    QTest.mouseClick(dialog.export_fasta_btn, Qt.LeftButton)
    QTest.mouseClick(dialog.export_png_btn, Qt.LeftButton)
    QTest.mouseClick(dialog.load_custom_btn, Qt.LeftButton)
    qt_app.processEvents()

    assert any(m["title"] == "Export" for m in workflow_boundaries["messages"])
    assert any(m["title"] == "Color scheme" for m in workflow_boundaries["messages"])

    dialog.hide()
    qt_app.processEvents()


def test_alignment_results_screen_resizes_without_losing_actions(
    workflow_window,
    qt_app,
    ui_artifact_dir,
    monkeypatch,
):
    class FakeViewer:
        def load_alignment(self, content):
            return True

        def show(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass

    page = workflow_window.alignment_page
    monkeypatch.setattr(page, "_ensure_alignment_viewer_dialog", lambda: FakeViewer())
    page.on_alignment_finished(SAMPLE_FASTA, "/tmp/fake-alignment.fasta")
    workflow_window.tabs.setCurrentWidget(page)

    for width, height in VIEWPORTS:
        workflow_window.resize(width, height)
        qt_app.processEvents()

        assert page._results_panel.isVisible()
        assert page.results_tabs.isVisible()
        assert page.raw_alignment_text.toPlainText() == SAMPLE_FASTA
        _assert_widget_has_size(page.results_tabs, min_width=320, min_height=180)
        _assert_widget_has_size(page.raw_alignment_text, min_width=260, min_height=120)
        _assert_button_usable(page.open_viewer_btn, workflow_window)

        for text in ["Run Quick SCA", "Run Full pySCA", "Export as FASTA", "Export as Clustal"]:
            buttons = _buttons_by_text(page, text)
            assert buttons, f"Missing {text!r}"
            for button in buttons:
                if button.isVisible() and button.isEnabled():
                    _assert_button_usable(button, workflow_window)

        _save_screenshot(workflow_window, ui_artifact_dir, f"alignment_results_{width}x{height}")


def test_clustering_results_screen_resizes_without_losing_actions(
    workflow_window,
    qt_app,
    ui_artifact_dir,
):
    page = workflow_window.clustering_page
    workflow_window.tabs.setCurrentWidget(page)

    stats = {
        "total_sequences": 2,
        "num_clusters": 1,
        "largest_cluster": 2,
        "avg_cluster_size": 2.0,
        "singletons": 0,
        "cluster_size_distribution": {2: 1},
        "clusters": {"seq1": ["seq1", "seq2"]},
    }
    page.on_clustering_finished(stats, "/tmp/representatives.fasta", "/tmp/clusters.tsv")

    for width, height in VIEWPORTS:
        workflow_window.resize(width, height)
        qt_app.processEvents()

        assert page.results_tabs.isVisible()
        assert page.clusters_table.rowCount() == 1
        _assert_widget_has_size(page.results_tabs, min_width=320, min_height=160)
        _assert_widget_has_size(page.summary_text, min_width=240, min_height=80)

        for text in ["Export as TSV (Cluster Assignments)", "Export Representatives as FASTA"]:
            buttons = _buttons_by_text(page, text)
            assert buttons, f"Missing {text!r}"
            for button in buttons:
                if button.isVisible() and button.isEnabled():
                    _assert_button_usable(button, workflow_window)

        _save_screenshot(workflow_window, ui_artifact_dir, f"clustering_results_{width}x{height}")


def test_motif_results_screen_resizes_without_losing_actions(
    workflow_window,
    qt_app,
    ui_artifact_dir,
):
    from core.motif_worker import ProteinRecord

    page = workflow_window.motif_search_page
    workflow_window.tabs.setCurrentWidget(page)
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

    for width, height in VIEWPORTS:
        workflow_window.resize(width, height)
        qt_app.processEvents()

        assert page.results_tabs.isVisible()
        assert page.results_table.rowCount() == 1
        _assert_widget_has_size(page.results_tabs, min_width=320, min_height=160)
        _assert_widget_has_size(page.summary_text, min_width=240, min_height=100)
        _assert_widget_has_size(page.results_table, min_width=260, min_height=120)

        for text in ["Export as CSV", "Export Summary"]:
            buttons = _buttons_by_text(page, text)
            assert buttons, f"Missing {text!r}"
            for button in buttons:
                if button.isVisible() and button.isEnabled():
                    _assert_button_usable(button, workflow_window)

        _save_screenshot(workflow_window, ui_artifact_dir, f"motif_results_{width}x{height}")
