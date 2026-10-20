#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path


SEED = 1729


def random_dna(rng: random.Random, length: int) -> str:
    return "".join(rng.choice("ACGT") for _ in range(length))


def reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def mutate(sequence: str, every: int) -> str:
    bases = "ACGT"
    chars = list(sequence)
    for index in range(every - 1, len(chars), every):
        chars[index] = bases[(bases.index(chars[index]) + 1) % 4]
    return "".join(chars)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_fastq(path: Path, records: list[tuple[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for name, sequence in records:
            handle.write(f"@{name}\n{sequence}\n+\n{'I' * len(sequence)}\n")


def pair(sequence: str, start: int, read_length: int, insert: int | None = None) -> tuple[str, str]:
    insert = insert or max(read_length * 2 + 20, 120)
    left = sequence[start:start + read_length]
    right_start = start + insert - read_length
    right = reverse_complement(sequence[right_start:right_start + read_length])
    if len(left) != read_length or len(right) != read_length:
        raise ValueError("synthetic pair exceeds its source reference")
    return left, right


def write_matrix(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    unique_ref = random_dna(rng, 1400)
    target_ref = random_dna(rng, 1400)
    equivalent_ref = random_dna(rng, 1400)
    equivalent_ref = equivalent_ref[:250] + target_ref[250:850] + equivalent_ref[850:]
    equivalent_source = random_dna(rng, 1400)
    equivalent_twin = random_dna(rng, 1400)
    equivalent_twin = equivalent_twin[:250] + equivalent_source[250:850] + equivalent_twin[850:]
    suboptimal_ref = mutate(target_ref, 23)
    negativeome_ref = random_dna(rng, 1400)
    low_complexity_ref = "ACGT" * 350
    references = {
        "unique_ref": unique_ref,
        "target_ref": target_ref,
        "homolog_equivalent": equivalent_ref,
        "equivalent_source": equivalent_source,
        "equivalent_twin": equivalent_twin,
        "homolog_suboptimal": suboptimal_ref,
        "negativeome_synthetic": negativeome_ref,
        "low_complexity_synthetic": low_complexity_ref,
    }
    panel = output / "panel.fa"
    with panel.open("w", encoding="utf-8", newline="\n") as handle:
        for name, sequence in references.items():
            handle.write(f">{name}\n{sequence}\n")
    loci = output / "loci.tsv"
    with loci.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("locus_id\tsseqid\treference_intervals\tcategory\n")
        handle.write("unique_locus\tunique_ref\t100-399;350-500\tSYNTHETIC_TARGET\n")
        handle.write("target_shared_locus\ttarget_ref\t250-850\tSYNTHETIC_TARGET\n")
        handle.write("negativeome_locus\tnegativeome_synthetic\t1-1400\tNEGATIVEOME\n")

    r1_records: list[tuple[str, str]] = []
    r2_records: list[tuple[str, str]] = []
    cases: list[dict] = []

    def add(case: str, name: str, left: str, right: str, abundance: int, umi: str) -> None:
        qname = f"{name}#{umi}"
        r1_records.append((qname + "/1", left))
        r2_records.append((qname + "/2", right))
        cases.append({"case": case, "read_name": qname, "abundance": abundance, "read_lengths": [len(left), len(right)]})

    lengths = (20, 30, 50, 75, 100)
    scenario_lengths: dict[str, list[int]] = {}
    for index, length in enumerate(lengths):
        umi = ("AAAA", "CCCC", "GGGG", "TTTT", "ACGT")[index]
        start = 50 + index * 190
        exact_left, exact_right = pair(unique_ref, start, length)
        add("exact_unique", f"exact_{length}", exact_left, exact_right, 1, umi)

        substitution_left = list(exact_left)
        midpoint = length // 2
        substitution_left[midpoint] = "A" if substitution_left[midpoint] != "A" else "C"
        add("substitution", f"substitution_{length}", "".join(substitution_left), exact_right, 1, umi)

        insertion_source = unique_ref[start:start + length - 1]
        insertion_base = "A" if insertion_source[midpoint - 1] != "A" else "C"
        insertion_left = insertion_source[:midpoint] + insertion_base + insertion_source[midpoint:]
        add("insertion", f"insertion_{length}", insertion_left, exact_right, 1, umi)

        deletion_source = unique_ref[start:start + length + 1]
        deletion_left = deletion_source[:midpoint] + deletion_source[midpoint + 1:]
        add("deletion", f"deletion_{length}", deletion_left, exact_right, 1, umi)

        equivalent_left, equivalent_right = pair(equivalent_source, 300 + index * 50, length, 220)
        add("equivalent_homolog", f"equivalent_{length}", equivalent_left, equivalent_right, 1, umi)
        suboptimal_left, suboptimal_right = pair(target_ref, 880 + index * 35, length, 220)
        add("suboptimal_homolog", f"suboptimal_{length}", suboptimal_left, suboptimal_right, 1, umi)
        negative_left, negative_right = pair(negativeome_ref, 300 + index * 90, length, 220)
        add("negativeome_only", f"negativeome_{length}", negative_left, negative_right, 1, umi)
        low_left, low_right = pair(low_complexity_ref, 100 + index * 50, length, 220)
        add("low_complexity", f"low_complexity_{length}", low_left, low_right, 1, umi)
        for scenario in (
            "exact_unique", "substitution", "insertion", "deletion", "equivalent_homolog",
            "suboptimal_homolog", "negativeome_only", "low_complexity",
        ):
            scenario_lengths.setdefault(scenario, []).append(length)

    abundance_three_left, abundance_three_right = pair(unique_ref, 1180, 50, 220)
    for replicate, umi in enumerate(("AGCT", "TCGA", "GATC")):
        add("abundance_three", f"abundance_three_{replicate}", abundance_three_left, abundance_three_right, 3, umi)

    duplicate_left, duplicate_right = pair(unique_ref, 1000, 75, 220)
    duplicate_umis = ("AAAA", "AAAA", "CCCC", "CCCC", "GGGG", "GGGG", "TTTT", "TTTT", "ACGT", "ACGT")
    for replicate, umi in enumerate(duplicate_umis):
        add("coordinate_duplicate_umi", f"duplicate_{replicate}", duplicate_left, duplicate_right, 10, umi)

    orphan_left, _ = pair(unique_ref, 600, 75, 220)
    add("orphan", "orphan", orphan_left, random_dna(rng, 75), 1, "AGAG")
    discordant_left = unique_ref[420:495]
    discordant_right = reverse_complement(negativeome_ref[820:895])
    add("discordant", "discordant", discordant_left, discordant_right, 1, "ATAT")
    add("unmapped_pair", "unmapped_pair", random_dna(rng, 75), random_dna(rng, 75), 1, "CGCG")

    write_fastq(output / "r1.fastq", r1_records)
    write_fastq(output / "r2.fastq", r2_records)
    single_records = [
        ("single_unique#AAAA", unique_ref[150:250]),
        ("single_equivalent#CCCC", target_ref[350:450]),
        ("single_unmapped#GGGG", random_dna(rng, 100)),
    ]
    write_fastq(output / "single.fastq", single_records)

    panel_manifest = {
        "schema_version": "experimental-direct-map-panel-v1",
        "panel_id": "synthetic-competitive-panel-v1",
        "seed": SEED,
        "authorized_data": "SYNTHETIC_ONLY",
        "negativeome": {"state": "MEASURED", "reference_ids": ["negativeome_synthetic"]},
        "controls": {
            "state": "NOT_APPLICABLE",
            "reason": "Algorithmic mapping fixture has no batch-level sample controls; negativeome is registered separately."
        },
        "references": [
            {"id": name, "role": (
                "TARGET" if name in {"unique_ref", "target_ref", "equivalent_source"} else
                "HOMOLOG" if name.startswith("homolog") or name == "equivalent_twin" else
                "NEGATIVEOME" if name.startswith("negativeome") else "CHALLENGE_SEQUENCE"
            ), "length": len(sequence), "sha256_sequence": hashlib.sha256(sequence.encode()).hexdigest()}
            for name, sequence in references.items()
        ],
    }
    (output / "panel_manifest.json").write_text(
        json.dumps(panel_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    truth = {
        "schema_version": "synthetic-direct-map-truth-v1",
        "seed": SEED,
        "generator_independent_of_summarizer": True,
        "authorized_data": "SYNTHETIC_ONLY",
        "fixture_lengths_bp": [20, 30, 50, 75, 100],
        "abundances": [0, 1, 3, 10],
        "zero_abundance_case": "absent_by_construction",
        "scenario_lengths_bp": scenario_lengths,
        "cases": cases,
        "oracles": {
            "level_1": [
                "oracle_primary.sam", "oracle_placements.sam", "oracle_expected.json",
                "oracle_paired_primary.sam", "oracle_paired_placements.sam",
                "oracle_quantitative_expected.json", "contract_paired_primary.sam",
                "contract_paired_placements.sam", "contract_paired_expected.json",
                "contract_loci.tsv", "contract_filter_primary.sam",
                "contract_filter_placements.sam", "contract_filter_expected.json"
            ],
            "level_2": ["panel.fa", "r1.fastq", "r2.fastq", "single.fastq", "loci.tsv"],
        },
    }
    (output / "truth.json").write_text(
        json.dumps(truth, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    write_oracle(output)
    hashes = {
        path.name: sha256(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "hashes.json"
    }
    (output / "hashes.json").write_text(
        json.dumps({"algorithm": "SHA-256", "files": hashes}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )


def write_oracle(output: Path) -> None:
    sequence = "ACGT" * 5
    qualities = "I" * 20
    header = "@HD\tVN:1.6\tSO:unknown\n@SQ\tSN:ref_a\tLN:100\n@SQ\tSN:ref_b\tLN:100\n"
    primary_rows = [
        f"oracle_unique\t0\tref_a\t1\t42\t20M\t*\t0\t0\t{sequence}\t{qualities}\tAS:i:20",
        f"oracle_equivalent\t0\tref_a\t11\t0\t20M\t*\t0\t0\t{sequence}\t{qualities}\tAS:i:20",
        f"oracle_unequal\t0\tref_a\t21\t10\t20M\t*\t0\t0\t{sequence}\t{qualities}\tAS:i:20",
        f"oracle_unmapped\t4\t*\t0\t0\t*\t*\t0\t0\t{sequence}\t{qualities}",
    ]
    placement_rows = [
        primary_rows[0], primary_rows[1],
        f"oracle_equivalent\t256\tref_b\t11\t255\t20M\t*\t0\t0\t{sequence}\t{qualities}\tAS:i:20",
        primary_rows[2],
        f"oracle_unequal\t256\tref_b\t21\t255\t20M\t*\t0\t0\t{sequence}\t{qualities}\tAS:i:15",
        primary_rows[3],
    ]
    (output / "oracle_primary.sam").write_text(header + "\n".join(primary_rows) + "\n", encoding="utf-8", newline="\n")
    (output / "oracle_placements.sam").write_text(header + "\n".join(placement_rows) + "\n", encoding="utf-8", newline="\n")
    write_fastq(output / "oracle_reads.fastq", [
        ("oracle_unique", sequence), ("oracle_equivalent", sequence),
        ("oracle_unequal", sequence), ("oracle_unmapped", sequence),
    ])
    (output / "oracle_expected.json").write_text(json.dumps({
        "UNIQUE": 1, "EQUIVALENT_AMBIGUOUS": 1, "MULTI_UNEQUAL": 1, "UNMAPPED": 1,
        "secondary": 2, "mapq_unknown": 2, "input_reads": 4,
        "all_eligible_unknown_mapq_by_reference": {"ref_a": 0, "ref_b": 2},
        "all_eligible_state_by_reference_minimum_mapq": {
            "ref_a": {"0": "MEASURED", "10": "MEASURED", "20": "MEASURED", "30": "MEASURED"},
            "ref_b": {"0": "MEASURED", "10": "NOT_MEASURED", "20": "NOT_MEASURED", "30": "NOT_MEASURED"}
        },
        "all_eligible_mapq0": {
            "placement_count": 5,
            "ref_a": {
                "denominator_bp": 100, "depth_total": 60, "breadth_1x": 0.4, "breadth_3x": 0.0,
                "histogram": {"0": 60, "1": 20, "2": 20},
                "max_window_depth_fraction": 0.6666666666666666
            },
            "ref_b": {
                "denominator_bp": 100, "depth_total": 40, "breadth_1x": 0.3, "breadth_3x": 0.0,
                "histogram": {"0": 70, "1": 20, "2": 10}, "max_window_depth_fraction": 0.75
            }
        },
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    paired_header = "@HD\tVN:1.6\tSO:unknown\n@SQ\tSN:ref_a\tLN:100\n"
    paired_primary: list[str] = []
    paired_r1: list[tuple[str, str]] = []
    paired_r2: list[tuple[str, str]] = []
    mapped_templates = (("pair_a#AAAA", 1), ("pair_b#AAAA", 1), ("pair_c#CCCC", 1))
    mate_sequence = "ACGTA"
    mate_quality = "IIIII"
    for name, _ in mapped_templates:
        paired_primary.extend((
            f"{name}\t99\tref_a\t1\t40\t5M\t=\t4\t8\t{mate_sequence}\t{mate_quality}\tAS:i:5",
            f"{name}\t147\tref_a\t4\t40\t5M\t=\t1\t-8\t{mate_sequence}\t{mate_quality}\tAS:i:5",
        ))
        paired_r1.append((name + "/1", mate_sequence))
        paired_r2.append((name + "/2", mate_sequence))
    for name in ("unmapped_a#GGGG", "unmapped_b#GGGG"):
        paired_primary.extend((
            f"{name}\t77\t*\t0\t0\t*\t*\t0\t0\t{mate_sequence}\t{mate_quality}",
            f"{name}\t141\t*\t0\t0\t*\t*\t0\t0\t{mate_sequence}\t{mate_quality}",
        ))
        paired_r1.append((name + "/1", mate_sequence))
        paired_r2.append((name + "/2", mate_sequence))
    paired_text = paired_header + "\n".join(paired_primary) + "\n"
    (output / "oracle_paired_primary.sam").write_text(paired_text, encoding="utf-8", newline="\n")
    (output / "oracle_paired_placements.sam").write_text(paired_text, encoding="utf-8", newline="\n")
    write_fastq(output / "oracle_paired_r1.fastq", paired_r1)
    write_fastq(output / "oracle_paired_r2.fastq", paired_r2)
    (output / "oracle_quantitative_expected.json").write_text(json.dumps({
        "input_reads": 10,
        "input_templates": 5,
        "read_classes": {"UNIQUE": 6, "UNMAPPED": 4},
        "geometry": {"proper": {"templates": 3, "reads": 6}, "unmapped_pair": {"templates": 2, "reads": 4}},
        "retained_templates": {"PRE_DEDUP": 5, "POST_COORDINATE_EXCLUSION": 3, "POST_UMI": 4},
        "overlapping_mates": {
            "coordinates": [[1, 20]],
            "window_bp": 20,
            "read": {
                "denominator_bp": 20, "depth_total": 10, "breadth_1x": 0.4, "breadth_3x": 0.0,
                "histogram": {"0": 12, "1": 6, "2": 2}, "max_window_depth_fraction": 1.0
            },
            "template": {
                "denominator_bp": 20, "depth_total": 8, "breadth_1x": 0.4, "breadth_3x": 0.0,
                "histogram": {"0": 12, "1": 8}, "max_window_depth_fraction": 1.0
            }
        },
        "disjoint_window": {
            "reference_length": 100, "intervals": [[1, 20], [81, 100]],
            "covered_positions": [16, 17, 18, 19, 20, 81, 82, 83, 84, 85],
            "window_bp": 20, "denominator_bp": 40, "depth_total": 10,
            "histogram": {"0": 30, "1": 10}, "max_window_depth_fraction": 0.5,
            "zero_run_count": 2, "max_zero_run_bp": 15, "covered_intervals": "16-20;81-85"
        },
        "window_not_applicable": {"denominator_bp": 10, "window_bp": 20, "state": "NOT_APPLICABLE"},
        "not_measured": {"denominator_bp": 20, "measurement_state": "NOT_MEASURED"}
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    contract_name = "contract_pair#AAAA"
    contract_sequence = "ACGT" * 5
    contract_quality = "I" * 20
    contract_header = "@HD\tVN:1.6\tSO:unknown\n@SQ\tSN:unique_ref\tLN:1400\n"
    contract_primary_rows = [
        f"{contract_name}\t99\tunique_ref\t100\t40\t20M\t=\t120\t40\t{contract_sequence}\t{contract_quality}\tAS:i:20",
        f"{contract_name}\t147\tunique_ref\t120\t40\t20M\t=\t100\t-40\t{contract_sequence}\t{contract_quality}\tAS:i:20",
    ]
    contract_placement_rows = [
        f"{contract_name}\t99\tunique_ref\t100\t255\t20M\t=\t120\t40\t{contract_sequence}\t{contract_quality}\tAS:i:20",
        f"{contract_name}\t147\tunique_ref\t120\t40\t20M\t=\t100\t-40\t{contract_sequence}\t{contract_quality}\tAS:i:20",
    ]
    (output / "contract_paired_primary.sam").write_text(
        contract_header + "\n".join(contract_primary_rows) + "\n", encoding="utf-8", newline="\n"
    )
    (output / "contract_paired_placements.sam").write_text(
        contract_header + "\n".join(contract_placement_rows) + "\n", encoding="utf-8", newline="\n"
    )
    write_fastq(output / "contract_paired_r1.fastq", [(contract_name + "/1", contract_sequence)])
    write_fastq(output / "contract_paired_r2.fastq", [(contract_name + "/2", contract_sequence)])
    (output / "contract_paired_expected.json").write_text(json.dumps({
        "all_eligible_mapq0_template_state": "MEASURED",
        "all_eligible_positive_template_state": "NOT_MEASURED",
        "all_eligible_positive_reason_contains": "placement MAPQ is unknown (255)",
        "primary_mapq": 40,
        "placement_mapqs": [40, 255],
        "pairing_invalid_pnext_count": 0,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    filter_loci = output / "contract_loci.tsv"
    filter_loci.write_text(
        "locus_id\tsseqid\treference_intervals\tcategory\n"
        "contract_locus_b\tunique_ref\t91-110\tSYNTHETIC_TARGET\n",
        encoding="utf-8", newline="\n",
    )
    filter_name = "contract_filter#BBBB"
    filter_primary_rows = [
        f"{filter_name}\t99\tunique_ref\t100\t40\t20M\t=\t120\t40\t{contract_sequence}\t{contract_quality}\tAS:i:20",
        f"{filter_name}\t147\tunique_ref\t120\t5\t20M\t=\t100\t-40\t{contract_sequence}\t{contract_quality}\tAS:i:20",
    ]
    (output / "contract_filter_primary.sam").write_text(
        contract_header + "\n".join(filter_primary_rows) + "\n", encoding="utf-8", newline="\n"
    )
    (output / "contract_filter_placements.sam").write_text(
        contract_header + "\n".join(filter_primary_rows) + "\n", encoding="utf-8", newline="\n"
    )
    write_fastq(output / "contract_filter_r1.fastq", [(filter_name + "/1", contract_sequence)])
    write_fastq(output / "contract_filter_r2.fastq", [(filter_name + "/2", contract_sequence)])
    (output / "contract_filter_expected.json").write_text(json.dumps({
        "all_eligible_mapq20_template_state": "MEASURED",
        "locus_b_template_state": "MEASURED",
        "pairing_invalid_pnext_count": 0,
        "ref_region_filtered_mate_count": 1,
        "ref_region_filtered_mate_reasons": {"MAPQ": 1},
        "locus_b_filtered_mate_count": 1,
        "locus_b_filtered_mate_reasons": {"REGION": 1},
        "placement_mapqs": [5, 40],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic direct-map matrix and independent oracles")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit("output directory must be absent or empty")
    write_matrix(args.out)


if __name__ == "__main__":
    main()
