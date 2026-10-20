"""External sort of text lines.

Runs stay in the caller-supplied directory. Reduction deletes a batch after
its merged run is written, so the extra space stays near one copy of the
lines rather than a second full copy.
"""
from __future__ import annotations

import heapq
from pathlib import Path


FANOUT = 64


def _normalize(line: str) -> str:
    return line if line.endswith("\n") else line + "\n"


def write_sorted_chunk(lines: list[str], path: Path, key_fn) -> None:
    ordered = sorted(lines, key=key_fn)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.writelines(_normalize(line) for line in ordered)


def merge_runs(paths: list[Path], dest: Path, key_fn) -> None:
    handles = [path.open("r", encoding="utf-8", newline="") for path in paths]
    try:
        with dest.open("w", encoding="utf-8", newline="\n") as output:
            for line in heapq.merge(*handles, key=key_fn):
                output.write(_normalize(line))
    finally:
        for handle in handles:
            handle.close()


def reduce_runs(paths: list[Path], directory: Path, prefix: str, key_fn, guard=None) -> list[Path]:
    """Merge until at most FANOUT runs remain."""
    pending = list(paths)
    generation = 0
    while len(pending) > FANOUT:
        generation += 1
        reduced: list[Path] = []
        for index in range(0, len(pending), FANOUT):
            batch = pending[index:index + FANOUT]
            if len(batch) == 1:
                reduced.append(batch[0])
                continue
            dest = directory / f"{prefix}-m{generation}-{len(reduced):05d}.tsv"
            merge_runs(batch, dest, key_fn)
            for path in batch:
                path.unlink(missing_ok=True)
            reduced.append(dest)
            if guard is not None:
                guard()
        pending = reduced
    return pending


def iter_merged(paths: list[Path], key_fn):
    if not paths:
        yield from ()
        return
    handles = [path.open("r", encoding="utf-8", newline="") for path in paths]
    try:
        yield from heapq.merge(*handles, key=key_fn)
    finally:
        for handle in handles:
            handle.close()


class LineSorter:
    """Collect lines, flush sorted chunks, and return a bounded set of runs."""

    def __init__(self, directory: Path, prefix: str, key_fn, guard=None, chunk_lines: int = 8000):
        self.directory = directory
        self.prefix = prefix
        self.key_fn = key_fn
        self.guard = guard
        self.chunk_lines = chunk_lines
        self.buffer: list[str] = []
        self.runs: list[Path] = []

    def add(self, line: str) -> None:
        self.buffer.append(line)
        if len(self.buffer) >= self.chunk_lines:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return
        path = self.directory / f"{self.prefix}-{len(self.runs):05d}.tsv"
        write_sorted_chunk(self.buffer, path, self.key_fn)
        self.runs.append(path)
        self.buffer.clear()
        if self.guard is not None:
            self.guard()

    def finish(self) -> list[Path]:
        self.flush()
        self.runs = reduce_runs(self.runs, self.directory, self.prefix, self.key_fn, self.guard)
        return self.runs
