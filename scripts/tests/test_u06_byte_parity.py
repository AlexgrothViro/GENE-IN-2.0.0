import json
from unittest.mock import patch
import scripts.dashboard.jobs as jobs


def test_explicit_custom_host_and_saved_sus_index():
    params = {'sample': 'SAMPLE', 'db': 'ptv', 'assembler': 'consensus', 'host_filter_mode': 'none'}
    before = jobs.build_command('pipeline', params)
    with patch.object(jobs, 'load_config_env', return_value={'HOST_NAME': 'Other', 'HOST_INDEX_PREFIX': '/other'}):
        assert json.dumps(jobs.build_command('pipeline', params)).encode() == json.dumps(before).encode()
        _, env = jobs.build_command('pipeline', dict(params, host_filter_mode='sus_scrofa'))
        assert env['HOST_INDEX_PREFIX'] == str(jobs.REPO_ROOT / 'ref/host/sus_scrofa_bt2')
    with patch.object(jobs, 'load_config_env', return_value={'HOST_NAME': 'Sus scrofa', 'HOST_INDEX_PREFIX': '/saved/pig'}):
        cmd, env = jobs.build_command('pipeline', dict(params, host_filter_mode='sus_scrofa'))
        assert cmd == before[0]
        assert env['HOST_INDEX_PREFIX'] == '/saved/pig'
    _, custom = jobs.build_command('pipeline', dict(params, host_filter_mode='custom', host_name='Pig', host_index_prefix='/saved/pig'))
    assert custom['HOST_NAME'] == 'Pig'
    assert custom['HOST_INDEX_PREFIX'] == '/saved/pig'
