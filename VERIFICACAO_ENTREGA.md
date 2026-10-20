# Verificação da recuperação 20–100 pb

Registro histórico de 02–03/10. Para a edição corrigida de 05/10, consulte [correções científicas e contrato](docs/correcoes-cientificas-05out.md) e o pacote separado de evidências da correção.

Data: 02/10/2026. Esta verificação refere-se à cópia `GENEIN_FINALIZACAO`, não à campanha congelada.

## Verificado

- Fluxo real FASTQ → fastp → montagem/resgate → BLAST → Evidence, com 150 pares por cenário: moléculas de 20 pb; mistura de 20/34/54/74/100 pb; moléculas de 20 pb em reads de 125 pb com adaptadores explícitos; controle de hospedeiro de 20 pb.
- Sequências pós-QC iguais às moléculas de origem conhecida; comprimento correto; exportação integrada e transação concluída. O controle de hospedeiro não foi classificado como específico do alvo.
- Fluxo canônico real com alvo, controle aleatório e falha deliberada de banco. Falha permaneceu `NOT_EVALUABLE`, sem reutilizar staging.
- Instalação editável do pacote em ambiente Linux temporário, sem novas dependências ou alterações no ambiente global; comandos da instalação testados pela suíte.
- Validação dos arquivos de candidatos: IDs, sequências, hashes, comprimento, proveniência e correspondência com as evidências. Corrupção deliberada do FASTA é rejeitada.
- Seleção MULTI e individual, campos de adaptador e exportações na interface verificados por testes dos módulos e servidor. Os 14 testes JavaScript passaram.

## Evidências

- `VERIFICACAO_REAL/fragment_recovery_final.log` e `VERIFICACAO_REAL/evidencias_fragmentos_final/summary.json`: quatro cenários reais aprovados, com entradas, verdade das moléculas, saídas e logs preservados.
- `VERIFICACAO_REAL/pipeline_final.log`: fluxo canônico aprovado. Artefatos Linux: `/tmp/genein-finalizacao-20261002/genein-e4-e2e.fgKYGy`.
- `VERIFICACAO_REAL/pytest_final.log`: 126 testes da suíte pública aprovados.
- `VERIFICACAO_REAL/pytest_final_completa.log`: 560 testes de módulos/scripts aprovados na revisão final, em 108 segundos, sem falhas.
- `VERIFICACAO_REAL/pytest_entrega_conferida.log`:562 testes aprovados após os ajustes finais de abertura/downloads, em113,82s. Os65 scripts shell incluídos passaram em `bash -n`.
- `VERIFICACAO_REAL/mapper_final.log` e `host_final.log`: integração real BLAST/Evidence/Mapper e saturação total pelo hospedeiro aprovadas.
- `VERIFICACAO_REAL/regressao_final_incremento.log`: 59 testes focados aprovados após os últimos ajustes de exportação e adaptadores.
- `VERIFICACAO_REAL/abertura_bundle.log`, `abertura_porta_ocupada.log`: interface aberta pelo ambiente isolado existente; porta ocupada8877 levou à porta8878, registrada no recibo exclusivo e confirmada pelo aguardador Windows.
- `VERIFICACAO_REAL/interface_configuracao_final.jpg` e `interface_resultado_final.jpg`: inspeção visual do fluxo guiado, MULTI/adaptadores e resultado funcional20pb. O ambiente WSL aparece pronto; os três links de candidatos aparecem após validação do resultado.
- `VERIFICACAO_REAL/downloads_http_final.json`: FASTA, TSV e JSON servidos com HTTP200, nomes de arquivo corretos e SHA-256 idêntico aos originais. O FASTA baixado pela interface também teve hash conferido.

## Limites

Os cenários sintéticos são verificações funcionais de origem conhecida, sem erros de sequenciamento simulados ou estimação de desempenho biológico. Não substituem o estudo fragmentado multissemente proposto na revisão científica, nem confirmação independente em amostras reais.

A detecção automática de adaptadores falhou no cenário de molécula de 20 pb com read-through; o cenário passou com os adaptadores corretos informados explicitamente. O QC mantém sobreposição padrão de 30 pb, registrada na proveniência.

A instalação completa a partir dos canais externos não foi repetida; a abertura pelo ambiente isolado já instalado e a inspeção visual da interface foram verificadas. O pacote continua identificado pelo contrato `2.0.0-alpha.2`, com política nova `fragment_recovery_20_100_v1`. As evidências anteriores, inclusive o G0.8 reprovado, permanecem inalteradas.
