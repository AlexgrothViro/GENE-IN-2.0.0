# Resultados e interpretação

[Início](../../README.md) / [Documentação](../README.md) / Resultados

## Arquivos para revisão

| Arquivo | Uso |
|---|---|
| `candidate_sequences.fa` | Sequências candidatas para revisão |
| `candidate_sequences.tsv` | Tabela completa de alinhamentos reportados |
| `candidate_summary.tsv` | Uma linha de resumo por candidato |
| `candidate_queries.json` | Proveniência das sequências consultadas |
| Relatórios Evidence | Suporte, referências, competição e avisos |
| `execution.json` | Estado técnico e recibo da CLI |

Guarde também configuração resolvida, logs e manifesto do banco. A presença e o conteúdo dos arquivos dependem do caminho executado e do estado final.

## Três coisas diferentes

| Pergunta | O que verificar |
|---|---|
| O programa terminou? | Estado técnico, código de saída e logs |
| Existem candidatos? | Tabelas e sequências reportadas |
| O que eles demonstram? | Evidências, controles, referências e revisão humana |

Uma execução concluída não confirma uma identificação biológica. Ausência de candidatos também não demonstra, isoladamente, ausência de um organismo.

O painel apresenta `CANDIDATOS_PARA_REVISAO` ou `SEM_CANDIDATOS_PARA_REVISAO`. Os códigos históricos dos arquivos estruturados permanecem preservados para compatibilidade. A qualificação científica continua separada do sucesso técnico.

## Ao usar o Builder

Consulte também `builder_raw/` e os arquivos de proveniência da montagem. Os avisos originais são mantidos, mesmo quando o Gene-In publica uma representação padronizada das sequências.

`so_fragmentos` significa que o Builder produziu registros fora da saída principal de contigs. `sem_kmer_valido` e `sem_registros` são tratados como falha registrada pela integração, sem troca automática de montador.

Os avisos do Builder não confirmam quimeras ou variantes. Não há nota de confiança na versão integrada.

## Alcance

Comprimento da leitura, da sequência emitida e do alinhamento são medidas distintas. Repetições de uma sequência não demonstram moléculas independentes. Similaridade não estabelece espécie, infecção ou diagnóstico.

Testes de instalação, formatos e integração verificam engenharia de software. Eles não estimam sensibilidade clínica, precisão em amostras reais ou recuperação completa. Os resultados históricos e suas limitações permanecem na [documentação científica preservada](https://github.com/AlexgrothViro/GENE-IN-2.0.0/blob/a61897fbce9c2fdff2a644ece59abaf82aeb8f51/docs/validacao.md), sem reclassificação nesta edição.
