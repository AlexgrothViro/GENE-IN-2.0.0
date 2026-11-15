# Gene-In: repositório principal e histórico

O desenvolvimento desta entrega está em [AlexgrothViro/GENE-IN-2.0.0](https://github.com/AlexgrothViro/GENE-IN-2.0.0). O nome anterior `gene-in-estabilizado` não é este repositório. Esta árvore identifica a versão de software **2.0.2**, com memória em disco, painel e fechamento de engenharia incorporados à main; consulte a [nota da integração](integracao-memoria-22out.md), o [histórico](../CHANGELOG.md), o [guia de uso](../README.md) e os [limites científicos](validacao.md). A rc1 e seus registros permanecem preservados como etapa anterior.

## Escolha da distribuição — consulta de 03/11/2026

A linha principal é `GENE-IN-2.0.0/main`. A base desta revisão é o commit `42fa5177a6c5f11d4ea3a6bf0f842104c6a7a5d7`, que incorporou o PR #10 em 03/11. Sua árvore coincide com a candidata de engenharia `602d64f`. Os checks dessa base passaram: [Engineering tests](https://github.com/AlexgrothViro/GENE-IN-2.0.0/actions/runs/41728803998), incluindo integridade e E2E de software, e [ShellCheck](https://github.com/AlexgrothViro/GENE-IN-2.0.0/actions/runs/41728803840). A [instalação independente](instalacao-do-zero.md) informa exatamente o pacote e o ambiente ensaiados; ela não é uma instalação repetida a cada commit.

| Linha examinada | Decisão de engenharia |
|---|---|
| `GENE-IN-2.0.0/main` | Base da distribuição: reúne painel, memória, instalação, contratos e CI atual. Fixar o commit usado. |
| `gene-in-estabilizado/main` | Histórico de desenvolvimento; a main de 22/10 antecede as correções posteriores da distribuição. |
| Linhas 1.0/1.1 e Alpha | Histórico de maio–julho; não substituem a distribuição atual. |
| `trabalho/software-builder` / PR #6 | Proposta separada em rascunho, divergente da main. Inclui Builder 0.4.0 e mudanças adicionais; não foi integrada em bloco. |
| `genein-builder` e `REA_GENE-IN_Geneious` | Produtos complementares, com escopo próprio; não são versões completas do Gene-In. |

Dessa comparação foram aproveitadas apenas melhorias independentes de identidade e empacotamento: commit nos arquivos gerados por Git, fallback de identificação pelo `RELEASE.json` e tratamento de metadados que não são objetos JSON. O empacotador grava a identidade dentro dos arquivos ZIP/TAR sem alterar a fonte. As demais mudanças das branches não estão implicitamente aprovadas ou incluídas.

O número **2.0.2** identifica o software; `VERSION=2.0.0-alpha.2` identifica o contrato Evidence congelado. Para distinguir revisões, registre o commit de `genein --version`/`SOURCE_COMMIT` e o hash do pacote. A conferência de engenharia não altera o status da validação científica.

## Endereços atuais

| Necessidade | Endereço |
|---|---|
| Código e histórico da fonte | [Repositório](https://github.com/AlexgrothViro/GENE-IN-2.0.0) |
| Versões publicadas | [Releases](https://github.com/AlexgrothViro/GENE-IN-2.0.0/releases) |
| Propostas de alteração | [Pull requests](https://github.com/AlexgrothViro/GENE-IN-2.0.0/pulls) |
| Relatar ou consultar problemas | [Issues](https://github.com/AlexgrothViro/GENE-IN-2.0.0/issues) |
| Instalar e usar esta cópia | [Documentação](README.md) |

A atualização 2.0.2 (integração de memória) está na main desde o PR #2 (`572a827`); o instalador (PR #3) também já está na main. Um ZIP local, uma release no GitHub e o commit de uma análise continuam estados distintos: cite o commit realmente usado. O Builder permanece separado. Uma proposta ou branch histórica não integra automaticamente a versão atual. Mudanças aproveitadas precisam ser verificadas contra a arquitetura, os contratos e os testes da fonte distribuída. A existência de uma release identifica software e não aprova resultados científicos.

## Repositórios históricos

Os nomes abaixo preservam linhas anteriores do projeto. Esses endereços não estão publicados. Conteúdo antigo, quando existir na cópia local do autor, deve ser lido com sua própria versão, sem substituir os guias e perfis desta entrega.

| Repositório | Contexto histórico |
|---|---|
| `GENE_IN-ALPHA` | Linha Alpha anterior |
| `Gene-in-Alpha-pre-release` | Preparação e congelamento técnico anteriores |
| `Gene-in-Alpha-2` | Desenvolvimento da Alpha.2 |
| `Gene-In-Limitado` | Etapas anteriores de instalação, integridade e hospedeiro |
| `Gene-in-private` | Revisões, empacotamento e lançadores anteriores |
| `Gene-In` | Linha 1.0 |
| `Gene-In_1.1` | Linha 1.1 |
| `Gene-In_1.0` | Desenvolvimento inicial |

O registro de organização de 06/10 foi associado ao nome anterior `gene-in-estabilizado`. Esse nome não aponta para este repositório. Ele não substitui a identificação e as verificações do pacote 2.0.0.

## Preservação dos registros

A organização de 06/10 produziu espelhos Git e bundles dos nove repositórios, com verificação de integridade, referências e SHA-256. Os inventários detalhados, hashes dos bundles e propostas preservadas continuam guardados pelo autor em `ORGANIZACAO_GENEIN_GITHUB_06OUT_2026`. Esses nomes identificam evidências locais, não arquivos incluídos na distribuição nem downloads públicos.

Na preparação de 20/10, inventários internos de testes foram preservados fora da fonte, com caminhos relativos e hashes, em diretórios locais do autor. Esses diretórios não entram no pacote e não são downloads públicos. A limpeza da documentação distribuída não altera os commits nem as conclusões das verificações anteriores.

O plano oficial mantido pelo autor continua sendo a referência de andamento das análises. Este índice serve à navegação do software e de suas versões; não é um plano de validação concorrente.
