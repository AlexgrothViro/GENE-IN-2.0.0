"""Auto-teste de contratos sobre amostras sintéticas.

O que isto é: um verificador de contratos. Ele constrói amostras com
``evaluate_contract_sample`` e confere as métricas resultantes contra os
critérios de aceitação fornecidos, produzindo PASS/FAIL por critério.

O que isto NÃO é: validação científica independente. As amostras avaliadas
são construídas a partir da categoria esperada, portanto o resultado não
estima recuperação, especificidade nem generalização em dados reais. Ver
``controle/VALIDACAO_CIENTIFICA.md`` e a decisão D010.

Renomeado de ``validation.py`` em 2026-09-08 para separar teste de contrato
de validação científica. Os identificadores ``schema_version`` foram
mantidos porque o formato do relatório não mudou.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .experimental_policy import materialize_experimental_policy
from .optimization import baseline_parameters, git_head
from .optimization_contract import evaluate_contract_sample
from .parameter_set import write_json_atomic
from .results import write_results_csv, write_results_json


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def evaluate_criteria(results: list[dict[str, Any]], criteria: dict[str, Any]) -> dict[str, Any]:
    total = len(results) or 1
    recovered = sum(1 for row in results if row.get("recovered"))
    short = [row for row in results if row.get("expected_length_bp") is not None and 20 <= int(row["expected_length_bp"]) <= 49]
    short_recovered = sum(1 for row in short if row.get("recovered"))
    false_positives = sum(1 for row in results if row.get("false_positive"))
    false_negatives = sum(1 for row in results if row.get("false_negative"))

    metrics = {
        "recovery_total_pct": round(100.0 * recovered / total, 2),
        "recovery_20_49_pct": round(100.0 * short_recovered / len(short), 2) if short else 0.0,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }
    checks: list[dict[str, Any]] = []
    for name, rule in (criteria.get("acceptance_criteria") or {}).items():
        observed = metrics.get(name)
        minimum = rule.get("minimum")
        maximum = rule.get("maximum")
        passed = True
        if minimum is not None and observed is not None and observed < minimum:
            passed = False
        if maximum is not None and observed is not None and observed > maximum:
            passed = False
        checks.append({"criterion": name, "observed": observed, "rule": rule, "status": "PASS" if passed else "FAIL"})

    if not checks:
        conclusion = "REVIEW_REQUIRED"
    elif all(item["status"] == "PASS" for item in checks):
        conclusion = "CRITERIA_MET"
    elif any(item["status"] == "FAIL" for item in checks):
        conclusion = "CRITERIA_NOT_MET"
    else:
        conclusion = "REVIEW_REQUIRED"

    return {
        "schema_version": "validation-validation-report-v1",
        "conclusion": conclusion,
        "metrics": metrics,
        "criteria_checks": checks,
    }


def run_contract_selftest(
    *,
    repo_root: Path,
    parameter_set_path: Path,
    validation_panel_path: Path,
    development_panel_path: Path | None,
    criteria_path: Path,
    out_dir: Path,
    experiment_id: str,
) -> dict[str, Any]:
    parameter_set = load_json(parameter_set_path)
    validation_panel = load_json(validation_panel_path)
    criteria = load_json(criteria_path)
    if not validation_panel.get("samples"):
        raise ValueError("Validation panel is empty.")

    parameters = parameter_set.get("parameters") or {}
    if not parameters:
        raise ValueError("Selected parameter set has no parameters.")

    ps_id = str(parameter_set.get("parameter_set_id") or parameter_set_path.stem)
    commit = git_head(repo_root)
    policy_paths = materialize_experimental_policy(
        parameters=parameters,
        parameter_set_id=ps_id,
        out_dir=out_dir / "policy" / ps_id,
    )
    baseline_map = baseline_parameters(repo_root)
    results = [
        evaluate_contract_sample(
            entry=entry,
            parameters=parameters,
            parameter_set_id=ps_id,
            experiment_id=experiment_id,
            commit=commit,
            policy_paths=policy_paths,
            baseline_parameters_map=baseline_map,
        )
        for entry in validation_panel.get("samples") or []
    ]
    write_results_json(out_dir / "results.json", results)
    write_results_csv(out_dir / "results.csv", results)
    report = evaluate_criteria([item.to_row() for item in results], criteria)
    report.update(
        {
            "experiment_id": experiment_id,
            "track": "contract-selftest",
            "parameter_set_id": ps_id,
            "commit": commit,
            "parameter_set": str(parameter_set_path),
        }
    )
    write_json_atomic(out_dir / "contract_selftest_report.json", report)
    return report
