"""End-to-end smoke tests for the PyQt desktop UI.

These tests intentionally stay at the GUI boundary: they click and edit widgets
with Qt events, while patching dialogs, startup probes, and tool checks so the
suite does not install software, open external links, download data, or launch
bioinformatics commands.
"""
import re
import sys

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTextEdit,
)


SAMPLE_PROTEIN = "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH"
SAMPLE_FASTA = (
    ">seq1 Example protein 1\n"
    "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH\n"
    ">seq2 Example protein 2\n"
    "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGDLST\n"
)


@pytest.fixture
def ui_boundaries(monkeypatch, tmp_path):
    """Patch GUI boundaries that would otherwise block, mutate the host, or run tools."""
    messages = []

    def record(kind):
        def _recorder(parent, title, text, *args, **kwargs):
            messages.append({"kind": kind, "title": title, "text": text})
            if kind == "question":
                return QMessageBox.No
            return QMessageBox.Ok

        return _recorder

    monkeypatch.setattr(QMessageBox, "warning", record("warning"))
    monkeypatch.setattr(QMessageBox, "information", record("information"))
    monkeypatch.setattr(QMessageBox, "critical", record("critical"))
    monkeypatch.setattr(QMessageBox, "question", record("question"))

    sample_fasta = tmp_path / "sample.fasta"
    sample_fasta.write_text(SAMPLE_FASTA, encoding="utf-8")

    from PyQt5.QtWidgets import QFileDialog

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(sample_fasta), "FASTA Files (*.fasta)"),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(tmp_path / "export.txt"), "All Files (*)"),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )

    import ui.alignment_page as alignment_page
    import ui.protein_search_page as protein_search_page
    import ui.tools_page as tools_page
    from core.tool_state import ToolStatus

    class FakeToolRuntime:
        def get_tool_status(self, tool_id):
            return ToolStatus(installed=False, source="missing", executable_path=None)

        def get_missing_tools_for_feature(self, feature_id):
            return []

        def get_installable_tools(self, tool_ids):
            return []

    fake_runtime = FakeToolRuntime()
    monkeypatch.setattr(tools_page, "get_tool_runtime", lambda: fake_runtime)

    monkeypatch.setattr(
        protein_search_page.ProteinSearchPage,
        "scan_installed_databases",
        lambda self: None,
    )
    monkeypatch.setattr(
        protein_search_page.ProteinSearchPage,
        "_check_mmseqs_requirements",
        lambda self: None,
    )
    monkeypatch.setattr(
        protein_search_page.ProteinSearchPage,
        "_ensure_feature_tools",
        lambda self, feature_id, retry_callback: True,
    )
    monkeypatch.setattr(
        alignment_page.AlignmentPage,
        "check_system_requirements",
        lambda self: None,
    )
    monkeypatch.setattr(
        alignment_page.AlignmentPage,
        "_ensure_alignment_tools",
        lambda self: True,
    )
    monkeypatch.setattr(alignment_page, "is_pysca_installed", lambda: False)
    monkeypatch.setattr(alignment_page, "check_pairwise_aligner", lambda: False)

    return messages


@pytest.fixture
def exception_recorder(monkeypatch):
    exceptions = []
    original_hook = sys.excepthook

    def hook(exc_type, exc, tb):
        exceptions.append((exc_type, exc))

    monkeypatch.setattr(sys, "excepthook", hook)
    yield exceptions
    monkeypatch.setattr(sys, "excepthook", original_hook)


@pytest.fixture
def main_window(qt_app, ui_boundaries):
    from protein_gui import ProteinGUI

    window = ProteinGUI()
    window.show()
    qt_app.processEvents()
    yield window
    window.close()
    qt_app.processEvents()


def _visible_enabled(widget):
    return widget.isVisible() and widget.isEnabled()


def _set_text_widget(widget, text):
    if isinstance(widget, QTextEdit):
        widget.setPlainText(text)
    else:
        widget.setText(text)
    QApplication.processEvents()


def _button_text(button):
    return re.sub(r"\s+", " ", button.text()).strip()


def _is_safe_button(button):
    text = _button_text(button).lower()
    if not text:
        return True

    skip_patterns = [
        r"\brun\b",
        r"\binstall\b",
        r"\bdownload\b",
        r"\bbrowse\b",
        r"\bchoose\b",
        r"\bexport\b",
        r"\bsave\b",
        r"\bcancel\b",
        r"\bopen\b",
        r"\bcluster\b",
        r"\balign\b",
        r"\bcontinue\b",
        r"\bstart\b",
        r"use managed",
        r"use system",
        r"search .*database",
        r"search ncbi",
    ]
    return not any(re.search(pattern, text) for pattern in skip_patterns)


def test_main_window_tabs_and_home_navigation(main_window, qt_app):
    expected_tabs = [
        "Home",
        "Protein Search",
        "BLASTN",
        "Clustering",
        "Alignment",
        "Phylogenetic Analysis",
        "Motif Search",
        "Tools",
        "Databases",
    ]

    assert [main_window.tabs.tabText(i) for i in range(main_window.tabs.count())] == expected_tabs

    for index, title in enumerate(expected_tabs):
        main_window.tabs.setCurrentIndex(index)
        qt_app.processEvents()
        assert main_window.tabs.currentWidget() is not None
        assert title in main_window.tabs.tabText(index)

    home_targets = {
        "protein_search": "Protein Search",
        "blastn": "BLASTN",
        "clustering": "Clustering",
        "alignment": "Alignment",
        "phylo": "Phylogenetic Analysis",
        "motif_search": "Motif Search",
        "tools": "Tools",
        "database_downloads": "Databases",
    }

    for service, tab_title in home_targets.items():
        main_window.tabs.setCurrentIndex(0)
        main_window.home_page.service_selected.emit(service)
        qt_app.processEvents()
        assert main_window.tabs.tabText(main_window.tabs.currentIndex()) == tab_title


def test_safe_widget_crawler_clicks_and_edits_visible_controls(
    main_window,
    qt_app,
    exception_recorder,
):
    clicked = []
    edited = []

    for tab_index in range(main_window.tabs.count()):
        main_window.tabs.setCurrentIndex(tab_index)
        qt_app.processEvents()
        page = main_window.tabs.currentWidget()

        for line_edit in page.findChildren(QLineEdit):
            if _visible_enabled(line_edit) and not line_edit.isReadOnly():
                _set_text_widget(line_edit, "test")
                edited.append(("QLineEdit", tab_index))

        for text_edit in page.findChildren(QTextEdit):
            if _visible_enabled(text_edit) and not text_edit.isReadOnly():
                _set_text_widget(text_edit, SAMPLE_FASTA)
                edited.append(("QTextEdit", tab_index))

        for spin_box in page.findChildren(QSpinBox):
            if _visible_enabled(spin_box):
                spin_box.setValue(min(spin_box.maximum(), max(spin_box.minimum(), spin_box.value() + 1)))
                edited.append(("QSpinBox", tab_index))

        for combo in page.findChildren(QComboBox):
            if _visible_enabled(combo) and combo.count() > 1:
                combo.setCurrentIndex((combo.currentIndex() + 1) % combo.count())
                edited.append(("QComboBox", tab_index))

        toggles = page.findChildren(QRadioButton) + page.findChildren(QCheckBox)
        for toggle in toggles:
            if _visible_enabled(toggle):
                QTest.mouseClick(toggle, Qt.LeftButton)
                clicked.append((type(toggle).__name__, _button_text(toggle), tab_index))
                qt_app.processEvents()

        for button in page.findChildren(QPushButton):
            if _visible_enabled(button) and _is_safe_button(button):
                QTest.mouseClick(button, Qt.LeftButton)
                clicked.append(("QPushButton", _button_text(button), tab_index))
                qt_app.processEvents()

    assert clicked, "The crawler did not find any safe clickable controls."
    assert edited, "The crawler did not find any safe editable controls."
    assert exception_recorder == []


def test_protein_search_validation_flow(main_window, qt_app, exception_recorder):
    page = main_window.protein_search_page
    main_window.tabs.setCurrentWidget(page)
    qt_app.processEvents()

    page.paste_radio.setChecked(True)
    page.input_text.setPlainText("BAD123")
    QTest.mouseClick(page.process_button, Qt.LeftButton)
    qt_app.processEvents()

    assert page.status_label.text() == "Invalid amino acid sequence."
    assert exception_recorder == []

    page.input_text.setPlainText(SAMPLE_PROTEIN)
    qt_app.processEvents()
    assert page.sequence_counter.text() == f"{len(SAMPLE_PROTEIN)} amino acids"


def test_file_dialog_backed_inputs_load_sample_fasta(main_window, qt_app, exception_recorder):
    protein_page = main_window.protein_search_page
    main_window.tabs.setCurrentWidget(protein_page)
    protein_page.upload_radio.setChecked(True)
    qt_app.processEvents()
    QTest.mouseClick(protein_page.upload_fasta_button, Qt.LeftButton)
    qt_app.processEvents()

    assert "sample.fasta" in protein_page.fasta_file_label.text()
    assert protein_page.input_text.toPlainText().strip() == SAMPLE_PROTEIN

    alignment_page = main_window.alignment_page
    main_window.tabs.setCurrentWidget(alignment_page)
    qt_app.processEvents()
    alignment_browse_buttons = [
        button
        for button in alignment_page.findChildren(QPushButton)
        if _button_text(button) == "Browse"
    ]
    assert alignment_browse_buttons
    QTest.mouseClick(alignment_browse_buttons[0], Qt.LeftButton)
    qt_app.processEvents()

    assert "sample.fasta" in alignment_page.file_path_input.text()
    assert "2" in alignment_page.file_info_label.text()

    motif_page = main_window.motif_search_page
    main_window.tabs.setCurrentWidget(motif_page)
    qt_app.processEvents()
    browse_buttons = [
        button
        for button in motif_page.findChildren(QPushButton)
        if _button_text(button) == "Browse"
    ]
    assert browse_buttons
    QTest.mouseClick(browse_buttons[0], Qt.LeftButton)
    qt_app.processEvents()

    assert motif_page.current_fasta_path
    assert motif_page.file_info_label.text() == "2 sequences found in file"
    assert exception_recorder == []


def test_motif_preset_populates_expected_pattern(main_window, qt_app, exception_recorder):
    page = main_window.motif_search_page
    main_window.tabs.setCurrentWidget(page)
    qt_app.processEvents()

    QTest.mouseClick(page.motif_widget.nglyc_preset_btn, Qt.LeftButton)
    qt_app.processEvents()

    assert page.motif_widget.get_motif() == ["N", "~P", "ST"]
    valid, error = page.motif_widget.validate()
    assert valid is True
    assert error == ""
    assert exception_recorder == []
