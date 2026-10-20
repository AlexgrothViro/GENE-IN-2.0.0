# Reteste b3 — limites preservados

## U-33-b2 — Velvet

O reteste independente observou contigs diferentes ao repetir Velvet com as mesmas reads e configuração: 5.250 e 5.282 contigs na SUINO02. As diferenças entre os candidatos b1/b2 ficaram nas sequências ≥60 pb. Isso limita a comparação byte a byte de montagens repetidas; não demonstra regressão da b2.

Nenhuma semente foi acrescentada e nenhum parâmetro, thread ou k-mer do Velvet foi alterado. Para comparar mudanças de engenharia posteriores à montagem, reutilize exatamente o mesmo FASTA de contigs e as mesmas reads, conferindo seus SHA-256. Essa equivalência não implica determinismo do montador.

## U-36-b2 — memória do metaSPAdes (parcial)

A b3 avisa quando o limite solicitado excede MemAvailable, sem modificar `-m`, os padrões nem outros parâmetros do montador. O limite máximo não representa reserva de RAM. A redução automática do limite do metaSPAdes não foi implementada porque o autor proibiu alterações nos parâmetros dos montadores; esse aspecto permanece pendente. O ajuste preexistente de SPAdes também foi preservado.

