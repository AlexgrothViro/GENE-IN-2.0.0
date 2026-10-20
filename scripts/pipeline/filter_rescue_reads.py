#!/usr/bin/env python3
import sys
import csv
import argparse
import hashlib
import json
import os
from pathlib import Path

# Adiciona o diretório lib ao path para importar logging_utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from logging_utils import log_fatal, log_info, log_warning, set_context

MIN_PID = 90.0
MAX_EVALUE = 1e-5
MIN_ALN_LEN = 80
MIN_ALN_FRAC = 0.8


def sha256_streaming(path):
    """sha256 of a file without loading it (the decision ledger can be several GB)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Filtra e classifica candidatos a nivel de reads resgatados")
    parser.add_argument("--blast-raw", required=True)
    parser.add_argument("--out-tsv", required=True)
    args = parser.parse_args()

    set_context(etapa="RESCUE_READS")

    raw_path = Path(args.blast_raw)
    out_path = Path(args.out_tsv)
    if raw_path.resolve() == out_path.resolve():
        log_fatal("arquivo de entrada e saida nao podem ser o mesmo", "Use um caminho de saida separado.")

    fieldnames = [
        "qseqid", "sseqid", "pident", "length", "evalue", "bitscore",
        "qlen", "aln_cov", "adj_identity", "evidence_class", "risk_note"
    ]

    best_hits = {} # qseqid -> best hit dict
    decision_fields = ["qseqid", "sseqid", "pident", "length", "evalue", "bitscore", "qlen", "disposition", "decision_rule"]
    decisions_path = out_path.with_suffix(out_path.suffix + ".decisions.tsv")

    def iter_rows():
        """Yield (decision, hit_or_None) per raw BLAST row, streaming.

        The raw read-level report can hold tens of millions of rows; keeping
        one dict per row in memory (as before) needs tens of GB.  The file is
        therefore read twice: pass 1 selects the best hit per read, pass 2
        writes the decision ledger.  Rules and outputs are unchanged.
        """
        with raw_path.open("r", encoding="utf-8", errors="strict") as fh:
            reader = csv.reader(fh, delimiter="\t")
            for row in reader:
                if len(row) < 14:
                    yield {"qseqid": row[0] if row else "", "sseqid": row[1] if len(row) > 1 else "", "disposition": "REJECTED_INVALID_ROW", "decision_rule": "BLAST-ROW-REQUIRES-14-COLUMNS"}, None
                    continue
                qseqid = row[0]
                sseqid = row[1]
                try:
                    pident = float(row[2])
                    length = int(float(row[3]))
                    evalue = float(row[10])
                    bitscore = float(row[11])
                    qlen = int(float(row[12]))
                except ValueError:
                    yield {"qseqid": qseqid, "sseqid": sseqid, "disposition": "REJECTED_INVALID_METRIC", "decision_rule": "NUMERIC-BLAST-METRICS-REQUIRED"}, None
                    continue

                if qlen <= 0:
                    yield {"qseqid": qseqid, "sseqid": sseqid, "pident": pident, "length": length, "evalue": evalue, "bitscore": bitscore, "qlen": qlen, "disposition": "REJECTED_INVALID_QUERY_LENGTH", "decision_rule": "POSITIVE-QUERY-LENGTH"}, None
                    continue

                # Criterios conservadores para sinal no nivel de leitura
                # pident >= 90
                # length >= 80 ou length >= 0.8 * qlen
                # evalue <= 1e-5
                if pident < MIN_PID:
                    rejection = "MINIMUM_IDENTITY"
                elif evalue > MAX_EVALUE:
                    rejection = "MAXIMUM_EVALUE"
                elif length < MIN_ALN_LEN and length < (MIN_ALN_FRAC * qlen):
                    rejection = "MINIMUM_ALIGNMENT_LENGTH_AND_QUERY_FRACTION"
                else:
                    rejection = ""
                if rejection:
                    yield {"qseqid": qseqid, "sseqid": sseqid, "pident": pident, "length": length, "evalue": evalue, "bitscore": bitscore, "qlen": qlen, "disposition": "REJECTED_FILTER", "decision_rule": rejection}, None
                    continue

                aln_cov = length / qlen if qlen > 0 else 0.0
                adj_identity = pident * aln_cov

                hit = {
                    "qseqid": qseqid,
                    "sseqid": sseqid,
                    "pident": f"{pident:.3f}",
                    "length": length,
                    "evalue": evalue,
                    "bitscore": bitscore,
                    "qlen": qlen,
                    "aln_cov": f"{aln_cov:.5f}",
                    "adj_identity": f"{adj_identity:.3f}",
                    "evidence_class": "READ_LEVEL_SIGNAL",
                    "risk_note": "sinal_de_leitura_sem_contig"
                }
                yield {"qseqid": qseqid, "sseqid": sseqid, "pident": pident, "length": length, "evalue": evalue, "bitscore": bitscore, "qlen": qlen, "disposition": "ACCEPTED_PENDING_BEST_HIT_SELECTION", "decision_rule": "PASS-READ-LEVEL-THRESHOLDS"}, hit

    input_alignment_rows = 0
    unique_query_ids = set()
    counts_by_disposition = {}
    try:
        # Pass 1: best hit per read (highest bitscore; first one wins ties).
        for _decision, hit in iter_rows():
            if hit is None:
                continue
            qseqid = hit["qseqid"]
            if qseqid not in best_hits or hit["bitscore"] > best_hits[qseqid]["bitscore"]:
                best_hits[qseqid] = hit

        # Pass 2: stream the decision ledger with the final dispositions.
        selected_keys = {(qid, hit["sseqid"], hit["bitscore"], hit["length"], float(hit["pident"])) for qid, hit in best_hits.items()}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_decisions = decisions_path.with_name(f".{decisions_path.name}.tmp.{os.getpid()}")
        with temporary_decisions.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=decision_fields, delimiter="\t", lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            for row, _hit in iter_rows():
                if row["disposition"] == "ACCEPTED_PENDING_BEST_HIT_SELECTION":
                    key = (row["qseqid"], row["sseqid"], row["bitscore"], row["length"], row["pident"])
                    if key in selected_keys:
                        row["disposition"] = "SELECTED_BEST_HIT"
                        row["decision_rule"] = "HIGHEST-BITSCORE-PER-QNAME"
                        selected_keys.remove(key)
                    else:
                        row["disposition"] = "ACCEPTED_ALTERNATIVE_NOT_SELECTED"
                        row["decision_rule"] = "LOWER-BITSCORE-THAN-SELECTED-QNAME-HIT"
                input_alignment_rows += 1
                if row.get("qseqid"):
                    unique_query_ids.add(row["qseqid"])
                status = row.get("disposition", "")
                counts_by_disposition[status] = counts_by_disposition.get(status, 0) + 1
                writer.writerow(row)
        os.replace(temporary_decisions, decisions_path)
    except FileNotFoundError:
        log_fatal(f"Arquivo de entrada raw BLAST nao encontrado: {raw_path}", "Verifique a execucao do alinhamento BLAST no modo de resgate.")
    except Exception as exc:
        log_fatal(f"Erro ao ler arquivo raw BLAST {raw_path}: {exc}", "Inspecione o log do pipeline.")

    # Gravar saída
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = out_path.with_name(f".{out_path.name}.tmp.{os.getpid()}")
        with temporary.open("w", encoding="utf-8", newline="") as out_fh:
            writer = csv.DictWriter(out_fh, delimiter="\t", fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            for hit in sorted(best_hits.values(), key=lambda h: -h["bitscore"]):
                h_copy = dict(hit)
                h_copy["evalue"] = f"{hit['evalue']:.2e}"
                writer.writerow(h_copy)
        os.replace(temporary, out_path)
    except Exception as exc:
        log_fatal(f"Erro ao gravar arquivo de candidatos resgatados {out_path}: {exc}", "Verifique as permissoes de escrita no diretorio results/blast/.")

    provenance_path = out_path.with_suffix(out_path.suffix + ".provenance.json")
    try:
        provenance = {
            "schema": "genein.rescue_filter_provenance.v1",
            "input_raw_blast": str(raw_path),
            "output_candidates": str(out_path),
            "output_sha256": sha256_streaming(out_path),
            "criteria": {
                "minimum_percent_identity": MIN_PID,
                "maximum_evalue": MAX_EVALUE,
                "minimum_alignment_length_bp": MIN_ALN_LEN,
                "minimum_alignment_fraction_of_query": MIN_ALN_FRAC,
            },
            "candidate_count": len(best_hits),
            "input_alignment_rows": input_alignment_rows,
            "unique_query_ids": len(unique_query_ids),
            "counts_by_disposition": {status: counts_by_disposition[status] for status in sorted(counts_by_disposition)},
            "decision_ledger": str(decisions_path),
            "decision_ledger_sha256": sha256_streaming(decisions_path),
        }
        temporary_json = provenance_path.with_name(f".{provenance_path.name}.tmp.{os.getpid()}")
        temporary_json.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary_json, provenance_path)
    except Exception as exc:
        log_fatal(f"Erro ao gravar proveniencia do resgate {provenance_path}: {exc}", "Inspecione as permissoes do diretorio de resultados.")

    log_info(f"{len(best_hits)} leitura(s) candidatas resgatadas salvas com sucesso em {out_path}")

if __name__ == "__main__":
    main()
