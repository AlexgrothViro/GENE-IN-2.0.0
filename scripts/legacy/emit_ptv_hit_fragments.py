#!/usr/bin/env python3
import sys, csv
from pathlib import Path
from common import WORK_DIR

# Uso:
#   python3 scripts/emit_ptv_hit_fragments.py \
#       run_T1/work/ptv_hits.adjust.tsv \
#       run_T1/work/ptv_hits_fragments.fa
#
# Se não passar argumentos, usa os caminhos padrão acima.

def main():
    adj_path = Path(sys.argv[1]) if len(sys.argv) > 1 else WORK_DIR / "ptv_hits.adjust.tsv"
    out_fa   = Path(sys.argv[2]) if len(sys.argv) > 2 else WORK_DIR / "ptv_hits_fragments.fa"
    out_fa.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with open(adj_path, newline="") as fh, open(out_fa, "w") as out:
        r = csv.reader(fh, delimiter="\t")
        for row in r:
            if not row:
                continue
            # ajusta para o formato gerado pelo adj_identity.py:
            # 0:qseqid 1:sseqid 2:pident 3:length 4:evalue 5:bitscore
            # 6:qend 7:qstart 8:send 9:sstart 10:consider 11:match 12:adj 13:qseq 14:sseq
            if len(row) < 14:
                continue
            qid  = row[0]
            sid  = row[1]
            try:
                alen = int(float(row[3]))
            except ValueError:
                continue
            try:
                adj  = float(row[12])
            except ValueError:
                adj = 0.0
            qseq = row[13]

            header = f"{qid}|{sid}|len={alen}|adj={adj:.2f}"
            out.write(f">{header}\n")
            for i in range(0, len(qseq), 70):
                out.write(qseq[i:i+70] + "\n")
            n += 1

    print(f"[OK] Escrito {out_fa} com {n} fragmentos de alinhamento (qseq).")

if __name__ == "__main__":
    main()
