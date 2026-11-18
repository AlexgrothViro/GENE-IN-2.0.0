# Registro prévio: coletor de sequências de qualquer tamanho

Data: 11/11/2026 (America/Sao_Paulo). Base B0: `18c686310e52ca87ee3a5ca46d9ff73952914263`, branch `trabalho/software-builder` (PR #6, integração com testes). `trabalho/software-documentado` é distribuição sem a suíte; main não é destino desta mudança. AGENTS.md, CLAUDE.md e CONTEXTO não existem nesta base; lidos os guias de desenvolvimento e correções científicas disponíveis.

## Motivo e escopo encaminhados
O coletor anterior ignorava FASTQ >100 pb e <20 pb silenciosamente. Decisão atribuída a Alexsander no recado do Orientador ao coordenador: sequências longas, contigs e genomas completos não podem ser ignorados. Não fatiar nem aparar. Preservar identidade original de read/par na proveniência, sem transformar ocorrências em templates independentes.

## Plano antes de alterar código
- Preservar IDs hash, deduplicação, parâmetros, níveis, suporte e empates da rota 20–100 pb (B0).
- Incluir reads >100 pb na rota convencional existente (blastn, word_size 11); não mudar blast_router nem os critérios científicos.
- <20 pb em FASTQ: manter exclusão de B0, contar e avisar; FASTA <20 mantém comportamento existente, com ressalva explícita de não validação.
- Contabilizar ocorrências por origem e tamanho e queries únicas; distinguir descartes de deduplicação. Manifesto e relatório legível devem mostrar o balanço.
- Verificar contrato Builder: o adaptador existente é 0.4.0, diferente de 3.0.0b1. Importação explícita de resultados 3.0 concluídos pelo coletor, sem declarar compatibilidade do instalador/adapter 0.4. Preservar ESPECIFICIDADE_NAO_VALIDADA dos fragmentos restritos.

## Comparações pré-definidas
1. Mesma entrada sintética 20,34,54,74,100 pb e mesmo ambiente/banco: B0 vs novo coletor, FASTA e resultados científicos idênticos (candidatos, níveis, suporte, empates). Diferenças novas somente em proveniência e balanço.
2. Fronteiras 19/20/100/101/150, pares, duplicatas exatas, contigs e genoma sintético completo: inclusão inteira e roteamento longo, sem inflação de suporte.
3. Resultados reais SRR17241648 do Builder: antes 3.078 reads não montadas de 150 pb ignoradas, depois todas contabilizadas. Teste operacional de coleta, não validação biológica nem benchmark.
4. Suíte de engenharia inteira; ferramentas ausentes registradas como não executadas. Nenhuma carga pesada.

Resultados e limitações serão acrescentados em commit posterior. Sem merge, tag ou alteração de main/Builder/Desktop.

## Resultados (11/11/2026, America/Sao_Paulo)

Implementação executada no WSL do MICRO-001, sem alterar Builder, Desktop, main, tags ou sessões interativas. Fonte de implementação `63684a0`; recibo estruturado [ao lado](coletor-qualquer-tamanho-20261111.recibo.json).

| Verificação | B0 | Novo |
|---|---:|---:|
| Queries 20–100 pb | 10 | 10 |
| Candidatos, painel sintético com alvos empatados | 30 | 30 |
| Linhas com dois táxons alvo concorrentes | 18 | 18 |
| Nível | REVIEW | REVIEW |
| Diferenças científicas da rota curta | — | 0 |
| Queries longas, sintéticas | 2 (só contigs) | 4 (150,150,350,1770 pb) |
| SRR17241648: reads não montadas reconhecidas | 0 | 3.078 |
| SRR17241648: queries únicas totais | 12.205 | 14.985 |

Nove artefatos científicos idênticos byte a byte na rota curta, incluindo BLAST de ambos os perfis, fragmentos, loci, HSPs, competição, suporte, cobertura e linhagem. JSONs de candidatos, nível, especificidade, resultado e cobertura idênticos. Referências alvo idênticas e de táxons distintos tornam explícita a ambiguidade. O remapeamento curto mede zero templates com MAPQ suficiente nesse painel ambíguo; isso não é demonstração de suporte positivo.

No painel longo com remapeamento não ambíguo, os dois mates de 150 pb entram inteiros, além do contig de 350 pb e do genoma sintético completo de 1.770 pb. Duplicar as ocorrências do mesmo par mantém **1 template e 2 inícios**, iguais ao par sem duplicação: dois inícios de mates são legítimos no contrato existente, mas não satisfazem o critério de pelo menos dois templates. Bowtie2 pode marcar nomes repetidos como discordantes: nessa fixture reduz proper-pair support (1 para 0), sem inflar templates/inícios; não alteramos essa semântica.

A coleta real aceitou 17.294 ocorrências longas no conjunto contigs+fragmentos+reads, reuniu 2.309 ocorrências idênticas e produziu 14.985 queries únicas; zero exclusões por comprimento nessa entrada. A execução real aqui é de **coleta**, não busca completa contra banco biológico nem validação científica.

Suíte final: 629 testes de scripts passaram, 1 pulado (Builder real opcional 0.4.0 não solicitado), 140 testes de API/CLI/grafo passaram, 17 testes JavaScript passaram; regressões shell, 69 verificações de sintaxe Bash e compileall passaram. A primeira execução encontrou uma falha de fixture de lote causada pela configuração preexistente do HOME (THREADS 4 em vez do 6 da fixture). A mesma fixture e a suíte inteira passaram com HOME isolado; configuração pessoal não foi alterada. Trilhas de otimização científica não executadas, conforme o guia do repositório.

Comandos reproduzíveis (ambiente científico e checkout Git com B0):

```bash
python scripts/tests/verify_query_sizes_real.py \
  --artifact-root /pasta/nova_ab \
  --builder-manifest /saida_builder/manifesto_execucao.json
HOME=/pasta/home_testes_vazia bash scripts/tests/run_test_suite.sh engineering
```

Artefatos completos locais: `/home/mestradoalex/genein-coletor-auditoria-20261111/ab_release` e `engineering-final.log` na pasta pai (cerca de 109 MB incluindo tentativas anteriores). Versões: Python 3.12.3, BLAST 2.12.0+, Bowtie2 2.5.2, samtools 1.19.2, Node 18.19.1. Não houve download nem execução pesada.

## Pendências e publicação

- FASTQ <20 pb continua excluída com contagem; eventual aceitação exige decisão científica.
- Adaptador/instalador Builder 0.4.0 foi atualizado para o contrato 3.0.0b1 (`-1/-2/-o`) preservando retrocompatibilidade com 0.4.0, e `sample_steps.sh` repassa `--builder-manifest` ao coletor.
- O Desktop em main `5418bf966f444cb643a9b5f74a9a4bcbfa7f247f` tem coletor **idêntico byte a byte ao B0** e precisará de port equivalente. Apenas leitura remota, sem mudanças.
- A atribuição da decisão científica chegou por outro bot; a autorização direta disponível para abrir PR era a do Builder. Confirmar diretamente o escopo desta mudança científica antes da publicação. Destino proposto: PR de `trabalho/coletor-qualquer-tamanho` para `trabalho/software-builder`, aberto, sem merge/tag.

## Portão de evidência forte e antes/depois em dados reais de pipeline (Revisão MICRO-001)

`classify_sample.py` passa a ler os limiares diretamente de `config/evidence_profiles.json` (`support.minimum_unique_templates = 3`, `support.minimum_distinct_starts_shotgun = 2`, `locus.minimum_candidate_bp = 50`) e avaliar `candidate_retention_reasons` em **todos** os candidatos (contigs montados, Builder e `read_level`), exigindo `category == "TARGET_VIRUS"` e `specificity_status in {"TARGET_SPECIFIC", "TARGET_BEST"}`. Candidatos que não cumprem os limiares recebem `retention_status = "CANDIDATE_RETAINED_BELOW_STRONG_EVIDENCE"` e mantêm a execução em `REVIEW`.

| Execução de pipeline (com controle validado `CONTROL_BELOW_SAMPLE`) | Categorias / Especificidade / Suporte | `fa21aa1` (antes) | `8698c92` (intermediário) | Novo portão (`evidence_profiles.json`) |
|---|---|---|---|---|
| `alpha2` (7 runs: `81554` SPAdes/metaSPAdes/Velvet, `81555`, `D26_03`, `79f201`, `8e612a`) | `UNLABELED`, `NOT_EVALUATED`, `0` templates | `DETECTED` (7/7) | `DETECTED` (7/7) | `REVIEW` / `CANDIDATE_RETAINED_BELOW_STRONG_EVIDENCE` (7/7) |
| `closure_test` (`b4-eg002-run1`, `b4-eg002-run2` — contig Velvet) | `TARGET_VIRUS`, `TARGET_SPECIFIC`, `0` templates | `DETECTED` (2/2) | `DETECTED` (2/2) | `REVIEW` / `CANDIDATE_RETAINED_BELOW_STRONG_EVIDENCE` (2/2) |
| `ab_release/long` (contig 350 pb + read 150 pb) | `TARGET_VIRUS`, `AMBIGUOUS`/`NOT_EVALUATED`, `1` template / `2` inícios | `DETECTED` | `DETECTED` | `REVIEW` / `CANDIDATE_RETAINED_BELOW_STRONG_EVIDENCE` |
| `ab_release/long_single_pair` (par `read_level` 150 pb) | `TARGET_VIRUS`, `AMBIGUOUS`/`NOT_EVALUATED`, `1` template / `2` inícios | `DETECTED` | `REVIEW` | `REVIEW` / `CANDIDATE_RETAINED_BELOW_STRONG_EVIDENCE` |
| Painel positivo com remapeamento (`TARGET_VIRUS`, `>=50 pb`, `>=3` templates, `>=2` inícios) | `TARGET_VIRUS`, `TARGET_SPECIFIC`/`TARGET_BEST`, `>=3` templates | `DETECTED` | `DETECTED` | `DETECTED` / `PROMOTED_TO_DETECTED` |

### Opções para decisão do Alexsander sobre `UNLABELED` e bancos do usuário sem `labels.tsv`

Por padrão, candidatos `UNLABELED` permanecem retidos em `REVIEW` (`CANDIDATE_RETAINED_BELOW_STRONG_EVIDENCE`, motivo `UNLABELED_REQUIRES_REVIEW`). Opções de política:
1. **Opção A (atual / conservadora)**: manter `UNLABELED` sempre em `REVIEW`, exigindo `labels.tsv` com `TARGET_VIRUS` para promoção a `DETECTED`.
2. **Opção B (modo banco do usuário dedicado)**: quando o usuário informar explicitamente que o banco customizado contém apenas alvos virais (ex.: flag/perfil `custom_target_only`), tratar ausências de `labels.tsv` como `TARGET_VIRUS` sujeitas aos demais portões (`>=3` templates, `>=2` inícios, `>=50 pb`).
3. **Opção C (geração automática de `labels.tsv` na indexação do banco)**: exigir/gerar `labels.tsv` no preparo do banco customizado antes da execução.
