#!/usr/bin/env python3
"""Check the actual Bowtie2 index against the declared FASTA and BLAST loci."""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import tempfile
from pathlib import Path

try:
    from .common import read_fasta, read_tsv, parse_intervals, sha256_file, write_json_atomic
except ImportError:
    from common import read_fasta, read_tsv, parse_intervals, sha256_file, write_json_atomic


def index_sequence(sequence: str) -> str:
    # Bowtie2 stores ambiguous reference bases as N. Do not claim identity of
    # the original ambiguity codes: compare the sequences the mapper can use.
    return ''.join(base if base in 'ACGT' else 'N' for base in sequence.upper())


def validate(index: str, reference: str, loci_path: str | None) -> dict:
    reference_sequences = read_fasta(reference)
    if not reference_sequences or any(not seq for seq in reference_sequences.values()):
        raise ValueError('reference FASTA is empty or contains an empty sequence')
    with tempfile.TemporaryDirectory(prefix='genein-index-check-') as temp:
        inspected = Path(temp) / 'index.fa'
        with inspected.open('w') as handle:
            subprocess.run(['bowtie2-inspect', index], stdout=handle, check=True)
        indexed = read_fasta(inspected)
    if set(reference_sequences) != set(indexed):
        raise ValueError('reference FASTA and Bowtie2 index have different sequence IDs')
    for name, sequence in reference_sequences.items():
        if index_sequence(sequence) != indexed[name].upper():
            raise ValueError(f'reference FASTA and Bowtie2 index sequence mismatch: {name}')
    loci = read_tsv(loci_path) if loci_path else []
    for locus in loci:
        name = locus['sseqid']
        if name not in reference_sequences:
            raise ValueError(f"locus {locus['locus_id']} references unknown sequence {name}")
        length = len(reference_sequences[name])
        if locus.get('reference_length') and int(locus['reference_length']) != length:
            raise ValueError(f"locus {locus['locus_id']} reference length differs from FASTA/index")
        intervals = parse_intervals(locus['reference_intervals'])
        if not intervals or any(left < 1 or right < left or right > length for left, right in intervals):
            raise ValueError(f"locus {locus['locus_id']} interval outside reference bounds")
    return {
        'status': 'VALIDATED', 'index_prefix': str(Path(index).resolve()),
        'reference_fasta': str(Path(reference).resolve()), 'reference_sha256': sha256_file(reference),
        'comparison': 'IDs and full indexed sequences; non-ACGT FASTA bases normalized to N',
        'locus_count': len(loci),
        'sequences': {name: {'length': len(seq), 'indexed_sequence_sha256': hashlib.sha256(index_sequence(seq).encode()).hexdigest()} for name, seq in reference_sequences.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--loci')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    write_json_atomic(args.out, validate(args.index, args.reference, args.loci))


if __name__ == '__main__':
    main()
