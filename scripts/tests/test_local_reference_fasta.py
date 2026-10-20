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
        self.assertFalse((ROOT / "tmp" / "db-manager.lock").exists())

    def test_make_forwards_database_name_and_fasta_but_not_query_for_a_named_database(self):
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
        self.assertNotIn("DB_QUERY=", recipe)
        self.assertNotIn("Organism[Organism]", recipe)
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

    def test_named_profile_ignores_external_query_and_custom_keeps_quotes(self):
        named = _run(
            ["make", "-n", "db", "DB=ptv"],
            {"DB_QUERY": "Teschovirus[Organism]"},
        )
        self.assertEqual(named.returncode, 0, named.stderr)
        self.assertNotIn("DB_QUERY=", named.stdout)
        self.assertNotIn("Teschovirus[Organism]", named.stdout)

        custom = _run(
            ["make", "-n", "db", "DB=custom", 'DB_QUERY="Orbivirus"[Organism]'],
            {},
        )
        self.assertEqual(custom.returncode, 0, custom.stderr)
        self.assertIn("""DB_QUERY='"Orbivirus"[Organism]'""", custom.stdout)

    def test_db_manager_uses_profile_query_and_records_only_custom(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            bin_dir = base / "bin"
            bin_dir.mkdir()
            seen = base / "esearch.args"
            for name in ("esearch", "efetch"):
                tool = bin_dir / name
                tool.write_text(
                    "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$GENEIN_FAKE_ESEARCH_ARGS\"\nexit 1\n",
                    encoding="utf-8",
                )
                tool.chmod(0o755)
            work = base / "work"
            work.mkdir()
            env = {
                "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
                "GENEIN_FAKE_ESEARCH_ARGS": str(seen),
                "GENEIN_WORK_ROOT": str(work),
                "EDIRECT_RETRIES": "1",
                "EDIRECT_RETRY_DELAY": "0",
                "DB_QUERY": "Teschovirus[Organism]",
            }
            named = _run(
                ["bash", "scripts/ops/db_manager.sh", "setup"],
                {**env, "DB": "ptv"},
            )
            named_text = named.stdout + named.stderr
            self.assertIn("consulta externa foi ignorada", named_text)
            self.assertIn('DB_QUERY="Teschovirus"[Organism]', named_text)
            self.assertNotIn("DB_QUERY=Teschovirus[Organism]", named_text)
            self.assertIn('"Teschovirus"[Organism]', seen.read_text(encoding="utf-8"))
            self.assertNotIn("Teschovirus[Organism]", seen.read_text(encoding="utf-8").replace('"Teschovirus"[Organism]', ""))
            seen.write_text("", encoding="utf-8")

            custom = _run(
                ["bash", "scripts/ops/db_manager.sh", "setup"],
                {**env, "DB": "custom", "DB_QUERY": '"Orbivirus"[Organism]'},
            )
            custom_text = custom.stdout + custom.stderr
            self.assertNotIn("consulta externa foi ignorada", custom_text)
            self.assertIn('DB_QUERY="Orbivirus"[Organism]', custom_text)
            self.assertIn('"Orbivirus"[Organism]', seen.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
