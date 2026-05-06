"""Golden-path UI workflow tests with fake worker results."""

import pytest
from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QPushButton

from tests.test_ui_e2e import SAMPLE_FASTA, SAMPLE_PROTEIN


@pytest.fixture
def workflow_boundaries(monkeypatch, tmp_path):
    """Keep workflow tests deterministic and isolated from external tools."""
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
    export_path = tmp_path / "export.txt"

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(sample_fasta), "FASTA Files (*.fasta)"),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(export_path), "All Files (*)"),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )

    import ui.alignment_page as alignment_page
    import ui.clustering_page as clustering_page
    import ui.protein_search_page as protein_search_page
    import ui.tools_page as tools_page
    from core.tool_state import ToolStatus

    class FakeToolRuntime:
        def get_tool_status(self, tool_id):
            return ToolStatus(installed=True, source="test", executable_path=tool_id)

        def get_missing_tools_for_feature(self, feature_id):
            return []

        def get_installable_tools(self, tool_ids):
            return []

    fake_runtime = FakeToolRuntime()
    monkeypatch.setattr(tools_page, "get_tool_runtime", lambda: fake_runtime)
    monkeypatch.setattr(clustering_page, "get_tool_runtime", lambda: fake_runtime)

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
    monkeypatch.setattr(
        alignment_page.AlignmentPage,
        "_run_builtin_sca",
        lambda self, silent=False: None,
    )
    monkeypatch.setattr(alignment_page, "is_pysca_installed", lambda: False)
    monkeypatch.setattr(alignment_page, "check_pairwise_aligner", lambda: False)
    monkeypatch.setattr(
        clustering_page.ClusteringPage,
        "check_system_requirements",
        lambda self: None,
    )
    monkeypatch.setattr(
        clustering_page.ClusteringPage,
        "_ensure_clustering_tools",
        lambda self: True,
    )
    monkeypatch.setattr(
        clustering_page,
        "create_distribution_chart",
        lambda stats, path: (False, "chart generation skipped in tests"),
    )

    return {"messages": messages, "sample_fasta": str(sample_fasta), "tmp_path": tmp_path}


@pytest.fixture
def workflow_window(qt_app, workflow_boundaries):
    from protein_gui import ProteinGUI

    window = ProteinGUI()
    window.show()
    qt_app.processEvents()
    yield window
    window.close()
    qt_app.processEvents()


class _FakeWorkerBase(QObject):
    def isRunning(self):
        return False

    def cancel(self):
        pass

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return True


def _button_text(button):
    return " ".join(button.text().split())


def _click_first_button_with_text(parent, text):
    matches = [
        button
        for button in parent.findChildren(QPushButton)
        if _button_text(button) == text
    ]
    assert matches, f"Could not find button with text {text!r}"
    QTest.mouseClick(matches[0], Qt.LeftButton)


def test_protein_search_run_renders_fake_blast_results(
    workflow_window,
    qt_app,
    workflow_boundaries,
    monkeypatch,
):
    from utils.results_parser import SearchHit
    import ui.protein_search_page as protein_search_page

    class FakeBLASTWorker(_FakeWorkerBase):
        finished = pyqtSignal(str, list)
        error = pyqtSignal(str)

        def __init__(self, sequence, database, use_remote=True, local_db_path="", advanced_params=None):
            super().__init__()
            self.sequence = sequence
            self.database = database

        def start(self):
            self.finished.emit(
                "<html><body>fake blast results</body></html>",
                [
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
                    )
                ],
            )

    monkeypatch.setattr(protein_search_page, "BLASTWorker", FakeBLASTWorker)

    page = workflow_window.protein_search_page
    workflow_window.tabs.setCurrentWidget(page)
    page.paste_radio.setChecked(True)
    page.input_text.setPlainText(SAMPLE_PROTEIN)
    qt_app.processEvents()

    QTest.mouseClick(page.process_button, Qt.LeftButton)
    qt_app.processEvents()

    assert page.status_label.text() == "Search complete!"
    assert page.process_button.isEnabled()
    assert page.current_query_info["tool"] == "BLASTP"
    assert len(page.current_results_data) == 1
    assert page.current_results_data[0].accession == "P12345"
    assert workflow_boundaries["messages"] == []


def test_alignment_run_renders_fake_alignment_results(
    workflow_window,
    qt_app,
    workflow_boundaries,
    monkeypatch,
    tmp_path,
):
    import ui.alignment_page as alignment_page

    aligned = (
        ">seq1\nMVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH\n"
        ">seq2\nMVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGDLST\n"
    )
    output_path = tmp_path / "aligned.fasta"
    output_path.write_text(aligned, encoding="utf-8")

    class FakeAlignmentWorker(_FakeWorkerBase):
        progress = pyqtSignal(int, str)
        finished = pyqtSignal(str, str)
        error = pyqtSignal(str)

        def __init__(self, *args, **kwargs):
            super().__init__()

        def start(self):
            self.progress.emit(50, "Fake alignment running")
            self.finished.emit(aligned, str(output_path))

    class FakeViewer:
        def load_alignment(self, content):
            return True

        def show(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass

    monkeypatch.setattr(alignment_page, "AlignmentWorker", FakeAlignmentWorker)
    monkeypatch.setattr(
        alignment_page.AlignmentPage,
        "_ensure_alignment_viewer_dialog",
        lambda self: FakeViewer(),
    )

    page = workflow_window.alignment_page
    workflow_window.tabs.setCurrentWidget(page)
    page.paste_radio.setChecked(True)
    page.paste_text.setPlainText(SAMPLE_FASTA)
    qt_app.processEvents()

    QTest.mouseClick(page.run_button, Qt.LeftButton)
    qt_app.processEvents()

    assert page.status_label.text() == "Alignment complete!"
    assert page.results_tabs.isVisible()
    assert page.raw_alignment_text.toPlainText() == aligned
    assert page.output_alignment_path == str(output_path)
    assert workflow_boundaries["messages"] == []


def test_clustering_run_renders_fake_cluster_results(
    workflow_window,
    qt_app,
    workflow_boundaries,
    monkeypatch,
    tmp_path,
):
    import ui.clustering_page as clustering_page

    rep_fasta = tmp_path / "representatives.fasta"
    rep_fasta.write_text(">seq1\nMVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH\n", encoding="utf-8")
    tsv_path = tmp_path / "clusters.tsv"
    tsv_path.write_text("seq1\tseq1\nseq1\tseq2\n", encoding="utf-8")
    stats = {
        "total_sequences": 2,
        "num_clusters": 1,
        "largest_cluster": 2,
        "avg_cluster_size": 2.0,
        "singletons": 0,
        "cluster_size_distribution": {2: 1},
        "clusters": {"seq1": ["seq1", "seq2"]},
    }

    class FakeClusteringWorker(_FakeWorkerBase):
        progress = pyqtSignal(int, str)
        finished = pyqtSignal(dict, str, str)
        error = pyqtSignal(str)

        def __init__(self, *args, **kwargs):
            super().__init__()

        def start(self):
            self.progress.emit(50, "Fake clustering running")
            self.finished.emit(stats, str(rep_fasta), str(tsv_path))

    monkeypatch.setattr(clustering_page, "ClusteringWorker", FakeClusteringWorker)

    page = workflow_window.clustering_page
    workflow_window.tabs.setCurrentWidget(page)
    _click_first_button_with_text(page, "Browse")
    qt_app.processEvents()

    assert page.fasta_path == workflow_boundaries["sample_fasta"]

    QTest.mouseClick(page.run_button, Qt.LeftButton)
    qt_app.processEvents()

    assert page.status_label.text().startswith("Clustering complete!")
    assert page.results_tabs.isVisible()
    assert page.clustering_results == stats
    assert page.clusters_table.rowCount() == 1
    assert page.clusters_table.item(0, 1).text() == "seq1"
    assert "Total Sequences:      2" in page.summary_text.toPlainText()
    assert workflow_boundaries["messages"] == []


def test_motif_search_run_renders_fake_results(
    workflow_window,
    qt_app,
    workflow_boundaries,
    monkeypatch,
):
    import ui.motif_search_page as motif_search_page
    from core.motif_worker import ProteinRecord

    record = ProteinRecord(
        seq=SAMPLE_PROTEIN,
        id="seq1",
        species="Homo sapiens",
        phylo=["Mammalia"],
        indices=[1, 12],
    )
    results = {
        "motif": ["N", "~P", "ST"],
        "total_sequences": 1,
        "total_motifs": 2,
        "category_stats": {
            "Mammalia": {"count": 1, "motifs": 2},
            "Other": {"count": 0, "motifs": 0},
        },
        "categories": {
            "Actinopterygii": [],
            "Mammalia": [record],
            "Aves": [],
            "Amphibia": [],
            "Other": [],
        },
    }

    class FakeMotifSearchWorker(_FakeWorkerBase):
        progress = pyqtSignal(int, str)
        finished = pyqtSignal(dict)
        error = pyqtSignal(str)

        def __init__(self, *args, **kwargs):
            super().__init__()

        def start(self):
            self.progress.emit(50, "Fake motif search running")
            self.finished.emit(results)

    monkeypatch.setattr(motif_search_page, "MotifSearchWorker", FakeMotifSearchWorker)

    page = workflow_window.motif_search_page
    workflow_window.tabs.setCurrentWidget(page)
    _click_first_button_with_text(page, "Browse")
    QTest.mouseClick(page.motif_widget.nglyc_preset_btn, Qt.LeftButton)
    qt_app.processEvents()

    QTest.mouseClick(page.run_button, Qt.LeftButton)
    qt_app.processEvents()

    assert page.status_label.text() == "Complete! Found 2 motifs in 1 sequences."
    assert page.results_tabs.isVisible()
    assert "Total Motifs Found: 2" in page.summary_text.toPlainText()
    assert page.results_table.rowCount() == 1
    assert page.results_table.item(0, 0).text() == "seq1"
    assert workflow_boundaries["messages"] == []


def test_validation_warnings_cover_common_negative_paths(
    workflow_window,
    qt_app,
    workflow_boundaries,
):
    messages = workflow_boundaries["messages"]

    protein_page = workflow_window.protein_search_page
    workflow_window.tabs.setCurrentWidget(protein_page)
    protein_page.paste_radio.setChecked(True)
    protein_page.input_text.clear()
    QTest.mouseClick(protein_page.process_button, Qt.LeftButton)
    qt_app.processEvents()
    assert protein_page.status_label.text() == "Please enter a protein sequence first."

    protein_page.input_text.setPlainText("BAD123")
    QTest.mouseClick(protein_page.process_button, Qt.LeftButton)
    qt_app.processEvents()
    assert protein_page.status_label.text() == "Invalid amino acid sequence."

    alignment_page = workflow_window.alignment_page
    workflow_window.tabs.setCurrentWidget(alignment_page)
    alignment_page.paste_radio.setChecked(True)
    alignment_page.paste_text.clear()
    QTest.mouseClick(alignment_page.run_button, Qt.LeftButton)
    qt_app.processEvents()
    assert any(m["kind"] == "warning" and m["title"] == "No Sequences" for m in messages)

    clustering_page = workflow_window.clustering_page
    workflow_window.tabs.setCurrentWidget(clustering_page)
    clustering_page.fasta_path = None
    clustering_page.file_path_input.clear()
    QTest.mouseClick(clustering_page.run_button, Qt.LeftButton)
    qt_app.processEvents()
    assert any(m["kind"] == "warning" and m["title"] == "No File" for m in messages)

    motif_page = workflow_window.motif_search_page
    workflow_window.tabs.setCurrentWidget(motif_page)
    motif_page.file_path_input.clear()
    motif_page.current_fasta_path = None
    QTest.mouseClick(motif_page.run_button, Qt.LeftButton)
    qt_app.processEvents()
    assert any(m["kind"] == "warning" and m["title"] == "No File" for m in messages)

    _click_first_button_with_text(motif_page, "Browse")
    motif_page.motif_widget.position_inputs[0].setText("")
    QTest.mouseClick(motif_page.run_button, Qt.LeftButton)
    qt_app.processEvents()
    assert any(m["kind"] == "warning" and m["title"] == "Invalid Motif" for m in messages)


def test_export_warnings_when_no_results_are_available(
    workflow_window,
    qt_app,
    workflow_boundaries,
):
    messages = workflow_boundaries["messages"]

    protein_page = workflow_window.protein_search_page
    workflow_window.tabs.setCurrentWidget(protein_page)
    protein_page._export_results("csv")
    qt_app.processEvents()
    assert any(m["kind"] == "warning" and m["title"] == "No Results" for m in messages)

    alignment_page = workflow_window.alignment_page
    workflow_window.tabs.setCurrentWidget(alignment_page)
    alignment_page._export_alignment("fasta")
    qt_app.processEvents()
    assert any(m["kind"] == "warning" and m["title"] == "No Alignment" for m in messages)

    clustering_page = workflow_window.clustering_page
    workflow_window.tabs.setCurrentWidget(clustering_page)
    clustering_page.export_tsv()
    qt_app.processEvents()
    assert any(m["kind"] == "warning" and m["title"] == "No Results" for m in messages)

    motif_page = workflow_window.motif_search_page
    workflow_window.tabs.setCurrentWidget(motif_page)
    motif_page.export_csv()
    qt_app.processEvents()
    assert any(m["kind"] == "warning" and m["title"] == "No Results" for m in messages)


def test_completed_alignment_clustering_and_motif_exports_write_files(
    workflow_window,
    qt_app,
    workflow_boundaries,
    tmp_path,
):
    export_path = tmp_path / "export.txt"

    alignment_page = workflow_window.alignment_page
    aligned = ">seq1\nMVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH\n"
    alignment_page.aligned_content = aligned
    alignment_page.format_combo.setCurrentIndex(alignment_page.format_combo.findData("fasta"))
    alignment_page._alignment_output_format = "fasta"
    alignment_page._export_alignment("fasta")
    qt_app.processEvents()
    assert export_path.read_text(encoding="utf-8") == aligned

    clustering_page = workflow_window.clustering_page
    stats = {
        "total_sequences": 2,
        "num_clusters": 1,
        "largest_cluster": 2,
        "avg_cluster_size": 2.0,
        "singletons": 0,
        "cluster_size_distribution": {2: 1},
        "clusters": {"seq1": ["seq1", "seq2"]},
    }
    rep_fasta = tmp_path / "representatives.fasta"
    rep_fasta.write_text(">seq1\nMVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH\n", encoding="utf-8")
    clustering_page.clustering_results = stats
    clustering_page.rep_fasta_path = str(rep_fasta)
    clustering_page.export_tsv()
    qt_app.processEvents()
    tsv_text = export_path.read_text(encoding="utf-8")
    assert "cluster_id\trepresentative_id\tmember_id\tcluster_size" in tsv_text
    assert "1\tseq1\tseq2\t2" in tsv_text

    clustering_page.export_fasta()
    qt_app.processEvents()
    assert export_path.read_text(encoding="utf-8") == rep_fasta.read_text(encoding="utf-8")

    motif_page = workflow_window.motif_search_page
    from core.motif_worker import ProteinRecord

    motif_page.results = {
        "categories": {
            "Mammalia": [
                ProteinRecord(
                    seq=SAMPLE_PROTEIN,
                    id="seq1",
                    species="Homo sapiens",
                    phylo=["Mammalia"],
                    indices=[1, 12],
                )
            ]
        }
    }
    motif_page.summary_text.setPlainText("MOTIF SEARCH RESULTS\nTotal Motifs Found: 2\n")
    motif_page.export_csv()
    qt_app.processEvents()
    csv_text = export_path.read_text(encoding="utf-8")
    assert "ID,Species,Category,Motif_Positions" in csv_text
    assert '"seq1","Homo sapiens","Mammalia","1;12"' in csv_text

    motif_page.export_summary()
    qt_app.processEvents()
    assert "Total Motifs Found: 2" in export_path.read_text(encoding="utf-8")


def test_protein_search_export_button_uses_page_exporter(
    workflow_window,
    qt_app,
    workflow_boundaries,
    tmp_path,
):
    from utils.results_parser import SearchHit

    export_path = tmp_path / "export.txt"
    page = workflow_window.protein_search_page
    workflow_window.tabs.setCurrentWidget(page)
    page.current_results_html = "<html>fake results</html>"
    page.current_query_info = {
        "tool": "BLASTP",
        "query_name": "query",
        "query_length": str(len(SAMPLE_PROTEIN)),
        "database": "swissprot",
        "search_time": "0.1s",
    }
    page.results_panel.set_results(
        [
            SearchHit(
                rank=1,
                accession="P12345",
                description="Fake hit",
                evalue=1e-80,
                score=250.0,
                identity_percent=96.0,
            )
        ],
        page.current_query_info,
    )

    def fake_export_blast_results(results_html, query_info, filepath, fmt):
        with open(filepath, "w", encoding="utf-8") as handle:
            handle.write(f"{fmt},{query_info['tool']},P12345\n")
        return True

    page.exporter.export_blast_results = fake_export_blast_results
    export_buttons = [
        button
        for button in page.results_panel.findChildren(QPushButton)
        if _button_text(button) == "Export CSV"
    ]
    assert export_buttons
    export_buttons[0].click()
    qt_app.processEvents()

    assert export_path.read_text(encoding="utf-8") == "csv,BLASTP,P12345\n"
    assert any(m["kind"] == "information" and m["title"] == "Export Successful" for m in workflow_boundaries["messages"])
