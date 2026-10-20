import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def blast_row(qseqid, length, qlen, evalue="1e-20", bitscore="100"):
    fields = [qseqid, "virus_ref", "100", str(length), "0", "0", "1", str(length), "1", str(length), evalue, bitscore, str(qlen), "1000"]
    return "\t".join(fields)


class AssemblyRescueTests(unittest.TestCase):
    def test_filter_keeps_best_read_and_records_criteria_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw.tsv"
            output = root / "candidates.tsv"
            raw.write_text(
                "\n".join([
                    blast_row("read-good", 100, 100, bitscore="90"),
                    blast_row("read-good", 100, 100, bitscore="110"),
                    blast_row("read-embedded-short", 20, 150),
                    blast_row("read-bad-evalue", 100, 100, evalue="1e-2"),
                ]) + "\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts/pipeline/filter_rescue_reads.py"), "--blast-raw", str(raw), "--out-tsv", str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with output.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual([row["qseqid"] for row in rows], ["read-good"])
            provenance = json.loads((output.with_suffix(output.suffix + ".provenance.json")).read_text(encoding="utf-8"))
            self.assertEqual(provenance["criteria"]["minimum_alignment_length_bp"], 80)
            self.assertEqual(provenance["candidate_count"], 1)

    def test_short_fragment_extractor_validates_fasta_and_preserves_20_to_49_bin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fasta = root / "input.fa"
            fasta.write_text(">twenty\n" + "A" * 20 + "\n>nineteen\n" + "C" * 19 + "\n", encoding="utf-8")
            output = root / "out"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts/pipeline/extract_short_fragments.py"), "--input", str(fasta), "--sample", "sample", "--out-dir", str(output), "--min-len", "20", "--max-len", "49"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((output / "sample_short_fragments.fa").read_text(encoding="utf-8").count(">"), 1)

            malformed = root / "malformed.fa"
            malformed.write_text("ACGT\n", encoding="utf-8")
            rejected = subprocess.run(
                [sys.executable, str(ROOT / "scripts/pipeline/extract_short_fragments.py"), "--input", str(malformed), "--sample", "sample", "--out-dir", str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)


if __name__ == "__main__":
    unittest.main()
