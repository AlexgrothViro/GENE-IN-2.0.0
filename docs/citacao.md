# Citação e atribuição

O titular e desenvolvedor identificado na [licença](../LICENSE) é **Alexsander Groth**. A licença solicita citar o trabalho acadêmico associado quando disponível e reconhecer o desenvolvimento do Gene-In como parte de um projeto de mestrado em virologia e bioinformática.

## Referência do software

Para esta distribuição, use:

> Groth, Alexsander. *Gene-In: recuperação e triagem de sequências candidatas*. Versão 2.0.1. 2026. Repositório: https://github.com/AlexgrothViro/GENE-IN-2.0.0.

Acrescente o commit exato e a data de acesso usados na análise. Em um checkout Git, o commit é `git rev-parse HEAD`. Em um pacote sem a pasta `.git`, o mesmo valor está na primeira linha de `SOURCE_COMMIT` e em `genein --version`. O arquivo [CITATION.cff](../CITATION.cff) contém os metadados estruturados.

A versão de software desta distribuição é `2.0.1`. O arquivo `VERSION` continua `2.0.0-alpha.2` porque identifica o contrato Evidence, não o programa; esse conteúdo está congelado no contrato científico. `candidate_version` `2.0.0rc1` em `RELEASE.json` nomeia a candidata histórica. O commit em que essa candidata foi preparada ficou na cópia local do autor e não está neste repositório público. O fechamento da fonte 2.0.0 publicado no GitHub está em `closure_commit` (`42a2c135666337b025b9cd1cdde5b8ae208831f6`). Cite a versão realmente usada: análises feitas na rc1 continuam identificadas como `2.0.0rc1`, e as feitas no pacote fechado de 20/10/2026 como `2.0.0`. Esta correção 2.0.1 não representa aprovação científica nem reprodução independente.

Não há DOI, ORCID, afiliação ou referência bibliográfica acadêmica confirmados nos metadados desta entrega. Esses identificadores não foram inventados. Se o autor fornecer um trabalho associado, cite-o além do software e confira a referência na fonte original.

## O que registrar no método

| Item | Registro necessário |
|---|---|
| Software | Gene-In `2.0.1`, commit exato e origem da fonte/pacote |
| Contrato de resultado | Evidence `2.0.0-alpha.2` |
| Políticas | `fragment_recovery_20_100_v1` e `scientific_review_20261005_v1` |
| Ambiente | Plataforma, locks e versões das ferramentas efetivamente usadas |
| Entradas | Identificadores, tipo da biblioteca, comprimento dos reads e hashes dos arquivos |
| Pré-processamento | QC, adaptadores, filtro do hospedeiro, referência/accession e índice |
| Montagem e busca | Montador ou MULTI, parâmetros e perfis resolvidos, threads e controles |
| Bancos | Fonte, consulta, accessions/versões, data, composição, hashes, manifestos e labels de competição |
| Resultados | Identificador da execução, estado técnico, artefatos e critérios de revisão humana |

Cite separadamente as ferramentas e os dados de terceiros conforme suas próprias recomendações. O inventário de [componentes e licenças](../THIRD_PARTY_NOTICES.md) ajuda a identificar o ambiente, mas não substitui as referências bibliográficas originais de cada ferramenta.

## Texto de método a adaptar

> As sequências candidatas foram recuperadas e organizadas para triagem humana com Gene-In 2.0.1 (Groth, 2026), usando o commit e os parâmetros registrados na proveniência da execução. `provenance.json` e `execution.json` trazem `software_version` e `source_commit`. O campo `pipeline_version` continua sendo o contrato Evidence `2.0.0-alpha.2`, não a versão do programa. O fluxo empregou o contrato Evidence 2.0.0-alpha.2, a política fragment_recovery_20_100_v1 e a revisão scientific_review_20261005_v1. Bancos, controles, pré-processamento e montadores foram documentados por execução. Similaridade, disponibilidade de candidatos e bases alinhadas foram interpretadas separadamente de confirmação de origem viral e atribuição definitiva de espécie.

Complete esse texto com os dados reais do experimento. Não declare etapas que não foram executadas, como filtro de hospedeiro, suporte por reads ou competição. A [validação científica](validacao.md) explica os limites das afirmações sustentadas pela entrega.

## Licença

O nome da licença é **Gene-In Limited Public Use License v1.0**. Não a descreva como MIT, GPL ou licença irrestrita de código aberto. O texto integral permite usos acadêmicos, educacionais e de pesquisa não comercial e restringe, entre outros, redistribuição, modificação e uso comercial sem autorização prévia por escrito do titular. Citar o programa não substitui essa autorização. Veja [LICENSE](../LICENSE).
