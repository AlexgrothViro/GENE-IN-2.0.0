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


COLLECT_SPEC = importlib.util.spec_from_file_location(
    "collect_candidate_queries_real",
    ROOT / "scripts/pipeline/collect_candidate_queries.py",
)
collector = importlib.util.module_from_spec(COLLECT_SPEC)
COLLECT_SPEC.loader.exec_module(collector)


@unittest.skipUnless(os.environ.get("GENEIN_BUILDER_REAL_BIN"), "optional real Builder not requested")
class InstalledBuilderTest(unittest.TestCase):
    def test_real_interface_and_original_outputs(self):
        # Arbitrary deterministic paired-end reads for 3.0.0b1 e2e verification.
        rng = random.Random(17)
        text = "".join(rng.choice("ACGT") for _ in range(400))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reads1 = root / "input_R1.fastq"
            reads2 = root / "input_R2.fastq"
            records1 = [text[i:i + 100] for i in range(0, 301, 10)]
            records2 = [text[i + 50:i + 150] if i + 150 <= len(text) else text[:100] for i in range(0, 301, 10)]
            reads1.write_text("".join(f"@record{i}/1\n{read}\n+\n{'I' * len(read)}\n" for i, read in enumerate(records1)))
            reads2.write_text("".join(f"@record{i}/2\n{read}\n+\n{'I' * len(read)}\n" for i, read in enumerate(records2)))
            output = root / "output"
            with patch.dict(os.environ, {"GENEIN_BUILDER_BIN": os.environ["GENEIN_BUILDER_REAL_BIN"]}):
                self.assertEqual(adapter.main(["check"]), 0)
                code = adapter.run_builder(outdir=output, read1=reads1, read2=reads2)
            self.assertEqual(code, 0)
            raw = output / "builder_raw"
            manifest_path = raw / "manifesto_execucao.json"
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["genein_builder"], adapter.EXPECTED_VERSION)
            self.assertEqual(manifest["status"], "ok")
            table = (raw / "fragmentos/fragmentos.tsv").read_text()
            self.assertIn("cobertura_kmers", table)
            self.assertIn("faixa", table)
            self.assertTrue((raw / "RESUMO.txt").is_file())
            published = (output / "contigs.fasta").read_text()
            self.assertGreater(published.count(">"), 0)
            self.assertIn('BUILDER_VERSION="3.0.0b1"', (output / "builder_provenance.env").read_text())
            self.assertIn('BUILDER_MOTOR="megahit"', (output / "builder_provenance.env").read_text())
            sequences, query_manifest = collector.collect(**collector.builder_inputs(manifest_path))
            self.assertGreater(len(sequences), 0)
            self.assertEqual(query_manifest["routing_summary"]["resource_precheck"]["status"], "PASSED")

    def test_sample_steps_and_router_end_to_end_with_real_builder_3_0_0b1(self):
        import subprocess
        sample_steps_text = (ROOT / "scripts/pipeline/sample_steps.sh").read_text(encoding="utf-8")
        self.assertIn("--builder-manifest", sample_steps_text)
        pcv2_r1 = Path("/home/mestradoalex/viral-dbg/exemplos/pcv2_pequeno/leituras_R1.fq.gz")
        pcv2_r2 = Path("/home/mestradoalex/viral-dbg/exemplos/pcv2_pequeno/leituras_R2.fq.gz")
        if not (pcv2_r1.is_file() and pcv2_r2.is_file()):
            return
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = str(Path(os.environ["GENEIN_BUILDER_REAL_BIN"]).resolve().parent)
            env = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
                "GENEIN_BUILDER_BIN": os.environ["GENEIN_BUILDER_REAL_BIN"],
                "PIPELINE_CONFIG_LOADED": "1",
                "GENEIN_WORK_ROOT": str(root / "work"),
                "SAMPLE_NAME": "PCV2E2E",
                "SAMPLE_ID": "PCV2E2E",
                "SAMPLE_R1": str(pcv2_r1),
                "SAMPLE_R2": str(pcv2_r2),
                "ASSEMBLY_DIR": str(root / "assemblies"),
                "ASSEMBLER": "builder",
                "THREADS": "1",
            }
            res = subprocess.run(
                ["bash", str(ROOT / "scripts/pipeline/assembly_router.sh")],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
            manifest_path = root / "assemblies/PCV2E2E_builder/builder_raw/manifesto_execucao.json"
            self.assertTrue(manifest_path.is_file())
            q_fa = root / "candidate_queries.fa"
            q_json = root / "candidate_queries.json"
            q_sup = root / "candidate_supplement.fa"
            q_sum = root / "collection_summary.md"
            col = subprocess.run(
                [
                    os.environ.get("PYTHON", "python3"),
                    str(ROOT / "scripts/pipeline/collect_candidate_queries.py"),
                    "--builder-manifest", str(manifest_path),
                    "--out", str(q_fa),
                    "--manifest", str(q_json),
                    "--supplement-out", str(q_sup),
                    "--summary", str(q_sum),
                ],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(col.returncode, 0, col.stderr)
            q_data = json.loads(q_json.read_text(encoding="utf-8"))
            self.assertIn("contig_1", q_data["queries"])
            self.assertEqual(q_data["queries"]["contig_1"]["length_bp"], 1767)


if __name__ == "__main__":
    unittest.main()
