"""Tests for worker command construction and logic (mocked subprocess calls)"""
import os
import tempfile
from unittest.mock import patch, MagicMock, call
import pytest

from core.alignment_worker import check_clustalo_installation, AlignmentWorker, SequenceAlignmentPrep


# ── check_clustalo_installation ──────────────────────────────────────

class TestCheckClustaloInstallation:
    @patch("core.alignment_worker.is_windows", return_value=False)
    @patch("core.alignment_worker.check_wsl_command", return_value=(True, "/usr/local/bin/clustalo"))
    @patch("core.alignment_worker.run_wsl_command")
    def test_found(self, mock_run, *_):
        mock_run.return_value = MagicMock(returncode=0, stdout="1.2.4\n")
        installed, version, path = check_clustalo_installation()
        assert installed is True
        assert version == "1.2.4"

    @patch("core.alignment_worker.is_windows", return_value=False)
    @patch("core.alignment_worker.check_wsl_command", return_value=(False, None))
    def test_not_found(self, *_):
        installed, version, path = check_clustalo_installation()
        assert installed is False
        assert version is None

    @patch("core.alignment_worker.is_windows", return_value=True)
    @patch("core.alignment_worker.is_wsl_available", return_value=False)
    def test_no_wsl_on_windows(self, *_):
        installed, version, path = check_clustalo_installation()
        assert installed is False


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
