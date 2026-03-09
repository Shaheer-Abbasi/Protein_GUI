"""Tests for utils/results_parser.py"""
import pytest

from utils.results_parser import SearchHit, BLASTResultsParser, MMSeqsResultsParser


class TestSearchHit:
    def test_to_dict(self):
        hit = SearchHit(rank=1, accession="P12345", evalue=1e-50, score=200.0)
        d = hit.to_dict()
        assert d["rank"] == 1
        assert d["accession"] == "P12345"
        assert d["evalue"] == 1e-50
        assert d["score"] == 200.0

    def test_defaults(self):
        hit = SearchHit()
        assert hit.rank == 0
        assert hit.accession == ""
        assert hit.full_sequence == ""


class TestBLASTResultsParser:
    def test_parse_xml(self, sample_blast_xml_file):
        hits = BLASTResultsParser.parse_xml(sample_blast_xml_file)
        assert len(hits) == 2

        assert hits[0].rank == 1
        assert hits[0].accession == "000509.1"
        assert hits[0].evalue == pytest.approx(1.5e-80)
        assert hits[0].score == pytest.approx(250.0)
        assert hits[0].identity_percent == pytest.approx(140 / 147 * 100, rel=1e-2)
        assert hits[0].organism == "Homo sapiens"

        assert hits[1].rank == 2
        assert hits[1].organism == "Mus musculus"

    def test_parse_nonexistent_file(self):
        hits = BLASTResultsParser.parse_xml("/nonexistent/file.xml")
        assert hits == []

    def test_extract_accession_genbank(self):
        acc = BLASTResultsParser._extract_accession("ref|NP_000509.1|", "hemoglobin")
        assert acc == "000509.1"

    def test_extract_accession_uniprot_sp(self):
        acc = BLASTResultsParser._extract_accession("sp|P02023|HBB_MOUSE", "")
        assert acc == "P02023"

    def test_extract_accession_uniprot_tr(self):
        acc = BLASTResultsParser._extract_accession("tr|A0A123|PROT_HUMAN", "")
        assert acc == "A0A123"

    def test_extract_organism_brackets(self):
        org = BLASTResultsParser._extract_organism("hemoglobin [Homo sapiens]")
        assert org == "Homo sapiens"

    def test_extract_organism_none(self):
        org = BLASTResultsParser._extract_organism("hemoglobin subunit beta")
        assert org == "Unknown"


class TestMMSeqsResultsParser:
    def test_parse_m8(self, sample_m8_file):
        hits = MMSeqsResultsParser.parse_m8(sample_m8_file)
        assert len(hits) == 3

        assert hits[0].rank == 1
        assert hits[0].accession == "P12345"
        assert hits[0].identity_percent == pytest.approx(95.5)
        assert hits[0].evalue == pytest.approx(1.5e-80)
        assert hits[0].score == pytest.approx(250.0)
        assert hits[0].alignment_length == 200

        assert hits[2].rank == 3
        assert hits[2].accession == "A11111"

    def test_parse_m8_with_comments(self, tmp_path):
        content = "# comment\nquery\tTARGET1\t99.0\t100\t1\t0\t1\t100\t1\t100\t1e-50\t200\n"
        m8 = tmp_path / "commented.m8"
        m8.write_text(content)
        hits = MMSeqsResultsParser.parse_m8(str(m8))
        assert len(hits) == 1
        assert hits[0].accession == "TARGET1"

    def test_parse_m8_short_lines_skipped(self, tmp_path):
        content = "query\tTARGET1\t99.0\n"  # too few fields
        m8 = tmp_path / "short.m8"
        m8.write_text(content)
        hits = MMSeqsResultsParser.parse_m8(str(m8))
        assert len(hits) == 0

    def test_parse_nonexistent_file(self):
        hits = MMSeqsResultsParser.parse_m8("/nonexistent/file.m8")
        assert hits == []

    def test_extract_accession_pipe_separated(self):
        acc = MMSeqsResultsParser._extract_accession("sp|P12345|HBB")
        assert acc in ("sp", "P12345", "HBB")  # first regex-matching part

    def test_extract_accession_simple(self):
        acc = MMSeqsResultsParser._extract_accession("ABC123")
        assert acc == "ABC123"
