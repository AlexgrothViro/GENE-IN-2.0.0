# Correções e verificação da b3 — 09/10/2026

Base: `fix/usabilidade-beta2-20261008`, commit `3b622e97e831fc18ed2de2c6d5d711dd9c43d8bb`. Branch de entrega: `fix/reteste-b2-20261009`. Software `2.0.0b3`; contrato Evidence `2.0.0-alpha.2` preservado. Sem push, merge, tag ou publicação.

São 23 commits de itens, mais o registro de entrega. U-33-b2 atende à instrução documental, sem prometer determinismo. U-36-b2 permanece parcial: aviso acrescentado, redução automática de `-m` não implementada para respeitar a proibição de alterar parâmetros dos montadores. Os demais achados solicitados foram corrigidos conforme o escopo e os limites abaixo.

## Verificações

- Trilha `all-safe` executada pelo orquestrador do pacote: engenharia, sintéticas, competição e ferramentas reais passaram. Não foi executado nem importado `optimization*`; descoberta exclui o teste que o importava. A preparação editável e o ambiente científico já existiam no Ubuntu 24.04/WSL x86_64; não se afirma instalação sem cache em outra máquina.
- Engenharia: 484 testes e 262 subtestes em `scripts/tests`, 127 testes em `tests`, 17 JavaScript, regressões shell e sintaxe/compilação. Uma adição posterior de reconhecimento de `std::bad_alloc` foi conferida na regressão focada final; contagens sobrepostas não devem ser somadas.
- Equivalência real b2/b3 do roteador: blocos de 3 e 256, comprimento 20–200 pb, queries sem alinhamento, dois sujeitos empatados, um/dois threads e ambas as políticas. TSVs curto, convencional e combinado e proveniência idênticos byte a byte. Filtro do resgate e exportações também têm testes antes/depois. Mensagens de erro, avisos e metadados de versão mudaram intencionalmente.
- ShellCheck dos scripts alterados aprovado com exclusões preexistentes SC1091/SC2012/SC2015. Os 19 arquivos científicos/perfis/padrões/locks congelados continuam idênticos por SHA-256.
- Interface em Chromium headless: seis rotas, revisão, upload, campo obrigatório/bloqueio de controle positivo, estado de falha, reexecução, confirmação de cancelamento e ajuda; nenhuma exceção JavaScript. API real recusou três submissões de positivo sem alvo com HTTP 400. Testes de estado/API registram memória, SIGKILL e SIGTERM persistidos.
- Tentativas anteriores e falhas de fixtures foram preservadas: expectativa antiga de mensagem, bancos de teste sem manifesto, fixture CLI sem marcador e cenário que esperava falha tardia de banco inexistente. Corrigidos os testes para os contratos novos, sem relaxar critérios científicos.

## Limites

AMOSTRA01 completa e as amostras suínas reais não foram reexecutadas. Os anexos fornecem logs e resultados, sem os FASTQs completos; a b3 não tem nova medição do pico de RAM nessa amostra. O bloco limita o conjunto de queries de cada processo BLAST, sem garantia universal de consumo máximo. O comportamento de memória do banco e de uma query individual permanece dependente da entrada.

Falha de ferramenta e SIGTERM permitem limpeza; SIGKILL não pode ser interceptado. Logs nativos de ferramentas externas são preservados. `results/runs/<id>/SUCCESS.json` continua sendo o marcador transacional do snapshot legado; seu campo `status` pode ser `failed`, sem significar êxito da análise. Não se alterou o contrato desse consumidor.

A validação científica, SAT4–6 e G0.8 histórico não foram reclassificados. Ausência de candidato não comprova ausência de vírus; candidatos continuam destinados à revisão humana.

## Limitações conhecidas da b3

Estas limitações permanecem por decisão. Nenhuma delas muda parâmetro, limiar, perfil ou padrão científico.

- O BLAST convencional do roteador e o BLAST de contigs seguem numa chamada só, sem divisão em blocos. O pico observado do BLAST convencional foi de cerca de 3,8 GB (3.788,8 MiB na medição da b2). O bloco de 256 queries aplica-se ao perfil curto.
- O Velvet continua não determinístico entre execuções. Nenhum k-mer, semente ou thread foi alterado.
- O metaSPAdes conserva `-m 64`. Quando esse valor excede a memória disponível, o programa só emite aviso.
- Itens somente de interface não foram verificados no navegador nesta rodada.
- `results/runs/<id>/SUCCESS.json` continua sendo o nome do marcador mesmo quando o campo `status` é `failed`. O nome não foi trocado.

## Disco nas etapas do Evidence V2

U-48-b3 troca o SQLite com JSON de cada HSP por agregação de uma consulta por vez. A ordenação externa fica na tabela já agregada, gravada em TSV e não em JSON. Se as consultas não estão agrupadas no relatório, as linhas originais são ordenadas por consulta, ainda sem JSON. O temporário fica em `--work-dir` (`TMPDIR_RUN` da execução). Antes de gravar, a etapa exige espaço livre de seis vezes o tamanho dos relatórios BLAST mais 1 GiB (sete vezes, mais 1 GiB, se o relatório não vier agrupado por consulta). Durante a gravação, para se o livre cair abaixo de 512 MiB. A mensagem é em português e o temporário é removido nessa falha. SIGTERM também desfaz o diretório e encerra com o código 143. SIGKILL não pode ser tratado pelo processo. O fator seis substitui o fator três: no reteste da AMOSTRA01 quase cada HSP permaneceu uma linha agregada, e o pico da etapa foi 44,7 GB para cerca de 4 GB de relatórios. Com as linhas em TSV, os blocos temporários ficam do tamanho da tabela de saída (9,93 GB naquela amostra), e a gravação atômica segura a segunda cópia: o pico esperado no diretório da etapa passa a cerca de 20 GB.

Medição local, 1.999.830 linhas sintéticas (10 sujeitos, HSPs sobrepostos, uma duplicata exata por par), SHA-256 da saída idêntico ao caminho antigo:

| Caminho | Pico de disco | Pico de RSS |
|---|---|---|
| SQLite com JSON (anterior) | 870,2 MiB | 47,8 MiB |
| Agregação em fluxo | 63,8 MiB | 47,0 MiB |

O relatório de entrada tinha 108,5 MiB e a tabela agregada 17,1 MiB. Na AMOSTRA01 o caminho antigo chegou a 19 GB e ainda crescia; esta medição usa linhas mais curtas e não substitui aquela execução.

As etapas seguintes, no mesmo relatório sintético:

| Etapa | O que ocupa disco | Medido |
|---|---|---|
| `build_hsp_evidence.py` | uma linha de saída por HSP e um SQLite de ordinais da chave bruta | 532,6 MiB no diretório de trabalho, dos quais 278,4 MiB são o TSV; RSS 28,4 MiB |
| `build_loci.py` | JSON das linhas já agregadas | mais 83,6 MiB além dos arquivos já gravados; RSS 77,4 MiB |
| `competitive_hits.py` | JSON das linhas já agregadas | mais 75,9 MiB; RSS 38,0 MiB |
| `export_candidate_sequences.py` | só os arquivos de saída, em fluxo | RSS 26,8 MiB; TSV de 7,6 MiB |
| `validate_run_artifacts.py` | leitura em fluxo dos TSV e da FASTA | sem SQLite de HSPs |
| `finalize_run.py` | `os.replace` no mesmo sistema de arquivos | sem segunda cópia do relatório |

A frase anterior, de que `build_loci.py` e `competitive_hits.py` acompanham a tabela agregada e não as dezenas de milhões de HSPs, não vale para a AMOSTRA01. Nessa amostra a agregação deixou 30.044.829 linhas para 30.358.157 HSPs, quase uma linha por HSP. O SQLite com JSON de cada linha chegou a 32,8 GB em `build_loci.py` e a 30,85 GB em `competitive_hits.py`, ambos em `/tmp`. `build_hsp_evidence.py` acompanha o número de HSPs brutos porque o contrato emite uma linha por observação; o SQLite das chaves brutas passou de 7,7 GB.

U-50-b3r troca esses SQLite por fluxo e ordenação compacta no diretório da execução (`--work-dir` / `TMPDIR_RUN`), não em `/tmp`. Cada etapa recusa o início se o espaço livre estiver abaixo da estimativa e interrompe a gravação abaixo de 512 MiB, com mensagem em português. U-51-b3r aplica o mesmo SIGTERM da agregação a essas três etapas: o processo sai com 143 e o temporário some. SIGKILL continua sem limpeza pelo próprio processo. Nada aqui é afirmação biológica: é só o espaço que o programa ocupa.

Medição local, 400.000 linhas sintéticas com uma linha por HSP (consultas em ordem lexicográfica). O SHA-256 da saída nova é igual ao do SQLite anterior em loci e na comparação competitiva.

| Etapa | Pico antigo | Pico novo | RSS |
|---|---|---|---|
| `build_loci.py` | 267,6 MiB | 165,6 MiB | 569 MiB nos dois |
| `competitive_hits.py` | 461,4 MiB | 150,0 MiB | 569 MiB nos dois |
| `build_hsp_evidence.py` | não refeito neste conjunto | 218,0 MiB, já com as entradas e a saída | 484 MiB |
| agregação sem colapso, caminho novo | — | 169,3 MiB (relatório 22,8 MiB, tabela 72,0 MiB) | 88 MiB |

No mesmo conjunto, o temporário novo dos loci ficou perto do tamanho da tabela de fragmentos (cerca de 85 MiB contra cerca de 192 MiB do SQLite). Na comparação competitiva agrupada por consulta o pico novo é a tabela de entrada mais a saída: não há segunda cópia em SQLite. O temporário antigo da AMOSTRA01, de 32,8 GB e 30,85 GB, deixa de ser necessário. A faixa esperada para os loci nessa amostra é da ordem da tabela de fragmentos (9,93 GB), não 33 GB. A evidência de HSP ainda grava uma linha por observação (6,69 GB naquela amostra) e um índice de hashes das linhas brutas, da ordem de alguns GB, no lugar do SQLite de 7,7 GB.

Disco livre para uma amostra no porte da AMOSTRA01 do reteste (300.000 pares, cerca de 30 milhões de HSPs), no mesmo sistema de arquivos:

- o diretório de trabalho de QC, montagem e BLAST mediu cerca de 16 GB e permanece;
- a agregação, com a tabela em TSV, fica em cerca de 20 GB no diretório da etapa enquanto esse trabalho ainda está no disco;
- a construção de loci soma a tabela de fragmentos (9,93 GB), um temporário da mesma ordem e a saída de 1,5 GB.

O ponto mais alto estimado é cerca de 40 GB. O diagnóstico avisa abaixo de **45 GB livres**. Esse número cobre a etapa que esgotou o disco no reteste. Remapeamento, cobertura, classificação, exportação, validação e finalização da AMOSTRA01 completa não foram executados de novo; o BAM de 300.000 pares é pequeno perto dessas tabelas, mas isso não foi medido até o fim nesta rodada. Uma consulta com centenas de milhares de HSPs no mesmo sujeito ainda é agregada em memória; o limite padrão antes de despejar a consulta em disco é 100.000 HSPs.

## Evidências e pacote

Evidências locais em `EVIDENCIAS_RETESTE_B3_09OUT_2026/`: `ANEXOS_VERIFICADOS.json`, `COMMITS_ITENS.json`, `all-safe/report.json` e seus logs, `VERIFICACAO_FINAL.json`, `focused-final.log`, `shellcheck.log`, `U37_HTTP.json`, `PAINEL_HEADLESS.json` e capturas. Caminho Windows: `C:/Users/Admin/Desktop/Nova pasta/EVIDENCIAS_RETESTE_B3_09OUT_2026`.

O ZIP de distribuição é gerado por `scripts/ops/build_bundle_wsl.sh`. `RELEASE.json` na fonte deixa `source_archive_sha256` como `pending`: o valor `97b5429c…` era o arquivo da b1 e não identifica a b3. Depois de fechar o ZIP, o script grava o SHA-256 em `dist/<nome>.zip.sha256` e repete o metadado preenchido em `dist/archive-release.json`. Esse hash não é copiado de volta para dentro do ZIP. A execução do ZIP extraído, sem `.git`, deve declarar NÃO EXECUTADO o teste experimental que exige Git e manter os testes canônicos.

## Itens e commits

| Item | Estado na b3 | Commit | Correção e limite |
|---|---|---|---|
| U-45-b2 | corrigido | `1fa90b6106f8` | BLAST curto em blocos de 256 queries, tanto no resgate quanto no roteamento. Equivalência real das saídas curta, convencional, combinada e proveniência contra a b2; blocos de 3 e 256, um e dois threads, ambas as políticas de roteamento. AMOSTRA01 completa não foi reexecutada; não há novo pico de RAM medido nessa amostra. |
| U-37-b2 | corrigido | `b150e4ebfbc8` | API recusa alvo ausente, vazio e apenas espaços antes de criar job (HTTP 400). Assistente bloqueia a execução e exige alvo; reexecução conserva o alvo declarado. Mensagem em português. |
| U-35-b2 | corrigido | `c505911727d3` | CLI e adaptadores exigem manifesto para o banco composto; integridade conferida antes de QC. Fixtures dos testes reais passaram a produzir os manifestos dos próprios índices. |
| U-42-b2 | corrigido com limite | `517b8af56a9c` | O fastp sai como QC_FASTP. Resgate e BLAST [5/6] usam RESCUE_READS e BLAST. Falha de integridade ou de banco composto grava database_preflight no log, no estado, no painel e no recibo. O recibo da CLI trata SIGKILL, SIGTERM e falta de memória como o painel. O primeiro commit do item foi `aeb4a01c5302`. `SUCCESS.json` em execução falha permanece. |
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
