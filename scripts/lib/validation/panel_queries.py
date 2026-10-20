"""Deterministic synthetic queries and competitive references for Validation pipeline panels.

Construction is documented; BLAST bitscores are empirical. Fixtures do not assert
TARGET_SPECIFIC, a numeric delta, recovery, or false-positive outcome.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


# Legacy seeds used by optimization-contract fixtures (not pipeline BLAST).
TARGET_SEED = "ACGTCAGTGCATGACCTGACTAGCATCGTACGATGCTAGCTGACGTACGTCAGTGCATG"
HOST_SEED = "ACGTCAGTGCATGACCTGACTAGCATCGTACGATGCTAGCTGACGTACGTCAGAAAAAA"
NEIGHBOR_SEED = "ACGTCAGTGCATGACCTGACTAGCATCGTACGATGCTAGCTGACGTACTCAGTGCATG"

# Pipeline BLAST references. Unique block (0–99) is unrelated across subjects so
# length-ladder target queries probe recovery and candidate-class, not a
# near-threshold competitive margin. Competitive windows are 50 bp blocks
# starting at offset 100; each is similar to only one non-target subject.
UNIQUE_TARGET = (
    "GCTAGATCGTACCTGAAGCT"
    "TAGCCGATTCAGGTACATGC"
    "AAGCTGTCCGATTAGCACGT"
    "CGTATCGAAGCTTGACCGAT"
    "GATCCTAGCTGCGATACCTT"
)
UNIQUE_HOST = (
    "TGCATGCAAGCTTGGTACCA"
    "GATTCGCTAGGATCCTAGAC"
    "CATGGTAGCTTAACCGATGC"
    "AGCTTGCCATGGTATCGAAT"
    "CCGTAGCTTGAATCGTACCA"
)
UNIQUE_NEIGHBOR = (
    "ACGTGCCTTAAGCTGATCCA"
    "TTGACGGTACCTAGCATCGA"
    "GCTTAACCTGGATCGTACAT"
    "CCATGCTTAGGAACGTCTAG"
    "ATCGGTACCTTGCAAGCTGA"
)

# 50 bp competitive windows. Substitutions are transversions at positions that
# leave ≥11 consecutive matches (blastn word_size) on both sides.
WINDOW_HOST_1MM = "ATGCCGATTAGGCTACAGTTCGTAAGCTTGATCCAGTACGTTGCACGATC"
WINDOW_HOST_2MM = "GATCCTAGCTGACGTACGTTACGTGCTTAGCTAGGATCGATGCATACGTG"
WINDOW_NEIGH_3MM = "TGCATACGTTGACCTAGCTAGACTAGCATCGTACGATGCTAGCTTGACGT"
WINDOW_NEIGH_4MM = "CGTAAGCTTGATCCGTACATGCAAGCTTGGATCCTAGTACGTTGCATGCA"
WINDOW_FP_MID = "TACGGTCCAATTGCGATCGTACCTTGCAAGCTGGTACCAGATTCGTACGA"

# 50 bp subject window used to probe blastn-short vs conventional at 49 bp.
# The query is this prefix with transversions every 10 bp so exact 11-mers
# break while 7-mers remain. Outcome is empirical.
WINDOW_ROUTE_50 = "GTACCGAATGCCTTAGATCGCAAGGTCTTAACCGATGCTAGATCGTACCA"

# Host/neighbor versions: 1, 2, 3, or 4 transversions. The pipeline measures the
# resulting BLAST delta; mismatch counts are a construction hypothesis around
# minimum_delta_bitscore 5/10/15, not an asserted outcome.
# WINDOW_HOST_1MM[12] = C → A
# WINDOW_HOST_2MM[12] = C → A, [24] = T → A
# WINDOW_NEIGH_3MM[12] = C → A, [24] = A → C, [36] = C → A
# WINDOW_NEIGH_4MM[12] = C → A, [24] = G → T, [36] = G → T, [48] = C → A
# WINDOW_FP_MID[12] = G → T, [24] = T → A  (host competitor for the delta-5 FP decoy)
# WINDOW_ROUTE_50 query transversions at 9, 19, 29, 39 (G→T / G→C / A→C / A→C)
HOST_1MM_POS = {12: "A"}
HOST_2MM_POS = {12: "A", 24: "A"}
NEIGH_3MM_POS = {12: "A", 24: "C", 36: "A"}
NEIGH_4MM_POS = {12: "A", 24: "T", 36: "T", 48: "A"}
FP_MID_HOST_POS = {12: "T", 24: "A"}
ROUTE_QUERY_POS = {9: "T", 19: "C", 29: "C", 39: "C"}


def _mutate(seq: str, substitutions: dict[int, str]) -> str:
    chars = list(seq)
    for index, base in substitutions.items():
        if chars[index] == base:
            raise ValueError(f"substitution at {index} does not change the base")
        chars[index] = base
    return "".join(chars)


def _require_length(name: str, seq: str, expected: int) -> str:
    if len(seq) != expected:
        raise ValueError(f"{name} length {len(seq)} != {expected}")
    return seq


_require_length("WINDOW_HOST_1MM", WINDOW_HOST_1MM, 50)
_require_length("WINDOW_HOST_2MM", WINDOW_HOST_2MM, 50)
_require_length("WINDOW_NEIGH_3MM", WINDOW_NEIGH_3MM, 50)
_require_length("WINDOW_NEIGH_4MM", WINDOW_NEIGH_4MM, 50)
_require_length("WINDOW_FP_MID", WINDOW_FP_MID, 50)
_require_length("WINDOW_ROUTE_50", WINDOW_ROUTE_50, 50)
_require_length("UNIQUE_TARGET", UNIQUE_TARGET, 100)
_require_length("UNIQUE_HOST", UNIQUE_HOST, 100)
_require_length("UNIQUE_NEIGHBOR", UNIQUE_NEIGHBOR, 100)

HOST_WINDOW_1MM = _mutate(WINDOW_HOST_1MM, HOST_1MM_POS)
HOST_WINDOW_2MM = _mutate(WINDOW_HOST_2MM, HOST_2MM_POS)
NEIGHBOR_WINDOW_3MM = _mutate(WINDOW_NEIGH_3MM, NEIGH_3MM_POS)
NEIGHBOR_WINDOW_4MM = _mutate(WINDOW_NEIGH_4MM, NEIGH_4MM_POS)
HOST_WINDOW_FP_MID = _mutate(WINDOW_FP_MID, FP_MID_HOST_POS)
ROUTE_QUERY_49 = _mutate(WINDOW_ROUTE_50[:49], ROUTE_QUERY_POS)
_require_length("ROUTE_QUERY_49", ROUTE_QUERY_49, 49)

UNRELATED_50_A = "CCGTAGCTTAACCTGGATCGTACATGCAAGCTTGGTACCAGATTCGCTAG"
UNRELATED_50_B = "AGGTATCGAATCCGTAGCTTGATCGTACCATGCAAGCTTGGATCCTAGTA"
UNRELATED_50_C = "TTGACCGATGCTAGATCGTACCTTGCATGCAAGCTTGGTACCAGATTCGT"
UNRELATED_50_D = "CATGGTAGCTTAACCGATGCAGCTTGCCATGGTATCGAATCCGTAGCTTA"
UNRELATED_50_E = "GCTTAACCGATGCCATGGTATCGAATCCGTAGCTTACGTGCTTAGCTAGC"
UNRELATED_50_F = "ATCGTACCATGCAAGCTTGGTACCAGATTCGCTAGGATCCTAGCTGACGT"
UNRELATED_50_G = "TTGCAAGCTTGGTACCAGATTCGTACCTTGCATGGTAGCTTAACCGATGC"
_require_length("UNRELATED_50_E", UNRELATED_50_E, 50)
_require_length("UNRELATED_50_F", UNRELATED_50_F, 50)
_require_length("UNRELATED_50_G", UNRELATED_50_G, 50)

TARGET_REF = (
    UNIQUE_TARGET
    + WINDOW_HOST_1MM
    + WINDOW_HOST_2MM
    + WINDOW_NEIGH_3MM
    + WINDOW_ROUTE_50
    + WINDOW_NEIGH_4MM
    + WINDOW_FP_MID
)
HOST_REF = UNIQUE_HOST + HOST_WINDOW_1MM + UNRELATED_50_A + UNRELATED_50_B + UNRELATED_50_E + UNRELATED_50_F + HOST_WINDOW_FP_MID
HOST_REF_2MM = UNIQUE_HOST + UNRELATED_50_C + HOST_WINDOW_2MM + UNRELATED_50_D + UNRELATED_50_G + UNRELATED_50_A + UNRELATED_50_C
NEIGHBOR_REF = (
    UNIQUE_NEIGHBOR
    + UNRELATED_50_B
    + UNRELATED_50_D
    + NEIGHBOR_WINDOW_3MM
    + UNRELATED_50_E
    + NEIGHBOR_WINDOW_4MM
    + UNRELATED_50_G
)

PANEL_REFERENCES = (
    ("target_ref", TARGET_REF, "TARGET_VIRUS", "synthetic_target"),
    ("host_ref", HOST_REF, "HOST", "synthetic_host"),
    ("host_ref_2mm", HOST_REF_2MM, "HOST", "synthetic_host"),
    ("neighbor_ref", NEIGHBOR_REF, "NEAR_NON_TARGET_VIRUS", "synthetic_neighbor"),
)

LENGTH_LADDER_BP = (29, 30, 35, 39, 40, 49, 50, 51, 79, 100)
PRESERVED_LADDER_BP = (29, 40, 49, 79, 100)
ADDED_LADDER_BP = (30, 35, 39, 50, 51)


def _slice_or_repeat(seed: str, length: int) -> str:
    if length <= len(seed):
        return seed[:length]
    return (seed * ((length // len(seed)) + 1))[:length]


def sequence_for_recipe(recipe: str, length: int) -> str:
    builders = {
        "target_unique_prefix": lambda: _slice_or_repeat(UNIQUE_TARGET, length),
        "target_window_host_1mm": lambda: WINDOW_HOST_1MM[:length],
        "target_window_host_2mm": lambda: WINDOW_HOST_2MM[:length],
        "target_window_neigh_3mm": lambda: WINDOW_NEIGH_3MM[:length],
        "target_window_neigh_4mm": lambda: WINDOW_NEIGH_4MM[:length],
        "target_window_route_49": lambda: ROUTE_QUERY_49 if length == 49 else ROUTE_QUERY_49[:length],
        "target_window_fp_mid": lambda: WINDOW_FP_MID[:length],
        "host_window_1mm": lambda: HOST_WINDOW_1MM[:length],
        "host_window_2mm": lambda: HOST_WINDOW_2MM[:length],
        "host_window_fp_mid": lambda: HOST_WINDOW_FP_MID[:length],
        "neighbor_window_3mm": lambda: NEIGHBOR_WINDOW_3MM[:length],
        "neighbor_window_4mm": lambda: NEIGHBOR_WINDOW_4MM[:length],
        "contaminant_poly_t": lambda: "T" * length,
    }
    if recipe not in builders:
        raise ValueError(f"Unknown pipeline query recipe: {recipe}")
    seq = builders[recipe]()
    if len(seq) != length:
        raise ValueError(f"recipe {recipe} produced {len(seq)} bp, expected {length}")
    return seq


def sequence_for_category(category: str, length: int) -> str:
    seed = {
        "TARGET_VIRUS": TARGET_SEED,
        "HOST": HOST_SEED,
        "NEAR_NON_TARGET_VIRUS": NEIGHBOR_SEED,
        "KNOWN_CONTAMINANT": "TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT",
        "LOW_COMPLEXITY": "AAAAAC" * 20,
    }.get(category, "NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN")
    return _slice_or_repeat(seed, length)


def sequence_for_entry(entry: dict[str, Any]) -> str:
    length = int(entry["length_bp"])
    explicit = entry.get("query_sequence")
    if explicit:
        seq = str(explicit).strip().upper()
        if len(seq) != length:
            raise ValueError(f"{entry.get('sample_id')}: query_sequence length {len(seq)} != {length}")
        return seq
    recipe = entry.get("recipe")
    if recipe:
        return sequence_for_recipe(str(recipe), length)
    return sequence_for_category(str(entry["category"]), length)


def write_query_fasta(
    path: Path,
    sample_id: str,
    category: str,
    length: int,
    *,
    sequence: str | None = None,
    recipe: str | None = None,
) -> str:
    if sequence:
        seq = sequence
    elif recipe:
        seq = sequence_for_recipe(recipe, length)
    else:
        seq = sequence_for_category(category, length)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f">{sample_id}\n{seq}\n", encoding="utf-8")
    return seq


def write_competition_panel(path: Path, target_seq: str, host_seq: str, neighbor_seq: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                ">target_ref",
                target_seq,
                ">host_ref",
                host_seq,
                ">neighbor_ref",
                neighbor_seq,
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_pipeline_panel_fasta(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for seqid, seq, _category, _taxon in PANEL_REFERENCES:
        lines.extend([f">{seqid}", seq])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_labels(path: Path) -> None:
    rows = ["sseqid\tcategory\ttaxon\tsegment"]
    for seqid, _seq, category, taxon in PANEL_REFERENCES:
        rows.append(f"{seqid}\t{category}\t{taxon}\tunsegmented")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def panel_fingerprint(category: str, length: int) -> str:
    payload = f"{category}:{length}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def construction_catalog() -> dict[str, Any]:
    """Machine-readable description of how pipeline fixtures were built."""
    return {
        "schema_version": "validation-panel-construction-v1",
        "disclaimer": (
            "Construction describes how sequences were assembled. "
            "It does not assert BLAST bitscores, specificity_status, recovery, or FP/FN."
        ),
        "reference_lengths": {seqid: len(seq) for seqid, seq, _c, _t in PANEL_REFERENCES},
        "unique_block_bp": 100,
        "competitive_windows": {
            "host_1mm": {
                "target_window": WINDOW_HOST_1MM,
                "host_window": HOST_WINDOW_1MM,
                "substitutions": {str(k): v for k, v in HOST_1MM_POS.items()},
                "design_intent": (
                    "One transversion in a 50 bp window so conventional blastn "
                    "margin may fall near minimum_delta_bitscore=5. Empirical."
                ),
            },
            "host_2mm": {
                "target_window": WINDOW_HOST_2MM,
                "host_window": HOST_WINDOW_2MM,
                "substitutions": {str(k): v for k, v in HOST_2MM_POS.items()},
                "design_intent": (
                    "Two transversions so conventional blastn margin may fall "
                    "near minimum_delta_bitscore=10. Empirical."
                ),
            },
            "neighbor_3mm": {
                "target_window": WINDOW_NEIGH_3MM,
                "neighbor_window": NEIGHBOR_WINDOW_3MM,
                "substitutions": {str(k): v for k, v in NEIGH_3MM_POS.items()},
                "design_intent": (
                    "Three transversions so conventional blastn margin may fall "
                    "near minimum_delta_bitscore=15. Empirical."
                ),
            },
            "neighbor_4mm": {
                "target_window": WINDOW_NEIGH_4MM,
                "neighbor_window": NEIGHBOR_WINDOW_4MM,
                "substitutions": {str(k): v for k, v in NEIGH_4MM_POS.items()},
                "design_intent": (
                    "Four transversions so conventional blastn margin may meet "
                    "or exceed minimum_delta_bitscore=15. Empirical."
                ),
            },
            "fp_mid_2mm": {
                "target_window": WINDOW_FP_MID,
                "host_window": HOST_WINDOW_FP_MID,
                "substitutions": {str(k): v for k, v in FP_MID_HOST_POS.items()},
                "design_intent": (
                    "Host-labeled decoy identical to the target 2-mismatch window "
                    "so BLAST may rank TARGET first with a margin near 5–10. Empirical."
                ),
            },
            "route_49_broken_11mer": {
                "target_window": WINDOW_ROUTE_50,
                "query_49": ROUTE_QUERY_49,
                "substitutions": {str(k): v for k, v in ROUTE_QUERY_POS.items()},
                "design_intent": (
                    "49 bp query with transversions every 10 bp so blastn-short "
                    "(word 7) may recover the target while conventional blastn "
                    "(word 11) may not. Discriminates dual_mode_max_bp 48 vs 49. Empirical."
                ),
            },
        },
    }
