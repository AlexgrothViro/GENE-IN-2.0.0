#!/usr/bin/env bash
# =============================================================================
# check_env.sh — Diagnóstico e Validação Completa do Ambiente Gene-In
# =============================================================================
# Realiza testes exaustivos e automatizados de caminhos, executáveis, versões e
# bancos de dados necessários tanto para o pipeline básico (Velvet/SPAdes/BLAST/Bowtie2)
# quanto para as análises filogenéticas avançadas (MAFFT/FastTree/IQ-TREE).
# =============================================================================
set -euo pipefail
DB="${DB:-ptv}"

INCOMING_DB="${DB:-}"
INCOMING_BLAST_DB="${BLAST_DB:-}"
INCOMING_ASSEMBLER="${ASSEMBLER:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_ROOT/.." && pwd)"
# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"

# Quando o Gene-In foi instalado via bundle/micromamba, as ferramentas de
# bioinformatica vivem em um ambiente isolado e nao necessariamente no PATH global.
detect_genein_env_bin() {
  local candidates=()

  if [[ -n "${GENEIN_ENV_DIR:-}" ]]; then
    [[ -x "${GENEIN_ENV_DIR}/bin/python" ]] || {
      echo "[ERRO] Ambiente solicitado ausente: $GENEIN_ENV_DIR" >&2
      return 2
    }
    echo "${GENEIN_ENV_DIR}/bin"
    return 0
  fi
  if [[ -n "${GENEIN_BUNDLE_DIR:-}" ]]; then
    [[ -x "${GENEIN_BUNDLE_DIR}/env/bin/python" ]] || {
      echo "[ERRO] Bundle solicitado ausente: $GENEIN_BUNDLE_DIR" >&2
      return 2
    }
    echo "${GENEIN_BUNDLE_DIR}/env/bin"
    return 0
  fi

  candidates+=("${REPO_ROOT}/bundle/env/bin")

  if [[ "${REPO_ROOT}" == "/opt/genein" ]]; then
    candidates+=("/opt/genein/bundle/env/bin")
  fi

  if [[ -n "${HOME:-}" ]]; then
    candidates+=("${HOME}/.gene-in-bundle/env/bin")
  fi

  local dir
  for dir in "${candidates[@]}"; do
    if [[ -d "$dir" && ( -x "$dir/python" || -x "$dir/python3" ) ]]; then
      echo "$dir"
      return 0
    fi
  done

  return 1
}

GENEIN_ENV_BIN="$(detect_genein_env_bin)" || {
  env_status=$?
  [[ "$env_status" == 1 ]] || exit "$env_status"
}
if [[ -n "$GENEIN_ENV_BIN" ]]; then
  export PATH="$GENEIN_ENV_BIN:$PATH"
  GENEIN_ENV_DIR="$(dirname "$GENEIN_ENV_BIN")"
  export GENEIN_ENV_DIR
fi

# shellcheck disable=SC1091
source "${SCRIPTS_ROOT}/lib/genein_config_path.sh"
CONFIG_FILE="$(genein_resolve_config_file)"
if [[ -f "${CONFIG_FILE}" ]]; then
  # User config/generated metadata is resolved at runtime.
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

# Restaura as variáveis vindas do ambiente (sobrescrevendo o config.env)
if [[ -n "$INCOMING_DB" ]]; then
  DB="$INCOMING_DB"
fi
if [[ -n "$INCOMING_BLAST_DB" ]]; then
  BLAST_DB="$INCOMING_BLAST_DB"
fi
if [[ -n "$INCOMING_ASSEMBLER" ]]; then
  ASSEMBLER="$INCOMING_ASSEMBLER"
fi

if [[ -f "${SCRIPTS_ROOT}/lib/common.sh" ]]; then
  # Resolved from this checkout at runtime.
  # shellcheck disable=SC1091
  source "${SCRIPTS_ROOT}/lib/common.sh"
fi

usage() {
  echo "Uso: $0 [--install] [--advanced]" >&2
  echo "  --install    prepara o ambiente fixado com bundle/install_wsl.sh" >&2
  echo "  --advanced   exige a presença de todas as dependências filogenéticas avançadas" >&2
}

AUTO_INSTALL=0
CHECK_ADVANCED=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --install)
      AUTO_INSTALL=1
      shift
      ;;
    --advanced)
      CHECK_ADVANCED=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done


ASSEMBLER="${ASSEMBLER:-velvet}"
MISSING=0

# Função para extrair de forma robusta a versão de cada ferramenta
get_version() {
  local cmd="$1"
  local ver=""
  case "$cmd" in
    python3)
      ver="$(python3 --version 2>&1 | awk '{print $2}')"
      ;;
    blastn|makeblastdb)
      ver="$(blastn -version 2>/dev/null | head -n 1 | awk '{print $2}')"
      ;;
    bowtie2|bowtie2-build)
      ver="$(bowtie2 --version 2>/dev/null | head -n 1 | awk '{print $NF}')"
      ;;
    samtools)
      ver="$(samtools --version 2>/dev/null | head -n 1 | awk '{print $2}')"
      ;;
    mafft)
      ver="$(mafft --version 2>&1 | head -n 1 | awk '{print $2}')"
      ;;
    fasttree)
      ver="$(fasttree < /dev/null 2>&1 | head -n 1 | grep -oE "version [0-9.]+" | awk '{print $2}' || true)"
      if [[ -z "$ver" ]]; then
        ver="$(fasttree < /dev/null 2>&1 | head -n 2 | tail -n 1 | grep -oE "version [0-9.]+" | awk '{print $2}' || true)"
      fi
      ;;
    iqtree|iqtree2)
      ver="$("$cmd" --version 2>/dev/null | head -n 1 | grep -oE "version [0-9.]+" | awk '{print $2}' || true)"
      ;;
    spades.py|metaspades.py)
      ver="$("$cmd" --version 2>/dev/null | head -n 1 | grep -oE "[0-9.]+" | head -n 1 || true)"
      ;;
    perl)
      ver="$(perl -v 2>/dev/null | head -n 2 | tail -n 1 | grep -oE "v[0-9.]+" | sed 's/^v//' || true)"
      ;;
    velveth|velvetg)
      ver="$("$cmd" 2>&1 | head -n 1 | grep -oE "Version [0-9.]+" | awk '{print $2}' || true)"
      ;;
    dos2unix)
      ver="$(dos2unix --version 2>&1 | head -n 1 | awk '{print $2}')"
      ;;
    curl)
      ver="$(curl --version 2>/dev/null | head -n 1 | awk '{print $2}')"
      ;;
    esearch|efetch)
      ver="$("$cmd" -version 2>/dev/null | head -n 1 || true)"
      ;;
    gzip)
      ver="$(gzip --version 2>&1 | head -n 1 | awk '{print $2}')"
      ;;
    unzip)
      ver="$(unzip -v 2>&1 | head -n 1 | awk '{print $2}' || true)"
      ;;
    tar)
      ver="$(tar --version 2>&1 | head -n 1 | awk '{print $4}' || true)"
      ;;
    gcc)
      ver="$(gcc --version 2>/dev/null | head -n 1 | awk '{print $NF}')"
      ;;
    make)
      ver="$(make --version 2>/dev/null | head -n 1 | awk '{print $3}')"
      ;;
    git)
      ver="$(git --version 2>/dev/null | awk '{print $3}' || true)"
      ;;
    rsync)
      ver="$(rsync --version 2>/dev/null | head -n 1 | awk '{print $3}' || true)"
      ;;
    openssl)
      ver="$(openssl version 2>/dev/null | awk '{print $2}' || true)"
      ;;
    wget)
      ver="$(wget --version 2>/dev/null | head -n 1 | awk '{print $3}' || true)"
      ;;
    bzip2)
      ver="$(bzip2 --help 2>&1 | head -n 1 | grep -oE "version [0-9.]+" | awk '{print $2}' || true)"
      ;;
  esac

  if [[ -n "$ver" ]]; then
    echo " (v$ver)"
  else
    echo ""
  fi
}

echo "======================================================="
echo "   DIAGNÓSTICO E VALIDAÇÃO DE AMBIENTE — GENE-IN"
echo "======================================================="
echo "   Horário da checagem: $(date +'%Y-%m-%d %H:%M:%S %Z')"
echo "   Configuração ativa:  ASSEMBLER=$ASSEMBLER • DB=$DB"
if [[ -n "$GENEIN_ENV_BIN" ]]; then
  echo "   Ambiente Gene-In:    $GENEIN_ENV_DIR"
fi
echo "======================================================="
echo

# 1. Checagem de ferramentas básicas do compilador/sistema
echo "== [1/6] Utilitários Básicos do Sistema =="
SYSTEM_UTILS=(bash gcc make dos2unix python3 git)
for cmd in "${SYSTEM_UTILS[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then
    path=$(command -v "$cmd")
    ver=$(get_version "$cmd")
    printf "  [OK] %-12s encontrado em %s%s\n" "$cmd" "$path" "$ver"
  else
    echo "  [FALTA] $cmd não encontrado no PATH! (Obrigatório). Ação: bash bundle/install_wsl.sh"
    MISSING=1
  fi
done
echo

# 2. Checagem de motores de busca e mapeamento
echo "== [2/6] Motores de Busca e Alinhamento Global =="
ALIGN_UTILS=(blastn makeblastdb bowtie2 bowtie2-build samtools)
for cmd in "${ALIGN_UTILS[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then
    path=$(command -v "$cmd")
    ver=$(get_version "$cmd")
    printf "  [OK] %-12s encontrado em %s%s\n" "$cmd" "$path" "$ver"
  else
    echo "  [FALTA] $cmd não encontrado no PATH! (Obrigatório)"
    MISSING=1
  fi
done
echo

# 3. Checagem dos Montadores (Assemblers) instalados
echo "== [3/6] Montadores Genômicos =="
VELVET_FOUND=0
SPADES_FOUND=0

# Verifica Velvet
if command -v velveth >/dev/null 2>&1 && command -v velvetg >/dev/null 2>&1; then
  VELVET_FOUND=1
  path_vh=$(command -v velveth)
  ver_vh=$(get_version "velveth")
  printf "  [OK] velvet       encontrado em %s%s\n" "$path_vh" "$ver_vh"
else
  echo "  [FALTA] velvet (velveth/velvetg) não está disponível."
fi

# Verifica SPAdes
if command -v spades.py >/dev/null 2>&1; then
  SPADES_FOUND=1
  path_sp=$(command -v spades.py)
  ver_sp=$(get_version "spades.py")
  printf "  [OK] SPAdes       encontrado em %s%s\n" "$path_sp" "$ver_sp"
else
  echo "  [FALTA] SPAdes (spades.py) não está disponível."
fi

# Verifica metaSPAdes
METASPADES_FOUND=0
if command -v metaspades.py >/dev/null 2>&1; then
  METASPADES_FOUND=1
  path_ms=$(command -v metaspades.py)
  ver_ms=$(get_version "metaspades.py")
  printf "  [OK] metaSPAdes   encontrado em %s%s\n" "$path_ms" "$ver_ms"
elif [[ $SPADES_FOUND -eq 1 ]]; then
  METASPADES_FOUND=1
  printf "  [OK] metaSPAdes   disponível via spades.py --meta%s\n" "$ver_sp"
else
  echo "  [FALTA] metaSPAdes não está disponível (nem metaspades.py nem spades.py)."
fi

# Valida se o montador ativo na configuração está presente
if [[ "$ASSEMBLER" == "velvet" && $VELVET_FOUND -eq 0 ]]; then
  echo "  [CRÍTICO] Velvet está configurado como ASSEMBLER ativo, mas não está instalado!"
  MISSING=1
elif [[ "$ASSEMBLER" == "spades" && $SPADES_FOUND -eq 0 ]]; then
  echo "  [CRÍTICO] SPAdes está configurado como ASSEMBLER ativo, mas não está instalado!"
  MISSING=1
elif [[ "$ASSEMBLER" == "metaspades" && $METASPADES_FOUND -eq 0 ]]; then
  echo "  [CRÍTICO] metaSPAdes está configurado como ASSEMBLER ativo, mas não está instalado!"
  MISSING=1
elif [[ "$ASSEMBLER" == "builder" ]]; then
  if python3 "${REPO_ROOT}/scripts/pipeline/assemblers/builder_adapter.py" check; then
    echo "  [OK] Gene-In Builder 0.4.0 disponível (opcional)."
  else
    echo "  [CRÍTICO] ASSEMBLER=builder, mas o pacote genein-builder nao esta instalado."
    echo "            bash bundle/install_builder.sh"
    MISSING=1
  fi
fi

# Garante que pelo menos um montador do caminho padrao esteja presente.
# builder e opcional e nao substitui essa exigencia quando outro montador esta ativo.
if [[ "$ASSEMBLER" != "builder" && $VELVET_FOUND -eq 0 && $SPADES_FOUND -eq 0 && $METASPADES_FOUND -eq 0 ]]; then
  echo "  [CRÍTICO] Nenhum montador genômico (Velvet, SPAdes ou metaSPAdes) está disponível no sistema!"
  MISSING=1
fi
echo

# 4. Checagem do módulo de Análise Filogenética Avançada
echo "== [4/6] Ferramentas Avançadas (Filogenia e Validação) =="
ADVANCED_CMDS=(mafft fasttree)
ADV_MISSING=0

for cmd in "${ADVANCED_CMDS[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then
    path=$(command -v "$cmd")
    ver=$(get_version "$cmd")
    printf "  [OK] %-12s encontrado em %s%s\n" "$cmd" "$path" "$ver"
  else
    echo "  [AVISO] $cmd não encontrado no PATH. (Necessário para a aba Análise Avançada)"
    ADV_MISSING=1
  fi
done

IQTREE_FOUND=0
IQTREE_CANDIDATES=(iqtree iqtree2)
for cmd in "${IQTREE_CANDIDATES[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then
    path=$(command -v "$cmd")
    ver=$(get_version "$cmd")
    printf "  [OK] %-12s encontrado em %s%s\n" "$cmd" "$path" "$ver"
    IQTREE_FOUND=1
    break
  fi
done

if [[ $IQTREE_FOUND -eq 0 ]]; then
  echo "  [AVISO] iqtree ou iqtree2 não encontrado. (Necessário para a aba Análise Avançada)"
  ADV_MISSING=1
fi

# Se foi exigido verificação avançada restrita, falhar o check
if [[ $CHECK_ADVANCED -eq 1 && $ADV_MISSING -ne 0 ]]; then
  echo "  [CRÍTICO] Algumas dependências avançadas de filogenia estão ausentes e o modo --advanced está ativo."
  MISSING=1
fi
echo

# 5. Utilitários Opcionais e Ferramentas de Download NCBI (EDirect)
echo "== [5/6] Utilitários Complementares (Download NCBI e Uploads) =="
EXTRA_UTILS=(gzip unzip tar bzip2 rsync curl wget openssl)
for cmd in "${EXTRA_UTILS[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then
    path=$(command -v "$cmd")
    ver=$(get_version "$cmd")
    printf "  [OK] %-12s encontrado em %s%s\n" "$cmd" "$path" "$ver"
  else
    if [[ "$cmd" == "rsync" ]]; then
      echo "  [AVISO] rsync ausente. Ele só entra na cópia para /opt feita por install_linux.sh e no fallback de genoma de hospedeiro quando datasets não está disponível. A análise, o upload do painel e bundle/install_wsl.sh não usam rsync."
    else
      echo "  [AVISO] Utilitário $cmd ausente. (Pode causar limitações em uploads/downloads)"
    fi
  fi
done

# EDirect check (NCBI Entrez Direct e Perl)
if command -v esearch >/dev/null 2>&1 && command -v efetch >/dev/null 2>&1; then
  path_es=$(command -v esearch)
  printf "  [OK] EDirect       encontrado em %s (esearch/efetch)\n" "$path_es"
  if command -v perl >/dev/null 2>&1; then
    path_perl=$(command -v perl)
    ver_perl=$(get_version "perl")
    printf "       [OK] Perl (obrigatório para EDirect) encontrado em %s%s\n" "$path_perl" "$ver_perl"
  else
    echo "       [CRÍTICO] EDirect está instalado, mas o 'perl' está ausente! O EDirect não irá funcionar."
    MISSING=1
  fi
else
  echo "  [AVISO] EDirect ausente (esearch/efetch) - necessário se desejar baixar DBs do NCBI via plataforma."
  echo "          Para instalar: sudo apt update && sudo apt install -y ncbi-entrez-direct"
fi
echo

# ─────────────────────────────────────────────────
# Auditoria de Recursos do Sistema
# ─────────────────────────────────────────────────
echo "== [6/6] Auditoria de Recursos do Sistema =="

# Checagem de RAM
if [[ -f /proc/meminfo ]]; then
  total_mem=$(grep MemTotal /proc/meminfo | awk '{print $2}')
  free_mem=$(awk '/^MemAvailable:/ {print $2; found=1} END {if (!found) exit 1}' /proc/meminfo) || \
    free_mem=$(awk '/^MemFree:/ {print $2}' /proc/meminfo)
  total_gb=$(echo "scale=1; $total_mem / 1024 / 1024" | bc -l 2>/dev/null || awk "BEGIN {print $total_mem/1024/1024}")
  free_gb=$(echo "scale=1; $free_mem / 1024 / 1024" | bc -l 2>/dev/null || awk "BEGIN {print $free_mem/1024/1024}")
  printf "  [INFO] Memória RAM Total: %.1f GiB (Disponível: %.1f GiB)\n" "$total_gb" "$free_gb"
  if (( $(echo "$total_gb < 8.0" | bc -l 2>/dev/null || awk "BEGIN {print ($total_gb < 8.0)?1:0}") )); then
    echo "         [AVISO] Pouca memória RAM total detectada (< 8.0 GB). O SPAdes/metaSPAdes pode falhar em amostras complexas."
  fi
else
  echo "  [INFO] Não foi possível ler /proc/meminfo para checar RAM."
fi

# Checagem de Espaço em Disco
if command -v df >/dev/null 2>&1; then
  free_disk_kb=$(df -k . | tail -n 1 | awk '{print $4}')
  free_disk_gb=$(echo "scale=1; $free_disk_kb / 1024 / 1024" | bc -l 2>/dev/null || awk "BEGIN {print $free_disk_kb/1024/1024}")
  printf "  [INFO] Espaço em Disco Disponível: %.1f GB\n" "$free_disk_gb"
  # 45 GB: porte da AMOSTRA01 no reteste (300.000 pares, cerca de 30 milhões de HSPs).
  # O aviso antigo de 5 GB não cobria essa amostra. Ver docs/correcoes-reteste-b3.md.
  if (( $(echo "$free_disk_gb < 45.0" | bc -l 2>/dev/null || awk "BEGIN {print ($free_disk_gb < 45.0)?1:0}") )); then
    echo "         [AVISO] Espaço em disco baixo (< 45 GB livres). Para uma amostra completa no porte medido (300.000 pares e cerca de 30 milhões de HSPs), deixe pelo menos 45 GB livres no mesmo disco."
  fi
else
  echo "  [INFO] Não foi possível verificar o espaço em disco livre."
fi

# Checagem de integridade de bibliotecas Python
if command -v python3 >/dev/null 2>&1; then
  if python3 -c "import sys, argparse, csv, pathlib, json, logging, threading, http.server, urllib.parse, subprocess" >/dev/null 2>&1; then
    echo "  [OK] Bibliotecas Python padrão verificadas e íntegras."
  else
    echo "  [AVISO] Algumas bibliotecas Python padrão parecem ausentes ou corrompidas!"
  fi
fi

# Evidence V2 usa UMI-tools no mesmo Python que executa o pipeline quando UMI está ativo.
if [[ "${EVIDENCE_V2:-false}" =~ ^(true|1|yes)$ ]] && command -v python3 >/dev/null 2>&1; then
  if [[ "${EVIDENCE_UMI_MODE:-none}" != "none" ]] && ! python3 -c "import umi_tools" >/dev/null 2>&1; then
    echo "  [AVISO] Evidence V2: UMI-tools ausente; suporte UMI será bloqueado explicitamente."
  fi
fi

# Checagem de montagem de sistema WSL
mount_type=$(mount | grep "on /mnt/" | head -n 1 || true)
if [[ -n "$mount_type" ]]; then
  if echo "$mount_type" | grep -q "drvfs"; then
    echo "  [INFO] Executando em montagem NTFS/drvfs. Symlinks nativos do Linux podem ter restrições."
  fi
fi
echo

# ─────────────────────────────────────────────────
# Validação de Arquivos Locais de Referência e BLAST DBs
# ─────────────────────────────────────────────────
echo "== Validação de Arquivos Físicos e Bancos Locais =="
REF_FASTA="${REF_FASTA:-data/ref/${DB}.fa}"
LEGACY_FASTA="data/${DB}_db.fa"
DIAG_BLAST_DB="${BLAST_DB:-blastdb/${DB}}"

# Damaged index files can make blastdbcmd crash (SIGSEGV/SIGBUS) instead of
# returning an error. A crash, or an error on files that exist, means a damaged
# database, never one that is merely not prepared yet. Hashes are left to the
# pipeline's DATABASE_PREFLIGHT; this only checks readability, manifest JSON and sizes.
BLAST_DB_FAILURE=""
inspect_blast_database() {
  local database="$1" status=0 present=0 file detail
  for file in "$database".n* "$database".db-manifest.json; do
    if [[ -e "$file" ]]; then
      present=1
      break
    fi
  done
  command -v blastdbcmd >/dev/null 2>&1 || return 1
  { validate_blast_database "$database"; } 2>/dev/null || status=$?
  if (( status > 128 )); then
    BLAST_DB_FAILURE="blastdbcmd encerrou com o sinal SIG$(kill -l $((status - 128)) 2>/dev/null || echo "$((status - 128))") ao ler o banco / blastdbcmd crashed while reading the database"
    return 1
  fi
  if (( status != 0 )); then
    if (( present )); then
      BLAST_DB_FAILURE="blastdbcmd não conseguiu ler os arquivos do banco (código ${status}) / blastdbcmd could not read the database files (exit ${status})"
    fi
    return 1
  fi
  if [[ -e "${database}.db-manifest.json" ]] && command -v python3 >/dev/null 2>&1; then
    if ! detail="$(python3 "${SCRIPTS_ROOT}/evidence/verify_blast_database_manifest.py" "$database" --sizes-only 2>&1 >/dev/null)"; then
      BLAST_DB_FAILURE="${detail#\[FATAL\] }"
      return 1
    fi
  fi
  return 0
}

BLAST_DB_READY=0
if inspect_blast_database "$DIAG_BLAST_DB"; then
  BLAST_DB_READY=1
fi
if [[ -n "$BLAST_DB_FAILURE" ]]; then
  echo "  [ERRO] Banco BLAST inválido ou corrompido em ${DIAG_BLAST_DB} / Invalid or corrupt BLAST database."
  echo "         ${BLAST_DB_FAILURE}"
  echo "         Ação: reconstrua o banco e o manifesto (bash bundle/run.sh db DB=${DB}) ou informe outro prefixo preparado."
  echo "         Action: rebuild the database and its manifest, or point to another prepared prefix."
fi

if [[ $BLAST_DB_READY -eq 1 ]]; then
  echo "  [OK] Banco explícito pronto; FASTA local adicional não é obrigatório."
elif [[ -s "$REF_FASTA" ]]; then
  echo "  [OK] FASTA de referência principal ativo: $REF_FASTA"
  if [[ -e "data/ref/ptv_db.fa" && "$REF_FASTA" == "data/ref/ptv_db.fa" && ! -e "$LEGACY_FASTA" ]]; then
    mkdir -p data
    ln -sf "$(resolve_path "$REF_FASTA")" "$LEGACY_FASTA"
    echo "       [INFO] Symlink legado criado: $LEGACY_FASTA -> $REF_FASTA"
  fi
elif [[ -s "$LEGACY_FASTA" ]]; then
  echo "  [OK] FASTA de referência legado ativo: $LEGACY_FASTA"
elif compgen -G "data/ref/*.fa" >/dev/null; then
  echo "  [OK] FASTAs alternativos encontrados no diretório data/ref/:"
  printf '       - %s\n' data/ref/*.fa
else
  echo "  [ATENÇÃO] FASTA de referência ausente em data/ref/*.fa."
  echo "            Prepare o banco: bash bundle/run.sh db DB=${DB}"
fi

# BLAST Index Check
if [[ -n "${BLAST_DB:-}" ]]; then
  echo "  [INFO] Caminho BLAST_DB ativo: $BLAST_DB"
  if [[ -n "$BLAST_DB_FAILURE" ]]; then
    echo "  [ERRO] Índices BLAST presentes, mas ilegíveis; veja o erro acima."
  elif [[ $BLAST_DB_READY -eq 0 ]]; then
    if [[ -s "$REF_FASTA" || -s "data/ref/${DB}.fa" || -s "data/${DB}_db.fa" ]]; then
      echo "  [INFO] BLAST_DB ainda não preparado. Execute: bash bundle/run.sh db DB=${DB}"
    else
      echo "  [AVISO] Caminho BLAST_DB configurado ($BLAST_DB), mas índices estão ausentes e a referência não foi encontrada."
      echo "          Execute: bash bundle/run.sh db DB=${DB}"
    fi
  else
    echo "  [OK] Índices BLAST encontrados e validados."
  fi
else
  # BLAST_DB não foi passado explicitamente no ambiente
  # Verifica o prefixo padrão pela interface do BLAST+, aceitando aliases v5.
  if [[ $BLAST_DB_READY -eq 1 ]]; then
    echo "  [OK] Índices BLAST autodetectados no caminho padrão: $DIAG_BLAST_DB"
  elif [[ -n "$BLAST_DB_FAILURE" ]]; then
    echo "  [ERRO] Índices BLAST presentes no caminho padrão, mas ilegíveis; veja o erro acima."
  else
    if [[ -s "$REF_FASTA" || -s "data/ref/${DB}.fa" || -s "data/${DB}_db.fa" ]]; then
      echo "  [INFO] BLAST_DB ainda não encontrado. Execute: bash bundle/run.sh db DB=${DB}"
    else
      echo "  [AVISO] BLAST_DB não configurado e referência não encontrada. Execute: bash bundle/run.sh db DB=${DB}"
    fi
  fi
fi
echo

# ─────────────────────────────────────────────────
# Execução da Ação Corretiva ou Finalização
# ─────────────────────────────────────────────────
if [[ $MISSING -ne 0 ]]; then
  if [[ $AUTO_INSTALL -eq 1 ]]; then
    echo "[AÇÃO] Preparando pré-requisitos e ambiente científico fixado."
    if bash "${REPO_ROOT}/bundle/install_wsl.sh"; then
      echo
      echo "[INFO] Reavaliando o ambiente de execução..."
      exec "$0"
    else
      echo "ERRO: A instalação de dependências falhou." >&2
      exit 1
    fi
  fi
  echo "-------------------------------------------------------"
  echo "⚠️ FALHA NO DIAGNÓSTICO: Alguns utilitários obrigatórios estão ausentes." >&2
  echo "Sugestão: prepare os pré-requisitos e o ambiente científico fixado:" >&2
  echo "          bash bundle/install_wsl.sh" >&2
  echo "-------------------------------------------------------"
  exit 1
fi

# Registro de versões de software
VERSIONS_DIR="$(genein_user_log_dir)"
VERSIONS_FILE="${VERSIONS_DIR}/software_versions.txt"
mkdir -p "$VERSIONS_DIR"
{
  echo "# Software versions - Gene-In Platform"
  echo "# Generated at: $(date +'%Y-%m-%d %H:%M:%S %Z')"
  echo
  for cmd in "${SYSTEM_UTILS[@]}" "${ALIGN_UTILS[@]}" velveth velvetg spades.py metaspades.py perl "${ADVANCED_CMDS[@]}" "${IQTREE_CANDIDATES[@]}" "${EXTRA_UTILS[@]}" esearch efetch; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ver=$(get_version "$cmd" | sed 's/^[ (]*//;s/[) ]*$//')
      [[ -n "$ver" ]] || ver="(versão não autodetectada)"
      printf "%s\t%s\n" "$cmd" "$ver"
    fi
  done
} > "$VERSIONS_FILE"

if [[ -n "$BLAST_DB_FAILURE" ]]; then
  echo "-------------------------------------------------------" >&2
  echo "⚠️ FALHA NO DIAGNÓSTICO: banco BLAST inválido ou manifesto corrompido." >&2
  echo "   Invalid or corrupt BLAST database or manifest. Do not treat this check as successful." >&2
  echo "   ${BLAST_DB_FAILURE}" >&2
  echo "   Ação: reconstrua o banco e o manifesto (bash bundle/run.sh db DB=${DB}) ou informe outro prefixo." >&2
  echo "   Action: rebuild the database and its manifest, or point to another prepared prefix." >&2
  echo "   Versões catalogadas em: $VERSIONS_FILE" >&2
  echo "-------------------------------------------------------" >&2
  exit 1
fi

echo "-------------------------------------------------------"
echo "✅ DIAGNÓSTICO CONCLUÍDO COM SUCESSO!"
echo "   Versões dos softwares catalogadas em: $VERSIONS_FILE"
echo "   Ferramentas verificadas. Confira o banco, o índice do hospedeiro e os recursos necessários antes da análise."
echo "-------------------------------------------------------"
exit 0
