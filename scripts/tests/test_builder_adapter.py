#!/usr/bin/env python3
"""Contrato do adaptador opcional genein-builder 0.4.0, sem o pacote privado."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "scripts" / "pipeline" / "assemblers" / "builder_adapter.py"
SPEC = importlib.util.spec_from_file_location("builder_adapter", ADAPTER_PATH)
builder_adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder_adapter)

PIN = "af7cb088b3013df07fd3abfaa23ba89dba42cf6b"
OTHER_COMMIT = "a" * 40
MARK = "ESPECIFICIDADE_NAO_VALIDADA"
TABLE_HEADER = (
    "fragmento\tcomprimento\tn_kmers\tcobertura_mediana\t"
    "cobertura_media\tphred_medio\tphred_mediana"
)
MAIN_HEADER = TABLE_HEADER + "\tfaixa"
RESTRICTED_HEADER = TABLE_HEADER + "\trestricao\tfaixa"


def write_mock(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def write_fasta(path: Path, records: list[tuple[str, str]]) -> None:
    lines = []
    for header, sequence in records:
        lines.append(f">{header}")
        for offset in range(0, len(sequence), 80):
            lines.append(sequence[offset:offset + 80])
    path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")


def builder_layout(root: Path) -> Path:
    """Saída da 0.4.0: o contig de 240 pb está em contigs.fasta e em fragmentos/."""
    fragment_dir = root / "fragmentos"
    fragment_dir.mkdir(parents=True)
    write_fasta(root / "contigs.fasta", [("NODE_1 len=240", "A" * 240)])
    write_fasta(fragment_dir / "fragmentos.fasta", [
        ("NODE_1 len=240 cob_mediana=6", "A" * 240),
        ("ext60 len=60 cob_mediana=4 phred_medio=35 escopo=teste", "T" * 60),
    ])
    (fragment_dir / "fragmentos.tsv").write_text(
        "# comentario antes do cabecalho\n"
        f"{MAIN_HEADER}\n"
        "NODE_1\t240\t210\t6\t6.0\t35\t35\t>=200\n"
        "ext60\t60\t30\t4\t4.0\t35\t35\t50-199\n",
        encoding="utf-8",
    )
    write_fasta(fragment_dir / "fragmentos_restritos.fasta", [
        ("f36 len=36 cob_mediana=2", "C" * 36),
        ("edge len=20", "T" * 20),
        ("short len=12", "G" * 12),
    ])
    (fragment_dir / "fragmentos_restritos.tsv").write_text(
        "# outra nota\n"
        "\n"
        f"{RESTRICTED_HEADER}\n"
        f"f36\t36\t6\t2\t2\t30\t30\t{MARK}\t31-49\n"
        f"edge\t20\t0\t\t\t\t\t{MARK}\t<31\n"
        f"short\t12\t0\t\t\t\t\t{MARK}\t<31\n",
        encoding="utf-8",
    )
    return fragment_dir


class BuilderConversionTests(unittest.TestCase):
    def test_current_warning_columns_are_accepted_without_changing_classification(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fragment_dir = builder_layout(root)
            before, counts_before = builder_adapter.convert_builder_products(root / "contigs.fasta", fragment_dir)
            for table in ("fragmentos.tsv", "fragmentos_restritos.tsv"):
                path = fragment_dir / table
                rows = []
                for line in path.read_text().splitlines():
                    if not line or line.startswith("#"):
                        rows.append(line)
                    elif line.startswith("fragmento\t"):
                        rows.append(line + "\taviso_quimera\tavisos_variante")
                    else:
                        rows.append(line + "\tnao_avaliavel\tnao_disponivel")
                path.write_text("\n".join(rows) + "\n")
            after, counts_after = builder_adapter.convert_builder_products(root / "contigs.fasta", fragment_dir)
            self.assertEqual(before, after)
            self.assertEqual(counts_before, counts_after)

    def test_raw_output_replacement_archives_previous_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, output = root / "raw", root / "output"
            raw.mkdir()
            output.mkdir()
            (raw / "manifesto_execucao.json").write_text("first")
            builder_adapter._preserve_raw(raw, output)
            (raw / "manifesto_execucao.json").write_text("second")
            builder_adapter._preserve_raw(raw, output)
            previous = list((output / "descarte").glob("*/builder_raw/manifesto_execucao.json"))
            self.assertEqual(len(previous), 1)
            self.assertEqual(previous[0].read_text(), "first")
            self.assertEqual((output / "builder_raw/manifesto_execucao.json").read_text(), "second")

    def test_contig_repeated_in_fragments_is_published_once(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fragment_dir = builder_layout(root)
            fasta, counts = builder_adapter.convert_builder_products(root / "contigs.fasta", fragment_dir)
        self.assertEqual(counts, {"contigs": 1, "fragments": 3, "dropped_lt20": 1})
        records = [block for block in fasta.split(">") if block]
        self.assertEqual(len(records), 4)
        sequences = ["".join(block.splitlines()[1:]) for block in records]
        self.assertEqual(len(set(sequences)), len(sequences))
        self.assertEqual(sequences.count("A" * 240), 1)
        self.assertTrue(records[0].startswith(
            "builder|class=contig|source_id=NODE_1|len=240|faixa=ge200|restricao=nenhuma"
            "|k=31|tool=genein-builder\n"
        ))
        self.assertIn("class=fragment|source_id=ext60|len=60|faixa=50-199|restricao=nenhuma", records[1])
        self.assertIn(f"class=fragment|source_id=f36|len=36|faixa=31-49|restricao={MARK}", records[2])
        self.assertIn(f"class=fragment|source_id=edge|len=20|faixa=lt31|restricao={MARK}", records[3])
        self.assertNotIn("G" * 12, fasta)
        self.assertNotIn("<", fasta)

    def test_contig_absent_or_different_in_fragments_is_rejected(self):
        for name, sequence in (("NODE_9", "A" * 240), ("NODE_1", "C" * 240)):
            with self.subTest(name=name):
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    fragment_dir = builder_layout(root)
                    write_fasta(root / "contigs.fasta", [(name, sequence)])
                    with self.assertRaisesRegex(ValueError, "sem o mesmo registro em fragmentos"):
                        builder_adapter.convert_builder_products(root / "contigs.fasta", fragment_dir)

    def test_fasta_record_without_table_row_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fragment_dir = builder_layout(root)
            with (fragment_dir / "fragmentos.fasta").open("a", encoding="utf-8") as handle:
                handle.write(">solto\n" + ("A" * 50) + "\n")
            with self.assertRaisesRegex(ValueError, "fora de fragmentos.tsv"):
                builder_adapter.convert_builder_products(root / "contigs.fasta", fragment_dir)

    def test_table_without_faixa_is_rejected(self):
        with TemporaryDirectory() as tmp:
            fragment_dir = Path(tmp) / "fragmentos"
            fragment_dir.mkdir()
            (fragment_dir / "fragmentos.tsv").write_text(
                f"{TABLE_HEADER}\next60\t60\t30\t4\t4.0\t35\t35\n", encoding="utf-8",
            )
            write_fasta(fragment_dir / "fragmentos.fasta", [("ext60", "T" * 60)])
            with self.assertRaisesRegex(ValueError, "faixa"):
                builder_adapter.convert_builder_products(None, fragment_dir)

    def test_megahit_header_does_not_claim_k31(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fragment_dir = builder_layout(root)
            fasta, _ = builder_adapter.convert_builder_products(
                root / "contigs.fasta", fragment_dir, k=builder_adapter.BUILDER_K["megahit"],
            )
        self.assertIn("|k=NA|tool=genein-builder", fasta)
        self.assertNotIn("k=31", fasta)

    def test_empty_and_zero_byte_products_publish_no_sequence(self):
        fasta, counts = builder_adapter.convert_builder_products(None, None)
        self.assertEqual(fasta, "")
        self.assertEqual(counts, {"contigs": 0, "fragments": 0, "dropped_lt20": 0})
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fragment_dir = root / "fragmentos"
            fragment_dir.mkdir()
            (root / "contigs.fasta").write_bytes(b"")
            (fragment_dir / "fragmentos.fasta").write_bytes(b"")
            (fragment_dir / "fragmentos.tsv").write_text(
                f"# vazio\n{MAIN_HEADER}\n", encoding="utf-8",
            )
            fasta, counts = builder_adapter.convert_builder_products(
                root / "contigs.fasta", fragment_dir,
            )
        self.assertEqual(fasta, "")
        self.assertEqual(counts["contigs"], 0)
        self.assertEqual(counts["fragments"], 0)

    def test_sequence_outside_acgtn_is_rejected(self):
        with TemporaryDirectory() as tmp:
            fragment_dir = Path(tmp) / "fragmentos"
            fragment_dir.mkdir()
            (fragment_dir / "fragmentos.tsv").write_text(
                f"{MAIN_HEADER}\nbad\t20\t1\t1\t1\t30\t30\t<31\n",
                encoding="utf-8",
            )
            (fragment_dir / "fragmentos.fasta").write_text(
                ">bad\n" + ("A" * 19) + "Y\n", encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                builder_adapter.convert_builder_products(None, fragment_dir)

    def test_long_fragment_without_fasta_is_rejected(self):
        with TemporaryDirectory() as tmp:
            fragment_dir = Path(tmp) / "fragmentos"
            fragment_dir.mkdir()
            (fragment_dir / "fragmentos.tsv").write_text(
                f"# nota\n{MAIN_HEADER}\nsolo\t50\t1\t1\t1\t30\t30\t50-199\n",
                encoding="utf-8",
            )
            (fragment_dir / "fragmentos.fasta").write_bytes(b"")
            with self.assertRaises(ValueError):
                builder_adapter.convert_builder_products(None, fragment_dir)

    def test_manifest_commit_values(self):
        commit = builder_adapter.manifest_commit
        self.assertEqual(commit({"commit": OTHER_COMMIT}), OTHER_COMMIT)
        self.assertEqual(
            commit({"commit": "árvore suja", "commit_head": PIN}), f"{PIN}+arvore_suja",
        )
        self.assertEqual(commit({"commit": "sem git"}), "sem_git")
        self.assertEqual(commit({}), "unavailable")
        self.assertEqual(commit({"commit": "abc; rm"}), "unavailable")

    def test_convert_cli_reads_status_and_commit_from_manifest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fragment_dir = builder_layout(root)
            manifest = root / "manifesto_execucao.json"
            manifest.write_text(json.dumps({
                "genein_builder": "0.4.0", "status": "so_fragmentos", "commit": OTHER_COMMIT,
            }), encoding="utf-8")
            out = root / "published.fasta"
            provenance = root / "builder_provenance.env"
            with patch.dict(os.environ, {
                "GENEIN_BUILDER_VERSION": "9.9.9", "GENEIN_BUILDER_COMMIT": "should-not-stick",
            }):
                code = builder_adapter.main([
                    "convert", "--contigs", str(root / "contigs.fasta"),
                    "--fragment-dir", str(fragment_dir), "--manifest", str(manifest),
                    "--out", str(out), "--provenance", str(provenance),
                ])
            self.assertEqual(code, 0)
            text = provenance.read_text(encoding="utf-8")
            self.assertIn('BUILDER_STATUS="SO_FRAGMENTOS"', text)
            self.assertIn('BUILDER_VERSION="0.4.0"', text)
            self.assertIn(f'BUILDER_COMMIT="{OTHER_COMMIT}"', text)
            self.assertIn('BUILDER_MOTOR="v1"', text)
            self.assertIn('BUILDER_K="31"', text)
            self.assertNotIn("should-not-stick", text)
            self.assertNotIn("9.9.9", text)
            self.assertNotIn(PIN, text)

            code = builder_adapter.main(["convert", "--out", str(out), "--provenance", str(provenance)])
            self.assertEqual(code, 0)
            text = provenance.read_text(encoding="utf-8")
            self.assertIn('BUILDER_STATUS="UNRECORDED"', text)
            self.assertIn('BUILDER_COMMIT="unavailable"', text)
            self.assertIn('BUILDER_VERSION="unavailable"', text)

    def test_argv_matches_0_4_0_contract_without_assumed_host(self):
        common = dict(output=Path("/tmp/out"), read1=Path("/tmp/R1.fq.gz"))
        paired = builder_adapter.builder_argv(["genein-builder"], read2=Path("/tmp/R2.fq.gz"), **common)
        single = builder_adapter.builder_argv(["genein-builder"], read2=None, **common)
        megahit = builder_adapter.builder_argv(
            ["genein-builder"], read2=Path("/tmp/R2.fq.gz"), motor="megahit", threads=3, **common,
        )
        self.assertEqual(paired, [
            "genein-builder", "run",
            "--r1", "/tmp/R1.fq.gz",
            "--r2", "/tmp/R2.fq.gz",
            "--saida", "/tmp/out",
            "--motor", "v1",
        ])
        self.assertEqual(single, [
            "genein-builder", "run",
            "--r1", "/tmp/R1.fq.gz",
            "--saida", "/tmp/out",
            "--motor", "v1",
        ])
        self.assertEqual(megahit[megahit.index("--motor"):], [
            "--motor", "megahit", "-t", "3",
        ])
        for argv in (paired, single):
            self.assertNotIn("-t", argv)
        for argv in (paired, single, megahit):
            self.assertNotIn("--hospedeiro", argv)
            self.assertNotIn("--threads", argv)
            self.assertNotIn("--single", argv)
            self.assertNotIn("--fragmentos", argv)
        self.assertNotIn("--r2", single)
        with self.assertRaises(ValueError):
            builder_adapter.builder_argv(["genein-builder"], read2=None, threads=2, **common)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            builder_adapter.main([
                "run", "--sample", "S", "--outdir", "/tmp/x", "--r1", "/tmp/R1.fq.gz", "--threads", "2",
            ])


class BuilderInstallTests(unittest.TestCase):
    def test_missing_install_stops_with_an_explicit_error(self):
        with TemporaryDirectory() as tmp:
            outdir = Path(tmp) / "out"
            with patch.object(builder_adapter.shutil, "which", return_value=None), \
                 patch.object(builder_adapter.importlib.util, "find_spec", return_value=None), \
                 patch.dict(os.environ, {"GENEIN_BUILDER_BIN": ""}, clear=False):
                os.environ.pop("GENEIN_BUILDER_BIN", None)
                with contextlib.redirect_stderr(io.StringIO()) as captured:
                    code = builder_adapter.main([
                        "run", "--sample", "BUILDERFIX",
                        "--r1", str(Path(tmp) / "R1.fastq.gz"),
                        "--r2", str(Path(tmp) / "R2.fastq.gz"),
                        "--outdir", str(outdir),
                    ])
            self.assertIn("nao esta instalado", captured.getvalue())
            self.assertEqual(code, 2)
            provenance = (outdir / "builder_provenance.env").read_text(encoding="utf-8")
            self.assertIn('BUILDER_STATUS="MISSING"', provenance)
            self.assertIn('BUILDER_COMMIT="unavailable"', provenance)
            self.assertIn('BUILDER_VERSION="unavailable"', provenance)
            self.assertIn('BUILDER_MOTOR="v1"', provenance)
            self.assertFalse((outdir / "contigs.fasta").exists())

    def test_module_fallback_uses_the_0_2_0_entry_point(self):
        with patch.object(builder_adapter.shutil, "which", return_value=None), \
             patch.object(builder_adapter.importlib.util, "find_spec", return_value=object()) as spec, \
             patch.dict(os.environ, {"GENEIN_BUILDER_BIN": ""}, clear=False):
            self.assertEqual(
                builder_adapter.locate_builder(), [sys.executable, "-m", "genein_builder_cli.cli"],
            )
        spec.assert_called_with("genein_builder_cli")

    def test_subprocess_missing_install_message(self):
        with TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.pop("GENEIN_BUILDER_BIN", None)
            env["PATH"] = "/usr/bin:/bin"
            env["PYTHONPATH"] = ""
            completed = subprocess.run(
                [
                    sys.executable, str(ADAPTER_PATH), "run",
                    "--sample", "BUILDERFIX",
                    "--r1", str(Path(tmp) / "R1.fastq.gz"),
                    "--r2", str(Path(tmp) / "R2.fastq.gz"),
                    "--outdir", tmp,
                ],
                check=False, capture_output=True, text=True, env=env,
            )
        if "nao esta instalado" not in completed.stderr:
            self.skipTest("genein-builder esta instalado neste interpretador")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("bash bundle/install_builder.sh", completed.stderr)
        self.assertIn(PIN, completed.stderr)
        self.assertIn("genein-builder 0.4.0", completed.stderr)
        self.assertIn("nao troca para", completed.stderr)


# Builder 0.4.0 simulado: --version, argumentos gravados em MOCK_ARGS e, conforme MOCK_MODE,
# saída com status e commit no manifesto ou um código de saída.
MOCK = """#!{python}
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
if args == ["--version"]:
    print("genein-builder " + os.environ.get("MOCK_VERSION", "0.4.0"))
    raise SystemExit(0)
if os.environ.get("MOCK_ARGS"):
    Path(os.environ["MOCK_ARGS"]).write_text("\\n".join(args) + "\\n", encoding="utf-8")
if args[:1] != ["run"] or {{"--single", "--threads", "--fragmentos"}} & set(args):
    raise SystemExit(2)
if "-t" in args and args[args.index("--motor") + 1] != "megahit":
    raise SystemExit(2)
saida = Path(args[args.index("--saida") + 1])
mode = os.environ.get("MOCK_MODE", "ok")
if mode.startswith("exit"):
    raise SystemExit(int(mode[4:]))
saida.mkdir(parents=True, exist_ok=True)
status = {{"ok": "ok", "short": "so_fragmentos", "nokmer": "sem_kmer_valido",
           "norecords": "sem_registros"}}.get(mode)
if status is not None:
    (saida / "manifesto_execucao.json").write_text(json.dumps({{
        "genein_builder": "0.4.0", "status": status,
        "commit": os.environ.get("MOCK_COMMIT", "{pin}"),
    }}, ensure_ascii=False), encoding="utf-8")
if mode in ("nokmer", "norecords", "nomanifest3"):
    raise SystemExit(3)
frag = saida / "fragmentos"
frag.mkdir()
head = "fragmento\\tcomprimento\\tn_kmers\\tcobertura_mediana\\tcobertura_media\\tphred_medio\\tphred_mediana"
if mode == "ok":
    (saida / "contigs.fasta").write_text(">NODE_1 len=240\\n" + "A" * 240 + "\\n")
    (frag / "fragmentos.fasta").write_text(">NODE_1 len=240\\n" + "A" * 240 + "\\n")
    (frag / "fragmentos.tsv").write_text("# nota\\n" + head + "\\tfaixa\\nNODE_1\\t240\\t210\\t6\\t6\\t35\\t35\\t>=200\\n")
else:
    (saida / "contigs.fasta").write_text("")
    (frag / "fragmentos.fasta").write_text("")
    (frag / "fragmentos.tsv").write_text("# nota\\n" + head + "\\tfaixa\\n")
(frag / "fragmentos_restritos.fasta").write_text(">f36 len=36\\n" + "C" * 36 + "\\n")
(frag / "fragmentos_restritos.tsv").write_text(
    head + "\\trestricao\\tfaixa\\nf36\\t36\\t6\\t2\\t2\\t30\\t30\\t{mark}\\t31-49\\n")
"""


class BuilderMockRunTests(unittest.TestCase):
    def run_mock(self, root: Path, mode: str, **kwargs) -> tuple[int, Path, str]:
        mock = root / "genein-builder"
        write_mock(mock, MOCK.format(python=sys.executable, pin=PIN, mark=MARK))
        outdir = root / "published"
        env = {
            "GENEIN_BUILDER_BIN": str(mock),
            "MOCK_MODE": mode,
            "MOCK_ARGS": str(root / "args"),
            "GENEIN_BUILDER_VERSION": "9.9.9",
            "GENEIN_BUILDER_COMMIT": "should-not-stick",
        }
        env.update(kwargs.pop("env", {}))
        with patch.dict(os.environ, env):
            with contextlib.redirect_stderr(io.StringIO()) as captured, \
                 contextlib.redirect_stdout(io.StringIO()):
                code = builder_adapter.run_builder(
                    outdir=outdir, read1=root / "R1.fastq.gz", read2=root / "R2.fastq.gz", **kwargs,
                )
        return code, outdir, captured.getvalue()

    def provenance(self, outdir: Path) -> str:
        return (outdir / "builder_provenance.env").read_text(encoding="utf-8")

    def test_ok_records_installed_version_and_manifest_commit(self):
        with TemporaryDirectory() as tmp:
            code, outdir, stderr = self.run_mock(Path(tmp), "ok", env={"MOCK_COMMIT": OTHER_COMMIT})
            self.assertEqual(code, 0)
            provenance = self.provenance(outdir)
            self.assertIn('BUILDER_STATUS="OK"', provenance)
            self.assertIn('BUILDER_VERSION="0.4.0"', provenance)
            self.assertIn(f'BUILDER_COMMIT="{OTHER_COMMIT}"', provenance)
            self.assertIn('BUILDER_CONTIG_COUNT="1"', provenance)
            self.assertIn('BUILDER_FRAGMENT_COUNT="1"', provenance)
            self.assertNotIn("should-not-stick", provenance)
            self.assertNotIn("9.9.9", provenance)
            self.assertIn("difere do fixado", stderr)
            fasta = (outdir / "contigs.fasta").read_text(encoding="utf-8")
            self.assertEqual(fasta.splitlines().count("A" * 240), 1)
            self.assertEqual(fasta.count(">"), 2)
            self.assertTrue((outdir / "builder_raw" / "manifesto_execucao.json").is_file())
            args = (Path(tmp) / "args").read_text(encoding="utf-8").split()
            self.assertEqual(args[args.index("--motor") + 1], "v1")
            self.assertNotIn("-t", args)

    def test_so_fragmentos_status_comes_from_manifest(self):
        with TemporaryDirectory() as tmp:
            code, outdir, stderr = self.run_mock(Path(tmp), "short")
            self.assertEqual(code, 0)
            provenance = self.provenance(outdir)
            self.assertIn('BUILDER_STATUS="SO_FRAGMENTOS"', provenance)
            self.assertIn(f'BUILDER_COMMIT="{PIN}"', provenance)
            self.assertNotIn("difere do fixado", stderr)
            self.assertIn("class=fragment|source_id=f36|len=36|faixa=31-49",
                          (outdir / "contigs.fasta").read_text(encoding="utf-8"))

    def test_code_3_records_manifest_status_without_publishing(self):
        for mode, status in (("nokmer", "SEM_KMER_VALIDO"), ("norecords", "SEM_REGISTROS")):
            with self.subTest(mode=mode), TemporaryDirectory() as tmp:
                code, outdir, stderr = self.run_mock(Path(tmp), mode)
                self.assertEqual(code, 1)
                provenance = self.provenance(outdir)
                self.assertIn(f'BUILDER_STATUS="{status}"', provenance)
                self.assertIn(f'BUILDER_COMMIT="{PIN}"', provenance)
                self.assertIn('BUILDER_VERSION="0.4.0"', provenance)
                self.assertFalse((outdir / "contigs.fasta").exists())
                self.assertTrue((outdir / "builder_raw" / "manifesto_execucao.json").is_file())
                self.assertIn("nenhum outro montador", stderr)

    def test_code_3_without_manifest_is_failed(self):
        with TemporaryDirectory() as tmp:
            code, outdir, _ = self.run_mock(Path(tmp), "nomanifest3")
            self.assertEqual(code, 1)
            provenance = self.provenance(outdir)
            self.assertIn('BUILDER_STATUS="FAILED"', provenance)
            self.assertIn('BUILDER_COMMIT="unavailable"', provenance)

    def test_megahit_motor_passes_threads(self):
        with TemporaryDirectory() as tmp:
            code, outdir, _ = self.run_mock(Path(tmp), "ok", motor="megahit", threads=3)
            self.assertEqual(code, 0)
            args = (Path(tmp) / "args").read_text(encoding="utf-8").split()
            self.assertEqual(args[args.index("--motor") + 1:args.index("--motor") + 4], ["megahit", "-t", "3"])
            provenance = self.provenance(outdir)
            self.assertIn('BUILDER_MOTOR="megahit"', provenance)
            self.assertIn('BUILDER_K="NA"', provenance)
            self.assertIn("|k=NA|", (outdir / "contigs.fasta").read_text(encoding="utf-8"))

    def test_other_version_is_refused_before_running(self):
        with TemporaryDirectory() as tmp:
            code, outdir, stderr = self.run_mock(Path(tmp), "ok", env={"MOCK_VERSION": "0.1.3"})
            self.assertEqual(code, 2)
            self.assertFalse((Path(tmp) / "args").exists())
            provenance = self.provenance(outdir)
            self.assertIn('BUILDER_STATUS="FAILED"', provenance)
            self.assertIn('BUILDER_VERSION="0.1.3"', provenance)
            self.assertIn("contrato da 0.4.0", stderr)

    def test_exit_codes_1_and_2_are_errors(self):
        for builder_code in (1, 2):
            with self.subTest(builder_code=builder_code), TemporaryDirectory() as tmp:
                code, outdir, _ = self.run_mock(Path(tmp), f"exit{builder_code}")
                self.assertEqual(code, builder_code)
                self.assertFalse((outdir / "contigs.fasta").exists())
                provenance = self.provenance(outdir)
                self.assertIn('BUILDER_STATUS="FAILED"', provenance)
                self.assertIn('BUILDER_VERSION="0.4.0"', provenance)
                self.assertIn('BUILDER_COMMIT="unavailable"', provenance)

    def test_other_nonzero_exit_is_reported_as_1(self):
        with TemporaryDirectory() as tmp:
            code, outdir, _ = self.run_mock(Path(tmp), "exit42")
            self.assertEqual(code, 1)
            self.assertFalse((outdir / "contigs.fasta").exists())
            self.assertIn('BUILDER_STATUS="FAILED"', self.provenance(outdir))


if __name__ == "__main__":
    unittest.main()
