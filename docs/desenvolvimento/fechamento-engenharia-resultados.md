# Resultado do fechamento de engenharia

## FATO

Base: main `1a9ea5d`. Branch `codex/fechamento-engenharia-20261102`.
Um commit por item; PR sem merge. Builder, config/, src/, VERSION, algoritmos,
limiares e perfis científicos preservados. Nenhuma validação científica.

| Item | Arquivo/linha principal | Teste | Resultado real |
|---|---|---|---|
| (a) | `scripts/pipeline/resolve_config.py:410` | `test_optional_profile_conflict.py` | Passou: false gera ConfigError; true e vazio preservam B. Grupo: 75 passed, 29 subtests passed. |
| (b) | `dashboard/js/state.js:7` | `test_optional_http_cli_parity.py; optional_evidence.test.mjs` | Passou: seis paridades antes do processamento; grupo 16 passed, 27 subtests passed; JS 31 passed. |
| (c) | `scripts/tests/test_real_index_metadata.py:22` | `test_real_index_metadata.py` | Parcial: índices/metadados passaram. Grupo com extras: 9 passed, 4 subtests passed. E2E integral não executado. |
| (d) | `scripts/evidence/check_competitive_labels.py:13` | `test_competitive_labels.py` | Passou: 7 passed; igualdade, faltante, órfão, duplicado, limite e falha da ferramenta; leitura real de IDs. |
| (e) | `scripts/tests/run_test_suite.sh:21` | `test_test_environment.py; ensaio de instalação` | Parcial: instalação e painel passaram; guard do Python de sistema retornou 2 como esperado. Percurso integral de (c) não executado. |

Saída integral resumida dos grupos e dos checks de entrada:
[fechamento-saidas.txt](fechamento-saidas.txt).
Os grupos focados são subconjuntos/repetições e não devem ser somados ao total
de 757 testes Python, 322 subtestes e 31 JavaScript de `make test`.

Os extras passaram: referência alterada com builders extras recusa o recibo;
gerações antigas geram aviso e permanecem preservadas. O job de índices do CI
instala ferramentas reais apenas para criação/inspeção de metadados; a suíte
de engenharia não executa os três testes operacionais explicitamente excluídos.

A primeira suíte teve duas falhas de compatibilidade. A conferência dos IDs
foi posicionada no preflight existente, mantendo a falha de banco em código 65
e sua etapa registrada. O teste de configuração agora fornece um arquivo real
no diretório de trabalho e o leitor respeita esse arquivo antes do caminho
armazenado em memória. Após as correções, `make test` passou.

Leia o [registro de instalação](../instalacao-do-zero.md) para versões e hashes,
e o [alcance de (c)](alcance-fechamento-engenharia.md) para a parte não executada.
Logs completos permanecem na pasta local FECHAMENTO_ENGENHARIA_20261102.

## OPINIÃO

Para (a), erro explícito é a alternativa de menor complexidade: evita alterar
silenciosamente o pedido B e dispensa um segundo contrato para pedido removido.
Para gerações antigas, aviso preserva arquivos cujo uso externo não é conhecido.
Esta revisão não fecha o aceite integral de (c)/(e); o PR deve permanecer em
revisão até a decisão do autor sobre essas pendências.
