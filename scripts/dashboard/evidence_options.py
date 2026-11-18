"""Per-run optional inputs: validate metadata, preserve the existing analysis engines."""
import re
import os
import subprocess
import json
import sys
from pathlib import Path

from . import config
from aggregate_hsps import load_labels
from common import sha256_file
from evidence_dashboard import LIBRARY_MODES
from validate_mapping_reference import validate as validate_mapping_reference
from verify_blast_database_manifest import verify as verify_database
from check_competitive_labels import check_subject_labels
from resolve_config import TIER_A_FIELDS, TIER_B_FIELDS, resolve_pipeline_config


OPTION_FIELDS = {
    "competition_enabled": "EVIDENCE_COMPETITION_ENABLED",
    "remapping_enabled": "EVIDENCE_REMAPPING_ENABLED",
}
PATH_FIELDS = {
    "competition_enabled": (("competition_db", "EVIDENCE_COMPOSITE_DB"), ("competition_labels", "EVIDENCE_SUBJECT_LABELS")),
    "remapping_enabled": (("remapping_reference", "EVIDENCE_PANEL_FASTA"), ("remapping_index", "EVIDENCE_PANEL_INDEX")),
}


def config_layers():
    """Use the CLI's shell semantics and preserve its pre-source environment."""
    path = config.get_config_env_path()
    keys = tuple(dict.fromkeys((*TIER_A_FIELDS, *TIER_B_FIELDS)))
    code = 'import json,os,sys; print(json.dumps({k:os.environ.get(k, "") for k in sys.argv[1:]}))'
    shell = 'set -e; if [[ -f "$1" ]]; then set -a; source "$1" >&2; fi; exec "$2" -c "$3" "${@:4}"'
    try:
        process = subprocess.run(["bash", "-c", shell, "genein-options", str(path), sys.executable, code, *keys],
                                 capture_output=True, text=True, check=True, timeout=10)
        sourced = json.loads(process.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise ValueError(f"Não foi possível ler a configuração das opções: {error}") from error
    return str(path), {key: os.environ[key] for key in keys if key in os.environ}, sourced


def resolve_optional_inputs(params, root):
    env = {}
    for option, switch in OPTION_FIELDS.items():
        value = params.get(option)
        if value is not None and type(value) is not bool:
            raise ValueError(f"{option} deve ser verdadeiro, falso ou não definido.")
        if value is not None:
            env[switch] = str(value).lower()
        if value is True:
            for field, variable in PATH_FIELDS[option]:
                if field in params:
                    env[variable] = str(local_path(params[field], root, field))
            if option == "remapping_enabled" and "library_mode" in params:
                env["EVIDENCE_LIBRARY_MODE"] = str(params["library_mode"] or "unknown")
    path, incoming, sourced = config_layers()
    resolved = resolve_pipeline_config(repo_root=str(root), sample_name=str(params.get("sample") or "options-preview"),
        incoming={**incoming, **env}, sourced=sourced, cli={},
        analysis_profiles_config=str(config.REPO_ROOT / "config/analysis_profiles.json"))
    evidence = resolved["evidence"]
    effective = {
        "competition_db": evidence["composite_db"], "competition_labels": evidence["subject_labels"],
        "remapping_reference": evidence["panel_fasta"], "remapping_index": evidence["panel_index"],
        "library_mode": evidence["library_mode"],
    }
    for option, switch in OPTION_FIELDS.items():
        selected = env.get(switch) or incoming.get(switch) or sourced.get(switch) or ""
        active_path = effective["competition_db" if option == "competition_enabled" else "remapping_reference"]
        effective[option] = selected.lower() == "true" or (selected == "" and bool(active_path))
    return env, {"config_file": path, "requested": {key: params.get(key) for key in OPTION_FIELDS}, "effective": effective}


def optional_evidence_defaults(*, root=None):
    return resolve_optional_inputs({}, Path(root or config.REPO_ROOT))[1]


def local_path(value, root, label):
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw or any(character in raw for character in "\0\r\n"):
        raise ValueError(f"Informe um caminho local válido para {label}.")
    windows = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if windows and os.name != "nt":
        raw = f"/mnt/{windows.group(1).lower()}/{windows.group(2).replace(chr(92), '/')}"
    path = Path(raw).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def optional_evidence_inputs(params, *, root=None):
    if not isinstance(params, dict):
        raise ValueError("As opções devem ser um objeto JSON.")
    root = Path(root or config.REPO_ROOT)
    env, details = resolve_optional_inputs(params, root)
    effective = details["effective"]
    details.update({key: effective[key] for key in OPTION_FIELDS})
    try:
        if details["competition_enabled"]:
            prefix = local_path(effective["competition_db"], root, "o banco competitivo")
            labels_path = local_path(effective["competition_labels"], root, "a tabela de rótulos")
            if not Path(str(prefix) + ".db-manifest.json").is_file() or not labels_path.is_file():
                raise ValueError("Manifesto do banco competitivo ou tabela de rótulos não encontrado.")
            count = verify_database(prefix)
            labels = load_labels(str(labels_path))
            identifiers = check_subject_labels(prefix, labels)
            categories = {row["category"] for row in labels.values()}
            if "TARGET_VIRUS" not in categories or not categories - {"TARGET_VIRUS", "UNLABELED"}:
                raise ValueError("Os rótulos precisam identificar alvo e pelo menos uma referência competidora.")
            details["competition"] = {"database": str(prefix), "index_files": count, "labels": str(labels_path), "labels_sha256": sha256_file(labels_path), **identifiers}
        if details["remapping_enabled"]:
            reference = local_path(effective["remapping_reference"], root, "a referência de remapeamento")
            index = local_path(effective["remapping_index"], root, "o índice de remapeamento")
            if not reference.is_file():
                raise ValueError("Referência de remapeamento não encontrada.")
            mode = str(effective["library_mode"] or "unknown")
            if mode not in LIBRARY_MODES:
                raise ValueError("Tipo de biblioteca inválido.")
            checked = validate_mapping_reference(str(index), str(reference), None)
            details["remapping"] = {"reference": str(reference), "index": str(index), "reference_sha256": checked["reference_sha256"], "sequence_count": len(checked["sequences"]), "library_mode": mode}
    except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
        raise ValueError(f"Não foi possível conferir os arquivos opcionais: {error}") from error
    return env, details
