# Licenças e componentes de terceiros

A licença [Gene-In Limited Public Use License v1.0](LICENSE) aplica-se ao código próprio do Gene-In. Componentes de terceiros mantêm suas respectivas licenças; as restrições do Gene-In não substituem os direitos concedidos por elas.

## Incluídos neste pacote

| Componente | Versão/família | Licença e aviso incluído | Fonte oficial |
|---|---|---|---|
| D3 | 7.9.0 | [ISC](dashboard/vendor/LICENSE-d3.txt) | [D3](https://github.com/d3/d3/tree/v7.9.0) |
| Observable Plot | 0.6.17 | [ISC](dashboard/vendor/LICENSE-observable-plot.txt) | [Plot](https://github.com/observablehq/plot/tree/v0.6.17) |
| Archivo | fonte WOFF2 local | [SIL OFL 1.1](dashboard/vendor/fonts/LICENSE-archivo.txt) | [Archivo](https://github.com/google/fonts/tree/main/ofl/archivo) |
| IBM Plex Sans | fonte WOFF2 local | [SIL OFL 1.1](dashboard/vendor/fonts/LICENSE-ibmplexsans.txt) | [IBM Plex Sans](https://github.com/google/fonts/tree/main/ofl/ibmplexsans) |
| IBM Plex Mono | fonte WOFF2 local | [SIL OFL 1.1](dashboard/vendor/fonts/LICENSE-ibmplexmono.txt) | [IBM Plex Mono](https://github.com/google/fonts/tree/main/ofl/ibmplexmono) |

Os arquivos de fonte já estavam presentes na versão anterior. Os avisos oficiais OFL foram incluídos em 08/10/2026; os binários não foram modificados. Os hashes do pacote identificam os arquivos distribuídos.

## Instalados separadamente

Os executáveis científicos e suas bibliotecas são obtidos pelos instaladores Conda/PyPI; não estão embutidos no ZIP da fonte. As versões exatas estão em `environment.linux-64.explicit.txt` e `requirements.lock.txt`. O inventário [dependency-licenses.tsv](docs/dependency-licenses.tsv) registra nome, versão, build, licença declarada e origem dos pacotes do ambiente verificado. Trata-se dos metadados dos distribuidores, não de uma nova licença nem de parecer jurídico.

Os principais executáveis são fastp, SPAdes/metaSPAdes, Velvet, BLAST+, Bowtie2, SAMtools e UMI-tools; MAFFT, FastTree e IQ-TREE atendem aos fluxos adicionais. Licenças integrais dos pacotes permanecem nos seus projetos e no ambiente/cache de instalação. Redistribuir ambientes, contêineres ou binários exige conferir também os termos desses componentes e seus códigos-fonte correspondentes; este ZIP distribui apenas a árvore Gene-In e os assets listados acima.

Bancos e sequências de referência não acompanham a beta. Registre fonte, accession/versão, data e termos dos dados ao preparar o painel. A licença do programa não concede direitos sobre amostras ou bancos de terceiros.
