"""Tests for worker command construction and logic (mocked subprocess calls)"""
import os
import tempfile
from unittest.mock import patch, MagicMock, call
import pytest

from core.blast_worker import BLASTWorker
from core.alignment_worker import check_clustalo_installation, AlignmentWorker, SequenceAlignmentPrep


# ── check_clustalo_installation ──────────────────────────────────────

class TestCheckClustaloInstallation:
    @patch("core.alignment_worker.get_tool_runtime")
    def test_found(self, mock_runtime):
        mock_runtime.return_value.get_tool_status.return_value = MagicMock(
            installed=True,
            version="1.2.4",
            executable_path="/usr/local/bin/clustalo",
        )
        installed, version, path = check_clustalo_installation()
        assert installed is True
        assert version == "1.2.4"
        assert path == "/usr/local/bin/clustalo"

    @patch("core.alignment_worker.get_tool_runtime")
    def test_not_found(self, mock_runtime):
        mock_runtime.return_value.get_tool_status.return_value = MagicMock(
            installed=False,
            version=None,
            executable_path=None,
        )
        installed, version, path = check_clustalo_installation()
        assert installed is False
        assert version is None


# ── SequenceAlignmentPrep ────────────────────────────────────────────

class TestSequenceAlignmentPrep:
    def test_prepare_from_hits(self, tmp_path):
        hit1 = MagicMock()
        hit1.sequence = "MVHLTPEEKSAVTAL"
        hit1.id = "seq1"
        hit2 = MagicMock()
        hit2.sequence = "MVHLTPEEKSAVTALWGKV"
        hit2.id = "seq2"

        out = str(tmp_path / "prep.fasta")
        ok, msg, count = SequenceAlignmentPrep.prepare_from_hits([hit1, hit2], out)
        assert ok is True
        assert count == 2
        assert os.path.exists(out)

        with open(out) as f:
            content = f.read()
        assert ">seq1" in content
        assert ">seq2" in content

    def test_prepare_from_hits_too_few(self, tmp_path):
        hit1 = MagicMock()
        hit1.sequence = "MVHLT"
        hit1.id = "only"

        out = str(tmp_path / "few.fasta")
        ok, msg, count = SequenceAlignmentPrep.prepare_from_hits([hit1], out)
        assert ok is False
        assert count == 1

    def test_prepare_skips_empty_sequences(self, tmp_path):
        hit1 = MagicMock()
        hit1.sequence = ""
        hit1.id = "empty"
        hit2 = MagicMock()
        hit2.sequence = "MVHLTPEEKSAVTAL"
        hit2.id = "good"

        out = str(tmp_path / "skip.fasta")
        ok, msg, count = SequenceAlignmentPrep.prepare_from_hits([hit1, hit2], out)
        assert ok is False  # only 1 valid sequence
        assert count == 1

    def test_validate_fasta_for_alignment(self, sample_fasta_file):
        from core.alignment_worker import SequenceAlignmentPrep
        valid, msg, count = SequenceAlignmentPrep.validate_fasta_for_alignment(sample_fasta_file)
        assert valid is True
        assert count == 2

    def test_validate_fasta_too_few_sequences(self, tmp_path):
        fasta = tmp_path / "one.fasta"
        fasta.write_text(">single\nMVHLTPEEK\n")
        valid, msg, count = SequenceAlignmentPrep.validate_fasta_for_alignment(str(fasta))
        assert valid is False
        assert count == 1

    def test_validate_nonexistent(self):
        valid, msg, count = SequenceAlignmentPrep.validate_fasta_for_alignment("/no/file")
        assert valid is False


# ── MMseqsWorker sensitivity mapping ─────────────────────────────────

class TestMMseqsWorkerParams:
    def test_sensitivity_values(self):
        from core.mmseqs_runner import MMseqsWorker
        w = MMseqsWorker("MVHLT", "/db/path", "fast")
        assert w.get_sensitivity_value() == "4"
        w2 = MMseqsWorker("MVHLT", "/db/path", "very-sensitive")
        assert w2.get_sensitivity_value() == "8.5"
        w3 = MMseqsWorker("MVHLT", "/db/path", "unknown")
        assert w3.get_sensitivity_value() == "5.7"  # default

    def test_evalue_color(self):
        from core.mmseqs_runner import MMseqsWorker
        w = MMseqsWorker("MVHLT", "/db/path")
        assert w.get_evalue_color("1e-150") == "#27ae60"
        assert w.get_evalue_color("0.5") == "#e74c3c"
        assert w.get_evalue_color("bad") == "#7f8c8d"

    def test_identity_color(self):
        from core.mmseqs_runner import MMseqsWorker
        w = MMseqsWorker("MVHLT", "/db/path")
        assert w.get_identity_color("95") == "#27ae60"
        assert w.get_identity_color("20") == "#e74c3c"
        assert w.get_identity_color("bad") == "#7f8c8d"


class TestRuntimeIntegratedWorkers:
    @patch("core.blast_worker.BLASTResultsParser.parse_xml", return_value=[])
    @patch.object(BLASTWorker, "parse_blast_xml", return_value="<html></html>")
    @patch("core.blast_worker.get_tool_runtime")
    @patch("core.blast_worker.os.unlink")
    def test_blast_worker_routes_execution_through_runtime(
        self,
        mock_unlink,
        mock_runtime_factory,
        _mock_parse_html,
        _mock_parse_structured,
    ):
        runtime = MagicMock()
        resolution = MagicMock(executable="/managed/blastp", backend="native")
        runtime.resolve_tool.return_value = resolution
        runtime.prepare_path.side_effect = lambda _resolution, path: path
        runtime.run_resolved.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_runtime_factory.return_value = runtime

        worker = BLASTWorker("MVHLTPEEKSAVTAL", "swissprot", use_remote=True)
        finished_payload = []
        worker.finished.connect(lambda html, data: finished_payload.append((html, data)))

        worker.run()

        runtime.resolve_tool.assert_called_once_with("blastp")
        assert runtime.run_resolved.called
        assert finished_payload == [("<html></html>", [])]
