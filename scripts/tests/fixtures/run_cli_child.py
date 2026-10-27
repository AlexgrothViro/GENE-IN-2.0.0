"""Minimal stand-in for run_sample.sh/run_batch.py used only by tests/test_run_cli.py.

Records the arguments and Gene-In environment variables it received so the CLI
adapter's env/receipt wiring can be asserted without real bioinformatics tools,
then exits with GENEIN_TEST_EXIT (default 0).
"""
import json
import os
import sys
import time
from pathlib import Path

record = {
    "argv": sys.argv[1:],
    "env": {key: value for key, value in os.environ.items()
             if key.startswith(("EVIDENCE_", "SAMPLE_", "HOST_", "GENEIN_", "BLAST_"))},
}
marker = Path(os.environ["GENEIN_TEST_MARKER"])
marker.write_text(json.dumps(record), encoding="utf-8")
log_text = os.environ.get("GENEIN_TEST_LOG")
if log_text:
    log_dir = Path(os.environ["GENEIN_WORK_ROOT"]) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "sample_pipeline.log").write_text(log_text, encoding="utf-8")
if os.environ.get("GENEIN_TEST_SLEEP"):
    time.sleep(float(os.environ["GENEIN_TEST_SLEEP"]))
raise SystemExit(int(os.environ.get("GENEIN_TEST_EXIT", "0")))
