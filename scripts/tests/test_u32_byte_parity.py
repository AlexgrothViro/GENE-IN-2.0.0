from scripts.dashboard.jobs import build_command


def test_two_runs_cannot_share_work_outputs():
    params = {'sample': 'SAMPLE', 'db': 'ptv', 'assembler': 'consensus', 'host_filter_mode': 'none'}
    first, a = build_command('evidence_pipeline', dict(params, run_id='first-run-00001'))
    second, b = build_command('evidence_pipeline', dict(params, run_id='second-run-00001'))
    assert a['GENEIN_WORK_ROOT'] != b['GENEIN_WORK_ROOT']
    assert first == second
    # Identical processing arguments/input paths; only run/output identity differs.
    scientific_a = {k: v for k, v in a.items() if k not in ('GENEIN_WORK_ROOT', 'EVIDENCE_RUN_ID')}
    scientific_b = {k: v for k, v in b.items() if k not in ('GENEIN_WORK_ROOT', 'EVIDENCE_RUN_ID')}
    assert repr(scientific_a).encode() == repr(scientific_b).encode()
