#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

import finalize_run
import run_state
from activation_policy import POLICY_IDENTITY_FIELDS
from aggregate_hsps import FIELDS as FRAGMENT_FIELDS
from build_hsp_evidence import FIELDS as HSP_FIELDS
from build_loci import FIELDS as LOCUS_FIELDS
from build_template_lineage import FIELDS as LINEAGE_FIELDS
from classify_sample import classify
from common import write_json_atomic, write_text_atomic, write_tsv_atomic
from competitive_hits import FIELDS as COMPETITIVE_FIELDS
from summarize_coverage import FIELDS as COVERAGE_FIELDS
from summarize_read_support import FIELDS as READ_SUPPORT_FIELDS
from validate_run_artifacts import validate


RUN_ID = "fixture-alpha2-run"
SAMPLE_ID = "fixture-alpha2"
FIXTURE_TIMESTAMP = "2026-07-17T00:00:00+00:00"
TABLE_FIELDS = {
    "fragment_evidence.tsv": FRAGMENT_FIELDS,
    "locus_evidence.tsv": LOCUS_FIELDS,
    "competitive_hits.tsv": COMPETITIVE_FIELDS,
    "read_support.tsv": READ_SUPPORT_FIELDS,
    "coverage.tsv": COVERAGE_FIELDS,
    "hsp_evidence.tsv": HSP_FIELDS,
    "template_lineage.tsv": LINEAGE_FIELDS,
}


def _write_staging(staging: Path) -> None:
    for name, fields in TABLE_FIELDS.items():
        write_tsv_atomic(staging / name, [], fields)
    fixture_evidence = classify(
            SAMPLE_ID,
            [],
            [],
            [],
            [],
            "UNCONTROLLED",
            "unknown",
            provenance={"fixture": True},
            run_id=RUN_ID,
            historical_compatibility="historical_alpha2_fixture",
        )
    # This fixture is intentionally frozen as the historical Alpha.2 shadow
    # artifact. New production runs use the active E1 policy and may include
    # optional assembly-consensus observations.
    fixture_evidence.pop("analysis_observations", None)
    fixture_evidence["caveats"][0] = (
        "Evidence 2.0 alpha.2 opera em shadow mode; E2 e E3 permanecem estruturalmente bloqueados."
    )
    fixture_evidence["metrics"].pop("multi_assembler_locus_count", None)
    fixture_evidence["promotion_gates"][-1]["reason"] = (
        "A polÃ­tica alpha.2 mantÃ©m o teto em E1 atÃ© benchmark aprovado."
    )
    fixture_evidence["promotion_gates"][-1]["reason"] = (
        "A pol\u00edtica alpha.2 mant\u00e9m o teto em E1 at\u00e9 benchmark aprovado."
    )
    write_json_atomic(staging / "sample_evidence.json", fixture_evidence)
    write_json_atomic(staging / "runtime_preflight.json", {"fixture": True, "valid": True})
    write_json_atomic(
        staging / "provenance.json",
        {
            "fixture": True,
            "pipeline_version": "2.0.0-alpha.2",
            "run_id": RUN_ID,
            "schema_version": "2.0",
        },
    )
    write_text_atomic(
        staging / "evidence_report.md",
        "# Fixture Evidence V2 Alpha.2\n\n"
        "Artefato sintético em `shadow_mode=true`, sem evidência recuperada e sem "
        "interpretação de ausência viral.\n",
    )


def generate_fixture(output: Path) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="alpha2-fixture-", dir=output.parent) as tmp:
        workspace = Path(tmp)
        staging = workspace / ".staging" / RUN_ID
        final = workspace / "runs" / RUN_ID
        state_path = workspace / "state" / f"{RUN_ID}.json"
        _write_staging(staging)
        with patch.object(run_state, "now", return_value=FIXTURE_TIMESTAMP):
            state = run_state.initial_state(RUN_ID, "evidence_single", [SAMPLE_ID], None)
        # This checked-in fixture represents the historical Alpha.2 shadow contract.
        # Keep its policy identity explicit instead of depending on a mismatch with
        # whichever public activation policy happens to be current.
        state.update({"policy_version": "2.0-alpha", "shadow_mode": True})
        for field in POLICY_IDENTITY_FIELDS:
            if field != "shadow_mode":
                state.pop(field, None)
        write_json_atomic(state_path, state)
        argv = [
            "finalize_run.py",
            "--state",
            str(state_path),
            "--staging",
            str(staging),
            "--final",
            str(final),
            "--historical-alpha2-fixture",
        ]
        with (
            patch.object(finalize_run, "now", return_value=FIXTURE_TIMESTAMP),
            patch.object(sys, "argv", argv),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            finalize_run.main()
        errors = validate(final, compatibility_mode="historical_alpha2_fixture")
        if errors:
            raise ValueError("generated Alpha.2 fixture is invalid: " + "; ".join(errors))

        generated = {path.name for path in final.iterdir() if path.is_file()}
        existing = {path.name for path in output.iterdir() if path.is_file()} if output.exists() else set()
        unexpected = existing - generated
        if unexpected:
            raise ValueError("refusing to remove unexpected fixture files: " + ", ".join(sorted(unexpected)))
        output.mkdir(parents=True, exist_ok=True)
        for source in sorted(final.iterdir()):
            if source.is_file():
                os.replace(source, output / source.name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate the canonical deterministic Alpha.2 fixture")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "fixtures" / "alpha2_complete",
    )
    args = parser.parse_args()
    generate_fixture(args.output)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
