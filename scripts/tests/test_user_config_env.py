"""The panel stores picornavirus.env outside the source tree."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_shell_and_python_choose_the_same_user_file(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.delenv("GENEIN_CONFIG_FILE", raising=False)
    monkeypatch.setenv("GENEIN_WORK_ROOT", str(work))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    from genein.paths import user_config_env_path
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; genein_user_config_file', "test",
         str(ROOT / "scripts/lib/genein_config_path.sh")],
        env=os.environ.copy(), text=True, capture_output=True, check=True,
    )
    assert result.stdout.strip() == str(user_config_env_path())


def test_shell_prefers_the_user_file_and_otherwise_keeps_the_checkout_copy(tmp_path):
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / "config/picornavirus.env").write_text("THREADS=6\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    helper = str(ROOT / "scripts/lib/genein_config_path.sh")
    env = os.environ.copy()
    env.update(REPO_ROOT=str(repo), GENEIN_WORK_ROOT=str(work))
    env.pop("GENEIN_CONFIG_FILE", None)
    checkout = subprocess.run(
        ["bash", "-c", 'source "$1"; genein_resolve_config_file', "test", helper],
        env=env, text=True, capture_output=True, check=True,
    )
    assert checkout.stdout.strip() == str(repo / "config/picornavirus.env")
    user = work / "config"
    user.mkdir()
    (user / "picornavirus.env").write_text("THREADS=3\n", encoding="utf-8")
    chosen = subprocess.run(
        ["bash", "-c", 'source "$1"; genein_resolve_config_file', "test", helper],
        env=env, text=True, capture_output=True, check=True,
    )
    assert chosen.stdout.strip() == str(user / "picornavirus.env")


def test_panel_writes_the_example_outside_the_source(tmp_path, monkeypatch):
    import dashboard.config as config
    from dashboard.server import _ensure_config_env
    source_file = ROOT / "config" / "picornavirus.env"
    before = source_file.exists()
    target = tmp_path / "home" / ".gene-in" / "config" / "picornavirus.env"
    monkeypatch.setattr(config, "CONFIG_ENV_PRIMARY", target)
    monkeypatch.setattr(config, "REPO_CONFIG_ENV", tmp_path / "absent-repo.env")
    monkeypatch.setattr(config, "CONFIG_ENV_LEGACY", tmp_path / "absent-legacy.env")
    _ensure_config_env()
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == (ROOT / "config/picornavirus.env.example").read_text(encoding="utf-8")
    assert source_file.exists() is before
    assert config.ensure_user_config_env() is False


def test_save_copies_an_existing_source_config_without_rewriting_it(tmp_path, monkeypatch):
    import dashboard.config as config
    repo = tmp_path / "picornavirus.env"
    repo.write_text("THREADS=7\n# keep\n", encoding="utf-8")
    user = tmp_path / "user" / "picornavirus.env"
    monkeypatch.setattr(config, "REPO_CONFIG_ENV", repo)
    monkeypatch.setattr(config, "CONFIG_ENV_LEGACY", tmp_path / "missing.env")
    monkeypatch.setattr(config, "CONFIG_ENV_PRIMARY", user)
    saved = config.save_config_env({"THREADS": "9"})
    assert repo.read_text(encoding="utf-8") == "THREADS=7\n# keep\n"
    text = user.read_text(encoding="utf-8")
    assert "THREADS=9" in text
    assert "# keep" in text
    assert saved["THREADS"] == "9"


def test_dashboard_job_keeps_the_user_config_when_the_work_root_becomes_per_run(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("GENEIN_WORK_ROOT", str(work))
    monkeypatch.delenv("GENEIN_CONFIG_FILE", raising=False)
    from scripts.dashboard.jobs import build_command
    _cmd, env = build_command(
        "evidence_pipeline",
        {"sample": "SAMPLE", "db": "ptv", "assembler": "consensus",
         "host_filter_mode": "none", "run_id": "first-run-00001"},
    )
    assert env["GENEIN_CONFIG_FILE"] == str(work / "config" / "picornavirus.env")
    assert Path(env["GENEIN_WORK_ROOT"]) != work
