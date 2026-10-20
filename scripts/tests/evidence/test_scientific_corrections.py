"""Regression tests for the concrete failures from the academic review."""
import copy
import json
import sys
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/evidence"))
from classify_sample import classify
from competitive_hits import evaluate
from evidence_contract import validate_document
from export_evidence import render
sys.path.insert(0, str(ROOT / "scripts/lib"))
from evidence_analytics import EvidenceAnalyticsService


def hit(subject, taxon, score, category="TARGET_VIRUS", task="blastn"):
    return dict(qseqid="q", sseqid=subject, taxon=taxon, best_bitscore=str(score),
                query_coverage="1.0", low_complexity_status="ACCEPTABLE", category=category, task=task)


def locus(subject="A", intervals="1-20", orientation="+", task="blastn", number=1):
    return dict(locus_id=f"L{number}", sseqid=subject, taxon=f"taxon-{subject}",
                query_ids="q", category="TARGET_VIRUS", reference_intervals=intervals,
                reference_length="100", covered_reference_bp="20", max_query_length="20",
                max_query_covered_bp="20", orientation=orientation, task=task)


def run(loci, competitive):
    return classify("sample", loci, competitive, [], [], "UNCONTROLLED", "shotgun")


class ScientificCorrectionsTests(unittest.TestCase):
    def test_host_candidates_remain_available_without_scientific_qualification(self):
        competitive = evaluate([hit("A", "taxon-A", 20), hit("host", "host", 40, "HOST")])
        value = run([locus()], competitive)
        self.assertEqual(value["evidence_label"], "Candidatos recuperados")
        self.assertEqual(value["specificity_status"], "NON_TARGET_BEST")
        self.assertEqual(value["metrics"]["available_candidate_count"], 1)
        self.assertEqual(value["metrics"]["promotion_eligible_candidate_count"], 0)
        self.assertEqual(value["metrics"]["qualifying_loci"], 0)
        self.assertEqual(value["candidates"][0]["availability_status"], "AVAILABLE_FOR_REVIEW")
        report = render(value)
        self.assertEqual(value["analysis_outcome"], "EVIDENCE_RECOVERED")
        self.assertEqual(value["evidence_level"], "DETECTED")
        self.assertIn("Candidatos recuperados", report)
        self.assertIn("CANDIDATOS_PARA_REVISAO", report)
        self.assertNotIn("| Resultado da análise | `EVIDENCE_RECOVERED`", report)
        self.assertNotIn("| Rótulo para revisão | `DETECTED`", report)
        self.assertIn("não representa confirmação viral", report)
        self.assertIn("melhor alinhamento competitivo é de um não alvo", report)
        self.assertIn("Suporte por reads não foi medido", report)

    def test_reference_union_ignores_strand_task_and_overlapping_loci(self):
        loci = [locus(intervals="1-20"), locus(intervals="1-20", orientation="-", number=2),
                locus(intervals="10-30", task="blastn-short", number=3),
                locus(intervals="40-50", number=4)]
        value = run(loci, [])
        self.assertEqual(value["metrics"]["total_nonredundant_reference_bp"], 41)
        self.assertEqual(value["reference_coverage"]["by_reference"][0]["reference_intervals"], "1-30;40-50")
        self.assertEqual(len(value["candidates"]), 4)

    def test_union_separates_references_and_segments(self):
        second = locus(subject="B", intervals="1-10", number=2)
        segment = dict(locus(intervals="1-10", number=3), segment="segment2")
        value = run([locus(), second, segment], [])
        self.assertEqual(value["metrics"]["total_nonredundant_reference_bp"], 40)
        self.assertEqual(len(value["reference_coverage"]["by_reference"]), 3)

    def test_missing_coordinates_are_not_invented_from_covered_count(self):
        value = run([locus(intervals="")], [])
        self.assertEqual(value["metrics"]["total_nonredundant_reference_bp"], 0)
        self.assertEqual(value["metrics"]["reference_coverage_status"], "NOT_EVALUATED")
        self.assertEqual(value["reference_coverage"]["by_reference"][0]["status"], "NOT_EVALUATED")

    def test_invalid_coordinates_or_inconsistent_reference_lengths_fail(self):
        for interval in ("0-20", "20-10", "90-110"):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                run([locus(intervals=interval)], [])
        with self.assertRaisesRegex(ValueError, "inconsistent reference length"):
            run([locus(), dict(locus(number=2), reference_length="200")], [])

    def test_weaker_reference_does_not_borrow_best_reference_specificity(self):
        comp = evaluate([hit("A", "taxon-A", 100), hit("B", "taxon-B", 50), hit("host", "host", 80, "HOST")])
        value = run([locus("A"), locus("B", number=2)], comp)
        a, b = value["candidates"]
        self.assertEqual(a["specificity_status"], "TARGET_SPECIFIC")
        self.assertEqual(a["taxonomic_status"], "PANEL_TAXON_PREFERRED")
        self.assertEqual(b["specificity_status"], "NON_TARGET_BEST")
        self.assertEqual(b["taxonomic_status"], "NON_TARGET_BEST")

    def test_tied_target_species_remain_taxonomically_ambiguous(self):
        comp = evaluate([hit("A", "taxon-A", 100), hit("B", "taxon-B", 100), hit("host", "host", 80, "HOST")])
        value = run([locus("A"), locus("B", number=2)], comp)
        self.assertTrue(all(c["specificity_status"] == "TARGET_SPECIFIC" for c in value["candidates"]))
        self.assertTrue(all(c["taxonomic_status"] == "AMBIGUOUS" for c in value["candidates"]))

    def test_no_other_taxon_or_unlabelled_competitor_is_not_species_confirmation(self):
        for hits in ([hit("A", "taxon-A", 100), hit("host", "host", 80, "HOST")],
                     [hit("A", "taxon-A", 100), hit("host", "host", 80, "HOST"), hit("unknown", "", 10, "UNLABELED")]):
            with self.subTest(hits=hits):
                result = run([locus()], evaluate(hits))["candidates"][0]
                self.assertNotEqual(result["taxonomic_status"], "PANEL_TAXON_PREFERRED")

    def test_reference_binding_and_task_binding_for_existing_competitive_tables(self):
        comp = [dict(qseqid="q", task="blastn", target_sseqid="A", specificity_status="TARGET_SPECIFIC")]
        value = run([locus("A"), locus("B", number=2), locus("A", task="blastn-short", number=3)], comp)
        self.assertEqual([c["specificity_status"] for c in value["candidates"]], ["TARGET_SPECIFIC", "NOT_EVALUATED", "NOT_EVALUATED"])
        self.assertTrue(all(c["taxonomic_status"] == "NOT_EVALUATED" for c in value["candidates"]))

    def test_unknown_query_only_status_cannot_qualify_a_reference(self):
        value = run([locus()], [dict(qseqid="q", task="blastn", specificity_status="TARGET_SPECIFIC")])
        self.assertEqual(value["specificity_status"], "NOT_EVALUATED")

    def test_contract_rejects_reintroduced_double_count_or_false_qualification(self):
        base = run([locus()], [])
        for metric, number in (("total_nonredundant_reference_bp", 40), ("qualifying_loci", 1), ("promotion_eligible_candidate_count", 1)):
            value = copy.deepcopy(base)
            value["metrics"][metric] = number
            with self.subTest(metric=metric), self.assertRaises(ValueError):
                validate_document(value)

    def test_duplicate_query_task_or_reference_evidence_fails(self):
        comp = evaluate([hit("A", "taxon-A", 100)])
        with self.assertRaisesRegex(ValueError, "duplicate competitive query/task"):
            run([locus()], [*comp, *comp])
        value = json.loads(comp[0]["target_evidence_json"])
        comp[0]["target_evidence_json"] = json.dumps(value * 2)
        with self.assertRaisesRegex(ValueError, "duplicate competitive reference_id"):
            run([locus()], comp)

    def test_analytics_api_keeps_availability_separate_and_exposes_reference_evidence(self):
        value = run([locus()], evaluate([hit("A", "taxon-A", 20), hit("host", "host", 40, "HOST")]))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory/'sample_evidence.json').write_text(json.dumps(value), encoding='utf-8')
            service = EvidenceAnalyticsService(None)
            with patch.object(service, '_run', return_value=('id', directory, {}, {'valid_alpha2': True}, {})):
                response = service.summary('id')
            self.assertEqual(response['metadata']['evidence_label'], 'Candidatos recuperados')
            self.assertEqual(response['promotion_summary']['eligible'], 0)
            self.assertEqual(response['availability_summary']['available'], 1)
            self.assertEqual(response['availability_summary']['qualification_status'], 'NOT_EVALUATED')
            self.assertEqual(response['candidates'][0]['specificity_status'], 'NON_TARGET_BEST')
            self.assertEqual(response['candidates'][0]['taxonomic_status'], 'NON_TARGET_BEST')


if __name__ == "__main__":
    unittest.main()
