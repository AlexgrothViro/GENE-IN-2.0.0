"""Local reference FASTA: the caller chooses the database name and the file."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def _run(args, env, cwd=ROOT):
    merged = os.environ.copy()
    for key in ("DB", "DB_QUERY", "REF_FASTA", "BLAST_DB", "BOWTIE2_INDEX"):
        merged.pop(key, None)
    merged.update(env)
    return subprocess.run(
        args, cwd=cwd, env=merged, text=True, capture_output=True, check=False,
    )


class LocalReferenceFastaTests(unittest.TestCase):
    def test_missing_local_fasta_names_the_file_and_the_database(self):
        result = _run(
            ["bash", "scripts/ops/db_manager.sh", "setup"],
            {"DB": "meu_banco", "REF_FASTA": "/tmp/nao-existe-genein.fa"},
        )
        text = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/tmp/nao-existe-genein.fa", text)
        self.assertIn("REF_FASTA", text)
        self.assertNotIn("não tem perfil conhecido", text)
        self.assertNotIn("DB_QUERY vazio e DB", text)

    def test_make_forwards_database_name_fasta_and_query(self):
        result = _run(
            [
                "make", "-n", "db",
                "DB=meu_banco",
                "REF_FASTA=/dados/referencia.fa",
                "DB_QUERY=Organism[Organism]",
                "BLAST_DB=/dados/blastdb/meu_banco",
                "BOWTIE2_INDEX=/dados/bowtie2/meu_banco",
            ],
            {},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        recipe = result.stdout
        self.assertIn('DB="meu_banco"', recipe)
        self.assertIn('DB_QUERY="Organism[Organism]"', recipe)
        self.assertIn('REF_FASTA="/dados/referencia.fa"', recipe)
        self.assertIn('BLAST_DB="/dados/blastdb/meu_banco"', recipe)
        self.assertIn('BOWTIE2_INDEX="/dados/bowtie2/meu_banco"', recipe)

    def test_local_fasta_is_not_replaced_by_an_ncbi_profile_name(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fasta = base / "referencia.fa"
            fasta.write_text(">seq1\nACGTACGTACGTACGT\n", encoding="utf-8")
            blast = base / "blastdb" / "banco_local"
            bowtie = base / "bowtie2" / "banco_local"
            result = _run(
                ["bash", "scripts/ops/db_manager.sh", "setup"],
                {
                    "DB": "banco_local",
                    "REF_FASTA": str(fasta),
                    "BLAST_DB": str(blast),
                    "BOWTIE2_INDEX": str(bowtie),
                },
            )
            text = result.stdout + result.stderr
            self.assertNotIn("não tem perfil conhecido", text)
            self.assertNotIn("DB_QUERY vazio e DB", text)
            self.assertIn(str(fasta), text)
            inside = ROOT / "data" / "ref" / "banco_local.fa"
            self.assertFalse(inside.exists())
            if result.returncode == 0:
                self.assertTrue((base / "blastdb").exists())
                self.assertTrue(any((base / "blastdb").iterdir()))
                self.assertTrue(fasta.read_text(encoding="utf-8").startswith(">seq1"))
            else:
                self.assertTrue(
                    "makeblastdb" in text or "bowtie2-build" in text,
                    text,
                )


if __name__ == "__main__":
    unittest.main()
