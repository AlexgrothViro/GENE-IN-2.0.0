#!/usr/bin/env python3
import sys

def read_fasta(path):
    seqs = {}
    header = None
    chunks = []
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    seqs[header] = "".join(chunks)
                header = line[1:].split()[0]
                chunks = []
            else:
                chunks.append(line)
    if header is not None:
        seqs[header] = "".join(chunks)
    return seqs

def main():
    if len(sys.argv) != 8:
        sys.stderr.write(
            "Uso: build_ptv_region_fasta.py <ptv_report.tsv> <ptv_fragments.fa> "
            "<ptv_db.fa> <saida_region.fa> <ref_id> <start> <end>\n"
        )
        sys.exit(1)

    tsv_path, frag_fa, ref_fa, out_fa, ref_id, start_s, end_s = sys.argv[1:]
    start = int(start_s)
    end = int(end_s)
    if start < 1 or end < start:
        sys.stderr.write("Erro: coordenadas inválidas: start=%d end=%d\n" % (start, end))
        sys.exit(1)

    # Carregar referências PTV
    ref_seqs = read_fasta(ref_fa)
    if ref_id not in ref_seqs:
        sys.stderr.write(
            f"Erro: ID de referência '{ref_id}' não encontrado em {ref_fa}.\n"
        )
        sys.stderr.write(
            "Certifique-se de usar o identificador exato (ex: KX686489.1).\n"
        )
        sys.exit(1)

    ref_seq = ref_seqs[ref_id]
    if end > len(ref_seq):
        sys.stderr.write(
            f"Aviso: end={end} > tamanho da sequência ({len(ref_seq)}). "
            "Usando o final da sequência.\n"
        )
        end = len(ref_seq)

    # Carregar fragmentos (saída do emit_ptv_hit_fragments.py)
    frag_seqs = read_fasta(frag_fa)

    # Indexar fragmentos por (qseqid, sseqid)
    index = {}
    for fid, seq in frag_seqs.items():
        parts = fid.split("|")
        if len(parts) < 2:
            continue
        qid = parts[0]
        sid = parts[1]
        key = (qid, sid)
        if key not in index:
            index[key] = (fid, seq)

    selected = {}

    # Ler tabela ptv_report.tsv
    with open(tsv_path) as fh:
        header = fh.readline().rstrip("\n").split("\t")
        col = {name: i for i, name in enumerate(header)}
        required = ["qseqid", "sseqid", "sstart", "send", "label"]
        for r in required:
            if r not in col:
                sys.stderr.write(
                    f"Erro: coluna '{r}' não encontrada em {tsv_path}.\n"
                )
                sys.exit(1)

        for line in fh:
            if not line.strip():
                continue
            fields = line.rstrip("\n").split("\t")

            sseqid = fields[col["sseqid"]]
            if sseqid != ref_id:
                continue

            label = fields[col["label"]]
            if label not in ("PASS", "SHORT_PASS", "REVIEW"):
                continue

            sstart = int(fields[col["sstart"]])
            send = int(fields[col["send"]])
            lo = min(sstart, send)
            hi = max(sstart, send)

            # Verifica sobreposição com a janela [start, end]
            if hi < start or lo > end:
                continue

            qseqid = fields[col["qseqid"]]
            key = (qseqid, sseqid)
            if key in index:
                fid, seq = index[key]
                selected[fid] = seq

    # Escrever FASTA de saída
    with open(out_fa, "w") as out:
        region_header = f"{ref_id}|region_{start}_{end}"
        region_seq = ref_seq[start - 1 : end]

        out.write(f">{region_header}\n")
        for i in range(0, len(region_seq), 60):
            out.write(region_seq[i : i + 60] + "\n")

        for fid, seq in sorted(selected.items()):
            out.write(f">{fid}\n")
            for i in range(0, len(seq), 60):
                out.write(seq[i : i + 60] + "\n")

    sys.stderr.write(
        f"[OK] Escrito {out_fa} com 1 sequência de referência + "
        f"{len(selected)} fragmentos.\n"
    )

if __name__ == "__main__":
    main()
