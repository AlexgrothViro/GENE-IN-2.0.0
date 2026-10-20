#!/usr/bin/env python3
import argparse, gzip, random, sys
from pathlib import Path

def read_fasta_records(path: Path):
    """Lê FASTA (inclusive multi-FASTA). Retorna lista de (header, seq)."""
    records = []
    header = None
    seq_parts = []

    with path.open("rt", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    seq = "".join(seq_parts).upper()
                    if seq:
                        records.append((header, seq))
                header = line[1:].strip()
                seq_parts = []
            else:
                seq_parts.append(line)

    if header is not None:
        seq = "".join(seq_parts).upper()
        if seq:
            records.append((header, seq))

    if not records:
        raise SystemExit(f"[ERRO] FASTA sem sequência útil: {path}")

    return records

def pick_reference(records, need_len: int, mode: str):
    """
    Seleciona a sequência de referência a partir de um multi-FASTA.
    mode:
      - first_valid: primeira com len >= need_len
      - longest: maior com len >= need_len
      - first: primeira sempre (legado)
    """
    if mode == "first":
        return records[0]

    valid = [(h, s) for (h, s) in records if len(s) >= need_len]

    if mode == "first_valid":
        if valid:
            return valid[0]
    elif mode == "longest":
        if valid:
            return max(valid, key=lambda x: len(x[1]))

    # Se chegou aqui: ninguém atende ao mínimo
    longest = max(records, key=lambda x: len(x[1]))
    top_lens = sorted([len(s) for _, s in records], reverse=True)[:10]
    raise SystemExit(
        f"[ERRO] Referência curta demais para o insert atual.\n"
        f"       Precisa >= {need_len} bp, mas nenhuma sequência atende.\n"
        f"       Maior sequência tem {len(longest[1])} bp.\n"
        f"       Top lengths: {top_lens}\n"
        f"       Dica: reduza --insert ou use um FASTA com genoma completo."
    )

def revcomp(s: str) -> str:
    comp = str.maketrans("ACGTN", "TGCAN")
    return s.translate(comp)[::-1]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=False)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--sample", default="DEMO")
    ap.add_argument("--pairs", type=int, default=2000)
    ap.add_argument("--len", dest="read_len", type=int, default=150)
    ap.add_argument("--insert", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--pick",
        choices=["first_valid", "longest", "first"],
        default="first_valid",
        help="Como escolher a sequência quando o FASTA tiver múltiplas entradas."
    )
    ap.add_argument(
        "--min_ref_len",
        type=int,
        default=0,
        help="Força tamanho mínimo da referência (0 = usa --insert)."
    )
    ap.add_argument(
        "--random",
        action="store_true",
        help="Gera sequência aleatória em vez de extrair da referência"
    )
    args = ap.parse_args()

    if not args.random and not args.ref:
        ap.error("--ref é obrigatório a menos que --random seja usado")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.read_len > args.insert:
        raise SystemExit("[ERRO] read_len maior que insert; ajuste --len ou --insert.")

    if args.random:
        random.seed(args.seed)
        seq = "".join(random.choices("ACGT", k=10000))
        header = "random_synthetic_nohits"
        print(f"[INFO] Gerando sequência aleatória de 10kb para controle negativo", file=sys.stderr)
    else:
        ref = Path(args.ref)
        records = read_fasta_records(ref)
        need = args.min_ref_len if args.min_ref_len and args.min_ref_len > 0 else args.insert
        header, seq = pick_reference(records, need_len=need, mode=args.pick)
        print(f"[INFO] Ref escolhida: {header} (len={len(seq)})", file=sys.stderr)

    if len(seq) < args.insert:
        # redundante (pick_reference já protege), mas mantém segurança
        raise SystemExit("[ERRO] Referência curta demais para o insert atual.")

    random.seed(args.seed)
    r1_path = outdir / f"{args.sample}_R1.fastq.gz"
    r2_path = outdir / f"{args.sample}_R2.fastq.gz"
    qual = "I" * args.read_len

    max_start = len(seq) - args.insert
    with gzip.open(r1_path, "wt", encoding="utf-8") as r1, gzip.open(r2_path, "wt", encoding="utf-8") as r2:
        for i in range(1, args.pairs + 1):
            start = random.randint(0, max_start)
            frag = seq[start:start + args.insert]
            read1 = frag[:args.read_len]
            read2 = revcomp(frag[-args.read_len:])
            rid = f"{args.sample}_{i}"
            r1.write(f"@{rid}/1\n{read1}\n+\n{qual}\n")
            r2.write(f"@{rid}/2\n{read2}\n+\n{qual}\n")

    print(f"[OK] DEMO gerada: {r1_path} e {r2_path}")

if __name__ == "__main__":
    main()
