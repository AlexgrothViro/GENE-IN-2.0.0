"""Correction 4.2: quando a montagem produz 0 contigs, o estagio Evidence
(scripts/evidence/run.sh) deve reconhecer isso como um desfecho negativo
legitimo -- emitir o contrato de 3 arquivos apenas com cabecalho e concluir
com exit 0 -- em vez de abortar com "[FATAL] query FASTA or evidence config
is missing", que era o comportamento antes desta correcao (ver
DECISAO_ENCERRAMENTO_GENEIN.md secao 4.2 e o caso DEV_NEG_RANDOM/braco SPAdes).

run.sh e um script bash e nao pode ser executado diretamente neste sandbox de
desenvolvimento (MSYS2/Git-Bash falha na inicializacao aqui com
NtCreateDirectoryObject; ver notas em test_host_filter.py). A mudanca feita
em run.sh e pequena e foi verificada por leitura manual linha a linha:
  1. o gate de entrada agora distingue "PROFILES vazio" e "QUERIES ausente"
     (fatais, inalterados) de "QUERIES presente porem vazio" (0 contigs: novo
     ramo QUERIES_HAS_SEQUENCES=false, nao fatal);
  2. a chamada a input_validation.py fasta (que rejeita FASTA vazia) e pulada
     quando QUERIES_HAS_SEQUENCES=false;
  3. no ramo --composite-db, blastn/blast_router.py nunca e invocado quando
     QUERIES_HAS_SEQUENCES=false -- TSVs de saida vazios sao escritos
     diretamente, preservando "nunca chamar BLAST com FASTA vazia".

Este teste cobre a parte que PODE ser executada aqui: a cadeia real de scripts
Python do Evidence (aggregate_hsps -> build_loci -> build_hsp_evidence ->
competitive_hits -> classify_sample -> export_evidence), exatamente como
run.sh os invoca, alimentada com uma FASTA de consulta vazia e TSVs de BLAST
vazios (o que run.sh agora produz para 0 contigs). Confirma que nenhum desses
estagios exige um FATAL sobre entrada vazia -- ou seja, que o unico bloqueio
real para 0 contigs sempre foi o gate de entrada do proprio run.sh, e que
relaxar aquele gate (passo 1 acima) e suficiente para obter o contrato de
negativo limpo exigido pela correcao 4.2.
"""
import json
import os
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "scripts" / "evidence"


class ZeroContigsEvidenceChainTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="genein_zero_contigs_test_")
        self.addCleanup(self.temp_dir.cleanup)
        self.tmp = Path(self.temp_dir.name)
        self.env = {**os.environ, "PYTHONPATH": str(EVIDENCE_DIR)}
        # Mimic exactly what the corrected run.sh writes for a 0-contig
        # sample: an empty query FASTA and empty (headerless) BLAST TSVs.
        self.queries = self.tmp / "queries.fa"
        self.queries.write_bytes(b"")
        self.short_tsv = self.tmp / "blastn-short.tsv"
        self.short_tsv.write_bytes(b"")
        self.conv_tsv = self.tmp / "blastn.tsv"
        self.conv_tsv.write_bytes(b"")

    def _run(self, script, args):
        result = subprocess.run(
            [sys.executable, str(EVIDENCE_DIR / script), *args],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(result.returncode, 0, f"{script} failed:\n{result.stderr}")
        return result

    def test_zero_contigs_flow_completes_with_no_signal_instead_of_crashing(self):
        frag = self.tmp / "fragment_evidence.tsv"
        self._run("aggregate_hsps.py", [
            "--blast", f"blastn-short={self.short_tsv}", "--blast", f"blastn={self.conv_tsv}",
            "--query-fasta", str(self.queries), "--out", str(frag),
        ])
        self.assertTrue(frag.read_text().startswith("qseqid\t"))
        self.assertEqual(len(frag.read_text().splitlines()), 1, "0 contigs must yield 0 fragment rows")

        loci = self.tmp / "locus_evidence.tsv"
        self._run("build_loci.py", ["--fragments", str(frag), "--gap-bp", "200", "--out", str(loci)])

        hsp = self.tmp / "hsp_evidence.tsv"
        self._run("build_hsp_evidence.py", [
            "--blast", f"blastn-short={self.short_tsv}", "--blast", f"blastn={self.conv_tsv}",
            "--loci", str(loci), "--out", str(hsp),
        ])

        comp = self.tmp / "competitive_hits.tsv"
        self._run("competitive_hits.py", [
            "--fragments", str(frag), "--minimum-delta-bitscore", "10",
            "--maximum-qcov-difference-pp", "10", "--out", str(comp), "--search-complete",
        ])

        # Placeholders run.sh itself writes directly (no script call) when no
        # read-mapping panel is configured -- unaffected by this correction.
        read_support = self.tmp / "read_support.tsv"
        read_support.write_text(
            "sample_id\treference_id\tcategory\tlocus_id\torientation\tquery_ids\tlibrary_mode\t"
            "umi_mode\tsupport_status\tunique_templates\tdistinct_starts\tproper_pair_templates\t"
            "discordant_templates\tminimum_mapq\n"
        )
        coverage = self.tmp / "coverage.tsv"
        coverage.write_text(
            "reference_id\tcategory\tlocus_id\torientation\tquery_ids\treference_length\tlocus_length\t"
            "covered_bases_1x\tcovered_bases_3x\tbreadth_1x\tbreadth_3x\tmean_depth_locus\t"
            "median_depth_covered\tmin_depth_covered\tmax_window_depth_fraction\t"
            "concentration_window_bp\tminimum_mapq\tminimum_base_quality\n"
        )

        sample_evidence = self.tmp / "sample_evidence.json"
        self._run("classify_sample.py", [
            "--sample", "DEV_NEG_RANDOM", "--loci", str(loci), "--competitive", str(comp),
            "--read-support", str(read_support), "--coverage", str(coverage),
            "--control-status", "UNCONTROLLED", "--library-mode", "shotgun",
            "--out", str(sample_evidence), "--run-id", "test-zero-contigs",
        ])
        doc = json.loads(sample_evidence.read_text(encoding="utf-8"))
        self.assertEqual(doc["candidates"], [])
        self.assertEqual(doc["analysis_outcome"], "NO_EVIDENCE_RECOVERED")
        self.assertEqual(doc["evidence_level"], "NO_SIGNAL")
        self.assertEqual(doc["execution_status"], "done")

        report = self.tmp / "evidence_report.md"
        self._run("export_evidence.py", ["--json", str(sample_evidence), "--out", str(report)])
        report_text = report.read_text(encoding="utf-8")
        self.assertIn("SEM_CANDIDATOS_PARA_REVISAO", report_text)
        self.assertNotIn("| Resultado da análise | `NO_EVIDENCE_RECOVERED`", report_text)


if __name__ == "__main__":
    unittest.main()
