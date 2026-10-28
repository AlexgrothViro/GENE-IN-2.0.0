<div align="center">

# Gene-In

### Recuperação e revisão de sequências candidatas

**Painel local · Linux e WSL2 · Proveniência por execução**

[Instalação](docs/guia/instalacao.md) · [Primeiros passos](docs/guia/uso.md) · [Montadores](docs/guia/montadores.md) · [Documentação](docs/README.md) · [English](README.en.md)

</div>

---

## O que é o Gene-In?

O **Gene-In** reúne preparação de dados, montagem, busca por similaridade e organização de resultados em um fluxo para revisão humana. Você escolhe as entradas, as referências e o montador; o programa registra a configuração e apresenta sequências candidatas com sua proveniência.

O painel funciona no próprio computador. A mesma instalação também oferece uma interface de linha de comando.

### Recursos

- **Fluxo guiado:** preparação, acompanhamento, resultados e exportação no painel.
- **Escolha de montagem:** Velvet, SPAdes, metaSPAdes, MULTI ou Gene-In Builder opcional.
- **Resultados rastreáveis:** sequências, tabelas, logs, configuração e manifesto.
- **Organização local:** código, ambientes, bancos e resultados podem ficar em diretórios separados.

> Sequências candidatas exigem revisão humana. Similaridade não confirma origem, espécie ou diagnóstico. Veja o [alcance e as limitações](docs/guia/resultados.md).

## Navegação

| Começar | Usar | Consultar |
|---|---|---|
| [Instalação](docs/guia/instalacao.md) | [Painel e CLI](docs/guia/uso.md) | [Arquivos de saída](docs/guia/resultados.md) |
| [Requisitos](docs/guia/instalacao.md#requisitos) | [Montadores e Builder](docs/guia/montadores.md) | [Suporte](docs/guia/suporte.md) |
| [Preparar o Builder](docs/guia/montadores.md#instalar-o-builder) | [Organizar os arquivos](docs/guia/uso.md#organização-dos-arquivos) | [Citação e licença](docs/guia/citacao.md) |

## Instalação

**Windows com WSL2:** extraia a fonte completa em uma pasta permanente. Execute `INSTALAR_GENEIN.bat` e, depois, `ABRIR_GENEIN.bat`.

**Linux ou terminal Ubuntu/WSL:** na pasta do programa:

```bash
bash bundle/install_wsl.sh
bash bundle/run.sh test-env
bash run_linux.sh
```

Abra o endereço exibido no terminal. Os [pré-requisitos e passos completos](docs/guia/instalacao.md) explicam a instalação, os caminhos e o ambiente separado.

## Primeiros passos

1. Abra **Nova análise** e selecione as entradas.
2. Escolha um banco preparado e uma pasta nova para a saída.
3. Escolha o montador e confira a configuração.
4. Acompanhe a execução e revise os arquivos em **Resultados**.

O pacote não inclui bancos biológicos nem dados de amostras. Consulte o [guia de uso](docs/guia/uso.md).

## Montadores

| Opção | Papel |
|---|---|
| **Velvet** | Montador disponível no ambiente do Gene-In |
| **SPAdes** | Opção individual de montagem |
| **metaSPAdes** | Opção individual para entradas compatíveis |
| **MULTI** | Reúne Velvet, SPAdes e metaSPAdes |
| **Gene-In Builder** | Opção adicional, instalada separadamente; integração com a versão 0.4.0 |

O Builder é selecionável no painel e na CLI. Ele não substitui os componentes do MULTI. Consulte [instalação, seleção e limitações do Builder](docs/guia/montadores.md).

## Comandos úteis

```bash
bash bundle/run.sh genein --version
bash bundle/run.sh genein --help
bash bundle/run.sh genein run --help
```

A [referência de uso](docs/guia/uso.md) explica a relação entre painel, CLI e arquivos de configuração.

## Saídas

| Arquivo | Conteúdo |
|---|---|
| `candidate_sequences.fa` | Sequências candidatas |
| `candidate_sequences.tsv` | Alinhamentos reportados |
| `candidate_summary.tsv` | Resumo por candidato |
| `candidate_queries.json` | Proveniência das sequências consultadas |
| `execution.json` | Recibo técnico da execução iniciada pela CLI |

Preserve a pasta completa da execução. Os [estados, avisos e limites de interpretação](docs/guia/resultados.md) fazem parte do resultado.

## Citação, suporte e licença

- **Citar:** use [CITATION.cff](CITATION.cff), a versão e o commit efetivamente usados. [Guia de citação](docs/guia/citacao.md).
- **Pedir suporte:** consulte [problemas comuns](docs/guia/suporte.md) e as [issues](https://github.com/AlexgrothViro/GENE-IN-2.0.0/issues).
- **Licença:** [Gene-In Limited Public Use License](LICENSE). Os componentes externos mantêm suas [licenças próprias](THIRD_PARTY_NOTICES.md).
- **Desenvolvimento e pesquisa:** [código de referência, testes e histórico](docs/guia/projeto.md).

---

[Documentação](docs/README.md) · [Repositório](https://github.com/AlexgrothViro/GENE-IN-2.0.0) · [Releases](https://github.com/AlexgrothViro/GENE-IN-2.0.0/releases)
