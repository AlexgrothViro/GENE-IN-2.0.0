"""GEN-005F3A: genein.pipeline.state_api is a thin adapter over run_state.py.

These tests prove two things test_batch.py's end-to-end runs cannot isolate:
1. The adapter delegates to run_state.py's existing functions -- it never
   reimplements the state machine.
2. Its module cache cannot silently hand back a run_state module imported
   from a different checkout.
"""
import os
from pathlib import Path
import sys
import types

import pytest

from genein.pipeline import state_api

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts/evidence"
pytestmark = pytest.mark.skipif(os.name != "posix", reason="Pipeline adapters require POSIX shell/process groups")


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(state_api, "_MODULE_CACHE", {})
    return state_api.RunStateApi(SCRIPTS, ROOT / "config/evidence_activation.json",
                                 ROOT / "config/evidence_profiles.json")


def test_load_run_state_caches_by_resolved_directory(monkeypatch):
    monkeypatch.setattr(state_api, "_MODULE_CACHE", {})
    module = state_api.load_run_state(SCRIPTS)
    assert module.__name__ == "run_state"
    assert Path(module.__file__).resolve() == (SCRIPTS / "run_state.py").resolve()
    # A second call for the same directory must not re-import.
    assert state_api.load_run_state(SCRIPTS) is module


def test_load_run_state_refuses_a_module_cached_from_another_checkout(monkeypatch, tmp_path):
    monkeypatch.setattr(state_api, "_MODULE_CACHE", {})
    foreign = types.ModuleType("run_state")
    foreign.__file__ = str(tmp_path / "other-checkout" / "scripts" / "evidence" / "run_state.py")
    monkeypatch.setitem(sys.modules, "run_state", foreign)
    with pytest.raises(RuntimeError, match="different checkout"):
        state_api.load_run_state(SCRIPTS)


def test_init_delegates_to_initialize_runner_state(api, monkeypatch):
    calls = []
    monkeypatch.setattr(api.rs, "initialize_runner_state",
                        lambda *a, **k: calls.append((a, k)) or {"ok": True})
    monkeypatch.setattr(api, "_policy", lambda: "the-policy")
    result = api.init(Path("/tmp/state.json"), "run-1", "evidence_batch", ["s1", "s2"], "batch-1")
    assert result == {"ok": True}
    assert calls == [((Path("/tmp/state.json"), "run-1", "evidence_batch", ["s1", "s2"], "batch-1", "the-policy"), {})]


def test_adopt_delegates_to_adopt_reserved_state(api, monkeypatch):
    calls = []
    monkeypatch.setattr(api.rs, "adopt_reserved_state",
                        lambda *a, **k: calls.append((a, k)) or {"ok": True})
    monkeypatch.setattr(api, "_policy", lambda: "the-policy")
    result = api.adopt(Path("/tmp/state.json"), run_id="run-1", action="evidence_batch",
                       samples=["s1"], batch_id="batch-1", reservation_token="tok",
                       staging=Path("/tmp/staging"), final=Path("/tmp/final"))
    assert result == {"ok": True}
    assert calls == [((Path("/tmp/state.json"),), {
        "run_id": "run-1", "action": "evidence_batch", "samples": ["s1"], "batch_id": "batch-1",
        "reservation_token": "tok", "staging": Path("/tmp/staging"), "final": Path("/tmp/final"),
        "policy": "the-policy",
    })]


def test_stage_delegates_to_mutate_state_file_set_stage_and_set_failure(api, monkeypatch):
    mutate_calls = []
    monkeypatch.setattr(api.rs, "mutate_state_file",
                        lambda path, mutator: mutate_calls.append((path, mutator)))
    api.stage(Path("/tmp/state.json"), "controls", "failed", "boom", failure_type="TOOL_FAILURE")
    assert len(mutate_calls) == 1
    path, mutator = mutate_calls[0]
    assert path == Path("/tmp/state.json")

    set_stage_calls, set_failure_calls = [], []
    monkeypatch.setattr(api.rs, "set_stage", lambda *a: set_stage_calls.append(a))
    monkeypatch.setattr(api.rs, "set_failure", lambda *a: set_failure_calls.append(a))
    fake_state = {"status": "running"}
    mutator(fake_state)
    assert set_stage_calls == [(fake_state, "controls", "failed", "boom")]
    assert set_failure_calls == [(fake_state, "TOOL_FAILURE", "controls", "boom", None)]


def test_write_failure_evidence_delegates_under_the_same_lock(api, monkeypatch):
    calls = []

    class FakeLock:
        def __enter__(self):
            calls.append("locked")

        def __exit__(self, *exc):
            calls.append("unlocked")

    monkeypatch.setattr(api.rs, "state_lock", lambda path: FakeLock())
    monkeypatch.setattr(api.rs, "read_state", lambda path: {"sample_ids": ["s1"]})
    monkeypatch.setattr(api.rs, "write_failure_evidence",
                        lambda state, root, reason, policy: calls.append((state, root, reason, policy)))
    monkeypatch.setattr(api, "_policy", lambda: "the-policy")
    api.write_failure_evidence(Path("/tmp/state.json"), Path("/tmp/root"), "why")
    assert calls == ["locked", ({"sample_ids": ["s1"]}, Path("/tmp/root"), "why", "the-policy"), "unlocked"]
