"""Per-run optional inputs: validate metadata, preserve the existing analysis engines."""
import re
import os
import subprocess
from pathlib import Path

from . import config
from aggregate_hsps import load_labels
from common import sha256_file
from evidence_dashboard import LIBRARY_MODES
from validate_mapping_reference import validate as validate_mapping_reference
from verify_blast_database_manifest import verify as verify_database


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
    env, details = {}, {}
    for option, switch in (("competition_enabled", "EVIDENCE_COMPETITION_ENABLED"), ("remapping_enabled", "EVIDENCE_REMAPPING_ENABLED")):
        if option in params:
            if type(params[option]) is not bool:
                raise ValueError(f"{option} deve ser verdadeiro ou falso.")
            env[switch] = str(params[option]).lower()
        details[option] = params.get(option, False) is True
    try:
        if details["competition_enabled"]:
            prefix = local_path(params.get("competition_db"), root, "o banco competitivo")
            labels_path = local_path(params.get("competition_labels"), root, "a tabela de rótulos")
            if not Path(str(prefix) + ".db-manifest.json").is_file() or not labels_path.is_file():
                raise ValueError("Manifesto do banco competitivo ou tabela de rótulos não encontrado.")
            count = verify_database(prefix)
            labels = load_labels(str(labels_path))
            categories = {row["category"] for row in labels.values()}
            if "TARGET_VIRUS" not in categories or not categories - {"TARGET_VIRUS", "UNLABELED"}:
                raise ValueError("Os rótulos precisam identificar alvo e pelo menos uma referência competidora.")
            env.update(EVIDENCE_COMPOSITE_DB=str(prefix), EVIDENCE_SUBJECT_LABELS=str(labels_path))
            details["competition"] = {"database": str(prefix), "index_files": count, "labels": str(labels_path), "labels_sha256": sha256_file(labels_path), "label_count": len(labels)}
        if details["remapping_enabled"]:
            reference = local_path(params.get("remapping_reference"), root, "a referência de remapeamento")
            index = local_path(params.get("remapping_index"), root, "o índice de remapeamento")
            if not reference.is_file():
                raise ValueError("Referência de remapeamento não encontrada.")
            mode = str(params.get("library_mode") or "unknown")
            if mode not in LIBRARY_MODES:
                raise ValueError("Tipo de biblioteca inválido.")
            checked = validate_mapping_reference(str(index), str(reference), None)
            env.update(EVIDENCE_PANEL_FASTA=str(reference), EVIDENCE_PANEL_INDEX=str(index), EVIDENCE_LIBRARY_MODE=mode)
            details["remapping"] = {"reference": str(reference), "index": str(index), "reference_sha256": checked["reference_sha256"], "sequence_count": len(checked["sequences"]), "library_mode": mode}
    except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
        raise ValueError(f"Não foi possível conferir os arquivos opcionais: {error}") from error
    return env, details
