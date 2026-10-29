"""Distribution 2.0.1 parity and bounded per-hit state in the memory port."""
import csv
import hashlib
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/evidence'))
from blast_router import deduplicate_combined_files
from export_candidate_sequences import _best_hit_rows, _builder_short, export
import validate_run_artifacts as validator


def reference_summary(rows, catalog):
    """The 2.0.1 list/min rule, independent of the streaming accumulator."""
    groups = {}
    for row in rows:
        groups.setdefault(row['qseqid'], []).append(row)

    def number(row, key, default):
        try:
            return float(row.get(key) or '')
        except (TypeError, ValueError):
            return default

    output = []
    for group in groups.values():
        best = dict(min(group, key=lambda row: (
            -number(row, 'best_bitscore', float('-inf')),
            number(row, 'best_evalue', float('inf')),
            -number(row, 'weighted_pident', float('-inf')),
            str(row.get('sseqid', '')), str(row.get('task', '')))))
        minimum, text = None, ''
        for row in group:
            value = number(row, 'best_evalue', float('inf'))
            if math.isfinite(value) and (minimum is None or value < minimum):
                minimum, text = value, str(row.get('best_evalue', ''))
        description, taxon = catalog.get(best['sseqid'], ('', ''))
        if not best.get('taxon') and taxon:
            best['taxon'] = taxon
        short = _builder_short(best)
        output.append({**best, 'reference_description': description,
                       'min_evalue': text, 'hit_row_count': str(len(group)),
                       'fragmento_curto': 'true' if short else 'false',
                       'rotulo': 'REVIEW' if short else 'CANDIDATO'})
    return output


def test_streaming_summary_keeps_2_0_1_order_ties_and_minimum():
    rng = random.Random(20261022)
    rows = [{'qseqid': f'q{rng.randrange(17)}', 'sseqid': f's{rng.randrange(5)}',
             'best_bitscore': rng.choice(['50', '10', '50.0', 'bad', '']),
             'best_evalue': rng.choice(['1e-8', '1e-20', '1e-2', 'nan', 'inf', '']),
             'weighted_pident': rng.choice(['90', '99', 'bad', '']),
             'taxon': '', 'task': rng.choice(['blastn', 'blastn-short']),
             'assembly_method': str(i)} for i in range(3000)]
    # Equal complete rank retains the first row, including its metadata.
    tie = dict(rows[0], assembly_method='later equal rank')
    rows.insert(1, tie)
    catalog = {'s1': ('Reference alpha strain X', 'Reference alpha')}
    assert _best_hit_rows(iter(rows), catalog) == reference_summary(rows, catalog)
    assert _best_hit_rows(iter([]), catalog) == []


def tracking_row_type(counter, limit):
    class TrackedRow(dict):
        def __init__(self, row):
            super().__init__(row)
            counter[0] += 1
            counter[1] = max(counter[1], counter[0])
            assert counter[0] <= limit, 'per-hit dictionaries retained in memory'

        def __del__(self):
            counter[0] -= 1
    return TrackedRow


def test_summary_releases_rows_instead_of_retaining_every_hit():
    counter = [0, 0]
    tracked = tracking_row_type(counter, 8)

    def rows():
        for i in range(6000):
            yield tracked({'qseqid': f'q{i % 3}', 'sseqid': 's', 'task': 'blastn',
                           'best_bitscore': str(i), 'best_evalue': '1e-8',
                           'weighted_pident': '99', 'taxon': ''})
    result = _best_hit_rows(rows())
    assert [row['hit_row_count'] for row in result] == ['2000'] * 3
    assert counter[1] <= 8


def test_validator_streams_full_table_when_checking_summary(tmp_path, monkeypatch):
    sequence = 'ACGT' * 5
    queries = tmp_path / 'queries.fa'
    queries.write_text(''.join(f'>q{i}\n{sequence}\n' for i in range(3)))
    manifest = tmp_path / 'queries.json'
    manifest.write_text(json.dumps({'schema_version': '1.0', 'queries': {
        f'q{i}': {'length_bp': 20, 'sequence_sha256': hashlib.sha256(sequence.encode()).hexdigest(),
                 'source_counts': {'short_read': 1}} for i in range(3)}}))
    fragments = tmp_path / 'fragment_evidence.tsv'
    with fragments.open('w', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t', lineterminator='\n')
        writer.writerow(['qseqid', 'sseqid', 'taxon', 'category', 'task', 'query_covered_bp',
                         'query_coverage', 'weighted_pident', 'best_bitscore', 'best_evalue', 'assembly_method'])
        for i in range(6000):
            writer.writerow([f'q{i % 3}', 's', '', 'UNLABELED', 'blastn-short', 20, 1, 99, i, '1e-8', 'read_level'])
    export(queries, manifest, fragments, tmp_path)
    reader = validator.iter_tsv
    counter = [0, 0]
    tracked = tracking_row_type(counter, 10)

    def observed(path):
        for row in reader(path):
            yield tracked(row) if Path(path).name == 'candidate_sequences.tsv' else row
    monkeypatch.setattr(validator, 'iter_tsv', observed)
    assert validator.validate_candidate_exports(tmp_path) == []
    assert counter[1] <= 10


def test_disk_merge_handles_interleaved_and_unlisted_query_ids(tmp_path, monkeypatch):
    def line(query, bits):
        return f'{query}\ts\t95\t20\t1\t0\t1\t20\t10\t29\t1e-8\t{bits}\t20\t100\t19\t0\n'
    a, b = tmp_path / 'a.tsv', tmp_path / 'b.tsv'
    a.write_text(line('q1', 10) + line('q3', 30) + line('q1', 20))
    b.write_text(line('q2', 40) + line('q1', 80))
    original_read_text = Path.read_text

    def forbid_raw_load(path, *args, **kwargs):
        assert path not in (a, b), 'raw BLAST table was read as a complete string'
        return original_read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', forbid_raw_load)
    output = tmp_path / 'out.tsv'
    deduplicate_combined_files([a, b], ['q1'], output)
    assert output.read_text() == line('q1', 80) + line('q3', 30) + line('q2', 40)
