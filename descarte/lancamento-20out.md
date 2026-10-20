# Gene-In 2.0.0 — distribuição final de pesquisa de 20/10/2026

**Distribuição final de software para pesquisa e triagem humana.** Esta versão consolida a fonte e os guias preparados na rc1, com a identificação pública de software `2.0.0`. O fechamento de versão não acrescenta validação biológica ou reprodução independente. A conferência de cada arquivo compactado e de sua execução extraída pertence aos recibos externos que identificam aquele arquivo por SHA-256. Publicação de tag, release ou pacote no GitHub não faz parte desta entrega local.

## Identidade e escopo

| Dimensão | Identificador |
|---|---|
| Versão de software | `2.0.0` |
| Versão de software | `2.0.0` (`pyproject.toml`, `RELEASE.json`) |
| Contrato Evidence / arquivo `VERSION` | `2.0.0-alpha.2` (identificador congelado do contrato, não a versão do programa) |
| Commit do pacote sem `.git` | primeira linha de `SOURCE_COMMIT`, também em `genein --version` |
| Recuperação | `fragment_recovery_20_100_v1` |
| Revisão científica | `scientific_review_20261005_v1` |
| Plataforma do ambiente fixado | Linux x86_64; Windows x86_64 via WSL2 |
| Finalidade | Recuperação e apresentação de sequências candidatas para pesquisa e triagem humana |

A versão 2.0.0 parte da rc1. O commit dessa candidata ficou na cópia local do autor e não está neste repositório público. A consolidação anterior incorporou a base b3 `d963dfc` e as correções executáveis registradas em `ec84845`, seguidas da organização da distribuição. Os recibos da entrega final identificam o commit completo efetivamente empacotado; esses identificadores históricos não substituem o identificador do pacote 2.0.0.

**Gene-In Builder permanece um desenvolvimento separado**, conforme instrução do autor. Ele não faz parte da instalação, dos perfis, dos exemplos ou da verificação desta distribuição. O fluxo de montagem mantém Velvet, SPAdes, metaSPAdes e MULTI.

Disponibilidade de candidatos, qualificação, competição e atribuição taxonômica continuam dimensões distintas. Os contratos, parâmetros e resultados científicos históricos não são recalculados ou reclassificados pelo fechamento da versão.

## O que usar primeiro

- [README](../README.md): propósito, começo rápido, CLI e resultados.
- [Instalação e reprodução](installation-reproducibility.md): plataformas, locks, servidor local e recursos.
- [Uso e bancos](uso-e-bancos.md): entradas, MULTI, controles, lotes, hospedeiro e interpretação.
- [Uso e bancos](uso-e-bancos.md): primeira análise local.
- [Citação e atribuição](citacao.md): referência da versão 2.0.0 e proveniência da execução.
- [Índice completo](README.md): arquitetura, testes, solução de problemas e histórico.

## Preservação da rc1

A candidata, os pacotes e as evidências anteriores continuam preservados. O histórico completo de 29 referências foi salvo e verificado em `EVIDENCIAS_RELEASE_2_0_0_20OUT_2026/arquivo-rc1-todas-referencias.bundle`. Antes da atualização dos guias, 13 originais documentais foram copiados com SHA-256 conferido para `EVIDENCIAS_RELEASE_2_0_0_20OUT_2026/originais-documentacao-rc1`; a lista completa está em `PRESERVACAO_DOCUMENTACAO_RC1_COMPLETA.json`.

Os registros completos anteriores ficam em `EVIDENCIAS_LANCAMENTO_20OUT_2026` e `ENTREGA_LANCAMENTO_20OUT_2026`. A preparação de 2.0.0 usa **`EVIDENCIAS_RELEASE_2_0_0_20OUT_2026`** e **`ENTREGA_GENEIN_2_0_0_20OUT_2026`**, sem substituir os conjuntos da rc1. Esses nomes identificam diretórios locais mantidos pelo autor, não downloads públicos ou arquivos incluídos na fonte.

## Verificações preservadas da rc1

A tabela abaixo documenta resultados da preparação da rc1. Eles sustentam a base de código consolidada e conservam sua identidade original; **não são resultados do novo ZIP ou tar.gz 2.0.0**.

| Verificação anterior | Resultado e evidência preservados |
|---|---|
| Documentação inicial e limpeza | 121 links/âncoras locais válidos na organização inicial; 141 na conferência documental após a limpeza, sem links quebrados; `git diff --check` aprovado |
| Citação estruturada da rc1 | `CITATION.cff` aprovado como YAML e contra o schema oficial CFF 1.2.0; recibo anterior `CITACAO_VERIFICADA.json` |
| Engenharia da base | Na rc1, 518 testes e 270 subtestes em `scripts/tests`, 130 testes em `tests/` e 17 testes JavaScript; recibos distinguem `fonte-final` e `limpeza-distribuicao`. A suíte medida nesta árvore 2.0.1 está em [desenvolvimento e testes](../docs/guia-de-desenvolvimento.md): 538 testes e 273 subtestes, 137 testes em `tests/` e 17 testes JavaScript |
| Shell e ajuda | ShellCheck de todos os scripts shell com saída 0; `make help` aprovado |
| Painel da fonte | Oito rotas com HTTP 200 e captura visual conferida; recibo `painel-fonte/PAINEL_HTTP.json`; serviço de verificação encerrado |
| Trilhas `all-safe` da fonte | Oito etapas `PASS`, todas com saída 0, incluindo a suíte operacional integral; recibo `fonte-final/ALL_SAFE_FONTE_FINAL.json` |
| Recuperação sintética com ferramentas reais | Quatro cenários aprovados: 20 pb, mistura 20/34/54/74/100 pb, 20 pb com adaptador e controle de hospedeiro de 20 pb; logs e `summary.json` em `fonte-final/fragmentos` |

Testes e subtestes são apresentados separadamente e não devem ser somados como execuções independentes. A limpeza da rc1 acrescentou uma verificação de preservação dos parâmetros experimentais, passando de 517 para 518 testes nessa suíte histórica. A contagem da 2.0.1 não substitui esse recibo da rc1. Os registros b1/b2/b3 continuam pertencendo às próprias versões e ambientes.

A primeira tentativa operacional falhou na construção de um banco sintético porque a ferramenta externa recebeu um caminho com espaços. Ela foi preservada e não representa aprovação operacional. A tentativa revelou também um erro no relatório das trilhas: falha realmente executada podia aparecer como teste não executado. O tratamento foi corrigido para manter `FAIL`; o código 77 continua indicando teste não executado. A repetição aprovada usou um diretório Linux sem espaços e tem seus próprios recibos.

## Verificação da distribuição 2.0.0

Na revisão documental de 2.0.0, os 13 originais continuaram íntegros por SHA-256, os 144 links/âncoras locais dos 32 arquivos Markdown conferidos estavam válidos e `git diff --check` terminou sem erros. O trecho histórico do CHANGELOG, da rc1 em diante, foi preservado integralmente. No `CITATION.cff`, somente o campo de versão mudou para `2.0.0`; autoria e demais metadados foram conservados.

Os recibos em `EVIDENCIAS_RELEASE_2_0_0_20OUT_2026` e `ENTREGA_GENEIN_2_0_0_20OUT_2026` devem identificar a versão, o commit, os comandos, o ambiente, os estados e os hashes efetivamente conferidos. O registro anterior de citação não substitui a conferência do arquivo `CITATION.cff` atualizado para 2.0.0.

`archive-release.json` identifica os arquivos compactados e seus SHA-256. `ZIP_EXECUCAO.json` registra as verificações da cópia extraída. A aprovação de um pacote depende dos recibos correspondentes ao seu próprio hash, inclusive quando a mudança em relação à rc1 se limita à identificação de versão e à documentação. Esta nota não antecipa aprovação de uma execução ou pacote antes da emissão de seu recibo.

Instalação em outro computador, preparação do WSL do zero, instalação global em `/opt/genein`, nova avaliação biológica e reprodução independente não são demonstradas pelo fechamento de 2.0.0. O plano oficial mantido pelo autor continua sendo a referência de andamento das análises; esta nota identifica o software e seus limites.

## Pacote e integridade

A fonte distribuída contém a árvore do programa, lançadores, locks, licenças e documentação. Ambiente científico, bancos, dados, resultados e caches são preparados separadamente.

Para o responsável pelo lançamento:

```bash
python3 scripts/ops/build_release.py --output-dir /caminho/pasta_nova
```

O comando exige checkout Git limpo, usa arquivos rastreados e recusa sobrescrever os destinos. Para esta versão, gera `Gene-In-2.0.0.zip`, `Gene-In-2.0.0.tar.gz`, `SHA256SUMS` e `archive-release.json`; os arquivos de fonte são identificados por `SOURCE_MANIFEST.sha256` dentro dos pacotes. O hash do arquivo compactado é externo, pois um arquivo não pode conter o próprio hash final. O wrapper histórico `build_bundle_wsl.sh` mantém seu nome de saída para consumidores anteriores.

O empacotador foi verificado por testes na preparação da rc1. A criação, a conferência dos membros e a execução extraída de 2.0.0 precisam ser identificadas nos recibos da nova entrega. Usuários instalam pelos lançadores e pelo [guia de instalação](installation-reproducibility.md).

## Limites que acompanham a versão 2.0.0

- A campanha histórica de 27 bibliotecas conserva **G0.8 reprovado**; os estudos adicionais descritos na [validação](validacao.md) permanecem pendentes.
- A recuperação funcional de candidatos não confirma origem viral ou espécie. Ausência de candidato não comprova ausência de vírus.
- O Velvet pode variar entre montagens; o metaSPAdes conserva `-m 64`, com aviso quando supera a memória disponível, sem redução automática.
- O bloco da busca curta não impõe um teto universal de RAM; BLAST convencional e custo das tabelas dependem da entrada.
- O aviso de 45 GB livres vem do porte medido no reteste b3 e não garante capacidade para qualquer biblioteca.
- Em registros legados, o nome `SUCCESS.json` pode acompanhar `status=failed`; confira campos, estado técnico e logs.
- macOS/ARM não são atendidos pelo ambiente fixado. Instalação e reprodução em ambientes não demonstrados exigem recibos próprios.

Os registros internos de reteste ficam em `docs/desenvolvimento/` no repositório Git e não acompanham o pacote distribuído. A licença é a [Gene-In Limited Public Use License v1.0](../LICENSE); redistribuição e modificação dependem da autorização prevista no texto, e os componentes de terceiros mantêm seus [termos próprios](../THIRD_PARTY_NOTICES.md).
