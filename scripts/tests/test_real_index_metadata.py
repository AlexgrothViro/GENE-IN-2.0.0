"""Real index creation and inspection only; no search, mapping or assembly."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evidence"))
from verify_blast_database_manifest import verify
from validate_mapping_reference import validate

TOOLS = ("makeblastdb", "blastdbcmd", "blastdb_aliastool", "bowtie2-build", "bowtie2-inspect")
MISSING = [name for name in TOOLS if not shutil.which(name)]


@unittest.skipUnless(os.name == "posix" and not MISSING, "PULOU: ferramentas de índice ausentes ou host não POSIX: " + ", ".join(MISSING))
class RealIndexMetadataTests(unittest.TestCase):
    def test_spaced_directory_and_prefix_produce_hash_receipt(self):
        with tempfile.TemporaryDirectory(prefix="index metadata with spaces ") as directory:
            work = Path(directory)
            reference = work / "reference with spaces.fa"
            reference.write_text(">fixture_a\nACGT\n>fixture_b\nTGCA\n")
            bank = work / "bank with spaces"
            index = work / "index with spaces"
            env = {**os.environ, "DB": "fixture", "REF_FASTA": str(reference), "BLAST_DB": str(bank), "BOWTIE2_INDEX": str(index),
                   "GENEIN_WORK_ROOT": str(work), "GENEIN_CONFIG_FILE": str(work / "empty configuration")}
            result = subprocess.run(["bash", str(ROOT / "scripts/ops/db_manager.sh"), "setup"], env=env, capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertGreater(verify(bank), 0)
            checked = validate(str(index), str(reference), None)
            hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in work.glob("index with spaces.*.bt2")}
            self.assertEqual(len(hashes), 6)
            manifest = json.loads(Path(str(bank) + ".db-manifest.json").read_text())
            receipt = {"scope": "index creation and metadata only", "complete_processing_executed": False,
                       "reference_sha256": checked["reference_sha256"], "database_files": manifest["produced_files"],
                       "mapping_index_files": hashes, "tools": {name: shutil.which(name) for name in TOOLS}}
            artifact_root = os.environ.get("GENEIN_TEST_ARTIFACT_ROOT")
            if artifact_root:
                target = Path(artifact_root)
                target.mkdir(parents=True, exist_ok=True)
                (target / "index-metadata-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
            print("METADATA_ONLY: database hashes and six index hashes recorded; complete processing not executed")


if __name__ == "__main__":
    unittest.main()
