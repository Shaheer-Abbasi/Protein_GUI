"""Tests for core/clustering_manager.py"""
import os
import pytest

from core.clustering_manager import (
    parse_clustering_results,
    export_clustering_tsv,
    get_cluster_table_data,
    validate_fasta_file,
)


class TestParseClusteringResults:
    def test_basic_parsing(self, sample_clustering_tsv_file):
        stats = parse_clustering_results(sample_clustering_tsv_file)
        assert stats["total_sequences"] == 6
        assert stats["num_clusters"] == 3
        assert stats["largest_cluster"] == 3  # rep1 has 3 members
        assert stats["singletons"] == 1  # rep2 is alone
        assert stats["avg_cluster_size"] == pytest.approx(2.0)

    def test_cluster_contents(self, sample_clustering_tsv_file):
        stats = parse_clustering_results(sample_clustering_tsv_file)
        clusters = stats["clusters"]
        assert "rep1" in clusters
        assert len(clusters["rep1"]) == 3
        assert "member1a" in clusters["rep1"]

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.tsv"
        empty.write_text("")
        stats = parse_clustering_results(str(empty))
        assert stats["total_sequences"] == 0
        assert stats["num_clusters"] == 0

    def test_single_cluster(self, tmp_path):
        tsv = tmp_path / "single.tsv"
        tsv.write_text("rep\trep\nrep\tmem1\nrep\tmem2\n")
        stats = parse_clustering_results(str(tsv))
        assert stats["num_clusters"] == 1
        assert stats["total_sequences"] == 3

    def test_all_singletons(self, tmp_path):
        tsv = tmp_path / "singletons.tsv"
        tsv.write_text("a\ta\nb\tb\nc\tc\n")
        stats = parse_clustering_results(str(tsv))
        assert stats["num_clusters"] == 3
        assert stats["singletons"] == 3
        assert stats["largest_cluster"] == 1

    def test_size_distribution(self, sample_clustering_tsv_file):
        stats = parse_clustering_results(sample_clustering_tsv_file)
        dist = stats["cluster_size_distribution"]
        assert dist[3] == 1  # one cluster of size 3
        assert dist[2] == 1  # one cluster of size 2
        assert dist[1] == 1  # one singleton


class TestExportClusteringTsv:
    def test_export(self, sample_clustering_tsv_file, tmp_path):
        stats = parse_clustering_results(sample_clustering_tsv_file)
        out_path = str(tmp_path / "export.tsv")
        result = export_clustering_tsv(stats, out_path)
        assert result is True
        assert os.path.exists(out_path)

        with open(out_path) as f:
            lines = f.readlines()
        assert lines[0].startswith("cluster_id")
        assert len(lines) == 7  # header + 6 data rows


class TestGetClusterTableData:
    def test_sorted_by_size(self, sample_clustering_tsv_file):
        stats = parse_clustering_results(sample_clustering_tsv_file)
        table = get_cluster_table_data(stats)
        assert len(table) == 3
        # Largest cluster first
        assert table[0][2] >= table[1][2]

    def test_max_rows(self, sample_clustering_tsv_file):
        stats = parse_clustering_results(sample_clustering_tsv_file)
        table = get_cluster_table_data(stats, max_rows=2)
        assert len(table) == 2


class TestValidateFastaFile:
    def test_valid_file(self, sample_fasta_file):
        valid, err, count, size_mb = validate_fasta_file(sample_fasta_file)
        assert valid is True
        assert err == ""
        assert count == 2
        assert size_mb > 0

    def test_nonexistent_file(self):
        valid, err, count, size_mb = validate_fasta_file("/nonexistent/file.fasta")
        assert valid is False
        assert "not exist" in err.lower() or "does not exist" in err.lower()

    def test_not_fasta(self, tmp_path):
        bad = tmp_path / "bad.fasta"
        bad.write_text("this is not fasta format")
        valid, err, count, size_mb = validate_fasta_file(str(bad))
        assert valid is False
        assert "must start with" in err.lower() or "not a valid" in err.lower()

    def test_header_only_no_sequence(self, tmp_path):
        bad = tmp_path / "header_only.fasta"
        bad.write_text(">only_header\n")
        valid, err, count, size_mb = validate_fasta_file(str(bad))
        assert valid is False
