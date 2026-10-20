from pathlib import Path
import pytest
import argparse
from genein.pipeline.cli import register_commands, prepare


def test_composite_requires_manifest_before_output_creation(tmp_path):
    db = tmp_path / 'db'
    Path(str(db) + '.db-manifest.json').write_text('{}')
    contigs = tmp_path / 'contigs.fa'
    contigs.write_text('>a\nACGT\n')
    output = tmp_path / 'out'
    parser = argparse.ArgumentParser()
    register_commands(parser.add_subparsers(dest='command'))
    args = parser.parse_args(['run', '--sample', 'TEST', '--contigs', str(contigs), '--blast-db', str(db), '--composite-db', str(tmp_path/'missing'), '--output-root', str(output)])
    with pytest.raises(ValueError, match='Banco composto sem manifesto'):
        prepare(args, Path(__file__).resolve().parents[2])
    assert not output.exists()
