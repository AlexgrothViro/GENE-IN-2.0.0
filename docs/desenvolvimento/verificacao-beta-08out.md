# Registro histórico de verificação da b1 — 08/10/2026

Este registro pertence à b1. Para a entrega atual, consulte [correções e verificação da b3](correcoes-reteste-b3.md); as contagens abaixo não são resultados da b3.

Versão de software `2.0.0b1`, baseada no commit `3688212c05c1508c5c8847f50275d6b49aa7cbd1`. Contrato Evidence `2.0.0-alpha.2`, recuperação `fragment_recovery_20_100_v1` e revisão científica `scientific_review_20261005_v1` preservados.

Foi criada uma instalação científica em prefixo novo no Ubuntu 24.04/WSL2 x86_64, a partir do lock explícito, com download do micromamba e instalação das dependências Python com hashes. `pip check`, instalação editável da beta, CLI e diagnóstico de ambiente passaram. O mesmo computador já possuía WSL e pode reutilizar caches; isso não equivale a teste em outro computador físico ou em Windows sem WSL instalado.

Regressão Python: 576 testes e 260 subtestes passaram. A regressão específica verifica que um prefixo explicitamente solicitado mas ausente falha antes da detecção das ferramentas, sem escolher outro ambiente. O instalador também rejeita plataforma não Linux x86_64 antes dos downloads e prepara permissões de scripts após extração de ZIP.

O inventário das dependências contém 172 pacotes, todos com licença declarada nos metadados. Avisos das bibliotecas JavaScript preservados; avisos OFL das fontes locais acrescentados. A licença do Gene-In não foi substituída. Essa conferência documental não constitui parecer jurídico.

A suíte de engenharia completa passou, incluindo regressões shell, sintaxe de 65 scripts, compilação e 16 testes JavaScript. ShellCheck passou para todos os sete scripts shell alterados. A suíte operacional passou com fastp/filtro de hospedeiro, BLAST→Evidence, Mapper, mapeamento direto experimental, linhagens UMI, comparação de contigs, três montadores, pipeline positivo/negativo/falha técnica e saturação do hospedeiro. O Mapper foi repetido após corrigir a seleção de ambiente, confirmando as ferramentas do prefixo novo.

A primeira tentativa operacional parou na construção direta do banco da fixture porque o diretório de artefatos continha espaços; a repetição usou caminho Linux sem espaços. Essa limitação do construtor externo está no guia dos participantes. Os registros da tentativa malsucedida foram preservados.

A verificação do ZIP extraído e dos quatro cenários de fragmentos está registrada no relatório de entrega que acompanha o pacote. Os logs completos ficam no conjunto separado de evidências da beta. Esses cenários são funcionais e sintéticos, não uma nova campanha de validação científica.

Limites: macOS/ARM não suportados pelo lock; instalação global `/opt/genein`, instalação do WSL do zero e reprodução por pesquisador em outra máquina não demonstradas nesta revisão. Acesso aos canais, permissões institucionais, RAM e espaço dos bancos precisam ser conferidos pelo participante. A recuperação científica em amostras reais permanece sujeita à [validação adicional](validacao.md).
