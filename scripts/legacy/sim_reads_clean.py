#!/usr/bin/env python3
import gzip, random
from common import WORK_DIR

WORK_DIR.mkdir(parents=True, exist_ok=True)
FASTA=WORK_DIR / "extend_regions.fasta"
R1=WORK_DIR / "sim_R1.fastq.gz"
R2=WORK_DIR / "sim_R2.fastq.gz"

random.seed(42)

def read_fa(p):
    seqs=[]; name=None; buf=[]
    with open(p) as fh:
        for ln in fh:
            ln=ln.strip()
            if not ln: continue
            if ln.startswith(">"):
                if name and buf: seqs.append((name,"".join(buf)))
                name=ln[1:]; buf=[]
            else:
                buf.append(ln)
    if name and buf: seqs.append((name,"".join(buf)))
    return seqs

def rc(s):
    tr=str.maketrans("ACGTacgt","TGCAtgca")
    return s.translate(tr)[::-1]

refs = read_fa(FASTA)
L = 40           # tamanho do read
PAIRS = 200      # pares por flanco (limite superior)
r1=[]; r2=[]; made=0

for name,seq in refs:
    n=len(seq)
    if n < L:           # nem 1 read cabe
        continue
    INS = min(n, max(L, 2*L))  # INS adaptativo (permite sobreposição quando n<2L)
    qual="I"*L
    # número de pares proporcional ao tamanho (limita em PAIRS)
    npairs = min(PAIRS, max(1, n // (L//2 if L>=2 else 1)))
    for _ in range(npairs):
        start_max = n - INS
        if start_max < 0:
            start_max = 0
        start = random.randint(0, start_max)
        frag = seq[start:start+INS]
        if len(frag) < L:
            continue
        r1seq = frag[:L]
        r2seq = rc(frag[-L:])
        rid = f"@{name}|start={start}|L={L}|INS={INS}"
        r1.append(f"{rid}/1\n{r1seq}\n+\n{qual}\n")
        r2.append(f"{rid}/2\n{r2seq}\n+\n{qual}\n")
        made += 1

with gzip.open(R1,"wt") as f:
    f.writelines(r1)
with gzip.open(R2,"wt") as f:
    f.writelines(r2)

print(f"[OK] Gerados {R1} e {R2} (pairs={made})")
