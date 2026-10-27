# Integração de memória — Gene-In 2.0.2

A 2.0.2 adapta o processamento em disco à distribuição pública 2.0.1, preservando seus resultados, metadados de referência e identidade. A base é o commit `96f0932884ae2e8ebe6b580b0c33fbaffc048266`. A integração está na main desde o PR #2 (`572a827`); o instalador (PR #3) também já está na main. Cite o commit realmente usado no [repositório](https://github.com/AlexgrothViro/GENE-IN-2.0.0).

O objetivo permanece recuperar e organizar sequências candidatas para pesquisa e revisão humana. Esta integração não acrescenta uma avaliação biológica, não repete o piloto e não incorpora o Gene-In Builder, que continua em desenvolvimento separado.

## O que muda no processamento

| Etapa | Processamento na 2.0.2 | Contrato preservado |
|---|---|---|
| Deduplicação do BLAST curto/resgate | O [roteador BLAST](../scripts/evidence/blast_router.py) percorre os arquivos e usa um banco SQLite temporário em disco. Não tenta carregar toda a tabela em RAM se SQLite falhar. | Mesma chave de query, referência, orientação e coordenadas; melhor linha por chave, com a posição da primeira ocorrência preservada |
| Filtro de reads resgatados | O [filtro](../scripts/pipeline/filter_rescue_reads.py) preserva as duas passagens e os hashes em fluxo já presentes na 2.0.1. A integração melhora o tratamento de falhas, preservando o contrato da 2.0.1: raw ausente encerra com erro; arquivo existente vazio produz somente cabeçalhos. | Critérios, seleção/desempate, linhas de decisão, contadores e proveniência; sem atribuir nova redução de RAM ao filtro |
| Exportação dos candidatos | O [exportador](../scripts/evidence/export_candidate_sequences.py) grava a tabela completa em fluxo e acumula um melhor hit e contadores por candidato para o resumo. | FASTA completo dos candidatos, tabela completa, catálogo de descrições/táxon, ordem e campos de saída |
| Validação do resumo | Percorre as linhas e acumula os dados necessários por candidato, em vez de conservar uma lista com todos os hits. | Conferência do melhor hit, contagem de linhas e menor e-value sem mudar a leitura do resumo |
| Configuração e ShellCheck | Remove atribuições `LEGACY_CONFIG` sem consumidores e explicita os `REPO_ROOT` necessários aos helpers carregados por `source`. | Mesma resolução de configuração e banco usada na 2.0.1 |

São preservados byte a byte em relação à base 2.0.1 os quatro módulos de disco da b3: [aggregate_hsps.py](../scripts/evidence/aggregate_hsps.py), [build_loci.py](../scripts/evidence/build_loci.py), [build_hsp_evidence.py](../scripts/evidence/build_hsp_evidence.py) e [competitive_hits.py](../scripts/evidence/competitive_hits.py). A adaptação é feita sobre a distribuição atual, conservando as melhorias já presentes nela.

## Saídas e metadados

`candidate_sequences.tsv` continua sendo a tabela completa, com uma linha por alinhamento de query, referência e tarefa. `candidate_summary.tsv` continua com uma linha por candidato; ele não substitui o TSV completo. A escolha usa maior bitscore, menor e-value, maior identidade e, em seguida, identificador da referência e tarefa. Um empate completo conserva a primeira linha correspondente. A ordem da tabela completa e a ordenação dos candidatos são preservadas.

`min_evalue` é o menor valor entre todos os hits do candidato e pode ser de outra referência que não a escolhida como melhor hit. `hit_row_count` conta as linhas do candidato no TSV completo. O título pode vir do FASTA de referência ou do banco BLAST; o táxon usa o rótulo do sujeito quando fornecido e, sem rótulo, o organismo lido no título. Referências sem esses metadados não permitem preenchê-los por suposição. Um título interpretado não confirma a origem biológica da sequência. O [guia de uso](uso-e-bancos.md#resultados-e-interpretação) detalha os campos e os arquivos.

A versão de software é `2.0.2`. O arquivo `VERSION` e `pipeline_version` continuam identificando o contrato Evidence `2.0.0-alpha.2`; permanecem também `fragment_recovery_20_100_v1` e `scientific_review_20261005_v1`. `software_version` e `source_commit` identificam o software nos recibos/proveniência. No pacote sem `.git`, confira também `SOURCE_COMMIT` e `genein --version`. Autoria, licença, parâmetros, perfis e locks científicos permanecem preservados. Resultados históricos continuam vinculados às suas versões e configurações.

## Recursos e falhas

A integração evita reter todas as linhas de HSP nas etapas alteradas. Ainda há estruturas em RAM por sequência, candidato, identificador e catálogo; montadores e ferramentas externas têm suas próprias exigências. Um ensaio sintético de recursos mede somente o cenário, a fonte e o ambiente ali registrados. Não estabelece um teto universal de RAM, capacidade para qualquer biblioteca ou tempo garantido de execução.

SQLite temporário, arquivos intermediários, ledger e saídas continuam consumindo disco. Confira espaço, cota e permissões tanto na saída quanto no diretório temporário efetivo; `TMPDIR`, quando definido, deve apontar a um local apropriado. A mensagem de falta de espaço, inclusive `database or disk is full`, é falha técnica e exige conferir o log. Ela não equivale a ausência de candidatos. Uma nova tentativa usa outra pasta de saída após resolver a causa. A atualização não elimina os demais custos de disco nem altera automaticamente parâmetros de montadores. Veja [instalação e recursos](installation-reproducibility.md#recursos-e-limites) e [solução de problemas](solucao-de-problemas.md).

## Medição sintética de memória e paridade

O recibo externo `memoria/MEMORIA_PARIDADE.json` registra uma comparação efetiva dos módulos da 2.0.1 extraídos do ZIP original arquivado com os da nova fonte, em subprocessos separados. A fixture de exportação/filtro tem 120.000 linhas e 100 queries na exportação. A deduplicação recebe 180.000 linhas com 120.000 chaves de coordenadas distintas de uma única query, exercitando múltiplos hits por identificador.

| Etapa | RSS máximo da 2.0.1 (KiB) | RSS máximo da 2.0.2 (KiB) |
|---|---:|---:|
| Deduplicação | 114.820 | 49.400 |
| Exportação | 145.096 | 19.564 |
| Filtro | 22.144 | 22.272 |

O recibo está em `PASS`: a saída deduplicada, os candidatos/ledger/proveniência do filtro e os quatro arquivos exportados foram idênticos byte a byte entre as versões. O filtro já fazia duas passagens e hashes em fluxo; os valores medidos não mostram uma nova redução de RAM nessa etapa. A deduplicação SQLite teve 13.479.936 bytes de temporários no pico amostrado e não deixou temporários nesse ensaio.

A medição ocorreu no mesmo computador WSL, com caches aquecidos e possibilidade de outras verificações simultâneas. RSS é o máximo de cada subprocesso; disco é somente o tamanho amostrado dos temporários. Esses números não descrevem o pico de uma execução completa, não medem a biblioteca do piloto e não estabelecem ganho universal de memória ou velocidade. Os tempos guardados no recibo pertencem a esse ensaio. A paridade aqui observada não substitui os testes completos da fonte nem os do pacote fechado.
## Como conferir a entrega

A aprovação de uma distribuição precisa estar vinculada ao seu commit e aos hashes dos arquivos fechados. Os recibos externos da entrega registram a comparação com a 2.0.1, preservação dos módulos de disco e contratos, equivalência das saídas, falhas exercitadas, testes de engenharia, ShellCheck e execução com ferramentas reais. A verificação do ZIP extraído é um registro separado da verificação da fonte. Consulte os recibos e o manifesto que acompanham o arquivo recebido; um resultado anterior não aprova automaticamente um novo pacote.

O empacotador usa a fonte rastreada e limpa e inclui `SOURCE_COMMIT` e `SOURCE_MANIFEST.sha256`. Compare o arquivo fechado com `SHA256SUMS` e com os dados de `archive-release.json`; confira também o recibo da instalação e execução extraída. A referência para repetir verificações é o [guia de desenvolvimento](guia-de-desenvolvimento.md). Instalação e execução no mesmo computador, com cache disponível, não demonstram outro computador físico ou preparação do WSL do zero.

Os cenários funcionais curtos, a equivalência de saídas e as medições de engenharia não estimam sensibilidade, precisão ou falsos candidatos em material biológico. G0.8 histórico reprovado, SAT4–6 e qualificação científica mantêm seus estados anteriores. As métricas relatadas em descrições de PR do piloto não são novas medições da 2.0.2 nem substituem tabelas e logs brutos. Consulte os [limites científicos](validacao.md), a [citação](citacao.md) e o [histórico de mudanças](../CHANGELOG.md).
