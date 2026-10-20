from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from input_validation import validate_batch_id, validate_fastq, validate_run_id, validate_sample_id
from common import fsync_directory, replace_atomic
from activation_policy import load_activation_policy
from evidence_profile import canonical_sha256, validate_profile
from evidence_contract import PIPELINE_VERSION, promote_for_public_output
from validate_run_artifacts import validate


ROLES = {"sample", "negative_extraction", "negative_library", "negative_sequencing", "positive"}
LIBRARY_MODES = {"shotgun", "amplicon", "targeted", "unknown"}
UMI_MODES = {"none", "read_name", "tag"}
MANIFEST_FIELDS = ["batch_id", "sample_id", "role", "library_mode", "umi_mode", "r1", "r2", "expected_target"]
ARTIFACTS = {
    "candidate_sequences": "candidate_sequences.tsv",
    "candidate_fasta": "candidate_sequences.fa",
    "candidate_queries": "candidate_queries.json",
    "fragment_evidence": "fragment_evidence.tsv",
    "hsp_evidence": "hsp_evidence.tsv",
    "locus_evidence": "locus_evidence.tsv",
    "competitive_hits": "competitive_hits.tsv",
    "read_support": "read_support.tsv",
    "coverage": "coverage.tsv",
    "template_lineage": "template_lineage.tsv",
    "sample_evidence": "sample_evidence.json",
    "provenance": "provenance.json",
    "read_support_bam": "read_support.bam",
    "read_support_bai": "read_support.bam.bai",
    "report": "evidence_report.md",
    "state": "run_state.json",
    "success": "SUCCESS.json",
    "batch_evidence": "batch_evidence.json",
    "control_status": "control_status.tsv",
    "batch_report": "batch_report.md",
}
STATUS_EXPLANATIONS = {
    "UNCONTROLLED": "A análise não possui controles associados.",
    "CONTROL_NOT_DETECTED": "O sinal avaliado não foi observado nos controles associados.",
    "CONTROL_BELOW_SAMPLE": "O controle apresentou sinal inferior ao da amostra.",
    "CONTROL_ASSOCIATED_SIGNAL": "Também existe sinal relacionado no controle; isso não confirma contaminação nem descarta o sinal da amostra, apenas registra que ambos foram observados.",
    "CONTROL_EQUAL_OR_HIGHER": "O controle apresentou suporte igual ou superior ao da amostra.",
    "CONTROL_NOT_APPLICABLE": "Esta linha representa um controle; a comparação amostra/controle não se aplica a ela.",
    "TARGET_CONTROL_FAILURE": "O controle positivo do alvo não atingiu o valor configurado.",
    "BATCH_GLOBAL_FAILURE": "Múltiplos controles positivos não atingiram os valores configurados.",
    "TARGET_SPECIFIC": "O alinhamento desta referência alvo superou os competidores não alvo reportados no painel; isso não confirma espécie.",
    "PANEL_TAXON_PREFERRED": "O taxon da referência foi preferido entre os hits reportados no painel; isso não confirma a espécie na amostra.",
    "AMBIGUOUS": "O alvo não foi separado de forma suficiente dos competidores.",
    "NON_TARGET_BEST": "Um competidor não alvo apresentou o melhor alinhamento.",
    "NOT_EVALUATED": "A especificidade competitiva não pôde ser avaliada.",
    "EXPLORATORY_FRAGMENT": "Fragmento curto recuperado pela análise.",
    "LOCUS_CANDIDATE": "Existe um locus candidato alinhado; suporte por reads e especificidade precisam ser conferidos separadamente.",
    "MULTI_LOCUS_CANDIDATE": "Existem loci candidatos independentes segundo os parâmetros configurados.",
    "GENOME_SUPPORTED": "A cobertura atende aos parâmetros configurados.",
    "INCONCLUSIVE": "Os parâmetros configurados não produziram uma classificação conclusiva.",
}
LEGACY_REEXECUTION_MESSAGE = (
    "Esta execu\u00e7\u00e3o foi gerada antes do contrato Evidence V2 Alpha.2 e seus artefatos "
    "s\u00e3o incompat\u00edveis. O resultado \u00e9 NOT_EVALUABLE; reexecute a an\u00e1lise para gerar "
    "artefatos Alpha.2 completos. Os arquivos originais permanecem preservados para auditoria."
)
INVALID_ALPHA2_MESSAGE = (
    "A execu\u00e7\u00e3o n\u00e3o passou na valida\u00e7\u00e3o integral do contrato Evidence V2 Alpha.2. "
    "O resultado é NOT_EVALUABLE. Confira os erros e use Revalidar arquivos após resolver a interferência. "
    "Reexecute somente se os artefatos estiverem incompletos ou alterados; os originais foram preservados para auditoria."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        replace_atomic(tmp_name, path)
        fsync_directory(path.parent)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


class EvidenceDashboardService:
    def __init__(self, repo_root: Path, *, background_inspection: bool = False):
        self.root = repo_root.resolve()
        self.config_path = self.root / "config" / "evidence_profiles.json"
        self.activation_path = self.root / "config" / "evidence_activation.json"
        self.manifest_dir = self.root / "data" / "manifests"
        self.evidence_root = self.root / "results" / "evidence"
        self._inspection_pool = ThreadPoolExecutor(max_workers=1) if background_inspection else None
        self._inspection_lock = threading.Lock()
        self._inspections = {}

    def _safe_id(self, value: str, label: str = "id") -> str:
        value = (value or "").strip()
        if label == "run_id":
            return validate_run_id(value)
        if not value or len(value) > 128 or not value.isascii() or not all(ch.isalnum() or ch in "._-" for ch in value):
            raise ValueError(f"{label} inválido")
        return value

    def _inside_root_file(self, value: str) -> Path:
        path = Path(value)
        path = path if path.is_absolute() else self.root / path
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("arquivos do manifesto devem estar dentro do projeto") from exc
        if not resolved.is_file():
            raise ValueError(f"arquivo inexistente: {resolved}")
        return resolved

    def config(self) -> dict:
        try:
            policy = load_activation_policy(self.activation_path)
        except Exception as exc:
            raise ValueError(f"configuração Evidence V2 inválida: {exc}") from exc
        return {
            "config": policy["thresholds"],
            "schema_version": "1.0",
            "pipeline_version": "2.0.0-alpha.2",
            "shadow_mode": policy["shadow_mode"],
            "profile_id": policy["profile_id"],
            "profile_version": policy["profile_version"],
            "profile_sha256": policy["profile_sha256"],
            "activation_record_id": policy["activation_record_id"],
            "evidence_ceiling": policy["evidence_ceiling"],
            "reported_conclusion": policy["presentation"]["reported_conclusion"],
            "source": str(self.config_path.relative_to(self.root)),
        }

    def dependencies(self) -> dict:
        try:
            policy = load_activation_policy(self.activation_path)
            report, errors = {
                "valid": True,
                "profile_id": policy["profile_id"],
                "profile_version": policy["profile_version"],
            }, []
        except Exception as exc:
            report, errors = {"valid": False, "python": {"executable": "unknown"}}, [str(exc)]
        report["valid"] = not errors
        report["errors"] = errors
        return report

    def validate_config_text(self, content: str) -> dict:
        if not isinstance(content, str) or not content.strip() or len(content.encode("utf-8")) > 1024 * 1024:
            raise ValueError("conteúdo JSON ausente ou muito grande")
        try:
            catalog = json.loads(content)
            if not isinstance(catalog, dict) or set(catalog) != {"schema_version", "profiles"}:
                raise ValueError("catálogo de perfis inválido")
            if catalog["schema_version"] != "1.0" or not isinstance(catalog["profiles"], dict):
                raise ValueError("catálogo requer schema_version 1.0")
            policy = load_activation_policy(self.activation_path)
            profile = validate_profile(
                catalog["profiles"].get(policy["profile_id"]),
                catalog_id=policy["profile_id"],
            )
            if canonical_sha256(profile) != policy["profile_sha256"]:
                raise ValueError("perfil não corresponde ao registro de ativação")
        except Exception as exc:
            raise ValueError(f"configuração Evidence V2 inválida: {exc}") from exc
        return {
            "valid": True, "config": profile["thresholds"], "shadow_mode": policy["shadow_mode"],
            "profile_version": policy["profile_version"],
            "evidence_ceiling": policy["evidence_ceiling"],
        }

    def validate_manifest(self, rows: list[dict], validate_files: bool = True) -> dict:
        if not isinstance(rows, list) or not rows:
            raise ValueError("o lote precisa conter pelo menos uma amostra")
        normalized = []
        errors = []
        warnings = []
        ids = set()
        paths = set()
        has_sample = False
        has_control = False
        batch_ids = set()
        for index, raw in enumerate(rows, 1):
            row_errors = []
            row = {field: str((raw or {}).get(field, "")).strip() for field in MANIFEST_FIELDS}
            try:
                row["sample_id"] = validate_sample_id(row["sample_id"])
            except ValueError as exc:
                row_errors.append(str(exc))
            if not row["batch_id"]:
                row_errors.append("batch_id obrigatório")
            else:
                try:
                    row["batch_id"] = validate_batch_id(row["batch_id"])
                    batch_ids.add(row["batch_id"])
                except ValueError as exc:
                    row_errors.append(str(exc))
            if row["role"] not in ROLES: row_errors.append("role inválido")
            if row["library_mode"] not in LIBRARY_MODES: row_errors.append("library_mode inválido")
            if row["umi_mode"] not in UMI_MODES: row_errors.append("umi_mode inválido")
            if row["umi_mode"] != "none" and row["library_mode"] == "unknown":
                row_errors.append("UMI exige library_mode conhecido")
            if row["role"] == "positive" and not row["expected_target"]:
                row_errors.append("controle positivo exige expected_target")
            has_sample = has_sample or row["role"] == "sample"
            has_control = has_control or row["role"] != "sample"
            if row["sample_id"] in ids: row_errors.append("sample_id duplicado")
            ids.add(row["sample_id"])
            try:
                r1 = self._inside_root_file(row["r1"])
                r2 = self._inside_root_file(row["r2"])
                for path in (r1, r2):
                    key = str(path).lower()
                    if key in paths: row_errors.append("arquivo reutilizado em outra amostra")
                    paths.add(key)
                row["r1"] = str(r1.relative_to(self.root))
                row["r2"] = str(r2.relative_to(self.root))
                if validate_files and not row_errors:
                    validate_fastq(r1, r2)
            except (OSError, ValueError) as exc:
                row_errors.append(str(exc))
            if row_errors:
                errors.append({"row": index, "sample_id": row["sample_id"], "errors": row_errors})
            normalized.append(row)
        if len(batch_ids) > 1:
            errors.append({"row": 0, "sample_id": "", "errors": ["um manifesto deve conter somente um batch_id"]})
        if not has_sample:
            errors.append({"row": 0, "sample_id": "", "errors": ["lote sem amostra analítica"]})
        if not has_control:
            warnings.append("Lote sem controles; resultados serão marcados como UNCONTROLLED.")
        return {"valid": not errors, "rows": normalized, "errors": errors, "warnings": warnings}

    def _manifest_tsv(self, rows: list[dict]) -> str:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, delimiter="\t", fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in MANIFEST_FIELDS} for row in rows)
        return output.getvalue()

    def save_manifest(self, rows: list[dict], manifest_id: str | None = None) -> dict:
        result = self.validate_manifest(rows, validate_files=True)
        if not result["valid"]:
            return result
        manifest_id = self._safe_id(manifest_id or uuid.uuid4().hex, "manifest_id")
        tsv_path = self.manifest_dir / f"{manifest_id}.tsv"
        json_path = self.manifest_dir / f"{manifest_id}.json"
        if tsv_path.exists() or json_path.exists():
            raise FileExistsError("manifest_id já existe")
        tsv = self._manifest_tsv(result["rows"])
        metadata = {
            "manifest_id": manifest_id,
            "schema_version": "2.0-alpha",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "sha256": hashlib.sha256(tsv.encode("utf-8")).hexdigest(),
            "row_count": len(result["rows"]),
            "batch_id": result["rows"][0]["batch_id"],
            "validation_status": "VALID",
            "warnings": result["warnings"],
        }
        atomic_text(tsv_path, tsv)
        try:
            atomic_json(json_path, metadata)
        except Exception:
            tsv_path.unlink(missing_ok=True)
            raise
        return {**result, "manifest_id": manifest_id, "metadata": metadata}

    def import_manifest(self, content: str) -> dict:
        if not isinstance(content, str) or len(content.encode("utf-8")) > 5 * 1024 * 1024:
            raise ValueError("manifesto ausente ou muito grande")
        reader = csv.DictReader(io.StringIO(content), delimiter="\t")
        if reader.fieldnames != MANIFEST_FIELDS:
            raise ValueError("cabeçalho do manifesto incompatível")
        return self.save_manifest(list(reader))

    def list_manifests(self) -> list[dict]:
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        result = []
        for path in sorted(self.manifest_dir.glob("*.json"), reverse=True):
            try:
                result.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return result

    def manifest(self, manifest_id: str) -> dict:
        manifest_id = self._safe_id(manifest_id, "manifest_id")
        tsv_path = self.manifest_dir / f"{manifest_id}.tsv"
        metadata_path = self.manifest_dir / f"{manifest_id}.json"
        if not tsv_path.is_file() or not metadata_path.is_file():
            raise FileNotFoundError("manifesto não encontrado")
        with tsv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        return {"manifest_id": manifest_id, "rows": rows, "metadata": json.loads(metadata_path.read_text(encoding="utf-8"))}

    def manifest_export(self, manifest_id: str) -> Path:
        manifest_id = self._safe_id(manifest_id, "manifest_id")
        path = self.manifest_dir / f"{manifest_id}.tsv"
        if not path.is_file():
            raise FileNotFoundError("manifesto não encontrado")
        return path

    def _raw_state(self, run_id: str) -> dict:
        run_id = self._safe_id(run_id, "run_id")
        path = self.evidence_root / "state" / f"{run_id}.json"
        if not path.is_file():
            raise FileNotFoundError("execução Evidence V2 não encontrada")
        return json.loads(path.read_text(encoding="utf-8"))

    def refresh_inspection(self, run_id: str) -> None:
        run_id = self._safe_id(run_id, "run_id")
        with self._inspection_lock:
            previous = self._inspections.get(run_id)
            if previous is not None and previous[1].done():
                self._inspections.pop(run_id, None)

    def inspect_run(self, run_id: str) -> dict:
        if self._inspection_pool is None:
            return self._inspect_run_uncached(run_id)
        run_id = self._safe_id(run_id, "run_id")
        run_dir = self.evidence_root / "runs" / run_id
        if not (run_dir / "SUCCESS.json").is_file():
            return self._inspect_run_uncached(run_id)
        paths = [self.evidence_root / "state" / f"{run_id}.json",
                 self.config_path, self.activation_path]
        paths.extend(sorted(path for path in run_dir.rglob("*") if path.is_file()))
        signature = []
        for path in paths:
            try:
                stat = path.stat()
                signature.append((str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
            except OSError:
                signature.append((str(path), None))
        signature = tuple(signature)
        with self._inspection_lock:
            previous = self._inspections.get(run_id)
            if previous is None or previous[0] != signature:
                # A single worker prevents simultaneous requests from repeatedly
                # reading multi-gigabyte artifacts and starving HTTP handlers.
                if previous is not None and not previous[1].done():
                    future = previous[1]
                else:
                    future = self._inspection_pool.submit(self._inspect_run_uncached, run_id)
                    self._inspections[run_id] = (signature, future)
            else:
                future = previous[1]
            if future.done() and self._inspections[run_id][0] == signature:
                return dict(future.result())
        return {
            "status": "VALIDATION_PENDING", "valid_alpha2": False, "complete": True,
            "analysis_outcome": "NOT_EVALUABLE", "errors": [],
            "message": "Validando os arquivos em segundo plano. Atualize esta página em instantes.",
        }

    def _inspect_run_uncached(self, run_id: str) -> dict:
        run_id = self._safe_id(run_id, "run_id")
        state = self._raw_state(run_id)
        run_dir = self.evidence_root / "runs" / run_id
        if not (run_dir / "SUCCESS.json").is_file():
            return {
                "status": "INCOMPLETE", "valid_alpha2": False, "complete": False,
                "analysis_outcome": "NOT_EVALUABLE",
                "evidence_level": "NOT_EVALUABLE",
                "message": "A execu\u00e7\u00e3o ainda n\u00e3o possui um commit SUCCESS.json completo.",
                "errors": [],
            }
        if state.get("pipeline_version") != PIPELINE_VERSION:
            return {
                "status": "LEGACY_INCOMPATIBLE", "valid_alpha2": False, "complete": True,
                "analysis_outcome": "NOT_EVALUABLE", "message": LEGACY_REEXECUTION_MESSAGE,
                "errors": [f"pipeline_version={state.get('pipeline_version')!r}"],
            }
        errors: list[str] = []
        if not isinstance(state.get("shadow_mode"), bool):
            errors.append("run state shadow_mode must be boolean")
        if state.get("profile_id"):
            try:
                policy = load_activation_policy(self.root / "config" / "evidence_activation.json")
                for field in (
                    "profile_id", "profile_version", "profile_sha256",
                    "activation_record_id", "activation_record_sha256",
                    "scientific_role", "shadow_mode", "evidence_ceiling",
                ):
                    if state.get(field) != policy[field]:
                        errors.append(f"run state {field} does not match active policy")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"active analysis configuration is invalid: {exc}")
        if state.get("action") == "evidence_batch":
            errors.extend(validate(run_dir))
            batch_path = run_dir / "batch_evidence.json"
            try:
                batch = json.loads(batch_path.read_text(encoding="utf-8", errors="strict"))
                promote_for_public_output(batch)
                if batch.get("run_id") != run_id:
                    errors.append("batch evidence run_id does not match the requested run")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"invalid batch_evidence.json: {exc}")
        else:
            errors.extend(validate(run_dir))
            try:
                evidence = json.loads((run_dir / "sample_evidence.json").read_text(encoding="utf-8", errors="strict"))
                if evidence.get("run_id") != run_id:
                    errors.append("sample evidence run_id does not match the requested run")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"invalid sample_evidence.json: {exc}")
        if errors:
            return {
                "status": "EVIDENCE_INVALID", "valid_alpha2": False, "complete": True,
                "analysis_outcome": "NOT_EVALUABLE", "message": INVALID_ALPHA2_MESSAGE,
                "errors": errors,
            }
        return {
            "status": "EVIDENCE_VALID", "valid_alpha2": True, "complete": True,
            "analysis_outcome": state.get("analysis_outcome"), "message": "", "errors": [],
        }

    def state(self, run_id: str) -> dict:
        state = self._raw_state(run_id)
        inspection = self.inspect_run(run_id)
        state["valid_alpha2"] = inspection["valid_alpha2"]
        state["compatibility_status"] = inspection["status"]
        if not inspection["valid_alpha2"]:
            state["original_status"] = state.get("status")
            state["status"] = str(inspection["status"] or "INCOMPLETE").lower()
            state["analysis_outcome"] = "NOT_EVALUABLE"
            state["evidence_level"] = "NOT_EVALUABLE"
            state["compatibility_message"] = inspection["message"]
        return state

    def result(self, run_id: str) -> dict:
        state = self.state(run_id)
        inspection = self.inspect_run(run_id)
        run_dir = self.evidence_root / "runs" / run_id
        official_v1 = None
        if state.get("action") != "evidence_batch":
            sample_ids = state.get("sample_ids") or []
            official_path = self.root / "results" / "reports" / f"{sample_ids[0]}_summary.md" if sample_ids else None
            official_status = state.get("official_v1_status", "not_started")
            preservation = "relatório preservado" if official_path and official_path.is_file() else "relatório ainda não disponível"
            official_v1 = f"Relatório anterior: {official_status}; {preservation}."
        if not inspection["valid_alpha2"]:
            v2_status = state.get("evidence_v2_status", state.get("status", "not_started"))
            return {
                "state": state, "complete": inspection["complete"], "valid_alpha2": False,
                "compatibility": inspection, "official_v1": official_v1, "evidence_v2": None,
                "experimental_warning": f"Evidence V2: {v2_status}; análise NOT_EVALUABLE.",
                "artifacts_preserved": run_dir.is_dir(),
            }
        if state.get("action") == "evidence_batch":
            evidence = promote_for_public_output(json.loads((run_dir / "batch_evidence.json").read_text(encoding="utf-8", errors="strict")))
            return {
                "state": state, "complete": True, "valid_alpha2": True, "official_v1": None,
                "evidence_v2": evidence, "explanations": STATUS_EXPLANATIONS,
                "artifacts": [
                    name for name, filename in ARTIFACTS.items()
                    if (run_dir / filename).is_file()
                ],
            }
        evidence = promote_for_public_output(json.loads((run_dir / "sample_evidence.json").read_text(encoding="utf-8", errors="strict")))
        sample = evidence.get("sample_id", "")
        official_path = self.root / "results" / "reports" / f"{sample}_summary.md"
        if official_path and official_path.is_file():
            official_v1 = "Relatório anterior preservado como artefato da execução."
        return {
            "state": state,
            "complete": True,
            "valid_alpha2": True,
            "official_v1": official_v1,
            "evidence_v2": evidence,
            "explanations": STATUS_EXPLANATIONS,
            "artifacts": [
                name for name, filename in ARTIFACTS.items()
                if (run_dir / filename).is_file()
            ],
        }

    def artifact(self, run_id: str, artifact_type: str) -> Path:
        run_id = self._safe_id(run_id, "run_id")
        if artifact_type not in ARTIFACTS:
            raise ValueError("tipo de artefato inválido")
        run_dir = self.evidence_root / "runs" / run_id
        inspection = self.inspect_run(run_id)
        if not inspection["valid_alpha2"]:
            raise ValueError(inspection["message"])
        path = (run_dir / ARTIFACTS[artifact_type]).resolve()
        path.relative_to(run_dir.resolve())
        if not path.is_file():
            raise FileNotFoundError("artefato não encontrado")
        return path
