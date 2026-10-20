import json
from types import SimpleNamespace
from unittest.mock import patch
from scripts.dashboard import jobs


def test_history_reads_preserved_configuration_without_rewriting_it(tmp_path):
    state = tmp_path / 'results/evidence/state/run-original.json'
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({'run_id': 'run-original', 'sample_ids': ['SAMPLE'], 'status': 'failed'}))
    snapshot = tmp_path / 'results/runs/run-original'
    snapshot.mkdir(parents=True)
    config = snapshot / 'resolved_config.json'
    config.write_bytes(b'{"db":"ptv","assembler":"consensus","qc_adapter_r1":"ACGT","host_filter_enabled":"false"}\n')
    before_state, before_config = state.read_bytes(), config.read_bytes()
    inspection = {'status': 'INCOMPLETE', 'valid_alpha2': False, 'complete': False, 'message': 'incompleto'}
    service = SimpleNamespace(evidence_root=state.parent.parent, inspect_run=lambda _: inspection)
    with patch.object(jobs, 'get_repo_root', return_value=tmp_path), patch.object(jobs, 'get_runs_dir', return_value=snapshot.parent), patch.object(jobs, 'EVIDENCE_SERVICE', service), patch.object(jobs, 'load_config_env', side_effect=AssertionError('must not read current global configuration')):
        history = jobs.list_run_history()
    assert history[0]['effective_config']['qc_adapter_r1'] == 'ACGT'
    assert state.read_bytes() == before_state
    assert config.read_bytes() == before_config
