#!/usr/bin/env bash

bt2_index_complete() {
  local prefix="$1"
  local extension="$2"
  local component

  for component in 1 2 3 4 rev.1 rev.2; do
    if [[ ! -s "${prefix}.${component}.${extension}" ]]; then
      return 1
    fi
  done
}

resolve_bt2_index() {
  local prefix="$1"
  if bt2_index_complete "$prefix" "bt2"; then
    echo "small"
    return 0
  fi
  if bt2_index_complete "$prefix" "bt2l"; then
    echo "large"
    return 0
  fi
  echo "none"
  return 1
}

validate_bt2_index() {
  local prefix="$1"
  local index_kind
  index_kind="$(resolve_bt2_index "$prefix" || true)"
  if [[ "$index_kind" == "none" ]]; then
    echo "Indice Bowtie2 do hospedeiro nao encontrado em ${prefix}. Esperado .bt2 ou .bt2l." >&2
    return 1
  fi
  if ! command -v bowtie2-inspect >/dev/null 2>&1; then
    echo "bowtie2-inspect nao encontrado no PATH. Verifique o ambiente Bowtie2." >&2
    return 1
  fi
  if ! bowtie2-inspect -s "$prefix" >/dev/null 2>&1; then
    echo "Indice Bowtie2 do hospedeiro encontrado (${index_kind}), mas nao esta legivel/integro: ${prefix}" >&2
    return 1
  fi
  echo "$index_kind"
}
