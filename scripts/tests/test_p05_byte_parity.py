import hashlib
import json
import pytest
from scripts.evidence.verify_blast_database_manifest import verify


def test_verification_preserves_database_bytes_and_rejects_tampering(tmp_path):
    prefix = tmp_path / 'panel'
    index = tmp_path / 'panel.nsq'
    index.write_bytes(b'recorded index')
    manifest = tmp_path / 'panel.db-manifest.json'
    manifest.write_text(json.dumps({'schema_version': '1.0', 'produced_files': {
        index.name: {'size': index.stat().st_size, 'sha256': hashlib.sha256(index.read_bytes()).hexdigest()}}}))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert verify(prefix) == 1
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    index.write_bytes(b'X' + index.read_bytes()[1:])
    with pytest.raises(ValueError, match='alterado'):
        verify(prefix)
