# Registro prévio: coletor de sequências de qualquer tamanho

Data: 11/11/2026 (America/Sao_Paulo). Base B0: `18c686310e52ca87ee3a5ca46d9ff73952914263`, branch `trabalho/software-builder` (PR #6, integração com testes). `trabalho/software-documentado` é distribuição sem a suíte; main não é destino desta mudança. AGENTS.md, CLAUDE.md e CONTEXTO não existem nesta base; lidos os guias de desenvolvimento e correções científicas disponíveis.

## Motivo e escopo aprovados
O coletor anterior ignorava FASTQ >100 pb e <20 pb silenciosamente. Decisão de Alexsander: sequências longas, contigs e genomas completos não podem ser ignorados. Não fatiar nem aparar. Preservar identidade original de read/par na proveniência, sem transformar ocorrências em templates independentes.

## Plano antes de alterar código
- Preservar IDs hash, deduplicação, parâmetros, níveis, suporte e empates da rota 20–100 pb (B0).
- Incluir reads >100 pb na rota convencional existente (blastn, word_size 11); não mudar blast_router nem os critérios científicos.
- <20 pb em FASTQ: manter exclusão de B0, contar e avisar; FASTA <20 mantém comportamento existente, com ressalva explícita de não validação.
- Contabilizar ocorrências por origem e tamanho e queries únicas; distinguir descartes de deduplicação. Manifesto e relatório legível devem mostrar o balanço.
- Verificar contrato Builder: o adaptador existente é 0.4.0, diferente de 3.0.0b1. Importação explícita de resultados 3.0 concluídos pelo coletor, sem declarar compatibilidade do instalador/adapter 0.4. Preservar ESPECIFICIDADE_NAO_VALIDADA dos fragmentos restritos.

## Comparações pré-definidas
1. Mesma entrada sintética 20,34,54,74,100 pb e mesmo ambiente/banco: B0 vs novo coletor, FASTA e resultados científicos idênticos (candidatos, níveis, suporte, empates). Diferenças novas somente em proveniência e balanço.
2. Fronteiras 19/20/100/101/150, pares, duplicatas exatas, contigs e genoma sintético completo: inclusão inteira e roteamento longo, sem inflação de suporte.
3. Resultados reais SRR17241648 do Builder: antes 3.078 reads não montadas de 150 pb ignoradas, depois todas contabilizadas. Teste operacional de coleta, não validação biológica nem benchmark.
4. Suíte de engenharia inteira; ferramentas ausentes registradas como não executadas. Nenhuma carga pesada.

Resultados e limitações serão acrescentados em commit posterior. Sem merge, tag ou alteração de main/Builder/Desktop.
