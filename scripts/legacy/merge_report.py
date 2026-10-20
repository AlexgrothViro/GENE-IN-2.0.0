#!/usr/bin/env python3
import sys, csv
from common import WORK_DIR

CONF = "run_T1/work/ptv_hits.confirm.tsv"   # outfmt 6 com qseq/sseq nas duas últimas colunas
ADJ  = "run_T1/work/ptv_hits.adjust.tsv"    # mesmas colunas + consider,match,adj (col 11,12,13)
OUT  = "run_T1/work/ptv_report.tsv"

# Lê confirm.tsv
CONF = WORK_DIR / "ptv_hits.confirm.tsv"
ADJ = WORK_DIR / "ptv_hits.adjust.tsv"
OUT = WORK_DIR / "ptv_report.tsv"
confirm = {}
with open(CONF, newline="") as fh:
    for row in csv.reader(fh, delimiter="\t"):
        if not row:
            continue
        # Espera 14 colunas: qseqid..send qseq sseq
        if len(row) < 14:
            continue
        qseqid = row[0]
        confirm[qseqid] = {
            "qseqid": qseqid,
            "sseqid": row[1],
            "pident": float(row[2]),
            "length": int(float(row[3])),
            "mismatch": row[4],
            "gapopen": row[5],
            "evalue": row[6],
            "bitscore": row[7],
            "qstart": row[8],
            "qend": row[9],
            "sstart": row[10],
            "send": row[11],
            # guardo qseq/sseq só se precisar depurar:
            # "qseq": row[12], "sseq": row[13],
        }

# Lê adjust.tsv e agrega consider/match/adj
with open(ADJ, newline="") as fh:
    for row in csv.reader(fh, delimiter="\t"):
        if not row:
            continue
        if len(row) < 15:
            continue
        qseqid = row[0]
        if qseqid not in confirm:
            continue
        confirm[qseqid]["consider"] = int(row[10])
        confirm[qseqid]["match"]    = int(row[11])
        confirm[qseqid]["adj"]      = float(row[12])

# Função de rótulo (reaplica regra da Etapa 6)
def label_of(alen, adj):
    if alen >= 60 and adj >= 90.0:
        return "PASS"
    if 40 <= alen < 60 and adj >= 95.0:
        return "SHORT_PASS"
    return "REVIEW"

# Escreve relatório com cabeçalho
cols = ["qseqid","sseqid","length","pident","adj","consider","match",
        "evalue","bitscore","qstart","qend","sstart","send","label"]

with open(OUT, "w", newline="") as wh:
    w = csv.writer(wh, delimiter="\t")
    w.writerow(cols)
    for qid in sorted(confirm.keys()):
        rec = confirm[qid]
        alen = rec["length"]
        adj  = rec.get("adj", 0.0)
        lab  = label_of(alen, adj)
        w.writerow([
            rec["qseqid"], rec["sseqid"], alen, f"{rec['pident']:.3f}",
            f"{adj:.2f}", rec.get("consider",0), rec.get("match",0),
            rec["evalue"], rec["bitscore"], rec["qstart"], rec["qend"], rec["sstart"], rec["send"], lab
        ])
print(f"[OK] Escrito: {OUT}")
