# Montadores

[Início](../../README.md) / [Documentação](../README.md) / Montadores

## Escolher uma opção

| Opção | Como aparece |
|---|---|
| Velvet | Montador individual |
| SPAdes | Montador individual |
| metaSPAdes | Montador individual, com requisitos próprios de entrada |
| MULTI | Combinação de Velvet, SPAdes e metaSPAdes |
| Gene-In Builder | Montador adicional, instalado separadamente |

O Builder não é acrescentado automaticamente ao MULTI. A seleção é explícita, no painel ou na CLI.

## Instalar o Builder

A integração usa **Gene-In Builder 0.4.0**. Depois da instalação principal, execute na raiz do Gene-In, em Linux/WSL:

```bash
bash bundle/install_builder.sh
```

O instalador cria `builder-env` dentro do diretório definido por `GENEIN_BUNDLE_DIR`, ou em `~/.gene-in-bundle/builder-env` no padrão. Esse ambiente é separado do ambiente principal: os locks e as dependências científicas existentes não são substituídos.

O código do Builder está fixado no commit `af7cb088b3013df07fd3abfaa23ba89dba42cf6b`. O repositório é privado; a conta usada pelo Git deve ter acesso. Não coloque tokens em arquivos do projeto.

As dependências Python do ambiente opcional são resolvidas pelo pip. O commit fixa a fonte do Builder, não um lock completo de suas dependências transitivas. Registre o ambiente usado quando precisar reproduzir uma execução.

## Conferir e selecionar

```bash
python3 scripts/pipeline/assemblers/builder_adapter.py check
```

Esse comando confere a disponibilidade e a versão sem montar sequências. Se usar outro `GENEIN_BUNDLE_DIR`, mantenha a variável definida também para a conferência e para abrir o programa.

- **Painel:** selecione **Gene-In Builder** na configuração da nova análise.
- **CLI:** selecione `--analysis-profile default --assembler builder`, junto dos demais argumentos exigidos na ajuda.

O adaptador exige a versão 0.4.0. Um pacote ausente, incompatível ou com falha produz erro explícito; não dispara outro montador como substituto.

## O que é preservado

O adaptador entrega os registros ao fluxo do Gene-In e mantém as saídas originais do Builder em `builder_raw/`, dentro da pasta de montagem da amostra. Ali ficam o manifesto, as tabelas e os avisos da versão usada.

Versão, commit efetivamente reportado, motor e estado são registrados em `builder_provenance.env` e em `assembly_metadata.env`. Uma diferença entre o commit instalado e o fixado gera aviso. Registros presentes tanto nos contigs quanto nas tabelas de fragmentos são publicados uma única vez.

O adaptador não declara um hospedeiro presumido. Isso mantém os avisos de escopo do próprio Builder quando esse contexto não está informado.

## Limitações

O Builder realiza montagem, não identificação viral. Seus avisos não confirmam variantes nem quimeras, e a versão 0.4.0 mantém a nota de confiança desligada. A compatibilidade de software não acrescenta validação científica.

O motor padrão da integração é `v1`. A opção técnica `BUILDER_MOTOR=megahit` exige o executável MEGAHIT compatível, instalado separadamente e acessível no ambiente da execução; o instalador opcional não o instala. Não há recomendação automática de motor para uma amostra.

[Documentação do Builder](https://github.com/AlexgrothViro/genein-builder/tree/trabalho/software-documentado) · [Resultados e limites](resultados.md)
