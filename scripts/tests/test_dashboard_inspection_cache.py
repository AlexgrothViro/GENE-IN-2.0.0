import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts/lib'), str(ROOT / 'scripts/evidence')]
from evidence_dashboard import EvidenceDashboardService


class InspectionCacheTests(unittest.TestCase):
    def test_pending_single_flight_cached_and_invalidated(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = EvidenceDashboardService(Path(tmp), background_inspection=True)
            run = service.evidence_root / 'runs/test-run'
            run.mkdir(parents=True)
            (run / 'SUCCESS.json').write_text('{}')
            release = threading.Event()
            expected = {'status': 'EVIDENCE_VALID', 'valid_alpha2': True}
            def inspect(run_id):
                release.wait(5)
                return expected
            service._inspect_run_uncached = Mock(side_effect=inspect)
            try:
                self.assertEqual(service.inspect_run('test-run')['status'], 'VALIDATION_PENDING')
                self.assertFalse(service.inspect_run('test-run')['valid_alpha2'])
                release.set()
                service._inspections['test-run'][1].result(timeout=5)
                self.assertEqual(service.inspect_run('test-run'), expected)
                self.assertEqual(service._inspect_run_uncached.call_count, 1)
                (run / 'SUCCESS.json').write_text('{"changed":true}')
                service.inspect_run('test-run')
                service._inspections['test-run'][1].result(timeout=5)
                self.assertEqual(service._inspect_run_uncached.call_count, 2)
                service.refresh_inspection('test-run')
                service.inspect_run('test-run')
                service._inspections['test-run'][1].result(timeout=5)
                self.assertEqual(service._inspect_run_uncached.call_count, 3)
                self.assertEqual(service.inspect_run('test-run'), expected)
            finally:
                release.set()
                service._inspection_pool.shutdown(wait=True)
