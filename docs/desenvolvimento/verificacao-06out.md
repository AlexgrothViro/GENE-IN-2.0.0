# Verificação da entrega — 06/10/2026

Entrega: `genein-functional-20261006`. Contrato `2.0.0-alpha.2`, recuperação `fragment_recovery_20_100_v1`, revisão científica `scientific_review_20261005_v1`. A base foi o ZIP corrigido de 05/10, com 418 arquivos conferidos por SHA-256 antes da organização.

## Verificações realizadas

| Verificação | Resultado |
|---|---|
| Base corrigida instalada em ambiente isolado | 575 testes e 258 subtestes aprovados; 16 testes JavaScript aprovados |
| Suíte de engenharia da entrega organizada | 449 testes unittest e 126 testes pytest aprovados; 16 testes JavaScript aprovados |
| Shell | Sintaxe válida nos 65 scripts; ShellCheck com severidade warning sem avisos |
| Dependências Python e CLI instalada | `pip check` sem conflitos; CLI pública executada |
| Ferramentas reais | Suíte operacional concluída: QC/filtro, BLAST/Evidence, Mapper, mapeamento direto experimental, UMI, comparação de contigs, montadores, pipeline canônico e saturação pelo hospedeiro |
| Recuperação curta | Quatro cenários aprovados: 20 pb, mistura 20/34/54/74/100 pb, adaptador explícito e hospedeiro sintético |
| Interface | Inspeção visual do início e da configuração: ambiente pronto, MULTI e montadores individuais, filtro opt-in e campos de adaptador |
| Preservação | Configurações científicas idênticas à base após normalização LF; fonte e pacotes históricos preservados; licença preservada |

A verificação das falhas anteriores do pacote extraído reproduziu a passagem da suíte após instalação editável correta. Os testes da CLI retiram `PYTHONPATH` de propósito: a ausência do pacote instalado produzia `No module named genein`.

O primeiro teste de engenharia no GitHub revelou que o caso controlado de ausência de UMI-tools dependia de `bowtie2-inspect` instalado no host. O executável passou a ser simulado explicitamente, como os outros pré-requisitos desse caso. Essa correção altera somente o isolamento do teste, sem mudar o mapeamento ou os parâmetros científicos. A publicação final usa a tag com sufixo `-r1`.

A primeira tentativa de suíte operacional numa cópia sem Git foi interrompida pelo requisito de proveniência do módulo experimental de mapeamento direto. A suíte passou com a identidade Git real e registro explícito `MODIFIED` para a fonte executada, com hashes dos módulos. A recuperação canônica de fragmentos não exige Git. Essa condição está documentada no guia de desenvolvimento.

Ambiente: Ubuntu 24.04/WSL, Python 3.11.15, fastp 1.3.6, SPAdes 4.2.0, Velvet 1.2.10, BLAST 2.17.0, Bowtie2 2.5.5, Samtools 1.24 e UMI-tools 1.1.6. Os testes usaram dependências científicas já instaladas e venv separado para a instalação da fonte. A criação de todo o ambiente por canais externos e a instalação global `/opt/genein` não foram repetidas nesta revisão.

Logs e artefatos completos foram preservados no pacote separado de verificação da entrega, com hashes. Os testes usam dados sintéticos, não amostras clínicas. Seu alcance é funcional; os limites científicos continuam em [validacao.md](validacao.md).

O histórico anterior do repositório permanece na branch `archive/pre-entrega-20261006`. A fonte atual incorpora as correções locais posteriores àquele histórico. Documentos antigos podem descrever defaults diferentes; use este índice e os perfis distribuídos para esta entrega.
