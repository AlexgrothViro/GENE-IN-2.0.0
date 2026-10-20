from __future__ import annotations

import csv
import json
from pathlib import Path

from evidence_dashboard import STATUS_EXPLANATIONS
from evidence_contract import evidence_label


DATASETS = {
    "coverage": "coverage.tsv",
    "read_support": "read_support.tsv",
    "fragment_evidence": "fragment_evidence.tsv",
    "hsp_evidence": "hsp_evidence.tsv",
    "locus_evidence": "locus_evidence.tsv",
    "competitive_hits": "competitive_hits.tsv",
    "template_lineage": "template_lineage.tsv",
}
MAX_DATASET_ROWS = 500


class EvidenceAnalyticsService:
    """Read-only presentation of already validated Evidence V2 artifacts."""

    def __init__(self, evidence_service):
        self.evidence_service = evidence_service
        self._dataset_counts = {}

    def _run(self, run_id: str) -> tuple[str, Path, dict, dict, dict]:
        run_id = self.evidence_service._safe_id(run_id, "run_id")
        state = self.evidence_service.state(run_id)
        inspection = self.evidence_service.inspect_run(run_id)
        run_dir = (self.evidence_service.evidence_root / "runs" / run_id).resolve()
        expected_root = self.evidence_service.evidence_root.resolve() / "runs"
        if run_dir.parent != expected_root or not run_dir.is_dir():
            raise FileNotFoundError("execução Evidence V2 não encontrada")
        success = self._read_json(run_dir / "SUCCESS.json")
        return run_id, run_dir, state, inspection, success

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _read_tsv(path: Path) -> tuple[list[str], list[dict]]:
        with path.open("r", encoding="utf-8", errors="strict", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames or any(not field for field in reader.fieldnames):
                raise ValueError("cabeçalho TSV inválido")
            rows = list(reader)
        return list(reader.fieldnames), rows

    def _dataset_status(self, run_dir: Path, name: str, valid: bool) -> dict:
        path = run_dir / DATASETS[name]
        base = {"dataset": name, "artifact": DATASETS[name]}
        if not path.is_file():
            return {**base, "status": "missing", "rows": None}
        if not valid:
            return {**base, "status": "invalid", "rows": None}
        try:
            stat = path.stat()
            signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            cached = self._dataset_counts.get(path)
            if cached is not None and cached[0] == signature:
                count = cached[1]
            else:
                with path.open("r", encoding="utf-8", errors="strict", newline="") as handle:
                    reader = csv.reader(handle, delimiter="\t")
                    header = next(reader, None)
                    if not header or any(not field for field in header):
                        raise ValueError("cabeçalho TSV inválido")
                    count = sum(1 for row in reader if row)
                self._dataset_counts[path] = (signature, count)
        except (OSError, UnicodeError, ValueError, csv.Error):
            return {**base, "status": "invalid", "rows": None}
        return {**base, "status": "available" if count else "empty", "rows": count}

    def summary(self, run_id: str) -> dict:
        run_id, run_dir, state, inspection, success = self._run(run_id)
        evidence = self._read_json(run_dir / "sample_evidence.json")
        valid = bool(inspection.get("valid_alpha2"))
        datasets = {
            name: self._dataset_status(run_dir, name, valid)
            for name in DATASETS
        }
        if valid:
            coverage_status = str(evidence.get("coverage_status") or "").upper()
            if coverage_status in {"NOT_APPLICABLE", "CONTROL_NOT_APPLICABLE"}:
                datasets["coverage"] = {
                    **datasets["coverage"],
                    "status": "not_applicable",
                    "rows": None,
                }
            elif coverage_status in {"NOT_MEASURED", "COVERAGE_UNAVAILABLE", "NOT_EVALUATED"}:
                datasets["coverage"] = {
                    **datasets["coverage"],
                    "status": "not_measured",
                    "rows": None,
                }
        candidates = []
        caveats = []
        provenance = None
        control_status = None
        reported_conclusion = None
        analysis_outcome = "NOT_EVALUABLE"
        evidence_level = "NOT_EVALUABLE"
        execution_status = state.get("execution_status") or state.get("status")
        if valid:
            reported_conclusion = evidence.get("reported_conclusion")
            control_status = evidence.get("control_status")
            analysis_outcome = evidence.get("analysis_outcome")
            evidence_level = evidence.get("evidence_level")
            execution_status = (
                evidence.get("execution_status")
                or state.get("execution_status")
                or state.get("status")
            )
            caveats = evidence.get("caveats") if isinstance(evidence.get("caveats"), list) else []
            provenance = evidence.get("provenance") if isinstance(evidence.get("provenance"), dict) else {}
            for candidate in evidence.get("candidates") or []:
                if not isinstance(candidate, dict):
                    continue
                candidates.append({
                    "candidate_id": candidate.get("candidate_id"),
                    "reference_id": candidate.get("reference_id"),
                    "locus_id": candidate.get("locus_id"),
                    "candidate_class": candidate.get("candidate_class"),
                    "promotion_status": candidate.get("promotion_status"),
                    "blocking_reasons": candidate.get("blocking_reasons") or [],
                    "availability_status": candidate.get("availability_status", "AVAILABLE_FOR_REVIEW"),
                    "qualification_status": candidate.get("qualification_status", "NOT_EVALUATED"),
                    "specificity_status": candidate.get("specificity_status", "NOT_EVALUATED"),
                    "taxon": candidate.get("taxon", ""),
                    "taxonomic_status": candidate.get("taxonomic_status", "NOT_EVALUATED"),
                    "support": candidate.get("support", {}),
                })
        available = sum(item.get("promotion_status") == "AVAILABLE" for item in candidates)
        # Availability is not a result of a scientific qualification gate.
        eligible = 0
        blocked = 0
        if not candidates:
            promotion_status = "NONE"
        else:
            promotion_status = "AVAILABLE"
        sample_ids = state.get("sample_ids") or []
        return {
            "run_id": run_id,
            "metadata": {
                "sample_id": (evidence.get("sample_id") if valid else None) or (sample_ids[0] if sample_ids else None),
                "created_at": state.get("created_at"),
                "started_at": state.get("started_at"),
                "finished_at": state.get("finished_at"),
                "execution_status": execution_status,
                "analysis_outcome": analysis_outcome,
                "evidence_level": evidence_level,
                "evidence_label": evidence_label({"analysis_outcome": analysis_outcome}),
                "scientific_revision": evidence.get("scientific_revision") if valid else None,
                "promotion_status": promotion_status if valid else None,
                "reported_conclusion": reported_conclusion,
                "shadow_mode": state.get("shadow_mode"),
                "evidence_ceiling": state.get("evidence_ceiling"),
                "schema_version": evidence.get("schema_version") if valid else None,
                "pipeline_version": (success.get("pipeline_version") or state.get("pipeline_version")) if valid else state.get("pipeline_version"),
                "policy_version": (success.get("policy_version") or state.get("policy_version")) if valid else state.get("policy_version"),
                "profile_id": state.get("profile_id"),
                "profile_version": state.get("profile_version"),
            },
            "metrics": evidence.get("metrics") if valid else None,
            "controls": {
                "status": control_status,
                "explanation": STATUS_EXPLANATIONS.get(control_status) if control_status else None,
            },
            "caveats": caveats,
            "provenance": provenance,
            "candidates": candidates,
            "promotion_summary": {
                "total": len(candidates),
                "eligible": eligible,
                "blocked": blocked,
                "status": promotion_status if valid else None,
            },
            "availability_summary": {"total": len(candidates), "available": available,
                                     "qualification_status": "NOT_EVALUATED"},
            "reference_coverage": evidence.get("reference_coverage") if valid else None,
            "gates": evidence.get("promotion_gates") if valid else [],
            "stages": state.get("stages") or [],
            "datasets": datasets,
            "explanations": STATUS_EXPLANATIONS if valid else {},
            "validation": {
                "status": inspection.get("status"),
                "valid": valid,
                "message": inspection.get("message") or "",
                "errors": inspection.get("errors") or [],
            },
        }

    def dataset(
        self,
        run_id: str,
        dataset: str,
        *,
        reference_id: str = "",
        locus_id: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> dict:
        dataset = str(dataset or "").strip()
        if dataset not in DATASETS:
            raise ValueError("dataset analítico inválido")
        try:
            offset = int(offset)
            limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("offset e limit devem ser inteiros") from exc
        if offset < 0 or limit < 1 or limit > MAX_DATASET_ROWS:
            raise ValueError(f"paginação inválida; limit deve estar entre 1 e {MAX_DATASET_ROWS}")

        run_id, run_dir, _, inspection, _ = self._run(run_id)
        if not inspection.get("valid_alpha2"):
            raise ValueError("execução inválida ou incompatível para exploração analítica")
        path = (run_dir / DATASETS[dataset]).resolve()
        if path.parent != run_dir:
            raise ValueError("caminho de artefato inválido")
        if not path.is_file():
            return {
                "run_id": run_id, "dataset": dataset, "status": "missing",
                "total": None, "offset": offset, "limit": limit, "rows": [],
                "truncated": False, "columns": [],
            }
        try:
            columns, rows = self._read_tsv(path)
        except (OSError, UnicodeError, ValueError, csv.Error) as exc:
            return {
                "run_id": run_id, "dataset": dataset, "status": "invalid",
                "total": None, "offset": offset, "limit": limit, "rows": [],
                "truncated": False, "columns": [], "error": str(exc),
            }
        filters = {
            "reference_id": str(reference_id or "").strip(),
            "locus_id": str(locus_id or "").strip(),
        }
        for field, value in filters.items():
            if value:
                rows = [row for row in rows if str(row.get(field, "")) == value]
        total = len(rows)
        page = rows[offset:offset + limit]
        return {
            "run_id": run_id,
            "dataset": dataset,
            "status": "available" if total else "empty",
            "total": total,
            "offset": offset,
            "limit": limit,
            "rows": page,
            "truncated": offset + len(page) < total,
            "columns": columns,
            "filters": filters,
            "artifact": f"/api/evidence/artifact?run={run_id}&type={dataset}",
        }

    def compare(self, run_ids: list[str]) -> dict:
        if not 2 <= len(run_ids) <= 4:
            raise ValueError("a comparação exige de duas a quatro execuções")
        if len(set(run_ids)) != len(run_ids):
            raise ValueError("a comparação exige execuções distintas")
        summaries = [self.summary(run_id) for run_id in run_ids]
        dimensions = ("schema_version", "pipeline_version", "policy_version", "profile_id", "profile_version")
        conflicts = []
        for dimension in dimensions:
            values = [item["metadata"].get(dimension) for item in summaries]
            if len({json.dumps(value, sort_keys=True) for value in values}) > 1:
                conflicts.append({"field": dimension, "values": values})
        valid = all(item["validation"]["valid"] for item in summaries)
        overlay_allowed = valid and not conflicts
        return {
            "runs": summaries,
            "compatibility": {
                "compatible": overlay_allowed,
                "overlay_allowed": overlay_allowed,
                "conflicts": conflicts,
                "reason": "" if overlay_allowed else (
                    "Sobreposição bloqueada: versões ou políticas incompatíveis."
                    if conflicts else "Sobreposição bloqueada: há execução inválida."
                ),
            },
        }
