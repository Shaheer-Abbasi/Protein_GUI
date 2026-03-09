"""Tests for utils/fasta_parser.py"""
import pytest

from utils.fasta_parser import FastaParser, FastaSequence, FastaParseError, validate_amino_acid_sequence


class TestFastaSequence:
    def test_extract_id_simple(self):
        seq = FastaSequence(">sp|P12345|HBB_HUMAN", "MVHLT")
        assert seq.id == "sp|P12345|HBB_HUMAN"

    def test_extract_id_with_description(self):
        seq = FastaSequence(">ABC123 some description here", "MVHLT")
        assert seq.id == "ABC123"

    def test_str_representation(self):
        seq = FastaSequence(">test", "MVHLT")
        assert "5 amino acids" in str(seq)

    def test_repr(self):
        seq = FastaSequence(">test", "MVHLT")
        assert "test" in repr(seq)
        assert "5" in repr(seq)


class TestFastaParserString:
    def test_parse_two_sequences(self, sample_fasta_content):
        parser = FastaParser()
        seqs = parser.parse_string(sample_fasta_content)
        assert len(seqs) == 2
        assert seqs[0].id == "seq1"
        assert seqs[1].id == "seq2"

    def test_parse_single_sequence(self):
        parser = FastaParser()
        seqs = parser.parse_string(">only\nMVHLTPEEK\n")
        assert len(seqs) == 1
        assert seqs[0].sequence == "MVHLTPEEK"

    def test_multiline_sequence(self):
        fasta = ">multi\nMVHLT\nPEEKS\nAVTAL\n"
        parser = FastaParser()
        seqs = parser.parse_string(fasta)
        assert seqs[0].sequence == "MVHLTPEEKSAVTAL"

    def test_empty_string_raises(self):
        parser = FastaParser()
        with pytest.raises(FastaParseError, match="Empty"):
            parser.parse_string("")

    def test_whitespace_only_raises(self):
        parser = FastaParser()
        with pytest.raises(FastaParseError, match="Empty"):
            parser.parse_string("   \n\n  ")

    def test_no_header_raises(self):
        parser = FastaParser()
        with pytest.raises(FastaParseError, match="before header"):
            parser.parse_string("MVHLTPEEK\n")

    def test_empty_sequence_gives_warning(self):
        parser = FastaParser()
        seqs = parser.parse_string(">empty_header\n>next\nMVHLT\n")
        assert len(seqs) == 1
        assert parser.has_warnings()
        assert any("Empty sequence" in w for w in parser.get_warnings())

    def test_invalid_chars_give_warning(self):
        parser = FastaParser()
        seqs = parser.parse_string(">test\nMVH123LT\n")
        assert parser.has_warnings()
        assert any("Invalid" in w for w in parser.get_warnings())

    def test_sequence_uppercased(self):
        parser = FastaParser()
        seqs = parser.parse_string(">test\nmvhlt\n")
        assert seqs[0].sequence == "MVHLT"

    def test_blank_lines_ignored(self):
        fasta = ">seq1\nMVHLT\n\n\n>seq2\nPEEKS\n"
        parser = FastaParser()
        seqs = parser.parse_string(fasta)
        assert len(seqs) == 2


class TestFastaParserFile:
    def test_parse_file(self, sample_fasta_file):
        parser = FastaParser()
        seqs = parser.parse_file(sample_fasta_file)
        assert len(seqs) == 2

    def test_file_not_found(self):
        parser = FastaParser()
        with pytest.raises(FastaParseError, match="not found"):
            parser.parse_file("/nonexistent/path.fasta")

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.fasta"
        empty.write_text("")
        parser = FastaParser()
        with pytest.raises(FastaParseError, match="empty"):
            parser.parse_file(str(empty))

    def test_large_file_warning(self, tmp_path):
        big = tmp_path / "big.fasta"
        big.write_text(">seq\n" + "M" * (11 * 1024 * 1024))
        parser = FastaParser()
        seqs = parser.parse_file(str(big))
        assert parser.has_warnings()
        assert any("Large" in w for w in parser.get_warnings())


class TestValidateSequence:
    def test_valid_sequence(self):
        parser = FastaParser()
        valid, err = parser.validate_sequence("MVHLTPEEKSAVTAL")
        assert valid is True
        assert err is None

    def test_too_short(self):
        parser = FastaParser()
        valid, err = parser.validate_sequence("MVH")
        assert valid is False
        assert "too short" in err.lower()

    def test_too_long(self):
        parser = FastaParser()
        valid, err = parser.validate_sequence("M" * 10001)
        assert valid is False
        assert "too long" in err.lower()

    def test_empty(self):
        parser = FastaParser()
        valid, err = parser.validate_sequence("")
        assert valid is False

    def test_invalid_characters(self):
        parser = FastaParser()
        valid, err = parser.validate_sequence("MVHLT12345PEEKS")
        assert valid is False
        assert "Invalid" in err


class TestValidateAminoAcidSequence:
    def test_valid(self):
        ok, msg = validate_amino_acid_sequence("MVHLTPEEKSAVTAL")
        assert ok is True
        assert "Valid" in msg

    def test_invalid(self):
        ok, msg = validate_amino_acid_sequence("123")
        assert ok is False
