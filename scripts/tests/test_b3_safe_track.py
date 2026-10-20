import subprocess
import sys
from pathlib import Path


def test_all_safe_preserves_real_failures_and_missing_tool_status():
    from scripts.ops.validation_track_runner import classify_exit, summarize, exit_code_for
    assert classify_exit(1, True) == "FAIL"
    assert classify_exit(-15, True) == "FAIL"
    assert classify_exit(77, True) == "NOT_EXECUTED"
    assert classify_exit(0, True) == "PASS"
    overall = summarize([{"status": "PASS"}, {"status": classify_exit(1, True)}])
    assert overall == "FAIL"
    assert exit_code_for("all-safe", overall, ["engineering", "operational"]) == 1


def test_all_safe_never_imports_optimization(tmp_path):
    root = Path(__file__).resolve().parents[2]
    code = '''
import builtins, runpy, sys
original = builtins.__import__
def checked(name, *args, **kwargs):
    if 'optimization' in name:
        raise AssertionError('Forbidden import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = checked
sys.argv = [sys.argv[1], '--track', 'all-safe', '--dry-run', '--out', sys.argv[2]]
runpy.run_path(sys.argv[0], run_name='__main__')
'''
    result = subprocess.run([sys.executable, '-c', code, str(root/'scripts/ops/validation_track_runner.py'), str(tmp_path/'safe.json')], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
