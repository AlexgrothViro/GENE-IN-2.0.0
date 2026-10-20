#!/usr/bin/env python3
import argparse
from pathlib import Path

ACGT = set("ACGTacgt")

def read_fasta(path: Path):
    seqs = {}
    name = None
    buf = []
    with path.open() as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith(">"):
                if name is not None:
                    seqs[name] = "".join(buf)
                name = line[1:].split()[0]
                buf = []
            else:
                buf.append(line)
        if name is not None:
            seqs[name] = "".join(buf)
    return seqs

def wrap_seq(seq: str, width: int = 80) -> str:
    return "\n".join(seq[i:i+width] for i in range(0, len(seq), width))

def acgt_count(aln_seq: str) -> int:
    return sum(1 for c in aln_seq if c in ACGT)

def merge_intervals(sorted_positions):
    # positions are 1-based, sorted unique
    if not sorted_positions:
        return []
    merged = []
    s = e = sorted_positions[0]
    for p in sorted_positions[1:]:
        if p == e + 1:
            e = p
        else:
            merged.append((s, e))
            s = e = p
    merged.append((s, e))
    return merged
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True, help="ex: results/phylogeny/SAMPLE_k51")
    ap.add_argument("--max-frags", type=int, default=200)
    ap.add_argument("--min-frag-acgt", type=int, default=80)
    ap.add_argument("--prefix", default="tree_input")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    refs_aln = outdir / "refs.aln.fa"
    frags_aln = outdir / "ptv_fragments.aln.fa"

    if not refs_aln.exists():
        raise SystemExit(f"ERRO: não encontrei {refs_aln}")
    if not frags_aln.exists():
        raise SystemExit(f"ERRO: não encontrei {frags_aln}")

    refs = read_fasta(refs_aln)
    all_aln = read_fasta(frags_aln)

    ref_ids = set(refs.keys())
    aln_len = None
    for rid, rseq in refs.items():
        aln_len = len(rseq) if aln_len is None else aln_len
        if len(rseq) != aln_len:
            raise SystemExit("ERRO: refs.aln.fa com comprimentos inconsistentes")

    fragments = {k: v for k, v in all_aln.items() if k not in ref_ids}

    # Seleciona fragments por quantidade de bases (ACGT) no alinhamento
    frag_stats = []
    for fid, seq in fragments.items():
        frag_stats.append((acgt_count(seq), fid, seq))
    frag_stats.sort(reverse=True)

    frags_used = [(c, fid, seq) for (c, fid, seq) in frag_stats if c >= args.min_frag_acgt]
    frags_used = frags_used[:args.max_frags]

    tree_aln_path = outdir / f"{args.prefix}.aln.fa"
    with tree_aln_path.open("w") as out:
        for rid in sorted(refs.keys()):
            out.write(f">{rid}\n{wrap_seq(refs[rid])}\n")
        for c, fid, seq in frags_used:
            out.write(f">{fid}\n{wrap_seq(seq)}\n")

    # Coverage por referência (usando somente frags_used)
    cov_tsv = outdir / "coverage_by_ref.tsv"
    cov_int = outdir / "coverage_intervals_by_ref.tsv"

    frag_has_base = [False] * aln_len
    for _, _, seq in frags_used:
        for i, ch in enumerate(seq):
            if ch != "-" and ch in ACGT:
                frag_has_base[i] = True

    with cov_tsv.open("w") as out1, cov_int.open("w") as out2:
        out1.write("ref\tref_len\tcov_bp\tcov_pct\tintervals\tmax_block\n")
        out2.write("ref\tstart\tend\tlen\n")

        for rid, rseq in sorted(refs.items()):
            pos = 0
            covered = []
            for i, ch in enumerate(rseq):
                if ch == "-":
                    continue
                pos += 1
                if frag_has_base[i]:
                    covered.append(pos)

            ref_len = pos
            cov_bp = len(set(covered))
            merged = merge_intervals(sorted(set(covered)))
            max_block = max((e - s + 1) for s, e in merged) if merged else 0
            cov_pct = (100.0 * cov_bp / ref_len) if ref_len else 0.0

            out1.write(f"{rid}\t{ref_len}\t{cov_bp}\t{cov_pct:.2f}\t{len(merged)}\t{max_block}\n")
            for s, e in merged:
                out2.write(f"{rid}\t{s}\t{e}\t{e - s + 1}\n")

    # Resumo
    used_counts = sorted([c for c, _, _ in frags_used])
    if used_counts:
        mn = used_counts[0]
        p50 = used_counts[int((len(used_counts) - 1) * 0.50)]
        p90 = used_counts[int((len(used_counts) - 1) * 0.90)]
        mx = used_counts[-1]
    else:
        mn = p50 = p90 = mx = 0

    print("== Postprocess (coverage + tree input) ==")
    print(f"Refs: {len(refs)}  Fragments_total: {len(fragments)}  Fragments_usados: {len(frags_used)}")
    print(f"Aln_len(colunas): {aln_len}")
    print(f"Fragments_usados (ACGT no alinhamento): min {mn} p50 {p50} p90 {p90} max {mx}")
    print("Gerados:")
    print(f"  {cov_tsv}")
    print(f"  {cov_int}")
    print(f"  {tree_aln_path}")

if __name__ == "__main__":
    main()
