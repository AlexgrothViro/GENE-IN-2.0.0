#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path

try:
    from .activation_policy import (
        POLICY_IDENTITY_FIELDS,
        load_experimental_activation_policy,
        load_public_activation_policy,
        validate_policy_identity,
    )
    from .aggregate_hsps import FIELDS as FRAGMENT_FIELDS
    from .build_hsp_evidence import FIELDS as HSP_FIELDS
    from .build_loci import FIELDS as LOCUS_FIELDS
    from .build_template_lineage import FIELDS as LINEAGE_FIELDS
    from .common import configure_csv_field_limit, sha256_file, sha256_text, read_fasta, read_tsv, iter_tsv, validate_artifact_manifest
    from .competitive_hits import FIELDS as COMPETITIVE_FIELDS
    from .evidence_contract import PIPELINE_VERSION, promote_for_public_output, validate_document
    from .evaluate_controls import FIELDS as CONTROL_FIELDS
    from .summarize_coverage import FIELDS as COVERAGE_FIELDS
    from .summarize_read_support import FIELDS as READ_SUPPORT_FIELDS
    from .validate_manifest import FIELDS as BATCH_MANIFEST_FIELDS
except ImportError:
    from activation_policy import (
        POLICY_IDENTITY_FIELDS,
        load_experimental_activation_policy,
        load_public_activation_policy,
        validate_policy_identity,
    )
    from aggregate_hsps import FIELDS as FRAGMENT_FIELDS
    from build_hsp_evidence import FIELDS as HSP_FIELDS
    from build_loci import FIELDS as LOCUS_FIELDS
    from build_template_lineage import FIELDS as LINEAGE_FIELDS
    from common import configure_csv_field_limit, sha256_file, sha256_text, read_fasta, read_tsv, iter_tsv, validate_artifact_manifest
    from competitive_hits import FIELDS as COMPETITIVE_FIELDS
    from evidence_contract import PIPELINE_VERSION, promote_for_public_output, validate_document
    from evaluate_controls import FIELDS as CONTROL_FIELDS
    from summarize_coverage import FIELDS as COVERAGE_FIELDS
    from summarize_read_support import FIELDS as READ_SUPPORT_FIELDS
    from validate_manifest import FIELDS as BATCH_MANIFEST_FIELDS

CONCORDANCE_TSV_FIELDS = [
    "reference_id", "category", "locus_id", "query_ids",
    "supporting_assemblers", "support_count", "concordance_status",
]


REQUIRED_TSV = {
    "fragment_evidence.tsv",
    "locus_evidence.tsv",
    "competitive_hits.tsv",
    "read_support.tsv",
    "coverage.tsv",
    "hsp_evidence.tsv",
    "template_lineage.tsv",
}
HISTORICAL_REQUIRED_TSV = {
    "fragment_evidence.tsv",
    "locus_evidence.tsv",
    "competitive_hits.tsv",
    "read_support.tsv",
    "coverage.tsv",
}
OPTIONAL_TSV = {"assembly_concordance.tsv"}
REQUIRED_JSON = {"sample_evidence.json", "provenance.json", "runtime_preflight.json"}
OPTIONAL_JSON = {"assembly_concordance.json"}
REQUIRED_TEXT = {"evidence_report.md"}
BATCH_REQUIRED_TSV = {"batch_manifest.tsv", "control_status.tsv"}
BATCH_REQUIRED_JSON = {"batch_evidence.json", "provenance.json", "run_state.json"}
BATCH_REQUIRED_TEXT = {"batch_report.md"}
# Exact producer contract for new runs:
# - hsp_evidence / template_lineage: ordered list equality with producer FIELDS
# - other contract TSVs: exact set equality with required columns (extras rejected)
REQUIRED_HEADERS: dict[str, list[str] | set[str]] = {
    "fragment_evidence.tsv": set(FRAGMENT_FIELDS),
    "locus_evidence.tsv": set(LOCUS_FIELDS),
    "competitive_hits.tsv": set(COMPETITIVE_FIELDS),
    "read_support.tsv": set(READ_SUPPORT_FIELDS),
    "coverage.tsv": set(COVERAGE_FIELDS),
    "assembly_concordance.tsv": set(CONCORDANCE_TSV_FIELDS),
    "hsp_evidence.tsv": list(HSP_FIELDS),
    "template_lineage.tsv": list(LINEAGE_FIELDS),
}
BATCH_REQUIRED_HEADERS = {
    "batch_manifest.tsv": list(BATCH_MANIFEST_FIELDS),
    "control_status.tsv": list(CONTROL_FIELDS),
}


def is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
HISTORICAL_REQUIRED_HEADERS = {
    "fragment_evidence.tsv": {"qseqid", "sseqid", "task", "query_covered_bp", "reference_covered_bp", "adj_identity"},
    "locus_evidence.tsv": {
        "locus_id", "sseqid", "segment", "orientation", "covered_reference_bp",
        "query_ids",
    },
    "competitive_hits.tsv": {"qseqid", "task", "target_bitscore", "competitor_bitscore", "delta_bitscore", "specificity_status"},
    "read_support.tsv": {"sample_id", "reference_id", "category", "locus_id", "query_ids", "unique_templates", "distinct_starts", "support_status"},
    "coverage.tsv": {"reference_id", "category", "locus_id", "query_ids", "breadth_1x", "breadth_3x", "mean_depth_locus", "median_depth_covered"},
    "assembly_concordance.tsv": {"reference_id", "category", "locus_id", "supporting_assemblers", "support_count", "concordance_status"},
}


def validate_tsv(
    path: Path,
    *,
    required_headers: dict[str, list[str] | set[str]] | None = None,
    historical: bool = False,
) -> None:
    headers = required_headers if required_headers is not None else REQUIRED_HEADERS
    # Evidence fields can contain long query/interval lists. Match the shared
    # TSV readers so validation does not reject valid large artifacts at the
    # csv module's 128 KiB default.
    configure_csv_field_limit()
    with path.open("r", encoding="utf-8", errors="strict", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if not header or any(not value for value in header):
            raise ValueError(f"invalid TSV header: {path.name}")
        if len(header) != len(set(header)):
            raise ValueError(f"duplicate TSV columns: {path.name}")
        required = headers.get(path.name)
        if required is not None:
            if historical or not isinstance(required, list):
                required_set = set(required)
                # The review adds per-reference competition to Alpha.2. Old
                # committed tables remain readable; their best-reference-only
                # evidence never qualifies other references or species.
                optional_extension = {"target_evidence_json"} if path.name == "competitive_hits.tsv" else set()
                missing = sorted(required_set - optional_extension - set(header))
                if missing:
                    raise ValueError(f"missing required TSV columns: {', '.join(missing)}")
                if not historical:
                    extra = sorted(set(header) - required_set)
                    if extra:
                        raise ValueError(f"unexpected TSV columns: {', '.join(extra)}")
            else:
                if header != list(required):
                    raise ValueError(
                        f"TSV header must equal producer FIELDS exactly: {path.name}"
                    )
        for line_number, row in enumerate(reader, 2):
            if len(row) != len(header):
                raise ValueError(f"{path.name}:{line_number}: column count mismatch")


def validate_provenance(path: Path, *, compatibility_mode: str | None = None) -> dict:
    value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    if compatibility_mode == "historical_alpha2_fixture":
        if not isinstance(value, dict) or value.get("schema_version") != "2.0":
            raise ValueError("historical provenance schema is invalid")
        return value
    required = {
        "schema_version", "pipeline_version", "platform", "config_path",
        "config_sha256", "parameters", "artifacts", "tools",
    }
    if not isinstance(value, dict) or required - set(value):
        raise ValueError("provenance fields are incomplete")
    if value["schema_version"] != "2.0" or value["pipeline_version"] != PIPELINE_VERSION:
        raise ValueError("provenance contract version is incompatible")
    for name in ("platform", "config_path", "config_sha256"):
        if not isinstance(value[name], str) or not value[name]:
            raise ValueError(f"provenance {name} is required")
    config_path = Path(value["config_path"])
    if not config_path.is_absolute() or not is_sha256(value["config_sha256"]):
        raise ValueError("provenance config identity is invalid")
    if not isinstance(value["parameters"], dict):
        raise ValueError("provenance parameters must be an object")
    artifacts = value["artifacts"]
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("provenance artifacts are empty or invalid")
    root = path.parent.resolve()
    for name, record in artifacts.items():
        if not isinstance(name, str) or not name or not isinstance(record, dict):
            raise ValueError("invalid provenance artifact record")
        if set(record) != {"path", "size", "sha256"}:
            raise ValueError(f"invalid provenance artifact fields: {name}")
        if (
            isinstance(record["size"], bool)
            or not isinstance(record["size"], int)
            or record["size"] < 0
            or not is_sha256(record["sha256"])
        ):
            raise ValueError(f"invalid provenance artifact identity: {name}")
        recorded_path = record["path"]
        if not isinstance(recorded_path, str) or not recorded_path:
            raise ValueError(f"invalid provenance artifact path: {name}")
        artifact_path = Path(recorded_path)
        internal = not artifact_path.is_absolute()
        if internal:
            artifact_path = (root / artifact_path).resolve()
            try:
                artifact_path.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"provenance artifact escapes run directory: {name}") from exc
            if not artifact_path.is_file():
                raise ValueError(f"provenance artifact is not readable: {name}")
            if artifact_path.stat().st_size != record["size"]:
                raise ValueError(f"provenance artifact size mismatch: {name}")
            if sha256_file(artifact_path) != record["sha256"]:
                raise ValueError(f"provenance artifact hash mismatch: {name}")
    tools = value["tools"]
    if not isinstance(tools, dict) or not tools:
        raise ValueError("provenance tools are empty or invalid")
    for name, record in tools.items():
        if not isinstance(name, str) or not isinstance(record, dict):
            raise ValueError("invalid provenance tool record")
        if set(record) != {"version", "executable", "sha256"}:
            raise ValueError(f"invalid provenance tool fields: {name}")
        if any(not isinstance(record[field], str) or not record[field] for field in record):
            raise ValueError(f"invalid provenance tool values: {name}")
        if record["executable"] == "UNAVAILABLE":
            if record["sha256"] != "UNAVAILABLE":
                raise ValueError(f"unavailable provenance tool has a hash: {name}")
        else:
            executable = Path(record["executable"])
            if not executable.is_absolute() or not is_sha256(record["sha256"]):
                raise ValueError(f"provenance tool identity mismatch: {name}")
    return value


def validate_json(
    path: Path, *, policy: dict | None = None, compatibility_mode: str | None = None,
) -> None:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if path.name == "runtime_preflight.json":
        if not isinstance(value, dict) or value.get("valid") is not True:
            raise ValueError("runtime preflight is not valid")
    elif path.name == "sample_evidence.json":
        validate_document(value, policy=policy, compatibility_mode=compatibility_mode)
    elif path.name == "batch_evidence.json":
        promote_for_public_output(value, policy=policy)
    elif path.name == "provenance.json":
        validate_provenance(path, compatibility_mode=compatibility_mode)
    elif path.name == "run_state.json":
        if not isinstance(value, dict) or not isinstance(value.get("run_id"), str):
            raise ValueError("run state schema is invalid")
    elif path.name == "assembly_concordance.json":
        if not isinstance(value, dict) or value.get("schema_version") != "1.0":
            raise ValueError("assembly concordance schema is invalid")
        if value.get("evidence_authority") != "ANALYSIS":
            raise ValueError("assembly concordance evidence_authority is invalid")


def validate_commit_metadata(
    directory: Path,
    expected_run_id: str | None = None,
    *,
    policy: dict | None = None,
    compatibility_mode: str | None = None,
) -> list[str]:
    errors: list[str] = []
    manifest_path = directory / "artifact_manifest.json"
    success_path = directory / "SUCCESS.json"
    if not manifest_path.is_file():
        errors.append("missing commit artifact: artifact_manifest.json")
    if not success_path.is_file():
        errors.append("missing commit artifact: SUCCESS.json")
    if errors:
        return errors
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8", errors="strict"))
        errors.extend(validate_artifact_manifest(directory, manifest))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid artifact_manifest.json: {exc}")
        return errors
    try:
        success = json.loads(success_path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid SUCCESS.json: {exc}")
        return errors
    if not isinstance(success, dict):
        return errors + ["SUCCESS.json must be an object"]
    if success.get("pipeline_version") != PIPELINE_VERSION:
        errors.append("SUCCESS.json is not an Alpha.2 commit")
    if not isinstance(success.get("shadow_mode"), bool):
        errors.append("SUCCESS.json shadow_mode must be boolean")
    if success.get("status") not in {"done", "done_with_warning"}:
        errors.append("SUCCESS.json has no successful terminal status")
    if not isinstance(success.get("run_id"), str) or not success["run_id"].strip():
        errors.append("SUCCESS.json run_id is required")
    if expected_run_id is not None and success.get("run_id") != expected_run_id:
        errors.append("SUCCESS.json run_id does not match the requested run")
    files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
    if success.get("artifact_count") != len(files):
        errors.append("SUCCESS.json artifact_count does not match the manifest")
    if success.get("artifact_manifest_sha256") != sha256_file(manifest_path):
        errors.append("SUCCESS.json artifact manifest hash mismatch")
    sample_evidence = directory / "sample_evidence.json"
    batch_evidence = directory / "batch_evidence.json"
    state_path = directory / "run_state.json"
    if sample_evidence.is_file() == batch_evidence.is_file():
        errors.append("committed run must contain exactly one canonical evidence document")
        return errors
    state = None
    if not state_path.is_file():
        errors.append("missing commit artifact: run_state.json")
    else:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8", errors="strict"))
            if not isinstance(state, dict) or state.get("run_id") != success.get("run_id"):
                errors.append("run_state.json identity does not match SUCCESS.json")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"invalid run_state.json during commit verification: {exc}")
    success_identity = None
    if compatibility_mode is None:
        try:
            success_identity = validate_policy_identity(success, context="SUCCESS.json")
            if state is not None:
                validate_policy_identity(
                    state, expected=success_identity, context="run_state.json",
                )
        except ValueError as exc:
            errors.append(str(exc))
    if sample_evidence.is_file():
        try:
            evidence = validate_document(
                json.loads(sample_evidence.read_text(encoding="utf-8", errors="strict")),
                policy=policy,
                compatibility_mode=compatibility_mode,
            )
            if evidence.get("run_id") != success.get("run_id"):
                errors.append("sample evidence run_id does not match SUCCESS.json")
            if evidence.get("shadow_mode") is not success.get("shadow_mode"):
                errors.append("sample evidence shadow_mode does not match SUCCESS.json")
            if "sample_evidence_sha256" not in success:
                errors.append("SUCCESS.json sample evidence hash is required")
            elif success["sample_evidence_sha256"] != sha256_file(sample_evidence):
                errors.append("SUCCESS.json sample evidence hash mismatch")
            provenance_path = directory / "provenance.json"
            if provenance_path.is_file() and compatibility_mode is None:
                provenance = json.loads(provenance_path.read_text(encoding="utf-8", errors="strict"))
                if evidence.get("provenance") != provenance:
                    errors.append("sample evidence provenance does not match provenance.json")
            if compatibility_mode == "historical_alpha2_fixture":
                if (
                    success.get("policy_version") != "2.0-alpha"
                    or any(field in success for field in POLICY_IDENTITY_FIELDS if field != "shadow_mode")
                ):
                    errors.append("historical SUCCESS.json identity is not the frozen Alpha.2 identity")
                if state is not None:
                    if (
                        state.get("policy_version") != "2.0-alpha"
                        or state.get("shadow_mode") is not True
                        or any(field in state for field in POLICY_IDENTITY_FIELDS if field != "shadow_mode")
                    ):
                        errors.append("historical run_state.json identity is not the frozen Alpha.2 identity")
            else:
                if success_identity is not None:
                    validate_policy_identity(
                        evidence, expected=success_identity, context="sample evidence",
                    )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"invalid sample_evidence.json during commit verification: {exc}")
    if batch_evidence.is_file():
        try:
            batch = promote_for_public_output(
                json.loads(batch_evidence.read_text(encoding="utf-8", errors="strict")),
                policy=policy,
            )
            if batch.get("run_id") != success.get("run_id"):
                errors.append("batch evidence run_id does not match SUCCESS.json")
            if batch.get("shadow_mode") is not success.get("shadow_mode"):
                errors.append("batch evidence shadow_mode does not match SUCCESS.json")
            if "batch_evidence_sha256" not in success:
                errors.append("SUCCESS.json batch evidence hash is required")
            elif success["batch_evidence_sha256"] != sha256_file(batch_evidence):
                errors.append("SUCCESS.json batch evidence hash mismatch")
            if success.get("sample_count") != len(batch["samples"]):
                errors.append("SUCCESS.json sample_count does not match batch evidence")
            if state is not None:
                if state.get("action") != "evidence_batch" or state.get("batch_id") != batch.get("batch_id"):
                    errors.append("batch run_state.json identity does not match batch evidence")
            if success_identity is not None:
                validate_policy_identity(
                    batch, expected=success_identity, context="batch evidence",
                )
            declared_samples = {item["sample_id"]: item["child_run_id"] for item in batch["samples"]}
            samples_root = directory / "samples"
            actual_samples = {
                path.name for path in samples_root.iterdir() if path.is_dir()
            } if samples_root.is_dir() else set()
            if set(declared_samples) != actual_samples:
                errors.append("batch committed samples do not match batch evidence")
            for sample_id, child_run_id in sorted(declared_samples.items()):
                child_dir = samples_root / sample_id
                for error in validate(child_dir, policy=policy, compatibility_mode=compatibility_mode):
                    errors.append(f"sample {sample_id}: {error}")
                child_success_path = child_dir / "SUCCESS.json"
                if child_success_path.is_file():
                    child_success = json.loads(child_success_path.read_text(encoding="utf-8", errors="strict"))
                    if child_success.get("run_id") != child_run_id:
                        errors.append(f"sample {sample_id}: child run_id mismatch")
                    if child_success.get("parent_run_id") != success.get("run_id"):
                        errors.append(f"sample {sample_id}: parent run_id mismatch")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"invalid batch_evidence.json during commit verification: {exc}")
    return errors


def validate_candidate_exports(directory: Path) -> list[str]:
    """New recovery artifacts must agree before transactional publication."""
    names = ("candidate_queries.json", "candidate_sequences.tsv", "candidate_sequences.fa")
    if not any((directory / name).exists() for name in names):
        return []
    if not all((directory / name).is_file() for name in names):
        return ["candidate recovery exports are incomplete"]
    try:
        manifest = json.loads((directory / names[0]).read_text(encoding="utf-8"))
        if manifest.get("schema_version") != "1.0" or not isinstance(manifest.get("queries"), dict):
            raise ValueError("invalid candidate query manifest")
        metadata = manifest["queries"]
        sequences = read_fasta(directory / names[2])
        row_count = sum(1 for _ in iter_tsv(directory / names[1]))
        fragment_count = 0
        aligned_queries = set()
        for fragment in iter_tsv(directory / "fragment_evidence.tsv"):
            fragment_count += 1
            aligned_queries.add(fragment["qseqid"])
        if row_count != fragment_count or set(sequences) != aligned_queries:
            raise ValueError("candidate exports do not cover every aligned query")
        for row, fragment in zip(iter_tsv(directory / names[1]),
                                 iter_tsv(directory / "fragment_evidence.tsv")):
            query = fragment["qseqid"]
            entry = metadata[query]
            sequence = sequences[query]
            if (sha256_text(sequence) != entry["sequence_sha256"] or
                int(entry["length_bp"]) != len(sequence) or
                int(row["sequence_length_bp"]) != len(sequence) or
                row["sequence_sha256"] != entry["sequence_sha256"]):
                raise ValueError(f"candidate sequence/hash/length mismatch: {query}")
            if row["query_origins"] != ";".join(sorted(entry["source_counts"])):
                raise ValueError(f"candidate origin mismatch: {query}")
            if row["aligned_query_bp"] != fragment["query_covered_bp"]:
                raise ValueError(f"candidate aligned length mismatch: {query}")
            for field in ("qseqid", "sseqid", "category", "taxon", "task", "query_coverage",
                          "weighted_pident", "best_bitscore", "best_evalue", "assembly_method"):
                if row[field] != fragment[field]:
                    raise ValueError(f"candidate alignment mismatch for {query}: {field}")
        return []
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
        return [f"invalid candidate recovery exports: {exc}"]


def validate(
    directory: Path, *, policy: dict | None = None, compatibility_mode: str | None = None,
) -> list[str]:
    errors = []
    batch = (
        (directory / "batch_evidence.json").exists()
        or (directory / "batch_manifest.tsv").exists()
        or (directory / "samples").is_dir()
    )
    if batch:
        for name in sorted(BATCH_REQUIRED_TSV | BATCH_REQUIRED_JSON | BATCH_REQUIRED_TEXT):
            path = directory / name
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"missing or empty artifact: {name}")
                continue
            try:
                if name.endswith(".tsv"):
                    validate_tsv(path, required_headers=BATCH_REQUIRED_HEADERS)
                elif name.endswith(".json"):
                    validate_json(path, policy=policy, compatibility_mode=compatibility_mode)
            except (OSError, ValueError, csv.Error, json.JSONDecodeError) as exc:
                errors.append(f"invalid artifact {name}: {exc}")
        samples_root = directory / "samples"
        if not samples_root.is_dir() or not any(path.is_dir() for path in samples_root.iterdir()):
            errors.append("batch has no sample artifact directories")
        elif samples_root.is_dir():
            for sample_dir in sorted(path for path in samples_root.iterdir() if path.is_dir()):
                for error in validate(sample_dir, policy=policy, compatibility_mode=compatibility_mode):
                    errors.append(f"sample {sample_dir.name}: {error}")
        partials = [
            path.relative_to(directory).as_posix()
            for path in directory.rglob("*")
            if path.is_file() and (path.name.endswith(".tmp") or path.name.startswith("."))
        ]
        if partials:
            errors.append("temporary artifacts remain: " + ", ".join(sorted(partials)))
        if (directory / "artifact_manifest.json").exists() or (directory / "SUCCESS.json").exists():
            errors.extend(
                validate_commit_metadata(directory, policy=policy, compatibility_mode=compatibility_mode)
            )
        return errors
    historical = compatibility_mode == "historical_alpha2_fixture"
    required_tsv = HISTORICAL_REQUIRED_TSV if historical else REQUIRED_TSV
    header_contract = HISTORICAL_REQUIRED_HEADERS if historical else REQUIRED_HEADERS
    for name in sorted(required_tsv | REQUIRED_JSON | REQUIRED_TEXT):
        path = directory / name
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing or empty artifact: {name}")
            continue
        try:
            if name.endswith(".tsv"):
                validate_tsv(path, required_headers=header_contract, historical=historical)
            elif name.endswith(".json"):
                validate_json(path, policy=policy, compatibility_mode=compatibility_mode)
        except (OSError, ValueError, csv.Error, json.JSONDecodeError) as exc:
            errors.append(f"invalid artifact {name}: {exc}")
    for name in sorted(OPTIONAL_JSON):
        path = directory / name
        if path.is_file() and path.stat().st_size:
            try:
                validate_json(path, policy=policy, compatibility_mode=compatibility_mode)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"invalid optional artifact {name}: {exc}")
    for name in sorted(OPTIONAL_TSV):
        path = directory / name
        if path.is_file() and path.stat().st_size:
            try:
                validate_tsv(path, required_headers=header_contract, historical=historical)
            except (OSError, ValueError, csv.Error) as exc:
                errors.append(f"invalid optional artifact {name}: {exc}")
    provenance_path = directory / "provenance.json"
    evidence_path = directory / "sample_evidence.json"
    if (
        provenance_path.is_file() and evidence_path.is_file()
        and compatibility_mode is None
    ):
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8", errors="strict"))
            evidence = json.loads(evidence_path.read_text(encoding="utf-8", errors="strict"))
            if evidence.get("provenance") != provenance:
                errors.append("sample evidence provenance does not match provenance.json")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"cannot compare sample provenance: {exc}")
    errors.extend(validate_candidate_exports(directory))
    partials = [p.name for p in directory.rglob("*") if p.is_file() and (p.name.endswith(".tmp") or p.name.startswith("."))]
    if partials:
        errors.append("temporary artifacts remain: " + ", ".join(sorted(partials)))
    bam = directory / "read_support.bam"
    bai = directory / "read_support.bam.bai"
    if bam.exists():
        if not bai.is_file() or bai.stat().st_size == 0:
            errors.append("BAM exists without a valid BAI")
        samtools = shutil.which("samtools")
        if not samtools:
            errors.append("samtools unavailable for BAM quickcheck")
        else:
            result = subprocess.run([samtools, "quickcheck", "-v", str(bam)], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                errors.append("samtools quickcheck failed: " + (result.stderr.strip() or result.stdout.strip()))
    manifest_exists = (directory / "artifact_manifest.json").exists()
    success_exists = (directory / "SUCCESS.json").exists()
    if manifest_exists or success_exists:
        errors.extend(
            validate_commit_metadata(directory, policy=policy, compatibility_mode=compatibility_mode)
        )
    return errors


def _load_policy(args: argparse.Namespace) -> dict | None:
    """Same public/experimental resolution used by scripts/evidence/run.sh.

    ``None`` preserves the historical default of validating against the
    active public policy for every call site that does not pass either flag.
    """
    if getattr(args, "experimental_activation_policy", None):
        return load_experimental_activation_policy(
            args.experimental_activation_policy, profiles_path=args.profiles,
        )
    if getattr(args, "activation_policy", None):
        return load_public_activation_policy(args.activation_policy, profiles_path=args.profiles)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a complete Evidence V2 staging directory")
    parser.add_argument("--dir", required=True, type=Path)
    parser.add_argument("--historical-alpha2-fixture", action="store_true")
    policy_group = parser.add_mutually_exclusive_group()
    policy_group.add_argument("--activation-policy")
    policy_group.add_argument("--experimental-activation-policy")
    parser.add_argument("--profiles")
    args = parser.parse_args()
    errors = validate(
        args.dir,
        policy=_load_policy(args),
        compatibility_mode=(
            "historical_alpha2_fixture" if args.historical_alpha2_fixture else None
        ),
    )
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        raise SystemExit(1)
    print("[OK] Os artefatos da camada de evidências estão completos e legíveis")


if __name__ == "__main__":
    main()

