"""Shared fixtures for Protein GUI tests"""
import os
import sys
import json
import tempfile
import pytest

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a clean temporary directory"""
    return tmp_path


@pytest.fixture
def sample_fasta_content():
    """A minimal valid FASTA string with two sequences"""
    return (
        ">seq1 Example protein 1\n"
        "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH\n"
        ">seq2 Example protein 2\n"
        "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGDLST\n"
    )


@pytest.fixture
def sample_fasta_file(tmp_path, sample_fasta_content):
    """Write sample FASTA to a temp file and return the path"""
    fasta_path = tmp_path / "test.fasta"
    fasta_path.write_text(sample_fasta_content)
    return str(fasta_path)


@pytest.fixture
def sample_m8_content():
    """Sample MMseqs2 M8 format output"""
    return (
        "query\tP12345\t95.5\t200\t9\t0\t1\t200\t1\t200\t1.5e-80\t250.0\n"
        "query\tQ67890\t78.2\t180\t39\t1\t10\t189\t5\t184\t3.2e-50\t180.5\n"
        "query\tA11111\t45.0\t150\t82\t3\t20\t169\t15\t164\t1.0e-10\t60.2\n"
    )


@pytest.fixture
def sample_m8_file(tmp_path, sample_m8_content):
    """Write sample M8 to a temp file and return the path"""
    m8_path = tmp_path / "results.m8"
    m8_path.write_text(sample_m8_content)
    return str(m8_path)


@pytest.fixture
def sample_clustering_tsv_content():
    """Sample MMseqs2 clustering TSV (representative\\tmember)"""
    return (
        "rep1\trep1\n"
        "rep1\tmember1a\n"
        "rep1\tmember1b\n"
        "rep2\trep2\n"
        "rep3\trep3\n"
        "rep3\tmember3a\n"
    )


@pytest.fixture
def sample_clustering_tsv_file(tmp_path, sample_clustering_tsv_content):
    """Write sample clustering TSV to a temp file"""
    tsv_path = tmp_path / "clusters.tsv"
    tsv_path.write_text(sample_clustering_tsv_content)
    return str(tsv_path)


@pytest.fixture
def sample_config(tmp_path):
    """Write a sample config.json and return its path"""
    config = {
        "blast_path": "blastp",
        "mmseqs_path": "mmseqs",
        "mmseqs_available": True,
        "blastdbcmd_available": True,
        "databases_found": ["swissprot"]
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    return str(config_path)


@pytest.fixture
def sample_blast_xml_content():
    """Minimal BLAST XML for testing the parser"""
    return """<?xml version="1.0"?>
<BlastOutput>
  <BlastOutput_iterations>
    <Iteration>
      <Iteration_query-len>200</Iteration_query-len>
      <Iteration_hits>
        <Hit>
          <Hit_id>ref|NP_000509.1|</Hit_id>
          <Hit_def>hemoglobin subunit beta [Homo sapiens]</Hit_def>
          <Hit_len>147</Hit_len>
          <Hit_hsps>
            <Hsp>
              <Hsp_evalue>1.5e-80</Hsp_evalue>
              <Hsp_bit-score>250.0</Hsp_bit-score>
              <Hsp_identity>140</Hsp_identity>
              <Hsp_align-len>147</Hsp_align-len>
              <Hsp_query-from>1</Hsp_query-from>
              <Hsp_query-to>147</Hsp_query-to>
            </Hsp>
          </Hit_hsps>
        </Hit>
        <Hit>
          <Hit_id>sp|P02023|HBB_MOUSE</Hit_id>
          <Hit_def>Hemoglobin subunit beta [Mus musculus]</Hit_def>
          <Hit_len>147</Hit_len>
          <Hit_hsps>
            <Hsp>
              <Hsp_evalue>3.2e-60</Hsp_evalue>
              <Hsp_bit-score>200.0</Hsp_bit-score>
              <Hsp_identity>120</Hsp_identity>
              <Hsp_align-len>147</Hsp_align-len>
              <Hsp_query-from>1</Hsp_query-from>
              <Hsp_query-to>147</Hsp_query-to>
            </Hsp>
          </Hit_hsps>
        </Hit>
      </Iteration_hits>
    </Iteration>
  </BlastOutput_iterations>
</BlastOutput>"""


@pytest.fixture
def sample_blast_xml_file(tmp_path, sample_blast_xml_content):
    """Write sample BLAST XML to a temp file"""
    xml_path = tmp_path / "blast_results.xml"
    xml_path.write_text(sample_blast_xml_content)
    return str(xml_path)
