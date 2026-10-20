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

genein_resolve_config_file() {
  local user_file repo_file legacy
  user_file="$(genein_user_config_file)"
  if [[ -f "${user_file}" ]]; then
    printf '%s\n' "${user_file}"
    return 0
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
  printf '%s\n' "${user_file}"
}
