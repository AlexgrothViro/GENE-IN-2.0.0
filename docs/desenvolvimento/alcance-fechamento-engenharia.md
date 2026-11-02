# Alcance do fechamento de engenharia

## FATO

O item (c) solicitado exige análise individual completa até o recibo final.
Essa execução não foi realizada nesta revisão. O teste real novo verifica
somente criação, inspeção e integridade de índices, com diretório e prefixos
contendo espaços. O recibo `index-metadata-receipt.json` declara esse alcance
e registra hashes do banco e de seis componentes do índice.

O teste usa somente duas strings arbitrárias de quatro letras. Não gera
leituras, não faz busca, montagem ou remapeamento. Se as ferramentas de
indexação estiverem ausentes, o resultado é `PULOU` com o motivo.

Há regressões adicionais para referência alterada com builders extras e
aviso de gerações antigas no armazenamento anterior. O aviso preserva os
arquivos antigos; uma falha de listagem não reverte a promoção já concluída.

## OPINIÃO

Avisar sobre gerações antigas é a escolha de menor impacto para esta revisão:
evita retirar arquivos que ainda possam ter uso fora do gerenciador.
O resultado de metadados não satisfaz o aceite integral de (c).
