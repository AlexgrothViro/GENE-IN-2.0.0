# Gene-In 2.0.2 — comece aqui

Atualização de software para pesquisa e triagem humana, preparada em 22/10/2026 sobre a distribuição 2.0.1. A deduplicação do BLAST passa a usar SQLite e as exportações percorrem as linhas em fluxo, preservando o resumo de candidatos e os contratos. O filtro conserva as duas passagens que já existiam na 2.0.1 e melhora o tratamento de falhas, sem mudar o contrato: raw ausente é erro; arquivo existente vazio produz somente cabeçalhos. Consulte a [nota da integração](docs/integracao-memoria-22out.md). A branch/PR da atualização não representa merge na main nem nova validação biológica. O programa é geral: hospedeiro e banco de referência são escolhas de quem analisa. Suíno e picornavírus são o caso-modelo de validação. Confira o [alcance científico](docs/validacao.md) e os campos de versão e commit no [guia de citação](docs/citacao.md). A licença rege a distribuição desta versão.

1. Leia o [guia inicial](README.md) para conhecer as utilidades e os resultados.
2. Instale em Linux x86_64 ou Windows x86_64 com WSL2/Ubuntu. No Windows, extraia o pacote inteiro em uma pasta permanente e execute `INSTALAR_GENEIN.bat`, depois `ABRIR_GENEIN.bat`. No Linux, use `bash bundle/install_wsl.sh` e `bash run_linux.sh`. O ambiente fica em `~/.gene-in-bundle`, salvo se `GENEIN_BUNDLE_DIR` apontar para outro diretório. `GENEIN_WORK_ROOT` e `GENEIN_OUTPUT_ROOT` separam bancos e saídas da fonte; o guia inicial explica os dois.
3. Prepare um banco e faça a primeira análise com uma biblioteca pequena e controles conhecidos. Veja [uso e bancos](docs/uso-e-bancos.md).
4. Preserve candidatos, relatórios, logs, configuração e manifestos. Use o [guia de citação](docs/citacao.md) para relatar a execução.

O Gene-In Builder permanece um trabalho separado e não integra esta atualização. O pacote não inclui bancos biológicos, índices de hospedeiro ou dados de pesquisa. O painel roda no computador local. Candidatos recuperados exigem revisão humana e não confirmam origem viral, espécie ou diagnóstico. Leia os [limites científicos](docs/validacao.md).

A [licença](LICENSE) permite avaliação acadêmica, ensino e pesquisa não comercial; redistribuição, modificação e outros usos restritos exigem autorização prévia por escrito do titular. Consulte também os [avisos de terceiros](THIRD_PARTY_NOTICES.md).

O [índice da documentação](docs/README.md) reúne instalação, solução de problemas, testes e registros históricos. A versão de software é `2.0.2` (`pyproject.toml` e `RELEASE.json`). O arquivo `VERSION` continua `2.0.0-alpha.2`: é o contrato Evidence, não uma versão alfa do programa. A fonte 2.0.0 fechada pelo autor permanece no histórico. Sem a pasta `.git`, o commit do pacote está em `SOURCE_COMMIT`.
