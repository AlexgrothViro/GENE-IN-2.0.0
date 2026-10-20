"""Runtime helpers for Validation (PATH isolation, tool presence)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional, Sequence


PIPELINE_TOOLS = ("python3", "bash", "blastn", "makeblastdb", "blastdbcmd")
OPERATIONAL_TOOLS = (
    "python3",
    "fastp",
    "bowtie2",
    "bowtie2-build",
    "samtools",
    "blastn",
    "blastdbcmd",
    "makeblastdb",
    "spades.py",
    "metaspades.py",
    "velveth",
    "velvetg",
)


def genein_bundle_env_bin(home: Optional[Path] = None) -> Optional[Path]:
    explicit_env = os.environ.get("GENEIN_ENV_DIR", "").strip()
    explicit_bundle = os.environ.get("GENEIN_BUNDLE_DIR", "").strip()
    if explicit_env:
        env_bin = Path(explicit_env).expanduser() / "bin"
    elif explicit_bundle:
        env_bin = Path(explicit_bundle).expanduser() / "env" / "bin"
    else:
        env_bin = (home or Path.home()) / ".gene-in-bundle" / "env" / "bin"
    if (env_bin / "blastn").is_file():
        return env_bin
    if explicit_env or explicit_bundle:
        raise FileNotFoundError(f"Ambiente Gene-In solicitado ausente ou incompleto: {env_bin}")
    return None


def ensure_genein_bundle_path(home: Optional[Path] = None) -> Optional[str]:
    """Prepend the isolated Gene-In bundle env to PATH. Does not replace system Python."""
    env_bin = genein_bundle_env_bin(home)
    if env_bin is None:
        return None
    prefix = str(env_bin)
    separator = ";" if os.name == "nt" else ":"
    parts = [part for part in os.environ.get("PATH", "").split(separator) if part]
    if prefix not in parts:
        os.environ["PATH"] = prefix + ((separator + separator.join(parts)) if parts else "")
    return prefix


def which_missing(names: Sequence[str]) -> list[str]:
    return [name for name in names if shutil.which(name) is None]
