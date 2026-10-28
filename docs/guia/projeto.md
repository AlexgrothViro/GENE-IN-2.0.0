# Projeto, desenvolvimento e pesquisa

[Início](../../README.md) / [Documentação](../README.md) / Projeto

## Duas visões do mesmo trabalho

| Branch | Finalidade |
|---|---|
| [`trabalho/software-documentado`](https://github.com/AlexgrothViro/GENE-IN-2.0.0/tree/trabalho/software-documentado) | Distribuição enxuta com software e guias de uso |
| [`trabalho/software-builder`](https://github.com/AlexgrothViro/GENE-IN-2.0.0/tree/trabalho/software-builder) | Integração revisável com testes e histórico preservados |
| [`main`](https://github.com/AlexgrothViro/GENE-IN-2.0.0/tree/main) | Base publicada do projeto |

A visão enxuta deve permanecer separada: não a mescle sobre a árvore de desenvolvimento. Correções de código e seus testes pertencem à branch de integração; a distribuição pode ser atualizada a partir de uma revisão identificada.

## Preservação

A base desta edição é o commit `a61897fbce9c2fdff2a644ece59abaf82aeb8f51`, que já contém as correções de instalação, cancelamento e mensagens de entradas inválidas. A integração opcional foi adaptada do [PR original do Builder](https://github.com/AlexgrothViro/gene-in-estabilizado/pull/19), com atualização para 0.4.0.

As branches existentes, os dados e os resultados anteriores permanecem em seus locais. Nenhum banco ou arquivo de amostra é incluído nesta distribuição. Os documentos de apresentação anteriores também foram preservados na branch de integração.

## Acessar o material técnico

- [Testes de integração e contratos](https://github.com/AlexgrothViro/GENE-IN-2.0.0/tree/trabalho/software-builder/scripts/tests)
- [Testes da API e CLI](https://github.com/AlexgrothViro/GENE-IN-2.0.0/tree/trabalho/software-builder/tests)
- [Documentação de desenvolvimento](https://github.com/AlexgrothViro/GENE-IN-2.0.0/tree/trabalho/software-builder/docs/desenvolvimento)
- [Histórico de mudanças](https://github.com/AlexgrothViro/GENE-IN-2.0.0/blob/trabalho/software-builder/CHANGELOG.md)
- [Arquitetura da base](https://github.com/AlexgrothViro/GENE-IN-2.0.0/blob/a61897fbce9c2fdff2a644ece59abaf82aeb8f51/docs/arquitetura.md)

A organização da apresentação usa o [FALCON2](https://github.com/cobilab/FALCON2) como referência visual e de navegação: apresentação curta, instalação, começo rápido, comandos, citação e suporte. O conteúdo é próprio do Gene-In e não implica associação entre os projetos.
