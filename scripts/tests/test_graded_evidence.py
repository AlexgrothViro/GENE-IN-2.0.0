import pytest
from scripts.evidence.graded_evidence import canonical_level, grade, negative_reference_support, render_grades


def test_grades_require_competition_and_measured_independent_support():
    candidate = {'reference_id': 'r'}
    assert grade(candidate)['level'] == 'SINAL_POR_SIMILARIDADE'
    assert grade(candidate)['tie'] is None
    candidate.update(specificity_status='TARGET_SPECIFIC', taxonomic_status='PANEL_TAXON_PREFERRED')
    assert grade(candidate)['level'] == 'ATRIBUIDO_A_REFERENCIA'
    candidate['support'] = {'status': 'NOT_EVALUATED', 'unique_templates': None, 'distinct_starts': None}
    assert grade(candidate)['level'] == 'ATRIBUIDO_A_REFERENCIA'
    candidate['support'] = {'status': 'SUPPORT_AVAILABLE', 'unique_templates': 2, 'distinct_starts': 2}
    assert grade(candidate)['level'] == 'SUPORTADO_POR_READS'
    candidate['taxonomic_status'] = 'AMBIGUOUS'
    assert grade(candidate)['tie'] and grade(candidate)['level'] == 'SINAL_POR_SIMILARIDADE'


def test_confirmation_requires_record_and_never_appears_automatically():
    candidate = {'reference_id': 'r'}
    with pytest.raises(ValueError):
        grade(candidate, {'method': 'PCR'})
    record = dict(reference_id='r', method='PCR', record_id='test-only', recorded_by='test', recorded_at='2026-11-09')
    assert grade(candidate, record)['level'] == 'CONFIRMACAO_EXTERNA_REGISTRADA'
    assert canonical_level('CONFIRMADO_EXTERNAMENTE') == 'CONFIRMACAO_EXTERNA_REGISTRADA'
    assert grade(candidate)['external_confirmation'] is None
    assert 'SEM_SINAL_RECUPERADO' in render_grades({'candidates': []})


def test_report_collapses_similarity_and_uses_measured_support_from_the_same_reference():
    supported = {
        'reference_id': 'ref', 'specificity_status': 'TARGET_SPECIFIC',
        'taxonomic_status': 'PANEL_TAXON_PREFERRED',
        'support': {'status': 'SUPPORT_AVAILABLE', 'unique_templates': 3, 'distinct_starts': 6},
        'coverage': {'breadth_1x': .8, 'breadth_3x': 0},
    }
    similarity = {'reference_id': 'other'}
    negative = negative_reference_support([{'candidates': [
        {'reference_id': 'ref', 'support': {'status': 'SUPPORT_AVAILABLE', 'unique_templates': 2}},
        {'reference_id': 'ref', 'support': {'status': 'SUPPORT_AVAILABLE', 'unique_templates': 4}},
        {'reference_id': 'other', 'support': {'status': 'SUPPORT_AVAILABLE', 'unique_templates': 9}},
    ]}])
    report = render_grades({'candidates': [supported, similarity]}, negative_support=negative,
                           control_metrics={'target': 'missing', 'sample_rpm': 'NA'})
    main, collapsed = report.split('<details>')
    assert '| ref | SUPORTADO_POR_READS | 3 | 6 | 80.00% | 0.00% |' in main
    assert '4 templates' in main and '9 templates' not in main
    assert 'SINA' not in main and 'Sinais por similaridade nesta amostra: 1' in main
    assert '| other | SINAL_POR_SIMILARIDADE | NA | NA |' in collapsed
    assert 'também no controle negativo' in collapsed
    assert 'NA (sem correspondência do alvo por accession ou rótulo)' in report
    assert 'suporte sem controle negativo no lote' in render_grades({'candidates': [supported]})
