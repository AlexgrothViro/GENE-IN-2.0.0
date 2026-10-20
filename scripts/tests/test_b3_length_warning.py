import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/evidence'))
from common import sha256_text
from export_candidate_sequences import export


def test_length_warning_preserves_exports(tmp_path, capsys):
    query, manifest, fragments = [tmp_path/name for name in ('q.fa', 'q.json', 'f.tsv')]
    query.write_text('>long_contig\n' + 'ACGT'*100 + '\n')
    manifest.write_text(json.dumps({'queries': {'long_contig': {'sequence_sha256': sha256_text('ACGT'*100), 'source_counts': {'contig': 1}}}}))
    header = 'qseqid\tsseqid\tquery_covered_bp\tslen\n'
    fragments.write_text(header + 'long_contig\tref\t40\t1000\n')
    out = tmp_path/'out'
    export(query, manifest, fragments, out)
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    assert not capsys.readouterr().err
    fragments.write_text(header + 'long_contig\tref\t40\t100\n')
    export(query, manifest, fragments, out)
    assert 'long_contig: 400 pb' in capsys.readouterr().err
    assert before == {p.name: p.read_bytes() for p in out.iterdir()}
