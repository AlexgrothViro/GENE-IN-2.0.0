"""User-owned paths. These stay outside the Gene-In source tree."""
from __future__ import annotations

import os
import stat
from pathlib import Path


class ConfigPermissionError(RuntimeError):
    """A work-directory picornavirus.env is writable by group or others."""


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


def _values(env: dict[str, str] | None) -> dict[str, str]:
    return os.environ if env is None else env


def _absolute_work_root(values: dict[str, str]) -> Path | None:
    work = str(values.get("GENEIN_WORK_ROOT") or "").strip()
    if not work:
        return None
    candidate = Path(work).expanduser()
    if candidate.is_absolute():
        return candidate
    return None


def _existing_work_root(values: dict[str, str]) -> Path | None:
    candidate = _absolute_work_root(values)
    if candidate is not None and candidate.is_dir():
        return candidate
    return None


def config_writable_by_others(path: Path) -> bool:
    """True when the mode allows write by others (permission digit 2, 3, 6 or 7).

    Group write is accepted. umask 002 creates 0664, and refusing that locks
    a file the panel itself just saved.
    """
    mode = stat.S_IMODE(path.stat().st_mode)
    return bool(mode & 0o002)


def resolve_config_file(
    env: dict[str, str] | None = None,
    home: Path | None = None,
    repo_root: Path | str | None = None,
) -> Path:
    """File the pipeline, Make and the panel read.

    Precedence: ``GENEIN_CONFIG_FILE`` (even when the file is missing),
    then ``$GENEIN_WORK_ROOT/config/picornavirus.env`` when that file exists,
    then ``~/.gene-in/config/picornavirus.env`` when that file exists, then
    the source ``config/picornavirus.env``, then ``config.env``. The last
    resort is the write path from :func:`user_config_env_path`.

    A work-root file that is writable by others is refused. The search does
    not continue to a less specific file. Group write is not refused.
    """
    values = _values(env)
    explicit = str(values.get("GENEIN_CONFIG_FILE") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    work = _existing_work_root(values)
    if work is not None:
        work_file = work / "config" / "picornavirus.env"
        if work_file.is_file():
            if config_writable_by_others(work_file):
                raise ConfigPermissionError(
                    "picornavirus.env no diretório de trabalho é gravável por outros: "
                    f"{work_file}"
                )
            return work_file
    base = home if home is not None else Path.home()
    home_file = base / ".gene-in" / "config" / "picornavirus.env"
    if home_file.is_file():
        return home_file
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    repo_file = root / "config" / "picornavirus.env"
    if repo_file.is_file():
        return repo_file
    legacy = root / "config.env"
    if legacy.is_file():
        return legacy
    return user_config_env_path(values, base)


def _manifest_ready(prefix: Path) -> bool:
    manifest = Path(str(prefix) + ".db-manifest.json")
    try:
        return manifest.is_file() and manifest.stat().st_size > 0
    except OSError:
        return False


def resolve_blast_db(
    db: str,
    env: dict[str, str] | None = None,
    home: Path | None = None,
    repo_root: Path | str | None = None,
    configured: str = "",
) -> str:
    """BLAST prefix shared by Make, the shell pipeline and the panel.

    An explicit ``BLAST_DB`` from the winning config is returned unchanged.
    Otherwise the first prepared database (non-empty ``*.db-manifest.json``)
    wins, in the same order as the config file: the work directory, then
    ``~/.gene-in``, then the source tree. With nothing prepared, the default
    is ``$GENEIN_WORK_ROOT/blastdb/<db>`` when that directory exists, and
    ``blastdb/<db>`` otherwise.
    """
    chosen = str(configured or "").strip().strip('"').strip("'")
    if chosen:
        return chosen
    values = _values(env)
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    base = home if home is not None else Path.home()
    work = _existing_work_root(values)
    if work is not None:
        prefix = work / "blastdb" / db
        if _manifest_ready(prefix):
            return str(prefix)
    home_prefix = base / ".gene-in" / "blastdb" / db
    if _manifest_ready(home_prefix):
        return str(home_prefix)
    repo_prefix = root / "blastdb" / db
    if _manifest_ready(repo_prefix):
        return str(repo_prefix)
    fallback = _absolute_work_root(values)
    if fallback is not None:
        return str(fallback / "blastdb" / db)
    return f"blastdb/{db}"
