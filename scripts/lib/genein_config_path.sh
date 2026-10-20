#!/usr/bin/env bash
# Resolve picornavirus.env outside the source tree when the user has a work
# directory. Do not enable set -e here; callers keep their own shell options.

genein_user_config_file() {
  if [[ -n "${GENEIN_CONFIG_FILE:-}" ]]; then
    printf '%s\n' "${GENEIN_CONFIG_FILE}"
    return 0
  fi
  if [[ -n "${GENEIN_WORK_ROOT:-}" && "${GENEIN_WORK_ROOT}" == /* && -d "${GENEIN_WORK_ROOT}" ]]; then
    printf '%s\n' "${GENEIN_WORK_ROOT}/config/picornavirus.env"
    return 0
  fi
  if [[ -n "${HOME:-}" ]]; then
    printf '%s\n' "${HOME}/.gene-in/config/picornavirus.env"
    return 0
  fi
  printf '%s\n' "${REPO_ROOT}/config/picornavirus.env"
}

# Scratch and locks stay in the work directory when one was requested.
# Otherwise they stay out of the source tree, so a test run does not create tmp/.
genein_scratch_dir() {
  if [[ -n "${GENEIN_WORK_ROOT:-}" && "${GENEIN_WORK_ROOT}" == /* && -d "${GENEIN_WORK_ROOT}" ]]; then
    printf '%s\n' "${GENEIN_WORK_ROOT}/tmp"
    return 0
  fi
  if [[ -n "${HOME:-}" ]]; then
    printf '%s\n' "${HOME}/.gene-in/tmp"
    return 0
  fi
  printf '%s\n' "${TMPDIR:-/tmp}/gene-in-locks"
}

genein_user_log_dir() {
  if [[ -n "${GENEIN_WORK_ROOT:-}" && "${GENEIN_WORK_ROOT}" == /* && -d "${GENEIN_WORK_ROOT}" ]]; then
    printf '%s\n' "${GENEIN_WORK_ROOT}/logs"
    return 0
  fi
  if [[ -n "${HOME:-}" ]]; then
    printf '%s\n' "${HOME}/.gene-in/logs"
    return 0
  fi
  printf '%s\n' "${TMPDIR:-/tmp}/gene-in-logs"
}

# Write by others (last permission digit 2, 3, 6 or 7). Group write, such as
# the 0664 that umask 002 produces, is not refused. Source files are not checked.
genein_config_writable_by_others() {
  local path="$1"
  local mode other
  mode="$(stat -c %a "${path}" 2>/dev/null || stat -f %OLp "${path}")"
  other="${mode: -1}"
  case "${other}" in
    2|3|6|7) return 0 ;;
  esac
  return 1
}

# Read path. GENEIN_CONFIG_FILE is exclusive even when the file is missing.
# Then an existing $GENEIN_WORK_ROOT/config/picornavirus.env, then
# ~/.gene-in/config/picornavirus.env, then the source file, then config.env.
# A work-root file writable by others is refused (exit 2); the search does
# not fall through to another file. Group write is accepted.
genein_resolve_config_file() {
  local work_file home_file repo_file legacy
  if [[ -n "${GENEIN_CONFIG_FILE:-}" ]]; then
    printf '%s\n' "${GENEIN_CONFIG_FILE}"
    return 0
  fi
  if [[ -n "${GENEIN_WORK_ROOT:-}" && "${GENEIN_WORK_ROOT}" == /* && -d "${GENEIN_WORK_ROOT}" ]]; then
    work_file="${GENEIN_WORK_ROOT}/config/picornavirus.env"
    if [[ -f "${work_file}" ]]; then
      if genein_config_writable_by_others "${work_file}"; then
        printf 'picornavirus.env no diretório de trabalho é gravável por outros: %s\n' "${work_file}" >&2
        return 2
      fi
      printf '%s\n' "${work_file}"
      return 0
    fi
  fi
  if [[ -n "${HOME:-}" ]]; then
    home_file="${HOME}/.gene-in/config/picornavirus.env"
    if [[ -f "${home_file}" ]]; then
      printf '%s\n' "${home_file}"
      return 0
    fi
  fi
  repo_file="${REPO_ROOT}/config/picornavirus.env"
  if [[ -f "${repo_file}" ]]; then
    printf '%s\n' "${repo_file}"
    return 0
  fi
  legacy="${REPO_ROOT}/config.env"
  if [[ -f "${legacy}" ]]; then
    printf '%s\n' "${legacy}"
    return 0
  fi
  genein_user_config_file
}

# BLAST prefix. $1 is the database name. $2, when set, is BLAST_DB from the
# winning config and wins outright. Otherwise the first non-empty
# *.db-manifest.json wins: work directory, ~/.gene-in, then the source tree.
genein_resolve_blast_db() {
  local db="${1:-}"
  local configured="${2:-}"
  local manifest
  if [[ -n "${configured}" ]]; then
    printf '%s\n' "${configured}"
    return 0
  fi
  if [[ -n "${GENEIN_WORK_ROOT:-}" && "${GENEIN_WORK_ROOT}" == /* && -d "${GENEIN_WORK_ROOT}" ]]; then
    manifest="${GENEIN_WORK_ROOT}/blastdb/${db}.db-manifest.json"
    if [[ -s "${manifest}" ]]; then
      printf '%s\n' "${GENEIN_WORK_ROOT}/blastdb/${db}"
      return 0
    fi
  fi
  if [[ -n "${HOME:-}" ]]; then
    manifest="${HOME}/.gene-in/blastdb/${db}.db-manifest.json"
    if [[ -s "${manifest}" ]]; then
      printf '%s\n' "${HOME}/.gene-in/blastdb/${db}"
      return 0
    fi
  fi
  if [[ -n "${REPO_ROOT:-}" ]]; then
    manifest="${REPO_ROOT}/blastdb/${db}.db-manifest.json"
    if [[ -s "${manifest}" ]]; then
      printf '%s\n' "${REPO_ROOT}/blastdb/${db}"
      return 0
    fi
  fi
  if [[ -n "${GENEIN_WORK_ROOT:-}" && "${GENEIN_WORK_ROOT}" == /* ]]; then
    printf '%s\n' "${GENEIN_WORK_ROOT}/blastdb/${db}"
    return 0
  fi
  printf '%s\n' "blastdb/${db}"
}
