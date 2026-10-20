import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(ROOT / "src"))

from common import format_intervals
from genein.evidence_graph.graph_builder.parse import parse_interval_list


class IntervalRoundtripTests(unittest.TestCase):
    def test_format_then_parse_multi_interval(self):
        raw = format_intervals([(100, 120), (150, 170)])
        self.assertEqual(raw, "100-120;150-170")
        parsed = parse_interval_list(raw)
        self.assertEqual(
            parsed,
            [{"start": 100, "end": 120}, {"start": 150, "end": 170}],
        )


if __name__ == "__main__":
    unittest.main()
