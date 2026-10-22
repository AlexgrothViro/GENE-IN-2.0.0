# Histórico de entregas

## 2026-10-22 — 2.0.2, integração de memória

- Integra o processamento em disco do resgate à distribuição 2.0.1, mantendo suas saídas, identidade, configuração e leitura de metadados de referência.
- Deduplica o BLAST do resgate em SQLite, sem fallback para carregar a tabela inteira em memória. Preserva o filtro em duas passagens e os hashes em fluxo já presentes na 2.0.1; melhora o tratamento de falhas, mantendo ledger/proveniência e o contrato da entrada: raw ausente encerra com erro; arquivo existente vazio produz somente cabeçalhos.
- Exporta a tabela completa e `candidate_summary.tsv` em fluxo; mantém um melhor hit por candidato, ordem/desempate, catálogo FASTA/BLAST, descrições, táxon e validação correspondente do resumo.
- Preserva byte a byte os quatro módulos de disco da b3: `aggregate_hsps.py`, `build_loci.py`, `build_hsp_evidence.py` e `competitive_hits.py`.
- Retira atribuições de configuração sem uso e documenta os globais consumidos pelos helpers, sem mudar a resolução da configuração.
- Mantém autoria/licença, VERSION/contrato Evidence `2.0.0-alpha.2`, parâmetros, perfis, locks e resultados históricos. Builder continua separado.
- A identificação 2.0.2 distingue o novo pacote e a proposta de PR; não anuncia merge na main, teto universal de RAM, solução geral de disco ou nova avaliação biológica. Verificações e limites em [integração de memória](docs/integracao-memoria-22out.md).

## 2026-10-20 — 2.0.1, correção de distribuição

- A versão de software passa a 2.0.1. O arquivo `VERSION` e o contrato Evidence permanecem `2.0.0-alpha.2`. Parâmetros, perfis e locks científicos não mudam.
- O gerenciador de banco aceita um FASTA local com nome escolhido, e os padrões podem ir para `GENEIN_WORK_ROOT`.
- O relatório e o painel mostram `CANDIDATOS_PARA_REVISAO`. Os JSON conservam os códigos do contrato.
- Há `candidate_summary.tsv`, com um melhor hit por candidato, além da tabela completa.
- O pacote grava `SOURCE_COMMIT` para leitura sem a pasta `.git`.
- O micromamba do instalador fica em 2.9.0, com hash do tar.bz2.
- Registros internos de reteste ficam em `docs/desenvolvimento/` e fora do pacote.
- O texto de preparação de 20/10 fica em `descarte/` e não entra no pacote.
- Make, os scripts e o painel leem `picornavirus.env` e o banco BLAST na mesma ordem: `GENEIN_CONFIG_FILE`, o diretório de trabalho, `~/.gene-in` e a fonte. Na 2.0.0 essa leitura ficava só na fonte. Um perfil nomeado ignora `DB_QUERY`; só `custom` grava a consulta no manifesto.

## 2026-10-20 — 2.0.0, distribuição final de pesquisa

- Fecha a versão de software 2.0.0 para recuperação de sequências candidatas e triagem humana, preservando integralmente a rc1, seus pacotes, evidências e histórico Git.
- Atualiza os guias em português/inglês, apresentação, exemplos de instalação e citação para a versão 2.0.0. Originais documentais da rc1 preservados com SHA-256 antes das alterações.
- Mantém autoria, licença, contrato Evidence `2.0.0-alpha.2`, recuperação `fragment_recovery_20_100_v1`, revisão `scientific_review_20261005_v1`, parâmetros e conclusões científicas anteriores.
- Distingue as verificações aprovadas da rc1 dos recibos que identificarão os novos pacotes 2.0.0; não anuncia nova validação biológica ou reprodução independente.
- Registros e alcance neste histórico. A entrega é local, sem publicação remota de tag ou release nesta preparação.

## 2026-10-20 — 2.0.0rc1, candidata ao lançamento

- Consolida a base b3 para preparação de uma entrega de pesquisa e triagem humana; Gene-In Builder permanece desenvolvimento separado e fora do pacote desta candidata.
- Reorganiza README em português/inglês, entrada rápida, guias de instalação e uso, índice da documentação e acesso aos registros históricos.
- Documenta utilidades, entradas paired/single/contigs, MULTI, bancos e manifestos, controles, lotes, filtro de hospedeiro, servidor local e interpretação de arquivos/estados.
- Acrescenta `CITATION.cff` e guia de citação com autoria identificada na licença, sem inventar DOI, ORCID ou referência acadêmica.
- Corrige a ajuda do Makefile e a seleção explícita do ambiente nas trilhas de verificação; conserva os padrões científicos do processamento.
- Corrige o estado das trilhas para que falhas realmente executadas permaneçam `FAIL` também em `all-safe`; código 77 identifica teste não executado. Ajusta a leitura de versões BLAST e rejeita texto de ajuda como versão em cache/proveniência.
- Acrescenta preparação de ZIP/tar.gz a partir da fonte rastreada, com recusa de sobrescrita, manifesto de arquivos, hashes dos pacotes e conferência de membros; preserva o wrapper de empacotamento anterior.
- Organiza nomes internos de verificação e retira orientações e registros de desenvolvimento da distribuição; originais preservados separadamente. Parâmetros experimentais preservados, com identificadores de metadados atualizados.
- Preserva contrato Evidence `2.0.0-alpha.2`, recuperação `fragment_recovery_20_100_v1`, revisão `scientific_review_20261005_v1`, parâmetros científicos e resultados anteriores.
- Estado das verificações e do fechamento do pacote neste histórico. A preparação local não implica publicação remota ou nova validação biológica.

## 2026-10-09 — 2.0.0b3, reteste de engenharia

- BLAST curto em blocos com equivalência byte a byte; validação antecipada de controles e banco composto.
- Falhas de memória/sinais, limpeza de temporários, arquivos FASTQ simples, progresso de upload e revalidação de artefatos.
- Parâmetros científicos preservados. Relatório e limites da b3: `docs/desenvolvimento/` no repositório Git, fora do pacote distribuído.

## 2026-10-08 — 2.0.0b2, usabilidade

- Correções individuais de instalação, memória e interface registradas em `docs/desenvolvimento/` no repositório Git, fora do pacote distribuído.

## 2026-10-08 — 2.0.0b1, beta de pesquisa

- Guia de instalação, aplicações, primeira execução, limites, citação e retorno para pesquisadores convidados.
- Inventário das licenças do ambiente e avisos OFL das fontes locais; licença própria preservada.
- Diagnóstico respeita o ambiente explicitamente selecionado, sem usar silenciosamente outra instalação.
- Instalador rejeita plataformas incompatíveis antes de baixar ferramentas e prepara permissões dos scripts extraídos de ZIP.
- Apresentação editorial revisada e comando público `make test-tracks` para as trilhas de testes.
- Contratos e parâmetros científicos preservados. A beta identifica a distribuição; a validação científica adicional permanece pendente.
- Evidências e limites da verificação: `docs/desenvolvimento/` no repositório Git, fora do pacote distribuído.

## 2026-10-06 — entrega funcional organizada

- Integra a recuperação `fragment_recovery_20_100_v1` e as correções `scientific_review_20261005_v1`. O nome de repositório daquela etapa era `gene-in-estabilizado`; esta fonte está em `AlexgrothViro/GENE-IN-2.0.0`.
- Organiza documentação de instalação, bancos, arquitetura, desenvolvimento, resultados e limites científicos, com índice e README em português/inglês.
- Corrige a preparação da suíte para verificar a instalação da árvore atual e evitar downloads de build desnecessários.
- Acrescenta instalação explícita e testes de interface à integração contínua.
- Confere pré-requisitos da instalação nativa e trata falhas HTTP no download do micromamba.
- Retira identificação 1.1 dos lançadores de instalação atuais e documenta fontes dinâmicas para ShellCheck.
- Mantém o contrato Evidence `2.0.0-alpha.2`, parâmetros científicos, sequências históricas e resultados congelados.

## 2026-10-05 — correções científicas implementadas

Disponibilidade de candidatos separada de qualificação; união de bases alinhadas por referência/segmento; competição por query/referência/perfil; atribuição taxonômica com ambiguidade e alcance explícitos. O registro está em `docs/desenvolvimento/` no repositório Git, fora do pacote distribuído.

## 2026-10-02 a 2026-10-03 — recuperação integrada de 20–100 pb

Queries unificadas de contigs, fragmentos montados e reads; preservação de curtos na presença de longos; busca e proveniência; exportação de sequências; integração de MULTI/adaptadores na interface; verificações funcionais com ferramentas reais. O registro histórico está em `docs/desenvolvimento/` no repositório Git, fora do pacote distribuído.

O desenvolvimento anterior permanece no histórico Git e na branch de preservação da versão anterior. Resultados de campanhas anteriores não foram recalculados para esta publicação.
