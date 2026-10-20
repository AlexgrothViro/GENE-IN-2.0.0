"""User-owned paths. These stay outside the Gene-In source tree."""
from __future__ import annotations

import os
from pathlib import Path


def user_config_env_path(env: dict[str, str] | None = None, home: Path | None = None) -> Path:
    """Where the panel may write picornavirus.env.

    ``GENEIN_CONFIG_FILE`` wins. Otherwise an existing absolute
    ``GENEIN_WORK_ROOT`` holds the file. The home default is used when neither
    is set. This function does not create the file.
    """
    values = os.environ if env is None else env
    explicit = str(values.get("GENEIN_CONFIG_FILE") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    work = str(values.get("GENEIN_WORK_ROOT") or "").strip()
    if work:
        candidate = Path(work).expanduser()
        if candidate.is_absolute() and candidate.is_dir():
            return candidate / "config" / "picornavirus.env"
    base = home if home is not None else Path.home()
    return base / ".gene-in" / "config" / "picornavirus.env"


def user_log_dir(env: dict[str, str] | None = None, home: Path | None = None) -> Path:
    """Where panel and diagnostic logs are written.

    An existing absolute ``GENEIN_WORK_ROOT`` holds ``logs/``. Otherwise the
    directory is ``~/.gene-in/logs``. This function does not create it, and it
    never points at the source tree.
    """
    values = os.environ if env is None else env
    work = str(values.get("GENEIN_WORK_ROOT") or "").strip()
    if work:
        candidate = Path(work).expanduser()
        if candidate.is_absolute() and candidate.is_dir():
            return candidate / "logs"
    base = home if home is not None else Path.home()
    return base / ".gene-in" / "logs"
