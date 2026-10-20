# Estado atualizado — reteste b3, 09/10/2026

Esta tabela substitui os estados históricos abaixo para os 23 itens solicitados. Relatos originais e referências às evidências externas foram preservados. U-36-b2 continua parcial; U-33-b2 foi somente documentado conforme solicitado.

**Rodada final (09/10/2026).** O resíduo de rótulo e de `failed_stage` de U-42-b2 foi fechado em `517b8af56a9cbcc4aee12162e26f861288f7084a`. O registro da entrega deixou de afirmar o resultado dos testes de estado/API em `62a79b99e1b1ca1f9d570c3ccdad649db2f7a09f`. O cenário de banco composto ausente voltou ao E4 em `03109042d4d9dd219fc1fd23721ec2bec3c0e4f4`, junto com o cenário de labels ausentes. `source_archive_sha256` deixou de repetir o arquivo da b1 em `1f746387f988c0058be9b10920b6e56a48388097`. U-36-b2 segue parcial, o Velvet segue não determinístico, o BLAST convencional e o de contigs seguem sem blocos, a interface não foi reaberta no navegador e `SUCCESS.json` em execução falha não foi renomeado.

**Agregação de HSPs (10/10/2026).** U-48-b3 foi corrigido em `0da4e39f4ab1268a7c4339ddaf875290fae77074`: a agregação não grava mais cada HSP como JSON no SQLite. Em 1.999.830 linhas sintéticas a saída teve o mesmo SHA-256 e o pico de disco caiu de 870,2 MiB para 63,8 MiB (RSS 47,8 MiB e 47,0 MiB). U-49-b3 foi corrigido em `e54b065c102b7d24dade1676abf4fa9a471a1a54`: o mesmo tratador de SIGTERM do roteador remove o temporário `genein-hsps-*` e o processo sai com 143. SIGKILL continua sem limpeza pelo próprio processo.

**Disco nas etapas seguintes (10/10/2026).** U-50-b3r foi corrigido em `a56de169e5310327f6a9ff10110e7bdbf5e8a8ac`: na AMOSTRA01 a agregação deixou quase uma linha por HSP, e o SQLite de `build_loci.py`, `build_hsp_evidence.py` e `competitive_hits.py` passou a encher o disco. Essas etapas agora usam fluxo ou ordenação compacta em `--work-dir`, com preflight em português. Em 400.000 linhas sintéticas de uma linha por HSP, o SHA-256 de loci e da comparação competitiva é igual ao do SQLite anterior. Picos: loci 267,6 → 165,6 MiB; competitiva 461,4 → 150,0 MiB; evidência de HSP 218,0 MiB; agregação sem colapso 169,3 MiB. O diagnóstico avisa abaixo de 45 GB livres. Remapeamento até a finalização da AMOSTRA01 completa não foi reexecutado. U-51-b3r foi corrigido em `24fee6496ceadd829b86a7eeb8e3ba41a07a42f4`: SIGTERM nessas três etapas desfaz o temporário e sai com 143. SIGKILL continua sem limpeza pelo próprio processo.

| Item | Estado na b3 | Commit | Correção e limite |
|---|---|---|---|
| U-45-b2 | corrigido | `1fa90b6106f8` | BLAST curto em blocos de 256 queries, tanto no resgate quanto no roteamento. Equivalência real das saídas curta, convencional, combinada e proveniência contra a b2; blocos de 3 e 256, um e dois threads, ambas as políticas de roteamento. AMOSTRA01 completa não foi reexecutada; não há novo pico de RAM medido nessa amostra. |
| U-37-b2 | corrigido | `b150e4ebfbc8` | API recusa alvo ausente, vazio e apenas espaços antes de criar job (HTTP 400). Assistente bloqueia a execução e exige alvo; reexecução conserva o alvo declarado. Mensagem em português. |
| U-35-b2 | corrigido | `c505911727d3` | CLI e adaptadores exigem manifesto para o banco composto; integridade conferida antes de QC. Fixtures dos testes reais passaram a produzir os manifestos dos próprios índices. |
| U-42-b2 | corrigido com limite | `517b8af56a9c` | QC fastp em QC_FASTP; resgate e BLAST [5/6] em RESCUE_READS e BLAST. Falha de integridade ou banco composto fica database_preflight no log, no estado, no painel e no recibo. Recibo da CLI alinha SIGKILL, SIGTERM e falta de memória ao painel. Commit anterior do item: `aeb4a01c5302`. `SUCCESS.json` em execução falha permanece. |
| U-39-b2 | corrigido | `87dd08597d01` | Arquivo bruto ausente causa falha sem TSV de sucesso. Arquivo existente vazio continua válido. Candidatos, decisões e proveniência mantêm equivalência byte a byte. |
| U-46-b2 | corrigido | `aa526c17dcfa` | Falha de comando e SIGTERM liberam TemporaryDirectory; testes de processo verificam ausência de resíduos. SIGKILL e desligamento abrupto não permitem limpeza pelo próprio processo. |
| U-33-b2 | documentado — escopo solicitado atendido | `3397dbdaba2e` | Variabilidade observada do Velvet documentada. Nenhum parâmetro, thread ou semente alterado; não se declara determinismo do montador. |
| U-34-b2 | corrigido | `14f6db8bf112` | run_linux.sh e bundle/run.sh recusam ausência de make com orientação em português antes de chamar o ambiente. Testados os dois caminhos. |
| U-36-b2 | PARCIAL | `b43ab0e45fe2` | Aviso quando -m excede MemAvailable. O valor -m 64 e o comportamento do montador foram preservados por instrução do autor. Ajuste automático do limite permanece não implementado; não marcar como corrigido. |
| U-38-b2 | corrigido | `97645123df02` | O comando do painel usa o par .fastq existente, mantendo preferência histórica pelo par .fastq.gz quando ambos existem. Seleção e integridade dos bytes testadas. |
| U-40-b2 | corrigido | `606746e42d58` | Versão 2.0.0b3 em metadados e guias atuais; changelog inclui b2/b3. A verificação da b1 foi identificada como registro histórico, sem reatribuir seus resultados à b3. |
| U-41-b2 | corrigido | `9bd505230e8f` | Descoberta de engenharia exclui o arquivo de testes das trilhas de otimização. Imports de optimization e contract_selftest são tardios, exclusivos das trilhas correspondentes. Teste bloqueia qualquer import de optimization ao carregar all-safe. |
| U-43-b2 | corrigido — verificação estática | `6c42fc47d506` | Desinstalação global usa MAMBA_ROOT_PREFIX, que está definida. ShellCheck aprovado; desinstalação real não executada para preservar o ambiente. |
| U-44-b2 | corrigido | `4c4debb7f069` | Revalidar arquivos invalida o veredito concluído em cache. API aceita refresh=1; resultado inválido orienta conferir erros/revalidar, sem exigir automaticamente nova análise. Critérios de integridade preservados. |
| U-47-b2 | corrigido | `2666dbc0acf3` | Rótulo Sus scrofa explicita que exige índice preparado separadamente; ausência continua recusada com segurança. |
| P-01 | corrigido | `fd68153993ca` | Complemento de U-34-b2: documentação registra os dois launchers, orientação de instalação e testes de make ausente. Instalação real via sudo não foi necessária nem executada. |
| P-02 | corrigido | `98b1045150dc` | A ação bash bundle/install_wsl.sh aparece junto à dependência obrigatória ausente, inclusive make, e no resumo do diagnóstico. |
| P-05 | corrigido | `d0dc54af86ee` | Complemento de U-35-b2: manifesto adulterado produz código 65 e recibo INPUT_INVALID/database_preflight. Mensagem não anuncia banco validado antes de conferir integridade; banco íntegro não é alterado. |
| P-07 | corrigido | `43106f903682` | Comandos de preparo do diagnóstico usam bundle/run.sh. Banco pronto dispensa aviso de FASTA adicional ausente; MemAvailable/unidades anteriores preservadas. |
| P-08 | corrigido no escopo dos achados do reteste | `92eba6d71848` | Pareamento só é anunciado após validação integral. Erros de FASTQ explicam a regra e ação em português; controle positivo sem alvo foi traduzido. Mensagens normais citadas no reteste e seletor de arquivos estão em português. Logs técnicos originais de ferramentas de terceiros não são reescritos. |
| P-11 | corrigido | `7b053a6bc8ef` | Cabeçalho, configuração efetiva e encerramento do log apresentam MULTI; identificador técnico consensus continua inalterado nos contratos. |
| U-05 | corrigido | `61325884955e` | Barra mostra progresso de envio por eventos reais do navegador; validação no servidor é uma fase distinta. FormData não é transformado; HTTP 409 e confirmação de substituição preservados. |
| U-15 | corrigido | `097f86343ad6` | Aviso individual quando uma sequência candidata excede a maior referência alinhada registrada. É orientação de revisão, sem inferir hospedeiro/origem, alterar filtros ou arquivos de candidatos. Teste confere exportações idênticas. |
| U-48-b3 | corrigido | `0da4e39f4ab1` | Agregação em fluxo por consulta, com ordenação só da tabela agregada. Saída com o mesmo SHA-256 do SQLite anterior em empates, dois perfis, consulta sem HSP, ordem entrelaçada e o mesmo task em dois arquivos. Preflight de espaço livre em português. Temporário no diretório da execução. Medição: 1.999.830 linhas, disco 870,2 MiB → 63,8 MiB. |
| U-49-b3 | corrigido | `e54b065c102b` | SIGTERM na agregação desfaz o TemporaryDirectory e sai com 143, no mesmo padrão do roteador. Teste de processo com FIFO. SIGKILL não pode ser limpo pelo próprio processo. |
| U-50-b3r | corrigido | `a56de169e531` | Loci, evidência de HSP e comparação competitiva deixam de copiar cada linha como JSON no SQLite em `/tmp`. Temporário em `--work-dir`. Preflight por etapa. Em 400.000 linhas sem colapso, SHA-256 igual ao caminho antigo. Diagnóstico avisa abaixo de 45 GB livres. A AMOSTRA01 completa não foi reexecutada até o fim. |
| U-51-b3r | corrigido | `24fee6496cea` | SIGTERM em `build_loci.py`, `build_hsp_evidence.py` e `competitive_hits.py` desfaz o temporário e sai com 143. Teste de processo com FIFO em cada etapa. SIGKILL não pode ser limpo pelo próprio processo. |

---

# Gene-In 2.0.0b1: lista viva de problemas para correção

> **Revisão de engenharia b2:** 42 itens corrigidos com commits individuais; P-08 permanece aberto (correção parcial da apresentação e das mensagens citadas). Perfis, limiares, faixas e valores padrão científicos preservados. Decisões científicas pendentes continuam com o autor. Evidências e limites: [correções da b2](docs/correcoes-usabilidade-b2.md). O texto histórico abaixo descreve o teste externo da b1.

> **Atualização SUINO01c (08/10/2026, ~18:00 BRT):** a execução `f6507ec470c94b5dba0565ec8cfc3c97` (SUINO01 reduzida de novo, mesma amostra da `885535c1`, `config/picornavirus.env` restaurado, filtro de hospedeiro desligado, adaptadores digitados, MULTI) **terminou** (`done`, Evidence V2 `done_with_warning`) em ~15 min 11 s, sem OOM. **Os três montadores rodaram.** É a execução SUINO01 completa; na `885535c1`, SPAdes/metaSPAdes tinham falhado (U-26). A memória foi amostrada desde antes da submissão, com cobertura completa: o `blastn-short` do resgate foi medido pela primeira vez (804 MiB); validação e finalização chegaram a 7.391 MiB cada (U-27). Novos: **U-31** (o Histórico não mostra banco, montador, adaptadores, hospedeiro nem rótulo; duas execuções da mesma amostra só diferem pelo id e pelo horário) e **U-32** (reexecutar uma amostra que já tem resultados não gera aviso e sobrescreve os arquivos de trabalho com o nome da amostra; verificado por SHA-256). Os resultados por execução e as telas do job antigo ficaram intactos. Mistura PT/EN no log do Acompanhar incorporada a P-08 (g); "Ambiente: ↻ Verificando" fora do assistente, a U-02; "Sucesso parcial" no Histórico, a U-22; repetições com as capturas G01–G06 em U-03, U-14, U-17, U-26 e U-27. Correção de unidade: valores antes escritos como "x,xx GiB" eram MiB ÷ 1.000; passam a aparecer em MiB, com GiB = MiB ÷ 1.024 (U-27 e notas acima). Dados brutos em `EXE/SUINO01_f6507ec4/DADOS_BRUTOS.md` (prova da sobrescrita na seção 8); comparação das quatro execuções em `EXE/TABELA_SUINO.md`. Nenhum ID foi renumerado. Versão anterior: `repro-oom/PROBLEMAS_GENEIN.md.bak-antes-suino01c`.

> **Atualização SUINO_NEG (08/10/2026, ~17:36 BRT):** execução `469b1a6fca034e1484222ab27cdc8de1` (SUINO_NEG reduzida, controle negativo por desenho, 11.200 pares, filtro de hospedeiro desligado, adaptadores digitados, MULTI) **terminou** (`done`, Evidence V2 `done_with_warning`) em ~12 min 8 s, sem OOM. Novo: **U-30** (o assistente não permite declarar o papel da amostra — controle negativo, positivo, lote —, embora a CLI e o Evidence V2 tenham esse suporte). U-27 com novos números (validação/finalização 5.692 MiB na SUINO_NEG; 7.224 MiB na 2ª SUINO01, valor que faltava). Acessibilidade do filtro de hospedeiro em U-07; repetições com as capturas F01–F03 em U-03, U-08, U-10, U-11, P-07 e P-11. Dados brutos em `EXE/SUINO_NEG_469b1a6f/DADOS_BRUTOS.md`; comparação das três execuções suínas em `EXE/TABELA_SUINO.md`. Nenhum ID foi renumerado. Versão anterior: `repro-oom/PROBLEMAS_GENEIN.md.bak-antes-suinoneg`.

> **Atualização SUINO02 (08/10/2026, ~17:20 BRT):** execução `ce2c576aa8d840cb9b2c19f9e4d5198c` (SUINO02 reduzida, 14.400 pares, filtro de hospedeiro desligado, adaptadores digitados, MULTI) **terminou** (`done`, Evidence V2 `done_with_warning`) em ~17 min 6 s, sem OOM. Antes dela, a pessoa testadora restaurou `config/picornavirus.env` a partir do backup do próprio painel; **SPAdes e metaSPAdes rodaram** e o consenso MULTI foi atingido (U-26). Na validação/finalização, dois processos chegaram a **~8.248 MiB (8,06 GiB)** de RSS cada, e a exportação a 6.298 MiB (6,15 GiB) com MemAvailable de 699 MiB: **U-27 sobe para Alta** e passa a cobrir esses dois scripts. Novo: **U-29** (a amostra selecionada muda em silêncio para a última importada). Achados de interface (capturas E01–E03) incorporados a U-03, U-05, U-08, U-10, P-07 e P-11; U-14 e U-17 com novas evidências. Dados brutos em `EXE/SUINO02_ce2c576a/DADOS_BRUTOS.md`. Nenhum ID foi renumerado. Versão anterior: `repro-oom/PROBLEMAS_GENEIN.md.bak-antes-suino02`.

> **Atualização SUINO01b (08/10/2026, ~16:55 BRT):** execução `885535c1febd48659b8089f60e1e6458` (SUINO01, filtro de hospedeiro desligado, adaptadores digitados) **terminou** (`done`, Evidence V2 `done_with_warning`) em ~16 min 20 s efetivos. Os adaptadores foram aplicados; o resgate processou 25.156 reads embora o log anuncie 266 (U-14); SPAdes e metaSPAdes falharam por `SPADES_PARAMS` com aspas simples (U-26, novo), a exportação dos candidatos chegou a 5.652 MiB (5,52 GiB) de RAM (U-27, novo) e "Cancelar execução" não pede confirmação (U-28, novo). Dados brutos em `EXE/SUINO01_885535c1/DADOS_BRUTOS.md`. Achados de interface da submissão incorporados a U-03, U-05, U-07, U-08, U-09, U-11, U-14, U-17, U-24, P-07, P-08 e P-11 (capturas D01–D06). Nenhum ID foi renumerado. Versão anterior: `repro-oom/PROBLEMAS_GENEIN.md.bak-antes-suino01b`.

> **Atualização SUINO01 (08/10/2026, ~15:50 BRT):** execução `1088e943d91d42cf819e9b3e14cca12b` (amostra suína reduzida SUINO01, filtro de hospedeiro ligado, adaptadores digitados) **falhou em ~24 s** na etapa [3/6] (filtro de hospedeiro): o painel usou o caminho fixo `ref/host/sus_scrofa_bt2`, que não existe, e ignorou o índice customizado salvo na Configuração técnica. Os adaptadores foram aplicados ao fastp. Montagem, BLAST, resgate e candidatos: **NÃO EXECUTADO**. Dados brutos em `EXE/SUINO01_1088e943/DADOS_BRUTOS.md`. Nesta atualização: U-06 passa de Média para **Alta** (reproduzido na execução); novos U-23, U-24 e U-25; novas evidências incorporadas a P-07, P-10, P-11, U-01, U-03, U-05, U-08, U-09, U-10, U-11, U-17 e U-21 (capturas C01–C11). Nenhum ID foi renumerado. Versão anterior: `repro-oom/PROBLEMAS_GENEIN.md.bak-antes-suino01`.

> **Revisão de enquadramento (08/10/2026, ~15:30 BRT):** esta lista foi conferida contra a finalidade declarada pelo autor e o `ESCOPO_TESTES_GENEIN.md`. Ver `REVISAO_AVALIACAO_OBJETIVO.md`. Os itens descrevem **instalação, funcionamento, interface e engenharia**; nenhum avalia o desempenho científico (recuperação por comprimento, falsos candidatos, categorias, bancos, montadores: **NÃO AVALIADO**). O cenário em células humanas fica **fora do desenho** do programa. Ajustes mínimos de redação em U-06, U-12, U-14, U-15, nos pontos positivos e em "Em andamento". IDs, gravidades e contagem não mudaram. Versão anterior: `repro-oom/PROBLEMAS_GENEIN.md.bak-antes-revisao-objetivo`.

> **Documento vivo.** Será atualizado com novos achados. Última atualização: 08/10/2026, ~18:00 (horário de Brasília, UTC-3; SUINO01c, ver nota acima). Atualizações anteriores: ~17:36, ~17:20, ~16:55, ~15:50. Na atualização anterior (~15:10): falha por falta de memória da AMOSTRA01 (U-14), contigs gigantes de origem humana (U-15), como a interface mostra a falha (U-16 a U-22, capturas B01–B05) e P-07 confirmado. Escopo de referência: `ESCOPO_TESTES_GENEIN.md` (definido pelo autor às 15:04).

## Introdução

Esta lista reúne, para o autor (Alexsander), os problemas encontrados no **Gene-In 2.0.0b1 (beta de pesquisa)** em duas frentes:

1. **Teste externo técnico** (08/10/2026, 10:49–11:15 BRT): instalação, CLI, diagnóstico, pipeline e verificação visual somente leitura do painel. Os IDs **P-01 a P-11** foram mantidos como no relatório original.
2. **Teste de usabilidade** (08/10/2026, a partir de ~13:41 BRT): persona de pesquisadora de bancada (sequenciamento), com pouca bioinformática, usando só a interface web em `http://127.0.0.1:8000`. Os itens novos estão numerados **U-01, U-02, …**. Quando o achado é o mesmo de um P-xx, ele foi incorporado ao P-xx com referência cruzada, sem duplicar.

- **Pacote:** `Gene-In-2.0.0b1-beta-pesquisa.zip`, SHA-256 `97b5429c102cf3976ee95b6544be8d5520ef036b4210fa0b1811aa049a690f28` (97b5429c…a690f28).
- **Fonte consultada para file:linha:** árvore extraída em `/workspace/genein-pesquisador/Gene-In-2.0.0b1`. Ela confere com `SHA256SUMS.txt`: `sha256sum -c` retornou 440/440 OK em 08/10 ~13:52. **Nenhum arquivo do pacote foi alterado** para produzir esta lista.
- **Abreviações de caminho usadas abaixo:**
  - `SRC/` = `/workspace/genein-pesquisador/Gene-In-2.0.0b1/`
  - `EXT/` = `/workspace/genein-teste-externo/evidencias/`, pasta de origem das evidências do teste externo. O mesmo conteúdo está no ZIP `/workspace/genein-teste-externo/entrega/evidencias-teste-externo-genein-2.0.0b1.zip`: `falhas/`, `visual/` e `patches/`.
  - `EXTLOG/` = `/workspace/genein-teste-externo/logs/` (no ZIP: `logs/`)
  - `CAP/` = `/workspace/genein-pesquisador/usabilidade/capturas/` (capturas A01–A15, B01–B05, C01–C11, D01–D06, E01–E03, F01–F03 e G01–G06; as C e D são das submissões da SUINO01, as E da SUINO02, as F da SUINO_NEG, as G da reexecução da SUINO01 `f6507ec4`)
  - `EXE/` = `/workspace/genein-pesquisador/usabilidade/execucoes/` (logs, configuração, estado e tabelas copiados por execução; `SUINO01_1088e943/` = 1ª SUINO01; `SUINO01_885535c1/` = 2ª; `SUINO02_ce2c576a/` = SUINO02; `SUINO_NEG_469b1a6f/` = SUINO_NEG; `SUINO01_f6507ec4/` = 3ª SUINO01, a execução completa; `TABELA_SUINO.md` = comparação das quatro)
  - `FAL/` = `/workspace/genein-pesquisador/usabilidade/falhas/` (evidências das falhas da usabilidade; F01 = AMOSTRA01 morta por falta de memória)
  - `REPRO/` = `/workspace/genein-pesquisador/repro-oom/` (reprodução do U-14 em cópia, com `README_REPRO.md`)
  - `PAT/` = `/workspace/genein-pesquisador/patches/` (patches propostos, aplicados só em cópias)
  - Relatório técnico completo: `/workspace/genein-teste-externo/entrega/RELATORIO_TESTE_EXTERNO.md`

**Gravidade:** **Alta** = impede o caminho documentado ou compromete o resultado sem aviso. **Média** = afeta função, integridade, entendimento de um passo importante ou uma afirmação da entrega, mas há contorno. **Baixa** = mensagem, cosmético, jargão ou rastreabilidade menor.

---

## Resumo

| ID | Severidade | Área | Título | Status |
|---|---|---|---|---|
| P-01 | Alta | instalação | `make` é obrigatório, mas o instalador Linux não o instala nem verifica, e o guia não o cita | corrigido — `fd68153993ca` |
| P-02 | Média | pipeline | Mensagens de falha não indicam a falta de `make` e sugerem `install_deps.sh` (apt sem versão fixa) | corrigido — `98b1045150dc` |
| P-03 | Baixa | pipeline | A proveniência registra "USAGE" como versão do BLAST+ | corrigido — `57f7b3604645` |
| P-04 | Baixa | interface | `/api/preflight` dá `iqtree2` como ausente (o lock traz `iqtree`/`iqtree3`) | corrigido — `b08df4bad9ae` |
| P-05 | Média | pipeline | Banco BLAST com arquivo alterado depois do manifesto é aceito sem aviso | corrigido — `d0dc54af86ee` |
| P-06 | Baixa | CLI | CLI sem `--version` | corrigido — `27965eaa6a6a` |
| P-07 | Baixa | instalação | Diagnóstico com dados imprecisos (MemFree, `make db` fora do wrapper, avisos indevidos); "pronta para uso" mesmo com 0,5 GB "livre" (**confirmado na usabilidade**) | corrigido — `43106f903682` |
| P-08 | Baixa | CLI / interface | Mensagens de erro e textos de interface pouco orientadores, contraditórios ou sem tradução | corrigido no escopo dos achados do reteste — `92eba6d71848` |
| P-09 | Média | pipeline | Mapeamento direto experimental falha sem `.git` (ZIP) e a suíte operacional reprova | corrigido — `97fcbde67489` |
| P-10 | Média | documentação / interface | O guia manda usar o menu "Bancos", que não existe; o preparo do banco fica escondido na Área avançada experimental (**confirmado na usabilidade**) | corrigido — `238d762e34fa` |
| P-11 | Baixa | interface | A Revisão mostra o montador como "consensus" e a Configuração, como "MULTI" (**confirmado na usabilidade**) | corrigido — `7b053a6bc8ef` |
| U-01 | Média | interface | Etapa 2 "Banco viral" sem status de preparo, sem botão de preparar e sem aviso de que o banco precisa existir | corrigido — `5c912d3023a6` |
| U-02 | Média | interface | Depois de preparar o banco, a barra superior continua em "Banco: Não selecionado", a única ação é "Abrir resultados" e não há mensagem final clara | corrigido — `101803ce5186` |
| U-03 | Média | interface | O log técnico perde todas as quebras de linha e vira um bloco corrido (todas as execuções) | corrigido — `e75f4678f280` |
| U-04 | Baixa | interface | "Acompanhar" promete etapas, mas a lista de etapas nunca aparece no pipeline | corrigido — `31462bafac96` |
| U-05 | Baixa | interface | Upload sem indicador de progresso (~6 s sem resposta) | corrigido — `61325884955e` |
| U-06 | **Alta** (era Média) | interface / pipeline | Filtro de hospedeiro: assistente sem opção "custom" (índice próprio), índice Sus scrofa ausente do pacote e nenhuma orientação (o caso humano está fora do desenho); **na SUINO01, o índice customizado salvo foi ignorado e a execução falhou** | corrigido — `29ae0e0a49ce` |
| U-07 | Média | interface | Adaptadores e filtro de hospedeiro escondidos em "Configurações técnicas" (fechado); a ajuda não cita SampleSheet nem read-through | corrigido — `9be1558a0d2d` |
| U-08 | Média | interface | A Revisão não mostra os adaptadores; o botão "Revisar limites da execução" não se explica e afirma "Integridade verificada" antes da execução | corrigido — `58807b8e57d4` |
| U-09 | Baixa | pipeline / interface | Adaptadores **aplicados** corretamente, mas ausentes do comando exibido e da "Configuração efetiva" do log | corrigido — `2f83b662e15b` |
| U-10 | Baixa | interface | O rastreador do assistente marca ✓ em etapas ainda não visitadas (relaciona-se a O-08) | corrigido — `179c70825965` |
| U-11 | Baixa | interface | Jargão técnico para quem trabalha em bancada | corrigido — `5b459706ea73` |
| U-12 | Baixa | interface | A lista de bancos mistura vírus suínos específicos com opções gerais | corrigido — `f3fe2d6bfdce` |
| U-13 | Baixa | documentação | O guia `.md` não abre no navegador (`file://` bloqueado) e o painel não tem página de ajuda | corrigido — `4b86d8eb2325` |
| U-14 | **Alta** | pipeline | Resgate de reads (caminho de 20–100 pb) morto por falta de memória: o Python carrega 57 milhões de linhas BLAST (6,35 GB) e precisaria de ~60 GB | corrigido — `613260308dea` |
| U-15 | Média | pipeline / interface | Com o filtro de hospedeiro desligado, contigs muito maiores que os genomas do banco (aqui 44–300 kb, de DNA humano) aparecem sem aviso (relaciona-se a U-06) | corrigido — `097f86343ad6` |
| U-16 | Média | interface | Após a falha, "Acompanhar" mostra só "Status técnico: Falha" e o log bruto: sem etapa, causa ou próximo passo | corrigido — `13f70fd233cd` |
| U-17 | Média | pipeline / interface | Registro técnico da falha errado: `returncode` nulo na API, `failure_type` INPUT_INVALID para um SIGKILL/OOM e `exit_code` 1 no histórico | corrigido — `1aca7a573d01` |
| U-18 | Média | interface | Saídas parciais (reads limpas, relatório de QC, contigs) existem, mas não aparecem nem podem ser baixadas após a falha | corrigido — `1efb68d3f87b` |
| U-19 | Baixa | interface | Não há "Reexecutar" para a execução que falhou (Acompanhar, Resultados, Histórico) | corrigido — `b1fd5d3b9a35` |
| U-20 | Média | interface | Resultados de uma execução que falhou não dizem "Falha": mostram "Evidence V2 não avaliável — execução Evidence V2 não encontrada" e "Finalizada" | corrigido — `4d64dfd6c1c3` |
| U-21 | Baixa | interface | O tempo decorrido continua contando depois do fim do job (23min 5s → 33min 11s) | corrigido — `f804712609ae` |
| U-22 | Baixa | interface | Rótulos pouco claros no Histórico: "Inspecionar inválida" e "Camada: Não avaliável" ao lado de "Falha" | corrigido — `15879c377042` |
| U-23 | Baixa | interface | Configuração técnica: "Validar índice" não salva; após "Configuração salva" a tabela "Configuração operacional efetiva" continua com os valores antigos até recarregar; "Read tracking" aparece vazio com valor salvo `yes` | corrigido — `68896ece77a8` |
| U-24 | Média | interface / pipeline | A configuração técnica é global (um arquivo dentro do pacote), não por execução: vale em silêncio para as análises seguintes, enquanto as chaves de hospedeiro são ignoradas pelo painel; a tela mostra ASSEMBLER=spades e DB=custom, que não são o que o assistente usa | corrigido — `9ba14cee7c61` |
| U-25 | Média | pipeline / interface | O índice do hospedeiro só é verificado depois do QC, a falha não diz como resolver e a mensagem sai com o rótulo `[QC_PREFLIGHT]` | corrigido — `e853e3177248` |
| U-26 | **Alta** | pipeline / interface | "Salvar configuração" grava `SPADES_PARAMS` com aspas simples e o SPAdes/metaSPAdes falham (`-m ${SPADES_MEMORY}` sem expansão); o pipeline segue só com velvet e termina como se tivesse concluído | corrigido — `76b6cdf9586c` |
| U-27 | **Alta** (era Média) | pipeline | Exportação, validação e finalização do Evidence V2 carregam os TSVs de candidatos/fragmentos inteiros na memória (SUINO02: 8.248 MiB em `validate_run_artifacts.py` e em `finalize_run.py`, 6.298 MiB na exportação, MemAvailable de 699 MiB) | corrigido — `201d33945184` |
| U-28 | Média | interface | "Cancelar execução" é um botão vermelho logo abaixo do log e cancela sem pedir confirmação | corrigido — `90810d811c54` |
| U-29 | Média | interface | Depois de uma segunda importação, a amostra selecionada e o cabeçalho passam em silêncio para a última importada (risco de executar a amostra errada) | corrigido — `bedcedd1d5f4` |
| U-30 | Média | interface / pipeline | O assistente não tem como declarar o papel da amostra (controle negativo, positivo, lote), embora o pipeline tenha esse suporte; toda execução sai como amostra comum, sem avaliação de controles | corrigido — `be99c20fc39b` |
| U-31 | Média | interface | O Histórico não mostra banco, montador, adaptadores, hospedeiro nem rótulo por execução; duas execuções da mesma amostra só diferem pelo id hexadecimal e pelo horário | corrigido — `c1a27b02a385` |
| U-32 | Média | interface / pipeline | Reexecutar uma amostra que já tem resultados não gera aviso, e a nova execução sobrescreve os arquivos de trabalho com o nome da amostra (montagem, BLAST, relatório, QC). Os resultados por execução e as telas do job antigo ficam intactos | corrigido — `5e8acc26ba13` |

**Contagem atual (43 itens):** Alta 5 · Média 21 · Baixa 17. (P: 1 Alta, 4 Média, 6 Baixa. U: 4 Alta, 17 Média, 11 Baixa.) Mudanças em 08/10 ~18:00 (SUINO01c): U-31 (Média) e U-32 (Média) novos. Em ~17:36 (SUINO_NEG): U-30 (Média) novo. Em ~17:20 (SUINO02): U-27 Média → Alta; U-29 (Média) novo. Em ~16:55: U-26 (Alta), U-27 (Média) e U-28 (Média) novos. Em ~15:50: U-06 Média → Alta; U-23 (Baixa), U-24 (Média) e U-25 (Média) novos.

> **Verificação específica (índice de hospedeiro customizado, SUINO01):** **não foi usado.** O índice salvo em `HOST_INDEX_PREFIX` foi substituído pelo caminho fixo `ref/host/sus_scrofa_bt2` (inexistente) e a execução parou no filtro de hospedeiro. Detalhes em **U-06**.

> **Verificação específica (adaptadores):** os adaptadores digitados na interface **foram aplicados** ao fastp na execução `59349d8fa52c4f24894789607ebff9f7` e, de novo, na `1088e943d91d42cf819e9b3e14cca12b` (SUINO01). Detalhes em **U-09**. Não é problema de alta gravidade. O problema é de transparência: o comando mostrado ao usuário e o bloco "Configuração efetiva" do log não incluem os adaptadores.

---

## Problemas do teste externo (P-01 a P-11)

### P-01 — `make` é obrigatório, mas o instalador Linux não o instala nem verifica, e o guia não o cita (Alta · instalação · corrigido — fd68153993ca)

**Reteste b3:** Complemento de U-34-b2: documentação registra os dois launchers, orientação de instalação e testes de make ausente. Instalação real via sudo não foi necessária nem executada. Commit `fd68153993ca1582fc6564778bf182983741f66d`.

**Correção de engenharia na b2:** commit `9621c889aff2b8ab6fb3a9bdf8c3ac6078175e52`. Verificação: scripts/tests/test_p01_byte_parity.py. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** depois de `bash bundle/install_wsl.sh` (exit 0), no diagnóstico (`bash bundle/run.sh test-env`), no painel (`bash run_linux.sh`) e em qualquer execução de pipeline, inclusive o teste sintético documentado.
- **Esperado:** o instalador detecta e instala `make`, como já faz com `curl`, `tar` e `bzip2`, ou o guia lista o pré-requisito.
- **Observado:** `exec: make: not found` (exit 127) no diagnóstico e no painel. O teste sintético sai com exit 1 e mostra só `Pipeline failed (1): …/twenty.log`. O lock Conda não inclui `make`. No Windows, `run.bat` + `install_wsl_dependencies.sh` instalam `make`; no Linux, não.
- **Evidência:** `EXT/falhas/P-01-make-ausente/` (14-test-env.log, 15-run-linux-painel.log, `sintetico-sem-make/`); `EXTLOG/16-reproducao-P01.log`; verificação do patch em `EXTLOG/30-patch-P01-install-prefix2.log` e `EXTLOG/31-patch-P01-test-env-prefix2.log`.
- **Provável local no código:**
  - `SRC/bundle/install_wsl.sh:48` (checagem de `tar`) e `:52` (checagem de `bzip2`). Falta a checagem equivalente para `make`.
  - `SRC/scripts/pipeline/sample_steps.sh:219` (`make -C "$REPO_ROOT" setup_dirs`): por causa desta linha, **toda** execução depende de `make`.
  - `SRC/scripts/ops/check_env.sh:234` (`SYSTEM_UTILS=(bash gcc make …)`).
  - `SRC/docs/beta-pesquisadores.md:25` ("No Ubuntu/Linux, na pasta extraída:"), sem pré-requisitos de sistema.
- **Sugestão de correção:** aplicar `P-01-make-prerequisito.patch` (`EXT/P-01-make-prerequisito.patch`, ou `patches/` no ZIP). Ele acrescenta `need_cmd make || sudo apt-get install -y make` em `install_wsl.sh` e lista `bash make curl tar bzip2 ca-certificates` no guia. A longo prazo, considerar trocar `make setup_dirs` por `mkdir -p` direto no `sample_steps.sh`.

### P-02 — Mensagens de falha não indicam a falta de `make` e sugerem `install_deps.sh` (Média · pipeline · corrigido — 98b1045150dc)

**Reteste b3:** A ação bash bundle/install_wsl.sh aparece junto à dependência obrigatória ausente, inclusive make, e no resumo do diagnóstico. Commit `98b1045150dcd0a00a2cd4c8695af69dbfd3922a`.

**Correção de engenharia na b2:** commit `f34aebbf11346b1355a22c70dbb48a81b8f28fcd`. Verificação: test_p01_byte_parity.py; all-safe-final/operational.log; diagnóstico final. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** teste sintético documentado e diagnóstico interno do pipeline, sem `make`.
- **Esperado:** mensagem com a causa (pré-requisito ausente) e um remédio coerente com o ambiente micromamba isolado.
- **Observado:** (a) o script de verificação mostra só `Pipeline failed (1): <log>`; (b) o diagnóstico sugere `sudo bash scripts/ops/install_deps.sh`, que instala pelo apt, **sem fixar versão**, spades, velvet, blast+, bowtie2, samtools, fastp e mafft. Isso contraria o lock e pode pôr versões diferentes no PATH.
- **Evidência:** `EXT/falhas/P-02-sugestao-install-deps/twenty-pipeline-sem-make.log` (final do log).
- **Provável local no código:** `SRC/scripts/tests/verify_fragment_recovery_real.py:103` (`raise SystemExit(f"Pipeline failed …")`); `SRC/scripts/ops/check_env.sh:506-507` (auto-instalação via `install_deps.sh`) e `:519` (sugestão `sudo bash scripts/ops/install_deps.sh`).
- **Sugestão de correção:** com o ambiente bundle ativo, sugerir só `sudo apt-get install -y make` (ou os utilitários de sistema que faltarem) e apontar a seção de requisitos. No script sintético, repetir as últimas linhas `[FALTA]`/`[ERRO]` do log do caso.

### P-03 — A proveniência registra "USAGE" como versão do BLAST+ (Baixa · pipeline · corrigido — 57f7b3604645)

**Correção de engenharia na b2:** commit `57f7b3604645e627befdd0225bc7c5c69b85446d`. Verificação: scripts/tests/test_p03_byte_parity.py. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** `provenance.json` e `run_state.json` do Evidence V2 e a identidade dos construtores de índice.
- **Esperado:** `"version": "blastn: 2.17.0+"` / `"makeblastdb: 2.17.0+"`.
- **Observado:** `"version": "USAGE"`. O BLAST+ responde a `--version` com exit 1 e o texto de uso, e o código aceita a primeira linha de qualquer saída. O SHA-256 do executável continua registrado.
- **Evidência:** `EXT/falhas/P-03-versao-USAGE/` (`provenance-twenty-primeira-evidencia.json`, `32-P03-antes.log`); depois do patch: `EXTLOG/33-P03-depois.log`. Script: `/workspace/genein-teste-externo/verif_P03.sh`.
- **Provável local no código:** `SRC/scripts/evidence/write_provenance.py:32` (`if line:`); `SRC/scripts/evidence/index_cache.py:28` (`if line:`).
- **Sugestão de correção:** aplicar `P-03-versao-blast-proveniencia.patch` (`EXT/P-03-versao-blast-proveniencia.patch`), que só aceita a linha quando `returncode == 0`. Reexecutar as suítes depois do patch (não foi feito).

### P-04 — `/api/preflight` dá `iqtree2` como ausente; a interface não mostra o alerta (Baixa · interface · corrigido — b08df4bad9ae)

**Correção de engenharia na b2:** commit `b08df4bad9aebc4477d6ba5a2bfecb56f736e869`. Verificação: scripts/tests/test_p04_byte_parity.py. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** `GET /api/preflight` (o JSON traz `{"name": "iqtree2", … "present": false}`).
- **Esperado:** a ferramenta opcional IQ-TREE aparece como presente (o lock traz `iqtree`/`iqtree3`; o diagnóstico de software desta sessão mostra `iqtree v3.1.1`).
- **Observado:** dado errado no endpoint. A tela mostra "● Pronto" sem alerta, porque a ferramenta é opcional.
- **Evidência:** `EXT/falhas/P-04-iqtree2-preflight/19-http-painel.log`; `EXT/visual/02-new-01-ambiente.png`; `SRC/logs/software_versions.txt` (sessão de usabilidade: `iqtree v3.1.1`).
- **Provável local no código:** `SRC/scripts/dashboard/config.py:58` (`("iqtree2", "Análise complementar", False)`).
- **Sugestão de correção:** aceitar `iqtree2`, `iqtree3` ou `iqtree`, como `check_env.sh` e `advanced_analysis/run.sh` já fazem.

### P-05 — Banco BLAST com arquivo alterado depois do manifesto é aceito sem aviso (Média · pipeline · corrigido — d0dc54af86ee)

**Reteste b3:** Complemento de U-35-b2: manifesto adulterado produz código 65 e recibo INPUT_INVALID/database_preflight. Mensagem não anuncia banco validado antes de conferir integridade; banco íntegro não é alterado. Commit `d0dc54af86eebd7d109b1ee56435f2a2e68a7bfa`.

**Correção de engenharia na b2:** commit `78596a7792669ef5f07434f0d4ec2660c8cafa8b`. Verificação: scripts/tests/test_p05_byte_parity.py; test_blast_specificity_integrity.py. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** `genein run` com banco preparado (o mesmo trecho vale para o pipeline do painel).
- **Esperado:** rejeição ou aviso quando o SHA-256/tamanho dos arquivos do índice difere do `.db-manifest.json`.
- **Observado:** com 1 byte acrescentado a `panel.nsq`, a execução terminou com exit 0 e `SUCCESS.json`. A proveniência registra só o hash do manifesto. Um banco copiado para outra pasta (com `logical_prefix` antigo) também foi aceito.
- **Evidência:** `EXT/falhas/P-05-banco-alterado-aceito/` (log e `artefatos/sha256-nsq-original-vs-alterado.txt`); `EXTLOG/47-cenario-banco-corrompido.log`.
- **Provável local no código:** `SRC/scripts/pipeline/sample_steps.sh:220-222` (`validate_blast_database … && [[ -s "$DATABASE_MANIFEST" ]]` → "Banco BLAST já validado … preparação omitida"); `SRC/scripts/lib/common.sh:55` (`validate_blast_database()`, que só consulta o blastdbcmd).
- **Sugestão de correção:** antes da busca, validar `produced_files` (tamanho + SHA-256) contra o manifesto. No mínimo, avisar e gravar na proveniência os hashes reais dos índices usados.

### P-06 — CLI sem `--version` (Baixa · CLI · corrigido — 27965eaa6a6a)

**Correção de engenharia na b2:** commit `27965eaa6a6aec4b6f7c1f4c09e4615b0fbb9479`. Verificação: tests/test_cli.py; versão do ZIP extraído. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** `bash bundle/run.sh genein --version` → exit 2, `error: the following arguments are required: command`.
- **Esperado:** imprimir `2.0.0b1`. O guia pede que o participante informe a versão.
- **Observado:** a opção não existe. Hoje só `pip show genein` mostra a versão.
- **Evidência:** `EXT/falhas/P-06-cli-sem-version/13-cli-version.log`.
- **Provável local no código:** `SRC/src/genein/cli.py:11-15` (`ArgumentParser` + `add_subparsers(…, required=True)` sem `--version`).
- **Sugestão de correção:** `parser.add_argument("--version", action="version", version=f"%(prog)s {importlib.metadata.version('genein')}")`, se possível também com o `delivery_id` do `RELEASE.json`.

### P-07 — Diagnóstico com dados imprecisos (Baixa · instalação · corrigido — 43106f903682)

**Reteste b3:** Comandos de preparo do diagnóstico usam bundle/run.sh. Banco pronto dispensa aviso de FASTA adicional ausente; MemAvailable/unidades anteriores preservadas. Commit `43106f90368246b3e7aedd29c4dd815e343a6b0e`.

**Correção de engenharia na b2:** commit `239d5b0d908e5c466ad7693f5f33e0712ca8c908`. Verificação: diagnóstico final; all-safe-final/operational.log. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** `bash bundle/run.sh test-env` (exit 0).
- **Esperado:** memória disponível real, comandos coerentes com o wrapper e nenhum aviso irrelevante.
- **Observado:** (a) "Livre: 0.2 GB" calculado com `MemFree`, quando `MemAvailable` era ~3,5 GB; (b) recomenda `make db DB=ptv` em vez de `bash bundle/run.sh db DB=ptv`; (c) "[ATENÇÃO] FASTA de referência ausente em data/ref/*.fa" e aviso sobre `blastdb/custom` mesmo com banco explícito.
- **Evidência:** `EXTLOG/17-test-env-apos-make.log`; `EXT/falhas/P-08-mensagens/17-test-env-apos-make.log`.
- **Provável local no código:** `SRC/scripts/ops/check_env.sh:399` (`grep MemFree`); `:467-468`, `:481`, `:495` (sugestões `make db DB=…` e aviso de FASTA ausente).
- **Sugestão de correção:** usar `MemAvailable`; padronizar as sugestões com `bash bundle/run.sh db DB=…`; suprimir os avisos de FASTA/banco quando `BLAST_DB` for explícito e válido.
- **Confirmado na usabilidade (08/10, job `59349d8f…`, 13:46:21):** o bloco de diagnóstico no início do log da análise diz "[INFO] Memória RAM Total: 15.6 GB (Livre: 0.5 GB)" e termina com "✅ DIAGNÓSTICO CONCLUÍDO COM SUCESSO! … Sua plataforma Gene-In está pronta para uso!". O valor "Livre" usa `MemFree`, que não conta a memória de cache que pode ser liberada, e nenhum valor de memória gera aviso (só existe aviso para RAM **total** < 8 GB). Na mesma execução, a falta de memória matou o resgate 23 min depois (U-14). O "pronta para uso" incondicional, ao lado de um número que parece crítico, confunde nos dois sentidos. Captura: `CAP/B01-track-falha-topo.png` / `CAP/B02-track-log-fim.png` (log); `FAL/F01-amostra01-killed/logs/AMOSTRA01_pipeline.log`, linhas 67–81. Locais: `SRC/scripts/ops/check_env.sh:399` (`MemFree`), `:402`, `:403-405` (só RAM total), `:542-544` (mensagem de sucesso incondicional). Sugestão adicional: mostrar `MemAvailable` e avisar ("memória disponível baixa para montagem/BLAST de reads; feche outros programas") abaixo de um limiar documentado. Terminar com "concluído com avisos" quando houver avisos.
- **Observado de novo na SUINO01 (job `1088e943…`, 15:34:36):** o diagnóstico da execução diz "[INFO] Caminho BLAST_DB ativo: blastdb/custom" e "[INFO] BLAST_DB ainda não preparado; será criado automaticamente…" (log, linhas 74–75), enquanto a mesma execução usa `BLAST_DB: …/blastdb/picornaviridae_refseq` (linha 15) e informa "Banco BLAST já validado… preparação omitida". O valor vem de `BLAST_DB="blastdb/custom"` em `SRC/config/picornavirus.env` (padrão do exemplo). É o ponto (c) acima, agora numa execução pelo painel. Evidência: `EXE/SUINO01_1088e943/logs/SUINO01_pipeline.log`. Ver também **U-24**.
- **Observado de novo na 2ª SUINO01 (job `885535c1…`, 15:55:17):** o mesmo bloco, na mesma execução: linha 15 `BLAST_DB: …/blastdb/picornaviridae_refseq`; linhas 74–75 "[INFO] Caminho BLAST_DB ativo: blastdb/custom" e "ainda não preparado; será criado automaticamente…"; linha 89 "[INFO] Banco BLAST já validado em …/blastdb/picornaviridae_refseq; preparação omitida." O banco não foi recriado. Evidência: `EXE/SUINO01_885535c1/logs/ux_885535c1febd48659b8089f60e1e6458.log` (captura `CAP/D06_acompanhar_30s.png`). Locais: `SRC/scripts/ops/check_env.sh:475` e `:478` (usam `BLAST_DB` do `picornavirus.env`, não o banco resolvido da execução) e `SRC/scripts/pipeline/sample_steps.sh:220-222` (a validação real).
- **Também no diagnóstico da 2ª SUINO01:** (d) a numeração vai de "[1/5]" a "[5/5]" e depois salta para "[6/6] Auditoria de Recursos do Sistema" (log, linhas 30, 55 e 67); (e) "[AVISO] Utilitário rsync ausente. (Pode causar limitações em uploads/downloads)" (linha 60) aparece em toda análise, embora o rsync não seja usado pelo pipeline nem pelo upload do painel. Locais: `SRC/scripts/ops/check_env.sh:233`, `:248`, `:263`, `:321`, `:361` ("[n/5]") × `:394` ("[6/6]"); `:362` (`EXTRA_UTILS=(… rsync …)`). Sugestão: numerar de 1 a 6 e mostrar o aviso do rsync só no diagnóstico de instalação, não no log de cada análise.
- **Observado de novo na SUINO_NEG (job `469b1a6f…`):** o mesmo bloco contraditório no início do log (`CAP/F03_acompanhar_30s.png`).
- **Observado de novo na SUINO02 (job `ce2c576a…`, 16:59:42):** mesmas linhas no log da execução: `BLAST_DB: …/blastdb/picornaviridae_refseq` (linha 15) × "Caminho BLAST_DB ativo: blastdb/custom" / "ainda não preparado" (linhas 74–75) × "Banco BLAST já validado em …/picornaviridae_refseq" (linha 89); "[1/5]"…"[5/5]" seguido de "[6/6]" e o aviso do rsync (linha 60). Evidência: `EXE/SUINO02_ce2c576a/logs/ux_ce2c576aa8d840cb9b2c19f9e4d5198c.log`; `CAP/E03_acompanhar_30s.png`.

### P-08 — Mensagens de erro e textos de interface pouco orientadores, contraditórios ou sem tradução (Baixa · CLI / interface · corrigido no escopo dos achados do reteste — 92eba6d71848)

**Reteste b3:** Pareamento só é anunciado após validação integral. Erros de FASTQ explicam a regra e ação em português; controle positivo sem alvo foi traduzido. Mensagens normais citadas no reteste e seletor de arquivos estão em português. Logs técnicos originais de ferramentas de terceiros não são reescritos. Commit `92eba6d718485f9549990208caf4efd952c7c9cf`.

- **Onde aparece:** CLI (banco ausente, FASTQ malformado) e painel (etapa 3 e Área avançada).
- **Esperado:** mensagens em português com a ação recomendada, sem sobras de desenvolvimento e sem inglês.
- **Observado:**
  - (a) Banco ausente: `[FATAL] Input is missing or empty: …/naoexiste.db-manifest.json`.
  - (b) FASTQ malformado: "FASTQs pareados com sucesso: 150 reads detectadas" e, logo depois, "[ERRO] FASTQ invalido …, registro 3", sem dizer qual regra falhou.
  - (c) A etapa 3 diz "Upload de R1/R2 ou ZIP, **como na versão anterior**" (**confirmado na usabilidade**, A08).
  - (d) Seletor nativo "Choose File / No file chosen" (confirmado em A03 e A08).
  - (e) Área avançada com "SHADOW", "Evidence V2", "P&D", `sample-id` e rótulos de rota `/analytics`, `/settings`. Ver também **U-11**.
- **Evidência:** `EXT/falhas/P-08-mensagens/` (41-cenario-banco-ausente.log, 44-cenario-fastq-malformado.log); `EXT/visual/04-new-03-amostra.png`, `EXT/visual/10-advanced.png`; `CAP/A03-configuracao-tecnica-preparar-banco.png`, `CAP/A08-wizard-amostra-vazia.png`.
- **Provável local no código:**
  - (a) `SRC/src/genein/pipeline/cli.py:88`.
  - (b) `SRC/scripts/pipeline/sample_steps.sh:176` (mensagem de sucesso baseada só na contagem de linhas) e `SRC/scripts/lib/input_validation.py:70` (`FASTQ invalido em {path}, registro {record_no}`).
  - (c) `SRC/dashboard/js/operational.js:108`.
  - (e) `SRC/dashboard/js/advanced.js:20` (badge "SHADOW"), `:43-47` (cartões), `:29` (o rótulo de rota vem de `href`), `:51` (placeholder `sample-id`); `SRC/dashboard/js/operational.js:42` (mesmo padrão na Início).
  - (d) não localizado no código: é o controle nativo `<input type="file">`, em `operational.js:110-112`.
- **(f) Observado na 2ª SUINO01 (etapa 1, relato da sessão; sem captura):** a etapa 1 mostra "Ambiente pronto" duas vezes seguidas: o título do painel e o resumo devolvido por `/api/preflight` ("Ambiente pronto."). Locais: `SRC/dashboard/js/operational.js:176` (título) e `SRC/scripts/dashboard/config.py:163` (resumo). Sugestão: usar o resumo para dizer o que foi verificado ("fastp, SPAdes, Velvet e BLAST encontrados").
- **Observado de novo na 2ª SUINO01 (D01):** o texto "Upload de R1/R2 ou ZIP, como na versão anterior." continua na etapa 3, e o seletor de arquivo segue em inglês ("Choose File" / "No file chosen").
- **Observado de novo na 3ª SUINO01 (`CAP/G02_amostra_SUINO01.png`):** "como na versão anterior" e "Choose File / No file chosen" continuam na etapa 3.
- **(g) Log do Acompanhar em português e inglês misturados (3ª SUINO01, job `f6507ec4…`; `CAP/G05_acompanhar_inicio.png`, `CAP/G06_acompanhar_30s.png`):** no mesmo bloco aparecem "Configuração efetiva", "Amostra", "Verificando integridade e pareamento" e, junto, "Analysis profile: assembly-consensus", "[PIPELINE] Sample key", "Input paired-end", "Montador velvet concluido" (sem acento) e "[OK] Evidence V2 artifact set is complete and internally readable". No meio do log também sai o JSON cru do preflight do remapeamento (`{"commands": {"bowtie2": …}, "policy": …, "valid": true}`). Linhas em `EXE/SUINO01_f6507ec4/logs/ux_f6507ec470c94b5dba0565ec8cfc3c97.log` (linhas 9–16, 153–159 e 176–177). Mesmo padrão nas execuções anteriores (o log é gerado pelo mesmo código). Prováveis locais: `SRC/scripts/pipeline/sample_steps.sh` (bloco "Configuração efetiva" e mensagens `[PIPELINE]`), `SRC/scripts/evidence/run.sh` (mensagem final em inglês e saída do preflight sem redirecionamento). Sugestão: um idioma só (português) nas mensagens que a pessoa vê, e o JSON do preflight só no arquivo de log.
- **Sugestão de correção:** traduzir e dar ação ("Banco não encontrado neste prefixo; prepare com …"); dizer a regra violada do FASTQ (linha `+` ausente / qualidade truncada) e não anunciar "sucesso" antes da validação completa; remover "como na versão anterior"; usar um botão próprio que dispare o `<input type=file>` oculto, com texto em português; trocar os rótulos técnicos por nomes em português.

### P-09 — Mapeamento direto experimental falha sem `.git` (ZIP); suíte operacional reprova (Média · pipeline · corrigido — 97fcbde67489)

**Correção de engenharia na b2:** commit `97fcbde6748904216063014eff5ce9396f5c2589`. Verificação: scripts/tests/run_test_suite.sh; trilha operational no ZIP sem .git. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** `bash bundle/run.sh test-operational` (passo `test_direct_map_e2e_real.sh`) e, possivelmente, `/api/experimental/direct-map/run` no painel (Área avançada → "P&D e mapeamento direto"; não testado pela interface).
- **Esperado:** sem git, usar a identidade da entrega (`RELEASE.json` + `SHA256SUMS.txt`) ou declarar a função indisponível com mensagem clara.
- **Observado:** `ValueError: repository commit cannot be resolved; experiment is NOT_REPRODUCIBLE`. Os passos seguintes da suíte não rodaram; executados um a um, todos passaram. Com `git init`, o teste passa.
- **Evidência:** `EXT/falhas/P-09-direct-map-sem-git/`; `EXTLOG/62-suite-operacional.log`, `EXTLOG/63-reproducao-P09-direct-map.log`, `EXTLOG/69-diagnostico-P09-com-git.log`.
- **Provável local no código:** `SRC/scripts/experimental/direct_map/experimental_direct_map.py:1386-1390` (`git_head`) e `:1405` (status do repositório).
- **Sugestão de correção:** fallback para `RELEASE.json`/`SHA256SUMS.txt`, ou ocultar/desabilitar a função na distribuição ZIP com aviso. Revisar as linhas `MISSING hist1/hist2 …logs/etapa3/…` do teste do Mapper (logs históricos ausentes no ZIP).

### P-10 — O guia manda usar "Bancos", que não existe; o preparo do banco fica escondido na Área avançada experimental (Média · documentação / interface · corrigido — 238d762e34fa)

**Correção de engenharia na b2:** commit `238d762e34fa1958b831d736c5e08c4a237054e0`. Verificação: PAINEL_HEADLESS.json; docs/uso-e-bancos.md. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Confirmado e ampliado pelo teste de usabilidade (capturas A01, A02 e A03). Este item absorve o primeiro achado de usabilidade.*

- **Onde aparece:** `docs/beta-pesquisadores.md`, "Primeira utilização", passo 1: "Prepare o banco em **Bancos** ou siga uso e bancos".
- **Esperado:** um menu ou seção "Bancos", ou um caminho evidente para preparar o banco, como o guia descreve.
- **Observado (teste externo):** o menu tem Início, Nova análise, Acompanhar, Resultados, Histórico e Área avançada; nada se chama "Bancos".
- **Observado (usabilidade):** a persona não encontrou "Bancos" (A01). O preparo fica na Área avançada → **Configuração técnica** (A02 → A03), área marcada com a faixa **"EXPERIMENTAL / SHADOW — Modo sombra: área técnica e experimental, separada da jornada operacional principal"**. O painel "Preparar banco viral" está **no fim da página**, depois de:
  1. "Editar configuração operacional", um editor de chaves como ASSEMBLER, THREADS e BLAST_EVALUE;
  2. o botão vermelho **"Reconstruir ambiente"**;
  3. a tabela crua "Configuração operacional efetiva", com chaves como `QC_ADAPTER_R1` e `HOST_INDEX_PREFIX`;
  4. "Importar amostra".

  A descrição do cartão na Visão geral ("**Ambiente, Evidence V2 e importação de amostras**") não menciona bancos (A02). Quem não conhece o código não tem motivo para entrar ali.
- **Evidência:** `EXT/visual/01-home.png`, `EXT/visual/03-new-02-banco.png`, `EXT/visual/10-advanced.png`; `CAP/A01-inicio-sem-menu-bancos.png`, `CAP/A02-area-avancada.png`, `CAP/A03-configuracao-tecnica-preparar-banco.png`.
- **Provável local no código:**
  - `SRC/docs/beta-pesquisadores.md:37` (texto "Bancos").
  - `SRC/dashboard/js/advanced.js:47` (descrição do cartão "Configuração técnica").
  - `SRC/dashboard/js/advanced.js:236-275`, a ordem dos painéis em `renderSettings`: `configEditor` (`:238`, que inclui "Reconstruir ambiente" em `:210-219`), tabela crua (`:239`), importação (`:240`) e só então "Preparar banco viral" (`:241-275`).
  - `SRC/dashboard/js/advanced.js:15` e `:20` (faixa SHADOW / "Modo sombra").
  - Menu principal: `SRC/dashboard/index.html` (sem item "Bancos").
- **Sugestão de correção:** criar um item de menu **"Bancos"** na jornada operacional, fora da Área avançada, com a lista dos bancos, o estado de cada um (preparado / não preparado, nº de sequências, data) e o botão "Preparar". Enquanto isso não existir: corrigir o guia ("Área avançada → Configuração técnica → Preparar banco viral"), mencionar bancos na descrição do cartão e levar o painel "Preparar banco viral" para o topo da página. Ver também **U-01** (preparo/estado na etapa 2).
- **Observado de novo na SUINO01 (08/10, ~15:34):** o mesmo caminho escondido vale para o **índice de hospedeiro customizado**. O único lugar para informá-lo é Área avançada (faixa EXPERIMENTAL) → Configuração técnica → "Filtro de hospedeiro" (`SRC/dashboard/js/advanced.js:176-193`). E, mesmo salvo ali, o painel não o usa (**U-06**).

### P-11 — A Revisão mostra o montador como "consensus" e a Configuração, como "MULTI" (Baixa · interface · corrigido — 7b053a6bc8ef)

**Reteste b3:** Cabeçalho, configuração efetiva e encerramento do log apresentam MULTI; identificador técnico consensus continua inalterado nos contratos. Commit `7b053a6bc8ef81d276bb71ae0deb0cead239a8a1`.

**Correção de engenharia na b2:** commit `db8bf2b2ee4a322214398d87ee3dc006ba7a17a9`. Verificação: PAINEL_HEADLESS.json (revisão MULTI). A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Confirmado na usabilidade (A11/A12 × A13). Os outros problemas da Revisão estão em **U-08**.*

- **Onde aparece:** assistente Nova análise, etapa 4 (Configuração) × etapa 5 (Revisão).
- **Esperado:** a Revisão repete o rótulo escolhido, "MULTI — SPAdes, metaSPAdes e Velvet".
- **Observado:** a Revisão mostra "Montador: consensus". Na usabilidade, o comando iniciado foi `--analysis-profile assembly-consensus` (o perfil MULTI), ou seja, **a execução corresponde à escolha** e a divergência é só de texto. O log ainda mostra "Assembler: consensus" (`SRC/logs/AMOSTRA01_pipeline.log`, linha 2).
- **Evidência:** `EXT/visual/05-new-04-configuracao.png`, `EXT/visual/06-new-05-revisao.png`; `CAP/A12-configuracao-adaptadores.png`, `CAP/A13-revisao.png`.
- **Provável local no código:** `SRC/dashboard/js/operational.js:224` (`value: "consensus"`, texto "MULTI — …"), `:246` (a Revisão exibe `wizard.assembler` bruto), `:273` (`consensus` → `assembly-consensus`).
- **Observado de novo na SUINO02 (`CAP/E01_revisao.png`):** Revisão com "Banco: picornaviridae_refseq" e "Montador: consensus"; o log abre com "Perfil: assembly-consensus  Assembler: consensus".
- **Observado de novo na SUINO_NEG (`CAP/F01_revisao_SUINO_NEG.png`):** Revisão com "Banco: picornaviridae_refseq" e "Montador: consensus". A etapa 6 continua dizendo só "A análise usará o perfil configurado" (`SRC/dashboard/js/operational.js:281`).
- **Observado de novo na 2ª SUINO01:** a Revisão (`CAP/D03_revisao.png`) mostra "Banco: picornaviridae_refseq" e "Montador: consensus", nomes internos, enquanto a etapa 2 mostra "Picornaviridae (RefSeq) [recomendado]" e a etapa 4 mostra "MULTI — SPAdes, metaSPAdes e Velvet". A etapa 6 diz só "A análise usará o perfil configurado" (`SRC/dashboard/js/operational.js:281`; `CAP/D04_execucao_pre_submit.png`), sem nomear o perfil; o log abre com "Perfil: assembly-consensus".
- **Observado de novo na SUINO01:** etapa 4 com "MULTI — SPAdes, metaSPAdes e Velvet" (`CAP/C09_wizard04_host_adaptadores.png`) e Revisão com "Montador: consensus" (`CAP/C10_wizard05_revisao_antes_indice.png`). O log repete "Assembler: consensus" (`EXE/SUINO01_1088e943/logs/SUINO01_pipeline.log`, linha 2).
- **Sugestão de correção:** mostrar na Revisão o texto da opção, por exemplo com um mapa `{consensus: "MULTI — SPAdes, metaSPAdes e Velvet", …}`. Se possível, usar "MULTI" também no cabeçalho do log.

---

## Problemas do teste de usabilidade (U-01 em diante)

### U-01 — Etapa 2 "Banco viral" sem status de preparo, sem botão de preparar e sem aviso de que o banco precisa existir (Média · interface · corrigido — 5c912d3023a6)

**Correção de engenharia na b2:** commit `5c912d3023a693c63c161fd6c43380d8b6ed8465`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Nova análise → 2. Banco viral (A06 vazio; A07 com "Picornaviridae (RefSeq) [recomendado]").
- **Esperado:** ao escolher um banco, a pessoa vê se ele está **preparado** (nº de sequências, data) ou **não preparado**. Se não estiver, aparece um botão "Preparar agora" ou um aviso claro do que acontece.
- **Observado:** só há o seletor "Banco de referência", com a ajuda "A seleção delimita a busca por homologia; não altera limiares científicos.", e o campo de query NCBI. Nada diz se o banco existe, se precisa ser preparado ou o que acontece se não estiver. Pelo código, se o banco não existir, o pipeline tenta montá-lo durante a execução. O usuário não é avisado disso (possível download grande, por exemplo "ALL [gigante]").
- **Evidência:** `CAP/A06-wizard-banco-vazio.png`, `CAP/A07-wizard-banco-picorna-refseq.png`. `GET /api/dbs` (consultado em 08/10 ~13:50) devolve só `id`, `label` e `query`, sem nenhum campo de estado.
- **Provável local no código:**
  - `SRC/dashboard/js/operational.js:178-204` (etapa 2: só seletor e query) e `:17-20` (`databaseReady` considera "pronto" qualquer banco selecionado).
  - `SRC/scripts/ops/db_manager.sh:139-162` (`list --json`: só `id`, `label` e `query`) e `SRC/scripts/dashboard/config.py:194-208` (`list_db_profiles`).
  - Preparo implícito: `SRC/scripts/pipeline/sample_steps.sh:220-232` (`make db-blast`/`db` quando o banco não valida).
- **Observado de novo na SUINO01 (C03/C04):** o seletor tem 10 opções (9 bancos de `GET /api/dbs` + "Outro vírus"), sem indicação de quais estão preparados. Em `SRC/blastdb/` só existe `picornaviridae_refseq` (consulta somente leitura, 08/10 ~15:45).
- **Sugestão de correção:** em `db_manager.sh list --json`, incluir `prepared` (manifesto existe e `validate_blast_database` OK), `sequences`, `created_at` e `size`. Na etapa 2, mostrar um selo "Pronto (206 sequências, 08/10 13:44)" ou "Não preparado" com botão "Preparar agora" (`action: build_db`). Avisar quando a execução vai baixar o banco e mostrar uma estimativa do tamanho (sobretudo "[gigante]").

### U-02 — Depois de preparar o banco: barra superior continua em "Banco: Não selecionado", a única ação é "Abrir resultados" e não há mensagem final clara (Média · interface · corrigido — 101803ce5186)

**Correção de engenharia na b2:** commit `101803ce5186b5faa92fc9f6ea54ef501140e26b`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Acompanhar, logo depois do job "Preparar banco" (`build_db`, job `fa045e2b8f3042e2abdfabba69c15dcd`, concluído em ~8 s: 206 sequências, BLAST + índice Bowtie2).
- **Esperado:** mensagem simples, por exemplo "**Banco pronto: Picornaviridae RefSeq, 206 sequências**", e próxima ação coerente ("Usar este banco em uma nova análise"), com a barra superior refletindo o banco.
- **Observado:**
  - A barra superior continua em **"Banco: Não selecionado"** e também **"Ambiente: Verificando"** (A04).
  - O único botão é **"Abrir resultados"**, que não faz sentido para um job de banco.
  - O log mistura a saída do `make`, os SHA-256 de cada arquivo e o JSON do manifesto. Sobre a natureza do job, só diz "Status técnico: Concluída". A última linha útil é `[INFO] [?] [?] — OK (DB=picornaviridae_refseq)`.
- **Evidência:** `CAP/A04-banco-preparado-log.png`; `SRC/logs/ux_fa045e2b8f3042e2abdfabba69c15dcd.log` (fim: `OK (DB=picornaviridae_refseq)`); `SRC/logs/ux_dashboard.log` (job enfileirado às 13:44:39).
- **Provável local no código:**
  - `SRC/dashboard/js/operational.js:333` ("Abrir resultados" para qualquer job `done`/`partial`, sem olhar o tipo de ação).
  - `SRC/dashboard/js/state.js:22-24` (`activateJob` só atualiza `context.job`).
  - `SRC/dashboard/js/main.js:11` (contexto inicial "Verificando"/"Não selecionado"; o banco só é atualizado no assistente, em `operational.js:190-196`, e o ambiente só no carregamento do assistente, em `operational.js:165`).
  - `SRC/scripts/ops/db_manager.sh:431` (mensagem final `OK (DB=${DB})`, sem contagem); `SRC/scripts/lib/common.sh:16` (`[?] [?]` quando `PIPELINE_ETAPA`/`SAMPLE_NAME` não existem, caso do job de banco).
- **Observado de novo na 3ª SUINO01 (`CAP/G01_historico.png`, ~17:37):** no Histórico, aberto fora do assistente, a barra superior mostra "AMBIENTE ↻ **Verificando**" (ícone de carregamento), "Banco: Não selecionado", "Amostra: Não selecionada" e "Execução: Aguardando", embora o ambiente estivesse pronto e cinco execuções aparecessem na tabela logo abaixo. Ao entrar no assistente, o ambiente passa a "Pronto" (`CAP/G06_acompanhar_30s.png`). O valor inicial "Verificando" vem de `SRC/dashboard/js/main.js:11`, e o ícone de "em andamento" vem de `main.js:27`. Ele só é trocado quando o assistente carrega o ambiente (`operational.js:165`). Para quem chega pelo Histórico, parece que algo está sendo verificado e nunca termina.
- **Sugestão de correção:** guardar a ação do job (`build_db`) no `activeJob` e, ao concluir, mostrar o painel "Banco pronto" (nome, nº de sequências, caminho) com o botão "Usar em nova análise", que preenche `wizard.database` e `context.database`. Esconder "Abrir resultados" para jobs que não são de análise. Imprimir no fim do `db_manager.sh` algo como `Banco pronto: <label> — N sequências (BLAST + Bowtie2)`. Atualizar o estado do ambiente na barra em todas as rotas. Mandar o JSON do manifesto só para o arquivo de log, não para a saída principal.

### U-03 — O log técnico perde todas as quebras de linha e vira um bloco corrido (Média · interface · corrigido — e75f4678f280)

**Correção de engenharia na b2:** commit `e75f4678f280a6cd95804fda89471abd4ab6f1c6`. Verificação: scripts/tests/test_u03_byte_parity.py; PAINEL_HEADLESS.json (linhas separadas). A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Acompanhar → "Log técnico", **em todas as execuções**: preparo de banco (A04) e pipeline (A15).
- **Esperado:** uma linha por mensagem, legível; idealmente com um resumo em linguagem simples por cima do log bruto.
- **Observado:** o texto chega sem `\n`, então mensagens e JSON ficam colados ("…picornaviridae_refseq=====…[INFO] … reads detectadas.== [2026-10-08 13:46:19] Configuração efetiva =="). A causa foi confirmada no código: o servidor tira o `\n` de cada linha ao guardá-la e depois junta as linhas com string vazia. O CSS está certo (`.log-output { white-space: pre-wrap }`). Outros detalhes do log:
  - uma linha solta "150000" logo abaixo de "Configuração efetiva";
  - prefixos `[?] [?]` no job de banco;
  - "150000 **reads** detectadas", quando são 150.000 **pares** (300.000 reads, conforme o fastp);
  - erro de digitação no marcador de truncamento ("linhas omissoas").
- **Evidência:** `CAP/A04-banco-preparado-log.png`, `CAP/A15-acompanhar-em-execucao.png`. `GET /api/job/59349d8fa52c4f24894789607ebff9f7` (somente leitura, ~13:50): o campo `output` vem sem quebras. O arquivo `SRC/logs/ux_59349d8fa52c4f24894789607ebff9f7.log` tem as quebras corretas.
- **Provável local no código:**
  - `SRC/scripts/dashboard/jobs.py:1011-1014` (`line_clean = line.rstrip("\r\n")` → `output_buf.append(line_clean)`) e `SRC/scripts/dashboard/handler.py:505` (`"output": "".join(job.get("output", []))`).
  - Linha "150000": `SRC/scripts/pipeline/sample_steps.sh:183` (`input_validation.py fastq … --mate …` imprime a contagem; falta `>/dev/null`).
  - "reads detectadas": `SRC/scripts/pipeline/sample_steps.sh:176`.
  - `[?] [?]`: `SRC/scripts/lib/common.sh:13-19`.
  - "omissoas": `SRC/scripts/dashboard/jobs.py:388`.
- **Observado de novo na SUINO01 (job `1088e943…`):** o campo `output` de `/api/job` continua sem quebras de linha ("…DB: picornaviridae_refseq==============================================[INFO]…"), com a linha solta "12800" após "Configuração efetiva" e "12800 reads detectadas" para 12.800 **pares** (25.600 reads, segundo o fastp). O arquivo `SRC/logs/ux_1088e943d91d42cf819e9b3e14cca12b.log` tem as quebras. Evidência: `EXE/SUINO01_1088e943/api/job_1088e943d91d42cf819e9b3e14cca12b.json`, `EXE/SUINO01_1088e943/logs/`.
- **Observado de novo na SUINO_NEG (job `469b1a6f…`):** o log do painel sai corrido, sem quebras de linha (`CAP/F03_acompanhar_30s.png`), com a linha solta da contagem logo após "Configuração efetiva ==".
- **Observado de novo na SUINO02 (job `ce2c576a…`):** linha solta "14400" logo após "Configuração efetiva ==" (log, linhas 7–8) e "14400 reads detectadas" para 14.400 pares (linha 5). No painel o log aparece corrido: "…Configuração efetiva ==14400Amostra: SUINO02Analysis profile: …" (`CAP/E03_acompanhar_30s.png`).
- **Observado de novo na 2ª SUINO01 (job `885535c1…`):** a linha solta "12800" logo após "== … Configuração efetiva ==" (log, linhas 7–8) e "12800 reads detectadas" (linha 5) para 12.800 pares. Mesma causa (`sample_steps.sh:183`).
- **Observado de novo na 3ª SUINO01 (job `f6507ec4…`):** log corrido no painel (`CAP/G06_acompanhar_30s.png`: "…Configuração efetiva ==12800Amostra: SUINO01Analysis profile: …"), linha solta "12800" (log, linha 8) e "12800 reads detectadas" para 12.800 pares (linha 5).
- **Sugestão de correção:** `handler.py:505` → `"\n".join(...)`. Redirecionar a saída de `input_validation.py` em `sample_steps.sh:183`. Escrever "150000 pares de reads (300000 reads)". Omitir os campos `[?]` quando estiverem vazios. Corrigir "omitidas". Considerar um resumo amigável ("Etapa atual: montagem", "QC: 45.376 reads com adaptador cortado") acima do log bruto.

### U-04 — "Acompanhar" promete etapas, mas a lista nunca aparece no pipeline (Baixa · interface · corrigido — 31462bafac96)

**Correção de engenharia na b2:** commit `31462bafac96ee4fe861198516ab17bb6866d89f`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Acompanhar, durante o pipeline (A15). O cabeçalho diz "Etapas e tempo decorrido real".
- **Esperado:** a lista de etapas (QC, filtro de hospedeiro, montagem, BLAST, Evidence) com o estado de cada uma.
- **Observado:** só aparecem o status geral, o tempo e o log. `GET /api/job/<id>` devolve `"stage_status": null` durante a execução, já na fase de BLAST.
- **Evidência:** `CAP/A15-acompanhar-em-execucao.png`; resposta de `/api/job/59349d8fa52c4f24894789607ebff9f7` (~13:50).
- **Provável local no código:** `SRC/dashboard/js/operational.js:316` (só desenha se `Array.isArray(job.stage_status)`); `SRC/scripts/dashboard/jobs.py:1018-1020` (`stage_status` só é preenchido, **como string**, para `[CONTIG_COMPARE][STATE]`). O pipeline grava as etapas em `results/evidence/state/<run_id>.json` (`evidence_state_stage` em `sample_steps.sh`, por exemplo `:197`), mas isso não é repassado.
- **Sugestão de correção:** no `/api/job`, ler `results/evidence/state/<run_id>.json` (ou as linhas `== [n/6] … ==` do log) e devolver um array `[{id, label, status, started_at, finished_at}]`. Unificar o tipo usado pelo contig-compare.

### U-05 — Upload sem indicador de progresso (Baixa · interface · corrigido — 61325884955e)

**Reteste b3:** Barra mostra progresso de envio por eventos reais do navegador; validação no servidor é uma fase distinta. FormData não é transformado; HTTP 409 e confirmação de substituição preservados. Commit `61325884955ed871704ebe3b7791823cbb09bfde`.

**Correção de engenharia na b2:** commit `3cfa3070ca24b15d5379a54f28311234e6b5f514`. Verificação: scripts/tests/test_u05_byte_parity.py; PAINEL_HEADLESS.json (upload em andamento). A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Nova análise → 3. Amostra → "Importar upload" (A09 → A10).
- **Esperado:** botão desabilitado com "Enviando…"/barra de progresso e aviso de que pode demorar com arquivos grandes (limite de 500 MB).
- **Observado:** cerca de 6 s sem nenhum sinal (o botão continua ativo e é possível clicar de novo). Depois, o toast "Amostra importada: AMOSTRA01" aparece e a amostra é selecionada (isso é positivo com uma amostra só; com duas importações seguidas, a troca silenciosa vira risco — ver **U-29**). Com FASTQs reais de centenas de MB, a espera será muito maior.
- **Evidência:** `CAP/A09-upload-sem-feedback.png`, `CAP/A10-amostra-importada.png`; `SRC/logs/ux_dashboard.log` (13:45:41 "Upload importado com sucesso: sample='AMOSTRA01'").
- **Provável local no código:** `SRC/dashboard/js/operational.js:91-105` (o `onsubmit` chama `postForm` sem desabilitar o botão nem mostrar estado) e `:113` (botão). `SRC/dashboard/js/api.js` (`postForm` com `fetch`, sem progresso).
- **Observado de novo na SUINO01 (C06 → C07):** o upload de 2 × ~1,8 MB também ficou sem nenhum indicador até o toast; `SRC/logs/ux_dashboard.log` registra a importação às 15:33:21.
- **Observado na 2ª SUINO01 (D01):** reenviar arquivos para um nome já importado falha com o toast **"Amostra 'SUINO01' ja existe; confirme substituicao explicitamente"** (sem acentos). O formulário não muda e **não há nenhum botão ou caixa para confirmar a substituição**, então a pessoa não consegue cumprir o que a mensagem pede. A lista "Amostra pareada já importada" também não mostra de onde vieram os arquivos, quantas reads têm nem o tamanho: só o nome ("SUINO01"), e não há como saber se é a amostra reduzida ou a completa. Locais: `SRC/dashboard/js/operational.js:207-211` (rótulo e texto de ajuda "Amostras em data/raw com R1 e R2 válidos."; a opção usa só o nome) e `SRC/scripts/dashboard/handler.py:180` (`list_samples` devolve apenas nomes). Mensagem de nome repetido: `handler.py:229-230`; formulário de upload: `operational.js:91-105`.
- **Observado na SUINO02/SUINO_NEG (16:59; relato da sessão, sem captura da importação):**
  - (a) "Importar upload" ficou mais de 5 s sem nenhum retorno, de novo.
  - (b) Ao terminar, aparece só o toast "Amostra importada: SUINO02". Não há resumo do que foi importado (nomes dos arquivos, tamanho, número de pares/reads), então não dá para conferir se o par certo entrou. A resposta do servidor também só traz nome e caminhos (`SRC/scripts/dashboard/handler.py:779-785`: `message`, `sample_id`, `r1`, `r2`, `source_scope`); o toast vem de `SRC/dashboard/js/operational.js:101`. Para comparação, o pipeline conta 14.400 pares logo no início do job (log, linha 5), mas isso só aparece depois de executar.
  - (c) "Próximo" na etapa 2 (Banco) também ficou mais de 5 s sem retorno. Pelo código, a passagem da etapa 2 para a 3 não chama o servidor (`operational.js:285`: `setStep(wizard.step + 1)` → `rerender`); a causa da espera não foi localizada. Não há indicador de "carregando" nessa troca.
- **Sugestão de correção:** desabilitar o botão e mostrar um `statusPanel("loading", "Enviando arquivos…")`. Para progresso real, usar `XMLHttpRequest.upload.onprogress`. Reabilitar o botão em caso de erro. Depois da importação, mostrar um resumo fixo na etapa ("SUINO02: R1 SUINO02_S1_L001_R1_001.fastq.gz, 2,0 MB; R2 …, 2,1 MB; 14.400 pares"). Na resposta 409, oferecer "Substituir a amostra existente" (envia `replace=true`; hoje `SRC/scripts/dashboard/handler.py:214` tem o parâmetro, mas a chamada em `:765-770` nunca o passa e a interface não tem o campo) com aviso do que será sobrescrito. Acentuar a mensagem.

### U-06 — Filtro de hospedeiro: assistente sem "custom" (índice próprio), índice Sus scrofa ausente e nenhuma orientação; o caso humano está fora do desenho (Alta, era Média · interface / pipeline · corrigido — 29ae0e0a49ce)

**Correção de engenharia na b2:** commit `29ae0e0a49ce1e8714011a953df1220496c07cdd`. Verificação: scripts/tests/test_u06_byte_parity.py; PAINEL_HEADLESS.json. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Enquadramento: o cenário em células humanas é do testador e fica fora do desenho suíno do programa. O que vale para o desenho: o assistente não oferece `custom` (que o backend aceita), o índice Sus scrofa não vem no pacote e a ajuda é insuficiente. A falta de uma opção "Humano" não é cobrada como defeito.*

- **Onde aparece:** Nova análise → 4. Configuração → Configurações técnicas → "Filtro do hospedeiro" (A11).
- **Esperado:** uma opção "Outro hospedeiro (índice próprio)", útil para qualquer hospedeiro (no cenário de teste, células humanas RD), com instrução de como obter ou criar o índice. A ajuda deve explicar o que o filtro faz.
- **Observado:**
  - Só existem "Sem filtro de hospedeiro" e "Sus scrofa". A ajuda é apenas "**Opt-in explícito.**", sem dizer o que faz nem como acrescentar outro hospedeiro.
  - A persona escolheu "Sem filtro". **As reads humanas permanecem** na montagem e no BLAST.
  - Pelo código (não testado na interface), há mais dois problemas. (a) A opção "Sus scrofa" aponta para `ref/host/sus_scrofa_bt2`, que **não vem no pacote** (a pasta `SRC/ref/` não existe). (b) O backend aceita o modo `custom` (nome + prefixo Bowtie2) e a Configuração técnica permite salvar e validar `HOST_INDEX_PREFIX`, mas **o assistente não oferece "custom"** e sempre envia `host_filter_mode`, que sobrepõe a configuração salva. A própria tela de configuração diz "O assistente operacional envia host_filter_mode".
- **Evidência:** `CAP/A11-configuracao-hospedeiro-so-sus-scrofa.png`; `SRC/data/incoming/AMOSTRA01.json` e `SRC/tmp/AMOSTRA01.resolved_config.json` (`host_filter_enabled: "false"`); `SRC/data/host_removed/` vazio; `/workspace/genein-pesquisador/dados/LEIA-ME_DADOS.md` (objetivo 2: "Separar/remover o que é da célula hospedeira (humana)").
- **Provável local no código:**
  - `SRC/dashboard/js/operational.js:231` (só `none` e `sus_scrofa`), `:234` ("Opt-in explícito.") e `:247` (Revisão).
  - `SRC/scripts/dashboard/jobs.py:714-733` (`none` → `HOST_FILTER_ENABLED=false`; `sus_scrofa` → `REPO_ROOT/ref/host/sus_scrofa_bt2`; `custom` suportado).
  - `SRC/dashboard/js/advanced.js:176-193` (filtro na Configuração técnica, com "Validar índice").
  - `SRC/Makefile:296-298` (`host-db` gera um índice sempre com o nome `sus_scrofa_bt2`); `SRC/scripts/ops/prepare_host_reference.sh` e `SRC/scripts/ops/validate_host_index.sh` existem, mas não estão expostos na interface.
- **Reproduzido na execução SUINO01 (job `1088e943d91d42cf819e9b3e14cca12b`, 08/10 15:34:35–15:35:00):** o que estava "pelo código, não testado" aconteceu de fato.
  1. A persona salvou na Configuração técnica (Área avançada, faixa EXPERIMENTAL) `HOST_FILTER_ENABLED=true`, `HOST_NAME=Sus scrofa` e `HOST_INDEX_PREFIX=/workspace/genein-pesquisador/host-suino/sus_scrofa_reduzido_TESTE_bt2` (`SRC/logs/ux_dashboard.log`, 15:34:14, "Configuração salva"; `SRC/config/picornavirus.env`). O índice é legível (`bowtie2-inspect -s`: 3 sequências).
  2. No assistente, a única forma de ligar o filtro é escolher "Sus scrofa" (`CAP/C09_wizard04_host_adaptadores.png`). O job foi enviado com `host_filter_mode: 'sus_scrofa'` (`ux_dashboard.log`, 15:34:35).
  3. O backend trocou o prefixo salvo pelo caminho fixo: `SRC/scripts/dashboard/jobs.py:717-720` (`env["HOST_INDEX_PREFIX"] = str(REPO_ROOT / "ref" / "host" / "sus_scrofa_bt2")`). O ambiente do job tem prioridade sobre `config/picornavirus.env` (`SRC/scripts/pipeline/prepare_run.sh:46-80`). `SRC/tmp/SUINO01.resolved_config.json` registra `"host_index_prefix": ".../Gene-In-2.0.0b1/ref/host/sus_scrofa_bt2"`.
  4. Depois do QC (~22 s), o pipeline parou: `[FATAL] [QC_PREFLIGHT] [SUINO01] — Índice completo do hospedeiro 'Sus scrofa' não encontrado ou inválido em /workspace/genein-pesquisador/Gene-In-2.0.0b1/ref/host/sus_scrofa_bt2.` (`SRC/logs/SUINO01_pipeline.log`, linha 150; `SRC/scripts/pipeline/sample_steps.sh:279-283`). Filtro de hospedeiro, montagem, BLAST e resgate: **NÃO EXECUTADO**.
  5. Consequência: **pela interface, não existe caminho que use um índice de hospedeiro.** "Sus scrofa" sempre aponta para uma pasta que o pacote não traz; "Sem filtro" força `HOST_FILTER_ENABLED=false` (`jobs.py:715-716`) e também ignora a configuração salva; a execução individual da Área avançada envia `host_filter_mode: "none"` fixo (`SRC/dashboard/js/advanced.js:281`, `:295`); o modo `custom` (`jobs.py:721-730`) não é oferecido por nenhuma tela. "Validar índice" diz que o índice é válido, mas nada avisa que ele não será usado.
  6. Textos da tela: no assistente, só "Sus scrofa" com "Opt-in explícito." (`SRC/dashboard/js/operational.js:231`, `:234`), sem dizer se o índice está instalado nem campo de caminho; a Revisão mostra só "Hospedeiro: Sus scrofa" (`:247`; `CAP/C10_wizard05_revisao_antes_indice.png`). Na Configuração técnica, o aviso "A execução usa HOST_FILTER_ENABLED, HOST_NAME e HOST_INDEX_PREFIX. O assistente operacional envia host_filter_mode." (`SRC/dashboard/js/advanced.js:177`) é jargão e não explica a consequência (o valor salvo é sobrescrito). Ver também **U-11**.
  - **Gravidade revista para Alta:** pelo escopo (`ESCOPO_TESTES_GENEIN.md`, item 1: amostras "com muita contaminação do hospedeiro"), o filtro de hospedeiro faz parte do caminho principal. Pela interface ele é impossível de usar, e a configuração salva é ignorada sem aviso.
  - **Evidência:** `EXE/SUINO01_1088e943/` (`DADOS_BRUTOS.md`, `logs/`, `config/SUINO01.resolved_config.json`, `config/picornavirus.env`, `config/picornavirus.env.bak-…`, `sistema/ls_ref_host_padrao.txt`, `sistema/bowtie2-inspect_indice_custom.txt`); `CAP/C09`, `CAP/C10`.
- **Sugestão de correção:** no assistente, acrescentar "Outro hospedeiro (índice Bowtie2 próprio)", com nome, prefixo e o botão "Validar índice" (reaproveitar `/api/host-index/validate`). Esconder ou desabilitar "Sus scrofa" quando o índice não existir. Escrever uma ajuda em linguagem simples ("Remove reads do organismo hospedeiro antes da montagem. Precisa de um índice do genoma do hospedeiro; veja como preparar"). Documentar como preparar um índice humano (`prepare_host_reference.sh`) e generalizar o alvo `host-db` para aceitar um nome de hospedeiro. Complemento (SUINO01): enquanto o assistente não tiver "custom", fazer o modo `sus_scrofa` usar `HOST_INDEX_PREFIX` salvo quando ele existir e for válido (em vez do caminho fixo de `jobs.py:720`), ou bloquear "Sus scrofa" na etapa 4/6 com a mensagem "índice não instalado". Mostrar na Revisão o caminho do índice que será usado.

### U-07 — Adaptadores e filtro de hospedeiro escondidos em "Configurações técnicas" (fechado); a ajuda não cita SampleSheet nem read-through (Média · interface · corrigido — 9be1558a0d2d)

**Correção de engenharia na b2:** commit `9be1558a0d2dcec3bac9b2fe91f71a34171bf515`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Nova análise → 4. Configuração (A11, A12).
- **Esperado:** os campos de adaptador visíveis, ou pelo menos um aviso visível de que há configurações importantes ali. Ajuda do tipo: "Cole aqui as sequências **Adapter / AdapterRead2 do SampleSheet** (adaptadores 3' lidos quando o fragmento é mais curto que a leitura — *read-through*). Se ficar vazio, o programa tenta detectar automaticamente."
- **Observado:** a seção "Configurações técnicas" vem **recolhida**. Dentro dela, ao lado de "k-mer do Velvet", estão os dois parâmetros com impacto real no resultado (filtro de hospedeiro e adaptadores). A ajuda do R1 diz "Use a sequência da biblioteca para remover adaptadores de fragmentos muito curtos. Vazio usa a configuração salva ou detecção automática." Ela não menciona o SampleSheet, não diz que são os adaptadores 3' (read-through) e o R2 não tem ajuda. O guia pede para "informar os adaptadores reais quando houver read-through", mas a tela não ajuda a cumprir isso.
- **Evidência:** `CAP/A11-configuracao-hospedeiro-so-sus-scrofa.png`, `CAP/A12-configuracao-adaptadores.png`; `SRC/docs/beta-pesquisadores.md:39`.
- **Provável local no código:** `SRC/dashboard/js/operational.js:228` (`<details>` "Configurações técnicas" sem `open`), `:234` (filtro de hospedeiro dentro do `details`), `:235-239` (adaptadores e texto de ajuda; R2 sem ajuda).
- **Observado de novo na 2ª SUINO01 (`CAP/D02_configuracao_campos_ocultos_em_configuracoes_tecnicas.png`):** com a seção recolhida, a etapa 4 mostra só "Montagem"; nada indica que filtro de hospedeiro e adaptadores estão ali dentro.
- **Acessibilidade (SUINO02/SUINO_NEG; relato da sessão):** dentro do `<details>` recolhido, as opções do filtro de hospedeiro ("Sem filtro de hospedeiro" / "Sus scrofa") ficam expostas sem rótulo acessível. No código, o campo é um `<select id="wizard-host">` com `<label for>` gerado por `field()` (`SRC/dashboard/js/operational.js:231-234`; `SRC/dashboard/js/components.js:123-128`). Mas a ajuda ("Opt-in explícito.") não está ligada ao campo (falta `aria-describedby`), e o `<summary>` "Configurações técnicas" não diz o que há dentro. A divergência entre o relato e o código fica registrada para conferir com leitor de tela. O mesmo vale para os campos de adaptador (o R2 não tem ajuda).
- **Sugestão de correção:** tirar adaptadores e hospedeiro do `<details>` e criar uma seção visível "Limpeza das leituras". Reescrever a ajuda citando o SampleSheet e o read-through, com exemplo (TruSeq). Dar ajuda ao R2. Validar A/C/G/T/N já no campo (hoje a validação só acontece no backend, em `jobs.py:782-787`).

### U-08 — A Revisão não mostra os adaptadores; "Revisar limites da execução" não se explica e afirma "Integridade verificada" antes da execução (Média · interface · corrigido — 58807b8e57d4)

**Correção de engenharia na b2:** commit `58807b8e57d488dfdcfa6b2d3d751ad3b5cf980a`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*O rótulo "consensus" × "MULTI" é o **P-11**.*

- **Onde aparece:** Nova análise → 5. Revisão (A13).
- **Esperado:** a Revisão lista **tudo** o que vai para a execução: banco, amostra, montagem (rótulo), k-mer, hospedeiro e **adaptadores R1/R2** (ou "detecção automática"). Um botão de "limites" deveria explicar o que é e mostrar informação útil.
- **Observado:** a tabela tem Ambiente, Banco, Amostra, Montador ("consensus"), k-mer e Hospedeiro. **Os adaptadores digitados não aparecem**, então a pessoa não consegue conferir se foram registrados. O botão "Revisar limites da execução" não tem nenhuma explicação. Pelo código, ele abre um modal com "**Integridade verificada** — A execução apresenta resultados calculados e artefatos rastreáveis." e "Os parâmetros usados na análise são carregados da configuração da execução.". Esse texto afirma uma verificação que ainda não ocorreu (nada foi executado) e não diz quais são os limites.
- **Evidência:** `CAP/A13-revisao.png`.
- **Provável local no código:** `SRC/dashboard/js/operational.js:244-249` (linhas da tabela, sem `qcAdapterR1`/`qcAdapterR2`) e `:250-257` (botão e modal).
- **Observado de novo na SUINO_NEG (`CAP/F01_revisao_SUINO_NEG.png`):** a Revisão lista Ambiente, Banco, Amostra ("SUINO_NEG"), Montador, k-mer e Hospedeiro ("Sem filtro"); os adaptadores digitados não aparecem, e também não há linha para o papel da amostra (controle negativo), que o pipeline tem e a interface não oferece (U-30).
- **Observado de novo na SUINO02 (`CAP/E01_revisao.png`):** a Revisão lista Ambiente, Banco, Amostra ("SUINO02"), Montador, k-mer e Hospedeiro ("Sem filtro"); os adaptadores digitados não aparecem, embora tenham sido enviados ao job (`SRC/logs/ux_dashboard.log`, 16:59:41, `qc_adapter_r1`).
- **Observado de novo na 2ª SUINO01 (`CAP/D03_revisao.png`):** a Revisão lista Ambiente, Banco ("picornaviridae_refseq"), Amostra, Montador ("consensus"), k-mer e Hospedeiro ("Sem filtro"). Os adaptadores digitados na etapa 4 não aparecem.
- **Observado de novo na SUINO01:** a Revisão (`CAP/C10_wizard05_revisao_antes_indice.png`) lista Ambiente, Banco, Amostra, Montador ("consensus"), k-mer e Hospedeiro ("Sus scrofa"). Não mostra os adaptadores digitados na etapa 4 (C09) nem o **caminho do índice de hospedeiro** — justamente o valor que a execução trocou (U-06). O modal "Limites desta execução" abriu com "Integridade verificada — A execução apresenta resultados calculados e artefatos rastreáveis." antes de qualquer execução (`CAP/C11_wizard05_modal_limites.png`; `SRC/dashboard/js/operational.js:250-257`).
- **Sugestão de correção:** acrescentar as linhas "Adaptador R1" e "Adaptador R2" (valor ou "detecção automática do fastp") e mostrar o rótulo do montador (P-11). Trocar o modal por um texto real sobre os limites ("triagem exploratória; não confirma espécie nem diagnóstico; o resultado depende do banco escolhido"), sem "Integridade verificada" antes da execução, ou remover o botão.

### U-09 — Adaptadores aplicados corretamente, mas ausentes do comando exibido e da "Configuração efetiva" do log (Baixa · pipeline / interface · corrigido — 2f83b662e15b)

**Correção de engenharia na b2:** commit `2f83b662e15b0e41b791b75e5e7a429110ed978f`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

**Verificação pedida: os adaptadores digitados na interface foram aplicados ao fastp?** **Sim, foram aplicados.** A verificação foi somente leitura, na execução em andamento `59349d8fa52c4f24894789607ebff9f7` (iniciada 13:46:17 BRT; às ~13:52 estava no BLAST read-level). Não houve interferência no job nem no painel.

- **Cadeia confirmada (código + arquivos da execução):**
  1. A interface envia `qc_adapter_r1`/`qc_adapter_r2` nos `params` do job (`SRC/dashboard/js/operational.js:275-276`). O `SRC/logs/ux_dashboard.log` (13:46:17) registra `'qc_adapter_r1': 'AGATCGGAAGAGCACACGTCTGAACTCCAGTCA', 'qc_adapter_r2': 'AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT'`.
  2. O backend converte esses parâmetros em **variáveis de ambiente** `QC_ADAPTER_R1`/`QC_ADAPTER_R2` (validadas A/C/G/T/N), e **não em argumentos de linha de comando** (`SRC/scripts/dashboard/jobs.py:782-787`). Por isso o comando exibido não traz adaptadores.
  3. `SRC/tmp/AMOSTRA01.resolved_config.json` registra `"qc_adapter_r1": "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA"` e `"qc_adapter_r2": "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT"` (`SRC/scripts/pipeline/resolve_config.py:436-437`).
  4. O `qc_fastp.sh` acrescenta `--adapter_sequence`/`--adapter_sequence_r2` (`SRC/scripts/pipeline/qc_fastp.sh:174-175`). O comando fastp efetivo, gravado em `SRC/results/qc/AMOSTRA01_fastp.json` (campo `command`) e no log (`SRC/logs/AMOSTRA01_pipeline.log`, linha 142), termina com `--adapter_sequence AGATCGGAAGAGCACACGTCTGAACTCCAGTCA --adapter_sequence_r2 AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT` (além de `--detect_adapter_for_pe`).
  5. Resultado no fastp (`adapter_cutting`): `read1_adapter_sequence`/`read2_adapter_sequence` iguais às digitadas; **45.376 reads com adaptador cortado**, 2.508.504 bases cortadas, 1.200 reads descartadas como dímero de adaptador; comprimento médio de 150 → 142 pb. As reads limpas estão em `SRC/data/cleaned/AMOSTRA01_R{1,2}.clean.fastq.gz` (13:46).
  6. As sequências digitadas são idênticas às do SampleSheet em `/workspace/genein-pesquisador/dados/LEIA-ME_DADOS.md` (linhas 32-33).
  7. Sobre os caminhos citados no pedido: não existe `config.env` na raiz; o painel usa `SRC/config/picornavirus.env`, com `QC_ADAPTER_R1=`/`QC_ADAPTER_R2=` vazios, então os valores vieram só do job. `results/runs/` também não existe; os artefatos estão em `SRC/results/qc`, `SRC/results/blast`, `SRC/results/evidence/state/` e outros.
- **Onde aparece o problema (transparência):**
  - O comando mostrado (`/api/job/<id>` → `command`): `scripts/pipeline/run.sh --sample AMOSTRA01 --analysis-profile assembly-consensus --evidence-v2 --evidence-profiles config/evidence_profiles.json --kmer 31`. Não tem adaptadores, hospedeiro nem banco (`DB` também vai por ambiente).
  - O bloco "Configuração efetiva" no início do log não lista adaptadores nem filtro de hospedeiro.
  - As linhas `[fastp] …` mostram só `min_len` e `qualified_quality_phred`.
  - A única prova visível para o usuário é a linha longa do comando fastp no meio do log, que, com U-03, fica ilegível. Somada a U-08, a pessoa não tem como confirmar pela interface que os adaptadores foram usados. Quem copiar o comando exibido para reproduzir a análise vai rodar **sem** os adaptadores.
- **Esperado:** o comando/parametrização exibidos refletem tudo o que muda o resultado, e a "Configuração efetiva" lista `QC_ADAPTER_R1/R2` (ou "detecção automática") e `HOST_FILTER_ENABLED/HOST_NAME`.
- **Evidência:** os arquivos listados nos itens 1–6; `CAP/A13-revisao.png`, `CAP/A15-acompanhar-em-execucao.png`.
- **Provável local no código:** `SRC/scripts/dashboard/jobs.py:966` (`command_text = " ".join(cmd)`, sem o `env`) e `:782-787`; `SRC/scripts/pipeline/sample_steps.sh:198-210` (bloco "Configuração efetiva" sem adaptadores/hospedeiro); `SRC/scripts/pipeline/qc_fastp.sh:163-164` (log `[fastp]` sem adaptadores).
- **Observado de novo na 2ª SUINO01 (job `885535c1…`):** os adaptadores digitados foram aplicados (comando fastp no log, linha 142; 797 reads com adaptador cortado, 82 dímeros) e o filtro desligado foi respeitado (log, linha 149: "[3/6] Filtro do hospedeiro ignorado"). O comando exibido e a "Configuração efetiva" seguem sem adaptadores e sem filtro de hospedeiro. Evidência: `EXE/SUINO01_885535c1/logs/ux_885535c1febd48659b8089f60e1e6458.log`, `EXE/SUINO01_885535c1/config/SUINO01.resolved_config.json`.
- **Observado de novo na SUINO01 (job `1088e943…`):** os adaptadores digitados foram aplicados (comando fastp no log, linha 142, e em `results/qc/SUINO01_fastp.json`; `adapter_cutting`: sequências iguais às digitadas, 797 reads com adaptador cortado, 82 dímeros). O comando exibido e a "Configuração efetiva" seguem sem adaptadores e sem filtro de hospedeiro; se o prefixo do hospedeiro estivesse na "Configuração efetiva", o caminho fixo errado do U-06 teria aparecido logo no início do log. Evidência: `EXE/SUINO01_1088e943/logs/SUINO01_pipeline.log`, `EXE/SUINO01_1088e943/results/SUINO01_fastp.json`.
- **Sugestão de correção:** guardar e exibir no job também as variáveis relevantes (`DB`, `QC_ADAPTER_R1/R2`, `HOST_*`), por exemplo `command_display = "QC_ADAPTER_R1=… QC_ADAPTER_R2=… scripts/pipeline/run.sh …"`. Acrescentar `echo "Adaptadores: R1=${QC_ADAPTER_R1:-auto} R2=${QC_ADAPTER_R2:-auto}"` e `echo "Filtro de hospedeiro: …"` na "Configuração efetiva". Fazer `qc_fastp.sh` registrar `log_info "[fastp] adaptadores: …"` e, ao final, "N reads com adaptador cortado".

### U-10 — O rastreador do assistente marca ✓ em etapas ainda não visitadas (Baixa · interface · corrigido — 179c70825965)

**Correção de engenharia na b2:** commit `179c70825965c7a2ccb0aa8fd0170cada3abae84`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Relacionado à observação O-08 do teste externo.*

- **Onde aparece:** barra de etapas 01–06 do assistente.
- **Esperado:** o ✓ indica que a etapa foi visitada ou confirmada pela pessoa.
- **Observado:** a etapa **04 Configuração** aparece com ✓ enquanto a pessoa ainda está na 02 (A07), porque o montador tem valor padrão. A etapa **05 Revisão** aparece com ✓ enquanto a pessoa está na 04 (A11, A12), porque ambiente, banco e amostra já estão válidos. Isso passa a impressão de que as configurações já foram revisadas e incentiva a pular a etapa 4, justamente onde ficam adaptadores e hospedeiro (U-07).
- **Evidência:** `CAP/A07-wizard-banco-picorna-refseq.png`, `CAP/A11-configuracao-hospedeiro-so-sus-scrofa.png`, `CAP/A12-configuracao-adaptadores.png`; `EXT/visual/06-new-05-revisao.png` (O-08).
- **Provável local no código:** `SRC/dashboard/js/operational.js:69-73` (`complete[3] = Boolean(wizard.assembler)`, sempre verdadeiro por causa do padrão `assembler: "consensus"` em `SRC/dashboard/js/main.js:15`; `complete[4]` = ambiente + banco + amostra).
- **Observado de novo na SUINO01:** `CAP/C04_wizard02_banco_selecionado.png` mostra **04 ✓** com a pessoa na etapa 02, antes de visitar a 04; `CAP/C09_wizard04_host_adaptadores.png` mostra **05 ✓** com a pessoa ainda na 04.
- **Observado de novo na SUINO_NEG (`CAP/F01_revisao_SUINO_NEG.png`):** na Revisão, as etapas 01–05 estão com ✓.
- **Observado de novo na SUINO02/SUINO_NEG (relato da sessão; `CAP/E01_revisao.png` mostra 01–05 com ✓ na Revisão):** as marcas ✓ aparecem e somem durante a navegação. É o efeito do mesmo cálculo: o ✓ reflete o estado atual dos valores (ambiente ok, banco válido, `wizard.sample` preenchido), não as etapas visitadas, então muda quando a amostra é trocada, limpa ou recarregada (`SRC/dashboard/js/operational.js:69-73`).
- **Observado de novo na 3ª SUINO01 (`CAP/G02_amostra_SUINO01.png`):** na etapa 3, "04 ✓ Configuração" já aparece marcada antes de a etapa 4 ser aberta.
- **Sugestão de correção:** guardar `wizard.visited` (conjunto de etapas abertas) e marcar ✓ só quando a etapa foi visitada **e** está válida. Opcionalmente, distinguir visualmente "válida" de "conferida".

### U-11 — Jargão técnico para quem trabalha em bancada (Baixa · interface · corrigido — 5b459706ea73)

**Correção de engenharia na b2:** commit `5b459706ea73567fe5c0790ed2f257be375d03c0`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Complementa P-08 (e).*

- **Onde aparece:** várias telas da jornada principal e da Área avançada.
- **Esperado:** termos em português simples, com uma explicação curta (tooltip ou "o que é isto?") nos termos técnicos que forem necessários.
- **Observado:** termos que a persona não entendeu ou que não têm explicação:
  - "**Evidence V2**" (Acompanhar, Histórico, Área avançada);
  - "**preflight**" ("Conclua o preflight antes de executar");
  - "**SHADOW**" / "Modo sombra";
  - "**k-mer**" ("k-mer do Velvet");
  - "**MULTI**" / "**consensus**" (P-11);
  - "**Opt-in explícito**";
  - sintaxe de query NCBI no placeholder (`"Orbivirus"[Organism] OR … AND refseq[filter]`), com `[Organism]`/`[filter]` sem explicação;
  - "**data/raw**" ("Importe um FASTQ que ainda não está em data/raw", "Amostras em data/raw com R1 e R2 válidos").
- **Evidência:** `CAP/A02-area-avancada.png`, `CAP/A03-configuracao-tecnica-preparar-banco.png`, `CAP/A05-wizard-ambiente.png`, `CAP/A07-wizard-banco-picorna-refseq.png`, `CAP/A08-wizard-amostra-vazia.png`, `CAP/A11-configuracao-hospedeiro-so-sus-scrofa.png`, `CAP/A13-revisao.png`.
- **Provável local no código:**
  - `SRC/dashboard/js/operational.js:176` ("preflight"), `:188` (placeholder NCBI), `:108` e `:211` ("data/raw"), `:229` e `:234` ("k-mer", "Opt-in explícito."), `:224` e `:246` (MULTI/consensus), `:312` e `:430` ("Evidence V2").
  - `SRC/dashboard/js/advanced.js:15` e `:20` (SHADOW / Modo sombra), `:43` e `:47` (Evidence V2), `:251` (placeholder NCBI).
- **Novos exemplos (SUINO_NEG, `CAP/F01_revisao_SUINO_NEG.png`):** a Revisão mostra "picornaviridae_refseq" e "consensus", e a etapa 6 fala em "perfil configurado" sem nomeá-lo.
- **Novos exemplos (2ª SUINO01, D03/D04):** a Revisão mostra os identificadores internos "picornaviridae_refseq" e "consensus" em vez dos rótulos escolhidos, e a etapa 6 fala em "perfil configurado" sem dizer qual. O log usa "Perfil: assembly-consensus".
- **Novos exemplos (SUINO01, Configuração técnica):** "O assistente operacional envia host_filter_mode." (`SRC/dashboard/js/advanced.js:177`); rótulos com chave crua, como "Read tracking (READ_TRKG)" e "Prefixo do índice Bowtie2 (HOST_INDEX_PREFIX)" (`advanced.js:145-157`, `:166`, que monta o rótulo `${label} (${key})`).
- **Sugestão de correção:** fazer um glossário curto e usar nomes simples: "Evidence V2" → "Relatório de evidências"; "preflight" → "verificação do ambiente"; "SHADOW" → "Experimental"; "k-mer" com uma explicação de uma linha e "deixe 31 se não souber"; "Opt-in explícito" → "Desligado por padrão; ligue só se tiver o índice do hospedeiro"; "data/raw" → "pasta de amostras do programa". Na query NCBI, oferecer campos simples (nome do vírus + "só RefSeq") que montem a query.

### U-12 — A lista de bancos mistura vírus suínos específicos com opções gerais (Baixa · interface · corrigido — f3fe2d6bfdce)

**Correção de engenharia na b2:** commit `f3fe2d6bfdce5377f39952c0d5b0d2543dec94aa`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Nova análise → 2. Banco viral → "Banco de referência" (A06/A07) e Configuração técnica → "Preparar banco viral" (A03).
- **Esperado:** opções gerais primeiro (por exemplo "Picornaviridae RefSeq [recomendado]"), separadas de alvos específicos e agrupadas por hospedeiro ou família.
- **Observado:** em uma lista só, na ordem: Porcine teschovirus, Enterovirus G (suínos), Sapelovirus A, Senecavirus A, FMDV (aftosa), Astrovirus Suíno, e só então Picornaviridae RefSeq [recomendado], complete e ALL [gigante]. A lista de alvos suínos é coerente com o desenho do programa (bancos direcionados por evidência prévia). O problema de interface é só a falta de agrupamento e de tamanho: as opções gerais ficam no meio, sem separação dos alvos específicos.
- **Evidência:** `CAP/A06-wizard-banco-vazio.png`, `CAP/A07-wizard-banco-picorna-refseq.png`, `CAP/A03-configuracao-tecnica-preparar-banco.png`; `GET /api/dbs`.
- **Provável local no código:** `SRC/scripts/ops/db_manager.sh:58-87` (`DB_QUERIES`/`DB_DESC`) e `:134-137` (`DB_ORDER`); `SRC/dashboard/js/operational.js:181` (`selectOptions` sem agrupamento).
- **Sugestão de correção:** qual banco aparece primeiro ou pré-selecionado é decisão do autor (metodologia de banco direcionado). Usar `<optgroup>` ("Gerais — família Picornaviridae" / "Alvos específicos — suínos" / "Outro vírus (query NCBI)"). Mostrar o tamanho aproximado de cada banco.

### U-13 — O guia `.md` não abre no navegador (`file://` bloqueado) e o painel não tem página de ajuda (Baixa · documentação · corrigido — 4b86d8eb2325)

**Correção de engenharia na b2:** commit `4b86d8eb232532601531481a174129712f1ae33b`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** ao tentar abrir `docs/beta-pesquisadores.md` (ou `LEIA_PRIMEIRO.md`) no navegador, ao lado do painel.
- **Esperado:** a pessoa consegue ler o guia formatado sem sair do painel.
- **Observado:** o navegador bloqueia `file://` a partir da sessão. Mesmo quando abre, o guia é Markdown puro (asteriscos, crases, links relativos). O painel não tem rota de ajuda: as rotas conhecidas são `home`, `new`, `track`, `results`, `history`, `advanced`, `analytics`, `compare`, `research`, `contigs` e `settings`.
- **Evidência:** observação da sessão de usabilidade (sem captura dedicada); `SRC/dashboard/js/router.js:2-5` (`KNOWN_ROUTES`, sem ajuda).
- **Provável local no código:** `SRC/dashboard/js/router.js:2-5`; `SRC/dashboard/index.html` (menu); `SRC/scripts/dashboard/handler.py` (não há rota que sirva `docs/`; a única servida como `text/markdown` é a de arquivos do histórico, em `handler.py:493`).
- **Sugestão de correção:** criar a rota `#/ajuda` com o guia do pesquisador renderizado (HTML gerado no build, ou um endpoint `/api/docs/<nome>` com lista branca e renderização simples) e um link "Ajuda" no menu. No guia, trocar instruções de "abrir o arquivo" por "no painel, clique em Ajuda".

### U-14 — Resgate de reads (caminho de 20–100 pb) morto por falta de memória: o Python carrega 57 milhões de linhas BLAST (6,35 GB) e precisaria de ~60 GB (Alta · pipeline · corrigido — 613260308dea)

**Correção de engenharia na b2:** commit `613260308dea76aebebb12dde68d38ba47a232d2`. Verificação: scripts/tests/test_u14_byte_parity.py; U14_PATCH.json; test_beta_scientific_contract.py. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Pelo escopo do autor (`ESCOPO_TESTES_GENEIN.md`, itens 1 e 5), o caminho de fragmentos curtos é a função central. Esta falha atinge exatamente esse caminho, por isso a gravidade é Alta.*

- **Onde aparece:** execução da AMOSTRA01 pela interface (job `59349d8fa52c4f24894789607ebff9f7`, 13:46:17–14:09:22 BRT), etapa [5/6] "BLAST dos contigs". O log mostra "Ativando resgate: 22268 reads de 20–100 pb…" e, cerca de 20 min depois, `sample_steps.sh: line 613: 120054 Killed python3 …/blast_router.py --query $RESCUE_FA … --recover-short-fragments …`. O `dmesg` registra um OOM global: `Killed process 121708 (python3) total-vm:12634500kB, anon-rss:11726924kB`. Máquina: 16 GB de RAM, sem swap, 8 vCPU, compartilhada com o desktop.
- **Dados:** sintéticos MiSeq 2×150, 150.000 pares, filtro de hospedeiro desligado (U-06), banco `picornaviridae_refseq` com 206 sequências (1.607.650 pb). **Comprimento dos reads no resgate:** 295.590 reads (42.010.066 pb), sendo 22.268 de 20–100 pb (nenhum de 20–29 pb, 130 de 30–34 pb) e 273.322 de 101–150 pb.
- **Esperado:** o resgate de reads curtos termina em uma máquina comum de pesquisador (8–16 GB) com uso de memória limitado. Se faltar memória, a falha é explicada (U-16).
- **Observado (causa raiz, verificada por reprodução em cópia, ver `REPRO/README_REPRO.md`):**
  1. **O FASTA do resgate contém todas as reads, não só as de 20–100 pb.** O log fala em 22.268 reads, mas `rescue_reads.fa` traz as 295.590 reads limpas (R1+R2). O resgate é acionado sempre que existe pelo menos uma read de 20–100 pb, o que acontece em quase toda amostra com adaptador cortado.
  2. **Os perfis do roteador geram relatórios enormes.** Os dois perfis usam `evalue 1000`, `max_target_seqs` = número de sequências do banco (206) e nenhum `-max_hsps`. Os 22.268 reads de 20–100 pb vão ao `blastn-short` (word_size 7) e todas as 295.590 reads vão ao `blastn` (word_size 11). Medido com blastn real: **short 28.711.550 linhas (3,16 GB); conventional 28.326.611 linhas (3,19 GB); total 57.038.161 linhas (6,35 GB).** No perfil short, cada read de 20–100 pb produz em média ~1.290 linhas, e só **0,028%** delas tem e-value ≤ 1e-5. O passo seguinte (`filter_rescue_reads.py`) descarta todo o resto (exige identidade ≥ 90%, e ≤ 1e-5 e alinhamento ≥ 80 pb ou ≥ 80% da query).
  3. **O código Python carrega tudo na memória (defeito de código).** O `blast_router.py` lê cada relatório inteiro com `read_text()`; essa leitura precisa, por um instante, dos bytes **e** da string, ou seja, ~6,3 GB só para o relatório short. Depois guarda os dois relatórios em uma lista, junta tudo em uma única string (`"".join`, mais 6,35 GB), quebra em 57 milhões de strings (`splitlines`) e monta um dicionário com uma tupla-chave e uma tupla de ordenação por linha. Medido: **~1,07 KB por linha BLAST**, ou seja, **~60 GB projetados** para esta amostra. O processo foi morto com 11,7 GB, na fase de junção/deduplicação (o blastn já tinha terminado e não aparece na tabela do OOM).
  4. **O próximo passo também estouraria.** O `filter_rescue_reads.py` guarda um dicionário por linha em `decisions` (~0,62 KB/linha, **~35 GB projetados**) e, no fim, calcula o sha256 do ledger com `read_bytes()` (o ledger tem 6,36 GB).
- **Picos de memória medidos (cópia, `ulimit -v`):**

  | Execução | Limite | Resultado | Pico RSS |
  |---|---|---|---|
  | blastn short (11.134 queries por parte) | 6 GB | OK, ~415 s | 2,71 GB (blastn) |
  | blastn conventional (98.530 queries por parte) | 6 GB | OK, ~285 s | 1,61 GB (blastn) |
  | roteador original, relatórios completos | 6 GB | MemoryError ao ler o relatório short | 3,2 GB |
  | roteador original, relatórios completos | 8 GB | short lido (pico 6,24 GB); MemoryError ao ler o conventional | 6,27 GB |
  | roteador original, fatia 1/100 → 1/20 (0,57 → 2,95 milhões de linhas) | 9 GB | OK | 0,64 → 3,18 GB |
  | roteador original, fim a fim, 10% das reads (29.559) | 6 GB | MemoryError | 5,64 GB |
  | **roteador corrigido, relatórios completos** | 6 GB | **OK** (169 s; 56.253.800 linhas após deduplicação) | **0,24 GB** |
  | filtro original, fatia 1/100 → 1/20 | 9 GB | OK | 0,36 → 1,83 GB |
  | **filtro corrigido, entrada completa** | 6 GB | **OK** (414 s) | **0,09 GB** |

- **Classificação:** **código** (causa principal: leitura e deduplicação de relatórios inteiros em memória; ledger em memória) agravado por **dimensionamento** (todas as reads no resgate; evalue 1000 sem limite de HSPs gera ~200 linhas por read). A **restrição do ambiente** (16 GB compartilhados, sem swap) só definiu o ponto exato da morte.
  - **Em um notebook típico de pesquisador (8–16 GB), o mesmo aconteceria.** A projeção é de ~60 GB para o roteador e ~35 GB para o filtro; nem 32 GB bastariam. Com o patch, o pico do passo fica em ~2,7 GB (blastn) + < 0,25 GB (Python), o que cabe em 8 GB.
  - **O filtro de hospedeiro não teria evitado a falha, só reduziria o volume.** Os nomes das reads não codificam a origem (formato MiSeq, comentário idêntico em todas), e o gabarito não foi consultado. Pelos critérios do próprio resgate, 44.458 reads (15,0%) passam. São candidatos computacionais, todas exceto 10 com melhor hit em NC_038307.1 num banco só viral, sem `--composite-db`. As outras 251.132 (85%) não passam; sua origem não foi avaliada. Mesmo no caso extremo de remover **todas** as que não passam, as que passam geram ~19% das linhas (~238 linhas por read, contra ~189 nas demais; fatia 1/20). Seriam ~10,8 milhões de linhas, ~11–12 GB no código original: ainda no limite de 16 GB.
- **Comprimento das sequências candidatas do resgate (reprodução com o patch, mesmos parâmetros; o job da interface não chegou a gerar candidatos):** 44.458 reads selecionadas. Por comprimento do read: 41.217 de 101–150 pb; 2.600 de 50–100 pb; 641 de 30–49 pb; **nenhuma abaixo de 35 pb**. Por faixas de 10 pb (≤ 100 pb): 30–39: 227; 40–49: 414; 50–59: 520; 60–69: 548; 70–79: 450; 80–89: 510; 90–99: 504; 100: 68. Comprimento do alinhamento: 30–153 pb (mediana 150). São candidatos computacionais para revisão humana; não indicam origem biológica.
- **Evidência:** `FAL/F01-amostra01-killed/`: `oom.txt`, `free.txt`, `job.json`, `logs/AMOSTRA01_pipeline.log`, `config/AMOSTRA01.resolved_config.json`, `config/evidence_profiles.json`, `rescue_fasta_stats.txt`, `partial_outputs.txt` (`SRC/results/blast/` vazio; nenhum `genein-blast-router-*` encontrado) e `repro/` (logs de memória, `README_REPRO.md`, hashes). Na reprodução: `REPRO/runs/` (relatórios do blastn em `precomputed/`, sha256 em `large_outputs_sha256.txt`).
- **Provável local no código:**
  - `SRC/scripts/evidence/blast_router.py:172` (`result_path.read_text(...)`), `:175` (`combined_chunks.append`), `:180` e `:100` (`"".join(chunks).splitlines()`), `:113-117` (dicionário com uma entrada por linha); `:38` (`"evalue": 1000`), `:143-148` (`max_target_seqs` = tamanho do banco), `:24-32` (`profiles_for_length`: 20–100 pb vão ao short e, a partir de 30 pb, também ao conventional).
  - `SRC/scripts/pipeline/sample_steps.sh:521-523` (aciona o resgate se houver ≥ 1 read de 20–100 pb), `:573-582` (o FASTA recebe **todas** as reads de R1/R2, sem filtro de comprimento), `:597-599` (chamada; o "line 613" do erro é o `fi` que fecha o bloco), `:601` (filtro).
  - `SRC/scripts/pipeline/filter_rescue_reads.py:39` e `:47-101` (`decisions` com um dicionário por linha), `:150` e `:165` (`read_bytes()` para o sha256), `:42` (arquivo bruto ausente → "0 leitura(s) candidatas… com sucesso": o `except FileNotFoundError` nunca é alcançado).
- **Observado de novo na 2ª SUINO01 (job `885535c1…`, 15:55–15:59, filtro de hospedeiro desligado):**
  - O log anuncia "Ativando resgate: **266 reads** de 20–100 pb" (`SRC/logs/ux_885535c1….log`, linha 167), mas `data/assemblies/SUINO01_assembly/rescue_reads.fa` tem **25.156** sequências — todas as reads limpas. A diferença é de 94,5×. É o ponto 1 acima, agora medido numa execução real pela interface.
  - Com a amostra reduzida, os relatórios ficaram menores e o resgate **terminou**: `results/blast/SUINO01_candidate_short.tsv` 1.918.240 linhas (185 MB), `SUINO01_candidate_conventional.tsv` 59.446 linhas (6,0 MB), combinado `SUINO01_read_level_vs_db_raw.tsv` 3.390.005 linhas (381 MB). O pico de RSS medido foi **3.549,9 MiB** no `blast_router.py` (15:59:15), **2.741,3 MiB** no `blastn-short`, **2.623,3 MiB** no `blastn` e **2.127,3 MiB** no `filter_rescue_reads.py` (15:59:37). Coube em 16 GB; o menor MemAvailable durante o resgate ficou acima de 8 GB. Nenhum OOM novo no `dmesg`.
  - O filtro do resgate selecionou **82** reads (`SUINO01_read_level_candidates.tsv`; log, linha 170), das quais 37 têm mais de 100 pb. Por comprimento: 20–29: 2; 30–39: 7; 40–59: 8; 60–99: 28; >100: 37.
  - Evidência: `EXE/SUINO01_885535c1/DADOS_BRUTOS.md` (itens 2 e 5), `sistema/mem_samples.tsv`.
- **Observado de novo na SUINO_NEG (job `469b1a6f…`, 17:21:43–17:24:35):** anunciados "**176 reads** de 20–100 pb"; `rescue_reads.fa` com **21.642** (todas as reads limpas); `read_level_vs_db_raw.tsv` com 2.807.730 linhas. Picos: `blast_router.py` 2.413,6 MiB, `blastn` 2.590,4 MiB, `filter_rescue_reads.py` 1.460,4 MiB; o `blastn-short` do resgate não foi medido (terminou antes do início da amostragem). 0 reads selecionadas. Evidência: `EXE/SUINO_NEG_469b1a6f/DADOS_BRUTOS.md` (itens 2 e 5); comparação em `EXE/TABELA_SUINO.md`.
- **Observado de novo na SUINO02 (job `ce2c576a…`, 17:00:45–17:04:43):** o log anuncia "**238 reads** de 20–100 pb", e o `rescue_reads.fa` tem **28.178** (todas as reads limpas). `SUINO02_read_level_vs_db_raw.tsv` 3.684.766 linhas (414 MB). Picos: `blast_router.py` **3.903,9 MiB** (17:04:18), `blastn` 2.586,6 MiB, `filter_rescue_reads.py` **1.912,6 MiB**; o `blastn-short` do resgate terminou antes do início da amostragem (NÃO MEDIDO). Menor MemAvailable no resgate: 3.069 MiB. Sem OOM. 714 reads selecionadas (654 com mais de 100 pb). Também: `assembly_metadata.env` registra `RESCUE_TRIGGERED=0` embora o resgate tenha rodado (na SUINO01, `1`). Evidência: `EXE/SUINO02_ce2c576a/DADOS_BRUTOS.md` (itens 2, 5 e 7).
- **Observado de novo na 3ª SUINO01 (job `f6507ec4…`, 17:38:49–17:42:24, mesma amostra da `885535c1`):** anunciados "**266 reads** de 20–100 pb" (log, linha 166); `rescue_reads.fa` com **25.156** (todas as reads limpas). `read_level_vs_db_raw.tsv`, o ledger e as 82 reads selecionadas saíram **idênticos byte a byte** aos da `885535c1`. Com a amostragem iniciada antes do job, todo o resgate foi medido: `blastn-short` **804,0 MiB** (17:38:50–17:39:00; primeira medição), `blastn` 2.617,6 MiB, `blast_router.py` **3.484,6 MiB**, `filter_rescue_reads.py` 1.900,2 MiB. Menor MemAvailable no resgate: 6.424 MiB. Sem OOM. Evidência: `EXE/SUINO01_f6507ec4/DADOS_BRUTOS.md` (itens 2 e 5).
- **Sugestão de correção:**
  - **Aplicável já (engenharia, mesma saída): `PAT/U-14-resgate-oom-streaming.patch`** (sha256 `4871d541c82f14621cab614eb3919597f6aeb9a6439de885fe2f29c5eb6e2473`). (a) `blast_router.py`: os relatórios do blastn não são mais lidos para a memória. A cópia para `--out-short/--out-conventional` é em streaming, e a nova `deduplicate_combined_files()` faz a fusão consulta a consulta, conferindo que o blastn emite as linhas na ordem das queries. Se a ordem não bater, volta ao método antigo com aviso. A saída é idêntica byte a byte à de `deduplicate_combined_hits()`, que foi mantida. (b) `filter_rescue_reads.py`: duas passagens pelo arquivo bruto (1ª: melhor hit por read; 2ª: grava o ledger linha a linha) e sha256 em blocos; regras, ordem e conteúdo inalterados. (c) Novo teste de equivalência em `tests/evidence/test_blast_specificity_integrity.py`. **Mesma saída:** na fatia 1/100, fim a fim com blastn real, `raw.tsv`, `raw_provenance.json`, `candidates.tsv` e `.decisions.tsv` têm o **mesmo sha256** antes e depois (também ordenados). Na fatia 1/20, os mesmos arquivos são idênticos (proveniência do filtro igual, exceto os caminhos). Testes do pacote na cópia corrigida: 38 passed. O patch foi aplicado só em `REPRO/patched-tree/` e conferido com `patch -p1` numa cópia limpa de `scripts/`.
  - **Decisões do autor (parâmetros científicos; NÃO aplicadas):**
    1. `evalue` 1000 na chamada do resgate. Teste só informativo na fatia 1/20: com `-evalue 1e-5`, o relatório bruto cai de 2.907.613 para 19.070 linhas e o blastn usa 152 MB em 4 s. O `candidates.tsv` sai **idêntico** (2.310 candidatos). Isso não se estende à faixa de 20–29 pb nem a bancos de outro tamanho: nesta amostra não havia reads < 30 pb, e o filtro do resgate já exige e ≤ 1e-5. Mudam o ledger (REJECTED_FILTER 2.904.709 → 16.166) e a linha "Alinhamentos BLAST brutos" do relatório mínimo (`report_minimal.sh:292-300`).
    2. Se o resgate deve mesmo receber todas as reads (o README diz "Reads maiores resgatados entram somente quando passam pela seleção do resgate") ou só as de 20–100 pb. Em qualquer caso, a mensagem "Ativando resgate: 22268 reads de 20–100 pb" deveria informar quantas reads entram de fato (295.590).
    3. Se o ledger precisa listar todas as linhas rejeitadas (6,36 GB em disco) ou se as contagens por regra bastam.
    4. Não reduzir `max_target_seqs` nem acrescentar `-max_hsps` sem decisão do autor: isso afeta a especificidade (painel competitivo).
  - **Outros pontos de engenharia (não incluídos no patch):** verificar espaço em disco antes do resgate (relatórios temporários ~6,35 GB + bruto 6,26 GB + ledger 6,36 GB ≈ 19 GB por amostra); gravar os temporários do blastn na pasta de trabalho, e não em `/tmp`; tratar `MemoryError`/código 137 com mensagem clara (U-16, U-17). Observação relacionada: a "Configuração efetiva" registra `SPADES_PARAMS: -m 64` (limite de 64 GB para o SPAdes) numa máquina de 16 GB.

### U-15 — Com o filtro de hospedeiro desligado, contigs muito maiores que os genomas do banco (aqui 44–300 kb, de DNA humano) aparecem sem aviso (Média · pipeline / interface · corrigido — 097f86343ad6)

**Reteste b3:** Aviso individual quando uma sequência candidata excede a maior referência alinhada registrada. É orientação de revisão, sem inferir hospedeiro/origem, alterar filtros ou arquivos de candidatos. Teste confere exportações idênticas. Commit `097f86343ad6bbef7fa67318429cd83816ad6426`.

**Correção de engenharia na b2:** commit `96aa122df72b98c5b5b6ecd269e3fc09636143dc`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Relaciona-se a U-06. Enquadramento: o hospedeiro humano está fora do desenho. O achado que vale para qualquer hospedeiro é a ausência de contexto ou aviso para contigs muito maiores que o alvo quando o filtro está desligado.*

- **Onde aparece:** log da execução (A15 e `SRC/logs/AMOSTRA01_pipeline.log`, linhas 159–163): "Montador velvet concluido. Maior contig: 44469 bp", "spades … 300739 bp", "metaspades … 153260 bp". O `assembly_metadata.env` grava `ASSEMBLY_MAX_CONTIG_LEN=300739`.
- **Esperado:** com o filtro de hospedeiro desligado (qualquer hospedeiro; aqui, células humanas), a interface avisa que contigs muito maiores que os genomas do banco (picornavírus: ~7,5 kb) provavelmente vêm do hospedeiro ou de contaminantes, e indica como usar um índice de hospedeiro (U-06).
- **Observado:**
  - Velvet: 662 contigs (680.981 pb), 21 ≥ 10 kb. SPAdes: 148 (911.872 pb), maior 300.739 pb. metaSPAdes: 160 (912.263 pb), maior 153.260 pb. União MULTI: 868 contigs, 2.283.030 pb, 38 ≥ 10 kb.
  - Os maiores contigs têm muitas cópias do motivo Alu `TGTAATCCCAGC` (SINE exclusivo de primatas): SPAdes NODE_1 (300.739 pb) 215; NODE_2 (199.827 pb) 203; metaSPAdes NODE_1–8 (153–28 kb) 13–114 cada; os 8 maiores do Velvet (44–20 kb) 5–17 cada. Isso indica DNA genômico **humano**.
  - Outros dois contigs têm composição compatível com rDNA e DNA mitocondrial humanos: SPAdes NODE_5, 13.641 pb, GC 72,5%; NODE_6, 13.462 pb, GC 44,4%, sem Alu. É hipótese pela composição, não verificada por alinhamento. O gabarito não foi consultado.
  - O "Maior contig" é o único número de montagem mostrado e só gera aviso quando fica abaixo de 200 pb. Quem trabalha em bancada pode ler "300 kb" como uma montagem excelente.
  - Esses contigs e todas as reads humanas seguem para o BLAST e para o resgate, o que aumenta o custo (U-14).
- **Evidência:** `FAL/F01-amostra01-killed/contig_stats.txt`, `FAL/F01-amostra01-killed/logs/AMOSTRA01_pipeline.log`, `FAL/F01-amostra01-killed/assembly/assembly_metadata.env`; `SRC/data/assemblies/AMOSTRA01_{velvet_k31,spades,metaspades,assembly}/`.
- **Provável local no código:** `SRC/scripts/pipeline/assembly_router.sh:180-185` (só avisa abaixo de 200 pb; não há limite superior nem contexto) e `:339`; `SRC/scripts/pipeline/report_minimal.sh:190` ("Maior contig (bp)"); hospedeiro: ver U-06 (`SRC/dashboard/js/operational.js:231`, `SRC/scripts/dashboard/jobs.py:714-733`).
- **Sugestão de correção:** quando o filtro de hospedeiro estiver desligado, mostrar no log e na interface: "Filtro de hospedeiro desligado: contigs maiores que N kb (N configurável conforme o banco, por exemplo 2× o maior genoma do banco) provavelmente vêm do hospedeiro ou de contaminantes". Resumir a montagem com N50, número de contigs e "contigs compatíveis com o tamanho do alvo". Resolver U-06 (opção humano/índice próprio).

### U-16 — Após a falha, "Acompanhar" mostra só "Status técnico: Falha" e o log bruto: sem etapa, causa ou próximo passo (Média · interface · corrigido — 13f70fd233cd)

**Correção de engenharia na b2:** commit `13f70fd233cdfc56e57dbb02686ea5c1d3e28d16`. Verificação: test_evidence_job_completion.py; PAINEL_HEADLESS.json. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Acompanhar, depois que a AMOSTRA01 falhou (B01, B02).
- **Esperado:** um resumo em linguagem simples, por exemplo: "A análise parou na etapa 5/6 (BLAST das reads). O processo foi encerrado pelo sistema por falta de memória (código 137). O que fazer: feche outros programas, reduza…, ou fale com o autor e envie o log." Quando o código for 137/SIGKILL, ou o `dmesg`/log tiver "Killed"/"Out of memory", a interface deveria dizer isso.
- **Observado:** só "Status técnico: Falha · Tempo decorrido: 23min 5s. Este painel descreve o job, não a evidência científica." e o log técnico sem quebras de linha (U-03). A causa só aparece no fim do log, como uma linha de shell (`… line 613: 120054 Killed python3 …`). Não há etapa que falhou, mensagem de erro traduzida nem orientação. O estado salvo tem `failed_stage: "initial_blast"` e `failure_message`, mas a API do job não devolve esses campos.
- **Evidência:** `CAP/B01-track-falha-topo.png`, `CAP/B02-track-log-fim.png`; `GET /api/job/59349d8fa52c4f24894789607ebff9f7` (somente leitura, ~14:22), sem `failed_stage`/`failure_message`; `SRC/results/evidence/state/59349d8fa52c4f24894789607ebff9f7.json`.
- **Provável local no código:** `SRC/dashboard/js/operational.js:308` (painel com status + tempo apenas), `:328` (log bruto), `:333` (ações só para `done`/`partial`); `SRC/scripts/dashboard/handler.py:503-515` (a resposta de `/api/job` não inclui `failure_type`, `failure_message` nem `failed_stage`); `SRC/scripts/dashboard/jobs.py:1107-1119` (mensagem genérica "Processo encerrou com codigo de erro {rc}").
- **Sugestão de correção:** devolver `failed_stage`, `failure_type`, `failure_message` e `exit_code` em `/api/job`. Mapear `rc == 137` ou `rc == -9`, ou o padrão `Killed`/`MemoryError` no fim do log, para `RESOURCE_EXHAUSTED`, com o texto "O sistema encerrou o processo por falta de memória na etapa X". No Acompanhar, mostrar um painel "O que aconteceu / O que fazer" acima do log, com as últimas linhas relevantes destacadas e os botões "Baixar log", "Ver saídas parciais" (U-18) e "Reexecutar" (U-19).

### U-17 — Registro técnico da falha errado: `returncode` nulo na API, `failure_type` INPUT_INVALID para um SIGKILL/OOM e `exit_code` 1 no histórico (Média · pipeline / interface · corrigido — 1aca7a573d01)

**Correção de engenharia na b2:** commit `1aca7a573d0127646f74d0f603e1474cbf97a888`. Verificação: scripts/tests/test_u17_byte_parity.py; REGRESSAO_ESTADOS.log; DASHBOARD_PIPELINE_REAL.json. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** `GET /api/job/<id>`, `GET /api/history` e o estado salvo da execução.
- **Esperado:** código de saída real (137 ou −9) e categoria coerente (falta de recurso), iguais em todos os lugares.
- **Observado:** `/api/job` devolve `"returncode": null` (e `log_path: null`). O estado e o histórico trazem `failure_type: "INPUT_INVALID"` com `failure_message: "Processo encerrou com codigo de erro 137"`, e o histórico mostra `exit_code: 1`. A entrada era válida: QC e montagem terminaram. Quem filtrar por categoria vai concluir que "a entrada estava errada". O estado também registra `pipeline_version: "2.0.0-alpha.2"` num pacote 2.0.0b1.
- **Evidência:** respostas somente leitura de `/api/job/59349d8fa52c4f24894789607ebff9f7` e `/api/history` (~14:22); `FAL/F01-amostra01-killed/results/59349d8fa52c4f24894789607ebff9f7.json`.
- **Provável local no código:** `SRC/scripts/dashboard/jobs.py:1037` grava `exit_code`, mas `SRC/scripts/dashboard/handler.py:506` lê `job.get("returncode")` (chave que nunca é preenchida). `SRC/scripts/dashboard/jobs.py:280-288` (`classify_evidence_failure`): classifica por palavras-chave em **todo** o log, e "fastq"/"fasta"/"entrada" aparecem em qualquer execução ("FASTQs pareados com sucesso", "FASTA de referência"), então quase toda falha vira INPUT_INVALID. `SRC/scripts/dashboard/jobs.py:1192`: `exit_code` sintetizado como 0/1.
- **Observado de novo na SUINO01 (job `1088e943…`):** a execução parou no filtro de hospedeiro ([3/6]), mas o estado e o histórico registram `failed_stage: "assembly"` (com `started_at` = `finished_at` = 15:35:00,06: a montagem nunca começou), `failure_type: "INPUT_INVALID"`, `failure_message: "Processo encerrou com codigo de erro 1"` e, na API, `returncode: null`, `log_path: null`, `stage_status: null`. Causa provável da etapa errada: a lista de etapas do estado não tem etapa de filtro de hospedeiro (`SRC/scripts/pipeline/sample_steps.sh`: `quality_control` termina em `:268` e `assembly` só começa em `:368`), e `terminalize` marca como falha a primeira etapa `pending` quando nenhuma está `running` (`SRC/scripts/dashboard/jobs.py:108-110`). Evidência: `EXE/SUINO01_1088e943/results/evidence_state_1088e943d91d42cf819e9b3e14cca12b.json`, `EXE/SUINO01_1088e943/api/history.json`.
- **Observado de novo na SUINO_NEG (job `469b1a6f…`):** `returncode: null`; histórico `validation_pending` / `exit_code: 1` às 17:33:23 e `done_with_warning` / `exit_code: 0` às 17:35:02 (`EXE/SUINO_NEG_469b1a6f/api/`).
- **Observado de novo na SUINO02 (job `ce2c576a…`, sucesso):** de novo `/api/job` com `returncode: null` e `/api/history` com `validation_pending` / `exit_code: 1` logo após o fim (17:16:48); na leitura seguinte (~17:18), `done_with_warning` / `exit_code: 0` / `EVIDENCE_VALID`. Evidência: `EXE/SUINO02_ce2c576a/api/`.
- **Observado de novo na 2ª SUINO01 (job `885535c1…`, sucesso):** logo após o fim (16:50:25), `/api/job` dava `status: done` com `returncode: null`, enquanto `/api/history` mostrou por cerca de 1 min `validation_pending` com `exit_code: 1`; depois passou a `done_with_warning`, `exit_code: 0`, `EVIDENCE_VALID`. O `exit_code` do histórico vem da validação, não do processo (`SRC/scripts/dashboard/jobs.py:1192`). Evidência: `EXE/SUINO01_885535c1/api/`.
- **Observado de novo na 3ª SUINO01 (job `f6507ec4…`):** `/api/job` com `returncode: null`. O histórico mostrou `validation_pending` / `exit_code: 1` às 17:53:51 e ainda às 17:54:59 (fim do estado: 17:53:06). Às 17:56:13 mostrou `done_with_warning` / `exit_code: 0` / `EVIDENCE_VALID`. A janela foi maior que nas anteriores (≥ 1 min 53 s). Evidência: `EXE/SUINO01_f6507ec4/api/history*.json`.
- **Sugestão de correção:** `handler.py:506` → `job.get("exit_code")`. Classificar primeiro pelo código (137/−9 → `RESOURCE_EXHAUSTED`/`KILLED`; 130 → cancelado) e só depois pelas **últimas** linhas do log, com padrões específicos (por exemplo `[ERRO] FASTQ invalido`), não por palavras soltas. Guardar o `exit_code` real no estado e repassá-lo ao histórico. Acrescentar a etapa `host_filter` ao estado (`evidence_state_stage host_filter running/done`) para que a falha seja atribuída à etapa certa.

### U-18 — Saídas parciais (reads limpas, relatório de QC, contigs) existem, mas não aparecem nem podem ser baixadas após a falha (Média · interface · corrigido — 1efb68d3f87b)

**Correção de engenharia na b2:** commit `1efb68d3f87b5f90c84ffdd6171cc3ccd9d6aeae`. Verificação: scripts/tests/test_u18_byte_parity.py; DASHBOARD_PIPELINE_REAL.json (falha e saídas parciais). A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Acompanhar, Resultados e Histórico da execução que falhou (B01–B04).
- **Esperado:** quando o pipeline para na etapa 5, as etapas concluídas continuam úteis: relatório do fastp, reads limpas, contigs dos três montadores. A interface deveria listá-las como "saídas parciais (análise incompleta)", com aviso claro de que não são resultado final.
- **Observado:** nenhuma tela oferece esses arquivos, embora existam em disco: `SRC/results/qc/AMOSTRA01_fastp.{html,json}`, `SRC/data/cleaned/AMOSTRA01_R{1,2}.clean.fastq.gz`, `SRC/data/assemblies/AMOSTRA01_*/contigs.fa*`, `SRC/results/short_fragments/AMOSTRA01_read_lengths.json`. Para a persona, a execução de 23 min "não deixou nada".
- **Evidência:** `CAP/B01-track-falha-topo.png`, `CAP/B03-resultados-falha.png`, `CAP/B04-historico-falha.png`; listagem de `SRC/data`, `SRC/results`.
- **Provável local no código:** `SRC/scripts/dashboard/jobs.py:1072-1090` (o snapshot `snapshot_run_artifacts` e o `run` com `paths` só são criados quando `rc == 0`); `SRC/dashboard/js/operational.js:344-351` (`artifactActions` depende de `run.runDir`/`paths`), `:414` (só se `run.valid !== false`).
- **Sugestão de correção:** criar o snapshot também em falha, marcado `partial: true`, com as saídas das etapas concluídas segundo `results/evidence/state/<run_id>.json`. Mostrar "Saídas parciais (não são resultado final)" em Resultados e no Histórico. Manter a regra de não apresentar artefatos inválidos como resultado concluído.

### U-19 — Não há "Reexecutar" para a execução que falhou (Acompanhar, Resultados, Histórico) (Baixa · interface · corrigido — b1fd5d3b9a35)

**Correção de engenharia na b2:** commit `b1fd5d3b9a35dc8e0243944d8d7c19e7c461885c`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Acompanhar (B01), Resultados (B03), Histórico (B04).
- **Esperado:** um botão "Reexecutar com os mesmos parâmetros" (ou "Abrir no assistente com estes parâmetros") depois de uma falha, sobretudo uma falha de recurso.
- **Observado:** nenhuma das três telas tem esse botão. A persona precisaria refazer o assistente inteiro e lembrar de digitar de novo os adaptadores (U-07, U-08).
- **Evidência:** `CAP/B01-track-falha-topo.png`, `CAP/B03-resultados-falha.png`, `CAP/B04-historico-falha.png`.
- **Provável local no código:** `SRC/dashboard/js/operational.js:415` e `:435` ("Reexecutar" só quando `run.runDir && run.action && !run.evidence`; execuções Evidence V2 nunca recebem o botão e execuções que falharam não têm `runDir`, ver U-18); `:329-333` (Acompanhar sem ação para `failed`); `SRC/scripts/dashboard/handler.py` (`/api/history/rerun` exige `run_dir`).
- **Sugestão de correção:** guardar os `params` do job (inclusive os adaptadores) no estado da execução e oferecer "Reexecutar" e "Editar e reexecutar" (pré-preenche o assistente) para `failed`/`cancelled`, também em execuções Evidence V2.

### U-20 — Resultados de uma execução que falhou não dizem "Falha": mostram "Evidence V2 não avaliável — execução Evidence V2 não encontrada" e "Finalizada" (Média · interface · corrigido — 4d64dfd6c1c3)

**Correção de engenharia na b2:** commit `4d64dfd6c1c3deea7cafd43369dfa0a36ec3cf67`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Resultados, com a execução `AMOSTRA01 · 59349d8f…` selecionada (B03).
- **Esperado:** no topo, "Esta análise falhou na etapa 5/6 e não gerou resultado" (com o motivo, U-16). Nunca uma frase que pareça "terminou e não encontrou nada".
- **Observado:** um painel "?" com "**Evidence V2 não avaliável** — execução Evidence V2 não encontrada" e, abaixo, "EXECUÇÃO … AMOSTRA … **FINALIZADA** 08/10/2026, 14:09:22". A palavra "Falha" não aparece na página (só na barra superior, "Execução: Falha"). "Não avaliável" + "Finalizada" pode ser lido como "a análise terminou e não deu resultado", ou seja, confundido com negativo. Pelo escopo (item 6), falha técnica não é negativo e a tela precisa deixar isso explícito.
- **Evidência:** `CAP/B03-resultados-falha.png`.
- **Provável local no código:** `SRC/dashboard/js/operational.js:371-373` (o status do job só é mostrado quando `jobStatus !== status`; aqui ambos são `failed`, então nada aparece), `:404` (no `catch`, mostra "Evidence V2 não avaliável" + mensagem da exceção), `:410` (rótulo "Finalizada"); a mensagem vem de `SRC/scripts/lib/evidence_analytics.py:37` ("execução Evidence V2 não encontrada"), quando a execução não tem `SUCCESS.json`.
- **Sugestão de correção:** em `renderResults`, se `run.status === "failed"`, mostrar primeiro `statusPanel("failed", "Análise interrompida — sem resultado", "<etapa> · <motivo>. Falha técnica não é resultado negativo.")` e não chamar `/api/evidence/analytics`. Trocar "Finalizada" por "Encerrada em" (ou "Falhou em") conforme o estado.

### U-21 — O tempo decorrido continua contando depois do fim do job (23min 5s → 33min 11s) (Baixa · interface · corrigido — f804712609ae)

**Correção de engenharia na b2:** commit `f804712609ae5e7d72bbaf9b2670bb6cfd133349`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Acompanhar, execução que falhou (B01 → B05).
- **Esperado:** depois do fim, mostrar a duração fixa (13:46:17 → 14:09:22 = 23 min 5 s) e o horário de término.
- **Observado:** B01 mostra "Tempo decorrido: 23min 5s". Ao voltar à página ~10 min depois (B05), mostra "33min 11s". O valor é recalculado como "agora − início" a cada renderização, mesmo com o job encerrado.
- **Evidência:** `CAP/B01-track-falha-topo.png`, `CAP/B05-track-sem-param-tempo-33min.png`.
- **Provável local no código:** `SRC/dashboard/js/operational.js:308` (`elapsed(active.startedAt)` sem fim → `Date.now()`); `SRC/dashboard/js/adapters.js:49-58`; `SRC/scripts/dashboard/handler.py:503-515` (`/api/job` não devolve `started_at`/`finished_at`, embora o job tenha `finished_at`, `jobs.py:1036`).
- **Observado na SUINO01 (submissão, ~15:34):** com ~6 s de execução, o Acompanhar mostrava "Tempo decorrido: 0min 0s" (relato da sessão; sem captura). Causa provável: o início é o horário do navegador no clique (`SRC/dashboard/js/state.js`, `activateJob`: `startedAt: new Date().toISOString()`), e a tela só se redesenha sozinha quando o status é `running` (`SRC/dashboard/js/operational.js:329-332`); se a primeira resposta vem como `queued`, a tela fica congelada em 0 s até a pessoa navegar.
- **Sugestão de correção:** devolver `started_at`/`finished_at` na API e usar `elapsed(job.started_at, job.finished_at || Date.now())`. Em estado terminal, escrever "Duração: 23 min 5 s (encerrada às 14:09:22)". Redesenhar também em `queued`.

### U-22 — Rótulos pouco claros no Histórico: "Inspecionar inválida" e "Camada: Não avaliável" ao lado de "Falha" (Baixa · interface · corrigido — 15879c377042)

**Correção de engenharia na b2:** commit `15879c377042064219a3e75068e23ef7f5bdaed1`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Complementa U-11 (jargão).*

- **Onde aparece:** Histórico, linha da execução que falhou (B04).
- **Esperado:** rótulos que digam o que aconteceu e o que o botão faz, por exemplo "Falhou (etapa 5/6)" e "Ver detalhes da falha".
- **Observado:** "Estado técnico: × Falha", "Camada: · Não avaliável" e o botão "**Inspecionar inválida**". "Camada" não se explica (Pipeline? Evidence V2?). "Não avaliável" ao lado de "Falha" parece um segundo resultado. "Inspecionar inválida" soa como se a pessoa tivesse feito algo inválido, e o botão leva ao explorador avançado (`#/analytics`), não ao log nem às saídas parciais.
- **Evidência:** `CAP/B04-historico-falha.png`.
- **Provável local no código:** `SRC/dashboard/js/operational.js:430` (coluna "Camada" com o badge "Evidence V2"/"Não avaliável") e `:433` (botão "Abrir Evidence V2"/"Inspecionar inválida").
- **Observado de novo (`CAP/G01_historico.png`, ~17:37):** as três execuções que terminaram (`885535c1`, `ce2c576a`, `469b1a6f`) aparecem como "Estado técnico: **Sucesso parcial**". É a tradução de `done_with_warning` (`SRC/dashboard/js/adapters.js:16`). As etapas "concluídas com aviso" foram remapeamento, cobertura e controles, que não se aplicam a uma execução individual sem painel. Para a persona, "Sucesso parcial" sugere que parte da análise falhou ou que o resultado está incompleto. Na `885535c1`, que de fato perdeu dois montadores (U-26), aparece o mesmo rótulo das outras. Ver também U-31.
- **Sugestão de correção:** renomear a coluna para "Tipo de análise" (valores "Relatório de evidências"/"Pipeline"). Quando o estado for `failed`, esconder o badge "Não avaliável" e trocar o botão por "Ver detalhes da falha" (abre Acompanhar/Resultados com o resumo do U-16).

### U-23 — Configuração técnica: "Validar índice" não salva; a tabela "efetiva" não muda depois de salvar; "Read tracking" aparece vazio (Baixa · interface · corrigido — 68896ece77a8)

**Correção de engenharia na b2:** commit `68896ece77a84696f61b0e56062a56cfb07b55fd`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Relaciona-se a U-06 e U-24.*

- **Onde aparece:** Área avançada → Configuração técnica (submissão da SUINO01, 08/10 ~15:34; relato da sessão, sem captura).
- **Esperado:** (b) deixar claro que validar não é salvar, ou salvar o índice validado; (c) depois de "Configuração salva", a tabela "Configuração operacional efetiva" mostra os novos valores; (f) cada campo mostra o valor salvo.
- **Observado:**
  - (b) "Validar índice" só chama `/api/host-index/validate` e mostra "Índice válido"; nada é gravado. A pessoa precisa achar e clicar "Salvar configuração", no fim do formulário.
  - (c) Depois do toast "Configuração salva", a tabela continua com `HOST_INDEX_PREFIX` vazio e `HOST_FILTER_ENABLED=false` até recarregar a página. Parece que a gravação não valeu. O arquivo já tinha os valores novos (`SRC/config/picornavirus.env`, 15:34:14).
  - (f) "Read tracking (READ_TRKG)" aparece vazio ("Não definido"), embora o valor salvo seja `READ_TRKG=yes` (`GET /api/config/env`). O seletor só tem as opções `""`, `false` e `true`.
- **Evidência:** `EXE/SUINO01_1088e943/api/config_env.json` (`READ_TRKG: "yes"`, `HOST_INDEX_PREFIX` preenchido); `EXE/SUINO01_1088e943/config/picornavirus.env` e `.bak-20261008_153414_065248-8cf7ec41`; `SRC/logs/ux_dashboard.log` (15:34:14).
- **Provável local no código:**
  - (b) `SRC/dashboard/js/advanced.js:180-193` (`validateHost` + botão "Validar índice", sem gravação); gravação só no `submit`, `:199-208`.
  - (c) `SRC/dashboard/js/advanced.js:206` (só atualiza `saveStatus`) × `:236-239` (tabela montada uma vez com os valores do carregamento, sem novo `GET /api/config/env`).
  - (f) `SRC/dashboard/js/advanced.js:154` (opções `["", "false", "true"]`) e `:165` (`control.value = values[key]`; `yes` não existe na lista) × `SRC/config/picornavirus.env.example:34` (`READ_TRKG=yes`) e `SRC/scripts/dashboard/config.py:310` (backend aceita `yes/no/sim/nao/0/1`).
- **Sugestão de correção:** depois de salvar, recarregar `/api/config/env` e redesenhar a tabela (ou atualizar a página). Trocar "Validar índice" por "Validar e salvar", ou mostrar "Índice válido — ainda não salvo". Normalizar booleanos (`yes`→`true`) ao exibir, ou incluir os valores aceitos pelo backend nas opções.

### U-24 — A configuração técnica é global (arquivo dentro do pacote), não por execução: vale em silêncio para as análises seguintes; a tela mostra ASSEMBLER=spades e DB=custom, diferentes do que o assistente usa (Média · interface / pipeline · corrigido — 9ba14cee7c61)

**Correção de engenharia na b2:** commit `9ba14cee7c61e12344a782a3bda312f1abfaebc7`. Verificação: test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Relaciona-se a U-06 (chaves de hospedeiro ignoradas), U-23 e P-07 (c).*

- **Onde aparece:** Área avançada → Configuração técnica × Nova análise (SUINO01, 08/10 ~15:34).
- **Esperado:** a pessoa sabe se uma mudança vale só para a próxima análise ou para todas, e a tela mostra o que cada análise de fato usará.
- **Observado:**
  - "Salvar configuração" reescreve `SRC/config/picornavirus.env` (dentro da pasta do programa), com backup `picornavirus.env.bak-<data>-<id>` na mesma pasta. O formulário reenvia todas as chaves preenchidas (o log lista `ASSEMBLER`, `THREADS`, `DB`, `BLAST_EVALUE`, `BLAST_MAX_TARGET_SEQS`, `HOST_*`, `VELVET_K`, `MIN_CONTIG_LEN`, `SPADES_MEMORY`, `SPADES_PARAMS`, `BIND_HOST`, `PORT`). Nada na tela diz que a mudança vale para **todas** as análises seguintes, inclusive as feitas pela linha de comando, que leem o mesmo arquivo.
  - O efeito é desigual e invisível: chaves como `THREADS`, `BLAST_EVALUE`, `MIN_CONTIG_LEN` e `SPADES_PARAMS` passam a valer para os próximos jobs do painel; `HOST_FILTER_ENABLED`/`HOST_INDEX_PREFIX`, `DB` e `ASSEMBLER` são sobrescritos pelos parâmetros do assistente (`SRC/scripts/dashboard/jobs.py:706-735`; prioridade em `SRC/scripts/pipeline/prepare_run.sh:46-80`). Na SUINO01, o filtro salvo como "ligado" ficou ligado no arquivo, mas o job usou outro índice (U-06).
  - A tela mostra `ASSEMBLER=spades` e `DB=custom` (valores do exemplo), enquanto o assistente usou MULTI/`consensus` e `picornaviridae_refseq` (`EXE/SUINO01_1088e943/api/config_env.json` × `config/SUINO01.resolved_config.json`). O valor `BLAST_DB="blastdb/custom"` ainda aparece no diagnóstico da execução como "Caminho BLAST_DB ativo: blastdb/custom… ainda não preparado" (log, linhas 74–75; ver P-07).
- **Evidência:** `EXE/SUINO01_1088e943/config/picornavirus.env`, `.bak-20261008_153414_065248-8cf7ec41`, `config/SUINO01.resolved_config.json`, `api/config_env.json`, `logs/ux_dashboard.log` (15:34:14) e `logs/SUINO01_pipeline.log`.
- **Provável local no código:** `SRC/scripts/dashboard/config.py:315-324` (`save_config_env`: grava em `config/picornavirus.env` e cria o backup no pacote); `SRC/dashboard/js/advanced.js:172` (texto "Somente chaves validadas pelo backend são enviadas…", sem dizer que é global) e `:199-208`; `SRC/scripts/dashboard/jobs.py:706-735` (o que o job sobrescreve).
- **Observado de novo na 2ª SUINO01:** a "Configuração efetiva" do log mostra `SPADES_PARAMS: -m ${SPADES_MEMORY}` **sem expandir** a variável (log, linha 13), e foi exatamente esse valor que derrubou o SPAdes (U-26). O mesmo bloco traz a linha solta "12800" logo depois de "Configuração efetiva ==" (a contagem de pares impressa por `input_validation.py`, já descrita em U-03).
- **Sugestão de correção:** dizer na tela "Configuração padrão de todas as próximas análises (painel e linha de comando)". Marcar quais chaves o assistente sobrescreve ("definido em cada análise") e escondê-las ou desabilitá-las aqui. Registrar no estado de cada execução uma cópia da configuração efetiva usada. Guardar a configuração do usuário fora da pasta do programa (ou em `config/local/`), para não misturá-la com os arquivos da entrega.

### U-25 — O índice do hospedeiro só é verificado depois do QC; a falha não diz como resolver e sai com o rótulo `[QC_PREFLIGHT]` (Média · pipeline / interface · corrigido — e853e3177248)

**Correção de engenharia na b2:** commit `e853e31772485394eb021bfa3f7585019256da56`. Verificação: scripts/tests/test_u25_byte_parity.py; test_host_filter.py. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Relaciona-se a U-06 (causa da falha), U-16 (falha sem explicação) e U-17 (registro da falha).*

- **Onde aparece:** execução SUINO01 (job `1088e943…`), etapa [3/6].
- **Esperado:** um índice de hospedeiro inexistente é recusado **antes** de o job começar (na submissão ou na Revisão), com uma mensagem acionável: "O índice do hospedeiro 'Sus scrofa' não está instalado em …; escolha 'Sem filtro', instale o índice ou informe um índice próprio".
- **Observado:** o backend aceitou o job sem verificar o caminho fixo (`SRC/scripts/dashboard/jobs.py:717-720`; o modo `custom` também não é validado ali). O pipeline rodou verificação de ambiente e fastp (~22 s; numa amostra real, o QC inteiro) e só então parou com `[FATAL] [QC_PREFLIGHT] [SUINO01] — Índice completo do hospedeiro 'Sus scrofa' não encontrado ou inválido em …/ref/host/sus_scrofa_bt2.` A mensagem não diz o que fazer, não menciona que o prefixo salvo foi substituído (U-06) e leva o rótulo `QC_PREFLIGHT`, embora a etapa seja o filtro de hospedeiro: `PIPELINE_ETAPA` é definido uma vez e nunca muda. O diagnóstico inicial terminou com "✅ DIAGNÓSTICO CONCLUÍDO COM SUCESSO! … pronta para uso!" sem checar o índice.
- **Evidência:** `EXE/SUINO01_1088e943/logs/SUINO01_pipeline.log` (linhas 78–80 e 149–150); `EXE/SUINO01_1088e943/logs/ux_dashboard.log` (15:34:35).
- **Provável local no código:** `SRC/scripts/dashboard/jobs.py:714-735` (sem validação do índice; comparar com `host_reference` em `SRC/scripts/dashboard/config.py:381-386`, que usa `validate_host_index`); `SRC/scripts/pipeline/sample_steps.sh:79` (`PIPELINE_ETAPA="QC_PREFLIGHT"` fixo) e `:279-283` (verificação só na etapa 3); `SRC/scripts/lib/common.sh:13` (formato do `log_fatal`).
- **Sugestão de correção:** em `build_command`, validar `HOST_INDEX_PREFIX` com `validate_host_index` sempre que o filtro estiver ligado e recusar o job com a mensagem acima (a interface já mostra erros de `/api/run` em toast). Repetir a verificação no início do pipeline, antes do QC. Atualizar `PIPELINE_ETAPA` a cada etapa (`HOST_FILTER`, `ASSEMBLY`…). Dar à mensagem do FATAL a ação recomendada.

### U-26 — "Salvar configuração" grava `SPADES_PARAMS` com aspas simples e o SPAdes/metaSPAdes falham; o pipeline segue só com velvet e termina como concluído (Alta · pipeline / interface · corrigido — 76b6cdf9586c)

**Correção de engenharia na b2:** commit `76b6cdf9586ca62d40968d2391556bdaf91b0e20`. Verificação: scripts/tests/test_u26_byte_parity.py; U26-router.log. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Relaciona-se a U-24 (a tela de configuração regrava o arquivo inteiro) e a U-15 (o que a montagem mostra).*

- **Onde aparece:** execução `885535c1…` (SUINO01, 08/10 15:55), etapa [4/6], e em qualquer execução feita depois de "Salvar configuração" na Configuração técnica.
- **Esperado:** SPAdes e metaSPAdes recebem um limite de memória numérico (o padrão do exemplo é `-m 64`) e os três montadores do perfil MULTI rodam. Se um montador não rodar, a pessoa vê isso com clareza e o resultado não aparece como uma montagem MULTI completa.
- **Observado:**
  1. O exemplo traz `SPADES_PARAMS="-m ${SPADES_MEMORY}"` com aspas duplas, então o bash expande `${SPADES_MEMORY}` ao ler o arquivo. Na 1ª execução (AMOSTRA01, antes de qualquer gravação pela tela) o log mostra `SPADES_PARAMS: -m 64`.
  2. "Salvar configuração" reescreve a linha com `shlex.quote`, que usa aspas simples: `SPADES_PARAMS='-m ${SPADES_MEMORY}'` (`SRC/config/picornavirus.env`, linha 29; o backup `.bak-20261008_153414…` ainda tem aspas duplas). Com aspas simples, `${SPADES_MEMORY}` não é expandido.
  3. Na 2ª SUINO01, SPAdes e metaSPAdes saíram com exit 2 em menos de 1 s: `spades.py: error: argument -m/--memory: invalid int value: '${SPADES_MEMORY}'` (`EXE/SUINO01_885535c1/logs/assembly/SUINO01_spades.stderr.log` e `SUINO01_metaspades.stderr.log`). O log da montagem registra `params='-m ${SPADES_MEMORY}'`.
  4. O pipeline tratou as duas falhas como "falha dura", montou só com velvet e seguiu até o fim: "Consenso incompleto: 1/2 montadores aplicáveis produziram contigs." O job terminou `done` e o Evidence V2 `done_with_warning`, sem dizer na interface que dois dos três montadores não rodaram. A "união MULTI" desta execução é só o velvet (4.939 contigs, 1.087.593 pb, N50 263, maior 15.793 pb).
  5. O denominador "1/2" também confunde: o perfil tem 3 montadores; o "2" é o mínimo exigido (`ASSEMBLY_CONSENSUS_MINIMUM=2`), não o total.
- **Evidência:** `EXE/SUINO01_885535c1/logs/assembly/`, `EXE/SUINO01_885535c1/results/assembly_metadata.env`, `EXE/SUINO01_885535c1/results/assembly_consensus.json` (`assembler_status`: velvet SUCCESS, spades HARD, metaspades HARD; `consensus_requirement_met: false`); `SRC/config/picornavirus.env` × `picornavirus.env.example`.
- **Provável local no código:** `SRC/scripts/dashboard/config.py:344` e `:350` (`line = f"{key}={shlex.quote(str(updates[key]))}"`); `SRC/scripts/pipeline/sample_steps.sh:202` (imprime `SPADES_PARAMS` sem expandir); `SRC/scripts/pipeline/assembly_router.sh:268` (mensagem "1/2").
- **Depois da restauração (SUINO02, job `ce2c576a…`):** a pessoa testadora restaurou `config/picornavirus.env` a partir do backup que o próprio painel fez antes de salvar (`SRC/config/picornavirus.env.bak-20261008_153414_065248-8cf7ec41`). Às ~17:05, `picornavirus.env`, o backup e `picornavirus.env.example` tinham o mesmo SHA-256 (`a6700e90…`). A cópia corrompida foi guardada em `EXE/SUINO01_885535c1/picornavirus.env.CORROMPIDO_apos_salvar_UI` (SHA-256 `1a9f5f82…`, linha 29 `SPADES_PARAMS='-m ${SPADES_MEMORY}'`). Com isso, a SUINO02 rodou os três montadores: velvet 5.302 contigs, SPAdes 2.512, metaSPAdes 2.978; `consensus_requirement_met: true`, 2.216 sequências idênticas entre montadores (`EXE/SUINO02_ce2c576a/DADOS_BRUTOS.md`, item 7). Isso reforça que a falha da 2ª SUINO01 veio só da regravação pela tela. Observação: `config/picornavirus.env` não consta do `SHA256SUMS.txt` do pacote, então a verificação de integridade não percebe essa alteração.
- **Detalhe novo (SUINO02):** com o valor correto, o SPAdes recebeu `-m 12` (o script reduz 64 para 80% da RAM: "[WARN] SPAdes -m 64 excede RAM disponível; ajustando para -m 12", `SRC/scripts/pipeline/assemblers/spades.sh:66-84`), mas o **metaSPAdes recebeu `-m 64`** numa máquina de 15,6 GB: `SRC/scripts/pipeline/assemblers/metaspades.sh` não tem esse ajuste (`:46`, `:155-168`). Nesta amostra pequena não fez diferença (pico interno de 2.401 MiB nos dois, pelo `spades.log`). Repetido na SUINO_NEG (`-m 12` × `-m 64`; `EXE/SUINO_NEG_469b1a6f/logs/assembly/`).
- **Mesma amostra com a config restaurada (3ª SUINO01, job `f6507ec4…`, 17:38:22–17:38:49):** com as mesmas reads limpas da `885535c1` (SHA-256 iguais), os três montadores terminaram com SUCCESS: velvet 4.950 contigs, SPAdes 2.389 (`-m 12`), metaSPAdes 2.857 (`-m 64`, sem o ajuste); união 7.424 contigs (na `885535c1`, só velvet: 4.939); `consensus_requirement_met: true`; `ASSEMBLY_FAILURE_TYPE="NONE"`. Isso fecha a comparação: com a linha `SPADES_PARAMS` original, a mesma amostra monta com os três. RSS amostrado a cada 2 s: SPAdes ≤ 138,5 MiB, metaSPAdes ≤ 123,0 MiB; o `spades.log` registra pico interno de 2.401 MiB nos dois. Evidência: `EXE/SUINO01_f6507ec4/DADOS_BRUTOS.md` (item 7), `logs/assembly/`. A execução `885535c1` está marcada na `EXE/TABELA_SUINO.md` como "SPAdes/metaSPAdes falharam — U-26".
- **Sugestão de correção:** ao gravar, preservar as aspas duplas quando o valor tiver `$`, ou expandir `${SPADES_MEMORY}` antes de passar ao SPAdes e recusar o valor se não virar número. Na interface, quando um montador do perfil falhar, mostrar "SPAdes não executou: <motivo>" no Acompanhar e no resultado, e não apresentar a montagem como MULTI. Trocar "1/2 montadores aplicáveis" por "1 de 3 montadores (mínimo exigido: 2)". Aplicar ao metaSPAdes o mesmo ajuste de `-m` do SPAdes.

### U-27 — Exportação, validação e finalização do Evidence V2 carregam os TSVs de candidatos e fragmentos inteiros na memória (Alta, era Média · pipeline · corrigido — 201d33945184)

**Correção de engenharia na b2:** commit `201d33945184f2ec5d0c9c19eb4b873856c1fce6`. Verificação: scripts/tests/test_u27_byte_parity.py; U27_MEMORIA_PARIDADE.json; PARIDADE_FINAL.json. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Relaciona-se a U-14 (mesmo padrão: arquivo grande lido de uma vez).*

- **Onde aparece:** execução `885535c1…`, etapa "Exportação do relatório" (16:47:48–16:49:41), no `export_candidate_sequences.py`.
- **Esperado:** exportar as sequências candidatas com pouca memória, como o patch do U-14 fez para o resgate.
- **Observado:** o processo subiu de ~1,1 GiB para **5.652,5 MiB de RSS** em ~30 s e o MemAvailable caiu a **883,1 MiB** (16:48:25), abaixo de 1 GiB por ~15 s, numa máquina de 16 GB sem swap. Voltou sozinho; nada foi encerrado e não houve OOM. A entrada era `fragment_evidence.tsv` (571.344.512 B) e a saída foi `candidate_sequences.tsv` com **1.947.891 linhas para 1.099 sequências** (604.635 linhas distintas): uma linha por hit, com linhas repetidas. O `sample_evidence.json` tem 38 MB para 10.206 candidatos.
- **Evidência:** `EXE/SUINO01_885535c1/sistema/mem_samples.tsv` (16:47:52–16:48:35); `EXE/SUINO01_885535c1/DADOS_BRUTOS.md` (itens 2 e 6).
- **Provável local no código:** `SRC/scripts/evidence/export_candidate_sequences.py:15` (`hits = read_tsv(fragments)`) e `:29-33` (uma linha de saída por hit); `SRC/scripts/evidence/common.py:43-49` (`read_tsv` devolve `list(reader)`, o arquivo inteiro na memória); chamada em `SRC/scripts/evidence/run.sh:520`.
- **Observado de novo e ampliado na SUINO02 (job `ce2c576a…`, 14.400 pares, 17:14–17:16):**
  1. `export_candidate_sequences.py`: pico de **6.297,5 MiB** (17:14:58); **MemAvailable mínimo de 699,4 MiB** (17:14:42), abaixo de 1 GiB por ~4–6 s.
  2. **`validate_run_artifacts.py`: pico de 8.248,4 MiB** (17:15:57), 38 s a 100% de CPU. Lê `candidate_sequences.tsv` (449 MB, 2.207.044 linhas) **e** `fragment_evidence.tsv` (678 MB, 2.207.044 linhas) inteiros, como listas de dicionários, só para comparar contagens e `qseqid` (`SRC/scripts/evidence/validate_run_artifacts.py:425-430`).
  3. **`finalize_run.py`: pico de 8.244,5 MiB** (17:16:37), mais 40 s: chama a mesma validação de novo (`SRC/scripts/evidence/finalize_run.py:131`, `validate(args.staging, …)`; importada em `:22`/`:35`).
  4. Os três rodam um depois do outro (17:14:16–17:16:47). Nesta execução o MemAvailable não passou de ~1,8 GiB durante a validação porque a exportação já tinha liberado a memória. **Não houve OOM** (`dmesg`). Nada foi encerrado.
  5. Escala: a SUINO02 reduzida tem 14.400 pares; a AMOSTRA01 completa tem 150.000 pares. Os TSVs crescem com o número de hits (SUINO01, 12.800 pares: 370 MB/571 MB; SUINO02: 449 MB/678 MB). **Por projeção**, com amostras completas a validação passa dos 16 GB desta máquina. Por isso a gravidade sobe para **Alta**: a etapa final, depois de todo o processamento, é a que tem mais chance de derrubar a análise.
  - **Valor que faltava da 2ª SUINO01 (`885535c1…`):** `validate_run_artifacts.py` 7.223,9 MiB (16:49:34) e `finalize_run.py` 7.223,2 MiB (16:50:11). Estavam em `EXE/SUINO01_885535c1/sistema/mem_samples.tsv`, mas não na tabela; acrescentados ao `DADOS_BRUTOS.md` dela.
  - **SUINO_NEG (`469b1a6f…`, 11.200 pares, 17:31:16–17:33:01):** `export_candidate_sequences.py` 4.335,9 MiB; `validate_run_artifacts.py` **5.692,2 MiB**; `finalize_run.py` **5.691,6 MiB**; `candidate_sequences.tsv` com 308 MB / 1.521.275 linhas e `fragment_evidence.tsv` com 466 MB. Menor MemAvailable: 4.185 MiB. Sem OOM. Nas três execuções, o pico dos dois scripts acompanha o tamanho dos TSVs (5.692 → 7.224 → 8.248 MiB para 308 → 370 → 449 MB de `candidate_sequences.tsv`; `EXE/TABELA_SUINO.md`).
  - **3ª SUINO01 (`f6507ec4…`, 12.800 pares, três montadores, 17:50:44–17:53:07):** `export_candidate_sequences.py` **5.642,6 MiB**; `validate_run_artifacts.py` **7.391,0 MiB** (7,22 GiB); `finalize_run.py` **7.390,4 MiB**. `candidate_sequences.tsv` com 404 MB / 1.979.710 linhas (611.525 distintas) para 1.112 sequências; `fragment_evidence.tsv` com 609 MB. Menor MemAvailable: **2.367 MiB** (17:53:01, na finalização). Sem OOM. Com as quatro execuções: 5.692 → 7.224 → 7.391 → 8.248 MiB para 308 → 370 → 404 → 449 MB. Evidência: `EXE/SUINO01_f6507ec4/sistema/mem_samples.tsv`, `DADOS_BRUTOS.md` (itens 2 e 6).
  - Evidência: `EXE/SUINO02_ce2c576a/sistema/mem_samples.tsv` (17:14:16–17:16:47); `EXE/SUINO02_ce2c576a/DADOS_BRUTOS.md` (itens 2, 6 e 9); `sistema/tamanhos_linhas_arquivos_grandes.txt`.
- **Sugestão de correção:** ler o TSV em streaming e gravar a saída linha a linha, no mesmo espírito do patch do U-14. Na validação, comparar os dois TSVs em paralelo, linha a linha (dois `csv.reader` lado a lado, guardando só o conjunto de `qseqid`), e não validar duas vezes (a finalização pode reaproveitar o resultado de `validate_run_artifacts.py` ou receber um hash). Vale a decisão do autor se a tabela deve ter uma linha por hit ou uma por sequência (hoje 1,95 milhão de linhas, sendo 1,34 milhão repetidas, para 1.099 sequências).

### U-28 — "Cancelar execução" é um botão vermelho logo abaixo do log e cancela sem pedir confirmação (Média · interface · corrigido — 90810d811c54)

**Correção de engenharia na b2:** commit `90810d811c54c756739695c45934ca2aaa4bb85c`. Verificação: PAINEL_HEADLESS.json (zero cancelamentos antes da confirmação; um após). A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

- **Onde aparece:** Acompanhar, durante uma análise em andamento (`CAP/D05_acompanhar_pos_submit.png`, `CAP/D06_acompanhar_30s.png`).
- **Esperado:** uma ação que interrompe horas de processamento pede confirmação ("Cancelar a análise da SUINO01? O que já foi processado será descartado") ou fica longe dos pontos onde a pessoa clica para rolar ou copiar o log.
- **Observado:** "Executar análise" inicia sem confirmação, o que é razoável (a Revisão vem antes). Já "Cancelar execução" é um botão vermelho de destaque logo abaixo da caixa do log, e o código envia o cancelamento direto, sem confirmação. A Área avançada pede confirmação para uma ação bem menos destrutiva ("Reconstruir o ambiente local agora?"). Pela regra deste teste o botão **não** foi clicado; a ausência de confirmação foi verificada só no código.
- **Provável local no código:** `SRC/dashboard/js/operational.js:330` (`button("Cancelar execução", async () => { await postJSON(…/cancel) … }, "danger")`, sem `window.confirm`); comparar `SRC/dashboard/js/advanced.js:214` (`window.confirm("Reconstruir o ambiente local agora?")`).
- **Sugestão de correção:** pedir confirmação com o nome da amostra e a etapa atual, e afastar o botão do log (por exemplo, no cabeçalho da execução, como botão secundário).

### U-29 — Depois de uma segunda importação, a amostra selecionada e o cabeçalho passam em silêncio para a última importada (Média · interface · corrigido — bedcedd1d5f4)

**Correção de engenharia na b2:** commit `bedcedd1d5f41def0a43b036621c53e0f3bba1b9`. Verificação: PAINEL_HEADLESS.json (importação conserva amostra selecionada). A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Relaciona-se a U-05 (importação sem resumo) e a U-28 (ação destrutiva sem confirmação).*

- **Onde aparece:** Nova análise → 3. Amostra, ao importar duas amostras seguidas (SUINO02 às 16:59:07 e SUINO_NEG às 16:59:15; `SRC/logs/ux_dashboard.log`).
- **Esperado:** importar uma amostra não muda a escolha já feita sem avisar; ou, se mudar, a tela diz claramente "Amostra selecionada agora: SUINO_NEG".
- **Observado:** depois da segunda importação, a lista "Amostra pareada já importada" e o cabeçalho (AMOSTRA) passaram para **SUINO_NEG**, a última importada, sem aviso além do toast de importação. Quem importou o controle negativo logo depois da amostra de interesse pode executar a análise da amostra errada sem perceber. Nesta sessão a pessoa testadora notou, voltou para SUINO02 e o job foi enviado com `sample: 'SUINO02'` (`ux_dashboard.log`, 16:59:41; `CAP/E01_revisao.png`). A Revisão mostra o nome da amostra, mas nada de origem ou tamanho (U-05) que ajude a perceber a troca.
- **Evidência:** relato da sessão; `SRC/logs/ux_dashboard.log` (16:59:07, 16:59:15, 16:59:41); `SRC/data/incoming/SUINO02.json`, `SUINO_NEG.json`.
- **Provável local no código:** `SRC/dashboard/js/operational.js:213-218` (`onImported` grava `wizard.sample = sampleId` e `context.sample = sampleId` a cada importação).
- **Sugestão de correção:** depois de importar, perguntar "Usar SUINO_NEG nesta análise?" ou manter a seleção atual e só acrescentar a nova amostra à lista; mostrar a troca em destaque. Na Revisão e no botão "Executar análise", repetir o nome da amostra ("Executar análise de SUINO02").

### U-30 — O assistente não tem como declarar o papel da amostra (controle negativo, positivo, lote), embora o pipeline tenha esse suporte (Média · interface / pipeline · corrigido — be99c20fc39b)

**Correção de engenharia na b2:** commit `be99c20fc39b6ef933dfcd2c00e289c4705e042b`. Verificação: scripts/tests/test_u30_byte_parity.py; DASHBOARD_PIPELINE_REAL.json (controle/lote). A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Relaciona-se a U-08 (a Revisão não lista tudo o que a execução usa) e ao escopo dos testes (falsos candidatos por milhão de reads nos controles negativos).*

- **Onde aparece:** as 6 etapas de "Nova análise" e a execução individual da Área avançada. `CAP/F01_revisao_SUINO_NEG.png` é a Revisão da SUINO_NEG: Ambiente, Banco, Amostra, Montador, k-mer e Hospedeiro; nenhum campo de papel, controle ou lote.
- **Esperado:** ao rodar uma amostra que é controle negativo, a pessoa marca isso na tela ("controle negativo de extração / de biblioteca / de sequenciamento", ou positivo, ou amostra) e, se houver lote, informa o lote. O resultado registra o papel e avalia os controles.
- **Observado:** nenhuma das 6 etapas oferece papel, controle ou lote. Toda execução individual sai como amostra comum e "sem avaliação de controles de lote". A SUINO_NEG é um controle negativo por desenho, mas a execução `469b1a6f…` foi enviada sem papel, como as anteriores.
- **O que o pipeline já tem (não exposto no assistente):**
  1. A CLI aceita `--role` com `sample`, `positive`, `negative_extraction`, `negative_library` e `negative_sequencing` (`SRC/src/genein/pipeline/cli.py:65`, mapeado para `EVIDENCE_ROLE` em `:182`), e o manifesto de lote tem a coluna `role` (`SRC/src/genein/pipeline/sample.py:105`).
  2. O Evidence V2 recebe `--role` (`SRC/scripts/evidence/run.sh:68`; padrão `ROLE="sample"` em `:20`), e o pipeline repassa `EVIDENCE_ROLE` (`SRC/scripts/pipeline/sample_steps.sh:685`). O padrão resolvido é `EVIDENCE_ROLE: "sample"` (`SRC/scripts/pipeline/resolve_config.py:122`).
  3. A avaliação de controles existe e usa esses papéis: `SRC/scripts/evidence/evaluate_controls.py:14` (`ROLES = {sample, negative_extraction, negative_library, negative_sequencing, positive}`), comparando a amostra com os controles negativos e positivos do mesmo lote (`:86-93`; campos `sample_rpm`, `maximum_negative_rpm`, `sample_to_negative_ratio`, `:19`).
  4. O lote também existe: manifesto TSV com `batch_id`, `sample_id`, `role`, `library_mode`, `umi_mode`, `r1`, `r2`, `expected_target` (`SRC/scripts/evidence/run_batch.sh`; ação `evidence_batch` em `SRC/scripts/dashboard/jobs.py:793-801`).
- **Onde a interface fixa o valor:** não há um `--role sample` literal no painel. O valor fica fixo porque o painel nunca envia o papel:
  - O assistente monta os `params` sem `role` e sem `batch_id` (`SRC/dashboard/js/operational.js:273`), e o backend monta o comando e o ambiente sem `EVIDENCE_ROLE` (`SRC/scripts/dashboard/jobs.py:776-792`). Vale então o padrão `sample` de `resolve_config.py:122` (o `resolved_config.json` registra `"role": "sample"`).
  - A execução individual da Área avançada também não tem o campo (`SRC/dashboard/js/advanced.js:281`).
  - O único lugar com `role` é "Evidence V2 em lote", na Área avançada, que pede um manifesto TSV colado à mão (`advanced.js:286-291`, placeholder `batch_id\tsample_id\trole…`), sem explicar os papéis e com `host_filter_mode: "none"` fixo (`:295`).
  - Na execução individual, `run.sh` registra sempre "Execução individual sem avaliação de controles de lote." (`SRC/scripts/evidence/run.sh:436`), e a execução sai `UNCONTROLLED`, como na 2ª SUINO01, na SUINO02 e na SUINO_NEG.
- **Por que importa:** o escopo prevê medir "falsos candidatos por milhão de reads nos controles negativos" (`ESCOPO_TESTES_GENEIN.md`, item 5). Pela interface, um controle negativo só pode ser rodado como amostra comum. O número de candidatos por milhão pode ser calculado à parte (está nos dados brutos da SUINO_NEG), mas o programa não o associa ao lote nem às amostras.
- **Evidência:** `CAP/F01_revisao_SUINO_NEG.png`; `SRC/tmp/SUINO02.resolved_config.json` e `SUINO_NEG.resolved_config.json` (`"role": "sample"`); estado das execuções (`scientific_role: "GENERAL"`, controles `UNCONTROLLED`); `EXE/SUINO_NEG_469b1a6f/DADOS_BRUTOS.md`.
- **Sugestão de correção:** na etapa 3, um campo "Papel da amostra" com os cinco valores da CLI em português ("Amostra", "Controle positivo", "Controle negativo — extração / biblioteca / sequenciamento"), e um campo opcional "Lote". Mostrar os dois na Revisão e na "Configuração efetiva" do log, e enviar `EVIDENCE_ROLE` no ambiente do job (`jobs.py:776-792`). Para lotes, um assistente de manifesto em vez do TSV colado.

### U-31 — O Histórico não mostra banco, montador, adaptadores, hospedeiro nem rótulo por execução; duas execuções da mesma amostra só diferem pelo id e pelo horário (Média · interface · corrigido — c1a27b02a385)

**Correção de engenharia na b2:** commit `c1a27b02a385b04ce02d7c0c449d8335fd9dd19d`. Verificação: scripts/tests/test_u31_byte_parity.py; test_dashboard_security.py. A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Relaciona-se a U-19 (os `params` do job não ficam no estado), U-22 (rótulos do Histórico) e U-32 (reexecução sem aviso).*

- **Onde aparece:** Histórico (`CAP/G01_historico.png`, ~17:37). Colunas: Execução (id hexadecimal de 32 caracteres), Amostra, Estado técnico, Início, Fim, Camada e Ações.
- **Esperado:** quem roda a mesma amostra duas vezes, com configurações diferentes, consegue saber qual linha é qual sem abrir arquivos: banco, montador/perfil, k-mer, adaptadores sim/não, filtro de hospedeiro, montadores que de fato rodaram e, de preferência, um rótulo livre ("SUINO01 — config restaurada").
- **Observado:** as duas execuções concluídas da SUINO01 (`885535c1…`, só velvet porque SPAdes/metaSPAdes falharam, U-26; e `f6507ec4…`, três montadores) têm a mesma amostra, o mesmo "Sucesso parcial" e a mesma camada "Evidence V2". Só mudam o id e os horários. A falha da `1088e943…` (filtro de hospedeiro ligado) também aparece apenas como "SUINO01 · Falha". Nenhuma tela de Nova análise permite dar nome ou rótulo à execução. O backend sabe os parâmetros no momento do envio (`ux_dashboard.log`: "Job enfileirado: … params={'sample': 'SUINO01', 'db': 'picornaviridae_refseq', 'assembler': 'consensus', 'kmer': '31', 'host_filter_mode': 'none', …}"), mas eles não chegam ao Histórico.
- **Evidência:** `CAP/G01_historico.png`; `EXE/SUINO01_f6507ec4/api/history_3.json` (entradas sem `db`, `assembler`, `host_filter_mode` nem adaptadores); `SRC/logs/ux_dashboard.log` (linhas 8, 11 e 22).
- **Provável local no código:** `SRC/scripts/dashboard/jobs.py:1188-1201` (a entrada do histórico tem `id`, `action`, `sample`, `start`, `end`, `status` e campos de validação, sem os parâmetros); `SRC/dashboard/js/operational.js:420-440` (`renderHistory`: colunas fixas, sem parâmetros); os parâmetros do job não são gravados no estado (U-19).
- **Sugestão de correção:** gravar os `params` do job (banco, perfil/montador, k-mer, adaptadores sim/não, modo do hospedeiro) e os montadores com sucesso no estado da execução. Mostrar no Histórico uma coluna "Configuração" curta ("Picornaviridae RefSeq · MULTI (3/3) · k31 · adaptadores · sem hospedeiro") e um campo opcional "Rótulo da execução" na Revisão. Mostrar o id encurtado (8 caracteres) com o completo ao passar o mouse.

### U-32 — Reexecutar uma amostra que já tem resultados não gera aviso, e a nova execução sobrescreve os arquivos de trabalho com o nome da amostra; os resultados por execução e as telas do job antigo ficam intactos (Média · interface / pipeline · corrigido — 5e8acc26ba13)

**Correção de engenharia na b2:** commit `5e8acc26ba131ad34689c1225ca883a9f8132529`. Verificação: scripts/tests/test_u32_byte_parity.py; DASHBOARD_PIPELINE_REAL.json (duas execuções preservadas). A comparação comum antes/depois está em `PARIDADE_FINAL.json` e `PIPELINE_PARIDADE_B1_B2.json`; seu escopo e as diferenças de proveniência estão descritos em `docs/correcoes-usabilidade-b2.md`.

*Relaciona-se a U-31 (o Histórico não distingue as execuções), U-24 (configuração global) e ao item de "Em andamento" sobre dados do usuário dentro da pasta do programa.*

- **Onde aparece:** Nova análise → Revisão → "Executar análise", com uma amostra que já tem execução concluída (SUINO01: `885535c1…` às 15:55; reexecutada como `f6507ec4…` às 17:37:55). Arquivos em `SRC/data/assemblies/SUINO01_*`, `SRC/results/blast/SUINO01_*`, `SRC/results/reports/SUINO01_summary.md`, `SRC/results/qc/SUINO01_*`, `SRC/results/short_fragments/SUINO01_*`, `SRC/tmp/SUINO01.resolved_config.json`, `SRC/logs/SUINO01_pipeline.log`.
- **Esperado:** ao reenviar uma amostra que já tem resultados, a tela avisa ("SUINO01 já tem uma análise concluída em 08/10 15:55; a nova execução substituirá os arquivos de trabalho; os resultados da execução anterior continuam no Histórico"). Os arquivos de trabalho ficam numa pasta por execução, ou ao menos a execução anterior fica preservada inteira.
- **Observado (verificado com SHA-256 antes e depois; nada foi alterado pelo testador):**
  1. **Nenhum aviso** na Revisão nem ao executar (`CAP/G04_revisao.png`, `CAP/G05_acompanhar_inicio.png`). Na etapa 3, a lista "Amostra pareada já importada" mostra só "SUINO01", sem indicar que a amostra já tem análises (`CAP/G02_amostra_SUINO01.png`). Para comparar: a importação de FASTQ com nome já existente exige confirmação (`SRC/scripts/dashboard/handler.py:229-230`).
  2. **Sobrescritos, com conteúdo diferente:** `data/assemblies/SUINO01_assembly/contigs.fa` (`1a39307e…` → `e0e2613d…`), `SUINO01_velvet_k31/contigs.fa` (`e7dce001…` → `a1f0e221…`), `assembly_consensus.json`, `assembly_metadata.env`; 15 dos 20 arquivos `results/blast/SUINO01_*`, entre eles `candidate_short.tsv` (`9f0c2ab6…` → `54011938…`), `candidate_conventional.tsv`, `labeled_hits.tsv`, `selection_ledger.tsv` e `hit_contigs.fa`; `results/reports/SUINO01_summary.md` ("Montador utilizado: velvet" → "velvet,spades,metaspades"); `results/qc/SUINO01_fastp.{json,html}`; `tmp/SUINO01.resolved_config.json`. Os outros 5 de `results/blast` (`read_level_*`), as reads limpas e o `rescue_reads.fa` foram regravados com o mesmo conteúdo (mesma entrada).
  3. **Uma geração de reserva só para os contigs:** a montagem anterior foi movida para `contigs.previous.fa` (`1a39307e…`; `SRC/scripts/pipeline/assembly_router.sh:347-351`). Uma 3ª execução substituiria essa cópia. Os demais arquivos não têm reserva.
  4. **`logs/SUINO01_pipeline.log` acumula** as três execuções da SUINO01 num só arquivo (inícios nas linhas 1, 151 e 340).
  5. **Preservados (chave = id da execução):** `results/evidence/runs/885535c1…/` (20 arquivos), `results/runs/885535c1…/` (10) e `results/evidence/state/885535c1….json`: SHA-256 iguais antes e depois.
  6. **O que o painel mostra ao abrir o job antigo depois da reexecução:** os dados **antigos**. `/api/evidence/result` e `/api/evidence/analytics` para `885535c1…` ficaram idênticos byte a byte (SHA-256 `2f9a8b5d…` e `9b8a5894…`); `/api/history/file?run=885535c1…` (relatório, log, BLAST, hits, contigs) serve `results/runs/885535c1…/` (`SRC/scripts/dashboard/jobs.py:1263-1296`), com os contigs antigos (`1a39307e…`); `/api/job/885535c1…` e a linha do Histórico ficaram iguais. **Não houve troca de dados nas telas.**
  7. O risco fica fora do painel: quem abre `results/reports/SUINO01_summary.md` ou `results/blast/SUINO01_*.tsv` no disco vê a execução nova, sem indicação de qual job gerou o arquivo. Arquivos que não entram no retrato por execução (relatório do fastp, `assembly_consensus.json`, contigs por montador, `selection_ledger.tsv`, `candidate_short/conventional.tsv`) **não existem mais na versão da `885535c1`**. O retrato `results/runs/<id>/` é montado no fim do job a partir desses arquivos com nome da amostra (`jobs.py:485-531`, `find_report_path` etc. em `:427-438`). Se a execução nova falhar no meio, os arquivos com nome da amostra ficam misturados entre as duas execuções.
- **Evidência:** `EXE/SUINO01_f6507ec4/DADOS_BRUTOS.md` (seção 8); `EXE/SUINO01_f6507ec4/sistema/sobrescrita/` (`snapshot_antes_mtime.tsv`, `snapshot_antes_sha256.txt`, `sha256_depois_verificacao.txt`, `comparacao_api_antigo.txt`, `api_antigo_antes/`); SHA-256 antigos em `EXE/SUINO01_885535c1/sistema/sha256_arquivos_grandes_nao_copiados.txt`; `CAP/G02_amostra_SUINO01.png`–`CAP/G05_acompanhar_inicio.png`.
- **Provável local no código:** caminhos por nome de amostra em `SRC/scripts/pipeline/sample_steps.sh` (`data/cleaned/${SAMPLE}_*`, `data/assemblies/${SAMPLE}_*`, `results/blast/${SAMPLE}_*`, `results/reports/${SAMPLE}_summary.md`) e `assembly_router.sh:347-351`; o painel não consulta execuções anteriores da amostra antes de enviar (`SRC/dashboard/js/operational.js`, Revisão/Executar; `SRC/scripts/dashboard/jobs.py:776-792`).
- **Sugestão de correção:** na Revisão, se a amostra já tiver execuções, listar a última (data, configuração, estado) e pedir confirmação. No pipeline, gravar os arquivos de trabalho numa pasta por execução (`work/<run_id>/…`) ou copiar para `results/runs/<id>/` também o QC, os contigs por montador e as tabelas de seleção. Escrever um cabeçalho com o `run_id` no `SUINO01_summary.md`. Separar o log por execução (o `ux_<run_id>.log` já existe; o `<amostra>_pipeline.log` poderia ser substituído ou datado).

---

## Pontos positivos (manter)

Observados no teste de usabilidade:

- **Assistente claro em 6 etapas** (Ambiente → Banco → Amostra → Configuração → Revisão → Execução), com Voltar/Próximo e bloqueio correto da execução quando falta algo (A05–A14).
- **A barra superior mostra o contexto** (Ambiente, Banco, Amostra, Execução) durante o assistente (A07, A11). Só precisa ser atualizada fora dele (U-02).
- **Rótulos úteis nos bancos:** "[recomendado]" e "[gigante]" orientam a escolha sem jargão (A07).
- **Preparo do banco rápido:** Picornaviridae RefSeq com 206 sequências, BLAST + índice Bowtie2, em ~8 s (A04).
- **Navegação automática para "Acompanhar"** quando um job começa (A04, A15).
- **Upload funcionou:** toast "Amostra importada: AMOSTRA01" e **amostra selecionada automaticamente** (A10). O backend registra SHA-256 e número de pares (`SRC/data/incoming/AMOSTRA01.json`).
- **Montagem padrão explicada:** "MULTI preserva as sequências dos três montadores, inclusive as produzidas por apenas um deles." (A11).
- **Textos honestos:** "Nenhuma porcentagem ou previsão é inventada", "Este painel descreve o job, não a evidência científica", "A seleção delimita a busca por homologia; não altera limiares científicos." (A04, A07, A15).
- **Confirmação inicial no log** de que a entrada é válida: "FASTQs pareados com sucesso: 150000 reads detectadas" (A15). Corrigir só a palavra "reads" → "pares" (U-03).
- **Os adaptadores informados na interface são de fato aplicados** e validados (A/C/G/T/N) antes da execução (U-09). Observado de novo na SUINO01.
- **3ª SUINO01 completa** (job `f6507ec4…`, ~15 min 11 s): com a config restaurada, a mesma amostra montou com os três montadores, os adaptadores foram aplicados (797 reads cortadas), o filtro desligado foi respeitado e não houve OOM. A reexecução **não alterou** os resultados nem as telas da execução anterior: as pastas por execução (`results/evidence/runs/<id>/`, `results/runs/<id>/`) ficaram intactas (U-32). A etapa de resgate é determinística: com as mesmas reads, os arquivos saíram idênticos byte a byte.
- **SUINO_NEG concluída** (job `469b1a6f…`, ~12 min 8 s): três montadores, adaptadores aplicados (889 reads cortadas), filtro desligado respeitado, sem OOM; o estado registra cada etapa com horário e aviso.
- **SUINO02 com os três montadores** (job `ce2c576a…`): com `config/picornavirus.env` restaurado, velvet, SPAdes e metaSPAdes rodaram, o consenso MULTI foi atingido e o Evidence V2 terminou em ~11 min, sem OOM, numa máquina de 16 GB. Adaptadores aplicados (868 reads cortadas) e filtro desligado respeitado, de novo.
- **2ª SUINO01 concluída de ponta a ponta com o filtro de hospedeiro desligado** (job `885535c1…`): o log diz explicitamente "[3/6] Filtro do hospedeiro ignorado" e os adaptadores digitados foram aplicados de novo. O resgate de reads terminou nesta amostra reduzida (pico de 3.550 MiB no roteador, sem OOM) e o estado registra cada etapa com início, fim e aviso.
- **Falha rápida e sem resultado indevido na SUINO01:** com o índice ausente, o pipeline parou na etapa 3 (sem montar nem buscar), não promoveu FASTQs vazios e marcou `failed`/`NOT_EVALUABLE` na API, no estado e no histórico. As saídas do QC foram preservadas.

Observados na falha da AMOSTRA01 (B01–B05):

- **O estado de falha é coerente** em Acompanhar ("Status técnico: Falha"), na barra superior ("Execução: Falha") e no Histórico ("× Falha"); nada é apresentado como sucesso.
- **Nenhum resultado indevido:** depois da falha, Resultados não mostra candidatos nem conclusão (falta só dizer "Falha", ver U-20).
- **Rastreabilidade:** ID da execução, início (13:46:17) e fim (14:09:22) aparecem no Histórico; o estado salvo registra a etapa que falhou (`failed_stage: initial_blast`).
- **Dados preservados:** a falha não apagou as saídas das etapas anteriores (QC, montagem), o que permite recuperá-las (U-18).

Do teste externo (resumo): instalação pelo lock idêntica ao ambiente travado; teste sintético PASS (funcionamento; não mede sensibilidade nem especificidade); dados anteriores preservados em todos os cenários de erro; `execution.json` com `failed` quando o pipeline falha; painel só em loopback.

---

## Em andamento

- **Análise da AMOSTRA01 encerrada com falha** às 14:09:22 BRT (job `59349d8fa52c4f24894789607ebff9f7`): o processo foi morto por falta de memória no resgate de reads (U-14). A reprodução foi feita em cópia (`REPRO/`), sem parar nem reiniciar o painel e sem iniciar jobs por ele. Fica **NÃO EXECUTADO** pela interface: Evidence V2, candidatos e relatório desta amostra. Os candidatos citados em U-14 vêm da reprodução do resgate (com o patch), não do job.
- **Análise da SUINO01 encerrada com falha** às 15:35:00 BRT (job `1088e943d91d42cf819e9b3e14cca12b`, ~24 s), no filtro de hospedeiro (U-06, U-25). Fica **NÃO EXECUTADO**: filtro de hospedeiro, montagem, BLAST, resgate de reads (a previsão de pico de ~3,6 GiB do `blast_router.py` não foi testada), candidatos e Evidence V2. Dados brutos (QC, comprimento dos reads limpos) em `EXE/SUINO01_1088e943/DADOS_BRUTOS.md`. Nenhum OOM novo no `dmesg`. **Para repetir a SUINO01 com filtro de hospedeiro pela interface, não há caminho** sem correção do U-06 ou decisão do autor; com "Sem filtro", a análise roda sem remoção do hospedeiro.
- **3ª SUINO01 concluída** às 17:53:09 BRT (job `f6507ec470c94b5dba0565ec8cfc3c97`): `done`, Evidence V2 `done_with_warning`, ~15 min 11 s. É a execução SUINO01 completa (três montadores). 1.112 sequências candidatas computacionais (43.437,5 por milhão de reads de entrada; 1.979.710 linhas e 611.525 linhas distintas em `candidate_sequences.tsv`), todas `NOT_EVALUATED`. Dados brutos em `EXE/SUINO01_f6507ec4/DADOS_BRUTOS.md`; comparação em `EXE/TABELA_SUINO.md`. Sem interpretação; tabelas de verdade não usadas.
- **SUINO_NEG concluída** às 17:33:02 BRT (job `469b1a6fca034e1484222ab27cdc8de1`): `done`, Evidence V2 `done_with_warning`, ~12 min 8 s. Executada como `role: sample` (U-30). 805 sequências candidatas computacionais (35.937,5 por milhão de reads de entrada), todas sem rótulo de especificidade (`NOT_EVALUATED`). A etapa BLAST legada teve 0 contigs com hit. Dados brutos em `EXE/SUINO_NEG_469b1a6f/DADOS_BRUTOS.md`; comparação em `EXE/TABELA_SUINO.md`. Sem interpretação; tabelas de verdade não usadas.
- **SUINO02 concluída** às 17:16:48 BRT (job `ce2c576aa8d840cb9b2c19f9e4d5198c`): `done`, Evidence V2 `done_with_warning`, ~17 min 6 s. Três montadores OK; 1.774 sequências candidatas; nenhum rótulo de especificidade atribuído (todos `NOT_EVALUATED`). Dados brutos em `EXE/SUINO02_ce2c576a/DADOS_BRUTOS.md`. A SUINO_NEG foi importada às 16:59:15 e executada às 17:20:54 (item acima).
- **2ª execução da SUINO01 concluída** às 16:50:25 BRT (job `885535c1febd48659b8089f60e1e6458`): `done`, Evidence V2 `done_with_warning`. Filtro de hospedeiro desligado, adaptadores aplicados, resgate executado (25.156 reads no FASTA, 266 anunciadas, 82 selecionadas). SPAdes e metaSPAdes não rodaram (U-26); a montagem ficou só com velvet. Dados brutos em `EXE/SUINO01_885535c1/DADOS_BRUTOS.md`. A comparação com a verdade por read continua fora deste teste.
- **Pendentes para as próximas atualizações desta lista:**
  - Resultados (A16+): desfecho, downloads ("Sequências candidatas (FASTA)", "Tabela de candidatos", "Origens e rastreabilidade"), explorador avançado e Histórico.
  - Registrar como dados brutos os comprimentos das reads e dos candidatos e, em `candidate_sequences.tsv`, o total de linhas, as linhas distintas e as colunas. A comparação com a verdade por read só entra sob especificação fechada do autor; não é objetivo do teste de usabilidade.
  - Efeito do filtro de hospedeiro desligado na montagem e nos candidatos: só registro bruto (o cenário humano está fora do desenho).
  - Execução de AMOSTRA02 e CONTROLE_NEG (mais read-through, segundo `LEIA-ME_DADOS.md`).
  - Comportamento ao executar de novo a mesma amostra: os artefatos ficam em pastas compartilhadas por nome de amostra (`SRC/data/cleaned`, `SRC/results/qc`), o que pode levar a sobrescrita. **Verificado em 08/10 ~17:55 com a SUINO01 (`885535c1` → `f6507ec4`): há sobrescrita dos arquivos de trabalho, sem aviso; os resultados por execução e as telas do job antigo ficam intactos. Ver U-32.** Observação (SUINO01): todas as saídas do painel ficam dentro da pasta do programa (`SRC/data/raw`, `SRC/data/cleaned`, `SRC/results/qc`, `SRC/logs`, `SRC/tmp`, `SRC/config/picornavirus.env` + backups). Esses arquivos ficam fora do manifesto, então `sha256sum -c` continua 440/440, mas misturam dados do usuário com a entrega.


## Novos itens do reteste b2 — evidências recebidas

### U-33-b2 — Velvet não determinístico (Média · reprodutibilidade · documentado — escopo solicitado atendido — 3397dbdaba2e)

**Reteste b3:** Variabilidade observada do Velvet documentada. Nenhum parâmetro, thread ou semente alterado; não se declara determinismo do montador. Commit `3397dbdaba2ed5854bafcb73ce7f35a9d6b19950`.
- **Observado:** `scripts/pipeline/assemblers/velvet.sh` duas vezes sobre os mesmos `SUINO02_R{1,2}.clean.fastq.gz` → 5.250 e 5.282 contigs (SHA diferentes); no job, 5.264. Duas SUINO_NEG b2: 4.240 × 4.256. SPAdes/metaSPAdes, reads limpas e BLAST bruto do resgate foram idênticos à b1.
- **Efeito:** as candidatas b1 × b2 diferem só em sequências ≥60 pb (SUINO01: 200 só b1 / 203 só b2; SUINO02: 226/191; SUINO_NEG: 134/105). Não é regressão da b2; impede comparação byte a byte entre execuções.
- **Evidência:** `/workspace/genein-reteste-b2/logs/63-velvet-determinismo.log`, `comparacao/`.
- **Sugestão (decisão do autor):** registrar a variação no relatório/proveniência ou fixar threads/semente do velvet, se possível.

### U-34-b2 — Wrappers sem verificação de `make` (Média · instalação · corrigido — 14f6db8bf112)

**Reteste b3:** run_linux.sh e bundle/run.sh recusam ausência de make com orientação em português antes de chamar o ambiente. Testados os dois caminhos. Commit `14f6db8bf11245a26a83ad8668acde6e1b3b4a0d`.
- `bash run_linux.sh test-env` e `bash bundle/run.sh test-env` num namespace sem `make` → exit 127 `exec: make: not found` (`logs/18`, `logs/19`). O instalador já verifica (`logs/10`).

### U-35-b2 — `--composite-db` sem manifesto aceito (Média · pipeline · corrigido — c505911727d3)

**Reteste b3:** CLI e adaptadores exigem manifesto para o banco composto; integridade conferida antes de QC. Fixtures dos testes reais passaram a produzir os manifestos dos próprios índices. Commit `c505911727d3e5d171644e43fe90e61e97997e7b`.
- `genein run … --composite-db <banco sem .db-manifest.json>` → exit 0, sem aviso (`logs/55`). Arquivo alterado com manifesto é recusado (`logs/53`).

### U-36-b2 — metaSPAdes com `-m 64` (Baixa · pipeline · PARCIAL — b43ab0e45fe2)

**Reteste b3:** Aviso quando -m excede MemAvailable. O valor -m 64 e o comportamento do montador foram preservados por instrução do autor. Ajuste automático do limite permanece não implementado; não marcar como corrigido. Commit `b43ab0e45fe21d2e9bed44fd297c5df11784b4ab`.
- Log: "[WARN] SPAdes -m 64 excede RAM disponível; ajustando para -m 12"; metaSPAdes: "Memory limit (in Gb): 64" (todas as execuções b2). Não houve falha nas amostras reduzidas.

### U-37-b2 — Controle positivo sem alvo falha tarde (Média · interface / pipeline · corrigido — b150e4ebfbc8)

**Reteste b3:** API recusa alvo ausente, vazio e apenas espaços antes de criar job (HTTP 400). Assistente bloqueia a execução e exige alvo; reexecução conserva o alvo declarado. Mensagem em português. Commit `b150e4ebfbc8d026a198984494544f8bf80bfd91`.
- Job `743f8b26` (`role: positive`, sem `expected_target`): aceito; falha após QC/montagem/BLAST com "[FATAL] positive control requires expected target"; `failed_stage hsp_aggregation`, `TOOL_FAILURE`. `scripts/dashboard/jobs.py` não valida na submissão; o assistente marca o campo como "(opcional)".

### U-38-b2 — `.fastq` listado mas não executável (Média · interface / pipeline · corrigido — 97645123df02)

**Reteste b3:** O comando do painel usa o par .fastq existente, mantendo preferência histórica pelo par .fastq.gz quando ambos existem. Seleção e integridade dos bytes testadas. Commit `97645123df02250f67bec588a663f2e8134c5f70`.
- `data/raw/TESTE_NAOGZ_R1.fastq`/`_R2.fastq` aparecem em `/api/samples` (`handler.py:191`), mas `jobs.py:820` fixa `…_R1.fastq.gz`; job `965f1ea9` falha em 3 s (`INPUT_INVALID`) e a dica lista `results/dashboard-work/<id>/data/raw` (vazia).

### U-39-b2 — Resgate com arquivo bruto ausente = sucesso (Baixa · pipeline · corrigido — 87dd08597d01)

**Reteste b3:** Arquivo bruto ausente causa falha sem TSV de sucesso. Arquivo existente vazio continua válido. Candidatos, decisões e proveniência mantêm equivalência byte a byte. Commit `87dd08597d018ec35ba9b680a1b582577e84fe22`.
- `filter_rescue_reads.py --blast-raw <inexistente>` → exit 0 e TSV só com cabeçalho (`logs/61`). No fluxo normal o roteador falha antes (visto na falha forçada), por isso é latente.

### U-40-b2 — Documentação com versão b1 (Baixa · documentação · corrigido — 606746e42d58)

**Reteste b3:** Versão 2.0.0b3 em metadados e guias atuais; changelog inclui b2/b3. A verificação da b1 foi identificada como registro histórico, sem reatribuir seus resultados à b3. Commit `606746e42d5851b9f5a24539ee8b99d31ee2e187`.
- `LEIA_PRIMEIRO.md` título "2.0.0b1"; `CHANGELOG.md` sem entrada 2.0.0b2; `docs/verificacao-beta-08out.md` "2.0.0b1". `docs/beta-pesquisadores.md` já diz b2.

### U-41-b2 — Suíte do pacote ainda executa testes das trilhas de otimização (Média · testes · corrigido — 9bd505230e8f)

**Reteste b3:** Descoberta de engenharia exclui o arquivo de testes das trilhas de otimização. Imports de optimization e contract_selftest são tardios, exclusivos das trilhas correspondentes. Teste bloqueia qualquer import de optimization ao carregar all-safe. Commit `9bd505230e8f6ab7e67990422e5c920236b39783`.
- `docs/correcoes-usabilidade-b2.md` diz que o teste foi excluído; a descoberta da etapa de engenharia de `scripts/tests/run_test_suite.sh` ainda o inclui. Para cumprir a regra, o reteste usou uma réplica sem esse arquivo por meio de um script auxiliar de engenharia e não rodou a trilha `all-safe` do pacote.

### U-42-b2 — Mensagens e classificação de falhas (Baixa · corrigido com limite — 517b8af56a9c)

**Reteste b3:** API, interface e estado persistido distinguem MEMORY_EXHAUSTED, PROCESS_KILLED e PROCESS_TERMINATED, incluindo sinais escondidos pelo wrapper. SIGKILL isolado não é tratado como prova de OOM. Commit inicial `aeb4a01c5302841d588000e33ff47332dfca9761`.

**Rodada final:** o QC fastp deixa de herdar DATABASE_PREFLIGHT; resgate e BLAST [5/6] deixam de herdar HOST_FILTER ou DATABASE_PREFLIGHT; falha de integridade ou de banco composto grava `failed_stage` `database_preflight` no estado, no painel e no recibo. O recibo da CLI classifica SIGKILL, SIGTERM e falta de memória como o painel. Commit `517b8af56a9cbcc4aee12162e26f861288f7084a`. Limite que permanece: `results/runs/<id>/SUCCESS.json` pode ter `status` `failed`.
- Ver tabela. Evidências: `logs/53`, `execucoes/R1_custom_sem_banco`, `execucoes/U17_falha_forcada`, `Gene-In-2.0.0b2/results/runs/f48e953b…/SUCCESS.json`.

### U-43-b2 — `$MAMBA_ROOT` indefinido (Baixa · instalação · corrigido — verificação estática — 6c42fc47d506)

**Reteste b3:** Desinstalação global usa MAMBA_ROOT_PREFIX, que está definida. ShellCheck aprovado; desinstalação real não executada para preservar o ambiente. Commit `6c42fc47d506e1ee08b4f05a5230f27824ff4c45`.
- Leitura de código: `bundle/run.sh:41`. Não reproduzido em execução.

### U-44-b2 — Veredito de validação em cache (Baixa · interface · corrigido — 4c4debb7f069)

**Reteste b3:** Revalidar arquivos invalida o veredito concluído em cache. API aceita refresh=1; resultado inválido orienta conferir erros/revalidar, sem exigir automaticamente nova análise. Critérios de integridade preservados. Commit `4c4debb7f06929fd9ea748384be9db74ce447b63`.
- `/api/evidence/result?run=99baa985…` → errors "artifact is missing from manifest: fragment_evidence.tsv.box-store-snap-…"; `logs/64c` → EVIDENCE_VALID. O Histórico continua com `evidence_invalid` e a mensagem "a análise precisa ser reexecutada".

### U-45-b2 — Pico de memória do blastn-short do resgate na amostra completa (Alta · pipeline · corrigido — 1fa90b6106f8)

**Reteste b3:** BLAST curto em blocos de 256 queries, tanto no resgate quanto no roteamento. Equivalência real das saídas curta, convencional, combinada e proveniência contra a b2; blocos de 3 e 256, um e dois threads, ambas as políticas de roteamento. AMOSTRA01 completa não foi reexecutada; não há novo pico de RAM medido nessa amostra. Commit `1fa90b6106f8a8ee0a152b70b2ab6bc8af599f7d`.
- **Observado:** F01b (job `617c7f80…`, AMOSTRA01 completa, 150.000 pares, mesmos parâmetros da b1): `blastn -task blastn-short` (22.268 queries, `-evalue 1000`, `-max_target_seqs 206`) pico **10.103 MiB** às 00:09:00 (MemAvailable mínimo 1.037 MiB); `blastn` conventional (295.590 queries) 3.789 MiB; `blast_router.py` 236,8 MiB; `filter_rescue_reads.py` ≤ 64 MiB. Na 1ª tentativa (`639f359a…`, com o painel b1 de 1,9 GB ainda ativo) o blastn-short passou de 1,6 a 6,8 GiB em 6 s e a guarda de 600 MB do reteste encerrou o job (returncode −15). Na F01b, depois de o resgate terminar (44.458 candidatos), o 2º `blastn -task blastn-short` (roteamento dos candidatos, 20.617 queries, `failed_stage hsp_aggregation`) subiu de 720 a 6.105 MiB em 26 s e a guarda encerrou o job às 00:54:17 (MemAvailable 546,9 MiB; job 3.023 s). Na b1 o job morreu no Python (~11,7 GB).
- **Leitura:** a correção U-14 (streaming) funciona: na réplica com os relatórios pré-computados da b1, roteador 241 MiB/164 s e filtro 93 MiB/409 s, com saídas idênticas byte a byte à correção b1. O gargalo restante é o próprio `blastn`, que a U-14 não alcança.
- **Sugestão (engenharia pura, sem mudar parâmetros):** dividir as queries do resgate em blocos e concatenar os relatórios (a reprodução b1 mostrou ~2,7 GB por metade); a escolha de `-evalue`/`-max_target_seqs` é decisão científica do autor.
- **Evidência:** `/workspace/genein-reteste-b2/execucoes/F01_AMOSTRA01_completa/`, `execucoes/F01b_AMOSTRA01_retentativa/`, `cenarios/F01_replay/`.

### U-46-b2 — Diretório temporário do roteador não limpo após SIGTERM (Baixa · corrigido — aa526c17dcfa)

**Reteste b3:** Falha de comando e SIGTERM liberam TemporaryDirectory; testes de processo verificam ausência de resíduos. SIGKILL e desligamento abrupto não permitem limpeza pelo próprio processo. Commit `aa526c17dcfa351bccb618cf37a2f0e5892ef263`.
- Nas duas tentativas: `/tmp/genein-blast-router-s09dhvoc/` (short.fa 2,6 MB com 22.268 queries; short.tsv 0 B) após o job `639f359a…` e `/tmp/genein-blast-router-e_h0qttc/` (short.fa 2,8 MB com 20.617 queries; short.tsv 0 B) após o job `617c7f80…` (`execucoes/F01*/tmp_router_residual.txt`); removidos pelo reteste.

### U-47-b2 — Preset "Sus scrofa" sem índice (Baixa · corrigido — 2666dbc0acf3)

**Reteste b3:** Rótulo Sus scrofa explicita que exige índice preparado separadamente; ausência continua recusada com segurança. Commit `2666dbc0acf3e1e7a5c5ff6f39368b74f7c3e703`.
- `host_filter_mode: sus_scrofa` → HTTP 400 "Índice Bowtie2 incompleto em …/ref/host/sus_scrofa_bt2 … veja docs/HOSPEDEIRO_BETA.md" (`logs/api.log`). Comportamento seguro; o rótulo da lista sugere algo pronto.
