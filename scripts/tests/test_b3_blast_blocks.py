"""Real BLAST equivalence against the frozen b2 router, including provenance."""
import importlib.machinery
import importlib.util
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/evidence'))
import blast_router as current
from activation_policy import load_public_activation_policy


@pytest.mark.parametrize('block_size,repeats', [(3, 3), (256, 50)])
def test_short_blocks_match_b2_bytes(tmp_path, monkeypatch, block_size, repeats):
    if not shutil.which('blastn'):
        pytest.skip('BLAST real ausente')
    loader = importlib.machinery.SourceFileLoader('b2_router', str(ROOT / 'scripts/tests/fixtures/b2_blast_router.py.txt'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    old = importlib.util.module_from_spec(spec)
    loader.exec_module(old)
    rng = random.Random(20261009)
    sequence = ''.join(rng.choice('ACGT') for _ in range(800))
    db = tmp_path / 'panel'
    fasta = tmp_path / 'db.fa'
    fasta.write_text(f'>a\n{sequence}\n>b\n{sequence}\n')
    subprocess.run(['makeblastdb', '-in', str(fasta), '-out', str(db), '-dbtype', 'nucl'], check=True, capture_output=True)
    query = tmp_path / 'queries.fa'
    query.write_text(''.join(f'>q{i}\n{sequence[i % 300:i % 300+n]}\n' for i, n in enumerate([20, 29, 30, 39, 40, 59, 60, 99, 100, 101, 200] * repeats)) + '>nohit\nNNNNNNNNNNNNNNNNNNNN\n')
    config = load_public_activation_policy(str(ROOT/'config/evidence_activation.json'), profiles_path=str(ROOT/'config/evidence_profiles.json'))['thresholds']
    monkeypatch.setattr(current, 'SHORT_QUERY_BLOCK_SIZE', block_size)
    for recover in (False, True):
        for threads in (1, 2):
            outputs = [tmp_path / name for name in ('short.tsv', 'conventional.tsv', 'combined.tsv')]
            before_meta = old.run_router(str(query), str(db), config, threads, *outputs, recover)
            before = [p.read_bytes() for p in outputs]
            after_meta = current.run_router(str(query), str(db), config, threads, *outputs, recover)
            assert before == [p.read_bytes() for p in outputs]
            assert before_meta == after_meta
