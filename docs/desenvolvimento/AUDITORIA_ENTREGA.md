# Conferência dos requisitos da entrega

Esta matriz registra a entrega funcional de 02–03/10. A revisão de 05/10 está descrita em [correções científicas](docs/correcoes-cientificas-05out.md), com identidade própria e métricas corrigidas para novas execuções.

Escopo: finalizar o programa para triagem humana, contemplando entrada e emissão20–100pb, com sequências maiores preservadas. A aprovação funcional desta entrega não é aprovação da campanha científica anterior.

| Requisito | Evidência verificável | Resultado |
|---|---|---|
| Reads/moléculas20–100 após QC | Quatro cenários reais, verdade por molécula e comparação exata pós-QC em `VERIFICACAO_REAL/evidencias_fragmentos_final` | Implementado e verificado |
| Candidatos emitidos20–100, inclusive20–54 | Exportações do cenário20pb e mistura20/34/54/74/100; `test_candidate_queries.py` | Implementado e verificado |
| Preservação de candidatos maiores | Fluxo canônico real, seleção filtrada do resgate longo e testes de união | Verificado sem ampliar a busca sensível aos contigs longos |
| Reads curtos com contigs longos de fundo | Inventário pós-QC/filtro e testes do gatilho em `test_short_read_inventory.py` | Gatilho independe do maior contig |
| Montagem sem contigs com reads úteis | Cenário20pb real; tratamento EMPTY e montagem não aplicável; testes do roteador | Reads úteis continuam para busca |
| Integração/proveniência | `candidate_queries.json`, FASTA/TSV e validação transacional de IDs/hashes/origens | Verificado |
| Tamanho emitido distinto de HSP | Campos separados no exportador/fragment_evidence; testes de agregação/exportação | Verificado |
| Triagem, suporte e competição visíveis | Relatório Evidence e tabelas de suporte/competição; controle hospedeiro não TARGET_SPECIFIC; WEAK_RECOVERABLE→REVIEW na nova exportação clássica | Não confirma diagnóstico; ocorrências não equivalem a templates |
| Interface coerente com execução | Testes de payload MULTI/individual/adaptadores, inspeção visual e ambiente WSL pronto | Verificado |
| Candidatos disponíveis ao pesquisador | Três links visíveis após validação; downloads HTTP200 com hashes iguais e nomes corretos | Verificado |
| Abertura com porta ocupada | Execução real do wrapper;8877 ocupada→8878; aguardador Windows lê recibo exclusivo | Verificado |
| Regressões |562 testes finais aprovados em `pytest_entrega_conferida.log`;14 testes JavaScript;65 scripts com sintaxe válida | Verificado |
| Instalação e instruções | Instalação editável isolada verificada, abertura pelo bundle existente e README; arquivos fixados de dependências preservados | Instalação de novo por canais externos não repetida |
| Pacote portátil de código/documentação | ZIP e `CONFERENCIA_PACOTE.json`, CRC e SHA-256 de todos os arquivos | Verificação feita na geração final |
| Preservação da campanha | Cópia de desenvolvimento separada, inventário inicial por hash e plano autoritativo | G0.8 continua reprovado; nenhuma reclassificação histórica |

O estudo fragmentado multissemente proposto na revisão científica continua sendo avaliação científica adicional, não executada por estes testes funcionais. A versão de contrato permanece `2.0.0-alpha.2`; a nova recuperação é identificada como `fragment_recovery_20_100_v1`.
