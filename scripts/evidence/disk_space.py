"""Free-space checks for evidence steps that spill to the run directory."""
from __future__ import annotations

import shutil
from pathlib import Path


class EvidenceDiskError(RuntimeError):
    """Free space is below the estimate for an evidence step."""


_GIB = 1024 ** 3
FLOOR = 512 * 1024 * 1024


def format_gib(value: int) -> str:
    return f"{value / _GIB:.1f}".replace(".", ",") + " GiB"


def require_free(directory: Path, required: int, step: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(directory).free
    if free < required:
        raise EvidenceDiskError(
            f"Espaço livre insuficiente para {step}. "
            f"Estimativa desta etapa: {format_gib(required)}. "
            f"Espaço livre em {directory}: {format_gib(free)}. "
            "Libere espaço em disco e execute novamente."
        )


def guard_floor(directory: Path, step: str) -> None:
    free = shutil.disk_usage(directory).free
    if free < FLOOR:
        raise EvidenceDiskError(
            f"Espaço livre insuficiente durante {step}. "
            f"Espaço livre em {directory}: {format_gib(free)}. "
            "A etapa foi interrompida antes de encher o disco."
        )


def require_step_space(
    work_dir: Path,
    output_dir: Path,
    work_bytes: int,
    output_bytes: int,
    step: str,
) -> None:
    """Reserve spill space and output space, splitting the check across devices."""
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    same_device = work_dir.stat().st_dev == output_dir.stat().st_dev
    if same_device:
        require_free(work_dir, work_bytes + output_bytes, step)
        return
    require_free(work_dir, work_bytes, step)
    require_free(output_dir, output_bytes, step)
