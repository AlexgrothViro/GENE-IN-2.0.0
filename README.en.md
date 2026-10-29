<div align="center">

# Gene-In

### Candidate sequence recovery and human review

**Local dashboard · Linux and WSL2 · Execution provenance**

[Português](README.md) · [Documentation](docs/README.md) · [Installation](docs/guia/instalacao.md) · [Assemblers](docs/guia/montadores.md)

</div>

---

Gene-In brings data preparation, assembly, similarity search and result reporting into a workflow for human review. Users select their inputs, references and assembler; the application records the configuration and provenance.

## Highlights

- Local dashboard for setup, execution monitoring and exports.
- Velvet, SPAdes, metaSPAdes, MULTI and an optional Gene-In Builder integration.
- Candidate sequences, tables, logs and execution records.
- Separate locations for source code, environments, databases and results.

Candidate sequences are not confirmed biological identifications. Similarity does not establish species, infection or diagnosis.

## Installation

Supported environments: Linux x86_64 or Windows x86_64 with WSL2/Ubuntu. The first installation needs internet access.

On Windows, extract the complete source into a permanent folder, then run `INSTALAR_GENEIN.bat` followed by `ABRIR_GENEIN.bat`.

On Linux or in an Ubuntu/WSL terminal:

```bash
bash bundle/install_wsl.sh
bash bundle/run.sh test-env
bash run_linux.sh
```

Open the address printed in the terminal. Keep the source in its installed location. Databases and sample data are not bundled. See the [installation guide](docs/guia/instalacao.md).

## Assemblers

| Option | Role |
|---|---|
| Velvet | Assembler in the Gene-In environment |
| SPAdes | Individual assembly option |
| metaSPAdes | Individual option for compatible inputs |
| MULTI | Velvet, SPAdes and metaSPAdes together |
| Gene-In Builder | Optional. It cannot be installed without granted access to the private repository |

## Optional Builder

The optional integration uses **Gene-In Builder 0.4.0**, pinned to an identified source commit. It cannot be installed without granted access to the private repository. It is installed into its own environment:

```bash
bash bundle/install_builder.sh
```

Access to the private Builder repository is required. Select **Gene-In Builder** in the dashboard or `--assembler builder` with the `default` analysis profile in the CLI. MULTI remains unchanged. A missing or incompatible Builder produces an explicit error without silently switching assemblers.

The original Builder outputs, warnings and manifest are retained in `builder_raw/`. No host is assumed. See [assemblers](docs/guia/montadores.md) and [results](docs/guia/resultados.md).

## Help

```bash
bash bundle/run.sh genein --version
bash bundle/run.sh genein --help
bash bundle/run.sh genein run --help
```

## Documentation

| Topic | Guide |
|---|---|
| Setup | [Installation](docs/guia/instalacao.md) |
| Dashboard and CLI | [Usage](docs/guia/uso.md) |
| Assembly options | [Assemblers](docs/guia/montadores.md) |
| Outputs and limitations | [Results](docs/guia/resultados.md) |
| Troubleshooting | [Support](docs/guia/suporte.md) |
| Citation and licensing | [Citation](docs/guia/citacao.md) |
| Development and research | [Project](docs/guia/projeto.md) |

The detailed guides are currently in Portuguese.

## Citation and license

Use [CITATION.cff](CITATION.cff) and record the exact source commit and environment. Gene-In uses the [Gene-In Limited Public Use License](LICENSE), not an unrestricted open-source license. Third-party components retain their [own terms](THIRD_PARTY_NOTICES.md).

Report software problems through [GitHub Issues](https://github.com/AlexgrothViro/GENE-IN-2.0.0/issues).
