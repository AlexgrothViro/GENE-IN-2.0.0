import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from competitive_hits import evaluate


def hit(subject, category, score, task="blastn", qcov=0.9):
    return {"qseqid": "q", "sseqid": subject, "category": category, "taxon": subject, "task": task,
            "best_bitscore": str(score), "query_coverage": str(qcov), "low_complexity_status": "ACCEPTABLE"}


class CompetitiveMarginTests(unittest.TestCase):
    def test_target_and_competitor_same_task_are_compared(self):
        result = evaluate([hit("target", "TARGET_VIRUS", 100), hit("host", "HOST", 85)])
        self.assertEqual(result[0]["specificity_status"], "TARGET_SPECIFIC")
        self.assertEqual(float(result[0]["delta_bitscore"]), 15.0)

    def test_different_tasks_are_never_compared(self):
        result = evaluate([hit("target", "TARGET_VIRUS", 100, "blastn-short"), hit("host", "HOST", 99, "blastn")])
        self.assertEqual(len(result), 2)
        by_task = {row["task"]: row for row in result}
        self.assertEqual(by_task["blastn-short"]["specificity_status"], "NOT_EVALUATED")
        self.assertEqual(by_task["blastn"]["specificity_status"], "NON_TARGET_BEST")
        self.assertEqual(float(by_task["blastn-short"]["competitor_bitscore"]), 0.0)

    def test_large_absolute_coverage_difference_is_ambiguous(self):
        result = evaluate([hit("target", "TARGET_VIRUS", 100, qcov=0.40),
                           hit("near", "NEAR_NON_TARGET_VIRUS", 85, qcov=0.95)])
        self.assertEqual(result[0]["specificity_status"], "AMBIGUOUS")
        self.assertEqual(float(result[0]["qcov_difference_abs_pp"]), 55.0)


if __name__ == "__main__":
    unittest.main()
