# Arquitetura e organização

O fluxo canônico usa QC, filtro opcional do hospedeiro, montagem ou resgate, busca por similaridade e exportação de candidatos. A interface e a CLI lançam os mesmos adaptadores de processamento.

```mermaid
flowchart LR
    F[FASTQ ou contigs] --> Q[QC quando aplicável]
    Q --> H[Filtro opcional do hospedeiro]
    H --> A[Montagem e resgate de reads]
    A --> U[Queries com proveniência]
    U --> B[BLAST convencional e curto]
    B --> E[Evidence e relatórios]
    E --> R[Revisão humana e exportação]
```

| Diretório | Responsabilidade |
|---|---|
| `src/genein/` | CLI instalada, lote, estados e Evidence Graph |
| `scripts/pipeline/` | Preparação, QC, filtro, montagem, busca, coleta de queries e relatórios |
| `scripts/evidence/` | Agregação, competição, suporte, classificação e validação de artefatos |
| `scripts/dashboard/` | Servidor local, trabalhos, API e downloads |
| `dashboard/` | Interface, módulos JavaScript e assets locais |
| `scripts/lib/` | Validação de entradas e rotinas compartilhadas |
| `scripts/ops/` | Preparação de bancos, ambiente e operações |
| `config/` | Perfis, alvos e exemplos de configuração |
| `bundle/` | Instalação do ambiente científico e lançadores |
| `tests/`, `scripts/tests/` | Verificações de CLI, contratos e fluxo |
| `scripts/legacy/`, `scripts/experimental/` | Caminhos históricos e estudos explicitamente selecionados |
| `docs/` | Documentação da versão atual |

MULTI reúne sequências dos montadores e registra a origem de cada uma. Ele preserva contigs presentes em apenas um montador; não é consenso de bases. Reads curtos pós-QC/filtro podem ser consultados mesmo quando existem contigs longos. Comprimento de read, comprimento de sequência emitida e comprimento do HSP são unidades distintas.

## Processamento em disco na 2.0.2

O BLAST do resgate é deduplicado por SQLite, sem fallback que carregue todas as linhas em memória. O filtro preserva as duas passagens já presentes na 2.0.1: primeiro escolhe o melhor hit por read, depois grava o ledger de decisões. Também conserva os hashes calculados em blocos; as alterações tratam falhas, mantendo critérios, ordem e vínculos de proveniência. O contrato da 2.0.1 permanece: raw ausente encerra com erro; arquivo existente vazio produz somente cabeçalhos.

A exportação percorre os alinhamentos e grava o TSV completo em fluxo. Para o resumo, conserva um melhor hit e contadores por candidato, em vez de uma lista de todos os alinhamentos. A validação do resumo adota a mesma acumulação incremental. O catálogo de referências FASTA/BLAST, o desempate, a tabela completa e a identidade da execução permanecem disponíveis. Os quatro módulos de disco da b3 — `aggregate_hsps.py`, `build_loci.py`, `build_hsp_evidence.py` e `competitive_hits.py` — são preservados byte a byte em relação à base 2.0.1.

As estruturas por candidato, as sequências e os catálogos ainda usam RAM; o banco temporário e o ledger usam disco. Isso reduz a retenção de linhas nas etapas alteradas, sem fixar um teto global de recursos. A [nota da integração](integracao-memoria-22out.md) identifica o alcance e os limites da atualização. O Builder continua um trabalho separado.

Dados, bancos, ambientes, resultados, caches e evidências de execução são produzidos localmente e não integram a fonte no GitHub. `genein run` exige uma árvore de fonte completa e instalação editável: os adaptadores shell não são incluídos como executáveis independentes em um wheel Python.
