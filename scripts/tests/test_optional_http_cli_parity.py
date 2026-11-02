"""Real HTTP and public CLI configuration boundaries; stop before processing."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import threading
import traceback
import unittest
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "scripts/pipeline")]
from dashboard import handler, jobs
from search_profile_manifest import build_manifest
from scripts.tests import test_optional_evidence_dashboard as fixtures


class OptionalHttpCliParityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.OptionalEvidenceTests("test_each_combination_reaches_the_canonical_resolver")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root / "CLI source with spaces"
        pipeline = self.root / "scripts/pipeline"
        pipeline.mkdir(parents=True)
        (self.root / "scripts/lib").symlink_to(ROOT / "scripts/lib", target_is_directory=True)
        (self.root / "config").symlink_to(ROOT / "config", target_is_directory=True)
        for name in ("run.sh", "run_sample.sh", "prepare_run.sh"):
            shutil.copy2(ROOT / "scripts/pipeline" / name, pipeline / name)
        for name in ("resolve_config.py", "analysis_profiles.py"):
            (pipeline / name).symlink_to(ROOT / "scripts/pipeline" / name)
        steps = (ROOT / "scripts/pipeline/sample_steps.sh").read_text()
        (pipeline / "sample_steps.sh").write_text(steps[:steps.index("# Preflight de IDs")] + '\ncat "$RESOLVED_CONFIG_JSON"\n')
        self.work = self.root / "results/dashboard-work/parity-run-0001"
        self.work.mkdir(parents=True)
        self.settings = {
            "EVIDENCE_COMPOSITE_DB": str(self.fixture.prefix), "EVIDENCE_SUBJECT_LABELS": str(self.fixture.labels),
            "EVIDENCE_PANEL_FASTA": str(self.fixture.reference), "EVIDENCE_PANEL_INDEX": str(self.fixture.index),
            "EVIDENCE_LIBRARY_MODE": "unknown", "EVIDENCE_COMPETITION_ENABLED": "true", "EVIDENCE_REMAPPING_ENABLED": "true",
        }
        self.write_config()
        for owner, name, value in ((jobs, "REPO_ROOT", self.root), (handler, "REPO_ROOT", self.root)):
            mocked = patch.object(owner, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        mocked = patch.object(jobs, "get_repo_root", return_value=self.root)
        mocked.start()
        self.addCleanup(mocked.stop)
        case = self

        class InspectionHandler(handler.DashboardHandler):
            def start_job(self, action, params):
                try:
                    command, overrides = jobs.build_command(action, params)
                    resolved = case.boundary(command, overrides)
                    return handler.json_response(self, HTTPStatus.OK, {"resolved": resolved, "provenance": build_manifest(config=resolved, sample="fixture")})
                except Exception:
                    return handler.json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"test_boundary_error": traceback.format_exc()})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), InspectionHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def write_config(self):
        self.fixture.config.write_text("\n".join(key + "=" + shlex.quote(value) for key, value in self.settings.items()) + "\n")

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def boundary(self, command, overrides):
        env = {**os.environ, **overrides, "ANALYSIS_PROFILES_CONFIG": str(ROOT / "config/analysis_profiles.json")}
        args = ["bash", str(self.root / command[1]), *command[2:]] if command[0] == "bash" else ["bash", str(self.root / command[0]), *command[1:]]
        result = subprocess.run(args, cwd=self.root, env=env, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_three_states_for_each_option_have_identical_http_cli_config_and_provenance(self):
        for option, variable in (("competition_enabled", "EVIDENCE_COMPETITION_ENABLED"), ("remapping_enabled", "EVIDENCE_REMAPPING_ENABLED")):
            for selected in (None, True, False):
                with self.subTest(option=option, selected=selected):
                    params = {"sample": "fixture", "db": "fixture-bank", "run_id": "parity-run-0001", option: selected}
                    if selected is True:
                        keys = ("competition_db", "competition_labels") if option == "competition_enabled" else ("remapping_reference", "remapping_index", "library_mode")
                        params.update({key: self.fixture.params[key] for key in keys})
                    request = urllib.request.Request(f"http://127.0.0.1:{self.server.server_port}/api/run", data=json.dumps({"action": "evidence_pipeline", "params": params}).encode(), headers={"Content-Type": "application/json"})
                    try:
                        response = urllib.request.urlopen(request, timeout=30)
                    except urllib.error.HTTPError as error:
                        self.fail(error.read().decode())
                    with response:
                        received = json.load(response)
                    incoming = {"DB": "fixture-bank", "HOST_FILTER_ENABLED": "false", "EVIDENCE_RUN_ID": "parity-run-0001", "GENEIN_WORK_ROOT": str(self.work)}
                    if selected is not None:
                        incoming[variable] = str(selected).lower()
                    command = ["bash", "scripts/pipeline/run.sh", "--sample", "fixture", "--analysis-profile", "default", "--assembler", "spades", "--evidence-v2", "--evidence-profiles", "config/evidence_profiles.json", "--r1", str(self.root / "data/raw/fixture_R1.fastq.gz"), "--r2", str(self.root / "data/raw/fixture_R2.fastq.gz")]
                    resolved = self.boundary(command, incoming)
                    self.assertEqual(received["resolved"], resolved)
                    self.assertEqual(received["provenance"], build_manifest(config=resolved, sample="fixture"))
                    field = "composite_db" if option == "competition_enabled" else "panel_index"
                    self.assertEqual(bool(resolved["evidence"][field]), selected is not False)

    def test_http_defaults_show_config_and_environment_precedence_without_overrides(self):
        url = f"http://127.0.0.1:{self.server.server_port}/api/evidence/options"
        with urllib.request.urlopen(url) as response:
            effective = json.load(response)["effective"]
        self.assertTrue(effective["competition_enabled"])
        self.assertTrue(effective["remapping_enabled"])
        with patch.dict(os.environ, {"EVIDENCE_COMPETITION_ENABLED": "false"}):
            with urllib.request.urlopen(url) as response:
                effective = json.load(response)["effective"]
            self.assertFalse(effective["competition_enabled"])
            self.assertTrue(effective["remapping_enabled"])


if __name__ == "__main__":
    unittest.main()
