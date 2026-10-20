# Gene-In 2.0.0b2 — correções de usabilidade

Fonte da distribuição b1 preservada no baseline `ddf1dd8`. Foram preparados 43 commits individuais, iniciando por U-14, U-26, U-27, U-06 e P-01. São 42 itens encerrados de engenharia; P-08 conserva o status aberto. O relatório externo original foi preservado antes da atualização.

## Preservação e comparações antes/depois

Os 19 arquivos versionados de configuração científica, perfis, padrões, contrato VERSION e locks foram comparados à b1 por SHA-256: nenhuma alteração de bytes. O teste `test_beta_scientific_contract.py` conserva esses hashes na distribuição. Não foram alterados e-value, max_target_seqs, intervalos de comprimento, perfis nem critérios de evidência.

No teste canônico positivo e negativo com ferramentas reais, 18 arquivos científicos FASTA/TSV da b1 e da fonte corrigida ficaram idênticos byte a byte. Em seis exportações de artefatos reais usando os mesmos arquivos de entrada e os mesmos caminhos, FASTA, TSV e JSON ficaram idênticos. Os testes focados dos itens com processamento também comparam referências b1 ou bytes de entrada e saída. A comparação canônica comum se aplica ao caminho padrão testado; não demonstra todos os dados possíveis nem todas as combinações opcionais.

Não se afirma igualdade byte a byte de toda a pasta de execução: logs traduzidos, versões corrigidas, estados de erro, rótulos, identificadores, datas e caminhos de proveniência necessariamente mudam. Na comparação entre pastas diferentes, candidate_queries.json diferiu exclusivamente nos caminhos inputs[*].path. Essa tentativa e seus hashes foram preservados; não houve normalização para alegar igualdade. Com entradas e caminhos iguais, o JSON exportado foi idêntico.

O patch externo U-14 foi revisado e aplicado; alterações posteriores limitaram-se a explicar a contagem real do resgate. Roteamento fora da ordem esperada conserva o fallback histórico em memória; a redução de memória não é afirmada para esse fallback. No U-27, o caso de 250.000 linhas caiu de 491.380 KiB para 20.864 KiB de RSS; a b1 falhou com limite de 256 MiB e a versão nova exportou/validou dentro desse limite com hashes iguais. Estes são casos de engenharia, não novos limiares ou avaliação de amostras biológicas.

## Verificação

Trilha all-safe padrão: engenharia Python/JavaScript e shell, casos sintéticos, competição e suíte operacional com ferramentas reais. Nenhum módulo optimization* foi importado ou executado; o arquivo de testes das trilhas de otimização foi excluído porque importa esse módulo. Testes de regressão focados complementam a trilha padrão.

O painel foi conferido em Chromium headless separado, sem controlar o ponteiro do usuário: seis rotas, revisão MULTI, adaptadores, hospedeiro próprio, controle negativo, falha com etapa/código, tempo encerrado, quebras de linha, ajuda local, progresso de upload, manutenção da amostra selecionada e confirmação de cancelamento. Submissões desse teste visual foram interceptadas; não são provas de processamento real. Separadamente, três execuções com ferramentas reais pelo gerenciador do painel comprovaram duas execuções isoladas da mesma entrada, igualdade de contigs/BLAST, controle/lote e disponibilidade de QC/contigs após uma falha controlada.

O ZIP sem .git declara NÃO EXECUTADO para o mapeamento direto experimental; isso não equivale a aprovação científica desse teste. O pipeline canônico continua disponível.

## Pendências e alcance

P-08: mensagens citadas, resumo repetido, seletor de arquivos e sobra de desenvolvimento foram corrigidos, mas não se encerra a tradução integral das mensagens técnicas e de ferramentas externas. O item permanece como estava no relatório original. U-12 mantém ordem e escolha padrão; o autor continua decidindo qual banco priorizar. U-15 acrescenta contexto sem aplicar regra quantitativa para contigs longos. As decisões científicas citadas no U-14 permanecem com o autor.

Verificação local em Ubuntu 24.04/WSL2 x86_64, com ambiente científico existente. Não foi demonstrada instalação sem cache em outro computador, Windows/WSL do zero, macOS/ARM, instalação global /opt/genein nem obtenção de um banco real do NCBI pela interface. BLAST continua exigindo os cuidados documentados com prefixos sem espaços. A tentativa em caminho Windows com espaços e as tentativas de montagem da fixture foram preservadas; o ensaio final do painel usou pasta Linux sem espaços e componentes BLAST sem renomear arquivos internos.

O programa organiza e recupera sequências candidatas para revisão humana; não estabelece diagnóstico ou confirmação biológica. Beta identifica a distribuição de software. SAT4–6 e o histórico G0.8 permanecem inalterados.

## Commits e verificações por item

Além das verificações específicas abaixo, a paridade canônica comum e a trava dos 19 arquivos científicos sustentam a preservação do caminho padrão das correções de engenharia. Alterações de apresentação têm saída visual intencionalmente diferente.

| Item | Commit | Estado | Verificação específica/complementar |
|---|---|---|---|
| U-14 | `613260308dea` | corrigido | scripts/tests/test_u14_byte_parity.py; U14_PATCH.json; test_beta_scientific_contract.py |
| U-26 | `76b6cdf9586c` | corrigido | scripts/tests/test_u26_byte_parity.py; U26-router.log |
| U-27 | `201d33945184` | corrigido | scripts/tests/test_u27_byte_parity.py; U27_MEMORIA_PARIDADE.json; PARIDADE_FINAL.json |
| U-06 | `29ae0e0a49ce` | corrigido | scripts/tests/test_u06_byte_parity.py; PAINEL_HEADLESS.json |
| P-01 | `9621c889aff2` | corrigido | scripts/tests/test_p01_byte_parity.py |
| U-25 | `e853e3177248` | corrigido | scripts/tests/test_u25_byte_parity.py; test_host_filter.py |
| P-02 | `f34aebbf1134` | corrigido | test_p01_byte_parity.py; all-safe-final/operational.log; diagnóstico final |
| P-05 | `78596a779266` | corrigido | scripts/tests/test_p05_byte_parity.py; test_blast_specificity_integrity.py |
| U-01 | `5c912d3023a6` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-02 | `101803ce5186` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-03 | `e75f4678f280` | corrigido | scripts/tests/test_u03_byte_parity.py; PAINEL_HEADLESS.json (linhas separadas) |
| U-17 | `1aca7a573d01` | corrigido | scripts/tests/test_u17_byte_parity.py; REGRESSAO_ESTADOS.log; DASHBOARD_PIPELINE_REAL.json |
| U-16 | `13f70fd233cd` | corrigido | test_evidence_job_completion.py; PAINEL_HEADLESS.json |
| U-32 | `5e8acc26ba13` | corrigido | scripts/tests/test_u32_byte_parity.py; DASHBOARD_PIPELINE_REAL.json (duas execuções preservadas) |
| U-18 | `1efb68d3f87b` | corrigido | scripts/tests/test_u18_byte_parity.py; DASHBOARD_PIPELINE_REAL.json (falha e saídas parciais) |
| U-20 | `4d64dfd6c1c3` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-28 | `90810d811c54` | corrigido | PAINEL_HEADLESS.json (zero cancelamentos antes da confirmação; um após) |
| U-24 | `9ba14cee7c61` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-29 | `bedcedd1d5f4` | corrigido | PAINEL_HEADLESS.json (importação conserva amostra selecionada) |
| U-30 | `be99c20fc39b` | corrigido | scripts/tests/test_u30_byte_parity.py; DASHBOARD_PIPELINE_REAL.json (controle/lote) |
| U-31 | `c1a27b02a385` | corrigido | scripts/tests/test_u31_byte_parity.py; test_dashboard_security.py |
| P-10 | `238d762e34fa` | corrigido | PAINEL_HEADLESS.json; docs/uso-e-bancos.md |
| U-07 | `9be1558a0d2d` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-08 | `58807b8e57d4` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-15 | `96aa122df72b` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| P-03 | `57f7b3604645` | corrigido | scripts/tests/test_p03_byte_parity.py |
| P-04 | `b08df4bad9ae` | corrigido | scripts/tests/test_p04_byte_parity.py |
| P-06 | `27965eaa6a6a` | corrigido | tests/test_cli.py; versão do ZIP extraído |
| P-07 | `239d5b0d908e` | corrigido | diagnóstico final; all-safe-final/operational.log |
| P-09 | `97fcbde67489` | corrigido | scripts/tests/run_test_suite.sh; trilha operational no ZIP sem .git |
| P-11 | `db8bf2b2ee4a` | corrigido | PAINEL_HEADLESS.json (revisão MULTI) |
| U-05 | `3cfa3070ca24` | corrigido | scripts/tests/test_u05_byte_parity.py; PAINEL_HEADLESS.json (upload em andamento) |
| U-04 | `31462bafac96` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-09 | `2f83b662e15b` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-10 | `179c70825965` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-13 | `4b86d8eb2325` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-11 | `5b459706ea73` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-12 | `f3fe2d6bfdce` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-23 | `68896ece77a8` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-21 | `f804712609ae` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-22 | `15879c377042` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| U-19 | `b1fd5d3b9a35` | corrigido | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |
| P-08 | `feff18afcc58` | parcial; aberto | test_dashboard_guided.py; regressão JavaScript; PAINEL_HEADLESS.json; paridade canônica comum |

Evidências locais: EVIDENCIAS_USABILIDADE_08OUT_2026/ (PARIDADE_FINAL.json, U27_MEMORIA_PARIDADE.json, DASHBOARD_PIPELINE_REAL.json, PAINEL_HEADLESS.json, logs all-safe-final e verificações do ZIP).
