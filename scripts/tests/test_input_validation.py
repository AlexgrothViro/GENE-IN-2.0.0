import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "input_validation", ROOT / "scripts" / "lib" / "input_validation.py"
)
validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validation)


class InputValidationTests(unittest.TestCase):
    def test_sample_id_rejects_path_traversal_and_shell_chars(self):
        for value in ("../sample", "a/b", "sample name", "$(touch x)", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validation.validate_sample_id(value)

    def test_run_and_batch_ids_are_ascii_and_path_safe(self):
        self.assertEqual(validation.validate_run_id("run-safe-0001"), "run-safe-0001")
        self.assertEqual(validation.validate_batch_id("batch-01"), "batch-01")
        for value in ("short", "../run-safe", "execução-0001", "run id 0001"):
            with self.subTest(run_id=value):
                with self.assertRaises(ValueError):
                    validation.validate_run_id(value)
        for value in ("", "../batch", "lote suino", "lote-á"):
            with self.subTest(batch_id=value):
                with self.assertRaises(ValueError):
                    validation.validate_batch_id(value)

    def test_single_fastq_is_fully_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "single.fastq"
            path.write_text("@read1\nACGT\n+\nIII\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                validation.validate_fastq(path)

    def test_valid_single_fastq(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "single.fastq"
            path.write_text("@read1\nACGT\n+\nIIII\n", encoding="utf-8")
            self.assertEqual(validation.validate_fastq(path), 1)

    def test_paired_fastq_checks_ids_and_lengths(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            r1 = tmp / "R1.fastq.gz"
            r2 = tmp / "R2.fastq.gz"
            with gzip.open(r1, "wt") as fh:
                fh.write("@read1/1\nACGT\n+\nIIII\n")
            with gzip.open(r2, "wt") as fh:
                fh.write("@read2/2\nACGT\n+\nIIII\n")
            with self.assertRaises(ValueError):
                validation.validate_fastq(r1, r2)

    def test_fasta_rejects_duplicate_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contigs.fa"
            path.write_text(">c1\nACGT\n>c1\nACGT\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                validation.validate_fasta(path)

    def test_valid_paired_fastq(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            r1 = tmp / "R1.fastq"
            r2 = tmp / "R2.fastq"
            r1.write_text("@read1/1\nACGT\n+\nIIII\n", encoding="utf-8")
            r2.write_text("@read1/2\nTGCA\n+\nIIII\n", encoding="utf-8")
            self.assertEqual(validation.validate_fastq(r1, r2), 1)

    def test_compressed_fastq_without_records_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.fastq.gz"
            with gzip.open(path, "wt", encoding="utf-8"):
                pass
            with self.assertRaises(ValueError):
                validation.validate_fastq(path)

    def test_fastp_json_requires_before_and_after_read_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fastp.json"
            path.write_text(
                json.dumps(
                    {
                        "summary": {
                            "before_filtering": {"total_reads": 2, "total_bases": 200},
                            "after_filtering": {"total_reads": 2, "total_bases": 190},
                        }
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                validation.validate_fastp_json(path)["summary"]["after_filtering"]["total_reads"],
                2,
            )
            path.write_text(
                json.dumps({"summary": {"after_filtering": {"total_reads": 2}}}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                validation.validate_fastp_json(path)


if __name__ == "__main__":
    unittest.main()
