# Primeiros passos

[Início](../../README.md) / [Documentação](../README.md) / Uso

## No painel

Abra o programa pelo lançador ou por `bash run_linux.sh`. A navegação principal reúne **Início**, **Nova análise**, **Acompanhar**, **Resultados** e **Histórico**.

Em **Nova análise**, selecione os arquivos da amostra, um banco preparado, o diretório de saída e o montador. Confira a configuração apresentada antes de iniciar. O [guia de montadores](montadores.md) explica as opções e a instalação do Builder.

O pacote não traz bancos nem arquivos de amostras. Referências e índices devem corresponder ao trabalho realizado. A escolha de hospedeiro é do usuário e não é inferida pela integração do Builder.

## Linha de comando

Use a ajuda da cópia instalada:

```bash
bash bundle/run.sh genein --help
bash bundle/run.sh genein run --help
```

| Opção | Finalidade |
|---|---|
| `--sample` | Identificador da amostra |
| `--r1`, `--r2` | Entradas pareadas |
| `--single` | Entrada simples, quando aplicável |
| `--blast-db` | Prefixo de banco preparado com manifesto |
| `--output-root` | Pasta nova de saída, fora da fonte |
| `--analysis-profile` | Perfil de execução |
| `--assembler` | Montador individual, com o perfil `default` |

Confirme as combinações na ajuda. O perfil `assembly-consensus` controla o MULTI e não aceita substituição por `--assembler`. Para selecionar Builder, use o perfil `default` e `--assembler builder`.

## Organização dos arquivos

| Local | Conteúdo |
|---|---|
| Pasta do programa | Fonte e documentação |
| Ambiente principal | Ferramentas e dependências do Gene-In |
| Ambiente opcional do Builder | Pacote Builder e suas dependências |
| Diretório de trabalho | Bancos e índices escolhidos pelo usuário |
| Diretório de resultados | Uma pasta por execução |

`GENEIN_WORK_ROOT` pode apontar para um diretório absoluto existente para bancos e índices padrão. Caminhos explicitamente fornecidos permanecem onde foram escolhidos.

`GENEIN_OUTPUT_ROOT`, definido antes de abrir o painel, permite listar execuções em uma pasta externa com recibos `execution.json`. A CLI exige uma saída nova e fora da fonte.

No WSL, um caminho como `C:\dados` corresponde normalmente a `/mnt/c/dados`. Coloque caminhos com espaços entre aspas.

## Ao concluir

Confira o estado técnico, os avisos e os arquivos produzidos. Preserve a pasta completa e exporte pelo painel quando conveniente. Fechar o navegador não encerra o servidor; use o terminal para isso.

Consulte [resultados](resultados.md) antes de interpretar candidatos. Para referência técnica das opções existentes e preparação de bancos, há um [guia preservado da base](https://github.com/AlexgrothViro/GENE-IN-2.0.0/blob/a61897fbce9c2fdff2a644ece59abaf82aeb8f51/docs/uso-e-bancos.md).
