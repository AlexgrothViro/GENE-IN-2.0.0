#!/usr/bin/env python3
"""Validation helpers shared by the CLI and the local dashboard.

The pipeline writes user-controlled sample identifiers into filenames.  Keep
the validation in one place so the dashboard and shell entry points enforce
the same contract.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path
from typing import Iterator, TextIO


SAMPLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{7,127}$")
BATCH_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
FASTQ_SUFFIXES = (".fastq", ".fastq.gz", ".fq", ".fq.gz")
CORRUPT_FASTQ = (
    "Arquivo FASTQ parece corrompido ou ilegível (gzip/UTF-8). "
    "Reimporte o FASTQ original completo. / "
    "File looks corrupt or unreadable (gzip/UTF-8). Re-import the complete original FASTQ."
)


def validate_sample_id(value: str) -> str:
    value = (value or "").strip()
    if not SAMPLE_RE.fullmatch(value):
        raise ValueError(
            "identificador de amostra invalido: use 1-80 caracteres "
            "alfanumericos, '.', '_' ou '-'; o primeiro deve ser alfanumerico"
        )
    return value


def validate_run_id(value: str) -> str:
    value = (value or "").strip()
    if not RUN_ID_RE.fullmatch(value):
        raise ValueError(
            "run_id invalido: use 8-128 caracteres ASCII alfanumericos, "
            "'.', '_' ou '-'; o primeiro deve ser alfanumerico"
        )
    return value


def validate_batch_id(value: str) -> str:
    value = (value or "").strip()
    if not BATCH_ID_RE.fullmatch(value):
        raise ValueError(
            "batch_id invalido: use 1-80 caracteres ASCII alfanumericos, "
            "'.', '_' ou '-'; o primeiro deve ser alfanumerico"
        )
    return value


def _open_text(path: Path) -> TextIO:
    if str(path).lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="strict")
    return path.open("r", encoding="utf-8", errors="strict")


def _corrupt_fastq(path: Path) -> ValueError:
    return ValueError(f"{CORRUPT_FASTQ} ({path})")


def _read_fastq_record(handle: TextIO, path: Path, record_no: int):
    lines = [handle.readline() for _ in range(4)]
    if not any(lines):
        return None
    if any(line == "" for line in lines):
        raise ValueError(f"FASTQ truncado em {path}, registro {record_no}. Importe novamente o arquivo original completo.")
    header, sequence, plus, quality = [line.rstrip("\r\n") for line in lines]
    if not header.startswith("@"):
        raise ValueError(f"FASTQ inválido em {path}, registro {record_no}: cabeçalho deve iniciar com '@'. Corrija o registro ou importe novamente o FASTQ original.")
    if not plus.startswith("+"):
        raise ValueError(f"FASTQ inválido em {path}, registro {record_no}: terceira linha deve iniciar com '+'. Corrija o registro ou importe novamente o FASTQ original.")
    if not sequence:
        raise ValueError(f"Sequência vazia em {path}, registro {record_no}. Corrija o registro ou importe novamente o FASTQ original.")
    if len(sequence) != len(quality):
        raise ValueError(f"Sequência/qualidade com tamanhos diferentes em {path}, registro {record_no}. Corrija o registro ou importe novamente o FASTQ original.")
    return header[1:].split()[0], sequence


def _pair_id(value: str) -> str:
    return re.sub(r"(?:[/._][12])$", "", value)


def iter_fastq(path: Path) -> Iterator[tuple[str, str]]:
    """Stream validated reads, including gzip and an empty post-filter file."""
    try:
        with _open_text(path) as handle:
            record_no = 1
            while True:
                record = _read_fastq_record(handle, path, record_no)
                if record is None:
                    return
                yield record
                record_no += 1
    except (UnicodeDecodeError, EOFError, OSError) as exc:
        raise _corrupt_fastq(path) from exc


def validate_fastq(path: Path, mate: Path | None = None) -> int:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"FASTQ ausente ou vazio: {path}")
    if mate is not None and (not mate.is_file() or mate.stat().st_size == 0):
        raise ValueError(f"FASTQ mate ausente ou vazio: {mate}")

    count = 0
    try:
        with _open_text(path) as first:
            second = _open_text(mate) if mate is not None else None
            try:
                while True:
                    left = _read_fastq_record(first, path, count + 1)
                    if second is None:
                        if left is None:
                            break
                        count += 1
                        continue
                    right = _read_fastq_record(second, mate, count + 1)
                    if left is None and right is None:
                        break
                    if left is None or right is None:
                        raise ValueError(f"FASTQ pareado com numero de reads diferente: {path} / {mate}")
                    if right is not None and _pair_id(left[0]) != _pair_id(right[0]):
                        raise ValueError(
                            f"IDs de reads nao pareados no registro {count + 1}: "
                            f"{left[0]} != {right[0]}"
                        )
                    count += 1
            finally:
                if second is not None:
                    second.close()
    except (UnicodeDecodeError, EOFError, OSError) as exc:
        raise _corrupt_fastq(path) from exc
    if count == 0:
        raise ValueError(f"FASTQ sem registros: {path}")
    return count


def validate_fastp_json(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"relatorio JSON do fastp ausente ou vazio: {path}")
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        document = json.load(handle)
    summary = document.get("summary")
    if not isinstance(summary, dict):
        raise ValueError(f"relatorio JSON do fastp sem summary valido: {path}")
    for phase in ("before_filtering", "after_filtering"):
        metrics = summary.get(phase)
        if not isinstance(metrics, dict):
            raise ValueError(f"relatorio JSON do fastp sem summary.{phase}: {path}")
        for field in ("total_reads", "total_bases"):
            value = metrics.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(
                    f"relatorio JSON do fastp com {phase}.{field} invalido: {path}"
                )
    return document


def iter_fasta(path: Path) -> Iterator[tuple[str, str]]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"FASTA ausente ou vazio: {path}")
    name = None
    sequence: list[str] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        for line_no, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name is not None:
                    yield name, "".join(sequence)
                name = line[1:].split()[0]
                if not name or name in seen:
                    raise ValueError(f"header FASTA ausente ou duplicado em {path}, linha {line_no}")
                seen.add(name)
                sequence = []
            else:
                if name is None:
                    raise ValueError(f"sequencia FASTA antes do primeiro header em {path}, linha {line_no}")
                if not re.fullmatch(r"[A-Za-z*.-]+", line):
                    raise ValueError(f"caracter invalido em FASTA {path}, linha {line_no}")
                sequence.append(line)
    if name is None or not sequence:
        raise ValueError(f"FASTA sem sequencias validas: {path}")
    yield name, "".join(sequence)


def validate_fasta(path: Path) -> int:
    count = 0
    for _, sequence in iter_fasta(path):
        if not sequence:
            raise ValueError(f"sequencia FASTA vazia: {path}")
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("value")
    run_id = sub.add_parser("run-id")
    run_id.add_argument("value")
    batch_id = sub.add_parser("batch-id")
    batch_id.add_argument("value")
    fastq = sub.add_parser("fastq")
    fastq.add_argument("path", type=Path)
    fastq.add_argument("--mate", type=Path)
    fastp_json = sub.add_parser("fastp-json")
    fastp_json.add_argument("path", type=Path)
    fasta = sub.add_parser("fasta")
    fasta.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "sample":
            print(validate_sample_id(args.value))
        elif args.command == "run-id":
            print(validate_run_id(args.value))
        elif args.command == "batch-id":
            print(validate_batch_id(args.value))
        elif args.command == "fastq":
            print(validate_fastq(args.path, args.mate))
        elif args.command == "fastp-json":
            validate_fastp_json(args.path)
            print(args.path)
        else:
            print(validate_fasta(args.path))
        return 0
    except (OSError, ValueError) as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
