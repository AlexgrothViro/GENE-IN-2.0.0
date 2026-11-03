# Comparação competitiva e remapeamento no painel

[Documentação](README.md) / [Uso e bancos](uso-e-bancos.md)

Este guia explica a seleção e a conferência de arquivos previamente preparados
nas opções de **Nova análise**. Ele não é um protocolo de construção de painéis
biológicos nem uma validação dos resultados produzidos por esses métodos.

## Para que serve cada opção

| Opção | Informação que acrescenta |
|---|---|
| Comparação competitiva (decoy) | Permite examinar correspondências com referências que representam explicações alternativas para o resultado |
| Remapeamento de reads | Acrescenta informações sobre o suporte das leituras originais à referência selecionada |

As opções são independentes e começam em **Usar configuração**. Cada escolha
explícita vale para a execução atual. O programa não seleciona automaticamente referências,
contaminantes, tipo de biblioteca ou identificadores moleculares.

## Arquivos que precisam estar disponíveis

Receba os conjuntos preparados, com sua identificação e origem registradas.
Guarde todos os componentes juntos e preserve os arquivos originais.

Para a comparação competitiva, são necessários o prefixo de um banco local,
seu manifesto de integridade e a tabela de rótulos correspondente. Os
identificadores da tabela precisam corresponder ao banco escolhido. A presença
de categorias na tabela não demonstra que o painel represente todas as
explicações alternativas pertinentes.

Para o remapeamento, são necessários o FASTA de referência, seu índice
correspondente e as leituras pareadas da análise. A referência e o índice
precisam representar as mesmas sequências. Declare o tipo de biblioteca de
acordo com os metadados disponíveis; **Não informado** mantém essa limitação
explícita. A escolha não cria UMI nem substitui controles de lote.

## Onde preencher

Abra **Nova análise** e vá à etapa **Configuração**. A seção
**Verificações adicionais (opcionais)** oferece três estados para cada opção:

| Estado | Efeito |
|---|---|
| Usar configuração | Não envia um seletor de presença; herda o arquivo e o ambiente na mesma prioridade da CLI. O painel mostra o valor efetivo e os caminhos herdados |
| Ligado nesta execução | Envia `true`; permite editar os caminhos da execução. Caminhos ainda não editados usam os valores exibidos da configuração |
| Desligado nesta execução | Envia `false` e desliga explicitamente a opção, mesmo quando o arquivo a habilita |

Ao voltar para **Usar configuração**, alterações locais dos campos deixam de
ser overrides. Os campos herdados ficam somente para leitura. A revisão mostra
o valor efetivo e a origem da escolha. Configuração sem seletores continua
usando a presença dos caminhos como nas chamadas anteriores.

Se `SEARCH_PROFILES` pedir B e a competição estiver explicitamente desligada,
a execução é rejeitada com `perfil B pedido, mas a competição está desligada`.
O pedido B não é retirado em silêncio.

| Campo | O que informar |
|---|---|
| Prefixo do banco competitivo | O prefixo indicado na identificação do banco, sem acrescentar a extensão de um dos componentes |
| Tabela de rótulos (TSV) | O caminho da tabela que acompanha esse banco |
| Referência do remapeamento (FASTA) | O caminho do arquivo de referência declarado para a análise |
| Prefixo do índice de remapeamento | O prefixo comum dos componentes do índice, sem a extensão de um componente individual |
| Tipo de biblioteca | A descrição correspondente aos dados, ou **Não informado** quando esse dado não estiver disponível |

O painel aceita caminhos locais Windows e WSL. Em WSL, arquivos de uma unidade
Windows costumam aparecer sob `/mnt/`. Isso não garante que todas as
ferramentas externas aceitem qualquer caminho: suas restrições precisam ser
conferidas na instalação utilizada, inclusive quanto a espaços.

## Conferir antes de continuar

Use **Conferir arquivos opcionais** depois de preencher os campos selecionados.
Se houver desligamento explícito, os caminhos não são enviados como seleção
ativa. Se a opção não for alterada, a conferência usa os caminhos herdados.

A conferência examina:

- Presença do manifesto e integridade dos componentes registrados do banco.
- Estrutura dos rótulos, identificadores duplicados e categorias aceitas pelo contrato.
- Igualdade dos conjuntos de IDs do banco e dos rótulos. IDs do banco sem rótulo
  ou rótulos sem ID no banco interrompem a execução; a mensagem informa o total
  e até 20 exemplos por categoria. A inspeção usa os IDs de acesso retornados
  pela interface pública do banco, sem executar busca.
- Correspondência entre as sequências da referência e as do índice de remapeamento.
- Tipo de biblioteca informado entre as opções aceitas.

**Arquivos opcionais conferidos** significa que essas verificações de arquivos
passaram. Não significa que uma análise terminou, que os rótulos cobrem todo o
banco, que o painel é taxonomicamente completo ou que houve confirmação
biológica. Os arquivos são conferidos novamente na construção do comando.

Na etapa **Revisão**, confira quais opções estão selecionadas e os caminhos
mostrados. Alterações nos arquivos ou nas seleções exigem nova conferência.
O restante do assistente segue os [guia de uso](uso-e-bancos.md).

## Como entender mensagens comuns

| Mensagem ou situação | O que conferir |
|---|---|
| Complete as opções | Campos necessários da opção selecionada ainda estão vazios |
| Manifesto ou rótulos não encontrado | O caminho e a presença dos arquivos que acompanham o conjunto preparado |
| Banco alterado ou incompleto | Se todos os componentes ainda correspondem ao manifesto original; não edite os hashes para contornar o alerta |
| Rótulos inválidos ou duplicados | A tabela recebida e sua correspondência com a identificação do banco |
| Referência e índice incompatíveis | Se os dois pertencem ao mesmo conjunto de referência; não misture arquivos de preparações diferentes |
| Ferramenta de inspeção indisponível | O ambiente de ferramentas da instalação utilizada |
| Nenhuma opção adicional selecionada | A análise está configurada para seguir sem competição e sem remapeamento |

Uma falha externa deve ser examinada no log, com a versão da ferramenta e os
caminhos registrados. A validação do formulário não substitui um ensaio
completo do processamento naquele ambiente.

## Resultados e repetição

Use **Acompanhar**, **Resultados** e **Histórico** para distinguir execução em
andamento, falha, saída parcial e resultado final. A existência de um arquivo
de competição ou suporte, isoladamente, não comprova uso completo do método:
ele pode estar vazio ou registrar indisponibilidade.

**Revisar antes de repetir** recupera as escolhas da execução. Confira os
caminhos novamente, pois os arquivos podem ter mudado. Na revisão de uma
execução antiga sem os novos seletores, as opções começam em **Usar configuração**.

Preserve parâmetros, versões, manifestos, rótulos, referências e logs junto dos
resultados. A interpretação continua condicionada às entradas e às referências;
consulte [guia de resultados e interpretação](uso-e-bancos.md).
