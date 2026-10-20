import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/evidence'))
from common import sha256_text, write_tsv_atomic
from export_candidate_sequences import export
from validate_run_artifacts import validate_candidate_exports


def reference(name):
    loader = importlib.machinery.SourceFileLoader('b1_' + name, str(ROOT / 'scripts/tests/fixtures/b1_reference' / (name + '.py.txt')))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_exports_and_validation_match_b1_bytes(tmp_path):
    queries = tmp_path / 'queries.fa'
    queries.write_text('>q2\nACGT\n>q1\nAAAA\n')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'schema_version': '1.0', 'queries': {
        q: {'length_bp': 4, 'sequence_sha256': sha256_text(seq), 'source_counts': {'b': 2, 'a': 1}}
        for q, seq in [('q1', 'AAAA'), ('q2', 'ACGT')]}}))
    out = tmp_path / 'out'
    out.mkdir()
    fragments = out / 'fragment_evidence.tsv'
    fields = ['qseqid', 'sseqid', 'category', 'taxon', 'task', 'query_covered_bp', 'query_coverage',
              'weighted_pident', 'best_bitscore', 'best_evalue', 'assembly_method']
    rows = [dict(zip(fields, [q, 'subject', 'REVIEW', 'taxon', 'blastn-short', '4', '1', '95', '8', '1e-3', 'consensus']))
            for q in ['q2', 'q1', 'q2'] * 5000]
    write_tsv_atomic(fragments, rows, fields)
    original = reference('export_candidate_sequences')
    old_validator = reference('validate_run_artifacts').validate_candidate_exports
    names = ['candidate_sequences.fa', 'candidate_sequences.tsv', 'candidate_queries.json']
    original.export(queries, manifest, fragments, out)
    before = {name: (out / name).read_bytes() for name in names}
    export(queries, manifest, fragments, out)
    assert {name: (out / name).read_bytes() for name in names} == before
    assert validate_candidate_exports(out) == old_validator(out) == []
    table = out / 'candidate_sequences.tsv'
    valid = table.read_bytes()
    for changed in [valid.replace(b'REVIEW', b'STRONG', 1), valid.replace(b'\t4\t', b'\t5\t', 1),
                    b'\n'.join(valid.split(b'\n')[:-2]) + b'\n']:
        table.write_bytes(changed)
        assert validate_candidate_exports(out) == old_validator(out)
        assert validate_candidate_exports(out)
    table.write_bytes(valid)
