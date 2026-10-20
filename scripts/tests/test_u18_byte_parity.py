from unittest.mock import patch
from scripts.dashboard import jobs


def test_partial_snapshot_copies_qc_byte_for_byte(tmp_path):
    work = tmp_path / 'work'
    qc = work / 'results/qc/SAMPLE_fastp.json'
    qc.parent.mkdir(parents=True)
    qc.write_bytes(b'{"reads":100}\n')
    contigs = work / 'data/assemblies/SAMPLE_assembly/contigs.fa'
    contigs.parent.mkdir(parents=True)
    contigs.write_bytes(b'>contig\nACGT\n')
    with patch.object(jobs, 'get_runs_dir', return_value=tmp_path / 'runs'):
        result = jobs.snapshot_run_artifacts({'run_id': 'failed-run-00001', 'sample': 'SAMPLE', 'status': 'failed', 'partial': True, 'work_root': str(work)})
    from pathlib import Path
    assert (Path(result) / 'qc.json').read_bytes() == qc.read_bytes()
    assert (Path(result) / 'assembly_contigs.fa').read_bytes() == contigs.read_bytes()
