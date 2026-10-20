#!/usr/bin/env python3
import sys
from pathlib import Path
from common import REPO_ROOT, WORK_DIR

# Uso:
#   python3 scripts/collect_ptv_contigs.py \
#       run_T1/work/ptv_report.tsv \
#       data/assemblies/81554_S150_velvet_k31/contigs.fa \
#       run_T1/work/ptv_hits_pass.fa
#
# Esta versão coleta **todos** os contigs que aparecem no ptv_report.tsv,
# independentemente do rótulo (PASS / SHORT_PASS / REVIEW).
# Se quiser restringir por label no futuro, dá pra adaptar.

def read_fasta(path):
    seqs = {}
    cur_id = None
    cur = []
    with open(path) as fh:
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
                cur.append(line)
        if cur_id is not None:
            seqs[cur_id] = "".join(cur)
    return seqs

def main():
    report = Path(sys.argv[1]) if len(sys.argv) > 1 else WORK_DIR / "ptv_report.tsv"
    contigs_fa = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO_ROOT / "data/assemblies/81554_S150_velvet_k31/contigs.fa"
    out_fa = Path(sys.argv[3]) if len(sys.argv) > 3 else WORK_DIR / "ptv_hits_pass.fa"
    out_fa.parent.mkdir(parents=True, exist_ok=True)

    keep = set()
    with open(report) as fh:
        header = fh.readline().rstrip("\n").split("\t")
        # pega sempre a coluna qseqid
        try:
            idx_q = header.index("qseqid")
        except ValueError:
            raise SystemExit("ERRO: ptv_report.tsv deve ter coluna 'qseqid'")

        for line in fh:
            if not line.strip():
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) <= idx_q:
                continue
            qid = cols[idx_q]
            keep.add(qid)

    if not keep:
        print("[AVISO] Nenhum contig encontrado no relatório.", file=sys.stderr)

    contigs = read_fasta(contigs_fa)
    n_found = 0
    with open(out_fa, "w") as out:
        for cid, seq in contigs.items():
            if cid in keep:
                out.write(f">{cid}\n")
                for i in range(0, len(seq), 70):
                    out.write(seq[i:i+70] + "\n")
                n_found += 1

    print(f"[OK] Escrito {out_fa} com {n_found} contigs presentes em ptv_report.tsv.")

if __name__ == "__main__":
    main()
