# Correções da revisão científica — 05/10/2026

Identidade da nova lógica: `scientific_review_20261005_v1`. O contrato estrutural Evidence continua `2.0` / `2.0.0-alpha.2`, com extensão identificada em `sample_evidence.json`. Esta edição não reclassifica resultados antigos. O pacote e suas evidências de 02–03/10 continuam como histórico; o novo pacote tem nome e hashes próprios.

## O que mudou

1. A apresentação pública de `DETECTED` é **Candidatos recuperados**, com aviso de que recuperação não confirma origem viral nem espécie. API analítica e interface expõem essa interpretação. O código antigo continua legível por consumidores existentes.
2. Candidatos permanecem exportados e `AVAILABLE` significa disponibilidade para revisão. `availability_status=AVAILABLE_FOR_REVIEW` e `qualification_status=NOT_EVALUATED` distinguem esses conceitos. `available_candidate_count` conta disponíveis; `promotion_eligible_candidate_count` e `qualifying_loci` ficam em zero, pois este classificador não executa seleção científica final. Zero não equivale a teste científico negativo.
3. `total_nonredundant_reference_bp` usa união de coordenadas por referência e segmento. A mesma posição não é somada por orientação, sobreposição ou perfil BLAST diferente. `reference_coverage` registra a unidade e as medições por referência. Sem intervalos, a medição é `NOT_EVALUATED`; quando parcialmente conhecida, é `PARTIAL`. Comprimento contraditório e coordenadas fora da referência são rejeitados. Não se infere posição a partir de uma contagem antiga.
4. `competitive_hits.tsv` recebe `target_evidence_json`, uma extensão com competição específica por referência alvo. O estado do melhor alvo não é atribuído a outros loci/referências. Hits do mesmo perfil são comparados; perfis distintos não têm scores misturados.
5. `specificity_status` avalia alvo contra não alvos; `taxonomic_status` registra a comparação entre taxa rotulados reportados. Os estados são `PANEL_TAXON_PREFERRED`, `AMBIGUOUS`, `NON_TARGET_BEST` e `NOT_EVALUATED`. Preferência é restrita ao painel/hits reportados, não uma confirmação de espécie. Os parâmetros existentes de margem/cobertura são reaproveitados e não foram calibrados por estes testes como probabilidades de acerto taxonômico.
6. Relatórios incluem avisos de melhor não alvo, suporte não medido ou medido em zero, controles com ressalvas e alcance taxonômico. A tabela detalhada mostra bases únicas e atribuição no painel.

## Compatibilidade e evidências históricas

O produtor escreve a nova coluna; o validador também aceita a tabela antiga sem ela para preservar a leitura de resultados existentes. Nas tabelas antigas, o estado competitivo só pode ser atribuído à referência explicitamente identificada em `target_sseqid`. Sem essa ligação, a especificidade fica não avaliada em qualquer resumo recalculado. Esses resumos devem ser gravados em novos diretórios; arquivos históricos não são alterados automaticamente.

Documentos anteriores sem `scientific_revision` continuam usando seu contrato original na leitura. Documentos da revisão têm verificações adicionais: rótulo consistente com o outcome, disponibilidade distinta de qualificação e contagem de bases igual à união dos intervalos dos candidatos. O identificador da revisão é necessário ao comparar métricas entre edições.

O campo `reference_coverage.biological_origin_confirmed=false` explicita que uma união de hits não demonstra origem viral. Bases em referências diferentes e segmentos não devem ser convertidas em cobertura de um único genoma sem um denominador biologicamente definido.

## Verificação desta edição

Os testes específicos cobrem: controle de hospedeiro com candidatos preservados, aviso de não alvo, ausência de suporte, união de bases sobrepostas/reversas/perfis, referências e segmentos distintos, intervalos ausentes ou inválidos, referências fracas, empate entre espécies alvo, taxonomia incompleta, ligação por query/referência/perfil, contrato contra dupla contagem e exposição na API. Testes de interface conferem o texto renderizado.

As verificações ponta a ponta incluem QC, montagem/resgate e BLAST reais, com cenários de 20 pb, mistura20/34/54/74/100, adaptador informado e hospedeiro sintético. O teste agora verifica também semântica pública, ausência de qualificação automática, limite de bases únicas e aviso no controle, além de registrar quantas sequências distintas da entrada foram exportadas.

Os cenários continuam sendo fixtures funcionais favoráveis, sem erros simulados e com filtro de hospedeiro desligado. As contagens de exportação não constituem validação de degradação biológica, falsos positivos em amostras reais, sensibilidade ou superioridade. A instalação limpa em outra máquina e a reprodução por terceiro não foram demonstradas por esta revisão.

Evidências da correção e comparação antes/depois são entregues separadamente do código. As etapas experimentais adicionais da estratégia SAT permanecem necessárias para estimar desempenho científico. G0.8 da campanha anterior conserva o estado reprovado.
