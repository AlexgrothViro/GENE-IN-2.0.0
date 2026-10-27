# Gene-In — candidate sequence recovery and review

[Português](README.md) · [Documentation](docs/README.md) · [Installation](docs/installation-reproducibility.md) · [Citation](docs/citacao.md)

Gene-In recovers and organizes candidate sequences from fragmented sequencing data for human review. The program is general: the host and the reference database are choices of the person running the analysis. Swine and picornavirus are only the model case used in validation, not a limit of the program. It combines quality control, optional host filtering, assembly, similarity search, provenance and export. Candidate sequences of **20–100 bases and longer** are retained. A sequence alignment does not establish origin, species, infection or diagnosis.

**2.0.2 — memory processing update on distribution 2.0.1, on main since PR #2 (`572a827`); the installer fix (PR #3) is also on main.** The Evidence contract remains `2.0.0-alpha.2`, with recovery policy `fragment_recovery_20_100_v1` and scientific revision `scientific_review_20261005_v1`. The [integration note](docs/integracao-memoria-22out.md) explains disk processing, preserved outputs and verification scope. Scientific parameters, profiles and locks remain unchanged.

This is the [repository](https://github.com/AlexgrothViro/GENE-IN-2.0.0). Published packages belong in [Releases](https://github.com/AlexgrothViro/GENE-IN-2.0.0/releases). Previous names are listed in the [history index](docs/repositorios-e-historico.md).

## Quick start

Supported fixed environment: **Linux x86_64 or Windows x86_64 through WSL2/Ubuntu**. Native Windows, macOS and ARM are not covered by this environment. Initial installation requires internet. The ZIP/source tree does not include a BLAST database or sample FASTQ; prepare a bank and supply your reads (see [usage and databases](docs/uso-e-bancos.md)).

On Windows, extract the complete package to a permanent directory, run `INSTALAR_GENEIN.bat`, then `ABRIR_GENEIN.bat`. On Linux, from the source directory:

```bash
bash bundle/install_wsl.sh
bash bundle/run.sh test-env
bash run_linux.sh
```

Open the URL printed in the terminal. The dashboard binds to `127.0.0.1`; keep its terminal open and stop the server with Ctrl+C when finished. Keep the source tree in place because the editable installation also uses its shell adapters. If tools such as `make` or `bzip2` are missing and `apt-get` fails, installation stops without creating the environment: install them and run the command again. See the [installation guide](docs/installation-reproducibility.md).

The scientific environment lives outside the source tree. The default prefix is `~/.gene-in-bundle`. Set `GENEIN_BUNDLE_DIR` before installing, opening the dashboard and running analyses when another directory is wanted. The Windows launcher uses the default.

Reference data can live outside the source tree as well. When `GENEIN_WORK_ROOT` is an existing absolute directory, the default download FASTA, BLAST database and Bowtie2 index are created there. An explicit `REF_FASTA`, `BLAST_DB` or `BOWTIE2_INDEX` stays on the path you chose. The CLI already requires `--output-root` outside the source tree. Export `GENEIN_OUTPUT_ROOT` to the directory that holds those outputs, or to one output directory that contains `execution.json`, before `bash run_linux.sh`, so the dashboard history lists them.

In the dashboard, select the input reads, prepare/select a database, choose MULTI or one assembler and start with a small library and known controls. MULTI combines Velvet, SPAdes and metaSPAdes outputs and keeps sequences produced by a single assembler. Supply actual library adapters when needed and enable host filtering explicitly with a matching index and host identity.

Read rescue uses SQLite to deduplicate BLAST rows on disk, and export and summary validation process rows incrementally. Filtering retains the two-pass processing and streaming hashes already present in 2.0.1, with improved failure handling and the same input contract: a missing raw file is an error; an existing empty file produces headers only. The full table, one best hit per candidate, descriptions, taxon and provenance remain available. This does not establish a universal RAM limit or solve every disk-space constraint. Gene-In Builder remains separate.

For data of about 300,000 read pairs and 30 million HSPs, the environment check warns below **45 GB free**. This is working space, not a universal capacity requirement. RAM, disk and time depend on the input, database and assembler.

## Command line

After installation, use Linux paths and a prepared BLAST database with its manifest:

```bash
bash bundle/run.sh genein run \
  --sample SAMPLE_01 --r1 /data/R1.fastq.gz --r2 /data/R2.fastq.gz \
  --blast-db /references/panel --output-root /results/new_run \
  --analysis-profile assembly-consensus --evidence-v2 --threads 2
```

The output directory must be new and outside the source tree. To build a database from your own reference FASTA, pass the database name and the file. Index prefixes may live outside the source tree:

```bash
bash bundle/run.sh db DB=my_database REF_FASTA=/data/reference.fa \
  BLAST_DB=/data/blastdb/my_database BOWTIE2_INDEX=/data/bowtie2/my_database
```

For individual SPAdes assembly, use `--analysis-profile default --assembler spades`. Do not combine `--assembler` with `assembly-consensus`. For all options:

```bash
bash bundle/run.sh genein --version
bash bundle/run.sh genein run --help
```

For single-end input, replace `--r1/--r2` with `--single /data/reads.fastq.gz`; for preassembled sequences, use `--contigs /data/contigs.fa`. See the [usage guide](docs/uso-e-bancos.md) for batches, host filtering, controls, competitive panels and adapters.

## Results and interpretation

Results include `candidate_sequences.fa`, `candidate_sequences.tsv`, `candidate_summary.tsv`, `candidate_queries.json` and Evidence reports. The summary has one row per candidate. The best hit is the highest bitscore; ties break on the lower e-value, then the higher identity. `min_evalue` also records the smallest e-value, which may belong to another subject. Taxon and the reference description come from the subject label or, when the label is absent, from the reference title. The query manifest may include queries without aligned candidates. Preserve the complete output directory, logs, resolved configuration and database manifests. `execution.json` is a technical launcher receipt.

Read length, emitted sequence length and HSP length are separate measurements. Repeated sequence observations do not establish independent molecules. Reference coverage is the union of aligned positions per reference/segment; do not add different references as coverage of one genome.

The label shown in the report and the panel is `CANDIDATOS_PARA_REVISAO` when candidate sequences are present, and `SEM_CANDIDATOS_PARA_REVISAO` when they are not. JSON files keep the contract codes `EVIDENCE_RECOVERED` and `DETECTED` (or `NO_EVIDENCE_RECOVERED` and `NO_SIGNAL`). Scientific qualification remains `NOT_EVALUATED`. Taxonomic preference is limited to labeled hits reported in the panel; ambiguity, missing competition and unmeasured support must remain visible.

Functional synthetic checks do not establish biological accuracy, clinical sensitivity, superiority or recovery of every fragment. The historical 27-library campaign belongs to an earlier configuration and retains its failed G0.8 gate. See [validation scope](docs/validacao.md).

The [Gene-In Limited Public Use License v1.0](LICENSE) permits academic evaluation, education and non-commercial research. Redistribution, modification and other restricted uses require prior written permission from the copyright holder. [Third-party terms](THIRD_PARTY_NOTICES.md) apply separately. Cite **Alexsander Groth, Gene-In, version 2.0.2, 2026**, the source commit, databases and parameters; see [CITATION.cff](CITATION.cff) and the [citation guide](docs/citacao.md).
