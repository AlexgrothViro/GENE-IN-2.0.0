"""Preflight equality of database accessions and label identifiers."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

from aggregate_hsps import load_labels
from common import blast_db_arg
from verify_blast_database_manifest import verify


def check_subject_labels(prefix: Path, labels: dict) -> dict:
    try:
        result = subprocess.run(["blastdbcmd", "-db", blast_db_arg(prefix), "-entry", "all", "-outfmt", "%a"],
                                check=True, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"Não foi possível listar os IDs do banco competitivo: {error}") from error
    database_ids = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if not database_ids:
        raise ValueError("O banco competitivo não retornou IDs para a conferência de rótulos.")
    missing = sorted(database_ids - labels.keys())
    orphaned = sorted(labels.keys() - database_ids)
    if missing or orphaned:
        raise ValueError("IDs divergentes entre banco e rótulos; "
                         f"IDs do banco sem rótulo: total={len(missing)}, exemplos={missing[:20]}; "
                         f"rótulos sem ID no banco: total={len(orphaned)}, exemplos={orphaned[:20]}")
    return {"database_id_count": len(database_ids), "label_count": len(labels),
            "ids_sha256": hashlib.sha256(("\n".join(sorted(database_ids)) + "\n").encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    args = parser.parse_args()
    try:
        verify(args.database)
        details = check_subject_labels(args.database, load_labels(str(args.labels)))
    except (ValueError, OSError) as error:
        print(f"[FATAL] Banco competitivo e rótulos: {error}", file=sys.stderr)
        return 2
    print(f"[OK] IDs do banco e rótulos: {details['database_id_count']}; SHA-256 dos IDs: {details['ids_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
