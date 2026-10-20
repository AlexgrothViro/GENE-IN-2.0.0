#!/usr/bin/env python3
import argparse
import collections
import csv
import sys
from pathlib import Path

# Adiciona o diretório lib ao path para importar logging_utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from logging_utils import log_fatal, log_info, log_warning, set_context


_CLASS_PRIORITY = {
    "STRONG":           0,
    "STRONG_DIVERGENT": 1,
    "MODERATE":         2,
    "WEAK_RECOVERABLE": 3,
    "REVIEW":           4,
}


def class_priority(label: str) -> int:
    return _CLASS_PRIORITY.get(label, 99)


def classify_hit(length, pident, evalue, bitscore, adj_identity, qlen=0, aln_cov=0.0):
    risk = []

    if length >= 80 and pident >= 90 and adj_identity >= 70 and evalue <= 1e-10:
        label = "STRONG"
    elif (length >= 1000 or qlen >= 1000) and aln_cov >= 0.80 and 80 <= pident < 90 and evalue <= 1e-10:
        label = "STRONG_DIVERGENT"
    elif 50 <= length < 80 and pident >= 85 and adj_identity >= 60 and evalue <= 1e-5:
        label = "MODERATE"
    elif 20 <= length < 50 and pident >= 90 and bitscore >= 35:
        label = "WEAK_RECOVERABLE"
        risk.append("fragmento_curto_exige_revisao")
    else:
        label = "REVIEW"

    if length < 50:
        risk.append("comprimento_muito_curto")
    if adj_identity < 70 and label != "STRONG_DIVERGENT":
        risk.append("baixa_identidade_ajustada")
    if bitscore < 40:
        risk.append("bitscore_baixo")

    return label, ";".join(risk) if risk else "ok"


def pick_best_hit_dict(hits: list) -> dict:
    def sort_key(h: dict) -> tuple:
        return (
            class_priority(h["evidence_class"]),
            -h["adj_identity"],
            -h["bitscore"],
            -h["aln_cov"],
            h["evalue"]
        )
    return sorted(hits, key=sort_key)[0]


def main():
    ap = argparse.ArgumentParser(description="Classifica hits virais por grau de evidência e calcula métricas de desambiguação")
    ap.add_argument("adj_path", help="TSV gerado por adj_identity.py")
    ap.add_argument("--out", default=None, help="Arquivo TSV de saída")
    args = ap.parse_args()

    set_context(etapa="CLASSIFICACAO")

    path = Path(args.adj_path)
    out_path = Path(args.out) if args.out else path.with_suffix(".labeled.tsv")
    if path.resolve() == out_path.resolve():
        log_fatal("arquivo de entrada e saida nao podem ser o mesmo", "Use um caminho de saida separado.")

    contig_hits = collections.defaultdict(list)
    headers = []

    try:
        with path.open("r", encoding="utf-8", errors="strict") as inp:
            reader = csv.DictReader(inp, delimiter="\t")
            headers = reader.fieldnames
            if not headers:
                log_fatal(f"Arquivo de entrada vazio ou sem cabecalho: {path}", "Verifique a geracao do arquivo de entrada.")
            for row in reader:
                try:
                    length = int(float(row["length"]))
                    pident = float(row["pident"])
                    evalue = float(row["evalue"])
                    bitscore = float(row["bitscore"])
                    adj_identity = float(row["adj_identity"])
                    qlen = int(float(row["qlen"])) if "qlen" in row else 0
                    aln_cov = float(row["aln_cov"]) if "aln_cov" in row else 0.0
                except (KeyError, ValueError) as exc:
                    print(f"[AVISO] linha ignorada (parse error: {exc}): {row}", file=sys.stderr)
                    continue

                # Converte valores string lidos para float/int nos dicionários para consistência interna
                row_typed = dict(row)
                row_typed["length"] = length
                row_typed["pident"] = pident
                row_typed["evalue"] = evalue
                row_typed["bitscore"] = bitscore
                row_typed["adj_identity"] = adj_identity
                row_typed["qlen"] = qlen
                row_typed["aln_cov"] = aln_cov

                label, risk = classify_hit(length, pident, evalue, bitscore, adj_identity, qlen=qlen, aln_cov=aln_cov)
                row_typed["evidence_class"] = label
                row_typed["risk_note"] = risk

                contig_hits[row_typed["qseqid"]].append(row_typed)

    except FileNotFoundError:
        log_fatal(f"Arquivo nao encontrado: {path}", "Verifique se a etapa anterior de identidade ajustada foi concluida com sucesso.")
    except Exception as exc:
        log_fatal(f"Erro ao ler arquivo {path}: {exc}", "Inspecione o log ou tente reexecutar a etapa anterior.")

    # Processamento de desambiguação por contig
    output_rows = []
    for qseqid, hits in contig_hits.items():
        hit_best_classified = pick_best_hit_dict(hits)

        def adj_sort_key(h):
            return (-h["adj_identity"], -h["bitscore"], h["evalue"])
        sorted_by_adj = sorted(hits, key=adj_sort_key)
        hit_max_adj = sorted_by_adj[0]
        hit_second_adj = sorted_by_adj[1] if len(sorted_by_adj) > 1 else None

        distinct_refs_90 = set(h["sseqid"] for h in hits if h["pident"] >= 90.0)
        n_hits_90 = len(distinct_refs_90)

        is_diff = "FALSE"
        if hit_best_classified["evidence_class"] in {"STRONG", "STRONG_DIVERGENT", "MODERATE"}:
            if hit_best_classified["sseqid"] != hit_max_adj["sseqid"]:
                is_diff = "TRUE"

        if hit_second_adj:
            sec_sseqid = hit_second_adj["sseqid"]
            sec_pident = f"{hit_second_adj['pident']:.3f}"
            sec_adj_id = f"{hit_second_adj['adj_identity']:.3f}"
            delta_pident = f"{(hit_best_classified['pident'] - hit_second_adj['pident']):.3f}"
        else:
            sec_sseqid = ""
            sec_pident = ""
            sec_adj_id = ""
            delta_pident = ""

        for h in hits:
            h["segundo_melhor_sseqid"] = sec_sseqid
            h["segundo_melhor_pident"] = sec_pident
            h["segundo_melhor_adj_identity"] = sec_adj_id
            h["delta_pident_top2"] = delta_pident
            h["n_hits_pident_90_ou_mais"] = str(n_hits_90)
            h["adj_identity_nao_e_o_melhor_hit_classificado"] = is_diff
            output_rows.append(h)

    new_fields = [
        "evidence_class",
        "risk_note",
        "segundo_melhor_sseqid",
        "segundo_melhor_pident",
        "segundo_melhor_adj_identity",
        "delta_pident_top2",
        "n_hits_pident_90_ou_mais",
        "adj_identity_nao_e_o_melhor_hit_classificado"
    ]
    fieldnames = headers + new_fields

    try:
        with out_path.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, delimiter="\t", fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            for r in output_rows:
                writer.writerow(r)
    except Exception as exc:
        log_fatal(f"Erro ao escrever arquivo de saida {out_path}: {exc}", "Verifique se ha permissoes de escrita no diretorio results/blast/.")

    log_info(f"Hits classificados e desambiguados com sucesso salvos em {out_path}")


if __name__ == "__main__":
    main()
