# Alcance do fechamento de engenharia

## FATO

O PR #10 passou a incluir `make e2e`: quatro execuções individuais reais até o recibo final, com as combinações de competição e remapeamento, referências inteiramente artificiais, FASTQ de 20–100 caracteres e diretório/prefixos com espaços. O executor registra logs e manifesto, verifica hashes e recusa sucesso sem trabalho real nas etapas habilitadas. O mesmo comando é usado no CI.

O teste inicial `test_real_index_metadata.py` continua verificando somente criação, inspeção e integridade de índices; seu recibo não deve ser apresentado isoladamente como E2E. O percurso completo tem outro manifesto e os recibos de cada execução, descritos no [relatório E2E](RELATORIO_E2E_20261102.md).

A [instalação independente](../instalacao-do-zero.md) provisiona ferramentas externas e bibliotecas em bundle novo a partir do pacote, abre o painel e repete esse E2E. Não corresponde à provisão de um SO novo. As evidências iniciais parciais continuam no histórico Git; o relatório atual identifica exatamente o pacote e o ambiente ensaiados.

Regressões adicionais cobrem referência alterada com builders extras, aviso de gerações antigas, conflito B/competição desligada, opções herdadas/ligadas/desligadas e correspondência exata entre IDs e rótulos. Não houve alteração de config/, src/, VERSION, parâmetros, algoritmos, limiares ou perfis científicos, nem execução do Builder ou da validação científica.

## OPINIÃO

O aceite mecânico não responde à pergunta sobre atribuições erradas e recuperação correta. Essa pergunta tem um [pré-registro próprio](../validacao/PROJETO_VALIDACAO_DECOY_REMAP.md), ainda dependente das decisões do autor e Orientador. O PR permanece sem merge para decisão do autor.
