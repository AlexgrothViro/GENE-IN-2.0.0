import hashlib
import json
import tempfile
import unittest
from argparse import Namespace
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.experimental.direct_map.experimental_direct_map import (
    COVERAGE_FIELDS,
    COVERAGE_SCHEMA,
    INVARIANTS_SCHEMA,
    METRICS_SCHEMA,
    OUTPUT_CONTRACTS,
    SamRecord,
    build_coverage_rows,
    cell_unknown_mapq_count,
    cigar_covered_positions,
    classify_reads,
    coverage_aggregate,
    coverage_invariant_state,
    coverage_depth,
    eligible_records,
    fastq_read_keys,
    finalize,
    geometry_rows,
    git_head,
    load_panel_manifest,
    load_profile,
    measured_metrics,
    parse_sam,
    records_overlapping_cell,
    stage_templates,
    summarize_stage_states,
    template_pairing_issue,
    template_pairing_assessment,
    template_pairing_summary,
    unavailable_metrics,
    validate_invariants,
    validate_alignment_references,
    validate_contract_identity,
)
from scripts.experimental.direct_map.experimental_direct_map import (
    BASELINE_COMPARISON,
    source_state,
)
from scripts.evidence.common import validate_artifact_manifest
from scripts.tests.evidence.generate_direct_map_matrix import write_matrix


ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / "config" / "experimental" / "direct_map_v1.json"


def record(name, flag, reference, position, mapq=40, cigar="10M", mate_reference="*", mate_position=0, score=10):
    return SamRecord(
        qname=name, flag=flag, reference=reference, position=position, mapq=mapq, cigar=cigar,
        mate_reference=mate_reference, mate_position=mate_position,
        sequence="A" * 10, qualities="I" * 10, tags={"AS": ("i", str(score))},
    )


class ExperimentalDirectMapTests(unittest.TestCase):
    def test_profile_is_complete(self):
        profile = load_profile(PROFILE)
        self.assertEqual(profile["grid"]["mapq"], [0, 10, 20, 30])
        self.assertEqual(profile["grid"]["baseq"], [0, 20, 30])
        self.assertEqual(profile["grid"]["windows_bp"], [20, 50, 100])
        self.assertEqual(profile["profile_id"], "GENEIN-EV2-DIRECT-MAP-001.profile-v1.2")
        self.assertEqual(profile["profile_revision"], "1.2")
        self.assertEqual(profile["pipeline_version"], "experimental-direct-map-1.2")
        self.assertEqual(profile["schema_version"], "experimental-direct-map-profile-v2")
        self.assertEqual(profile["output_contracts"], OUTPUT_CONTRACTS)
        self.assertNotIn("baseline", profile)
        self.assertEqual(profile["profile_compatibility"]["previous_profile_id"], "GENEIN-EV2-DIRECT-MAP-001.profile-v1.1")
        self.assertEqual(profile["profile_compatibility"]["semantic_compatibility"], "INCOMPATIBLE_MAPQ255_MEASUREMENT")
        self.assertEqual(profile["track_semantics"]["all_eligible_mapq_source"], "PLACEMENT")
        self.assertEqual(
            profile["track_semantics"]["unknown_placement_mapq"],
            "MAPQ_ZERO_INCLUDED_POSITIVE_THRESHOLDS_NOT_MEASURED",
        )
        self.assertEqual(
            profile["measurement_error_scope"]["unknown_placement_mapq"],
            "ALL_ELIGIBLE_MAPQ_ZERO_INCLUDED_POSITIVE_THRESHOLDS_PER_CELL_AFTER_STAGE_AND_FILTERS",
        )
        self.assertEqual(
            profile["measurement_error_scope"]["unknown_primary_mapq"],
            "UNIQUE_ALL_THRESHOLDS_PER_CELL_AFTER_STAGE_AND_FILTERS",
        )
        self.assertEqual(
            profile["measurement_error_scope"]["template_pairing"],
            "ALL_TEMPLATE_CELLS_PER_STAGE_TRACK_MAPQ_BASEQ_REGION_AFTER_FILTERS",
        )
        self.assertEqual(
            profile["track_semantics"]["cross_track_unique_le_all_eligible"]["mapq_zero"],
            "EVALUATE_WHEN_BOTH_CELLS_MEASURED",
        )
        with tempfile.TemporaryDirectory() as tmp:
            legacy_profile = dict(profile)
            legacy_profile["profile_id"] = "GENEIN-EV2-DIRECT-MAP-001.profile-v1"
            legacy_path = Path(tmp) / "legacy-profile.json"
            legacy_path.write_text(json.dumps(legacy_profile), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "profile identity must be"):
                load_profile(legacy_path)
            legacy_schema = dict(profile)
            legacy_schema["schema_version"] = "experimental-direct-map-profile-v1"
            legacy_path.write_text(json.dumps(legacy_schema), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "experimental-direct-map-profile-v2"):
                load_profile(legacy_path)

    def test_all_mapped_alignment_references_are_validated_before_metrics(self):
        primary = [record("known", 0, "ref_a", 1), record("ghost_primary", 0, "ref_ghost", 1)]
        placements = [
            record("known", 0, "ref_a", 1),
            record("ghost_z", 0, "ref_z", 1),
            record("ghost_b", 0, "ref_b", 1),
        ]
        with self.assertRaisesRegex(
            ValueError,
            r"primary=ref_ghost; placements=ref_b,ref_z",
        ):
            validate_alignment_references(primary, placements, {"ref_a": 20})
        validate_alignment_references([primary[0]], [placements[0]], {"ref_a": 20})

    def test_independent_gold_sam_classifies_multimapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "matrix"
            write_matrix(fixture)
            primary = parse_sam(fixture / "oracle_primary.sam")
            placements = parse_sam(fixture / "oracle_placements.sam")
            keys = [(name, 0) for name in (
                "oracle_unique", "oracle_equivalent", "oracle_unequal", "oracle_unmapped",
            )]
            classified, errors = classify_reads(keys, primary, placements)
            expected = json.loads((fixture / "oracle_expected.json").read_text(encoding="utf-8"))
        self.assertEqual(errors, [])
        counts = Counter(item["classification"] for item in classified.values())
        for name in ("UNIQUE", "EQUIVALENT_AMBIGUOUS", "MULTI_UNEQUAL", "UNMAPPED"):
            self.assertEqual(counts[name], expected[name])
        self.assertEqual(sum(item.get("secondary", 0) for item in classified.values()), expected["secondary"])
        self.assertEqual(sum(item.get("mapq_unknown", 0) for item in classified.values()), expected["mapq_unknown"])
        keep = {name for name, _ in keys}
        selected = eligible_records(placements, classified, "all_eligible", keep, 0)
        self.assertEqual(len(selected), expected["all_eligible_mapq0"]["placement_count"])
        depths = coverage_depth(selected, {"ref_a": 100, "ref_b": 100}, "READ", 0)
        for reference in ("ref_a", "ref_b"):
            flat, _ = measured_metrics(depths[reference], list(range(1, 101)), 20, [(1, 100)])
            oracle = expected["all_eligible_mapq0"][reference]
            for field in ("denominator_bp", "depth_total", "breadth_1x", "breadth_3x", "max_window_depth_fraction"):
                self.assertEqual(flat[field], oracle[field])
            self.assertEqual(json.loads(flat["histogram_json"]), oracle["histogram"])
        for reference in ("ref_a", "ref_b"):
            cell_records = records_overlapping_cell(placements, reference, list(range(1, 101)), 0)
            unknown_count = cell_unknown_mapq_count(cell_records, classified, "all_eligible", keep)
            self.assertEqual(unknown_count, expected["all_eligible_unknown_mapq_by_reference"][reference])
            observed_states = {
                str(minimum_mapq): "NOT_MEASURED" if unknown_count and minimum_mapq > 0 else "MEASURED"
                for minimum_mapq in (0, 10, 20, 30)
            }
            self.assertEqual(
                observed_states,
                expected["all_eligible_state_by_reference_minimum_mapq"][reference],
            )

    def test_unreconciled_primary_is_not_measured_instead_of_zero(self):
        primary = [record("read", 0, "ref", 1)]
        placements = [record("read", 0, "ref", 2)]
        classified, errors = classify_reads([("read", 0)], primary, placements)
        self.assertEqual(classified[("read", 0)]["measurement_state"], "NOT_MEASURED")
        self.assertIsNone(classified[("read", 0)]["classification"])
        self.assertTrue(errors)

    def test_qc_failed_alignment_is_not_reclassified_as_unmapped(self):
        qc_failed = record("read", 0x200, "ref", 1)
        classified, errors = classify_reads([("read", 0)], [], [qc_failed])
        self.assertEqual(classified[("read", 0)]["measurement_state"], "NOT_MEASURED")
        self.assertIsNone(classified[("read", 0)]["classification"])
        self.assertTrue(errors)

    def test_zero_is_measured_but_ratios_without_denominator_are_undefined(self):
        flat, structured = measured_metrics([0] * 100, list(range(1, 101)), 20)
        self.assertEqual(flat["depth_total"], 0)
        self.assertEqual(flat["breadth_1x"], 0)
        self.assertEqual(flat["covered_depth_state"], "UNDEFINED")
        self.assertEqual(flat["cv_state"], "UNDEFINED")
        self.assertEqual(structured["depth_total"]["state"], "MEASURED")
        self.assertEqual(structured["depth_total"]["value"], 0)
        histogram = {int(key): value for key, value in json.loads(flat["histogram_json"]).items()}
        self.assertEqual(histogram, {0: 100})

    def test_disjoint_intervals_do_not_share_windows_or_zero_runs(self):
        depth = [0] * 100
        for position in (16, 17, 18, 19, 20, 81, 82, 83, 84, 85):
            depth[position - 1] = 1
        coordinates = list(range(1, 21)) + list(range(81, 101))
        flat, _ = measured_metrics(depth, coordinates, 20, [(1, 20), (81, 100)])
        self.assertEqual(flat["max_window_depth_fraction"], 0.5)
        self.assertEqual(flat["zero_run_count"], 2)
        self.assertEqual(flat["max_zero_run_bp"], 15)
        self.assertEqual(flat["covered_intervals"], "16-20;81-85")

    def test_window_larger_than_region_is_not_applicable(self):
        flat, structured = measured_metrics([1] * 10, list(range(1, 11)), 20, [(1, 10)])
        self.assertEqual(flat["concentration_state"], "NOT_APPLICABLE")
        self.assertIsNone(flat["max_window_depth_fraction"])
        self.assertEqual(structured["max_window_depth_fraction"]["state"], "NOT_APPLICABLE")

    def test_not_measured_cell_preserves_known_denominator(self):
        flat, structured = unavailable_metrics("NOT_MEASURED", "reconciliation failed", 37)
        self.assertEqual(flat["denominator_bp"], 37)
        self.assertEqual(structured["denominator_bp"], {"state": "MEASURED", "value": 37, "reason": None})
        self.assertEqual(flat["depth_total"], "")

    def test_template_depth_counts_overlapping_mates_once(self):
        records = [
            record("pair", 99, "ref", 1, mate_reference="=", mate_position=6),
            record("pair", 147, "ref", 6, mate_reference="=", mate_position=1),
        ]
        read_depth = coverage_depth(records, {"ref": 30}, "READ", 0)["ref"]
        template_depth = coverage_depth(records, {"ref": 30}, "TEMPLATE", 0)["ref"]
        self.assertEqual(sum(read_depth), 20)
        self.assertEqual(sum(template_depth), 15)
        self.assertEqual(max(read_depth), 2)
        self.assertEqual(max(template_depth), 1)

    def test_coordinate_and_umi_ablations_are_explicit(self):
        inputs = [("a#AAAA", 0), ("b#AAAA", 0), ("c#CCCC", 0)]
        primary = [record(name, 0, "ref", 1) for name, _ in inputs]
        stages, states = stage_templates(inputs, primary, "read_name")
        self.assertEqual(len(stages["PRE_DEDUP"]), 3)
        self.assertEqual(len(stages["POST_COORDINATE_EXCLUSION"]), 1)
        self.assertEqual(len(stages["POST_UMI"]), 2)
        self.assertEqual(states["POST_UMI"][0], "MEASURED")
        no_umi_stages, no_umi_states = stage_templates(inputs, primary, "none")
        self.assertEqual(no_umi_stages["POST_UMI"], set())
        self.assertEqual(no_umi_states["POST_UMI"][0], "NOT_APPLICABLE")

    def test_unmapped_templates_with_same_umi_are_not_collapsed(self):
        inputs = [("mapped_a#AAAA", 0), ("mapped_b#AAAA", 0), ("unmapped_a#GGGG", 0), ("unmapped_b#GGGG", 0)]
        primary = [record("mapped_a#AAAA", 0, "ref", 1), record("mapped_b#AAAA", 0, "ref", 1)]
        stages, _ = stage_templates(inputs, primary, "read_name")
        self.assertEqual(stages["POST_UMI"], {"mapped_a#AAAA", "unmapped_a#GGGG", "unmapped_b#GGGG"})

    def test_all_eligible_uses_each_placement_mapq(self):
        primary = [record("multi", 0, "ref_a", 1, mapq=30, score=10)]
        placements = [
            record("multi", 0, "ref_a", 1, mapq=30, score=10),
            record("multi", 0x100, "ref_b", 1, mapq=5, score=8),
        ]
        classified, errors = classify_reads([("multi", 0)], primary, placements)
        self.assertEqual(errors, [])
        keep = {"multi"}
        self.assertEqual(len(eligible_records(placements, classified, "all_eligible", keep, 0)), 2)
        self.assertEqual(len(eligible_records(placements, classified, "all_eligible", keep, 10)), 1)

    def test_unknown_placement_mapq_cannot_be_silently_filtered(self):
        primary = [record("multi", 0, "ref_a", 1, mapq=30, score=10)]
        placements = [
            record("multi", 0, "ref_a", 1, mapq=30, score=10),
            record("multi", 0x100, "ref_b", 1, mapq=255, score=8),
        ]
        classified, errors = classify_reads([("multi", 0)], primary, placements)
        self.assertEqual(errors, [])
        selected = eligible_records(placements, classified, "all_eligible", {"multi"}, 0)
        self.assertEqual(len(selected), 2)
        self.assertEqual(sum(bool(item.flag & 0x100) for item in selected), 1)
        unknown_count = cell_unknown_mapq_count(placements, classified, "all_eligible", {"multi"})
        self.assertEqual(unknown_count, 1)
        for minimum_mapq in (10, 20, 30):
            with self.assertRaisesRegex(ValueError, "positive-threshold coverage must be NOT_MEASURED"):
                eligible_records(placements, classified, "all_eligible", {"multi"}, minimum_mapq)

    def test_unknown_primary_mapq_intentionally_leaves_unique_mapq_zero_not_measured(self):
        primary = [record("unique", 0, "ref", 1, mapq=255)]
        placements = [record("unique", 0, "ref", 1, mapq=255)]
        classified, errors = classify_reads([("unique", 0)], primary, placements)
        self.assertEqual(errors, [])
        self.assertEqual(classified[("unique", 0)]["classification"], "UNIQUE")
        self.assertEqual(cell_unknown_mapq_count(placements, classified, "unique", {"unique"}), 1)
        coverage, _ = build_coverage_rows(
            "sample", load_profile(PROFILE), {"ref": 20}, [{
                "scope": "REFERENCE", "reference_id": "ref", "region_id": "REFERENCE::ref",
                "coordinates": list(range(1, 21)), "intervals": [(1, 20)],
            }], placements, classified,
            {stage: {"unique"} for stage in ("PRE_DEDUP", "POST_COORDINATE_EXCLUSION", "POST_UMI")},
            {stage: ("MEASURED", stage) for stage in ("PRE_DEDUP", "POST_COORDINATE_EXCLUSION", "POST_UMI")},
            [], False,
        )
        unique_mapq0 = [row for row in coverage if row["track"] == "unique" and row["minimum_mapq"] == 0]
        self.assertEqual({row["measurement_state"] for row in unique_mapq0}, {"NOT_MEASURED"})
        self.assertEqual({row["unknown_mapq_count"] for row in unique_mapq0}, {1})
        self.assertTrue(all("primary MAPQ is unknown" in row["reason"] for row in unique_mapq0))

    def test_unknown_placement_scope_is_recomputed_after_ablation_and_baseq(self):
        inputs = [("a_keep#AAAA", 0), ("z_drop#AAAA", 0)]
        primary = [
            record("a_keep#AAAA", 0, "ref_a", 1, mapq=30),
            record("z_drop#AAAA", 0, "ref_a", 1, mapq=30),
        ]
        low_quality_unknown = record("z_drop#AAAA", 0x100, "ref_b", 1, mapq=255, score=8)
        low_quality_unknown = SamRecord(**{**low_quality_unknown.__dict__, "qualities": "!" * 10})
        placements = [primary[0], primary[1], low_quality_unknown]
        classified, errors = classify_reads(inputs, primary, placements)
        self.assertEqual(errors, [])
        stages, stage_states = stage_templates(inputs, primary, "read_name")
        self.assertEqual(stages["POST_COORDINATE_EXCLUSION"], {"a_keep#AAAA"})
        self.assertEqual(stages["POST_UMI"], {"a_keep#AAAA"})
        coverage, _ = build_coverage_rows(
            "sample", load_profile(PROFILE), {"ref_a": 20, "ref_b": 20}, [{
                "scope": "REFERENCE", "reference_id": "ref_b", "region_id": "REFERENCE::ref_b",
                "coordinates": list(range(1, 21)), "intervals": [(1, 20)],
            }], placements, classified, stages, stage_states, [], False,
        )
        cells = {
            (row["stage"], row["minimum_base_quality"]): row
            for row in coverage
            if row["track"] == "all_eligible" and row["minimum_mapq"] == 30 and
            row["unit"] == "READ" and row["window_bp"] == 20
        }
        self.assertEqual(cells[("PRE_DEDUP", 0)]["measurement_state"], "NOT_MEASURED")
        self.assertEqual(cells[("PRE_DEDUP", 0)]["unknown_mapq_count"], 1)
        self.assertIn("1 eligible placement(s) in this cell", cells[("PRE_DEDUP", 0)]["reason"])
        self.assertEqual(cells[("PRE_DEDUP", 20)]["measurement_state"], "MEASURED")
        self.assertEqual(cells[("PRE_DEDUP", 20)]["unknown_mapq_count"], 0)
        for stage in ("POST_COORDINATE_EXCLUSION", "POST_UMI"):
            self.assertEqual(cells[(stage, 0)]["measurement_state"], "MEASURED")
            self.assertEqual(cells[(stage, 0)]["unknown_mapq_count"], 0)

    def test_secondary_without_reciprocal_pnext_is_explicitly_unmeasurable(self):
        records = [
            record("pair", 99, "ref", 1, mate_reference="=", mate_position=6),
            record("pair", 147, "ref", 6, mate_reference="=", mate_position=0),
        ]
        self.assertIn("no exact reciprocal PNEXT", template_pairing_issue(records))

    def test_filtered_reciprocal_mate_is_not_mislabeled_as_invalid_pnext(self):
        mate_255 = record("pair", 99, "ref", 1, mapq=255, mate_reference="=", mate_position=40)
        mate_40 = record("pair", 147, "ref", 40, mapq=40, mate_reference="=", mate_position=1)
        classifications = {
            ("pair", 1): {"measurement_state": "MEASURED", "classification": "UNIQUE", "primary_mapq": 255},
            ("pair", 2): {"measurement_state": "MEASURED", "classification": "UNIQUE", "primary_mapq": 40},
        }
        assessment = template_pairing_assessment(
            [mate_40], [mate_255, mate_40], baseq0_records=[mate_40], cell_records=[mate_40],
            keep_templates={"pair"}, classifications=classifications, track="unique", minimum_mapq=0,
        )
        self.assertIsNone(assessment["reason"])
        self.assertEqual(assessment["invalid_pnext_count"], 0)
        self.assertEqual(assessment["filtered_mate_reasons"], {"REGION": 1})

        coverage, _ = build_coverage_rows(
            "sample", load_profile(PROFILE), {"ref": 60}, [{
                "scope": "LOCUS", "reference_id": "ref", "region_id": "far",
                "coordinates": list(range(35, 51)), "intervals": [(35, 50)],
            }], [mate_255, mate_40], classifications,
            {stage: {"pair"} for stage in ("PRE_DEDUP", "POST_COORDINATE_EXCLUSION", "POST_UMI")},
            {stage: ("MEASURED", stage) for stage in ("PRE_DEDUP", "POST_COORDINATE_EXCLUSION", "POST_UMI")},
            [], True,
        )
        far_template = [
            row for row in coverage
            if row["track"] == "unique" and row["minimum_mapq"] == 0 and
            row["minimum_base_quality"] == 0 and row["unit"] == "TEMPLATE" and
            row["stage"] == "PRE_DEDUP" and row["window_bp"] == 20
        ][0]
        self.assertEqual(far_template["measurement_state"], "MEASURED")
        self.assertEqual(far_template["pairing_invalid_pnext_count"], 0)
        self.assertEqual(far_template["pairing_filtered_mate_count"], 1)
        self.assertEqual(json.loads(far_template["pairing_filtered_mate_reasons_json"]), {"REGION": 1})

    def test_mapq_filtered_reciprocal_mate_stays_measured_with_mapq_reason(self):
        mate_40 = record("pair", 99, "ref", 1, mapq=40, mate_reference="=", mate_position=120)
        mate_5 = record("pair", 147, "ref", 120, mapq=5, mate_reference="=", mate_position=1)
        classifications = {
            ("pair", 1): {"measurement_state": "MEASURED", "classification": "UNIQUE", "primary_mapq": 40},
            ("pair", 2): {"measurement_state": "MEASURED", "classification": "UNIQUE", "primary_mapq": 5},
        }
        assessment = template_pairing_assessment(
            [mate_40], [mate_40, mate_5], baseq0_records=[mate_40, mate_5], cell_records=[mate_40, mate_5],
            keep_templates={"pair"}, classifications=classifications, track="all_eligible", minimum_mapq=20,
        )
        self.assertIsNone(assessment["reason"])
        self.assertEqual(assessment["invalid_pnext_count"], 0)
        self.assertEqual(assessment["filtered_mate_reasons"], {"MAPQ": 1})

        coverage, _ = build_coverage_rows(
            "sample", load_profile(PROFILE), {"ref": 1400}, [{
                "scope": "REFERENCE", "reference_id": "ref", "region_id": "REFERENCE::ref",
                "coordinates": list(range(1, 1401)), "intervals": [(1, 1400)],
            }], [mate_40, mate_5], classifications,
            {stage: {"pair"} for stage in ("PRE_DEDUP", "POST_COORDINATE_EXCLUSION", "POST_UMI")},
            {stage: ("MEASURED", stage) for stage in ("PRE_DEDUP", "POST_COORDINATE_EXCLUSION", "POST_UMI")},
            [], True,
        )
        ref_template = [
            row for row in coverage
            if row["track"] == "all_eligible" and row["minimum_mapq"] == 20 and
            row["minimum_base_quality"] == 0 and row["unit"] == "TEMPLATE" and
            row["stage"] == "PRE_DEDUP" and row["window_bp"] == 20
        ][0]
        self.assertEqual(ref_template["measurement_state"], "MEASURED")
        self.assertEqual(ref_template["pairing_invalid_pnext_count"], 0)
        self.assertEqual(ref_template["pairing_filtered_mate_count"], 1)
        self.assertEqual(json.loads(ref_template["pairing_filtered_mate_reasons_json"]), {"MAPQ": 1})

    def test_template_pairing_summary_aggregates_pairing_counts_per_cell(self):
        cell_a = {
            "scope": "REFERENCE", "reference_id": "ref", "region_id": "ref",
            "track": "unique", "minimum_mapq": 0, "minimum_base_quality": 0, "stage": "PRE_DEDUP",
        }
        cell_b = {
            "scope": "REFERENCE", "reference_id": "ref", "region_id": "ref",
            "track": "unique", "minimum_mapq": 10, "minimum_base_quality": 0, "stage": "PRE_DEDUP",
        }
        cell_c = {
            "scope": "REFERENCE", "reference_id": "ref", "region_id": "ref",
            "track": "unique", "minimum_mapq": 20, "minimum_base_quality": 0, "stage": "PRE_DEDUP",
        }
        rows = [
            {"unit": "READ", "measurement_state": "MEASURED"},
            {"unit": "TEMPLATE", "measurement_state": "MEASURED", "window_bp": 20, **cell_a,
             "pairing_invalid_pnext_count": 1,
             "pairing_filtered_mate_count": 2, "pairing_filtered_mate_reasons_json": json.dumps({"MAPQ": 1, "REGION": 1})},
            {"unit": "TEMPLATE", "measurement_state": "MEASURED", "window_bp": 50, **cell_a,
             "pairing_invalid_pnext_count": 1,
             "pairing_filtered_mate_count": 2, "pairing_filtered_mate_reasons_json": json.dumps({"MAPQ": 1, "REGION": 1})},
            {"unit": "TEMPLATE", "measurement_state": "MEASURED", "window_bp": 20, **cell_b,
             "pairing_invalid_pnext_count": 0,
             "pairing_filtered_mate_count": 1, "pairing_filtered_mate_reasons_json": json.dumps({"REGION": 1})},
            {"unit": "TEMPLATE", "measurement_state": "NOT_MEASURED", "window_bp": 100, **cell_c,
             "pairing_invalid_pnext_count": None},
        ]
        summary = template_pairing_summary(rows)
        self.assertEqual(summary["template_cell_count"], 3)
        self.assertEqual(summary["invalid_pnext_count"], 1)
        self.assertEqual(summary["filtered_mate_count"], 3)
        self.assertEqual(summary["filtered_mate_reasons"], {"MAPQ": 1, "REGION": 2})
        empty = template_pairing_summary([{"unit": "TEMPLATE", "measurement_state": "MEASURED"}])
        self.assertIsNone(empty["filtered_mate_reasons"])

    def test_contract_versions_reject_old_outputs_without_reinterpretation(self):
        profile = load_profile(PROFILE)
        metrics = {
            "schema_version": METRICS_SCHEMA,
            "contract_versions": OUTPUT_CONTRACTS,
            "invariants": {"schema_version": INVARIANTS_SCHEMA},
        }
        provenance = {"contract_versions": OUTPUT_CONTRACTS}
        validate_contract_identity(profile, metrics, provenance, COVERAGE_FIELDS)
        for mutated, pattern in (
            ({**metrics, "schema_version": "experimental-direct-map-metrics-v1"}, "metrics"),
            ({**metrics, "invariants": {"schema_version": "experimental-direct-map-invariants-v1"}}, "invariants"),
        ):
            with self.assertRaisesRegex(ValueError, pattern):
                validate_contract_identity(profile, mutated, provenance, COVERAGE_FIELDS)
        with self.assertRaisesRegex(ValueError, "coverage TSV"):
            validate_contract_identity(profile, metrics, provenance, COVERAGE_FIELDS[1:])
        self.assertEqual(COVERAGE_SCHEMA, "experimental-direct-map-coverage-v2")

    def test_cross_track_is_evaluated_at_mapq_zero_and_positive_thresholds_remain_inapplicable(self):
        def coverage_row(track, mapq, depth):
            return {
                "scope": "REFERENCE", "reference_id": "ref", "region_id": "ref",
                "track": track, "minimum_mapq": mapq, "minimum_base_quality": 0,
                "unit": "READ", "stage": "PRE_DEDUP", "window_bp": 20,
                "measurement_state": "MEASURED", "histogram_json": json.dumps({str(depth): 1}),
                "denominator_bp": 1, "depth_total": depth,
                "breadth_1x": 1.0 if depth >= 1 else 0.0,
                "breadth_3x": 1.0 if depth >= 3 else 0.0,
            }

        inputs = [("read", 0)]
        classifications = {inputs[0]: {"classification": "UNMAPPED", "measurement_state": "MEASURED"}}
        geometry = [{"geometry": "single_end", "templates": 1, "reads": 1}]
        cross_track = [coverage_row("unique", 0, 2), coverage_row("all_eligible", 0, 1)]
        violations, checks, details = validate_invariants(inputs, classifications, geometry, cross_track, False)
        self.assertIn("MAPQ-0 cross-track unique exceeds all_eligible for depth_total", violations)
        self.assertEqual(details["cross_track_unique_le_all_eligible"]["state"], "MEASURED")
        self.assertEqual(details["cross_track_unique_le_all_eligible"]["evaluated_checks"], 3)
        self.assertEqual(
            details["cross_track_unique_le_all_eligible"]["positive_thresholds"]["state"],
            "NOT_APPLICABLE",
        )
        self.assertEqual(details["within_track_monotonicity"]["all_eligible"]["mapq"]["state"], "NOT_APPLICABLE")
        self.assertEqual(details["within_track_monotonicity"]["all_eligible"]["mapq"]["evaluated_checks"], 0)
        self.assertGreater(checks, 9)

        passing_cross_track = [coverage_row("unique", 0, 1), coverage_row("all_eligible", 0, 2)]
        violations, _, _ = validate_invariants(inputs, classifications, geometry, passing_cross_track, False)
        self.assertEqual(violations, [])

        within_track = [coverage_row("unique", 0, 1), coverage_row("unique", 10, 2)]
        violations, _, _ = validate_invariants(inputs, classifications, geometry, within_track, False)
        self.assertIn("raising MAPQ increased depth_total", violations)

    def test_partial_coverage_aggregate_is_measured_with_explicit_completeness(self):
        aggregate = coverage_aggregate([
            {"measurement_state": "MEASURED", "unknown_mapq_count": 2},
            {"measurement_state": "NOT_MEASURED", "unknown_mapq_count": 2},
            {"measurement_state": "NOT_APPLICABLE", "unknown_mapq_count": None},
        ])
        self.assertEqual(aggregate["state"], "MEASURED")
        self.assertEqual(aggregate["completeness"], "PARTIAL")
        self.assertEqual(aggregate["measured_cell_count"], 1)
        self.assertEqual(aggregate["measured_cell_fraction"], 1 / 3)
        self.assertEqual(aggregate["cells_with_unknown_mapq"], 2)

    def test_invariant_state_requires_at_least_one_measured_coverage_cell(self):
        state, reason, measured, not_measured = coverage_invariant_state([
            {"measurement_state": "NOT_MEASURED"}, {"measurement_state": "NOT_APPLICABLE"},
        ])
        self.assertEqual((state, measured, not_measured), ("NOT_MEASURED", 0, 1))
        self.assertIn("not evaluated", reason)
        state, reason, measured, not_measured = coverage_invariant_state([
            {"measurement_state": "MEASURED"}, {"measurement_state": "NOT_MEASURED"},
        ])
        self.assertEqual((state, measured, not_measured), ("MEASURED", 1, 1))
        self.assertIn("only MEASURED cells", reason)

    def test_retained_templates_is_null_outside_measured_stages(self):
        summary = summarize_stage_states(
            {"PRE_DEDUP": {"a"}, "POST_COORDINATE_EXCLUSION": set(), "POST_UMI": set()},
            {
                "PRE_DEDUP": ("MEASURED", ""),
                "POST_COORDINATE_EXCLUSION": ("NOT_MEASURED", "failed"),
                "POST_UMI": ("NOT_APPLICABLE", "not declared"),
            },
        )
        self.assertEqual(summary["PRE_DEDUP"]["retained_templates"], 1)
        self.assertIsNone(summary["POST_COORDINATE_EXCLUSION"]["retained_templates"])
        self.assertIsNone(summary["POST_UMI"]["retained_templates"])

    def test_cigar_only_match_equal_and_mismatch_cover_reference(self):
        alignment = record("indel", 0, "ref", 10, cigar="2S4M1I2=1X2D1N", score=7)
        alignment = SamRecord(**{**alignment.__dict__, "sequence": "A" * 10, "qualities": "I" * 10})
        covered = cigar_covered_positions(alignment, 20)
        self.assertEqual(len(covered), 7)
        self.assertIn(16, covered)
        self.assertNotIn(17, covered)
        self.assertNotIn(19, covered)

    def test_matrix_contains_required_lengths_abundances_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "matrix"
            repeated = Path(tmp) / "matrix-repeated"
            write_matrix(output)
            write_matrix(repeated)
            truth = json.loads((output / "truth.json").read_text(encoding="utf-8"))
            hashes = json.loads((output / "hashes.json").read_text(encoding="utf-8"))
            first_files = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
            repeated_files = {path.name: path.read_bytes() for path in repeated.iterdir() if path.is_file()}
        self.assertEqual(truth["fixture_lengths_bp"], [20, 30, 50, 75, 100])
        self.assertEqual(truth["abundances"], [0, 1, 3, 10])
        self.assertTrue(truth["generator_independent_of_summarizer"])
        for scenario in (
            "exact_unique", "substitution", "insertion", "deletion", "equivalent_homolog",
            "suboptimal_homolog", "negativeome_only", "low_complexity",
        ):
            self.assertEqual(truth["scenario_lengths_bp"][scenario], [20, 30, 50, 75, 100])
        abundance_three = [case for case in truth["cases"] if case["case"] == "abundance_three"]
        self.assertEqual(len(abundance_three), 3)
        self.assertEqual({case["abundance"] for case in abundance_three}, {3})
        self.assertIn("panel.fa", hashes["files"])
        self.assertIn("oracle_placements.sam", hashes["files"])
        self.assertEqual(first_files, repeated_files)

    def test_quantitative_oracle_covers_depth_geometry_and_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "matrix"
            write_matrix(fixture)
            expected = json.loads((fixture / "oracle_quantitative_expected.json").read_text(encoding="utf-8"))
            primary = parse_sam(fixture / "oracle_paired_primary.sam")
            placements = parse_sam(fixture / "oracle_paired_placements.sam")
            left = fastq_read_keys(fixture / "oracle_paired_r1.fastq", 1)
            right = fastq_read_keys(fixture / "oracle_paired_r2.fastq", 2)
            inputs = [item for pair in zip(left, right) for item in pair]
            classified, errors = classify_reads(inputs, primary, placements)
            geometry = geometry_rows("oracle", inputs, primary, True)
            stages, _ = stage_templates(inputs, primary, "read_name")
        self.assertEqual(errors, [])
        counts = Counter(item["classification"] for item in classified.values())
        for name, value in expected["read_classes"].items():
            self.assertEqual(counts[name], value)
        geometry_by_name = {row["geometry"]: {"templates": row["templates"], "reads": row["reads"]} for row in geometry}
        for name, value in expected["geometry"].items():
            self.assertEqual(geometry_by_name[name], value)
        self.assertEqual({name: len(values) for name, values in stages.items()}, expected["retained_templates"])

        one_pair = primary[:2]
        for unit, oracle_key in (("READ", "read"), ("TEMPLATE", "template")):
            depth = coverage_depth(one_pair, {"ref_a": 100}, unit, 0)["ref_a"]
            flat, _ = measured_metrics(depth, list(range(1, 21)), 20, [(1, 20)])
            oracle = expected["overlapping_mates"][oracle_key]
            self.assertEqual(flat["denominator_bp"], oracle["denominator_bp"])
            self.assertEqual(flat["depth_total"], oracle["depth_total"])
            self.assertEqual(flat["breadth_1x"], oracle["breadth_1x"])
            self.assertEqual(flat["breadth_3x"], oracle["breadth_3x"])
            self.assertEqual(json.loads(flat["histogram_json"]), oracle["histogram"])
            self.assertEqual(flat["max_window_depth_fraction"], oracle["max_window_depth_fraction"])

        disjoint = expected["disjoint_window"]
        disjoint_depth = [0] * disjoint["reference_length"]
        for position in disjoint["covered_positions"]:
            disjoint_depth[position - 1] = 1
        flat, _ = measured_metrics(
            disjoint_depth,
            [position for start, end in disjoint["intervals"] for position in range(start, end + 1)],
            disjoint["window_bp"],
            [tuple(interval) for interval in disjoint["intervals"]],
        )
        for field in ("denominator_bp", "depth_total", "max_window_depth_fraction", "zero_run_count", "max_zero_run_bp", "covered_intervals"):
            self.assertEqual(flat[field], disjoint[field])
        self.assertEqual(json.loads(flat["histogram_json"]), disjoint["histogram"])

        not_applicable = expected["window_not_applicable"]
        flat, _ = measured_metrics(
            [1] * not_applicable["denominator_bp"],
            list(range(1, not_applicable["denominator_bp"] + 1)),
            not_applicable["window_bp"],
            [(1, not_applicable["denominator_bp"])],
        )
        self.assertEqual(flat["concentration_state"], not_applicable["state"])
        unavailable, structured = unavailable_metrics(
            expected["not_measured"]["measurement_state"], "oracle error", expected["not_measured"]["denominator_bp"]
        )
        self.assertEqual(unavailable["denominator_bp"], expected["not_measured"]["denominator_bp"])
        self.assertEqual(structured["denominator_bp"]["state"], "MEASURED")

    def test_panel_registry_is_contractually_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "matrix"
            write_matrix(fixture)
            panel = load_panel_manifest(fixture / "panel_manifest.json", fixture / "panel.fa")
            self.assertIn("CHALLENGE_SEQUENCE", {record["role"] for record in panel["references"]})
            invalid_panel = json.loads((fixture / "panel_manifest.json").read_text(encoding="utf-8"))
            invalid_panel["references"][-1]["role"] = "CONTROL"
            invalid_path = fixture / "invalid_control_panel.json"
            invalid_path.write_text(json.dumps(invalid_panel) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no control-role references"):
                load_panel_manifest(invalid_path, fixture / "panel.fa")
        self.assertEqual(panel["negativeome"]["state"], "MEASURED")
        self.assertEqual(panel["controls"]["state"], "NOT_APPLICABLE")

    def test_unknown_git_commit_fails_closed(self):
        with patch("scripts.experimental.direct_map.experimental_direct_map.subprocess.run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = ""
            with self.assertRaisesRegex(ValueError, "NOT_REPRODUCIBLE"):
                git_head(ROOT)

    def test_finalize_rejects_reused_staging_with_success_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / ".staging" / "run-0001"
            staging.mkdir(parents=True)
            (staging / "SUCCESS.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot be reused"):
                finalize(Namespace(staging=str(staging), final=str(root / "runs" / "run-0001"), run_id="run-0001"))

    def test_shared_universe_position_index_matches_lazy_per_call_lookup(self):
        # build_coverage_rows precomputes one universe_position_index and
        # reuses it across every (stage x track x mapq x baseq x region)
        # grid cell instead of letting template_pairing_assessment rebuild
        # it per call. Both paths must agree on every result field.
        from collections import defaultdict

        from scripts.experimental.direct_map.experimental_direct_map import normalize_qname

        universe_records = []
        selected = []
        for t in range(20):
            name = f"multi{t}"
            # decoys: secondary placements for mate 1 that never pair with
            # anything, mirroring a read multi-mapped into a repetitive
            # locus under `bowtie2 --very-sensitive-local -a`.
            for decoy in range(15):
                universe_records.append(record(
                    name, 99, "ref", 1000 + decoy, mate_reference="=", mate_position=5000 + decoy,
                ))
            selected_record = record(name, 99, "ref", 1, mate_reference="=", mate_position=500)
            universe_records.append(selected_record)
            selected.append(selected_record)
            # true reciprocal mate, present in the universe but filtered out
            # of `selected` for this grid cell (e.g. outside the locus).
            universe_records.append(record(name, 147, "ref", 500, mate_reference="=", mate_position=1))

        universe_dict = defaultdict(list)
        for rec in universe_records:
            universe_dict[normalize_qname(rec.qname)].append(rec)
        universe_dict = dict(universe_dict)

        shared_index = {}
        for name, recs in universe_dict.items():
            bucket = defaultdict(list)
            for candidate in sorted(recs, key=lambda item: item.placement_key):
                bucket[(candidate.reference, candidate.position)].append(candidate)
            shared_index[name] = bucket

        lazy_list_universe = template_pairing_assessment(selected, universe_records)
        lazy_dict_universe = template_pairing_assessment(selected, universe_dict)
        shared_index_universe = template_pairing_assessment(
            selected, universe_dict, universe_position_index=shared_index,
        )
        self.assertEqual(lazy_list_universe, lazy_dict_universe)
        self.assertEqual(lazy_list_universe, shared_index_universe)
        self.assertEqual(lazy_list_universe["invalid_pnext_count"], 0)
        self.assertEqual(lazy_list_universe["filtered_mate_reasons"], {"REGION": 20})

    def test_template_pairing_assessment_is_not_quadratic_in_placements_per_template(self):
        # Regression for a timeout: a single highly multi-mapped template
        # (e.g. a read landing in a repetitive/low-complexity locus with
        # bowtie2 -a) used to force an O(k) rescan of all k placements for
        # every one of its k unmatched records, i.e. O(k^2) per grid cell,
        # repeated across the whole (stage x track x mapq x baseq x region)
        # grid. Indexing candidates by position turns this near-linear.
        import time

        placements = 800
        records = [
            record("multi", 99, "ref", 1 + i, mate_reference="=", mate_position=100_000 + i)
            for i in range(placements)
        ]
        start = time.perf_counter()
        assessment = template_pairing_assessment(records, records)
        elapsed = time.perf_counter() - start
        self.assertEqual(assessment["invalid_pnext_count"], placements)
        self.assertLess(
            elapsed, 0.5,
            f"template_pairing_assessment took {elapsed:.3f}s for {placements} placements in one "
            "template; this scales quadratically if the per-position index regresses",
        )


    # ------------------------------------------------------------------
    # Cadeia de integridade da execucao (substitui a comparacao com o
    # baseline congelado, indisponivel nesta historia do repositorio).
    # ------------------------------------------------------------------

    def _finalize_fixture(self, root):
        """Roda finalize() de verdade sobre um staging minimo.

        validate_output() exige os 13 artefatos de uma corrida real; aqui interessa
        a cadeia manifesto/SUCCESS, entao ela e neutralizada e todo o resto executa
        sem mock: build_artifact_manifest, validate_artifact_manifest, a gravacao
        atomica, a releitura do disco e a ancoragem de hashes.
        """
        staging = root / ".staging" / "run-0001"
        staging.mkdir(parents=True)
        (staging / "direct_map_metrics.json").write_text('{"a": 1}\n', encoding="utf-8")
        (staging / "provenance.json").write_text('{"b": 2}\n', encoding="utf-8")
        (staging / "coverage_metrics.tsv").write_text("schema_version\n", encoding="utf-8")
        final = root / "runs" / "run-0001"
        with patch(
            "scripts.experimental.direct_map.experimental_direct_map.validate_output",
            lambda directory: None,
        ):
            finalize(Namespace(staging=str(staging), final=str(final), run_id="run-0001"))
        return final

    def test_persisted_artifact_manifest_revalidates_from_disk(self):
        # O defeito corrigido: finalize() validava o dicionario em memoria e so
        # depois acrescentava `direct_map_contract_versions` antes de gravar, de
        # modo que o arquivo efetivamente persistido reprovava no schema fechado
        # compartilhado. Recarregar do disco e a unica verificacao que prova isso.
        with tempfile.TemporaryDirectory() as tmp:
            final = self._finalize_fixture(Path(tmp))
            manifest = json.loads((final / "artifact_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(set(manifest), {"schema_version", "files"})
            self.assertNotIn("direct_map_contract_versions", manifest)
            self.assertEqual(validate_artifact_manifest(final, manifest), [])

    def test_success_preserves_contract_identification_dropped_from_the_manifest(self):
        # A identificacao de contrato nao se perdeu: saiu do manifesto e continua
        # em SUCCESS.json, que por sua vez ancora o hash do manifesto.
        with tempfile.TemporaryDirectory() as tmp:
            final = self._finalize_fixture(Path(tmp))
            success = json.loads((final / "SUCCESS.json").read_text(encoding="utf-8"))
            manifest = json.loads((final / "artifact_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(success["contract_versions"], OUTPUT_CONTRACTS)
            self.assertEqual(success["governance_state"], "EXPERIMENTAL")
            self.assertIs(success["diagnostic"], False)
            self.assertEqual(success["artifact_count"], len(manifest["files"]))
            self.assertEqual(
                success["artifact_manifest_sha256"],
                hashlib.sha256((final / "artifact_manifest.json").read_bytes()).hexdigest(),
            )

    def test_tampered_artifact_is_detected_by_the_manifest_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            final = self._finalize_fixture(Path(tmp))
            manifest = json.loads((final / "artifact_manifest.json").read_text(encoding="utf-8"))
            (final / "provenance.json").write_text('{"b": 99}\n', encoding="utf-8")
            entry = manifest["files"]["provenance.json"]
            digest = hashlib.sha256((final / "provenance.json").read_bytes()).hexdigest()
            self.assertNotEqual(digest, entry["sha256"], "artifact tampering went undetected")
            self.assertNotEqual(
                (final / "provenance.json").stat().st_size, entry["size"],
                "artifact size drift went undetected",
            )

    def test_tampered_manifest_is_detected_by_the_success_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            final = self._finalize_fixture(Path(tmp))
            success = json.loads((final / "SUCCESS.json").read_text(encoding="utf-8"))
            manifest = json.loads((final / "artifact_manifest.json").read_text(encoding="utf-8"))
            # Reescrever o manifesto para "cobrir" o artefato adulterado quebra a
            # ancora no SUCCESS: a cadeia so fecha se os dois forem consistentes.
            manifest["files"]["provenance.json"]["sha256"] = "0" * 64
            (final / "artifact_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            recomputed = hashlib.sha256((final / "artifact_manifest.json").read_bytes()).hexdigest()
            self.assertNotEqual(
                recomputed, success["artifact_manifest_sha256"],
                "manifest tampering went undetected by the SUCCESS anchor",
            )

    def test_baseline_comparison_declares_not_executed_without_claiming_a_pass(self):
        # A comparacao com o baseline congelado do Gene-In 1.1 nao pode rodar aqui:
        # o commit congelado nao existe nesta historia. Declarar NOT_EXECUTED e
        # obrigatorio; declarar aprovacao seria falso.
        self.assertEqual(BASELINE_COMPARISON["state"], "NOT_EXECUTED")
        self.assertEqual(BASELINE_COMPARISON["comparison"], "FROZEN_PUBLIC_ARTIFACTS")
        self.assertNotIn("all_unchanged", BASELINE_COMPARISON)
        self.assertNotIn("PASS", json.dumps(BASELINE_COMPARISON))
        self.assertTrue(BASELINE_COMPARISON["reason"].strip())
        self.assertTrue(BASELINE_COMPARISON["guarantee_not_provided"].strip())
        self.assertIn("NOT verified", BASELINE_COMPARISON["guarantee_not_provided"])

    def test_metrics_limitations_do_not_claim_the_baseline_comparison_ran(self):
        # A lista de limitacoes voltou ao documento de metricas (a reorganizacao a
        # tinha perdido), mas a entrada historica sobre o baseline afirmava uma
        # verificacao que nao acontece mais. Ela nao pode voltar como estava.
        import inspect

        from scripts.experimental.direct_map import experimental_direct_map as module

        source = inspect.getsource(module.summarize)
        start = source.index('"limitations": [')
        block = source[start:source.index("],", start)]
        self.assertIn("partial reconciliation is not implemented", block)
        self.assertIn("partial template measurement is not implemented", block)
        self.assertIn("not biological absence", block)
        self.assertNotIn(
            "Baseline comparison verifies frozen public artifacts", block,
            "a limitacao historica afirma uma verificacao que este modulo nao executa",
        )
        self.assertIn("did not run", block)

    def test_source_state_identifies_the_executed_source_not_only_head(self):
        # HEAD sozinho nao identifica um checkout modificado. O registro precisa
        # dizer se a arvore estava suja e fixar os bytes do modulo executado.
        # Release archives do not carry .git. Verify real source hashes with
        # a controlled Git response; Git failures have separate coverage.
        with patch("scripts.experimental.direct_map.experimental_direct_map.git_head", return_value="a" * 40), \
             patch("scripts.experimental.direct_map.experimental_direct_map._portable_git",
                   return_value=SimpleNamespace(returncode=0, stdout=" M module.py\n")):
            state = source_state(ROOT)
        self.assertRegex(state["commit"], r"^[0-9a-f]{40}$")
        self.assertIn(state["working_tree"], {"CLEAN", "MODIFIED"})
        self.assertIs(
            state["commit_identifies_executed_source"], state["working_tree"] == "CLEAN",
        )
        sources = state["executing_module_sources"]
        self.assertTrue(
            any(name.endswith("experimental_direct_map.py") for name in sources),
            "executing module source was not identified",
        )
        for relative, entry in sources.items():
            path = ROOT / relative
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
            self.assertEqual(path.stat().st_size, entry["size"])


if __name__ == "__main__":
    unittest.main()
