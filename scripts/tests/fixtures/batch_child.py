"""Scientific-tool double; real Evidence validation/finalization, synthetic inputs only."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

source = Path(os.environ["GENEIN_TEST_SOURCE"])
repo = Path(os.environ["GENEIN_TEST_REPO"])
sys.path.insert(0, str(source / "scripts/tests/evidence"))
from test_transactional_dashboard import TransactionTests
from classify_sample import classify
from common import write_json_atomic
from run_state import initial_state

parser = argparse.ArgumentParser()
parser.add_argument("--sample")
parser.add_argument("--r1")
parser.add_argument("--r2")
parser.add_argument("--threads")
parser.add_argument("--evidence-v2", action="store_true")
parser.add_argument("--evidence-profiles")
parser.add_argument("--evidence-root", type=Path)
args, _unrecognized_sample_arg_passthrough = parser.parse_known_args()
run_id = os.environ["EVIDENCE_RUN_ID"]
state_path = args.evidence_root / "state" / f"{run_id}.json"
state = initial_state(run_id, "evidence_single", [args.sample], os.environ["EVIDENCE_BATCH_ID"])
state["status"] = "running"
write_json_atomic(state_path, state)
record = {"args": vars(args) | {"evidence_root": str(args.evidence_root)},
          "env": {key: value for key, value in os.environ.items()
                  if key.startswith(("EVIDENCE_", "SAMPLE_", "HOST_")) or key in {"DB", "SEARCH_PROFILES"}}}
write_json_atomic(repo / f"{args.sample}.invocation.json", record)

if os.environ.get("GENEIN_TEST_FAIL") == args.sample:
    state["status"] = "failed"
    write_json_atomic(state_path, state)
    raise SystemExit(23)
if os.environ.get("GENEIN_TEST_WAIT") == args.sample:
    def cancel(_sig, _frame):
        state["status"] = "cancelled"
        write_json_atomic(state_path, state)
        raise SystemExit(130)

    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    child = subprocess.Popen([sys.executable, "-c",
                              "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)"])
    # Child has time to install its deliberately hostile handler before readiness.
    time.sleep(0.15)
    write_json_atomic(repo / "ready.json", {"child": os.getpid(), "grandchild": child.pid})
    while True:
        time.sleep(0.1)

fixture = TransactionTests()
staging = fixture.make_staging(repo / f"fixture-{args.sample}")
destination = args.evidence_root / ".staging" / run_id
staging.replace(destination)
provenance = json.loads((destination / "provenance.json").read_text())
write_json_atomic(destination / "sample_evidence.json", classify(
    args.sample, [], [], [], [], "UNCONTROLLED", os.environ["EVIDENCE_LIBRARY_MODE"],
    provenance=provenance, run_id=run_id,
))
if os.environ.get("GENEIN_TEST_INCOMPLETE") != args.sample:
    subprocess.run([sys.executable, source / "scripts/evidence/finalize_run.py",
                    "--state", state_path, "--staging", destination,
                    "--final", args.evidence_root / "runs" / run_id], check=True)
else:
    destination.replace(args.evidence_root / "runs" / run_id)
write_json_atomic(repo / "results/qc" / f"{args.sample}_fastp.json",
                  {"summary": {"after_filtering": {"total_reads": 2}}})
