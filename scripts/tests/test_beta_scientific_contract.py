"""Release engineering must preserve the author's frozen b1 configuration bytes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_frozen_profiles_defaults_and_dependency_locks_match_b1_bytes():
    reference = ROOT / 'scripts/tests/fixtures/b1_reference/scientific_configuration_sha256.json'
    for relative, before_sha256 in json.loads(reference.read_text()).items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == before_sha256, relative


def test_experimental_parameters_preserved_across_metadata_organization():
    reference = ROOT / 'scripts/tests/fixtures/b1_reference/experimental_configuration_parameters.json'
    expected = json.loads(reference.read_text())
    assert len(expected) == 9
    for relative, before in expected.items():
        current = json.loads((ROOT / relative).read_text())
        for metadata in ('schema_version', '$id', 'title'):
            current.pop(metadata, None)
        assert current == before, relative
