import gzip
from unittest.mock import patch
from scripts.dashboard import handler


def test_compressed_fastq_is_not_reencoded_by_import_or_explicit_replace(tmp_path):
    r1 = gzip.compress(b'@read/1\nACGT\n+\nIIII\n', mtime=0)
    r2 = gzip.compress(b'@read/2\nTGCA\n+\nIIII\n', mtime=0)
    with patch.object(handler, 'REPO_ROOT', tmp_path):
        for replace in (False, True):
            handler.import_uploaded_files('SAFE', 'R1.fastq.gz', r1, 'R2.fastq.gz', r2, replace=replace)
            assert (tmp_path / 'data/raw/SAFE_R1.fastq.gz').read_bytes() == r1
            assert (tmp_path / 'data/raw/SAFE_R2.fastq.gz').read_bytes() == r2
