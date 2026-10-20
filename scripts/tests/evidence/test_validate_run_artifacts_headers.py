import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from build_hsp_evidence import FIELDS as HSP_FIELDS
from validate_run_artifacts import validate_tsv


class ValidateRunArtifactsHeaderTests(unittest.TestCase):
    def test_partial_hsp_evidence_header_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hsp_evidence.tsv"
            partial = [
                "hsp_id", "qseqid", "sseqid", "task", "matches", "mismatches",
                "gaps", "locus_id", "eligible", "coord_system",
            ]
            path.write_text("\t".join(partial) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must equal producer FIELDS"):
                validate_tsv(path)

    def test_exact_hsp_evidence_header_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hsp_evidence.tsv"
            path.write_text("\t".join(HSP_FIELDS) + "\n", encoding="utf-8")
            validate_tsv(path)


if __name__ == "__main__":
    unittest.main()
