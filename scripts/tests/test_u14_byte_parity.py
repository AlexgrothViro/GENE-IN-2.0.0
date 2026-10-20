import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / 'scripts/tests/fixtures/b1_reference'
sys.path.insert(0, str(ROOT / 'scripts/evidence'))
from blast_router import deduplicate_combined_files


class U14ByteParityTests(unittest.TestCase):
    def test_router_streaming_matches_b1_bytes(self):
        loader = importlib.machinery.SourceFileLoader('b1_router_reference', str(REFERENCE / 'blast_router.py.txt'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        original = importlib.util.module_from_spec(spec)
        loader.exec_module(original)
        def row(q, subject='s', bits=30, reverse=False):
            return f'{q}\t{subject}\t95\t20\t1\t0\t1\t20\t{29 if reverse else 10}\t{10 if reverse else 29}\t1e-6\t{bits}\t40\t100\t19\t0\n'
        cases = [([], []), (['', ''], ['q1']),
                 ([row('q1') + row('q3', reverse=True),
                   row('q1', bits=40) + row('q1', 'other') + row('q2') + row('q3', reverse=True)], ['q1','q2','q3']),
                 ([row('q1') * 10000, row('q1') * 2000], ['q1'])]
        with tempfile.TemporaryDirectory() as tmp:
            for chunks, order in cases:
                paths=[]
                for i, chunk in enumerate(chunks):
                    path=Path(tmp)/f'{i}.tsv'; path.write_text(chunk); paths.append(path)
                output=Path(tmp)/'combined.tsv'
                deduplicate_combined_files(paths, order, output)
                self.assertEqual(output.read_bytes(), original.deduplicate_combined_hits(chunks).encode())

    def test_filter_candidates_ledger_and_provenance_match_b1_bytes(self):
        def row(q, pid='95.123', length=80, evalue='1e-8', bits=50, qlen=100):
            return f'{q}\ts\t{pid}\t{length}\t0\t0\t1\t{length}\t1\t{length}\t{evalue}\t{bits}\t{qlen}\t100\t80\t0\n'
        raw = ('short\ts\n\n' + row('invalid', pid='bad') + row('zero', qlen=0)
               + row('pid', pid='89') + row('ev', evalue='1') + row('len', length=20)
               + row('tie', pid='95') * 2 + row('tie', pid='96', bits=60)
               + row('rounding') + row('shortpass', pid='99', length=20, qlen=20))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw.tsv'; output=Path(tmp)/'candidate.tsv'
            path.write_text(raw)
            env=dict(os.environ, PYTHONPATH=str(ROOT/'scripts/lib'))
            def run(script):
                subprocess.run([sys.executable,str(script),'--blast-raw',str(path),'--out-tsv',str(output)],env=env,check=True,capture_output=True)
                return {suffix: Path(str(output)+suffix).read_bytes() for suffix in ('','.decisions.tsv','.provenance.json')}
            before=run(REFERENCE/'filter_rescue_reads.py.txt')
            after=run(ROOT/'scripts/pipeline/filter_rescue_reads.py')
            self.assertEqual(before, after)
