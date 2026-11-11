"""Boundary, provenance, Builder manifest and no-inflation regression tests."""
import gzip
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/pipeline/collect_candidate_queries.py"
spec = importlib.util.spec_from_file_location("candidate_sizes", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from blast_router import profiles_for_length, profile_parameters
from query_accounting import render_collection_summary


def fastq(path, records):
    text = "".join(f"@{name}\n{seq}\n+\n{'I' * len(seq)}\n" for name, seq in records)
    if path.suffix == ".gz":
        with gzip.open(path, "wt") as handle:
            handle.write(text)
    else:
        path.write_text(text)


class AllSizeQueryTests(unittest.TestCase):
    def test_boundaries_whole_sequences_and_balanced_discard(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            contigs = base / "empty.fa"
            contigs.touch()
            reads = base / "reads.fq"
            rng = random.Random(11)
            records = [(f"r{n}", "".join(rng.choice("ACGT") for _ in range(n)))
                       for n in (19, 20, 100, 101, 150)]
            fastq(reads, records)
            sequences, manifest = module.collect(contigs, fastqs=[reads])
            self.assertEqual(set(sequences.values()), {seq for _, seq in records[1:]})
            balance = manifest["routing_summary"]
            self.assertEqual(balance["accepted_occurrences"], {
                "short_20_100": 2, "long_above_100": 2, "legacy_fasta_below_20": 0})
            self.assertEqual(balance["discarded_occurrences"]["fastq_below_20_legacy_exclusion"], 1)
            self.assertIn("fastq_below_20_legacy_exclusion | 1", render_collection_summary(manifest))
            config = {"blast": {"short_max_bp": 29, "dual_mode_min_bp": 30,
                                 "dual_mode_max_bp": 49, "explicit_dust": False, "soft_masking": False}}
            for n in (101, 150, 1770):
                self.assertEqual(profiles_for_length(n, config, True), ("conventional",))
            self.assertEqual(profile_parameters(config)["conventional"]["word_size"], 11)

    def test_duplicate_long_mates_are_provenance_not_new_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            contigs = base / "contigs.fa"
            seq = "ACGT" * 37 + "AC"
            contigs.write_text(f">original_contig\n{seq}\n")
            paths = [base / "R1.fq.gz", base / "R2.fq.gz"]
            for mate, path in enumerate(paths, 1):
                fastq(path, [(f"pair/{mate}", seq), (f"pair/{mate}", seq)])
            sequences, manifest = module.collect(contigs, fastqs=paths)
            self.assertEqual(sequences, {"original_contig": seq})
            entry = manifest["queries"]["original_contig"]
            self.assertEqual(entry["source_counts"], {"contig": 1, "long_read": 4})
            self.assertEqual({s["pair_id"] for s in entry["sources"] if "pair_id" in s}, {"pair"})
            self.assertEqual({s["mate"] for s in entry["sources"] if "mate" in s}, {1, 2})
            self.assertEqual(len(entry["sources"]), 3)
            self.assertEqual(
                {s["mate"]: s["occurrences"] for s in entry["sources"] if "mate" in s},
                {1: 2, 2: 2},
            )
            self.assertNotIn("unique_templates", entry)
            self.assertEqual(manifest["routing_summary"]["merged_occurrences"], 4)
            self.assertEqual(manifest["routing_summary"]["resource_precheck"]["status"], "PASSED")
            with self.assertRaisesRegex(RuntimeError, "disco insuficiente"):
                module.precheck_collection_resources(paths, base, free_disk_bytes=1024)
            with self.assertRaisesRegex(RuntimeError, "Memória RAM insuficiente"):
                module.precheck_collection_resources(paths, base, available_ram_bytes=1024)

    def test_complete_genome_and_legacy_sub20_fasta_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            rng = random.Random(1770)
            genome = "".join(rng.choice("ACGT") for _ in range(1770))
            contigs = base / "genome.fa"
            contigs.write_text(f">synthetic_complete_genome\n{genome}\n>legacy_tiny\nACGT\n")
            sequences, manifest = module.collect(contigs)
            self.assertEqual(sequences["synthetic_complete_genome"], genome)
            self.assertEqual(manifest["routing_summary"]["accepted_occurrences"]["legacy_fasta_below_20"], 1)

    def test_builder_manifest_restriction_preserved_and_unfinished_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "fragmentos").mkdir()
            (base / "contigs.fasta").write_text(">contig\n" + "ACGT" * 40 + "\n")
            (base / "fragmentos/fragmentos.fasta").write_text(">normal\n" + "TGCA" * 20 + "\n")
            (base / "fragmentos/fragmentos_restritos.fasta").write_text(">restricted\n" + "CAGT" * 8 + "\n")
            for mate in (1, 2):
                fastq(base / f"nao_montadas_R{mate}.fq.gz", [(f"pair/{mate}", "AC" * 75)])
            manifest_path = base / "manifesto_execucao.json"
            data = {"genein_builder": "3.0.0b1", "estado": "concluido", "status": "ok"}
            manifest_path.write_text(json.dumps(data))
            sequences, manifest = module.collect(**module.builder_inputs(manifest_path))
            self.assertEqual(len(sequences), 4)
            restricted = [entry for entry in manifest["queries"].values() if "restrictions" in entry]
            self.assertEqual(restricted[0]["restrictions"], ["ESPECIFICIDADE_NAO_VALIDADA"])
            self.assertEqual(manifest["routing_summary"]["restricted_occurrences"], 1)
            data["estado"] = "falhou"
            manifest_path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "concluído"):
                module.builder_inputs(manifest_path)

    def test_builder_manifest_rejects_escape_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            manifest = base / "manifesto_execucao.json"
            manifest.write_text(json.dumps({"genein_builder": "3.0.0b1", "estado": "concluido", "status": "ok"}))
            (base / "contigs.fasta").symlink_to(ROOT / "README.md")
            with self.assertRaisesRegex(ValueError, "fora da pasta"):
                module.builder_inputs(manifest)

    def test_cli_requires_explicit_input(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(SCRIPT), "--out", str(Path(directory)/"q.fa"),
                                     "--manifest", str(Path(directory)/"q.json")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("--contigs ou --builder-manifest", result.stderr)


if __name__ == "__main__":
    unittest.main()
