# Gene-In — recuperação e triagem de sequências

[English](README.en.md) · [Instalação](docs/installation-reproducibility.md) · [Uso e bancos](docs/uso-e-bancos.md) · [Documentação](docs/README.md) · [Citação](docs/citacao.md)

O Gene-In recupera e organiza sequências candidatas de dados de sequenciamento fragmentados para revisão humana. O programa é geral: o hospedeiro e o banco de referência são escolhas de quem analisa. Suíno e picornavírus são apenas o caso-modelo usado na validação, não um limite do programa. Integra controle de qualidade, filtro opcional do hospedeiro, montadores, busca por similaridade, proveniência e exportação. Preserva candidatos de **20–100 pb e maiores**. O resultado depende das entradas, dos adaptadores e das referências; um alinhamento não atribui origem, espécie ou diagnóstico.

**2.0.2 — integração de memória sobre a distribuição 2.0.1, na main desde o PR #2 (`572a827`); o instalador (PR #3) também já está na main.** O contrato Evidence continua `2.0.0-alpha.2`, com recuperação `fragment_recovery_20_100_v1` e revisão `scientific_review_20261005_v1`. A [nota da integração](docs/integracao-memoria-22out.md) explica o processamento em disco, as saídas preservadas e o alcance das verificações. Parâmetros, perfis e locks científicos permanecem os mesmos.

Este é o [repositório](https://github.com/AlexgrothViro/GENE-IN-2.0.0). Entregas publicadas ficam em [Releases](https://github.com/AlexgrothViro/GENE-IN-2.0.0/releases). O [índice de repositórios e histórico](docs/repositorios-e-historico.md) guarda os nomes anteriores.

## Começo rápido

Plataforma: **Linux x86_64 ou Windows x86_64 com WSL2/Ubuntu**. O ambiente científico fixado não atende macOS, ARM ou Windows sem WSL. A primeira instalação precisa de internet. O ZIP/fonte não inclui banco BLAST nem FASTQ de exemplo: prepare um banco e forneça as leituras (veja [uso e bancos](docs/uso-e-bancos.md)).

No Windows, extraia o pacote inteiro em uma pasta permanente, execute `INSTALAR_GENEIN.bat` e depois `ABRIR_GENEIN.bat`. No Linux, na raiz da fonte:

```bash
bash bundle/install_wsl.sh
bash bundle/run.sh test-env
bash run_linux.sh
```

Abra a URL indicada no terminal. O painel roda localmente em `127.0.0.1` e escolhe outra porta se necessário. Mantenha o terminal aberto e use Ctrl+C para encerrar o servidor após os trabalhos. Se faltarem programas como `make` ou `bzip2` e o `apt-get` falhar, a instalação para sem criar o ambiente: instale-os e rode o comando de novo. Veja [instalação e reprodução](docs/installation-reproducibility.md) para pré-requisitos e ambientes separados.

O ambiente científico fica fora da fonte. O prefixo padrão é `~/.gene-in-bundle`. Para outro diretório, exporte `GENEIN_BUNDLE_DIR` antes de instalar, abrir o painel e analisar. O lançador Windows usa o padrão.

Bancos e índices também podem ficar fora da fonte. Com `GENEIN_WORK_ROOT` apontando para um diretório absoluto que já existe, o FASTA padrão de download, o BLAST e o Bowtie2 passam a ser criados ali. Um caminho informado em `REF_FASTA`, `BLAST_DB` ou `BOWTIE2_INDEX` continua onde a pessoa escolheu. A CLI já exige `--output-root` fora da fonte. Para o painel listar essas execuções, exporte `GENEIN_OUTPUT_ROOT` com a pasta que contém as saídas — ou com a própria saída que tem `execution.json` — antes de `bash run_linux.sh`.

Na interface:

1. Em **Nova análise → Banco**, escolha o perfil e use **Preparar banco selecionado**, ou selecione um banco já preparado.
2. Escolha os FASTQ da mesma amostra, o diretório de saída e o montador. **MULTI** reúne Velvet, SPAdes e metaSPAdes; preserva também sequências encontradas por apenas um deles.
3. Informe os adaptadores reais da biblioteca quando houver read-through. Configure o filtro de hospedeiro somente com um índice correspondente e identidade documentada.
4. Confira o estado técnico, os avisos, o suporte e as referências antes de interpretar os candidatos. Exporte as sequências e a proveniência.

O resgate usa SQLite para deduplicar o BLAST em disco, e exportação e validação do resumo são feitas em fluxo. O filtro preserva as duas passagens e os hashes em fluxo que já existiam na 2.0.1, com melhorias no tratamento de falhas e o mesmo contrato: raw ausente é erro; arquivo existente vazio produz somente cabeçalhos. O programa preserva a tabela completa e um melhor hit por candidato, com descrições, táxon e proveniência. Essas mudanças não impõem um teto universal de RAM nem resolvem todo custo de disco. O Gene-In Builder continua separado.

Não mova a fonte após instalar: o pacote usa instalação editável e os adaptadores da mesma pasta. Para dados no porte de 300.000 pares e cerca de 30 milhões de HSPs, o diagnóstico usa **45 GB livres** como aviso de espaço. RAM, tempo e disco variam com biblioteca, banco e montador; consulte [recursos e limites](docs/installation-reproducibility.md#recursos-e-limites).

## Linha de comando

Após instalar e preparar um banco BLAST com manifesto, substitua os caminhos pelos seus arquivos Linux:

```bash
bash bundle/run.sh genein run \
  --sample AMOSTRA_01 --r1 /dados/R1.fastq.gz --r2 /dados/R2.fastq.gz \
  --blast-db /bancos/painel --output-root /resultados/execucao_nova \
  --analysis-profile assembly-consensus --evidence-v2 --threads 2
```

O diretório de saída deve ser **novo e fora da fonte**. Para preparar o banco a partir de um FASTA local, escolha o nome e o arquivo (os índices podem ficar fora da fonte):

```bash
bash bundle/run.sh db DB=meu_banco REF_FASTA=/dados/referencia.fa \
  BLAST_DB=/dados/blastdb/meu_banco BOWTIE2_INDEX=/dados/bowtie2/meu_banco
```

Para SPAdes individual, use `--analysis-profile default --assembler spades`. Não combine `--assembler` com `assembly-consensus`. Entradas single-end, contigs, lotes, controles, filtro de hospedeiro e competição estão em [uso e bancos](docs/uso-e-bancos.md).

```bash
bash bundle/run.sh genein --version
bash bundle/run.sh genein run --help
```

Em bibliotecas com moléculas menores que a leitura, a detecção automática de adaptador pode falhar. Quando conhecidos, passe os adaptadores reais por `QC_ADAPTER_R1` e `QC_ADAPTER_R2` ou pelos ajustes de qualidade da interface. Não há um adaptador universal.

## O que o programa entrega

O Evidence integra contigs, fragmentos montados e reads curtos após QC/filtro; reads maiores resgatados dependem da seleção do resgate. Ausência de montagem útil não impede a consulta dos reads curtos preservados.

| Artefato | Utilidade |
|---|---|
| `candidate_sequences.fa` | Sequências candidatas alinhadas, para revisão e análises posteriores |
| `candidate_sequences.tsv` | Tabela completa: uma linha por alinhamento (query, referência e tarefa) |
| `candidate_summary.tsv` | Uma linha por candidato. O melhor hit é o maior bitscore; `min_evalue` guarda também o menor e-value. Táxon e descrição vêm do rótulo ou do título da referência |
| `candidate_queries.json` | Proveniência e hashes das queries, incluindo as sem candidato alinhado |
| Relatórios Evidence | Estado da execução, suporte, competição, referências e avisos |
| `execution.json` | Recibo técnico da execução iniciada pela CLI |

Confira também a configuração resolvida, os logs e o manifesto do banco. No painel, use os downloads da execução; na CLI, preserve toda a pasta de saída. A tabela de [resultados e interpretação](docs/uso-e-bancos.md#resultados-e-interpretação) explica os estados e as unidades.

**Comprimento do read, comprimento da sequência emitida e comprimento do HSP são medidas distintas.** Repetições da mesma sequência não demonstram moléculas independentes. Cobertura é a união de posições alinhadas por referência/segmento, sem somar referências distintas como um único genoma.

O rótulo exibido no relatório e no painel é `CANDIDATOS_PARA_REVISAO` quando há sequências candidatas, e `SEM_CANDIDATOS_PARA_REVISAO` quando não há. Os arquivos JSON conservam os códigos contratuais `EVIDENCE_RECOVERED` e `DETECTED` (ou `NO_EVIDENCE_RECOVERED` e `NO_SIGNAL`). Essa compatibilidade está na tabela de [resultados](docs/uso-e-bancos.md#resultados-e-interpretação). A qualificação científica permanece `NOT_EVALUATED`. A preferência taxonômica se restringe aos hits rotulados reportados no painel. Empates, competição ausente e suporte não demonstrado precisam permanecer explícitos.

## Alcance, licença e registros

Verificações funcionais sintéticas demonstram caminhos do programa; não estimam sensibilidade clínica, precisão em amostras reais nem recuperação de todo fragmento. A campanha histórica de 27 bibliotecas pertence a outra configuração e conserva **G0.8 reprovado**. Veja [validação científica](docs/validacao.md).

A [Gene-In Limited Public Use License v1.0](LICENSE) permite avaliação acadêmica, ensino e pesquisa não comercial. Redistribuição, modificação e os demais usos restritos dependem de autorização prévia por escrito do titular. Componentes de terceiros mantêm suas [licenças próprias](THIRD_PARTY_NOTICES.md). Consulte [como citar](docs/citacao.md) e registre versão, bancos e parâmetros.

O [índice da documentação](docs/README.md) reúne instalação, utilidades, solução de problemas e desenvolvimento. O [CHANGELOG](CHANGELOG.md) preserva as entregas. Dados, bancos, ambientes e resultados ficam separados do código versionado.
