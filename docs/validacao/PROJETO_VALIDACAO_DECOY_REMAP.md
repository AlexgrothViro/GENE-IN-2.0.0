# Projeto de validação de competição com decoys e remapeamento

- Status: **PROPOSTA DE PRÉ-REGISTRO — NÃO EXECUTAR** (02/11/2026).
- Responsáveis pelas decisões: **Alexsander e Orientador**. Executor previsto: Antigravity, no Argon, após aprovação registrada.
- FATO: este documento não contém resultados de piloto ou de corrida principal. Não foram escolhidos acessos, margem definitiva ou tamanho de amostra.
- Forma: hipótese, métricas, comparadores, portões e decisões pendentes, seguindo a organização da [ADR 0059](https://github.com/AlexgrothViro/genein-builder/blob/c449974a0d6a6946efc75b1a57787791f9717f04/docs/adr/0059-o1-o2-criterios.md). O vínculo é editorial; nenhuma execução do Builder integra este projeto. Referência consultada em 02/11/2026 no commit indicado.
- Limite: planejamento estatístico, rastreabilidade e operação computacional genérica. A escolha e a preparação dos materiais de referência ficam sob responsabilidade dos pesquisadores; este documento não fornece receitas de preparação biológica.

## 1. Pergunta, hipótese e alcance da conclusão

**Pergunta:** ligar a competição com decoys e/ou o remapeamento reduz as atribuições erradas de fragmentos virais curtos sem perder a recuperação correta?

**Hipótese:** pelo menos uma das configurações opcionais reduz a proporção de atribuições erradas em comparação à configuração com as duas opções desligadas, enquanto a perda na recuperação correta permanece dentro da margem de não inferioridade registrada antes da corrida principal.

O estudo avalia entradas simuladas no domínio aprovado pelos pesquisadores. O E2E de software usa strings arbitrárias e verifica funcionamento, recibos e hashes; ele não responde à pergunta científica. No artigo, competição e remapeamento continuam descritos somente como funcionalidades até a validação terminar. Eventuais conclusões posteriores devem ser limitadas aos cenários avaliados, sem extrapolação para uso clínico ou entradas reais.

## 2. Unidade, comparadores e pareamento

**Unidade de análise: a amostra simulada.** Leituras, HSPs, contigs e quatro execuções da mesma amostra não são réplicas independentes.

Cada amostra tem uma entrada imutável e quatro execuções:

| Código | Competição | Remapeamento | Perfil de busca esperado |
|---|---|---|---|
| 00 | desligada | desligado | A |
| 10 | ligada | desligado | A+B |
| 01 | desligada | ligado | A |
| 11 | ligada | ligado | A+B |

O programa recusa B pedido com competição desligada. Os perfis são os existentes, sem mudança de parâmetros. A escolha do montador, ambiente e demais opções deve ser única e congelada para as quatro execuções. O mesmo FASTQ e a mesma verdade de origem, verificados por hash, acompanham o quarteto. A ordem de execução será balanceada e registrada, para separar efeitos de ordem ou cache de diferenças entre opções.

Contrastes planejados: **10−00, 01−00 e 11−00**. A interação `11−10−01+00` será descritiva, identificada como exploração. A estimativa principal por contraste é a média das diferenças dentro da amostra, com pesos dos estratos congelados antes da corrida principal. Não agrupar todas as leituras como se fossem unidades independentes.

Amostras que compartilhem genoma ou clado de origem podem continuar dependentes. O manifesto deve registrar esse agrupamento, e a reamostragem deve preservar todos os quartetos do grupo. A quantidade de grupos independentes também será reportada; aumentar sementes para um único genoma não substitui diversidade de grupos.

## 3. Escopo dos dados solicitado pelo autor

O escopo abaixo transcreve o pedido; não constitui uma seleção de materiais ou protocolo de geração:

| Dimensão | Escopo a representar |
|---|---|
| Vírus | PTV, PSV, SVA e EV-G |
| Comprimento | 20–30, 31–50 e 51–100 pb |
| Fundo | com e sem fundo de hospedeiro suíno |
| Quantidade | poucas leituras por alvo; definição numérica pendente |
| Classes de decoys | parentes próximos, quimeras e regiões conservadas |
| Negativos | amostras sem vírus e amostras contendo somente hospedeiro; registrar se essas classes se sobrepõem |

O número de amostras por combinação, a composição das misturas e a definição de “poucas leituras” são **a decidir por Alexsander e Orientador antes de rodar**. Nem o E2E nem esta proposta atribuem desempenho a essas classes.

### 3.1 Procedência e separação por clado

Os genomas usados como decoy e os usados como origem das leituras devem pertencer a **partições por clado sem sobreposição**. O critério de clado, sua fonte e o nível de atribuição da verdade são decisões científicas pendentes. Uma divisão aleatória de leituras do mesmo genoma não atende a esse requisito.

Antes do selo, os pesquisadores devem preencher um inventário com: identificador de material; acesso NCBI **com versão**; táxon; clado e fonte da classificação; papel no estudo; partição piloto/principal; data de consulta; data de obtenção; URL de origem; hash do arquivo; relação de derivação com outros materiais. **Acessos e datas: A PREENCHER; nenhum acesso é proposto aqui.** Materiais derivados herdam a partição de todos os seus materiais de origem. Uma derivação que atravesse a separação invalida essa entrada antes da corrida.

O piloto e a corrida principal também precisam de conjuntos separados e selados, com a regra de agrupamento documentada. A conferência de vazamento e a identidade dos responsáveis devem ser registradas antes de qualquer análise principal. Não consultar os resultados da partição principal para escolher referências, margem, parâmetros, métrica ou exclusões.

## 4. Régua de avaliação e desfechos por amostra

Antes do piloto, congelar a regra que associa as saídas do programa à verdade dos fragmentos simulados. A implementação dessa régua é uma pendência; a presença de `sample_evidence.json` não demonstra que tal associação já exista. A régua deve ter casos controlados de acerto, erro, abstenção, ambiguidade, duplicação e ausência de saída, revisados pelos responsáveis.

Para a amostra `i`, definir `N_i` como o total de fragmentos elegíveis na verdade de entrada, independente da configuração. Cada fragmento recebe uma decisão avaliável única. Saídas repetidas não podem multiplicar o denominador. Uma atribuição incompatível com a verdade conta como erro, mesmo que venha acompanhada de uma atribuição correta. A regra de ambiguidade, o nível taxonômico exigido e a ligação de saídas compostas à verdade devem ser preenchidos e selados antes do piloto; não serão inferidos de escores observados.

| Desfecho | Definição proposta | Denominador zero |
|---|---|---|
| **Primário: proporção de atribuições erradas** | `E_ic / N_i`, em que `E_ic` é o número de fragmentos com alguma atribuição incompatível com a verdade, na amostra `i`, configuração `c` | entrada sem fragmentos elegíveis é inválida; não transformar em zero |
| **Secundário: recuperação correta** | `C_ic / T_i`, em que `T_i` é o total de fragmentos-alvo elegíveis e `C_ic` é o número recuperado com atribuição correta e sem atribuição incompatível | em negativos sem alvo, não se aplica; reportar N/A |
| Complementares | erradas/total de atribuições emitidas; abstenções; ambiguidade; falhas técnicas; tempo e memória por execução | se nenhuma atribuição foi emitida, erradas/emitidas é N/A |

O denominador fixo do primário mede o risco de atribuir errado por fragmento de entrada. O desfecho de recuperação impede considerar a ausência de todas as atribuições como sucesso. Também reportar numeradores e denominadores, sem substituir proporção por contagem de candidatos. O acordo sobre essa régua é um portão científico, não uma mudança do algoritmo do Gene-In.

Negativos participam do primário e de uma análise descritiva própria; não entram no denominador de recuperação correta. Mostrar resultados com e sem fundo, por faixa de comprimento e por alvo, além do agregado. Os pesos do agregado e a participação dos negativos devem ser definidos antes da corrida principal, sem selecionar estratos pelo resultado.

## 5. Piloto, margem e tamanho de amostra

### 5.1 Margem de não inferioridade

A margem `Δ` é uma **perda absoluta em pontos percentuais** na recuperação correta, não uma variação relativa. Alvo proposto pelo autor: **2 pp**; teto: **5 pp**. O piloto informa a viabilidade, a variância das diferenças e a precisão alcançável. Ele não autoriza aumentar a margem apenas para acomodar uma perda observada.

Alexsander e Orientador devem justificar a perda cientificamente aceitável, escolher `0 < Δ ≤ 5 pp` e assinar o registro. Qualquer afastamento do alvo de 2 pp exige justificativa explícita. Se nenhuma margem aceitável for viável, o estudo é redesenhado antes da corrida principal, sem declarar não inferioridade.

| Registro obrigatório antes da corrida principal | Valor atual |
|---|---|
| Piloto utilizado, hash e data de encerramento | PENDENTE — piloto não executado nesta revisão |
| Margem definitiva `Δ`, em pp, e justificativa | PENDENTE — alvo 2 pp; teto 5 pp |
| Aprovação de Alexsander e Orientador; data UTC | PENDENTE |
| Hash do pré-registro congelado e do plano estatístico | PENDENTE |

### 5.2 Dimensionamento a partir do piloto

**Não existe N calculado nesta entrega:** faltam resultados de piloto e uma diferença mínima relevante para o primário. Um número sem essas entradas seria fictício.

O cálculo deverá usar a variância das **diferenças pareadas por amostra**, a dependência por grupo de origem e a taxa de quartetos tecnicamente incompletos. Registrar também o número de grupos independentes. A meta proposta é 90% de poder para a decisão conjunta dos dois desfechos no contraste 11−00, com a correção de multiplicidade da seção 6; informar o poder obtido para os demais contrastes.

Como aproximação inicial para cada desfecho, usar `n ≈ (z_(1−α/(2m)) + z_(1−β))² × s_d² / g²`, com `m=6`, `α=0,05`, `β=0,10`, `s_d` estimado no piloto. Para o primário, `g` é a redução mínima relevante, decidida antes do cálculo; para recuperação, `g` é a distância da diferença esperada ao limite `−Δ`. A aproximação não resolve agrupamento ou proporções esparsas.

O cálculo final deve reproduzir por simulação estatística a regra pareada da seção 6, usando a estrutura de grupos, os estratos e a distribuição observada no piloto, com sementes próprias. Escolher o menor N que atenda à meta conjunta, acrescentar a perda técnica prevista e arredondar para a alocação planejada. Guardar a curva poder × N, a incerteza da variância do piloto, todos os pressupostos e a justificativa final. Nenhuma dessas simulações é executada nesta revisão. A documentação de [dimensionamento pareado do R](https://stat.ethz.ch/R-manual/R-patched/RHOME/library/stats/html/power.t.test.html) é uma referência computacional para a aproximação, não para os pressupostos do estudo.

## 6. Análise pareada e regra de decisão anterior aos dados

Para cada contraste `c−00`, estimar `D_E = média(E_ic/N_i − E_i00/N_i)` e `D_C = média(C_ic/T_i − C_i00/T_i)`, respeitando os pesos congelados. Diferença negativa no primário favorece menos erros; no secundário, a fronteira de não inferioridade é `−Δ`.

Proposta a aprovar: bootstrap pareado estratificado, reamostrando grupos independentes de origem e mantendo juntos os quatro resultados de cada amostra. Usar os mesmos grupos sorteados para os dois desfechos e todos os contrastes. Fixar antes da corrida principal o gerador, a semente e **99.999 reamostragens**. Reportar IC marginais de 95% e IC simultâneos pela correção de Bonferroni para os seis efeitos planejados: três contrastes × dois desfechos, cada intervalo bilateral com confiança `1−0,05/6` (aproximadamente 99,167%). Essa proposta prioriza uma regra explícita com controle da família; não depende de selecionar o contraste mais favorável.

A documentação de [bootstrap estratificado](https://stat.ethz.ch/R-manual/R-devel/library/boot/html/boot.html), [intervalos bootstrap](https://stat.ethz.ch/R-manual/R-devel/library/boot/html/boot.ci.html) e [ajustes de multiplicidade](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html) descreve as ferramentas estatísticas de referência. O plano deve fixar o estimador de intervalo e sua implementação antes da principal. A proposta é o intervalo percentil; o piloto deve avaliar sua adequação para poucos eventos e agrupamento. Se for inadequado, emendar e selar um plano revisado antes da principal, com justificativa e revisão estatística.

**Regra proposta para cada configuração, usando os intervalos simultâneos:**

1. Evidência de redução de atribuições erradas somente se o limite acima da estimativa de `D_E` estiver estritamente abaixo de zero.
2. Não inferioridade da recuperação somente se o limite abaixo da estimativa de `D_C` estiver estritamente acima de `−Δ`.
3. A configuração atende à pergunta conjunta somente quando **ambas** as condições são satisfeitas e os portões de integridade/avaliabilidade foram cumpridos. Cruzar qualquer fronteira produz resultado inconclusivo para a pergunta conjunta, não equivalência.
4. Se todo o intervalo de `D_C` ficar abaixo de `−Δ`, registrar perda incompatível com a margem. Se todo o intervalo de `D_E` ficar acima de zero, registrar aumento de erros. Não escolher uma configuração vencedora depois de observar os dados.

Distribuição degenerada, ausência de erros no comparador, grupos insuficientes ou pares incompletos podem impedir uma estimativa inferencial válida. Nesses casos, apresentar contagens, limites descritivos quando cabíveis e **NÃO AVALIÁVEL para a decisão correspondente**. Um IC bootstrap [0,0] por ausência de eventos não autoriza uma alegação de redução. Análises por estrato e interação serão descritivas; novas alegações exigem família e dimensionamento pré-registrados.

## 7. Falha, exclusão e o que não pode ser avaliado

| Situação | Tratamento pré-especificado |
|---|---|
| código não zero, processo interrompido, prazo/memória esgotados, ausência de recibo, hash divergente | falha técnica; preservar código, logs e arquivos; reportar por configuração |
| FASTQ inválido, verdade ausente, acesso sem versão, vazamento entre partições, duplicação não prevista | inelegibilidade da entrada, identificada antes da principal; registrar no inventário de exclusões |
| quarteto incompleto durante a principal | manter a amostra no fluxo de contabilização; sem imputar erro zero ou recuperação zero; estimativa pareada somente nos quartetos completos, com análise de sensibilidade previamente aprovada |
| nenhuma saída atribuída em execução tecnicamente válida | abstenção, não falha nem motivo de exclusão; recuperação zero se havia alvo elegível |
| resultado inesperado, muitos erros, perda de recuperação ou estrato difícil | resultado válido; não excluir nem repetir para tentar obter outro resultado |
| nenhum alvo na verdade | recuperação N/A por definição; primário e resumo de negativos permanecem |
| poucos grupos independentes, ausência de eventos, régua ambígua ou margem/N não congelados | decisão estatística não avaliável; sem alegação de desempenho |

O limite aceitável de falhas técnicas, a análise de sensibilidade para dados ausentes e o número máximo de repetições estritamente técnicas são **a decidir antes de rodar**. Até isso ser registrado, falhas que impeçam o pareamento bloqueiam o veredito. Uma repetição técnica usa a mesma entrada, semente e configuração e preserva a tentativa anterior; não constitui nova amostra. Não substituir quartetos após observar métricas.

## 8. Operação computacional genérica no Argon

Esta seção descreve o contrato operacional. Não contém comandos para preparar referências ou gerar material biológico, e não presume recursos do Argon.

### 8.1 Ambiente e versões

Escolher e registrar um commit imutável do Gene-In e um pacote com SHA-256. Usar um prefixo Conda/micromamba novo, sem herdar pacotes de outro ambiente. O projeto já fornece `environment.linux-64.explicit.txt` e `requirements.lock.txt`, com versões e hashes. A compatibilidade do lock Linux x86_64 com o Argon é **A CONFIRMAR**. Congelar também as ferramentas estatísticas e qualquer ferramenta externa aprovada pelos pesquisadores, incluindo os arquivos de lock e seus hashes.

Versões registradas no lock atual como referência de ambiente: Python 3.11.15, BLAST+ 2.17.0, Bowtie2 2.5.5, samtools 1.24 e fastp 1.3.6. A disponibilidade no Argon não foi verificada. Arquitetura, SO, versão do Conda/micromamba, bibliotecas, módulos necessários e acesso à rede: **A CONFIRMAR**. Não substituir versões silenciosamente; uma troca exige novo lock, ensaio de engenharia e emenda anterior à principal.

### 8.2 Lotes e sementes

Manter no repositório do estudo scripts de lote revisados para: verificar ambiente e hashes; listar as unidades aprovadas; submeter os quartetos; recolher recibos; agregar métricas pela régua congelada. Os scripts devem receber manifesto e diretório de saída, preservar os códigos de saída e recusar artefatos antigos como resultado de execução nova. Nenhum script de validação científica é criado ou executado nesta entrega.

Registrar uma semente mestra e a tabela imutável de sementes derivadas para piloto, principal, ordem de execução e reamostragem estatística. As sementes da principal são distintas das do piloto; as quatro opções de uma amostra usam os mesmos arquivos de entrada, sem regenerá-los. **Valores das sementes: A PREENCHER pelos responsáveis antes do selo.**

Agendador e sua sintaxe, filas, módulos, CPUs, memória, limite de tempo, cotas, armazenamento temporário/persistente, política de reenvio e permissões: **A CONFIRMAR com a administração do Argon**. Não há pressuposto de Slurm, PBS ou nomes de módulos. O E2E de software deve passar no ambiente escolhido antes de liberar os lotes; isso não substitui os portões científicos.

### 8.3 Estrutura de saída proposta

```text
estudo/<id-imutavel>/
  preregistro/       # documento, assinaturas, emendas e selo
  ambiente/         # locks, versões, SO, commit e hashes do pacote
  manifestos/       # inventário, partições, quartetos e sementes
  piloto/           # resultados próprios; não reutilizar como principal
  principal/<amostra>/<00|10|01|11>/<tentativa>/
                    # comando, ambiente, logs, código, recibo e artefatos
  avaliacao/        # régua selada, métricas por amostra, análises e IC
  integridade/      # exclusões, falhas, consumo, desvios e checksums
```

Usar SHA-256 para pacote, locks, entradas, verdade, rótulos, bancos, componentes dos índices, régua, manifestos e saídas finais. Verificar antes de submeter e ao recolher. Cada tentativa tem identidade própria e vínculo ao quarteto; um recibo só é válido para os arquivos e a configuração daquela execução. Manter as tentativas e a trilha de emendas em armazenamento com política **A CONFIRMAR** no Argon.

## 9. Portões e decisões de Alexsander e Orientador

| Portão / decisão | Responsável | Situação |
|---|---|---|
| aprovar pergunta, unidade e interpretação dos dois desfechos | Alexsander + Orientador | PENDENTE |
| definir nível de atribuição, ambiguidade e régua entre saídas e verdade | Alexsander + Orientador | PENDENTE; sem régua não rodar piloto |
| aprovar inventário de materiais, acessos NCBI com versão/datas e separação por clado | Alexsander + Orientador | PENDENTE; nenhum acesso selecionado nesta entrega |
| quantificar poucas leituras, misturas, negativos, alocação e pesos dos estratos | Alexsander + Orientador | PENDENTE |
| autorizar e encerrar piloto independente | Alexsander + Orientador | PENDENTE; não executado |
| justificar e registrar margem definitiva, alvo 2 pp e teto 5 pp | Alexsander + Orientador | PENDENTE; antes da principal |
| escolher efeito mínimo relevante do primário e aprovar N/poder calculados do piloto | Alexsander + Orientador, com revisão estatística | PENDENTE; sem N fictício |
| aprovar IC pareados, agrupamento, família de seis efeitos e regra conjunta | Orientador + Alexsander | PROPOSTA nas seções 5–6; requer assinatura |
| fixar tratamento de falhas, ausências e repetições técnicas | Alexsander + Orientador | PENDENTE |
| verificar recursos reais do Argon e congelar ambiente/scripts/sementes | Antigravity + administração, revisão dos responsáveis | A CONFIRMAR |
| selar pré-registro e liberar uma corrida principal | Alexsander + Orientador | BLOQUEADO até os portões anteriores |
| revisar limites da redação do artigo após o estudo | Alexsander + Orientador | funcionalidade apenas, até terminar |

**OPINIÃO:** separar o aceite mecânico do programa, a aprovação do desenho e o resultado científico facilita interpretar o que cada evidência permite afirmar. Esta proposta não é autorização de execução nem alegação de desempenho.
