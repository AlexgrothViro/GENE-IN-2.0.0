"""Technical collection balance; never independent-template evidence."""
from __future__ import annotations


def render_collection_summary(manifest: dict) -> str:
    counts = manifest.get("routing_summary")
    if counts is None:
        return ""
    routes = counts["accepted_occurrences"]
    discarded = counts["discarded_occurrences"]
    lines = ["## Balanço de sequências coletadas", "",
             "Unidade: ocorrências de entrada, não templates independentes.", "",
             "| Destino/motivo | Sequências |", "|---|---:|",
             f"| Rota curta B0 (20–100 pb, perfis originais) | {routes['short_20_100']} |",
             f"| Rota longa (>100 pb, blastn word_size 11) | {routes['long_above_100']} |",
             f"| FASTA <20 pb, comportamento legado não validado | {routes['legacy_fasta_below_20']} |"]
    lines.extend(f"| Descartadas: {reason} | {count} |" for reason, count in discarded.items())
    lines += ["", f"Queries únicas após deduplicação exata: {counts['unique_queries']}; "
              f"ocorrências reunidas por sequência: {counts['merged_occurrences']}.",
              f"Ocorrências ESPECIFICIDADE_NAO_VALIDADA: {counts['restricted_occurrences']}.",
              "<20 pb em FASTQ: excluídas como em B0; decisão científica futura. "
              "FASTA <20 pb mantém a rota legada, sem validação de especificidade.",
              "IDs de read/par são proveniência, nunca suporte independente. "
              "Suporte exige o remapeamento original; sequências não são fatiadas nem aparadas.", ""]
    return "\n".join(lines)
