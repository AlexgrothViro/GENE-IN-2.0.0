# Resultado do fechamento de engenharia

## FATO

Base: main `1a9ea5d`. Branch `codex/fechamento-engenharia-20261102`, PR #10, sem merge. Os cinco commits iniciais preservam um commit por item (a)–(e); complementos de cobertura, E2E, CI, pré-registro e evidências estão separados em commits posteriores. Builder, config/, src/, VERSION, algoritmos, limiares e perfis científicos preservados. Nenhuma validação científica executada.

| Item | Arquivo principal | Teste | Resultado real |
|---|---|---|---|
| (a) conflito B/desligado | `scripts/pipeline/resolve_config.py` | `test_optional_profile_conflict.py` | Passou: false gera erro explícito; true e vazio preservam B. Coberto pela suíte completa. |
| (b) painel × CLI | `dashboard/js/state.js; scripts/dashboard/evidence_options.py` | `test_optional_http_cli_parity.py; optional_evidence.test.mjs` | Passou: seis paridades de configuração e proveniência, três estados × duas opções. |
| (c) E2E real | `scripts/tests/run_optional_e2e.py; Makefile` | `make e2e` | Passou localmente e no CI: quatro combinações reais, FASTQ artificial de 20–100 caracteres, caminhos com espaços, recibos e hashes. |
| (d) rótulos × banco | `scripts/evidence/check_competitive_labels.py` | `test_competitive_labels.py` | Passou: igualdade, IDs faltantes, órfãos, duplicados, contagem e limite de exemplos. E2E exercita o preflight real. |
| (e) instalação | `bundle/install_wsl.sh; scripts/tests/run_test_suite.sh` | instalador do pacote, HTTP e `make e2e` | Passou: ferramentas externas provisionadas, painel HTTP200 e E2E após instalação; guard de Python gerenciado permanece coberto. |
| cobertura restaurada | `scripts/tests/run_test_suite.sh` | `make test` | RealBlastRouterTests e teste real de resumo voltaram à coleta; sem --deselect; skips condicionais mostram motivo. |
| comentário solto | `scripts/pipeline/sample_steps.sh` | regressões de configuração/paridade | Removido; testes usam o marcador estável seguinte. |
| plano científico | `docs/validacao/PROJETO_VALIDACAO_DECOY_REMAP.md` | revisão documental | Proposta criada, sem execução, N ou margem inventados; decisões pendentes explicitadas. |

Os extras continuam cobertos: referência alterada com builders extras recusa o recibo de cache; gerações antigas geram aviso e permanecem preservadas. A suíte de engenharia não executa `test_validation_tracks.py`, que pertence à otimização/validação e está fora desta revisão.

Resultados e saídas atuais: [relatório E2E](RELATORIO_E2E_20261102.md), [instalação](../instalacao-do-zero.md), [saídas resumidas](fechamento-saidas.txt), [manifesto E2E](e2e-manifest-20261102.json), [CI](e2e-ci-20261102.json) e [recibo de instalação](instalacao-independente-e2e.json). Grupos focados e repetições se sobrepõem; não somar seus contadores ao total da suíte.

Os registros iniciais de (c)/(e) eram parciais. A revisão atual acrescenta o percurso completo de software e a instalação com ferramentas externas provisionadas. Isso não altera resultados científicos históricos, nem constitui evidência de desempenho em dados biológicos.

## OPINIÃO

Erro explícito no conflito B evita substituir silenciosamente o pedido com menor complexidade. Avisar sobre gerações antigas preserva arquivos com possível uso externo. A decisão de merge continua exclusivamente com o autor; o estudo exige aprovação dos portões do pré-registro.
