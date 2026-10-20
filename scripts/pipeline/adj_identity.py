#!/usr/bin/env python3
import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path

# Adiciona o diretório lib ao path para importar logging_utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from logging_utils import log_fatal, log_info, log_warning, set_context



def parse_fasta_lengths(path: Path):
    lengths = {}
    current = None
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                current = line[1:].split()[0]
                lengths[current] = 0
            elif current is not None:
                lengths[current] += len(line)
    return lengths


def compute_adjusted(blast_path: Path, contigs_path: Path, out_path: Path):
    if blast_path.resolve() == out_path.resolve() or contigs_path.resolve() == out_path.resolve():
        log_fatal("arquivo de entrada e saida nao podem ser o mesmo", "Use um caminho de saida separado.")
    try:
        qlens = parse_fasta_lengths(contigs_path)
    except FileNotFoundError:
        log_fatal(f"Arquivo FASTA de contigs nao encontrado: {contigs_path}", "Verifique se a etapa de montagem foi concluida com sucesso.")
    except Exception as exc:
        log_fatal(f"Erro ao ler arquivo FASTA {contigs_path}: {exc}", "Inspecione o log do pipeline.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{out_path.name}.", suffix=".tmp", dir=out_path.parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as out, blast_path.open(
            "r", encoding="utf-8", errors="strict"
        ) as blast_in:
            reader = csv.reader(blast_in, delimiter="\t")
            writer = csv.writer(out, delimiter="\t", lineterminator="\n")
            writer.writerow([
                "qseqid",
                "sseqid",
                "pident",
                "length",
                "evalue",
                "bitscore",
                "qlen",
                "aln_cov",
                "adj_identity",
            ])

            for row in reader:
                if len(row) < 12:
                    continue
                qseqid, sseqid = row[0], row[1]
                evalue, bitscore = row[10], row[11]
                try:
                    pident = float(row[2])
                    aln_len = float(row[3])
                    float(evalue)
                    float(bitscore)
                except ValueError as exc:
                    print(f"[AVISO] linha BLAST ignorada: {exc}", file=sys.stderr)
                    continue
                fasta_qlen = qlens.get(qseqid)
                if not fasta_qlen:
                    raise ValueError(f"query BLAST ausente do FASTA: {qseqid}")
                if len(row) >= 13 and row[12].strip():
                    try:
                        qlen = float(row[12])
                    except ValueError:
                        qlen = float(fasta_qlen)
                else:
                    qlen = float(fasta_qlen)
                if int(qlen) != fasta_qlen:
                    raise ValueError(
                        f"qlen do BLAST diverge do FASTA para {qseqid}: {qlen} != {fasta_qlen}"
                    )
                if len(row) >= 14:
                    qstart, qend = int(row[6]), int(row[7])
                    if min(qstart, qend) < 1 or max(qstart, qend) > qlen:
                        raise ValueError(f"coordenadas BLAST fora da query: {qseqid}")
                    aligned_query_bp = abs(qend - qstart) + 1
                else:
                    aligned_query_bp = aln_len
                aln_cov = (aligned_query_bp / qlen) if qlen > 0 else 0.0
                adj_identity = pident * aln_cov
                writer.writerow(
                    [
                        qseqid,
                        sseqid,
                        f"{pident:.3f}",
                        f"{int(aln_len)}",
                        evalue,
                        bitscore,
                        f"{int(qlen)}",
                        f"{aln_cov:.5f}",
                        f"{adj_identity:.3f}",
                    ]
                )
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_path, out_path)
    except FileNotFoundError:
        log_fatal(f"Arquivo TSV do BLAST nao encontrado: {blast_path}", "Verifique se a etapa de BLAST contra o banco viral foi concluida com sucesso.")
    except Exception as exc:
        log_fatal(f"Erro ao ler ou escrever arquivos em adj_identity.py: {exc}", "Inspecione os caminhos e permissoes de escrita/leitura.")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def main():
    parser = argparse.ArgumentParser(description="Calcula identidade ajustada por cobertura de alinhamento")
    parser.add_argument("--blast", required=True, help="TSV BLAST outfmt 6 (12 colunas)")
    parser.add_argument("--contigs", required=True, help="FASTA de contigs")
    parser.add_argument("--out", required=True, help="TSV de saída com aln_cov e adj_identity")
    args = parser.parse_args()

    set_context(etapa="CLASSIFICACAO")
    compute_adjusted(Path(args.blast), Path(args.contigs), Path(args.out))


if __name__ == "__main__":
    main()
