# Instalação

[Início](../../README.md) / [Documentação](../README.md) / Instalação

## Requisitos

| Item | Suporte |
|---|---|
| Linux | x86_64 |
| Windows | x86_64 com WSL2 e Ubuntu |
| Internet | Necessária na primeira instalação |
| Fonte | Pasta completa, em local permanente |
| Dados e bancos | Fornecidos separadamente pelo usuário |

O ambiente fixado não atende macOS, ARM ou Windows sem WSL. No Linux, são necessários Bash, make, Python 3, curl, tar, bzip2, certificados e utilitários básicos. Em Debian/Ubuntu, o instalador tenta obter os pré-requisitos ausentes; se não conseguir, encerra com orientação antes de criar o ambiente.

## Obter esta edição

Use a branch de software e extraia a pasta completa. Com Git:

```bash
git clone --single-branch --branch trabalho/software-documentado https://github.com/AlexgrothViro/GENE-IN-2.0.0.git
cd GENE-IN-2.0.0
```

A branch é uma edição de distribuição separada. As releases publicadas podem representar versões anteriores, sem a opção Builder. Confira sempre a versão e o commit da cópia usada.

## Windows com WSL2

1. Prepare o WSL2/Ubuntu e conclua a criação do usuário Linux.
2. Extraia o programa em uma pasta permanente.
3. Execute `INSTALAR_GENEIN.bat` e acompanhe o terminal.
4. Execute `ABRIR_GENEIN.bat` e abra o endereço informado.

Se houver pedido de senha de sudo, ele se refere ao usuário Linux. Não execute arquivos de dentro do ZIP.

## Linux ou terminal Ubuntu/WSL

Na raiz do programa:

```bash
bash bundle/install_wsl.sh
bash bundle/run.sh test-env
bash bundle/run.sh genein --version
bash run_linux.sh
```

O painel atende em loopback, normalmente começando em `127.0.0.1:8000`, e pode escolher outra porta. Use o endereço impresso. Mantenha o terminal aberto; Ctrl+C encerra o servidor quando não houver trabalho que precise continuar.

## Ambiente e atualização

O ambiente principal fica em `~/.gene-in-bundle`. Para preparar uma instalação independente, exporte `GENEIN_BUNDLE_DIR` com um diretório próprio antes de todas as chamadas de instalação, painel e CLI. Os lançadores Windows usam o padrão.

Não mova a fonte depois de instalar: a instalação editável e os adaptadores dependem desse caminho. `Atualizar Gene-In.bat` atualiza/verifica a instalação da cópia atual; não baixa automaticamente uma nova fonte do GitHub. Preserve a cópia anterior ao instalar outra versão.

## Builder opcional

| Opção | Como aparece |
|---|---|
| Velvet | Montador individual no ambiente do Gene-In |
| SPAdes | Opção individual de montagem |
| metaSPAdes | Opção individual para entradas compatíveis |
| MULTI | Velvet, SPAdes e metaSPAdes |
| Gene-In Builder | Não pode ser instalado sem acesso concedido ao repositório privado |

Depois de instalar o Gene-In, siga o [guia de montadores](montadores.md). O Builder usa seu próprio ambiente. Sem acesso concedido ao repositório privado, a instalação do Builder para antes de concluir. A ausência do Builder não impede o uso dos outros montadores.

## Conferência rápida

```bash
bash bundle/run.sh genein --version
bash bundle/run.sh genein --help
bash bundle/run.sh genein run --help
```

Essas conferências mostram a instalação e a interface; não validam resultados biológicos. A [documentação técnica preservada](https://github.com/AlexgrothViro/GENE-IN-2.0.0/blob/a61897fbce9c2fdff2a644ece59abaf82aeb8f51/docs/installation-reproducibility.md) detalha locks, recursos e precedência de configuração da base.

[Próximo: uso](uso.md) · [Suporte](suporte.md)
