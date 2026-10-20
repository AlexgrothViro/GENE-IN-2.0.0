#!/usr/bin/env python3
import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from input_validation import iter_fasta, validate_sample_id

def read_fasta(file_path):
    return [(f">{name}", sequence) for name, sequence in iter_fasta(Path(file_path))]


def write_atomic(path, content):
    path = Path(path)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)

def main():
    parser = argparse.ArgumentParser(description="Extract and deduplicate short fragments from FASTA file.")
    parser.add_argument("--input", required=True, help="Input FASTA file")
    parser.add_argument("--sample", required=True, help="Sample name")
    parser.add_argument("--min-len", type=int, default=20, help="Minimum sequence length")
    parser.add_argument("--max-len", type=int, default=100, help="Maximum sequence length")
    parser.add_argument("--out-dir", default="results/short_fragments", help="Output directory")
    parser.add_argument("--dedup", action="store_true", help="Deduplicate exact sequences")

    args = parser.parse_args()

    try:
        args.sample = validate_sample_id(args.sample)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(2)
    if args.min_len < 20 or args.max_len < args.min_len:
        print("[ERROR] intervalo invalido: fragmentos exploratorios comecam em 20 bp", file=sys.stderr)
        sys.exit(2)

    if not os.path.exists(args.input):
        print(f"[ERROR] Input file {args.input} does not exist.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)

    # Read FASTA
    try:
        sequences = read_fasta(args.input)
    except Exception as e:
        print(f"[ERROR] Failed to read FASTA file: {e}", file=sys.stderr)
        sys.exit(1)

    total_sequences = len(sequences)
    kept_sequences = []

    for header, seq in sequences:
        seq_len = len(seq)
        if args.min_len <= seq_len <= args.max_len:
            kept_sequences.append((header, seq))

    # Write output FASTA (bruto)
    out_fasta = os.path.join(args.out_dir, f"{args.sample}_short_fragments.fa")
    try:
        write_atomic(out_fasta, "".join(f"{header}\n{seq}\n" for header, seq in kept_sequences))
    except Exception as e:
        print(f"[ERROR] Failed to write output FASTA file: {e}", file=sys.stderr)
        sys.exit(1)

    # Deduplication logic if active
    unique_sequences_count = "N/A"
    if args.dedup:
        seq_map = {}
        seq_order = []
        for header, seq in kept_sequences:
            seq_upper = seq.upper()
            if seq_upper not in seq_map:
                seq_map[seq_upper] = {
                    'header': header,
                    'seq': seq,
                    'count': 1,
                    'length': len(seq)
                }
                seq_order.append(seq_upper)
            else:
                seq_map[seq_upper]['count'] += 1

        unique_sequences_count = len(seq_order)

        # Write unique FASTA
        unique_fasta = os.path.join(args.out_dir, f"{args.sample}_short_fragments_unique.fa")
        try:
            write_atomic(unique_fasta, "".join(
                f">{args.sample}|unique_{idx:06d}|count={item['count']}|representative={item['header'].lstrip('>')}\n{item['seq']}\n"
                for idx, item in enumerate((seq_map[s] for s in seq_order), 1)
            ))
        except Exception as e:
            print(f"[ERROR] Failed to write output unique FASTA file: {e}", file=sys.stderr)
            sys.exit(1)

        # Write dedup TSV
        dedup_tsv = os.path.join(args.out_dir, f"{args.sample}_short_fragments_dedup.tsv")
        try:
            write_atomic(dedup_tsv, "".join(
                ["sample\tunique_id\tcount\tlength\trepresentative_header\n"] + [
                    f"{args.sample}\tunique_{idx:06d}\t{item['count']}\t{item['length']}\t{item['header'].lstrip('>')}\n"
                    for idx, item in enumerate((seq_map[s] for s in seq_order), 1)
                ]
            ))
        except Exception as e:
            print(f"[ERROR] Failed to write output dedup TSV file: {e}", file=sys.stderr)
            sys.exit(1)

    # Write output stats TSV
    out_tsv = os.path.join(args.out_dir, f"{args.sample}_short_fragments_stats.tsv")
    try:
        write_atomic(out_tsv, "sample\tinput_fasta\tmin_len\tmax_len\ttotal_sequences\tkept_sequences\tunique_sequences\n" +
                     f"{args.sample}\t{os.path.basename(args.input)}\t{args.min_len}\t{args.max_len}\t{total_sequences}\t{len(kept_sequences)}\t{unique_sequences_count}\n")
    except Exception as e:
        print(f"[ERROR] Failed to write output stats TSV file: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Short fragment extraction complete for sample {args.sample}:")
    print(f"  - Input FASTA: {args.input} ({total_sequences} sequences)")
    print(f"  - Kept sequences: {len(kept_sequences)} (range {args.min_len}-{args.max_len} bp)")
    if args.dedup:
        print(f"  - Deduplicated unique sequences: {unique_sequences_count}")
        print(f"  - Saved Unique FASTA: {unique_fasta}")
        print(f"  - Saved Dedup TSV: {dedup_tsv}")
    print(f"  - Saved Bruto FASTA: {out_fasta}")
    print(f"  - Saved stats: {out_tsv}")

if __name__ == "__main__":
    main()
