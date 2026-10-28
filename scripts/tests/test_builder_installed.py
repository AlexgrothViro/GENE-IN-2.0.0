"""Opt-in software integration with an installed Builder; no biological reference."""
import importlib.util
import json
import os
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("builder_adapter_real", ROOT / "scripts/pipeline/assemblers/builder_adapter.py")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


@unittest.skipUnless(os.environ.get("GENEIN_BUILDER_REAL_BIN"), "optional real Builder not requested")
class InstalledBuilderTest(unittest.TestCase):
    def test_real_interface_and_original_outputs(self):
        # Arbitrary deterministic text data for format/process verification only.
        rng = random.Random(17)
        text = "".join(rng.choice("ACGT") for _ in range(400))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reads = root / "input.fastq"
            records = [text[i:i + 100] for i in range(0, 301, 10)]
            reads.write_text("".join(f"@record{i}\n{read}\n+\n{'I' * len(read)}\n" for i, read in enumerate(records)))
            output = root / "output"
            with patch.dict(os.environ, {"GENEIN_BUILDER_BIN": os.environ["GENEIN_BUILDER_REAL_BIN"]}):
                self.assertEqual(adapter.main(["check"]), 0)
                code = adapter.run_builder(outdir=output, read1=reads, read2=None)
            self.assertEqual(code, 0)
            raw = output / "builder_raw"
            manifest = json.loads((raw / "manifesto_execucao.json").read_text())
            self.assertEqual(manifest["genein_builder"], adapter.EXPECTED_VERSION)
            self.assertEqual(manifest["status"], "ok")
            table = (raw / "fragmentos/fragmentos.tsv").read_text()
            self.assertIn("aviso_quimera", table)
            self.assertIn("avisos_variante", table)
            self.assertTrue((raw / "fragmentos/AVISO_ESPECIFICIDADE.txt").is_file())
            self.assertIn("hospedeiro não informado", (raw / "fragmentos/AVISO_ESPECIFICIDADE.txt").read_text())
            published = (output / "contigs.fasta").read_text()
            self.assertGreater(published.count(">"), 0)
            self.assertIn('BUILDER_VERSION="0.4.0"', (output / "builder_provenance.env").read_text())


if __name__ == "__main__":
    unittest.main()
