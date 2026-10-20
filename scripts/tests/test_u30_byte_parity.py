import json
from unittest import mock
from pathlib import Path
from scripts.dashboard.jobs import build_command
from scripts.dashboard import jobs


def test_role_metadata_does_not_change_processing_command():
    params = {'sample': 'SAMPLE', 'db': 'ptv', 'assembler': 'consensus', 'host_filter_mode': 'none'}
    before, env_before = build_command('evidence_pipeline', params)
    after, env_after = build_command('evidence_pipeline', dict(params, role='negative_library', batch_id='BATCH'))
    assert json.dumps(before).encode() == json.dumps(after).encode()
    assert env_after.pop('EVIDENCE_ROLE') == 'negative_library'
    assert env_after.pop('EVIDENCE_BATCH_ID') == 'BATCH'
    assert json.dumps(env_before).encode() == json.dumps(env_after).encode()


def test_declared_batch_matches_reserved_state():
    service = mock.Mock(evidence_root=Path('/tmp/evidence'))
    for batch_id in ('BATCH', None):
        params = {'sample': 'SAMPLE', 'run_id': 'dashboard-run-00000001'}
        if batch_id:
            params['batch_id'] = batch_id
        with mock.patch.object(jobs, 'get_evidence_service', return_value=service), mock.patch.object(jobs, 'reserve_evidence_state') as reserve:
            jobs.initialize_evidence_dashboard_state('evidence_pipeline', params)
        assert reserve.call_args.args[4] == batch_id
