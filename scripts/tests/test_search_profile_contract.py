"""GEN-013: the A/B/C search profiles are a run contract, not a new default.

Engineering-level checks only (no real sample, no 30-minute E2E): the resolver
freezes an identity, the manifest declares it, the minimal report prints it,
and the pipeline still turns B and C on only when the run asks for them.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from resolve_config import resolve_pipeline_config  # noqa: E402
from search_profile_manifest import build_manifest  # noqa: E402

PIPELINE_RUN = "\n".join((ROOT / "scripts/pipeline" / part).read_text(encoding="utf-8") for part in ("prepare_run.sh", "sample_steps.sh", "run.sh"))
EVIDENCE_RUN = (ROOT / "scripts" / "evidence" / "run.sh").read_text(encoding="utf-8")


def resolved(**overrides) -> dict:
    kwargs = dict(
        repo_root="/repo", incoming={}, sourced={}, cli={}, sample_name="amostra1",
        analysis_profiles_config=str(ROOT / "config" / "analysis_profiles.json"),
    )
    kwargs.update(overrides)
    return resolve_pipeline_config(**kwargs)


class SearchProfileManifestTests(unittest.TestCase):
    def test_default_manifest_declares_only_profile_a(self):
        manifest = build_manifest(config=resolved(), sample="amostra1")
        self.assertEqual(manifest["identity"], "search-profile:A")
        self.assertEqual(manifest["selected"], "A")
        self.assertTrue(manifest["profiles"]["A"]["active"])
        self.assertFalse(manifest["profiles"]["B"]["active"])
        self.assertFalse(manifest["profiles"]["C"]["active"])
        self.assertFalse(manifest["evidence_v2"])

    def test_profile_c_manifest_carries_its_own_artifacts_and_the_shared_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fragments = root / "fragments.fa"
            fragments.write_text(">frag-1\nACGTACGTAC\n", encoding="utf-8")
            short_tsv = root / "short.tsv"
            short_tsv.write_text("frag-1\tref-1\t100\t10\n", encoding="utf-8")
            db_manifest = root / "custom.db-manifest.json"
            db_manifest.write_text(json.dumps({
                "generation_id": "gen-123",
                "source_fasta": {"sha256": "abc123"},
            }), encoding="utf-8")

            manifest = build_manifest(
                config=resolved(cli={"SEARCH_PROFILES": "C"}), sample="amostra1",
                database_manifest=str(db_manifest),
                short_fragment_fasta=str(fragments),
                short_fragment_blast_tsv=str(short_tsv),
            )

        profile_c = manifest["profiles"]["C"]
        self.assertEqual(manifest["identity"], "search-profile:A+C")
        self.assertTrue(profile_c["active"])
        self.assertEqual(profile_c["search"]["task"], "blastn-short")
        self.assertTrue(profile_c["artifacts"]["blast_tsv"]["present"])
        self.assertTrue(profile_c["artifacts"]["query_fasta"]["present"])
        # Mesmo banco direcionado de A, com a identidade da geração do banco.
        self.assertEqual(profile_c["database"]["blast_db"], manifest["profiles"]["A"]["database"]["blast_db"])
        self.assertEqual(profile_c["database"]["generation_id"], "gen-123")
        self.assertEqual(profile_c["database"]["source_fasta_sha256"], "abc123")

    def test_named_combination_keeps_the_provenance_of_every_profile(self):
        manifest = build_manifest(
            config=resolved(
                cli={"SEARCH_PROFILES": "B,C"},
                incoming={
                    "EVIDENCE_COMPOSITE_DB": "/panel/composite",
                    "EVIDENCE_SUBJECT_LABELS": "/panel/labels.tsv",
                },
            ),
            sample="amostra1",
        )
        self.assertEqual(manifest["identity"], "search-profile:A+B+C")
        self.assertTrue(all(manifest["profiles"][key]["active"] for key in "ABC"))
        self.assertEqual(manifest["profiles"]["B"]["database"]["composite_db"], "/panel/composite")
        self.assertEqual(
            manifest["profiles"]["B"]["database"]["subject_labels"]["path"], "/panel/labels.tsv",
        )
        self.assertEqual(manifest["profiles"]["C"]["search"]["task"], "blastn-short")
        self.assertEqual(manifest["profiles"]["A"]["search"]["task"], "blastn")

    def test_missing_artifacts_are_reported_as_absent_instead_of_failing(self):
        manifest = build_manifest(
            config=resolved(), sample="amostra1",
            database_manifest="/nao/existe.json", contig_blast_tsv="/nao/existe.tsv",
        )
        self.assertFalse(manifest["profiles"]["A"]["artifacts"]["blast_tsv"]["present"])
        self.assertEqual(manifest["profiles"]["A"]["database"]["generation_id"], "")

    def test_cli_writes_the_manifest_next_to_the_blast_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "resolved_config.json"
            subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "pipeline" / "resolve_config.py"),
                    "pipeline", "--repo-root", tmp, "--sample-name", "amostra1",
                    "--analysis-profiles-config", str(ROOT / "config" / "analysis_profiles.json"),
                    "--out", str(config),
                ],
                check=True, capture_output=True, text=True,
            )
            out = root / "results" / "blast" / "amostra1_search_profile.json"
            subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "pipeline" / "search_profile_manifest.py"),
                    "--config", str(config), "--sample", "amostra1", "--out", str(out),
                ],
                check=True, capture_output=True, text=True,
            )
            manifest = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(manifest["identity"], "search-profile:A")
        self.assertEqual(manifest["sample"], "amostra1")


class PipelineWiringTests(unittest.TestCase):
    """The pipeline may only reach B or C through the pre-existing flags."""

    def test_profile_selection_is_resolved_once_by_resolve_config(self):
        self.assertIn('--cli "SEARCH_PROFILES=${SEARCH_PROFILES_OVERRIDE}"', PIPELINE_RUN)
        self.assertIn("SEARCH_PROFILES_OVERRIDE=\"\"", PIPELINE_RUN)
        self.assertIn("--search-profiles)", PIPELINE_RUN)

    def test_short_fragment_stages_stay_gated_on_their_own_flags(self):
        self.assertIn('if [[ "${SHORT_FRAGMENT_MODE:-false}" == "true" && -s "$ASSEMBLY_CONTIGS" ]]; then', PIPELINE_RUN)
        self.assertIn('if [[ "${SHORT_FRAGMENT_BLAST:-false}" == "true" ]]; then', PIPELINE_RUN)

    def test_contig_blast_of_profile_a_is_unchanged(self):
        self.assertIn(
            # -db goes through blast_db_arg() so a spaced BLAST_DB path is not
            # misread by BLAST+ as a whitespace-separated database list.
            'blastn -task "$BLAST_TASK" -query "$ASSEMBLY_CONTIGS" -db "$(blast_db_arg "$BLAST_DB")"', PIPELINE_RUN,
        )
        self.assertIn(
            '-evalue "$BLAST_EVALUE" -word_size "$BLAST_WORD_SIZE" -num_threads "$THREADS"',
            PIPELINE_RUN,
        )

    def test_identity_reaches_the_minimal_report_and_the_evidence_run(self):
        self.assertIn('--search-profile "$SEARCH_PROFILE_MANIFEST"', PIPELINE_RUN)
        self.assertIn(
            'EVIDENCE_ARGS+=(--search-profile-manifest "$SEARCH_PROFILE_MANIFEST")', PIPELINE_RUN,
        )
        self.assertIn("--search-profile-manifest) SEARCH_PROFILE_MANIFEST=", EVIDENCE_RUN)
        self.assertIn(
            '--artifact "search_profile_manifest=$SEARCH_PROFILE_MANIFEST"', EVIDENCE_RUN,
        )

    def test_recovery_queries_reach_evidence_without_legacy_tsv_duplication(self):
        self.assertIn(
            '--queries "$CANDIDATE_QUERIES" --query-manifest "$CANDIDATE_MANIFEST"',
            PIPELINE_RUN,
        )
        self.assertNotIn('EVIDENCE_ARGS+=(--blast "blastn-short=${SF_BLAST_TSV}")', PIPELINE_RUN)

    def test_evidence_v2_is_not_promoted_by_the_search_profiles(self):
        # Nada em torno dos perfis liga Evidence: a única ativação continua
        # sendo --evidence-v2 / EVIDENCE_V2.
        self.assertNotIn("EVIDENCE_V2=true", PIPELINE_RUN)
        self.assertEqual(PIPELINE_RUN.count("EVIDENCE_V2_OVERRIDE=true"), 1)
        # Nenhuma atribuição liga as flags de C; a única menção a
        # "SHORT_FRAGMENT_MODE=true" no script é a dica impressa ao usuário.
        assignments = re.findall(
            r"^\s*(?:export\s+)?SHORT_FRAGMENT_(?:MODE|BLAST)=\S+", PIPELINE_RUN, re.MULTILINE,
        )
        self.assertEqual(assignments, [])

    def test_shipped_configuration_keeps_every_optional_profile_off(self):
        example = (ROOT / "config.env.example").read_text(encoding="utf-8")
        self.assertIn("SEARCH_PROFILES=\n", example)
        self.assertIn("SHORT_FRAGMENT_MODE=false", example)
        self.assertIn("SHORT_FRAGMENT_BLAST=false", example)


class MinimalReportTests(unittest.TestCase):
    @staticmethod
    def git_bash() -> Path | None:
        if os.name != "nt":
            bash = shutil.which("bash")
            return Path(bash) if bash else None
        candidates = [
            Path(r"C:\Program Files\Git\bin\bash.exe"),
            Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
        ]
        return next((path for path in candidates if path.is_file()), None)

    @staticmethod
    def posix(path: Path) -> str:
        resolved_path = path.resolve()
        if os.name != "nt":
            return resolved_path.as_posix()
        drive = resolved_path.drive.rstrip(":").lower()
        return f"/{drive}/{resolved_path.as_posix().split(':', 1)[1].lstrip('/')}"

    def run_report(self, root: Path, *extra: str) -> str:
        contigs = root / "contigs.fa"
        blast = root / "blast.tsv"
        report = root / "results/reports/sample_summary.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        (root / "results/blast").mkdir(parents=True, exist_ok=True)
        contigs.write_text(">contig-1\n" + "A" * 100 + "\n", encoding="utf-8")
        blast.write_text(
            "contig-1\tref-1\t99\t50\t0\t0\t1\t50\t1\t50\t1e-20\t100\t100\t100\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment["EVIDENCE_RUN_ID"] = "dashboard-run-00000001"
        result = subprocess.run([
            str(self.git_bash()), "-c",
            'export PATH="/usr/bin:/bin:$PATH"; mkdir() { :; }; export -f mkdir; exec "$@"', "bash",
            "scripts/pipeline/report_minimal.sh", "--sample", "sample",
            "--contigs", self.posix(contigs), "--blast", self.posix(blast),
            "--out", self.posix(report), *extra,
        ], cwd=ROOT, env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return report.read_text(encoding="utf-8")

    @unittest.skipUnless(git_bash.__func__(), "Bash is required for report_minimal.sh")
    def test_minimal_report_declares_the_search_profile(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "scripts/tests") as tmp:
            root = Path(tmp)
            manifest = root / "search_profile.json"
            manifest.write_text(json.dumps(build_manifest(
                config=resolved(cli={"SEARCH_PROFILES": "C"}), sample="sample",
            )), encoding="utf-8")
            text = self.run_report(root, "--search-profile", self.posix(manifest))
        self.assertIn("## Perfil de busca", text)
        self.assertIn("search-profile:A+C", text)
        self.assertIn("| C —", text)

    @unittest.skipUnless(git_bash.__func__(), "Bash is required for report_minimal.sh")
    def test_minimal_report_without_a_manifest_is_unchanged(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "scripts/tests") as tmp:
            text = self.run_report(Path(tmp))
        self.assertNotIn("## Perfil de busca", text)
        self.assertIn("## Assembly", text)


if __name__ == "__main__":
    unittest.main()
