"""Structured experiment result records for Validation."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


RESULT_FIELDS = (
    "run_id",
    "experiment_id",
    "parameter_set_id",
    "commit",
    "configuration",
    "sample_id",
    "ground_truth",
    "sample_role",
    "expected_length_bp",
    "recovered_length_bp",
    "identity_pct",
    "coverage_pct",
    "bitscore",
    "evalue",
    "evidence_found",
    "recovered",
    "observed_classification",
    "expected_classification",
    "concordant",
    "false_positive",
    "false_negative",
    "competition_outcome",
    "runtime_seconds",
    "technical_failure",
    "failure_reason",
    "status",
)


@dataclass
class ExperimentResult:
    run_id: str
    experiment_id: str
    parameter_set_id: str
    commit: str
    configuration: dict[str, Any]
    sample_id: str
    ground_truth: str | None = None
    sample_role: str = "unknown"
    expected_length_bp: int | None = None
    recovered_length_bp: int | None = None
    identity_pct: float | None = None
    coverage_pct: float | None = None
    bitscore: float | None = None
    evalue: float | None = None
    evidence_found: bool = False
    recovered: bool = False
    observed_classification: str | None = None
    expected_classification: str | None = None
    concordant: bool | None = None
    false_positive: bool = False
    false_negative: bool = False
    competition_outcome: str | None = None
    runtime_seconds: float | None = None
    technical_failure: bool = False
    failure_reason: str | None = None
    status: str = "NOT_EXECUTED"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        row = {key: getattr(self, key) for key in RESULT_FIELDS}
        row["configuration"] = json.dumps(self.configuration, sort_keys=True, ensure_ascii=False)
        return row


def write_results_json(path: Path, results: list[ExperimentResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(item) for item in results]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_results_csv(path: Path, results: list[ExperimentResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for item in results:
            writer.writerow(item.to_row())
