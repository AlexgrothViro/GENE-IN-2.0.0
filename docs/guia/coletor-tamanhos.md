# Coleta por comprimento e saídas do Builder 3.0 beta

O coletor de Evidence inclui reads FASTQ inteiras de **20 pb ou mais**, contigs e genomas completos FASTA. Não monta um genoma completo por aceitar esse tipo de entrada, não fatia sequências e não confirma origem viral.

- 20–100 pb: rota curta B0 sem mudanças nos perfis/parâmetros existentes.
- >100 pb: rota convencional existente (`blastn`, `word_size=11`).
- FASTQ <20 pb: excluídas como antes, mas agora contadas e avisadas. Aceitação científica nessa faixa depende de decisão futura.
- FASTA <20 pb: comportamento legado preservado, com aviso de especificidade não validada. Não constitui validação dessa faixa.

O `candidate_queries.json` registra `routing_summary` (ocorrências aceitas por faixa, descartes por motivo, queries únicas e deduplicação) e a origem de cada query (`sources`, IDs de read/par, mate e arquivo). A contagem de origens **não** mede templates independentes. Suporte por reads continua exigindo remapeamento das reads originais, sem promover candidatos por multiplicar fragmentos ou ocorrências. Queries iguais são reunidas na mesma orientação; os IDs de contigs são preservados.

O balanço aparece no resumo mínimo e no `evidence_report.md` quando o coletor de Evidence é executado. Evidence desligado não executa esse coletor; este trabalho não altera o caminho legado sem Evidence.

## Importação explícita do Builder 3.0.0b1

O adaptador de montagem e o instalador da branch de origem continuam fixados no **Builder 0.4.0**. Não use `--assembler builder` como promessa de compatibilidade automática com 3.0.0b1. Esta mudança acrescenta a importação técnica explícita do **resultado concluído**, sem executar nem modificar o Builder:

```bash
mkdir -p /caminho/nova_coleta
python scripts/pipeline/collect_candidate_queries.py \
  --builder-manifest /caminho/saida_builder/manifesto_execucao.json \
  --out /caminho/nova_coleta/queries.fa \
  --manifest /caminho/nova_coleta/queries.json \
  --summary /caminho/nova_coleta/balanco.md
```

São lidos `contigs.fasta`, `fragmentos/fragmentos.fasta`, `fragmentos/fragmentos_restritos.fasta` e `nao_montadas_R1.fq.gz`/`nao_montadas_R2.fq.gz`, todos dentro da mesma pasta. O manifesto deve declarar versão 3.0.0b1, `estado=concluido` e `status=ok`; falta de arquivo e links para fora da pasta são erros. O manifesto é somente dado, nunca comando a executar. Não combine essa opção com entradas manuais.

Fragmentos restritos mantêm `ESPECIFICIDADE_NAO_VALIDADA` no manifesto de queries; nenhum corte de 50 pb do Builder é alterado. Reads não montadas de 150 pb entram inteiras na rota longa. Para busca Evidence, passe `queries.fa` por `--queries` e `queries.json` por `--query-manifest` a `scripts/evidence/run.sh`, com o banco/perfil e os controles do experimento. A coleta sozinha não é uma análise nem integração biológica validada.

## Verificação e alcance

Comparação antes/depois pré-registrada e comandos reproduzíveis: [registro científico](../desenvolvimento/coletor-qualquer-tamanho-20261111.md). Testes sintéticos favoráveis com BLAST/Bowtie2 reais verificam invariância da rota curta e admissão de sequências longas. A coleta das saídas reais SRR17241648 é somente operacional; não mede sensibilidade, especificidade ou desempenho em escala. O coletor mantém sequências/proveniência em memória: não foi validado em entradas de milhões de reads.
