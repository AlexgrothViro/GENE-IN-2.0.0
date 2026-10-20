#!/usr/bin/env python3
import os
import sys
import csv
import argparse
from pathlib import Path
from common import REPO_ROOT, WORK_DIR, repo_path

REPORT_DEFAULT = "run_T1/work/ptv_report.tsv"
OUT_TSV_DEFAULT = "run_T1/work/extend_plan.tsv"

def resolve_ref_fa(env_ref=None):
    if env_ref:
        return env_ref
    ref_env = os.environ.get("REF_FA") or os.environ.get("REF_FASTA")
    if ref_env:
        return ref_env
    return f"data/ref/{os.environ.get('DB','ptv')}.fa"

def read_fasta(path):
    seqs = {}
    cur_id = None
    cur = []
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if cur_id is not None:
                    seqs[cur_id] = "".join(cur)
                cur_id = line[1:].split()[0]
                cur = []
            else:
                cur.append(line.replace(" ", "").replace("\t", ""))
        if cur_id is not None:
            seqs[cur_id] = "".join(cur)
    return seqs

def main():
    ap = argparse.ArgumentParser(description="Gerar plano de extensão para hits PTV")
    ap.add_argument("--report", default=REPORT_DEFAULT)
    ap.add_argument("--ref", default=None, help="FASTA de referência ou via REF_FA/REF_FASTA env")
    ap.add_argument("--out", default=OUT_TSV_DEFAULT)
    args = ap.parse_args()

    report = WORK_DIR / "ptv_report.tsv" if args.report == REPORT_DEFAULT else repo_path(args.report)
    ref_fa = repo_path(args.ref) if args.ref else repo_path(resolve_ref_fa())
    out_tsv = WORK_DIR / "extend_plan.tsv" if args.out == OUT_TSV_DEFAULT else repo_path(args.out)
    out_tsv.parent.mkdir(parents=True, exist_ok=True)

    if not os.path.exists(report):
        raise SystemExit(f"[ERRO] Report não encontrado: {report}")
    if not os.path.exists(ref_fa):
        raise SystemExit(f"[ERRO] Referência não encontrada: {ref_fa}")

    FLANK_MIN = 60
    FLANK_MAX = 150

    ref = read_fasta(ref_fa)
    ref_len = {k: len(v) for k, v in ref.items()}

    rows = []
    with open(report, newline="") as fh:
        r = csv.DictReader(fh, delimiter="\t")
        for d in r:
            label = d.get("label", "")
            if label not in ("PASS", "SHORT_PASS"):
                continue
            qid = d["qseqid"]
            sid = d["sseqid"]
            L = int(float(d["length"]))
            qstart = int(d["qstart"])
            qend = int(d["qend"])
            sstart = int(d["sstart"])
            send = int(d["send"])

            if sid not in ref_len:
                strand = "?"
                Lref = 0
                left_gap = right_gap = 0
                rows.append([qid, sid, strand, L, Lref, sstart, send, left_gap, right_gap, 0, 0, "REF_NOT_FOUND"])
                continue

            Lref = ref_len[sid]
            strand = "+" if send >= sstart else "-"
            sL = min(sstart, send)
            sR = max(sstart, send)
            left_gap = sL - 1
            right_gap = Lref - sR
            left_w = min(max(FLANK_MIN, 0), min(FLANK_MAX, left_gap))
            right_w = min(max(FLANK_MIN, 0), min(FLANK_MAX, right_gap))
            status = []
            status.append("HAS_LEFT" if left_w > 0 else "NO_LEFT")
            status.append("HAS_RIGHT" if right_w > 0 else "NO_RIGHT")
            rows.append([qid, sid, strand, L, Lref, sstart, send, left_gap, right_gap, left_w, right_w, ";".join(status)])

    with open(out_tsv, "w", newline="") as outfh:
        writer = csv.writer(outfh, delimiter="\t")
        writer.writerow(["qseqid", "sseqid", "strand", "length", "ref_len", "sstart", "send", "left_gap", "right_gap", "left_w", "right_w", "status"])
        writer.writerows(rows)

    print(f"[OK] Plano escrito em: {out_tsv}")

if __name__ == "__main__":
    main()
