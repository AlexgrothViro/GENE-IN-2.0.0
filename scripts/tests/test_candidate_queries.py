import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/pipeline/collect_candidate_queries.py"
spec = importlib.util.spec_from_file_location("candidate_queries", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.path.insert(0, str(ROOT / "scripts/evidence"))
from blast_router import profiles_for_length


class CandidateQueryTests(unittest.TestCase):
    def test_union_deduplicates_reads_without_losing_contig_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            contigs = base / "contigs.fa"
            contigs.write_text(">gic_original\n" + "ACGT" * 20 + "\n>long_background\n" + "AC" * 500 + "\n")
            shorts = base / "shorts.fa"
            shorts.write_text(">other_assembler\n" + "ACGT" * 20 + "\n>unique_short\n" + "TGCA" * 8 + "\n")
            reads = base / "reads.fq"
            reads.write_text("@r1\n" + "TGCA" * 8 + "\n+\n" + "I" * 32 + "\n" +
                             "@r2\n" + "TGCA" * 8 + "\n+\n" + "I" * 32 + "\n")
            sequences, manifest = module.collect(contigs, shorts, [reads])
            self.assertEqual(len(sequences), 3)
            self.assertIn("gic_original", sequences)
            self.assertIn("long_background", sequences)
            self.assertEqual(manifest["queries"]["gic_original"]["source_counts"],
                             {"contig": 1, "assembled_short": 1})
            query = next(key for key, seq in sequences.items() if len(seq) == 32)
            self.assertEqual(manifest["queries"][query]["source_counts"],
                             {"assembled_short": 1, "short_read": 2})

    def test_empty_assembly_still_recovers_twenty_base_read(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            contigs = base / "empty.fa"
            contigs.touch()
            reads = base / "reads.fq"
            reads.write_text("@short\n" + "ACGT" * 5 + "\n+\n" + "I" * 20 + "\n")
            sequences, manifest = module.collect(contigs, fastqs=[reads])
            self.assertEqual(list(map(len, sequences.values())), [20])
            query = next(iter(sequences))
            self.assertEqual(manifest["queries"][query]["source_counts"], {"short_read": 1})

    def test_read_origin_survives_hsp_aggregation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            contigs = base / "empty.fa"
            contigs.touch()
            reads = base / "reads.fq"
            reads.write_text("@short\n" + "ACGT" * 5 + "\n+\n" + "I" * 20 + "\n")
            sequences, manifest = module.collect(contigs, fastqs=[reads])
            query = next(iter(sequences))
            query_fasta = base / "queries.fa"
            query_fasta.write_text(f">{query}\n{sequences[query]}\n")
            query_manifest = base / "queries.json"
            query_manifest.write_text(json.dumps(manifest))
            blast = base / "blast.tsv"
            blast.write_text("\t".join(map(str, [query, "ref", 100, 20, 0, 0,
                                                1, 20, 1, 20, 0.1, 40, 20, 100, 20, 0])) + "\n")
            output = base / "fragments.tsv"
            result = subprocess.run([sys.executable, str(ROOT / "scripts/evidence/aggregate_hsps.py"),
                "--blast", f"blastn-short={blast}", "--query-fasta", str(query_fasta),
                "--query-manifest", str(query_manifest), "--assembly-method", "spades",
                "--out", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.read_text().splitlines()[1].endswith("\tread_level"))
            from export_candidate_sequences import export
            export(query_fasta, query_manifest, output, base / "review")
            self.assertEqual((base / "review/candidate_sequences.fa").read_text(),
                             query_fasta.read_text())
            table = (base / "review/candidate_sequences.tsv").read_text()
            self.assertIn("short_read", table)
            self.assertIn("sequence_length_bp", table)
            self.assertIn("aligned_query_bp", table)
            (base / "review/fragment_evidence.tsv").write_bytes(output.read_bytes())
            from validate_run_artifacts import validate_candidate_exports
            self.assertEqual(validate_candidate_exports(base / "review"), [])
            (base / "review/candidate_sequences.fa").write_text(f">{query}\n{'T' * 20}\n")
            self.assertTrue(validate_candidate_exports(base / "review"))

    def test_fragment_routing_is_explicit_and_preserves_default(self):
        config = {"blast": {"short_max_bp": 29, "dual_mode_min_bp": 30, "dual_mode_max_bp": 49}}
        self.assertEqual(profiles_for_length(80, config), ("conventional",))
        for length in (20, 34, 54, 74, 100):
            self.assertIn("short", profiles_for_length(length, config, True))
        self.assertEqual(profiles_for_length(101, config, True), ("conventional",))

    def test_long_read_rescue_only_includes_selected_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            contigs = base / "empty.fa"
            contigs.touch()
            rescue = base / "rescue.fa"
            rescue.write_text(">hit\n" + "ACGT" * 31 + "\n>background\n" + "TGCA" * 31 + "\n")
            hits = base / "raw.tsv"
            hits.write_text("qseqid\tsseqid\nhit\tref\n")
            sequences, _ = module.collect(contigs, rescue_fasta=rescue, rescue_candidates=hits)
            self.assertEqual(list(sequences.values()), ["ACGT" * 31])
            hits.write_text("qseqid\tsseqid\nmissing\tref\n")
            with self.assertRaisesRegex(ValueError, "absent"):
                module.collect(contigs, rescue_fasta=rescue, rescue_candidates=hits)


if __name__ == "__main__":
    unittest.main()
