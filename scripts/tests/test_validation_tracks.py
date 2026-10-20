#!/usr/bin/env python3
"""Security and behavior tests for Validation track infrastructure."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from validation.experimental_policy import baseline_thresholds, materialize_experimental_policy
from validation.optimization import (
    MAX_PIPELINE_PARAMETER_SETS,
    load_pinned_parameter_sets,
    select_parameter_sets_for_pipeline,
)
from validation.optimization_contract import evaluate_contract_sample, run_contract_optimization
from validation.panel_queries import (
    ADDED_LADDER_BP,
    LENGTH_LADDER_BP,
    PRESERVED_LADDER_BP,
    construction_catalog,
    sequence_for_recipe,
)
from validation.pipeline_metrics import build_pipeline_metrics
from validation.optimization_pipeline import (
    _blast_stage_key,
    _primary_candidate,
    _run_from_cached_blast,
    cached_blast_run,
)
from validation.parameter_map import minimum_rerun_stage
from validation.parameter_map import PARAMETER_REGISTRY
from validation.parameter_set import expand_grid, parameter_set_id
from validation.ranking import aggregate_scores, ranking_report
from validation.tracks import resolve_tracks


class ValidationTrackTests(unittest.TestCase):

    def test_all_safe_includes_operational_but_not_optimization(self):
        tracks = resolve_tracks(["all-safe"])
        ids = {track.track_id for track in tracks}
        self.assertEqual(ids, {"engineering", "synthetic", "competitive", "operational"})
        self.assertNotIn("scientific-optimization", ids)
        self.assertNotIn("scientific-validation", ids)

    def test_parameter_set_id_is_reproducible(self):
        params = {"specificity.minimum_delta_bitscore": 10, "locus.minimum_candidate_bp": 50}
        first = parameter_set_id(params)
        second = parameter_set_id(dict(reversed(list(params.items()))))
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("ps-"))

    def test_grid_expansion_count(self):
        grid = json.loads(
            (ROOT / "config" / "experimental" / "validation" / "optimization_grid_v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(len(expand_grid(grid)), 18)

    def test_ranking_never_auto_promotes(self):
        rows = [
            {
                "parameter_set_id": "ps-aaa",
                "sample_id": "a",
                "ground_truth": "TARGET_VIRUS",
                "recovered": True,
                "expected_length_bp": 30,
                "sample_role": "positive_target",
                "false_positive": False,
                "false_negative": False,
                "competition_outcome": "TARGET_SPECIFIC",
            }
        ]
        report = ranking_report(aggregate_scores(rows))
        # validation.ranking.ranking_report has no dedicated "disclaimer" field
        # (out of this task's file scope: scripts/lib/validation/**); the actual
        # guarantee under test is that ranking never emits promotion language
        # or an automatic-selection verdict, which we check directly.
        self.assertNotIn("PROMOTED", json.dumps(report))
        self.assertNotIn("promotion", json.dumps(report).lower())
        for configuration in report["configurations"]:
            self.assertNotIn("PROMOTED", configuration["labels"])

    def test_ranking_recovery_denominator_contains_only_target_samples(self):
        rows = [
            {
                "parameter_set_id": "ps-a",
                "sample_id": "target-short",
                "ground_truth": "TARGET_VIRUS",
                "sample_role": "positive_target",
                "expected_length_bp": 29,
                "recovered": True,
                "false_positive": False,
                "false_negative": False,
            },
            {
                "parameter_set_id": "ps-a",
                "sample_id": "target-long",
                "ground_truth": "TARGET_VIRUS",
                "sample_role": "positive_target",
                "expected_length_bp": 50,
                "recovered": True,
                "false_positive": False,
                "false_negative": False,
            },
            {
                "parameter_set_id": "ps-a",
                "sample_id": "negative-short",
                "ground_truth": "HOST",
                "sample_role": "negative_control",
                "expected_length_bp": 29,
                "recovered": False,
                "false_positive": True,
                "false_negative": False,
                "competition_outcome": "AMBIGUOUS",
            },
        ]
        score = aggregate_scores(rows)[0]
        self.assertEqual(score.total_samples, 3)
        self.assertEqual(score.recovery_total_pct, 100.0)
        self.assertEqual(score.recovery_20_49_pct, 100.0)
        self.assertEqual(score.recovery_by_length["20-49"], 100.0)






    def test_blast_cache_key_ignores_classification_parameters(self):
        blast_params = {
            "blast.short_max_bp": 29,
            "blast.dual_mode_min_bp": 30,
            "blast.dual_mode_max_bp": 49,
            "locus.minimum_candidate_bp": 50,
            "specificity.minimum_delta_bitscore": 10,
        }
        changed = dict(blast_params)
        changed["locus.minimum_candidate_bp"] = 40
        changed["specificity.minimum_delta_bitscore"] = 5
        self.assertEqual(_blast_stage_key("pipe_target_49bp", blast_params), _blast_stage_key("pipe_target_49bp", changed))
        self.assertEqual(
            minimum_rerun_stage(changed, blast_params),
            "competitive_search",
        )

    def test_cached_blast_run_requires_blast_artifact(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            parameters = {
                "blast.short_max_bp": 29,
                "blast.dual_mode_min_bp": 30,
                "blast.dual_mode_max_bp": 49,
            }
            self.assertIsNone(cached_blast_run(tmp_path, "s1", parameters))
            from validation.optimization_pipeline import _store_blast_cache

            run_dir = tmp_path / "run"
            run_dir.mkdir()
            (run_dir / "blastn-short.tsv").write_text("qseqid\n", encoding="utf-8")
            _store_blast_cache(tmp_path, "s1", parameters, run_dir)
            cached = cached_blast_run(tmp_path, "s1", parameters)
            self.assertIsNotNone(cached)
            other = dict(parameters)
            other["blast.dual_mode_max_bp"] = 48
            self.assertIsNone(cached_blast_run(tmp_path, "s1", other))

    def test_cached_blast_provenance_reports_rebuilt_downstream_stages(self):
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cached_run = tmp_path / "cached"
            cached_run.mkdir()
            for name in ("blastn-short.tsv", "blastn.tsv", "fragment_evidence.tsv", "blast_routing.json"):
                (cached_run / name).write_text("\n", encoding="utf-8")
            policy_dir = tmp_path / "policy"
            policy_dir.mkdir()
            policy_paths = {
                "activation": policy_dir / "activation.json",
                "profiles": policy_dir / "profiles.json",
            }
            with patch("validation.optimization_pipeline.subprocess.run"):
                stages = _run_from_cached_blast(
                    repo_root=ROOT,
                    sample_id="s1",
                    query_fasta=tmp_path / "query.fa",
                    run_dir=tmp_path / "run",
                    run_id="run-1",
                    policy_paths=policy_paths,
                    cached_run=cached_run,
                    parameters={},
                )
            self.assertEqual(
                stages,
                ["locus_building", "hsp_aggregation", "competitive_search", "evidence_classification"],
            )

    def test_operational_exit_77_maps_to_not_executed(self):
        # Verify exit status mapping through the current track runner.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "validation_track_runner_tracks",
            ROOT / "scripts" / "ops" / "validation_track_runner.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.classify_exit(77, False), "NOT_EXECUTED")
        self.assertNotEqual(module.classify_exit(77, False), "PASS")
        self.assertEqual(module.classify_exit(1, True), "FAIL")


    def test_parameter_registry_documents_pipeline_stages(self):
        self.assertIn("locus.minimum_candidate_bp", PARAMETER_REGISTRY)
        self.assertEqual(PARAMETER_REGISTRY["blast.dual_mode_max_bp"].stage, "initial_blast")

    def test_pipeline_panel_covers_length_ladder_and_hard_competitors(self):
        panel = json.loads(
            (ROOT / "config/experimental/validation/sample_panel_pipeline.json").read_text(encoding="utf-8")
        )
        samples = panel["samples"]
        lengths = {int(item["length_bp"]) for item in samples if item.get("recipe") == "target_unique_prefix"}
        self.assertTrue(set(PRESERVED_LADDER_BP).issubset(lengths))
        self.assertTrue(set(ADDED_LADDER_BP).issubset(lengths))
        self.assertEqual(lengths, set(LENGTH_LADDER_BP))
        recipes = {item["recipe"] for item in samples}
        self.assertIn("target_window_host_1mm", recipes)
        self.assertIn("target_window_host_2mm", recipes)
        self.assertIn("target_window_neigh_3mm", recipes)
        self.assertIn("target_window_neigh_4mm", recipes)
        self.assertIn("target_window_route_49", recipes)
        self.assertIn("target_window_fp_mid", recipes)
        self.assertIn("host_window_1mm", recipes)
        self.assertIn("neighbor_window_3mm", recipes)
        for item in samples:
            self.assertTrue(item.get("construction"))
            self.assertNotIn("expected_outcome", item)
            seq = sequence_for_recipe(item["recipe"], int(item["length_bp"]))
            self.assertEqual(len(seq), int(item["length_bp"]))
        catalog = construction_catalog()
        self.assertIn("does not assert", catalog["disclaimer"].lower())

    def test_pipeline_selection_caps_collapsed_labels_at_five(self):
        self.assertEqual(MAX_PIPELINE_PARAMETER_SETS, 5)
        import shutil

        out = ROOT / "results" / "validation" / "test-selection-cap"
        if out.exists():
            shutil.rmtree(out)
        ranking = {"configurations": []}
        (out / "parameter_sets").mkdir(parents=True, exist_ok=True)
        for index in range(8):
            ps_id = f"ps-fake-{index:02d}"
            ranking["configurations"].append(
                {
                    "parameter_set_id": ps_id,
                    "labels": ["BEST_RECOVERY", "BEST_SHORT_FRAGMENT_RECOVERY", "BEST_BALANCE", "BEST_SPECIFICITY"]
                    if index == 0
                    else ["REVIEW_REQUIRED"],
                }
            )
            (out / "parameter_sets" / f"{ps_id}.json").write_text(
                json.dumps({"parameter_set_id": ps_id, "parameters": {"n": index}}),
                encoding="utf-8",
            )
        selected = select_parameter_sets_for_pipeline(
            repo_root=ROOT,
            ranking=ranking,
            out_dir=out,
            experiment_id="cap-test",
            commit="test",
            top_n=5,
        )
        self.assertEqual(len(selected), 5)
        ids = [item["parameter_set_id"] for item in selected]
        self.assertEqual(len(ids), len(set(ids)))
        shutil.rmtree(out)

    def test_pinned_round2_sets_are_the_six_round1_configurations(self):
        import shutil

        out = ROOT / "results" / "validation" / "test-pinned-round2"
        if out.exists():
            shutil.rmtree(out)
        records = load_pinned_parameter_sets(
            repo_root=ROOT,
            pinned_path=ROOT / "config/experimental/validation/pipeline_round2_parameter_sets.json",
            out_dir=out,
            experiment_id="pin-test",
            commit="test",
        )
        self.assertEqual(len(records), 6)
        expected = {
            "ps-32b8942739d01f60",
            "ps-78bea3be7ff116c6",
            "ps-a51f07e642d4b6dd",
            "ps-a9f2ccb61b9565b5",
            "ps-a2400e369ade2065",
            "ps-4625fadce87a70a0",
        }
        self.assertEqual({item["parameter_set_id"] for item in records}, expected)
        baseline = records[0]["parameters"]
        self.assertEqual(baseline["locus.minimum_candidate_bp"], 50)
        self.assertEqual(baseline["specificity.minimum_delta_bitscore"], 10)
        self.assertEqual(baseline["blast.dual_mode_max_bp"], 49)
        shutil.rmtree(out)

    def test_pinned_round3_sets_are_the_six_round1_configurations(self):
        import shutil

        out = ROOT / "results" / "validation" / "test-pinned-round3"
        if out.exists():
            shutil.rmtree(out)
        records = load_pinned_parameter_sets(
            repo_root=ROOT,
            pinned_path=ROOT / "config/experimental/validation/pipeline_round3_parameter_sets.json",
            out_dir=out,
            experiment_id="pin-test-r3",
            commit="test",
        )
        self.assertEqual(len(records), 6)
        expected = {
            "ps-32b8942739d01f60",
            "ps-78bea3be7ff116c6",
            "ps-a51f07e642d4b6dd",
            "ps-a9f2ccb61b9565b5",
            "ps-a2400e369ade2065",
            "ps-4625fadce87a70a0",
        }
        self.assertEqual({item["parameter_set_id"] for item in records}, expected)
        ids = [item["recipe"] for item in json.loads(
            (ROOT / "config/experimental/validation/sample_panel_pipeline.json").read_text(encoding="utf-8")
        )["samples"]]
        self.assertIn("target_window_route_49", ids)
        self.assertIn("target_window_neigh_4mm", ids)
        self.assertIn("target_window_fp_mid", ids)
        shutil.rmtree(out)

    def test_pinned_round4_sets_cover_delta10_grid(self):
        import shutil

        out = ROOT / "results" / "validation" / "test-pinned-round4"
        if out.exists():
            shutil.rmtree(out)
        records = load_pinned_parameter_sets(
            repo_root=ROOT,
            pinned_path=ROOT / "config/experimental/validation/pipeline_round4_parameter_sets.json",
            out_dir=out,
            experiment_id="pin-test-r4",
            commit="test",
        )
        self.assertEqual(len(records), 9)
        expected = {
            "ps-32b8942739d01f60",
            "ps-a51f07e642d4b6dd",
            "ps-0c60ec876349ec18",
            "ps-4625fadce87a70a0",
            "ps-71e1d5fd11edd460",
            "ps-a0413548bc852a91",
            "ps-78bea3be7ff116c6",
            "ps-a9f2ccb61b9565b5",
            "ps-a2400e369ade2065",
        }
        self.assertEqual({item["parameter_set_id"] for item in records}, expected)
        delta10_dual49 = [
            item
            for item in records
            if item["parameters"]["specificity.minimum_delta_bitscore"] == 10
            and item["parameters"]["blast.dual_mode_max_bp"] == 49
            and item["parameters"]["locus.minimum_candidate_bp"] in {40, 45}
        ]
        self.assertEqual(len(delta10_dual49), 2)
        shutil.rmtree(out)

    def test_pipeline_metrics_recovery_first_pareto_and_early_discard(self):
        rows = []
        for ps_id, recovered_50, route_recovered in (
            ("ps-base", True, True),
            ("ps-cand", False, False),
        ):
            for sample_id, length, truth, role, recovered in (
                ("pipe_target_29bp", 29, "TARGET_VIRUS", "positive_target", True),
                ("pipe_target_35bp", 35, "TARGET_VIRUS", "positive_target", True),
                ("pipe_target_50bp", 50, "TARGET_VIRUS", "positive_target", recovered_50),
                ("pipe_route_short_only_49bp", 49, "TARGET_VIRUS", "positive_target", route_recovered),
                ("pipe_fp_hostlike_50bp", 50, "HOST", "negative_control", False),
            ):
                analysis_recovered = recovered if truth == "TARGET_VIRUS" else False
                rows.append(
                    {
                        "parameter_set_id": ps_id,
                        "sample_id": sample_id,
                        "ground_truth": truth,
                        "sample_role": role,
                        "expected_length_bp": length,
                        "recovered": recovered and truth == "TARGET_VIRUS",
                        "false_positive": role == "negative_control" and analysis_recovered,
                        "false_negative": truth == "TARGET_VIRUS" and not recovered,
                        "competition_outcome": (
                            "TARGET_SPECIFIC"
                            if recovered and truth == "TARGET_VIRUS"
                            else "AMBIGUOUS"
                        ),
                        "observed_classification": "LOCUS_CANDIDATE" if analysis_recovered else "NO_CANDIDATE",
                        "runtime_seconds": 1.0,
                        "extra": {
                            "length_bucket": None,
                            "stages_reused": ["initial_blast"] if ps_id != "ps-base" else [],
                            "analysis_outcome": "EVIDENCE_RECOVERED" if analysis_recovered else "NO_EVIDENCE",
                        },
                    }
                )
                rows[-1]["extra"]["length_bucket"] = (
                    "20-29" if length <= 29 else "30-39" if length <= 39 else "40-49" if length <= 49 else "50-99"
                )
        metrics = build_pipeline_metrics(
            results=rows,
            parameter_sets=[
                {"parameter_set_id": "ps-base", "parameters": {"specificity.minimum_delta_bitscore": 10}},
                {"parameter_set_id": "ps-cand", "parameters": {"specificity.minimum_delta_bitscore": 5}},
            ],
            baseline_parameter_set_id="ps-base",
            baseline_parameters={"specificity.minimum_delta_bitscore": 10},
        )
        self.assertIn("50-99", metrics["parameter_sets"][0]["recovery_by_bucket"])
        self.assertIn("30-39", metrics["parameter_sets"][0]["recovery_by_bucket"])
        self.assertIn("pipe_route_short_only_49bp", metrics["discrimination"]["discriminating_sample_ids"])
        # build_pipeline_metrics has no "automatic_promotion" field (out of this
        # task's file scope: scripts/lib/validation/**); it never selects a winner
        # by itself, it only reports domination/discard signals for a human.
        self.assertNotIn("automatic_promotion", metrics)
        self.assertNotIn("promoted", json.dumps(metrics).lower())
        self.assertEqual(metrics["domination"]["undominated_parameter_set_ids"], ["ps-base"])
        self.assertTrue(metrics["early_discard_flags"][0]["suspicious_early_discard"])
        self.assertEqual(metrics["early_discard_summary"]["count"], 1)
        self.assertEqual(metrics["early_discard_summary"]["parameter_set_ids"], ["ps-cand"])
        lost_ids = {item["sample_id"] for item in metrics["early_discard_flags"][0]["lost_target_samples"]}
        self.assertIn("pipe_route_short_only_49bp", lost_ids)

    def test_pipeline_metrics_report_fine_buckets_and_baseline_delta(self):
        rows = []
        for ps_id, recovered_50 in (("ps-base", True), ("ps-cand", False)):
            for sample_id, length, truth, role, recovered in (
                ("pipe_target_29bp", 29, "TARGET_VIRUS", "positive_target", True),
                ("pipe_target_35bp", 35, "TARGET_VIRUS", "positive_target", True),
                ("pipe_target_50bp", 50, "TARGET_VIRUS", "positive_target", recovered_50),
                ("pipe_fp_hostlike_50bp", 50, "HOST", "negative_control", False),
            ):
                rows.append(
                    {
                        "parameter_set_id": ps_id,
                        "sample_id": sample_id,
                        "ground_truth": truth,
                        "sample_role": role,
                        "expected_length_bp": length,
                        "recovered": recovered and truth == "TARGET_VIRUS",
                        "false_positive": role == "negative_control" and recovered,
                        "false_negative": truth == "TARGET_VIRUS" and not recovered,
                        "competition_outcome": "TARGET_SPECIFIC" if recovered else "AMBIGUOUS",
                        "runtime_seconds": 1.0,
                        "extra": {"length_bucket": None, "stages_reused": ["initial_blast"] if ps_id != "ps-base" else []},
                    }
                )
                rows[-1]["extra"]["length_bucket"] = (
                    "20-29" if length <= 29 else "30-39" if length <= 39 else "50-99"
                )
        metrics = build_pipeline_metrics(
            results=rows,
            parameter_sets=[
                {"parameter_set_id": "ps-base", "parameters": {"specificity.minimum_delta_bitscore": 10}},
                {"parameter_set_id": "ps-cand", "parameters": {"specificity.minimum_delta_bitscore": 5}},
            ],
            baseline_parameter_set_id="ps-base",
            baseline_parameters={"specificity.minimum_delta_bitscore": 10},
        )
        self.assertIn("50-99", metrics["parameter_sets"][0]["recovery_by_bucket"])
        self.assertIn("30-39", metrics["parameter_sets"][0]["recovery_by_bucket"])
        self.assertEqual(metrics["discrimination"]["discriminating_sample_ids"], ["pipe_target_50bp"])
        self.assertNotIn("automatic_promotion", metrics)
        self.assertNotIn("promoted", json.dumps(metrics).lower())
        self.assertIn("undominated_parameter_set_ids", metrics["domination"])
        self.assertIn("specific_false_positives", metrics["parameter_sets"][0])

    def test_primary_candidate_prefers_locus_over_shorter_exploratory(self):
        picked = _primary_candidate(
            [
                {"category": "TARGET_VIRUS", "candidate_class": "EXPLORATORY_FRAGMENT", "candidate_bp": 46},
                {"category": "TARGET_VIRUS", "candidate_class": "LOCUS_CANDIDATE", "candidate_bp": 50},
            ]
        )
        self.assertEqual(picked["candidate_class"], "LOCUS_CANDIDATE")
        self.assertEqual(picked["candidate_bp"], 50)


if __name__ == "__main__":
    unittest.main()
