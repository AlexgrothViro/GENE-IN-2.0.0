#!/usr/bin/env python3
"""
06_export_hit_contigs.py
------------------------
Exporta contigs da montagem que tiveram hit viral classificado pelo pipeline
Gene-In para um arquivo FASTA, usando o labeled_hits.tsv como fonte de
evidência e o contigs.fa como fonte de sequências.

Saídas:
  {out_dir}/{sample}_hit_contigs.fa          FASTA dos contigs com hit
  {out_dir}/{sample}_hit_contigs_summary.tsv Tabela de contigs exportados

Colunas obrigatórias no labeled_hits.tsv (produzido por label_hits.py):
  qseqid, sseqid, pident, aln_cov, adj_identity, evidence_class, evalue,
  bitscore

Coluna opcional (incluída no summary se presente):
  risk_note
"""
import argparse
import csv
import hashlib
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from input_validation import validate_sample_id

# ---------------------------------------------------------------------------
# Colunas que DEVEM existir no labeled_hits.tsv para o script operar
# ---------------------------------------------------------------------------
_REQUIRED_COLUMNS = {
    "qseqid",
    "sseqid",
    "pident",
    "aln_cov",
    "adj_identity",
    "evidence_class",
    "evalue",
    "bitscore",
}

# Prioridade de classe para desempate (menor número = melhor)
_CLASS_PRIORITY = {
    "STRONG":           0,
    "STRONG_DIVERGENT": 1,
    "MODERATE":         2,
    "WEAK_RECOVERABLE": 3,
    "REVIEW":           4,
    "DISCORDANT":       5,
}
_ACTIONABLE_CLASSES = {"STRONG", "STRONG_DIVERGENT", "MODERATE"}
# New fragment-recovery version: weak candidates remain visible in REVIEW.
# Their short alignment alone does not establish specificity/read support.

# Classes válidas reconhecidas pelo pipeline. DISCORDANT é preservada como
# veio da classificação e permanece fora das alegações ACTIONABLE.
_VALID_CLASSES = set(_CLASS_PRIORITY.keys())


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def class_priority(label: str) -> int:
    """Retorna o valor de prioridade da classe (menor = melhor)."""
    return _CLASS_PRIORITY.get(label, 99)


_VALIDATED_CONTROLS = {"CONTROL_BELOW_SAMPLE", "CONTROL_NOT_DETECTED", "CONTROL_NOT_APPLICABLE"}


def confidence_tier_for(evidence_class: str, *, control_status: str = "UNCONTROLLED") -> str:
    """Mapeia as classes que participam da contagem canônica.

    REVIEW continua exportado com best_ref, evidence_class e valores brutos
    preservados, mas fica fora da contagem canônica. DISCORDANT e classes
    desconhecidas também não entram nessa contagem. DISCORDANT é mantida como
    DISCORDANT; esta camada não reescreve evidence_class.

    Sem controle positivo ou negativo validado, o rótulo da execução não passa
    de REVIEW: a classe bruta permanece, e confidence_tier não fica ACTIONABLE.
    """
    if evidence_class in _ACTIONABLE_CLASSES:
        tier = "ACTIONABLE"
    elif evidence_class in {"REVIEW", "WEAK_RECOVERABLE"}:
        tier = "REVIEW"
    elif evidence_class == "DISCORDANT":
        tier = "DISCORDANT"
    else:
        tier = "UNCLASSIFIED"
    if tier == "ACTIONABLE" and control_status not in _VALIDATED_CONTROLS:
        return "REVIEW"
    return tier


def read_fasta(path: Path) -> dict:
    """
    Lê um arquivo FASTA e retorna {primeiro_token_do_header: sequência}.

    Apenas o primeiro token após '>' é usado como chave, garantindo
    compatibilidade com cabeçalhos no estilo Velvet/SPAdes:
      >NODE_1_length_543_cov_12.4  →  chave: "NODE_1_length_543_cov_12.4"
    """
    seqs: dict[str, str] = {}
    name: str | None = None
    buf: list[str] = []
    with path.open("r", encoding="utf-8", errors="strict") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith(">"):
                if name is not None:
                    seqs[name] = "".join(buf)
                # Pega somente o primeiro token → exclui descrição livre
                name = line[1:].split()[0]
                buf = []
            else:
                buf.append(line.strip())
        if name is not None:
            seqs[name] = "".join(buf)
    return seqs


def wrap(seq: str, width: int = 80) -> str:
    """Quebra a sequência em linhas de `width` caracteres."""
    return "\n".join(seq[i : i + width] for i in range(0, len(seq), width))


def pick_best_hit(hits: list) -> dict:
    """
    Seleciona o melhor hit de um contig com múltiplos hits.

    Critério hierárquico (em ordem de prioridade):
      1. evidence_class  STRONG > STRONG_DIVERGENT > MODERATE > WEAK_RECOVERABLE > REVIEW > DISCORDANT
      2. adj_identity    maior é melhor
      3. bitscore        maior é melhor
      4. aln_cov         maior é melhor
      5. evalue          menor é melhor
    """
    def sort_key(h: dict) -> tuple:
        return (
            class_priority(h["evidence_class"]),  # menor = melhor classe
            -h["adj_identity"],                   # negado → maior primeiro
            -h["bitscore"],                       # negado → maior primeiro
            -h["aln_cov"],                        # negado → maior primeiro
            h["evalue"],                          # menor primeiro
        )

    return sorted(hits, key=sort_key)[0]


def validate_columns(header: list[str]) -> None:
    """
    Valida que o labeled_hits.tsv possui todas as colunas obrigatórias.
    Encerra com sys.exit(1) e mensagem clara se alguma estiver ausente.
    """
    present = set(header)
    missing = _REQUIRED_COLUMNS - present
    if missing:
        missing_fmt = ", ".join(sorted(missing))
        print(
            f"[ERRO] O arquivo labeled_hits.tsv não contém as colunas obrigatórias.\n"
            f"       Colunas ausentes: {missing_fmt}\n"
            f"       Colunas encontradas: {', '.join(header)}\n"
            f"       Verifique se o arquivo foi gerado corretamente por label_hits.py.",
            file=sys.stderr,
        )
        sys.exit(1)


def load_labeled_hits(
    labeled_path: Path,
    allowed_classes: set,
    has_risk_note: "list[bool]",  # lista de 1 elemento: flag mutável
) -> dict:
    """
    Lê o labeled_hits.tsv, valida colunas e agrupa todos os hits por qseqid.
    Retorna {qseqid: melhor_hit_dict} após deduplicação.

    `has_risk_note` é uma lista de 1 elemento (mutable flag) preenchida
    com True se a coluna risk_note estiver presente no arquivo.
    """
    hits_by_contig: dict[str, list] = {}

    with labeled_path.open("r", encoding="utf-8", errors="strict") as fh:
        reader = csv.DictReader(fh, delimiter="\t")

        # ---- Validação de colunas (feita uma vez, no cabeçalho) ----
        if reader.fieldnames is None:
            print(
                "[ERRO] labeled_hits.tsv está vazio ou não possui cabeçalho.",
                file=sys.stderr,
            )
            sys.exit(1)

        validate_columns(list(reader.fieldnames))

        # risk_note é opcional — registra presença para formatação do summary
        has_risk_note[0] = "risk_note" in reader.fieldnames

        # ---- Iteração por linha ----
        for row in reader:
            qseqid         = row["qseqid"].strip()
            evidence_class = row["evidence_class"].strip()

            if not qseqid:
                continue

            # Filtro por classe de evidência
            if "ALL" not in allowed_classes and evidence_class not in allowed_classes:
                continue

            # Parse de valores numéricos obrigatórios
            try:
                adj_identity = float(row["adj_identity"])
                bitscore     = float(row["bitscore"])
                aln_cov      = float(row["aln_cov"])
                evalue       = float(row["evalue"])
                pident       = float(row["pident"])
            except (ValueError, TypeError) as exc:
                print(
                    f"[AVISO] Valores numéricos inválidos para '{qseqid}' "
                    f"({exc}). Linha ignorada.",
                    file=sys.stderr,
                )
                continue

            # Parse de colunas numéricas opcionais
            try:
                qlen    = int(float(row.get("qlen", 0) or 0))
                aln_len = int(float(row.get("length", 0) or 0))
            except (ValueError, TypeError):
                qlen    = 0
                aln_len = 0

            hit = {
                "qseqid":         qseqid,
                "sseqid":         row["sseqid"].strip(),
                "pident":         pident,
                "aln_len":        aln_len,
                "evalue":         evalue,
                "bitscore":       bitscore,
                "qlen":           qlen,
                "aln_cov":        aln_cov,
                "adj_identity":   adj_identity,
                "evidence_class": evidence_class,
                # risk_note lido de forma segura — vazio se coluna ausente
                "risk_note":      row.get("risk_note", ""),
            }

            hits_by_contig.setdefault(qseqid, []).append(hit)

    # Deduplica: um único registro por qseqid — melhor hit segundo pick_best_hit
    best_hits: dict[str, dict] = {}
    for qseqid, hit_list in hits_by_contig.items():
        best_hits[qseqid] = pick_best_hit(hit_list)

    return best_hits


def build_fasta_header(hit: dict) -> str:
    """
    Monta o cabeçalho FASTA enriquecido com metadados do melhor hit.

    Formato (primeira palavra = ID canônico do contig):
      >{qseqid} best_ref=... pident=... aln_cov=... adj_identity=...
               evidence_class=... evalue=... bitscore=...
    """
    return (
        f">{hit['qseqid']} "
        f"best_ref={hit['sseqid']} "
        f"pident={hit['pident']:.3f} "
        f"aln_cov={hit['aln_cov']:.5f} "
        f"adj_identity={hit['adj_identity']:.3f} "
        f"evidence_class={hit['evidence_class']} "
        f"confidence_tier={confidence_tier_for(hit['evidence_class'])} "
        f"evalue={hit['evalue']:.2e} "
        f"bitscore={hit['bitscore']:.1f}"
    )


def compute_n50(lengths: list) -> int:
    """Calcula o N50 de uma lista de comprimentos de sequências."""
    if not lengths:
        return 0
    sorted_lens = sorted(lengths, reverse=True)
    target = sum(sorted_lens) / 2
    cumulative = 0
    for length in sorted_lens:
        cumulative += length
        if cumulative >= target:
            return length
    return sorted_lens[-1]


def emit_stats(
    total_exported: int,
    counts_by_class: dict,
    counts_by_tier: dict,
    refs_count: int,
    sz_min: int,
    sz_median: int,
    sz_max: int,
    sz_n50: int,
    missing_count: int,
) -> None:
    """
    Emite variáveis KEY=VALUE no stdout para o script Bash parsear.
    Todas as linhas começam com EXPORT_HIT_CONTIGS_ para fácil filtragem.
    """
    print(f"EXPORT_HIT_CONTIGS_COUNT={total_exported}")
    print(f"EXPORT_HIT_CONTIGS_STRONG={counts_by_class.get('STRONG', 0)}")
    print(f"EXPORT_HIT_CONTIGS_MODERATE={counts_by_class.get('MODERATE', 0)}")
    print(f"EXPORT_HIT_CONTIGS_WEAK={counts_by_class.get('WEAK_RECOVERABLE', 0)}")
    print(f"EXPORT_HIT_CONTIGS_REVIEW={counts_by_class.get('REVIEW', 0)}")
    print(f"EXPORT_HIT_CONTIGS_CANONICAL_CLAIM_COUNT={counts_by_tier.get('ACTIONABLE', 0)}")
    print(f"EXPORT_HIT_CONTIGS_REFS={refs_count}")
    print(f"EXPORT_HIT_CONTIGS_MIN={sz_min}")
    print(f"EXPORT_HIT_CONTIGS_MEDIAN={sz_median}")
    print(f"EXPORT_HIT_CONTIGS_MAX={sz_max}")
    print(f"EXPORT_HIT_CONTIGS_N50={sz_n50}")
    print(f"EXPORT_HIT_CONTIGS_MISSING_IN_FASTA={missing_count}")


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Exporta contigs com hit viral classificado para FASTA.\n"
            "Deduplicação automática: um único registro FASTA por contig,\n"
            "escolhendo o melhor hit por:\n"
            "  evidence_class (STRONG > STRONG_DIVERGENT > MODERATE > WEAK_RECOVERABLE > REVIEW > DISCORDANT)\n"
            "  → adj_identity (maior) → bitscore (maior) → aln_cov (maior)\n"
            "  → evalue (menor)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--labeled",
        required=True,
        metavar="ARQUIVO",
        help="TSV gerado por label_hits.py (ex: results/blast/{sample}_labeled_hits.tsv)",
    )
    ap.add_argument(
        "--contigs",
        required=True,
        metavar="ARQUIVO",
        help="FASTA da montagem (ex: data/assemblies/{sample}_assembly/contigs.fa)",
    )
    ap.add_argument(
        "--sample",
        required=True,
        metavar="NOME",
        help="Nome da amostra (usado nos nomes dos arquivos de saída)",
    )
    ap.add_argument(
        "--out-dir",
        default="results/blast",
        metavar="DIR",
        help="Diretório de saída (default: results/blast)",
    )
    ap.add_argument(
        "--classes",
        default="ALL",
        metavar="LISTA",
        help=(
            "Classes de evidência a exportar, separadas por vírgula.\n"
            "Use ALL para exportar tudo (default).\n"
            "Válidos: STRONG, STRONG_DIVERGENT, MODERATE, WEAK_RECOVERABLE, REVIEW, DISCORDANT, ALL"
        ),
    )
    ap.add_argument(
        "--min-len",
        type=int,
        default=0,
        metavar="N",
        help="Comprimento mínimo do contig para exportação em bp (default: 0 = sem filtro)",
    )
    ap.add_argument(
        "--control-status",
        default="UNCONTROLLED",
        help="Estado de controle da execução. Sem controle validado, confidence_tier permanece REVIEW.",
    )
    args = ap.parse_args()

    try:
        args.sample = validate_sample_id(args.sample)
    except ValueError as exc:
        ap.error(str(exc))

    labeled_path = Path(args.labeled)
    contigs_path = Path(args.contigs)
    out_dir      = Path(args.out_dir)

    # ---- Validações de existência dos arquivos de entrada ----
    if not labeled_path.exists():
        print(
            f"[ERRO] labeled_hits.tsv não encontrado: {labeled_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not contigs_path.exists():
        print(
            f"[ERRO] contigs.fa não encontrado: {contigs_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---- Normaliza e valida as classes solicitadas ----
    raw_classes = {c.strip().upper() for c in args.classes.split(",")}
    if "ALL" in raw_classes:
        allowed_classes = {"ALL"}
    else:
        invalid = raw_classes - _VALID_CLASSES
        if invalid:
            print(
                f"[ERRO] Classes inválidas: {', '.join(sorted(invalid))}.\n"
                f"       Use: {', '.join(sorted(_VALID_CLASSES))} ou ALL",
                file=sys.stderr,
            )
            sys.exit(1)
        allowed_classes = raw_classes

    out_dir.mkdir(parents=True, exist_ok=True)
    fasta_out   = out_dir / f"{args.sample}_hit_contigs.fa"
    summary_out = out_dir / f"{args.sample}_hit_contigs_summary.tsv"
    selection_ledger = out_dir / f"{args.sample}_selection_ledger.tsv"
    selection_summary = out_dir / f"{args.sample}_selection_summary.json"

    # ---- Carrega e valida o labeled_hits.tsv ----
    print(f"[INFO] Carregando hits classificados: {labeled_path}")
    has_risk_note: list[bool] = [False]   # flag mutável passada para load_labeled_hits
    best_hits = load_labeled_hits(labeled_path, allowed_classes, has_risk_note)
    risk_note_present = has_risk_note[0]
    all_best_hits = best_hits if allowed_classes == {"ALL"} else load_labeled_hits(labeled_path, {"ALL"}, [False])
    contigs_seqs = read_fasta(contigs_path)
    disposition_counts = {key: 0 for key in ("EXPORTED", "PENDING_MISSING_CONTIG", "EXCLUDED_CLASS_FILTER", "EXCLUDED_LENGTH_FILTER", "NO_BLAST_HIT")}
    ledger_fields = ["qseqid", "sequence_sha256", "query_length", "hit_row_count", "hit_accessions", "best_ref", "pident", "alignment_bp", "query_coverage", "adj_identity", "evidence_class", "risk_note", "disposition", "decision_rule"]
    with labeled_path.open("r", encoding="utf-8", errors="strict", newline="") as source:
        labeled_rows = list(csv.DictReader(source, delimiter="\t"))
    hit_row_counts: dict[str, int] = {}
    hit_accessions: dict[str, set[str]] = {}
    for row in labeled_rows:
        qid = (row.get("qseqid") or "").strip()
        if qid:
            hit_row_counts[qid] = hit_row_counts.get(qid, 0) + 1
            hit_accessions.setdefault(qid, set()).add((row.get("sseqid") or "").strip())
    with selection_ledger.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ledger_fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for qid in sorted(set(contigs_seqs) | set(all_best_hits)):
            sequence = contigs_seqs.get(qid)
            hit = all_best_hits.get(qid)
            seq_len = len(sequence) if sequence is not None else ""
            if hit is None:
                disposition, rule = "NO_BLAST_HIT", "NO-LABELED-HIT"
            elif sequence is None:
                disposition, rule = "PENDING_MISSING_CONTIG", "HIT-QUERY-NOT-IN-ASSEMBLY"
            elif allowed_classes != {"ALL"} and hit["evidence_class"] not in allowed_classes:
                disposition, rule = "EXCLUDED_CLASS_FILTER", "CLASS-FILTER"
            elif args.min_len > 0 and len(sequence) < args.min_len:
                disposition, rule = "EXCLUDED_LENGTH_FILTER", "MIN-LENGTH-FILTER"
            else:
                disposition, rule = "EXPORTED", "BEST-HIT-AND-EXPORT-FILTERS"
            disposition_counts[disposition] += 1
            writer.writerow({
                "qseqid": qid,
                "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest() if sequence is not None else "",
                "query_length": seq_len, "hit_row_count": hit_row_counts.get(qid, 0),
                "hit_accessions": ";".join(sorted(filter(None, hit_accessions.get(qid, set())))),
                "best_ref": hit.get("sseqid", "") if hit else "",
                "pident": f"{hit['pident']:.3f}" if hit else "",
                "alignment_bp": hit.get("aln_len", "") if hit else "",
                "query_coverage": f"{hit['aln_cov']:.6f}" if hit else "",
                "adj_identity": f"{hit['adj_identity']:.3f}" if hit else "",
                "evidence_class": hit.get("evidence_class", "") if hit else "",
                "risk_note": hit.get("risk_note", "") if hit else "",
                "disposition": disposition, "decision_rule": rule,
            })
    selection_summary.write_text(json.dumps({
        "schema_version": "1.0", "selection_performed": True,
        "allowed_classes": sorted(allowed_classes), "minimum_sequence_length_bp": args.min_len,
        "decision_rule": "best classified hit by class, adjusted identity, bitscore, query coverage, then e-value",
        "counts_by_disposition": disposition_counts,
        "assembly_contigs": len(contigs_seqs), "blast_query_ids": len(hit_row_counts),
        "distinct_assembly_sequences": len({hashlib.sha256(seq.encode()).hexdigest() for seq in contigs_seqs.values()}),
        "distinct_hit_accessions": len({row.get("sseqid", "") for row in labeled_rows if row.get("sseqid")}),
        "labeled_hit_rows": len(labeled_rows),
        "selection_ledger": selection_ledger.name,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---- Caso sem hits: arquivos vazios + sinalização, sem falha ----
    if not best_hits:
        print("[INFO] Nenhum contig com hit encontrado após aplicar filtros.")
        fasta_out.write_text("", encoding="utf-8")

        # Cabeçalho do summary adaptado à presença de risk_note
        summary_header = [
            "sample", "qseqid", "seq_len", "best_ref",
            "pident", "aln_len", "aln_cov", "adj_identity",
            "evidence_class", "confidence_tier",
        ]
        if risk_note_present:
            summary_header.append("risk_note")
        summary_header += ["evalue", "bitscore"]

        with summary_out.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, delimiter="\t", lineterminator="\n").writerow(summary_header)

        print(f"[OK] FASTA vazio: {fasta_out}")
        print(f"[OK] Summary vazio: {summary_out}")
        emit_stats(0, {}, {}, 0, 0, 0, 0, 0, 0)
        return

    # ---- Carrega sequências da montagem ----
    print(f"[INFO] Carregando sequências da montagem: {contigs_path}")

    # ---- Exportação ----
    exported:    list[dict] = []   # hits efetivamente escritos no FASTA
    missing:     list[str]  = []   # qseqids sem sequência no contigs.fa
    skipped_len: list[str]  = []   # qseqids filtrados por --min-len
    written_ids: set[str]   = set()  # garantia extra de unicidade no FASTA

    # Cabeçalho do summary TSV (risk_note apenas se presente no labeled)
    summary_header = [
        "sample", "qseqid", "seq_len", "best_ref",
        "pident", "aln_len", "aln_cov", "adj_identity",
        "evidence_class", "confidence_tier",
    ]
    if risk_note_present:
        summary_header.append("risk_note")
    summary_header += ["evalue", "bitscore"]

    with fasta_out.open("w", encoding="utf-8") as fa_fh, \
         summary_out.open("w", encoding="utf-8", newline="") as tsv_fh:

        tsv_writer = csv.writer(tsv_fh, delimiter="\t", lineterminator="\n")
        tsv_writer.writerow(summary_header)

        # Ordena por melhor evidência → saída consistente e reproduzível
        ordered = sorted(
            best_hits.values(),
            key=lambda h: (
                class_priority(h["evidence_class"]),
                -h["adj_identity"],
                -h["bitscore"],
                -h["aln_cov"],
                h["evalue"],
            ),
        )

        for hit in ordered:
            qseqid = hit["qseqid"]

            # Garantia extra de unicidade: ignora duplicata improvável de ID
            if qseqid in written_ids:
                print(
                    f"[AVISO] qseqid '{qseqid}' duplicado na lista de melhores hits. "
                    "Apenas a primeira ocorrência será exportada.",
                    file=sys.stderr,
                )
                continue

            seq = contigs_seqs.get(qseqid)
            if seq is None:
                missing.append(qseqid)
                continue

            seq_len = len(seq)
            if args.min_len > 0 and seq_len < args.min_len:
                skipped_len.append(qseqid)
                continue

            # Escreve sequência no FASTA
            fa_fh.write(f"{build_fasta_header(hit)}\n{wrap(seq)}\n")
            written_ids.add(qseqid)

            # Escreve linha no summary TSV
            row_data = [
                args.sample,
                qseqid,
                seq_len,
                hit["sseqid"],
                f"{hit['pident']:.3f}",
                hit["aln_len"],
                f"{hit['aln_cov']:.5f}",
                f"{hit['adj_identity']:.3f}",
                hit["evidence_class"],
                confidence_tier_for(hit["evidence_class"], control_status=args.control_status),
            ]
            if risk_note_present:
                row_data.append(hit["risk_note"])
            row_data += [
                f"{hit['evalue']:.2e}",
                f"{hit['bitscore']:.1f}",
            ]
            tsv_writer.writerow(row_data)
            exported.append(hit)

    # ---- Advertências de integridade ----
    if missing:
        print(
            f"[AVISO] {len(missing)} contig(s) do labeled_hits.tsv não foram encontrados "
            f"no contigs.fa (TSV e assembly podem estar descasados).",
            file=sys.stderr,
        )
        print(f"        Exemplos (até 5): {', '.join(missing[:5])}", file=sys.stderr)

    if skipped_len:
        print(
            f"[INFO] {len(skipped_len)} contig(s) ignorados por tamanho < {args.min_len} bp.",
        )

    # ---- Estatísticas para o relatório ----
    total_exported  = len(exported)
    counts_by_class: dict[str, int] = {}
    counts_by_tier: dict[str, int] = {}
    refs_found: set[str] = set()
    seq_lens: list[int] = []

    for hit in exported:
        cls = hit["evidence_class"]
        counts_by_class[cls] = counts_by_class.get(cls, 0) + 1
        tier = confidence_tier_for(cls, control_status=args.control_status)
        counts_by_tier[tier] = counts_by_tier.get(tier, 0) + 1
        refs_found.add(hit["sseqid"])
        seq_lens.append(len(contigs_seqs[hit["qseqid"]]))

    if seq_lens:
        s_sorted  = sorted(seq_lens)
        sz_min    = min(s_sorted)
        sz_median = int(st.median(s_sorted))
        sz_max    = max(s_sorted)
        sz_mean   = round(st.mean(s_sorted), 1)
        sz_n50    = compute_n50(s_sorted)
    else:
        sz_min = sz_median = sz_max = sz_mean = sz_n50 = 0

    print(f"[OK] FASTA exportado: {fasta_out}")
    print(f"[OK] Summary TSV: {summary_out}")
    print(f"[INFO] Total de contigs exportados: {total_exported}")
    for cls in ["STRONG", "STRONG_DIVERGENT", "MODERATE", "WEAK_RECOVERABLE", "REVIEW"]:
        n = counts_by_class.get(cls, 0)
        if n:
            print(f"[INFO]   {cls}: {n}")
    print(f"[INFO] Referências virais distintas atingidas: {len(refs_found)}")
    print(
        f"[INFO] Tamanho (bp): min={sz_min} mediana={sz_median} "
        f"max={sz_max} média={sz_mean} N50={sz_n50}"
    )

    # ---- Variáveis KEY=VALUE para o script Bash parsear ----
    emit_stats(
        total_exported=total_exported,
        counts_by_class=counts_by_class,
        counts_by_tier=counts_by_tier,
        refs_count=len(refs_found),
        sz_min=sz_min,
        sz_median=sz_median,
        sz_max=sz_max,
        sz_n50=sz_n50,
        missing_count=len(missing),
    )


if __name__ == "__main__":
    main()
