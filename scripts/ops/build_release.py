#!/usr/bin/env python3
"""Build verified source archives from a clean Git checkout, without local data."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import tarfile
import time
import tomllib
import zipfile


MANIFEST = 'SOURCE_MANIFEST.sha256'
SAFE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+-]*\Z')


def unix_time_extra(epoch: int) -> bytes:
    """Info-ZIP UT extra field so unzip keeps the commit time, not the DOS clock."""
    payload = bytes([1]) + struct.pack('<I', epoch & 0xFFFFFFFF)
    return struct.pack('<HH', 0x5455, len(payload)) + payload


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '-c', 'core.autocrlf=true', *args], cwd=root)


def build_release(root: Path, output: Path, name: str | None = None) -> dict:
    root, output = root.resolve(), output.resolve()
    version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    release = json.loads((root / 'RELEASE.json').read_text(encoding='utf-8'))
    if release['software_version'] != version:
        raise ValueError('pyproject.toml and RELEASE.json have different software versions')
    name = name or f'Gene-In-{version}'
    if not SAFE_NAME.fullmatch(name):
        raise ValueError('archive name must contain only letters, numbers, dots, +, _ and -')
    if git(root, 'status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('commit tracked changes before building a release')
    sha = git(root, 'rev-parse', 'HEAD').decode().strip()
    epoch = int(git(root, 'show', '-s', '--format=%ct', 'HEAD'))
    entries = []
    for record in git(root, 'ls-files', '--stage', '-z').split(b'\0'):
        if not record:
            continue
        metadata, raw_path = record.split(b'\t', 1)
        mode, _, stage = metadata.decode().split()
        rel = raw_path.decode('utf-8')
        if mode not in ('100644', '100755') or stage != '0':
            raise ValueError(f'unsupported Git entry: {rel}')
        path = root / rel
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f'not a regular source file: {rel}')
        if rel == MANIFEST or rel.startswith('docs/desenvolvimento/'):
            # A tracked snapshot of an earlier package is not the manifest of
            # this archive. The archive writes a fresh manifest below.
            continue
        data = path.read_bytes()
        # Zip extraction on Windows can lose execute bits. Preserve all nested
        # shell entry points in both archives, including scripts added later.
        permission = 0o755 if mode == '100755' or rel.endswith('.sh') else 0o644
        entries.append((rel, data, permission))
    entries = [entry for entry in entries if entry[0] != 'SOURCE_COMMIT']
    entries.append(('SOURCE_COMMIT', (sha + '\n').encode(), 0o644))
    entries.sort(key=lambda e: e[0])
    manifest = ''.join(f'{hashlib.sha256(data).hexdigest()}  {rel}\n' for rel, data, _ in entries).encode()
    entries.append((MANIFEST, manifest, 0o644))
    output.mkdir(parents=True, exist_ok=True)
    zip_path = output / (name + '.zip')
    tar_path = output / (name + '.tar.gz')
    # Refuse replacement: previous deliveries and their evidence remain intact.
    for path in (zip_path, tar_path, output / 'archive-release.json', output / 'SHA256SUMS',
                 Path(str(zip_path) + '.sha256'), Path(str(tar_path) + '.sha256')):
        if path.exists():
            raise FileExistsError(f'output already exists: {path}; choose a new output directory')
    stamp = time.gmtime(max(epoch, 315532800))[:6]
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel, data, mode in entries:
            item = zipfile.ZipInfo(name + '/' + rel, date_time=stamp)
            item.create_system = 3
            item.external_attr = (0o100000 | mode) << 16
            item.extra = unix_time_extra(epoch)
            archive.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with tar_path.open('wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=epoch) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as archive:
                for rel, data, mode in entries:
                    item = tarfile.TarInfo(name + '/' + rel)
                    item.size, item.mode, item.mtime = len(data), mode, epoch
                    archive.addfile(item, io.BytesIO(data))
    expected = {name + '/' + rel: hashlib.sha256(data).hexdigest() for rel, data, _ in entries}
    with zipfile.ZipFile(zip_path) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(expected):
            raise ValueError('ZIP member or CRC verification failed')
        for member, digest in expected.items():
            if hashlib.sha256(archive.read(member)).hexdigest() != digest:
                raise ValueError(f'ZIP digest mismatch: {member}')
    with tarfile.open(tar_path) as archive:
        if set(archive.getnames()) != set(expected):
            raise ValueError('tar member verification failed')
        for member in archive:
            if hashlib.sha256(archive.extractfile(member).read()).hexdigest() != expected[member.name]:
                raise ValueError(f'tar digest mismatch: {member.name}')
    # Refuse a package if source content changed while it was being archived.
    for rel, data, _ in entries:
        if rel in {MANIFEST, 'SOURCE_COMMIT'}:
            continue
        if (root / rel).read_bytes() != data:
            raise ValueError(f'source changed during packaging: {rel}')
    if git(root, 'rev-parse', 'HEAD').decode().strip() != sha or git(root, 'status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('source checkout changed during packaging')
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (zip_path, tar_path)}
    for file, digest in hashes.items():
        (output / (file + '.sha256')).write_text(f'{digest}  {file}\n', encoding='utf-8')
    record = {**release, 'source_commit': sha, 'source_archive_name': zip_path.name,
              'source_archive_sha256': hashes[zip_path.name], 'archives': hashes,
              'source_files': len(entries) - 1, 'manifest': MANIFEST,
              'verification': 'ZIP CRC and SHA-256 of every ZIP/tar member verified'}
    (output / 'SHA256SUMS').write_text(''.join(f'{digest}  {file}\n' for file, digest in hashes.items()), encoding='utf-8')
    (output / 'archive-release.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--name')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    try:
        record = build_release(root, args.output_dir or root / 'dist', args.name)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'[ERRO] {exc}\n')
    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
