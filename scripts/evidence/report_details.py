"""Render denominator-explicit recovery and candidate tables from run artifacts."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

try:
    from .common import configure_csv_field_limit
except ImportError:
    from common import configure_csv_field_limit


def rows(path: Path) -> list[dict[str, str]]:
    return list(iter_rows(path))


def iter_rows(path: Path):
    if not path.is_file():
        return
    configure_csv_field_limit()
    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle, delimiter="\t")


def render_details(run_dir: str | Path, data: dict) -> str:
    root = Path(run_dir)
    support, coverage = iter_rows(root / "read_support.tsv"), iter_rows(root / "coverage.tsv")
    candidates = data.get("candidates", [])
    locus_tasks = {}
    locus_count = 0
    for row in iter_rows(root / "locus_evidence.tsv"):
        locus_count += 1
        locus_tasks.setdefault(row.get("locus_id"), row.get("task", ""))
    hsp_count = eligible_count = rejected_count = 0
    reason_counts = Counter()
    best_by_locus = {}
    hsp_path = root / "hsp_evidence.tsv"
    if hsp_path.is_file():
        with hsp_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                hsp_count += 1
                status = row.get("eligible", "").lower()
                if status == "true":
                    eligible_count += 1
                    locus = row.get("locus_id")
                    previous = best_by_locus.get(locus)
                    if previous is None or float(row.get("bitscore") or 0) > float(previous.get("bitscore") or 0):
                        best_by_locus[locus] = row
                elif status == "false":
                    rejected_count += 1
                    reason_counts[row.get("rejection_reason") or "UNSPECIFIED"] += 1
    wanted = {(best_by_locus.get(c.get("locus_id", ""), {}).get("qseqid", ""),
               c.get("reference_id"), locus_tasks.get(c.get("locus_id", ""), ""))
              for c in candidates}
    matched_queries = {}
    assembler_methods, qids, unique_sequences, accessions = set(), set(), set(), set()
    for row in iter_rows(root / "fragment_evidence.tsv"):
        for field, values in (("assembly_method", assembler_methods), ("qseqid", qids),
                              ("sequence_sha256", unique_sequences), ("sseqid", accessions)):
            if row.get(field):
                values.add(row[field])
        key = (row.get("qseqid"), row.get("sseqid"), row.get("task"))
        for match in (key, (key[0], key[1], "")):
            if match in wanted and match not in matched_queries:
                matched_queries[match] = {"qlen": row.get("qlen"),
                                          "query_covered_bp": row.get("query_covered_bp")}
    assembler_methods = sorted(assembler_methods)
    class_counts = Counter(row.get("candidate_class", "NOT_EVALUATED") for row in candidates)
    support_counts = Counter(row.get("support_status", "NOT_EVALUATED") for row in support)
    coverage_counts = Counter(
        "AVAILABLE" if row.get("breadth_1x") not in ("", None) else "NOT_EVALUATED"
        for row in coverage
    )
    artifact_refs = "`fragment_evidence.tsv`, `hsp_evidence.tsv`, `locus_evidence.tsv`, `competitive_hits.tsv`, `read_support.tsv` e `coverage.tsv`"
    lines = [
        "## Recuperação e avaliação posterior",
        "",
        "As contagens abaixo mantêm unidades distintas. Um identificador de query, uma sequência distinta, um HSP, um locus e um accession são unidades diferentes.",
        "",
        "| Etapa/unidade | Contagem | Estado ou definição |",
        "|---|---:|---|",
        f"| IDs de contigs/query recuperados em alinhamentos | {len(qids)} | qseqid distintos em `fragment_evidence.tsv` |",
        f"| Sequências distintas | {len(unique_sequences)} | hashes SHA-256 distintos entre fragmentos alinhados |",
        f"| HSPs | {hsp_count} | todos os HSPs na tabela; elegíveis: {eligible_count}, rejeitados: {rejected_count} |",
        f"| Loci | {locus_count} | linhas de `locus_evidence.tsv` |",
        f"| Accessions de referência | {len(accessions)} | sseqid distintos; não somar como genomas recuperados |",
        f"| Montador(es) registrado(s) | {', '.join(assembler_methods) if assembler_methods else 'NOT_RECORDED'} | campo `assembly_method` das queries alinhadas |",
        f"| Candidatos retidos para avaliação posterior | {len(candidates)} | seleção final: NÃO EXECUTADA neste classificador |",
        f"| Excluídos por gates de promoção | 0 | nenhum gate de promoção foi executado |",
        "",
        "| Classe de candidato | Contagem |",
        "|---|---:|",
    ]
    for label in ("EXPLORATORY_FRAGMENT", "LOCUS_CANDIDATE", "NOT_EVALUATED"):
        lines.append(f"| {label} | {class_counts.get(label, 0)} |")
    assembly_statuses = Counter(candidate.get("assembly_support", {}).get("status", "NOT_EVALUATED") for candidate in candidates)
    lines.extend(["", "| Suporte por reads | Loci | Cobertura por reads | Loci | Concordância entre montadores | Candidatos |", "|---|---:|---|---:|---|---:|"])
    support_names = sorted(support_counts) or ["NOT_EVALUATED"]
    coverage_names = sorted(coverage_counts) or ["NOT_EVALUATED"]
    for i in range(max(len(support_names), len(coverage_names))):
        left = support_names[i] if i < len(support_names) else ""
        right = coverage_names[i] if i < len(coverage_names) else ""
        assembly_name = sorted(assembly_statuses)[i] if i < len(assembly_statuses) else ""
        lines.append(f"| {left} | {support_counts.get(left, 0) if left else ''} | {right} | {coverage_counts.get(right, 0) if right else ''} | {assembly_name} | {assembly_statuses.get(assembly_name, 0) if assembly_name else ''} |")
    lines.extend(["", "HSPs rejeitados por regra:"])
    lines.extend(f"- `{rule}`: {count}" for rule, count in sorted(reason_counts.items()))
    if not reason_counts:
        lines.append("- Nenhum.")
    if data.get("scientific_revision"):
        lines.extend(["", "## Bases alinhadas únicas na referência", "",
                      "União de posições por referência/segmento, incluindo as duas orientações e todos os perfis de busca. Essas bases podem incluir alinhamentos espúrios; não representam bases virais de origem confirmada.", "",
                      "| Referência | Segmento | Bases alinhadas únicas | Estado |",
                      "|---|---|---:|---|"])
        for reference in data.get("reference_coverage", {}).get("by_reference", []):
            lines.append(f"| `{reference['reference_id']}` | {reference['segment']} | {reference['aligned_reference_bp']} | {reference['status']} |")
        lines.extend(["", "Qualificação científica dos candidatos: NOT_EVALUATED. Disponibilidade para revisão não é elegibilidade para confirmação.", "",
                      "| Candidato/locus | Taxon rotulado na referência | Atribuição no painel |",
                      "|---|---|---|"])
        for candidate in candidates:
            lines.append(f"| `{candidate.get('locus_id', '')}` | {candidate.get('taxon') or 'não informado'} | {candidate.get('taxonomic_status', 'NOT_EVALUATED')} |")
        lines.extend(["", "PANEL_TAXON_PREFERRED indica preferência entre os hits taxonômicos reportados no painel; não confirma espécie. AMBIGUOUS mantém a atribuição em revisão."])
    lines.extend(["", "## Detalhe por candidato/locus", "", "Identidade e comprimento vêm dos HSPs elegíveis associados ao locus. Cobertura de query = bases cobertas na query / comprimento da query. O candidato continua disponível para avaliação; a classe não é uma seleção final.", "", "| Locus | Query(s) | Referência/accession | Classe | Identidade % | Alinhamento máx. (bp) | Query: cobertas/tamanho | Cobertura da query | Especificidade | Suporte | Cobertura reads | Concordância de montagem |", "|---|---|---|---|---:|---:|---|---:|---|---|---|---|"])
    for candidate in candidates:
        locus_id = candidate.get("locus_id", "")
        best = best_by_locus.get(locus_id, {})
        best_qid = best.get("qseqid", "")
        locus_task = locus_tasks.get(locus_id, "")
        matched_query = matched_queries.get((best_qid, candidate.get("reference_id"), locus_task), {})
        qlen = int(matched_query.get("qlen") or 0)
        qcovered = int(matched_query.get("query_covered_bp") or 0)
        qcov = qcovered / qlen if qlen else 0.0
        lines.append(
            f"| `{locus_id}` | `{';'.join(candidate.get('query_ids', []))}` | `{candidate.get('reference_id', '')}` | {candidate.get('candidate_class', 'NOT_EVALUATED')} | {best.get('identity_pct', 'NA')} | {best.get('alignment_length', 'NA')} | {qcovered}/{qlen or 'NA'} | {qcov:.3f} | {candidate.get('specificity_status', 'NOT_EVALUATED')} | {candidate.get('support', {}).get('status', 'NOT_EVALUATED')} | {candidate.get('coverage', {}).get('status', 'NOT_EVALUATED')} | {candidate.get('assembly_support', {}).get('status', 'NOT_EVALUATED')} |"
        )
    if (root / "candidate_queries.json").is_file():
        lines.extend(["", "Sequências candidatas para revisão: `candidate_sequences.fa`; alinhamentos e comprimentos: `candidate_sequences.tsv`; origens e hashes: `candidate_queries.json`.",
                      "A recuperação inclui contigs e reads resgatados. Ocorrências de uma sequência em reads não equivalem a templates independentes nem confirmam origem viral."])
    else:
        lines.append("Os sinais de resgate direto de reads pertencem ao relatório clássico e não são somados aos contigs/loci acima.")
    lines.extend(["", f"Tabelas completas preservadas no bundle: {artifact_refs}.", ""])
    return "\n".join(lines)
