import pytest
from scripts.dashboard.jobs import build_command


@pytest.mark.parametrize('target', [None, '', '   '])
def test_positive_rejected_before_submission(target):
    with pytest.raises(ValueError, match='Controle positivo exige um alvo esperado'):
        build_command('evidence_pipeline', dict(sample='TEST', db='ptv', host_filter_mode='none', role='positive', expected_target=target))


def test_positive_command_unchanged_with_target():
    params = dict(sample='TEST', db='ptv', host_filter_mode='none')
    before, env = build_command('evidence_pipeline', params)
    after, positive = build_command('evidence_pipeline', dict(params, role='positive', expected_target='PTV'))
    assert before == after
    assert positive.pop('EVIDENCE_ROLE') == 'positive'
    assert positive.pop('EVIDENCE_EXPECTED_TARGET') == 'PTV'
    assert env == positive
