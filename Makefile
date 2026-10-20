SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -euo pipefail -c

SCRIPTS_DIR := scripts
# Keep inputs and generated files outside the source tree when requested.
GENEIN_WORK_ROOT ?=
WORK_PREFIX := $(if $(strip $(GENEIN_WORK_ROOT)),$(GENEIN_WORK_ROOT)/,)

ENV_DB := $(if $(filter environment environment\ override,$(origin DB)),$(DB),)
ENV_DB_QUERY := $(if $(filter environment environment\ override,$(origin DB_QUERY)),$(DB_QUERY),)
ENV_REF_FASTA := $(if $(filter environment environment\ override,$(origin REF_FASTA)),$(REF_FASTA),)
ENV_BLAST_DB := $(if $(filter environment environment\ override,$(origin BLAST_DB)),$(BLAST_DB),)
ENV_BOWTIE2_INDEX := $(if $(filter environment environment\ override,$(origin BOWTIE2_INDEX)),$(BOWTIE2_INDEX),)

# Parâmetros padrão (podem ser sobrescritos: SAMPLE= KMER=)
SAMPLE ?=
KMER   ?= 31
ID     ?= amostra_teste
R1     ?=
R2     ?=
SINGLE ?=
DB      ?= custom
DB_QUERY ?=
TRACK ?= all-safe

# Force simply-expanded evaluation to break any imported environment/recursive loops
SAMPLE := $(SAMPLE)
KMER   := $(KMER)
ID     := $(ID)
DB     := $(DB)
DB_QUERY := $(DB_QUERY)
TRACK := $(TRACK)

KMERS   ?=
THREADS ?= 4

# Controle de qualidade (fastp)
SKIP_QC       ?=

# Parâmetros CLI repassados ao pipeline
ASSEMBLER      ?=
ANALYSIS_PROFILE ?=
SPADES_PARAMS  ?=
BLAST_TASK     ?=
BLAST_WORD_SIZE ?=
BLAST_EVALUE   ?=

# Caminhos padrão (definidos como simplesmente expandidos para quebrar referências circulares)
REF_DIR       ?= data/ref
REF_FASTA     := $(REF_DIR)/$(DB).fa
BLAST_DB      := blastdb/$(DB)
BOWTIE2_INDEX := bowtie2/$(DB)
.PHONY: help setup_dirs deps test-env test-env-advanced filter-host test-velvet test-blast \
  ptv-fasta ptv-fasta-legacy blastdb bowtie2-index db-blast pipeline test clean clean-safe clean-all fix-wsl \
  db db-list sample-add run smoke-test benchmark-demo test-validation

ifneq ($(wildcard config/picornavirus.env),)
-include config/picornavirus.env
else
-include config.env
endif

ifneq ($(strip $(ENV_DB)),)
DB := $(ENV_DB)
endif
ifneq ($(strip $(ENV_DB_QUERY)),)
DB_QUERY := $(ENV_DB_QUERY)
endif

# Strip any double quotes that might be imported literally from env files
DB              := $(subst ",,$(DB))
SAMPLE          := $(subst ",,$(SAMPLE))
KMER            := $(subst ",,$(KMER))
ID              := $(subst ",,$(ID))
REF_DIR         := $(subst ",,$(REF_DIR))
REF_FASTA       := $(subst ",,$(REF_FASTA))
BLAST_DB        := $(subst ",,$(BLAST_DB))
BOWTIE2_INDEX   := $(subst ",,$(BOWTIE2_INDEX))
DB_QUERY        := $(subst ",,$(DB_QUERY))
ASSEMBLER       := $(subst ",,$(ASSEMBLER))
ANALYSIS_PROFILE := $(subst ",,$(ANALYSIS_PROFILE))
SPADES_PARAMS   := $(subst ",,$(SPADES_PARAMS))
BLAST_TASK      := $(subst ",,$(BLAST_TASK))
BLAST_WORD_SIZE := $(subst ",,$(BLAST_WORD_SIZE))
BLAST_EVALUE    := $(subst ",,$(BLAST_EVALUE))
SKIP_QC         := $(subst ",,$(SKIP_QC))
TRACK           := $(subst ",,$(TRACK))

# Recalculate paths to ensure consistency and quote-free values.
# Command-line values are kept by GNU make. Values coming from the
# environment are captured above and restored here, because a plain
# assignment would otherwise drop them. GENEIN_WORK_ROOT, when set,
# places these defaults outside the source tree.
REF_FASTA     := $(WORK_PREFIX)$(REF_DIR)/$(DB).fa
BLAST_DB      := $(WORK_PREFIX)blastdb/$(DB)
BOWTIE2_INDEX := $(WORK_PREFIX)bowtie2/$(DB)
ifneq ($(strip $(ENV_REF_FASTA)),)
REF_FASTA := $(ENV_REF_FASTA)
endif
ifneq ($(strip $(ENV_BLAST_DB)),)
BLAST_DB := $(ENV_BLAST_DB)
endif
ifneq ($(strip $(ENV_BOWTIE2_INDEX)),)
BOWTIE2_INDEX := $(ENV_BOWTIE2_INDEX)
endif

# Forward REF_FASTA only when the user chose the file. The computed default
# is a download destination inside db_manager.sh; passing it unconditionally
# makes a missing profile FASTA look like a local file.
PASS_REF_FASTA := $(if $(filter command line,$(origin REF_FASTA)),REF_FASTA="$(REF_FASTA)",$(if $(strip $(ENV_REF_FASTA)),REF_FASTA="$(ENV_REF_FASTA)",))

.PHONY: cfg-all cfg-db cfg-assembly cfg-blast

cfg-all: cfg-db cfg-assembly cfg-blast

cfg-db:
	bash scripts/ops/build_custom_db.sh

cfg-assembly:
	bash scripts/pipeline/assembly_router.sh

cfg-blast:
	bash scripts/legacy/ptv/blast.sh

help:
	@echo "Alvos disponíveis:"
	@echo "  make deps                  # instala dependências (apt-get, incl. ncbi-entrez-direct) e roda check de ambiente"
	@echo "  make setup_dirs             # cria estrutura básica (data/, results/, docs/)"
	@echo "  make demo                  # gera FASTQ demo reprodutível em data/raw (DEMO_R1/R2)"
	@echo "  make ptv-fasta              # baixa/gera FASTA de PTV em $(REF_FASTA)"
	@echo "  make ptv-fasta-legacy       # cria symlink data/$(DB)_db.fa -> $(REF_FASTA)"
	@echo "  make blastdb                # gera banco BLAST em $(BLAST_DB) (usa $(REF_FASTA))"
	@echo "  make bowtie2-index          # gera índice Bowtie2 em $(BOWTIE2_INDEX) (usa $(REF_FASTA))"
	@echo "  make db                     # prepara FASTA + BLAST DB + Bowtie2 (via db_manager)"
	@echo "  make db-list                # lista perfis básicos de DB"
	@echo "  make sample-add             # faz staging de amostra em data/raw"
	@echo "  make run                    # sample-add + db + pipeline"
	@echo "  make pipeline               # roda verificação + pipeline completo (scripts/pipeline/run.sh)"
	@echo "  make benchmark-demo         # gera tabela e gráficos preliminares do demo"
	@echo "  make test-env               # verifica dependências básicas"
	@echo "  make test-env-advanced      # inclui checagens avançadas (filogenia)"
	@echo "  make smoke-test             # roda smoke test (prep + scripts/ops/smoke_test.sh)"
	@echo "  make test                   # suíte de engenharia (contratos/fixtures; nao e validacao cientifica)"
	@echo "  make test-operational       # ferramentas reais em casos sinteticos; nao e validacao cientifica"
	@echo "  make test-tracks            # orquestra faixas de teste (TRACK=all-safe por padrao)"
	@echo "  make filter-host/test-velvet/test-blast # alvos individuais legados"
	@echo "  make clean                  # remove artefatos gerados (blastdb, bowtie2, run_T1, logs/tmp/results)"
	@echo "  make clean-safe             # remove apenas temporários/cache (preserva results/ e logs/)"
	@echo "  make clean-all              # limpeza completa (pede confirmação; NÃO apaga data/raw/)"
	@echo "  make ux                     # inicia o painel web local"
	@echo
	@echo "Variáveis úteis:"
	@echo "  REF_FASTA=$(REF_FASTA)"
	@echo "  BLAST_DB=$(BLAST_DB)"
	@echo "  BOWTIE2_INDEX=$(BOWTIE2_INDEX)"
	@echo "  SAMPLE=$(SAMPLE) KMER=$(KMER)"
	@echo "  ID=$(ID) R1=$(R1) R2=$(R2) SINGLE=$(SINGLE)"
	@echo "  DB=$(DB) DB_QUERY=$(DB_QUERY)"
	@echo "  GENEIN_WORK_ROOT=$(GENEIN_WORK_ROOT) (vazio: padrões dentro da fonte)"
	@echo "  THREADS=$(THREADS) KMERS=$(KMERS)"
	@echo
	@echo "Exemplos de montagem:"
	@echo "  make pipeline SAMPLE=DEMO ASSEMBLER=velvet"
	@echo "  make pipeline SAMPLE=DEMO ASSEMBLER=spades"
	@echo "  make pipeline SAMPLE=DEMO ASSEMBLER=metaspades"
	@echo "  make pipeline SAMPLE=DEMO ANALYSIS_PROFILE=assembly-consensus"

setup_dirs:
	mkdir -p "$(WORK_PREFIX)data/raw" "$(WORK_PREFIX)data/cleaned" "$(WORK_PREFIX)data/host_removed" "$(WORK_PREFIX)data/assemblies"
	mkdir -p "$(WORK_PREFIX)results/qc" "$(WORK_PREFIX)results/blast" "$(WORK_PREFIX)results/phylogeny" "$(WORK_PREFIX)results/reports" "$(WORK_PREFIX)logs" "$(WORK_PREFIX)tmp"
	if [[ -z "$(GENEIN_WORK_ROOT)" ]]; then mkdir -p "$(REF_DIR)" docs; fi

deps:
	$(SCRIPTS_DIR)/ops/check_env.sh --install

fix-wsl:
	bash scripts/ops/fix_wsl.sh

test-env:
	ASSEMBLER="$(ASSEMBLER)" BLAST_DB="$(BLAST_DB)" BOWTIE2_INDEX="$(BOWTIE2_INDEX)" \
	$(SCRIPTS_DIR)/ops/check_env.sh

test-env-advanced:
	ASSEMBLER="$(ASSEMBLER)" BLAST_DB="$(BLAST_DB)" BOWTIE2_INDEX="$(BOWTIE2_INDEX)" \
	$(SCRIPTS_DIR)/ops/check_env.sh --advanced

ptv-fasta: setup_dirs
	$(SCRIPTS_DIR)/legacy/ptv/fetch_fasta.sh "$(REF_FASTA)"

ptv-fasta-legacy: ptv-fasta
	mkdir -p data
	ln -sf "$(abspath $(REF_FASTA))" data/$(DB)_db.fa
blastdb: ptv-fasta
	mkdir -p $(dir $(BLAST_DB))
	source "$(SCRIPTS_DIR)/lib/common.sh"
	DB_MARKER=""
	if [[ -s "$(BLAST_DB).nal" ]]; then DB_MARKER="$(BLAST_DB).nal"; elif [[ -s "$(BLAST_DB).nhr" ]]; then DB_MARKER="$(BLAST_DB).nhr"; fi
	if validate_blast_database "$(BLAST_DB)" && [[ -n "$$DB_MARKER" && "$$DB_MARKER" -nt "$(REF_FASTA)" ]]; then
		echo "[INFO] BLAST DB já existe e está atualizado: $(BLAST_DB)"
	else
		echo "[INFO] Gerando BLAST DB em $(BLAST_DB) a partir de $(REF_FASTA)"
		makeblastdb -in "$(REF_FASTA)" -dbtype nucl -out "$(BLAST_DB)"
	fi

bowtie2-index: ptv-fasta
	mkdir -p $(dir $(BOWTIE2_INDEX))
	if [[ -s "$(BOWTIE2_INDEX).1.bt2" && -s "$(BOWTIE2_INDEX).2.bt2" && -s "$(BOWTIE2_INDEX).3.bt2" && -s "$(BOWTIE2_INDEX).4.bt2" \
	      && -s "$(BOWTIE2_INDEX).rev.1.bt2" && -s "$(BOWTIE2_INDEX).rev.2.bt2" \
	      && "$(BOWTIE2_INDEX).1.bt2" -nt "$(REF_FASTA)" ]]; then
		echo "[INFO] Índice Bowtie2 já existe e está atualizado: $(BOWTIE2_INDEX)"
	else
		echo "[INFO] Gerando índice Bowtie2 em $(BOWTIE2_INDEX) a partir de $(REF_FASTA)"
		bowtie2-build "$(REF_FASTA)" "$(BOWTIE2_INDEX)"
	fi

pipeline:
	@PIPELINE_ARGS=(--sample "$(SAMPLE)"); \
	if [[ -n "$(ANALYSIS_PROFILE)" ]]; then PIPELINE_ARGS+=(--analysis-profile "$(ANALYSIS_PROFILE)"); fi; \
	if [[ -n "$(ASSEMBLER)" ]];       then PIPELINE_ARGS+=(--assembler "$(ASSEMBLER)"); fi; \
	if [[ -n "$(SPADES_PARAMS)" ]];   then PIPELINE_ARGS+=(--spades-params "$(SPADES_PARAMS)"); fi; \
	if [[ -n "$(BLAST_TASK)" ]];      then PIPELINE_ARGS+=(--blast-task "$(BLAST_TASK)"); fi; \
	if [[ -n "$(BLAST_WORD_SIZE)" ]]; then PIPELINE_ARGS+=(--blast-word-size "$(BLAST_WORD_SIZE)"); fi; \
	if [[ -n "$(BLAST_EVALUE)" ]];    then PIPELINE_ARGS+=(--blast-evalue "$(BLAST_EVALUE)"); fi; \
	if [[ -n "$(CONTIGS)" ]];         then PIPELINE_ARGS+=(--contigs "$(CONTIGS)" --skip-assembly); fi; \
	if [[ "$(SKIP_QC)" == "1" || "$(SKIP_QC)" == "true" ]]; then PIPELINE_ARGS+=(--skip-qc); fi; \
	BLAST_DB="$(BLAST_DB)" BOWTIE2_INDEX="$(BOWTIE2_INDEX)" \
	scripts/pipeline/run.sh "$${PIPELINE_ARGS[@]}"

db:
	DB="$(DB)" DB_QUERY="$(DB_QUERY)" $(PASS_REF_FASTA) \
	BLAST_DB="$(BLAST_DB)" BOWTIE2_INDEX="$(BOWTIE2_INDEX)" \
	$(SCRIPTS_DIR)/ops/db_manager.sh setup

db-blast:
	DB="$(DB)" DB_QUERY="$(DB_QUERY)" $(PASS_REF_FASTA) \
	BLAST_DB="$(BLAST_DB)" BOWTIE2_INDEX="$(BOWTIE2_INDEX)" \
	$(SCRIPTS_DIR)/ops/db_manager.sh setup-blast

sample-add:
	ARGS=(--id "$(ID)")
	if [[ -n "$(R1)" ]]; then ARGS+=(--r1 "$(R1)"); fi
	if [[ -n "$(R2)" ]]; then ARGS+=(--r2 "$(R2)"); fi
	if [[ -n "$(SINGLE)" ]]; then ARGS+=(--single "$(SINGLE)"); fi
	if [[ -n "$(COPY)" ]]; then ARGS+=(--copy); fi
	$(SCRIPTS_DIR)/ops/stage_sample.sh "$${ARGS[@]}"

filter-host:
	$(SCRIPTS_DIR)/pipeline/filter_host.sh $(SAMPLE)

test-velvet:
	$(SCRIPTS_DIR)/pipeline/assemblers/velvet.sh $(SAMPLE) $(KMER)

test-blast:
	$(SCRIPTS_DIR)/legacy/ptv/blast.sh $(SAMPLE) $(KMER)

smoke-test: test-env ptv-fasta-legacy blastdb bowtie2-index
	BLAST_DB="$(BLAST_DB)" BOWTIE2_INDEX="$(BOWTIE2_INDEX)" \
	$(SCRIPTS_DIR)/ops/smoke_test.sh

.PHONY: test test-engineering test-operational test-validation
test: test-engineering

test-engineering:
	bash scripts/tests/run_test_suite.sh engineering

test-operational:
	bash scripts/tests/run_test_suite.sh operational

.PHONY: test-tracks
test-tracks: test-validation

test-validation:
	python3 -m unittest scripts.tests.test_open_configuration
	python3 scripts/ops/validation_track_runner.py --track "$(TRACK)"


.PHONY: test-demo
test-demo:
	bash scripts/ops/verify_demo_outputs.sh "$(SAMPLE)"

clean:
	rm -rf run_T1 blastdb bowtie2 results logs tmp

clean-safe:
	@echo "[INFO] Removendo apenas temporários e cache (resultados preservados)."
	rm -rf run_T1 tmp
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

clean-all:
	@echo "AVISO: Este alvo remove resultados, bancos e logs gerados."
	@echo "       Dados em data/raw/ NÃO são apagados."
	@read -p "Tem certeza? Digite 'sim' para continuar: " confirm && [ "$$confirm" = "sim" ] || { echo "Cancelado."; exit 1; }
	rm -rf run_T1 blastdb bowtie2 results logs tmp
	@echo "[OK] Limpeza completa concluída."
# ---- PTV-enriched (Bowtie2 -> Velvet -> BLAST -> hits -> MAFFT addfragments) ----
KMER_PTV ?= 51

.PHONY: ptv-enriched-run
ptv-enriched-run: bowtie2-index blastdb
	STOP_AFTER_ALIGN=$(STOP_AFTER_ALIGN) ./scripts/legacy/ptv/enriched_run.sh "$(SAMPLE)" "$(KMER_PTV)"

# ---- Bundle WSL (micromamba) ----
BUNDLE_TAG ?= dev

.PHONY: bundle-wsl test-bundle-wsl test-all

bundle-wsl:
	bash scripts/ops/build_bundle_wsl.sh "$(BUNDLE_TAG)"

test-bundle-wsl:
	bash scripts/ops/test_bundle_wsl.sh "$(BUNDLE_TAG)"

test-all: test test-bundle-wsl


# Gera índice Bowtie2 do hospedeiro em ref/host/sus_scrofa_bt2*
# (A pipeline hoje procura por ref/host/sus_scrofa_bt2.1.bt2)
host-db:
	@mkdir -p ref/host data/ref/host
	@bash scripts/legacy/ptv/download_sus_scrofa.sh || true
	@HOST_FASTA="$$(ls -1 ref/host/*.fa ref/host/*.fasta ref/host/*.fa.gz ref/host/*.fasta.gz data/ref/host/*.fa data/ref/host/*.fasta data/ref/host/*.fa.gz data/ref/host/*.fasta.gz 2>/dev/null | head -n1)"; \
	if [[ -z "$$HOST_FASTA" ]]; then \
		echo "[ERRO] Nenhum FASTA do hospedeiro encontrado em ref/host/ ou data/ref/host/."; \
		echo "       Verifique scripts/legacy/ptv/download_sus_scrofa.sh (saída/paths)."; \
		exit 1; \
	fi; \
	if [[ "$$HOST_FASTA" == *.gz ]]; then \
		echo "[INFO] Descompactando FASTA do hospedeiro para ref/host/sus_scrofa.fa"; \
		gzip -cd "$$HOST_FASTA" > ref/host/sus_scrofa.fa; \
		HOST_FASTA=ref/host/sus_scrofa.fa; \
	else \
		if [[ "$$HOST_FASTA" != ref/host/* ]]; then \
			ln -sf "$$(realpath "$$HOST_FASTA")" ref/host/sus_scrofa.fa; \
			HOST_FASTA=ref/host/sus_scrofa.fa; \
		else \
			HOST_FASTA="$$HOST_FASTA"; \
		fi; \
	fi; \
	if [[ -s ref/host/sus_scrofa_bt2.1.bt2 && ref/host/sus_scrofa_bt2.1.bt2 -nt "$$HOST_FASTA" ]]; then \
		echo "[INFO] Índice do hospedeiro já existe e está atualizado: ref/host/sus_scrofa_bt2"; \
	else \
		echo "[INFO] Gerando índice Bowtie2 do hospedeiro em ref/host/sus_scrofa_bt2"; \
		bowtie2-build "$$HOST_FASTA" ref/host/sus_scrofa_bt2; \
	fi

check-env: test-env
	@:


.PHONY: demo ux run run-contigs report run-demo report-demo db-list db-setup

# Defaults (sobrescreva na linha de comando)
SAMPLE ?=
R1 ?=
R2 ?=
CONTIGS ?=

demo: ptv-fasta
	python3 scripts/ops/make_demo_fastq.py --ref "$(REF_FASTA)" --outdir data/raw --sample DEMO --pairs 2000 --len 150 --insert 150

PORT ?= 8000

ux:
	python3 scripts/ux_dashboard.py --host 127.0.0.1 --port $(PORT) $(UX_ARGS)

db-list:
	DB="$(DB)" scripts/ops/db_manager.sh list

db-setup:
	DB="$(DB)" DB_QUERY="$(DB_QUERY)" $(PASS_REF_FASTA) \
	BLAST_DB="$(BLAST_DB)" BOWTIE2_INDEX="$(BOWTIE2_INDEX)" \
	scripts/ops/db_manager.sh setup

run:
	@if [[ -z "$(SAMPLE)" || -z "$(R1)" || -z "$(R2)" ]]; then \
	  echo "Uso: make run SAMPLE=<id> R1=<R1.fastq.gz> R2=<R2.fastq.gz> [DB=ptv] [ASSEMBLER=velvet|spades|metaspades]"; \
	  exit 2; \
	fi
	$(MAKE) sample-add ID="$(SAMPLE)" R1="$(R1)" R2="$(R2)" $(if $(COPY),COPY=1,)
	$(MAKE) db DB="$(DB)"
	$(MAKE) pipeline SAMPLE="$(SAMPLE)" DB="$(DB)" \
	  $(if $(ASSEMBLER),ASSEMBLER="$(ASSEMBLER)",) \
	  $(if $(SPADES_PARAMS),SPADES_PARAMS="$(SPADES_PARAMS)",) \
	  $(if $(BLAST_TASK),BLAST_TASK="$(BLAST_TASK)",) \
	  $(if $(BLAST_WORD_SIZE),BLAST_WORD_SIZE="$(BLAST_WORD_SIZE)",) \
	  $(if $(BLAST_EVALUE),BLAST_EVALUE="$(BLAST_EVALUE)",)

run-contigs:
	@if [[ -z "$(SAMPLE)" || -z "$(CONTIGS)" ]]; then \
	  echo "Uso: make run-contigs SAMPLE=<id> CONTIGS=<contigs.fa> DB=$(DB) [ASSEMBLER=velvet|spades|metaspades] [SPADES_PARAMS=...] [BLAST_TASK=blastn|blastn-short] [BLAST_WORD_SIZE=...] [BLAST_EVALUE=...]"; \
	  exit 2; \
	fi
	$(MAKE) db DB="$(DB)"
	$(MAKE) pipeline SAMPLE="$(SAMPLE)" DB="$(DB)" CONTIGS="$(CONTIGS)" \
	  $(if $(ASSEMBLER),ASSEMBLER="$(ASSEMBLER)",) \
	  $(if $(SPADES_PARAMS),SPADES_PARAMS="$(SPADES_PARAMS)",) \
	  $(if $(BLAST_TASK),BLAST_TASK="$(BLAST_TASK)",) \
	  $(if $(BLAST_WORD_SIZE),BLAST_WORD_SIZE="$(BLAST_WORD_SIZE)",) \
	  $(if $(BLAST_EVALUE),BLAST_EVALUE="$(BLAST_EVALUE)",)

report:
	@if [[ -z "$(SAMPLE)" ]]; then \
	  echo "Uso: make report SAMPLE=<id>"; \
	  exit 2; \
	fi
	@REPORT_SUMMARY="results/reports/$(SAMPLE)_summary.md"; \
	REPORT_LEGACY="results/reports/$(SAMPLE).report.md"; \
	if [[ -f "$$REPORT_SUMMARY" ]]; then \
	  REPORT="$$REPORT_SUMMARY"; \
	elif [[ -f "$$REPORT_LEGACY" ]]; then \
	  REPORT="$$REPORT_LEGACY"; \
	else \
	  echo "Relatório não encontrado. Rode make run-demo ou make pipeline SAMPLE=<id>."; \
	  exit 1; \
	fi; \
	echo "[INFO] Abrindo relatório: $$REPORT"; \
	ls -lh "$$REPORT"
	@echo "==== REPORT (head) ===="
	@REPORT_SUMMARY="results/reports/$(SAMPLE)_summary.md"; \
	REPORT_LEGACY="results/reports/$(SAMPLE).report.md"; \
	if [[ -f "$$REPORT_SUMMARY" ]]; then \
	  REPORT="$$REPORT_SUMMARY"; \
	else \
	  REPORT="$$REPORT_LEGACY"; \
	fi; \
	sed -n '1,200p' "$$REPORT"
	@echo "======================="

run-demo:
	@$(MAKE) demo
	@$(MAKE) db DB=ptv
	@$(MAKE) pipeline SAMPLE=DEMO DB=ptv
	@if [[ -f "results/reports/DEMO_summary.md" ]]; then \
	  $(MAKE) report SAMPLE=DEMO; \
	else \
	  echo "[INFO] Relatório DEMO ainda não encontrado em results/reports/DEMO_summary.md"; \
	fi

report-demo:
	@$(MAKE) report SAMPLE=DEMO

.PHONY: nohits run-nohits
nohits:
	python3 scripts/ops/make_demo_fastq.py --random --outdir data/raw --sample nohits --pairs 1000 --len 150 --insert 300

run-nohits:
	@$(MAKE) nohits
	@$(MAKE) db DB=ptv
	@$(MAKE) pipeline SAMPLE=nohits DB=ptv

benchmark-demo:
	python3 scripts/ops/benchmark_preliminar.py --samples DEMO --assemblers velvet,metaspades --db $(DB)
