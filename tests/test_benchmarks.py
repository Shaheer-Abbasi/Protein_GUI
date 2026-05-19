"""Unit tests for benchmark helpers (stdlib unittest; no external aligners required)."""

from __future__ import annotations

import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from benchmarks import aggregate
from benchmarks.alignment import build_argv_muscle
from benchmarks.datasets import count_sequences, subset_fasta, uniprot_pfam_stream_url
from benchmarks.quality import QualityMetrics, compute_quality


class BenchmarkHelpersTest(unittest.TestCase):
    def test_subset_and_count(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            fasta = td_path / "in.fasta"
            recs = [SeqRecord(Seq("ACGT"), id=f"s{i}", description="") for i in range(10)]
            SeqIO.write(recs, fasta, "fasta")

            self.assertEqual(count_sequences(str(fasta)), 10)

            out = td_path / "sub.fasta"
            n = subset_fasta(str(fasta), 4, str(out), seed=0)
            self.assertEqual(n, 4)
            self.assertEqual(count_sequences(str(out)), 4)
            ids_in = {r.id for r in recs}
            ids_out = {r.id for r in SeqIO.parse(out, "fasta")}
            self.assertTrue(ids_out.issubset(ids_in))
            self.assertEqual(len(ids_out), 4)

    def test_uniprot_pfam_stream_url_encoding(self):
        u = uniprot_pfam_stream_url("PF00005")
        qs = parse_qs(urlparse(u).query)
        self.assertEqual(qs["compressed"], ["true"])
        self.assertEqual(qs["query"], ["(xref:pfam-PF00005)"])

    def test_aggregate_summarize_alignment_tiers(self):
        rows = [
            {
                "study": "alignment",
                "tool": "famsa",
                "dataset_label": "n100",
                "tier": "1",
                "seq_count": 100,
                "threads": 8,
                "repeat": 0,
                "wall_seconds": 1.0,
                "exit_code": 0,
                "timed_out": False,
                "avg_pid": 0.9,
                "peak_rss_mib": 120.0,
                "gap_fraction": 0.1,
                "mean_entropy": 0.05,
            },
            {
                "study": "alignment",
                "tool": "famsa",
                "dataset_label": "n100",
                "tier": "2",
                "seq_count": 100,
                "threads": 8,
                "repeat": 0,
                "wall_seconds": 2.0,
                "exit_code": 0,
                "timed_out": False,
                "avg_pid": 0.8,
                "peak_rss_mib": 200.0,
                "gap_fraction": 0.2,
                "mean_entropy": 0.06,
            },
        ]
        s = aggregate.summarize_alignment(rows)
        self.assertEqual(len(s), 2)
        tiers = sorted(r["tier"] for r in s)
        self.assertEqual(tiers, ["1", "2"])

    def test_compute_quality_simple(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            aln = td_path / "aln.fasta"
            SeqIO.write(
                [
                    SeqRecord(Seq("ABC"), id="a", description=""),
                    SeqRecord(Seq("ABC"), id="b", description=""),
                ],
                aln,
                "fasta",
            )
            q = compute_quality(str(aln), max_pairs=10)
            self.assertIsInstance(q, QualityMetrics)
            self.assertEqual(q.avg_pid, 1.0)
            self.assertEqual(q.gap_fraction, 0.0)
            self.assertEqual(q.mean_entropy, 0.0)

    def test_aggregate_summarize_alignment_empty(self):
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "empty.jsonl"
            empty.write_text("", encoding="utf-8")
            rows = aggregate.read_jsonl(str(empty))
            self.assertEqual(aggregate.summarize_alignment(rows), [])

    def test_muscle_super5_argv(self):
        class RT:
            @staticmethod
            def prepare_path(_resolution, path):
                return path

        class Resolution:
            executable = "muscle"
            backend = "native"

        argv = build_argv_muscle(
            RT(),
            Resolution(),
            "input.fasta",
            "output.fasta",
            8,
            mode="super5",
        )
        self.assertIn("-super5", argv)
        self.assertNotIn("-align", argv)


if __name__ == "__main__":
    unittest.main()
