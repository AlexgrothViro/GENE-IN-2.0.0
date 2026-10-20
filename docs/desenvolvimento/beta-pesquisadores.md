# Gene-In 2.0.0 — guia para pesquisadores

Esta distribuição final de software permite usar localmente a recuperação e organização de sequências candidatas em dados fragmentados, para pesquisa e triagem humana. O nome deste arquivo conserva o endereço usado pelas betas; o guia se refere à **2.0.0**. Os registros das versões anteriores permanecem no [índice histórico](README.md#registros-preservados).

## Aplicações

- Triagem exploratória dirigida pela pergunta do pesquisador e por um banco de referência documentado.
- Recuperação e exportação de candidatos de 20–100 pb e maiores, com origem e alinhamentos rastreáveis.
- Uso de SPAdes, metaSPAdes e Velvet, individualmente ou pela união MULTI.
- Revisão de similaridade, suporte, competição e ambiguidade antes de análises posteriores.

O programa não confirma espécie, infecção, ausência viral ou diagnóstico. O resultado depende da biblioteca, adaptadores, banco e competidores. Verificações sintéticas funcionais não estimam desempenho em material biológico real; veja [validação](validacao.md).

## Preparar o computador

Use Linux x86_64 ou Windows x86_64 com WSL2/Ubuntu. A primeira instalação precisa de internet. O pacote não traz bancos biológicos, índices de hospedeiro ou amostras de pesquisa. O ambiente fixado não atende macOS, ARM ou Windows sem WSL.

No Windows, extraia o pacote inteiro em uma pasta permanente, execute `INSTALAR_GENEIN.bat` e depois `ABRIR_GENEIN.bat`. No Linux, execute `bash bundle/install_wsl.sh`, `bash bundle/run.sh test-env` e `bash run_linux.sh`. Siga o [guia de instalação](installation-reproducibility.md) para pré-requisitos, ambientes separados, servidor local e recursos.

Não existe um requisito universal de RAM validado. Comece com uma biblioteca pequena. O aviso de 45 GB livres corresponde ao porte medido no reteste b3; confira o [alcance dessa estimativa](installation-reproducibility.md#recursos-e-limites). A pasta da fonte deve permanecer no local em que foi instalada.

## Primeira análise

1. Em **Nova análise → Banco**, prepare o banco escolhido ou selecione um já preparado. Use composição adequada à pergunta e registre sua versão.
2. Selecione os FASTQ da mesma amostra e uma nova pasta de saída. No WSL, use caminhos Linux para os arquivos.
3. Escolha MULTI ou um montador compatível. Informe os adaptadores reais quando houver read-through e habilite filtro de hospedeiro apenas com índice correspondente.
4. Use controles conhecidos e confira primeiro o estado técnico, QC e avisos. Um controle positivo precisa do alvo esperado.
5. Exporte `candidate_sequences.fa`, `candidate_sequences.tsv` e `candidate_queries.json`. Preserve também configuração resolvida, logs, relatórios e manifestos dos bancos.

Veja [uso e bancos](uso-e-bancos.md) para exemplos de CLI, single-end, contigs e lotes. Para repetir a verificação sintética curta com ferramentas reais, use o comando em [instalação](installation-reproducibility.md#primeira-análise-e-verificação-opcional). Ele cria dados locais de teste e conserva evidências; não usa os dados do pesquisador.

## Ler e relatar resultados

Comprimento do read, comprimento do contig/candidato e comprimento do HSP são medidas diferentes. Repetições da mesma sequência não demonstram moléculas independentes. `Candidatos recuperados` informa disponibilidade para revisão; qualificação científica permanece `NOT_EVALUATED`.

Ao relatar uma execução, use o [guia de citação](citacao.md), indique a versão de software e o commit, o banco, os parâmetros, os controles e as limitações. O contrato Evidence e `VERSION` permanecem `2.0.0-alpha.2`; a distribuição é `2.0.0`.

## Problemas e licença

Ao relatar um problema ao autor, informe versão/commit, Windows/Ubuntu e arquitetura, etapa, mensagem completa, montador, RAM/threads e o resultado do teste sintético, se realizado. Preserve o log original e os identificadores da execução. Compartilhe dados biológicos somente conforme o acordo da pesquisa; retire credenciais e dados pessoais dos logs enviados.

Leia a [licença integral](../LICENSE) e os [avisos de terceiros](../THIRD_PARTY_NOTICES.md). A licença permite avaliação acadêmica, ensino e pesquisa não comercial; redistribuição, modificação e usos mais amplos estão sujeitos às restrições e à autorização prévia por escrito do titular. A distribuição aos participantes é feita pelo autor. Consulte a [nota da versão 2.0.0](lancamento-20out.md) para o estado da preparação e da publicação.
