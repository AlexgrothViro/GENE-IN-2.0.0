# Uso e bancos de referência

O Gene-In não está preso a um hospedeiro nem a uma família viral. Quem analisa escolhe o índice do hospedeiro e o FASTA ou o perfil do banco. Os perfis de picornavírus e o exemplo de Sus scrofa documentam o caso-modelo de validação; outro organismo e outro banco usam os mesmos comandos, com os arquivos correspondentes.

Instale o [ambiente científico](installation-reproducibility.md) e abra `ABRIR_GENEIN.bat` no Windows ou `bash run_linux.sh` no Linux. Os exemplos abaixo usam a CLI da 2.0.1, caminhos Linux e arquivos que devem ser substituídos pelos da sua análise.

## Utilidades e escolha de entrada

| Entrada/uso | Caminho disponível | O que conferir |
|---|---|---|
| FASTQ paired-end | `--r1` e `--r2` | Pares da mesma amostra, nomes e ordem compatíveis |
| FASTQ single-end | `--single` | Montador compatível; metaSPAdes exige pares |
| FASTA já montado | `--contigs` | Origem e parâmetros da montagem; não recupera reads brutos que não foram fornecidos |
| Lote com controles | `--batch-manifest` | TSV do lote, entradas e papéis de cada amostra |
| Comparar a união dos montadores | `--analysis-profile assembly-consensus` | MULTI preserva sequências exclusivas; não é consenso de bases |
| Montador individual | `--analysis-profile default --assembler spades` | Também aceita `velvet` ou `metaspades` quando a entrada é compatível |

A recuperação curta usa `fragment_recovery_20_100_v1`. As buscas convencionais de contigs longos preservam sua política anterior. Não combine `--assembler` com `assembly-consensus`. MULTI usa Velvet, SPAdes e metaSPAdes; o perfil exige pelo menos dois montadores bem-sucedidos e registra as falhas dos demais.

## Bancos: preparar antes de analisar

A composição do banco deve responder à pergunta da análise. O pacote não inclui referências biológicas ou índices prontos. O gerenciador registra FASTA, hashes, ferramentas e manifestos e promove o banco preparado de forma transacional.

No painel, use **Nova análise → Banco → Preparar banco selecionado** e depois **Continuar nova análise**. A alternativa fica em **Área avançada → Configuração técnica → Preparar banco**. Há perfis históricos e consulta NCBI personalizada. Verifique consulta, fontes, accessions/versões e composição antes do uso; o nome de um perfil não garante especificidade biológica.

Para listar perfis e preparar o perfil histórico de PTV:

```bash
bash bundle/run.sh db-list
bash bundle/run.sh db DB=ptv
```

Para montar um banco a partir de um FASTA seu, escolha o nome e o arquivo. O nome não precisa ser um perfil NCBI. O FASTA não é copiado para dentro de um perfil:

```bash
bash bundle/run.sh db \
  DB=meu_banco \
  REF_FASTA=/dados/referencia.fa \
  BLAST_DB=/dados/blastdb/meu_banco \
  BOWTIE2_INDEX=/dados/bowtie2/meu_banco
```

`REF_FASTA` é o arquivo de referência. `DB` é o nome do banco. `BLAST_DB` e `BOWTIE2_INDEX` podem apontar para pastas fora da fonte. Se forem omitidos, os índices ficam em `blastdb/<DB>` e `bowtie2/<DB>` dentro da fonte. Com `GENEIN_WORK_ROOT` apontando para um diretório absoluto existente, esses padrões e o FASTA de download passam para esse diretório. O painel inclui execuções de fora da fonte quando `GENEIN_OUTPUT_ROOT` aponta para a pasta das saídas. O mesmo vale na chamada direta, sem o wrapper:

```bash
DB=meu_banco REF_FASTA=/dados/referencia.fa \
  BLAST_DB=/dados/blastdb/meu_banco \
  BOWTIE2_INDEX=/dados/bowtie2/meu_banco \
  bash scripts/ops/db_manager.sh setup
```

Na linha do `make`, `DB_QUERY` também é repassado ao gerenciador. Uma consulta NCBI continua possível com `DB=custom DB_QUERY=...` quando não houver FASTA local. Se o arquivo em `REF_FASTA` não existir, o comando para e informa o caminho; ele não pede um perfil NCBI no lugar do arquivo.

O prefixo lógico do exemplo histórico é `blastdb/ptv`, na pasta da fonte. Para usá-lo na CLI, informe seu caminho absoluto. A CLI não baixa banco automaticamente e exige o manifesto correspondente `<prefixo>.db-manifest.json`. Preserve a estrutura completa do banco e as gerações internas ao copiar; um arquivo `.nin` sozinho é insuficiente. Não crie um manifesto vazio para contornar a validação.

Mantenha as versões do banco usadas em análises anteriores. Uma consulta NCBI repetida em outra data pode produzir um conjunto diferente. Conserve também o FASTA original, a consulta, a data, os hashes e os termos de uso das referências.

## Exemplo paired-end com MULTI

Use um diretório de saída novo, fora da árvore do programa:

```bash
bash bundle/run.sh genein run \
  --sample AMOSTRA_01 --r1 /dados/R1.fastq.gz --r2 /dados/R2.fastq.gz \
  --blast-db /bancos/painel --output-root /resultados/execucao_nova \
  --analysis-profile assembly-consensus --evidence-v2 --threads 2
```

As entradas FASTQ podem estar comprimidas ou sem compressão. O diretório indicado em `--output-root` não pode existir; cada repetição recebe uma pasta nova. Guarde a pasta inteira depois de concluir.

Para limitar a memória solicitada pelo SPAdes individual:

```bash
bash bundle/run.sh genein run \
  --sample AMOSTRA_02 --single /dados/reads.fastq.gz \
  --blast-db /bancos/painel --output-root /resultados/execucao_single \
  --analysis-profile default --assembler spades \
  --spades-params='-m 4' --evidence-v2 --threads 2
```

`-m 4` é um exemplo de limite em GB do SPAdes, não um requisito universal. Verifique a compatibilidade com a biblioteca e os [limites de recursos](installation-reproducibility.md#recursos-e-limites).

## FASTA já montado

```bash
bash bundle/run.sh genein run \
  --sample CONTIGS_01 --contigs /dados/contigs.fa \
  --blast-db /bancos/painel --output-root /resultados/execucao_contigs \
  --evidence-v2 --threads 2
```

Esse caminho analisa as sequências fornecidas e conserva seus vínculos de evidência. Sem reads brutos não há como medir suporte por remapeamento de reads ou reconstruir os fragmentos que faltaram à montagem. Registre essa limitação.

## Adaptadores e configuração persistente

Quando houver read-through, passe as sequências reais da biblioteca. Exemplo de formato, a substituir por sequências A/C/G/T/N reais:

```bash
QC_ADAPTER_R1=SEQUENCIA_REAL_R1 QC_ADAPTER_R2=SEQUENCIA_REAL_R2 \
  bash bundle/run.sh genein run \
  --sample AMOSTRA_03 --r1 /dados/R1.fastq.gz --r2 /dados/R2.fastq.gz \
  --blast-db /bancos/painel --output-root /resultados/execucao_adaptadores \
  --analysis-profile assembly-consensus --evidence-v2 --threads 2
```

Os textos `SEQUENCIA_REAL_R1/R2` são marcadores, não adaptadores válidos. Omita as variáveis quando não souber as sequências; confira o QC e a distribuição de comprimentos. A detecção automática falhou em um dos cenários históricos de moléculas de 20 pb com adaptador; não se presume um adaptador universal.

Para persistir ajustes locais, copie o exemplo para o diretório de trabalho. Com `GENEIN_WORK_ROOT` apontando para um diretório absoluto existente:

```bash
mkdir -p "$GENEIN_WORK_ROOT/config"
cp config/picornavirus.env.example "$GENEIN_WORK_ROOT/config/picornavirus.env"
```

Sem essa variável, o painel grava em `~/.gene-in/config/picornavirus.env`. `GENEIN_CONFIG_FILE` escolhe outro caminho. O painel não cria `config/picornavirus.env` dentro da fonte. A leitura, no Make, nos scripts e no painel, segue `GENEIN_CONFIG_FILE`, depois o arquivo do diretório de trabalho, depois `~/.gene-in/config/picornavirus.env` e por fim a cópia da fonte. O banco BLAST usa a mesma ordem; o detalhe está em [instalação e reprodutibilidade](installation-reproducibility.md). Na 2.0.0 essa leitura ficava só na fonte. Edite a cópia conforme entradas, banco, recursos, hospedeiro e adaptadores da análise. O nome vem do desenvolvimento histórico com picornavírus e não define um alvo universal. Os perfis JSON versionados e os parâmetros científicos devem conservar sua identidade; confira a configuração resolvida nos resultados.

## Filtro do hospedeiro

O filtro é opcional. Prepare o índice separadamente com a referência correta e veja o [guia de hospedeiro](HOSPEDEIRO_BETA.md). Para habilitá-lo na CLI, acrescente ao comando:

```text
--host-index /bancos/hospedeiro_bt2 --host-name NOME_DO_HOSPEDEIRO
```

O prefixo deve apontar aos seis componentes Bowtie2 `.bt2` ou `.bt2l`, sem acrescentar `.1.bt2`. Informe `--host-accession` quando houver accession documentado. Não combine `--host-index` com `--skip-host-filter`.

O padrão `--host-expected true` mantém a baixa taxa de alinhamento como falha. `--host-expected false` permite esse cenário com aviso quando a expectativa experimental justificar. Saturação total de hospedeiro é registrada como desfecho concluído reconhecido. Escolha a expectativa antes de observar o resultado. Com o filtro desligado, sequências de hospedeiro podem permanecer entre as queries e candidatos.

## Competição e controles

Um banco apenas viral mede similaridade dentro daquele conjunto; não demonstra especificidade contra hospedeiro, contaminantes ou vírus próximos. Um painel composto deve conter alvos e competidores curados, com `subject-labels` cujos `sseqid` correspondam às referências.

Para uma execução com competição, acrescente:

```text
--composite-db /bancos/painel_composto --subject-labels /bancos/labels.tsv
```

O banco composto também exige manifesto. O utilitário [build_competitive_panel.py](../scripts/evidence/build_competitive_panel.py) cria FASTA e labels a partir das categorias `TARGET_VIRUS`, `NEAR_NON_TARGET_VIRUS`, `HOST`, `VECTOR_ADAPTER`, `KNOWN_CONTAMINANT` e `SYNTHETIC_SEQUENCE`; a construção/manifestação do banco BLAST é uma etapa separada. Consulte seu `--help` no ambiente científico. O utilitário não faz a curadoria científica do painel.

Use papéis explícitos: `sample`, `positive`, `negative_extraction`, `negative_library` ou `negative_sequencing`. Controle positivo exige `--expected-target` preenchido. Falta de controles, competição ou suporte precisa permanecer visível; não equivale a evidência favorável.

## Lotes

O manifesto de lote é um TSV com colunas `batch_id`, `sample_id`, `role`, `library_mode`, `umi_mode`, `r1`, `r2` e `expected_target`. Deve ter um único `batch_id`, identificadores de amostra únicos, pelo menos uma linha `sample` e pares FASTQ válidos sem reutilizar os mesmos arquivos em outra amostra. Caminhos relativos são resolvidos a partir da pasta do TSV.

`library_mode` aceita `shotgun`, `amplicon`, `targeted` ou `unknown`; `umi_mode` aceita `none`, `read_name` ou `tag`. Use somente o modo que corresponda aos dados; UMI exige biblioteca conhecida. `expected_target` é obrigatório no positivo e pode ficar vazio nos demais papéis.

```bash
bash bundle/run.sh genein run \
  --batch-manifest /dados/lote.tsv --blast-db /bancos/painel \
  --output-root /resultados/lote_novo --threads 2
```

O lote já usa Evidence. Entradas, papéis e metadados vêm do TSV; não combine `--batch-manifest` com `--sample`, entradas individuais ou metadados individuais. O lote exige denominadores pós-QC medidos e não aceita `--skip-qc`.

## Resultados e interpretação

Na execução individual pela CLI, o recibo fica em `<output-root>/execution.json`; os artefatos Evidence concluídos ficam em `<output-root>/results/evidence/runs/<run-id>/`. Estados e staging são mantidos em pastas próprias sob `results/evidence`. Os diretórios de lote também preservam as amostras e a consolidação. No painel, use os artefatos da execução selecionada.

| Arquivo/campo | Leitura correta |
|---|---|
| `candidate_sequences.fa` | Sequências com alinhamento, disponíveis para revisão; não necessariamente de origem viral confirmada |
| `candidate_sequences.tsv` | Tabela completa: uma linha por alinhamento (query, referência e tarefa) |
| `candidate_summary.tsv` | Uma linha por candidato. O melhor hit é o de maior bitscore; no empate, o menor e-value e, em seguida, a maior identidade. `min_evalue` é o menor e-value entre todos os hits desse candidato e pode pertencer a outro subject. `reference_description` é o título da referência. `taxon` usa o rótulo do sujeito quando ele existe; sem rótulo, usa o organismo lido nesse título. `category` continua sendo o rótulo e fica `UNLABELED` quando não há arquivo de rótulos. `hit_row_count` é o número de linhas desse candidato na tabela completa |
| `candidate_queries.json` | Queries consultadas e hashes; pode incluir sequências sem candidato alinhado |
| `evidence_report.md` / `sample_evidence.json` | Evidência, estados, avisos e medidas da amostra |
| `run_state.json` / `artifact_manifest.json` | Estado final e integridade dos artefatos Evidence |
| `execution.json` | Recibo do lançador da CLI; `completed` indica término técnico |

`SUCCESS.json` é um marcador de finalização. No caminho legado `results/runs/<id>/SUCCESS.json`, o contrato histórico permite `status=failed`: leia os campos e os logs, não deduza sucesso pelo nome do arquivo. Resultado incompleto ou falha técnica não é ausência biológica.

| Medida/estado | Significado |
|---|---|
| Comprimento do read | Sequência lida no FASTQ; QC pode retirar adaptadores e bases |
| Comprimento do candidato/contig | Sequência inteira emitida e exportada |
| Comprimento do HSP | Trecho alinhado a uma referência; pode ser menor que o candidato |
| `CANDIDATOS_PARA_REVISAO` | Rótulo exibido quando há sequências candidatas. No JSON, os códigos contratuais equivalentes continuam `EVIDENCE_RECOVERED` e `DETECTED` |
| `SEM_CANDIDATOS_PARA_REVISAO` | Rótulo exibido quando a execução terminou sem candidato. No JSON, os códigos equivalentes continuam `NO_EVIDENCE_RECOVERED` e `NO_SIGNAL` |
| `DETECTED` / `EVIDENCE_RECOVERED` | Códigos contratuais antigos, ainda gravados nos JSON. A leitura pública correspondente é `CANDIDATOS_PARA_REVISAO` |
| `NOT_EVALUATED` | Qualificação científica não realizada; disponibilidade não preenche contagens de qualificação |
| `PANEL_TAXON_PREFERRED` | Preferência entre hits rotulados reportados no painel |
| `AMBIGUOUS` | Empate ou separação insuficiente |

`WEAK_RECOVERABLE` aparece como `REVIEW` na exportação clássica. Contagens de sequências repetidas não demonstram moléculas independentes. `total_nonredundant_reference_bp` usa a união de posições por referência/segmento entre loci, orientações e perfis; mede bases alinhadas, sem confirmar origem. Consulte `reference_coverage.by_reference` e não some referências distintas como cobertura de um único genoma.

Preserve entradas e hashes, configuração resolvida, manifestos dos bancos, logs, relatórios e exportações. Ausência de candidatos não comprova ausência de vírus. Veja os [limites de validação](validacao.md) e [como citar a execução](citacao.md).
