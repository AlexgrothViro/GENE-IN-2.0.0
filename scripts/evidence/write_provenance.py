#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from .common import sha256_file, write_json_atomic
except ImportError:
    from common import sha256_file, write_json_atomic


def version(command: str) -> str:
    executable = shutil.which(command)
    if not executable:
        return "UNAVAILABLE"
    options = ("-version", "--version") if command in {"blastn", "makeblastdb", "blastdbcmd"} else ("--version", "-version")
    for option in options:
        args = [command, option]
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
            line = (result.stdout or result.stderr).splitlines()
            if result.returncode == 0 and line and not line[0].strip().upper().startswith("USAGE"):
                return line[0].strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return "UNKNOWN"


def tool_record(command: str) -> dict[str, str]:
    executable = shutil.which(command)
    return {
        "version": version(command),
        "executable": str(Path(executable).resolve()) if executable else "UNAVAILABLE",
        "sha256": sha256_file(executable) if executable and Path(executable).is_file() else "UNAVAILABLE",
    }


EFFECTIVE_BLAST_KEYS = (
    "blast_evalue",
    "blastn_word_size",
    "blast_gapopen",
    "blast_gapextend",
    "blastn_reward",
    "blastn_penalty",
    "blast_max_target_seqs",
    "blast_database_sequence_count",
)


def apply_effective_blast(values: dict, manifest: Path) -> None:
    """Fill blast parameters that are still unresolved from the search profile.

    The profile is the same artifact written at
    ``results/blast/<sample>_search_profile.json``. Existing concrete values
    are kept.
    """
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    effective = payload.get("effective_blast")
    if not isinstance(effective, dict):
        return
    for key in EFFECTIVE_BLAST_KEYS:
        current = values.get(key)
        incoming = effective.get(key)
        if incoming in (None, ""):
            continue
        if current in (None, "", "unknown"):
            values[key] = str(incoming)


def distribution_identity() -> dict[str, str]:
    """Software version and commit, kept apart from the Evidence contract."""
    root = Path(__file__).resolve().parents[2]
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from genein.identity import software_version, source_commit

    return {"software_version": software_version(root), "source_commit": source_commit(root)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Write reproducible evidence-v2 provenance")
    parser.add_argument("--out", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--search-profile", default="", help="results/blast/<sample>_search_profile.json")
    parser.add_argument("--value", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--artifact", action="append", default=[], metavar="KEY=PATH")
    args = parser.parse_args()
    output_path = Path(args.out).resolve()
    output_root = output_path.parent
    values = {}
    for item in args.value:
        if "=" not in item:
            parser.error("--value must use KEY=VALUE")
        key, value = item.split("=", 1)
        values[key] = value
    if args.search_profile:
        profile = Path(args.search_profile)
        if not profile.is_file():
            parser.error(f"search profile does not exist: {profile}")
        apply_effective_blast(values, profile)
    missing = [key for key in EFFECTIVE_BLAST_KEYS if values.get(key) in (None, "", "unknown")]
    if args.search_profile and missing:
        parser.error(
            "search profile did not resolve blast parameters: " + ", ".join(missing)
        )
    artifacts = {}
    for item in args.artifact:
        if "=" not in item:
            parser.error("--artifact must use KEY=PATH")
        key, value = item.split("=", 1)
        path = Path(value).resolve()
        if not path.is_file():
            parser.error(f"artifact does not exist: {path}")
        try:
            recorded_path = path.relative_to(output_root).as_posix()
        except ValueError:
            recorded_path = str(path)
        artifacts[key] = {
            "path": recorded_path, "size": path.stat().st_size, "sha256": sha256_file(path),
        }
    write_json_atomic(output_path, {
        "schema_version": "2.0", "pipeline_version": "2.0.0-alpha.2",
        **distribution_identity(),
        "platform": platform.platform(), "config_path": str(Path(args.config).resolve()),
        "config_sha256": sha256_file(args.config), "parameters": values, "artifacts": artifacts,
        "tools": {name: tool_record(name) for name in (
            "python3", "fastp", "blastn", "makeblastdb", "bowtie2", "bowtie2-inspect", "samtools", "spades.py",
            "metaspades.py", "umi_tools", "mafft", "iqtree2", "iqtree",
        )},
    })


if __name__ == "__main__":
    main()
