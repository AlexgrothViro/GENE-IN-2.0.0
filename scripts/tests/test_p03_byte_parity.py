import subprocess
from unittest.mock import patch
from scripts.evidence.write_provenance import version


def test_supported_blast_version_preserves_stdout_bytes():
    expected = 'blastn: 2.17.0+'
    with patch('scripts.evidence.write_provenance.shutil.which', return_value='/bin/blastn'), patch('scripts.evidence.write_provenance.subprocess.run', return_value=subprocess.CompletedProcess([], 0, expected + '\n', '')) as run:
        assert version('blastn').encode() == expected.encode()
        assert run.call_args.args[0] == ['blastn', '-version']
    with patch('scripts.evidence.write_provenance.shutil.which', return_value='/bin/tool'), patch('scripts.evidence.write_provenance.subprocess.run', side_effect=[subprocess.CompletedProcess([], 1, 'USAGE\n', ''), subprocess.CompletedProcess([], 0, 'tool: 1.2\n', '')]):
        assert version('tool') == 'tool: 1.2'
