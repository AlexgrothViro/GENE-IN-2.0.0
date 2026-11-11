"""Reporting interpretation over recorded evidence and optional batch controls."""
from __future__ import annotations

LEVELS = ('SINAL_POR_SIMILARIDADE', 'ATRIBUIDO_A_REFERENCIA',
          'SUPORTADO_POR_READS', 'CONFIRMACAO_EXTERNA_REGISTRADA')
REVISION = 'desktop_graded_evidence_v2'
SHORT_NOTE = ('o modo curto recupera similaridade casual; amostras sem alvo deste '
              'ensaio produziram centenas de sinais deste nível')
SUPPORT_NOTE = ('2 templates e 2 inícios distintos são uma convenção interna '
                'de suporte, não um limiar de presença.')
CONTROL_NOTE = ('O numerador do RPM é o máximo de templates por locus do alvo. '
                'Ele não quantifica o total viral. Sem correspondência por accession '
                'ou rótulo exato, o suporte do alvo fica como NA.')


def canonical_level(level: str) -> str:
    return LEVELS[3] if level == 'CONFIRMADO_EXTERNAMENTE' else level


def negative_reference_support(samples) -> dict | None:
    references = None
    for sample in samples:
        if references is None:
            references = {}
        for candidate in sample['candidates']:
            ref = candidate['reference_id']
            references.setdefault(ref, None)
            support = candidate.get('support', {})
            templates = support.get('unique_templates')
            if support.get('status') == 'SUPPORT_AVAILABLE' and templates is not None:
                previous = references[ref]
                references[ref] = templates if previous is None else max(previous, templates)
    return references


def grade(candidate: dict, confirmation: dict | None = None, *, negative_support=None) -> dict:
    specificity = candidate.get('specificity_status', 'NOT_EVALUATED')
    taxonomy = candidate.get('taxonomic_status', 'NOT_EVALUATED')
    tie = (None if specificity == 'NOT_EVALUATED' and taxonomy == 'NOT_EVALUATED'
           else specificity == 'AMBIGUOUS' or taxonomy == 'AMBIGUOUS')
    reference = candidate.get('reference_id')
    support = candidate.get('support', {})
    coverage = candidate.get('coverage', {})
    templates, starts = support.get('unique_templates'), support.get('distinct_starts')
    level = LEVELS[0]
    reasons = ['Alinhamento recuperado. Atribuição limitada ao banco consultado.']
    if specificity == 'TARGET_SPECIFIC' and taxonomy == 'PANEL_TAXON_PREFERRED' and not tie:
        level = LEVELS[1]
        reasons.append('Referência preferida na comparação competitiva rotulada.')
        if (support.get('status') == 'SUPPORT_AVAILABLE'
                and templates is not None and starts is not None and templates >= 2 and starts >= 2):
            level = LEVELS[2]
            reasons.append('Pelo menos 2 templates e 2 inícios distintos medidos por remapeamento.')
    read_supported = level == LEVELS[2]
    external = None
    if confirmation is not None:
        required = ('reference_id', 'method', 'record_id', 'recorded_by', 'recorded_at')
        if (any(not isinstance(confirmation.get(k), str) or not confirmation[k].strip() for k in required)
                or confirmation['method'] not in ('PCR', 'SEQUENCIAMENTO')
                or confirmation['reference_id'] != reference):
            raise ValueError('Confirmação externa exige referência, PCR/SEQUENCIAMENTO, registro, autor e data.')
        external = {k: confirmation[k].strip() for k in required}
        level = LEVELS[3]
        reasons.append('Confirmação externa registrada pelo usuário. O Gene-In não verifica o ensaio.')
    negative_note = ''
    if level == LEVELS[0] and negative_support is not None and reference in negative_support:
        negative_note = 'também no controle negativo'
    elif read_supported:
        if negative_support is None:
            negative_note = 'suporte sem controle negativo no lote'
        else:
            maximum = negative_support.get(reference)
            negative_note = f'Máximo no controle negativo para a referência: {maximum if maximum is not None else "NA"} templates'
    return {'level': level, 'tie': tie, 'revision': REVISION, 'reasons': reasons,
            'external_confirmation': external, 'similarity_only': level == LEVELS[0],
            'unique_templates': templates, 'distinct_starts': starts,
            'breadth_1x': coverage.get('breadth_1x'), 'breadth_3x': coverage.get('breadth_3x'),
            'negative_note': negative_note}


def control_missing_note(data: dict, metrics: dict | None) -> str:
    if not metrics or metrics.get('sample_rpm') != 'NA':
        return ''
    target = metrics.get('target') or 'UNSPECIFIED'
    matched = any(target in (c.get('reference_id'), c.get('taxon')) for c in data.get('candidates', []))
    reason = ('suporte do alvo sem medição' if matched
              else 'sem correspondência do alvo por accession ou rótulo')
    return f'RPM do alvo {target}: NA ({reason}).'


def _cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')


def _percent(value):
    return 'NA' if value is None else f'{value:.2%}'


def render_grades(data: dict, confirmations: list[dict] | None = None, *,
                  negative_support=None, control_metrics=None) -> str:
    lines = ['## Evidência graduada', '',
             'Escopo: similaridade → atribuição no painel → suporte por reads → registro externo. Não é diagnóstico clínico.',
             '', SUPPORT_NOTE, '', CONTROL_NOTE]
    header = ['| Referência | Nível | Templates | Inícios distintos | Cobertura 1× | Cobertura 3× | Empate | Negativo do lote | Motivo |',
              '|---|---|---|---|---|---|---|---|---|']
    primary, similarity = [], []
    for candidate in data.get('candidates', []):
        matches = [c for c in confirmations or [] if c.get('reference_id') == candidate.get('reference_id')]
        result = grade(candidate, matches[-1] if matches else None, negative_support=negative_support)
        rows = similarity if result['similarity_only'] else primary
        tie = ('SIM — atribuição ambígua' if result['tie'] else
               'Não avaliado' if result['tie'] is None else 'Não observado no painel')
        values = [candidate.get('reference_id'), result['level'],
                  result['unique_templates'], result['distinct_starts'],
                  _percent(result['breadth_1x']), _percent(result['breadth_3x']),
                  tie, result['negative_note'] or '—', ' '.join(result['reasons'])]
        rows.append('| ' + ' | '.join(_cell('NA' if value is None else value) for value in values) + ' |')
    if primary:
        lines += ['', *header, *primary]
    if not primary and not similarity:
        lines += ['', 'SEM_SINAL_RECUPERADO nas condições executadas. A presença não pode ser excluída.']
    lines += ['', f'Sinais por similaridade nesta amostra: {len(similarity)}.', '', SHORT_NOTE + '.']
    if similarity:
        lines += ['', '<details>', f'<summary>Sinais por similaridade ({len(similarity)})</summary>',
                  '', *header, *similarity, '', '</details>']
    if note := control_missing_note(data, control_metrics):
        lines += ['', _cell(note)]
    lines += ['', 'Regra: ' + REVISION + '. Ausência de medição permanece nula/não avaliada.', '',
              'Origem dos critérios: código versionado scripts/evidence/graded_evidence.py. Atribuição exige TARGET_SPECIFIC e PANEL_TAXON_PREFERRED.', '',
              LEVELS[3] + ' exige registro explícito de PCR ou sequenciamento pelo usuário. O Gene-In não verifica o ensaio.', '']
    for confirmation in confirmations or []:
        lines.append('Registro externo: ' + _cell(confirmation))
    return '\n'.join(lines)
