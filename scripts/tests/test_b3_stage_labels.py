"""Rótulos de etapa do QC, do resgate, do BLAST e da falha de preflight do banco."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STEPS = (ROOT / "scripts/pipeline/sample_steps.sh").read_text(encoding="utf-8")


def test_killed_blastn_keeps_its_signal_exit_code():
    import sys
    sys.path.insert(0, str(ROOT / "scripts/evidence"))
    from blast_router import external_blast_exit

    assert external_blast_exit(-9) == 137
    assert external_blast_exit(-15) == 143
    assert external_blast_exit(1) == 1
    assert external_blast_exit(0) == 0


def test_step_labels_do_not_inherit_the_previous_stage():
    qc = STEPS.index('export PIPELINE_ETAPA="QC_FASTP"')
    fastp = STEPS.index('"$SCRIPT_DIR/qc_fastp.sh"')
    blast_banner = STEPS.index('log_info "[5/6] BLAST dos contigs"')
    rescue = STEPS.index('export PIPELINE_ETAPA="RESCUE_READS"')
    rescue_router = STEPS.index('blast_router.py" --query "$RESCUE_FA"')
    restored_blast = STEPS.index('export PIPELINE_ETAPA="BLAST"', rescue)
    contig_blast = STEPS.index('blastn -task "$BLAST_TASK"')
    database = STEPS.index('export PIPELINE_ETAPA="DATABASE_PREFLIGHT"')
    composite = STEPS.index("Banco composto sem manifesto")
    assert database < composite < qc < fastp
    assert STEPS.index('export PIPELINE_ETAPA="BLAST"') < blast_banner < rescue < rescue_router
    assert restored_blast < contig_blast
    assert "--failed-stage database_preflight" in STEPS
    assert "exit 65" in STEPS


def test_missing_composite_database_is_database_preflight(tmp_path):
    work = tmp_path / "work"
    evidence = tmp_path / "evidence"
    work.mkdir()
    contigs = tmp_path / "contigs.fa"
    contigs.write_text(">a\nACGT\n", encoding="utf-8")
    run_id = "stagepre1"
    state = evidence / "state" / f"{run_id}.json"
    subprocess.run(
        [
            "python3", str(ROOT / "scripts/evidence/run_state.py"),
            "--state", str(state), "init",
            "--run-id", run_id, "--action", "evidence_single", "--sample", "stagec",
        ],
        check=True,
    )
    env = os.environ.copy()
    for name in ("DB", "DB_QUERY", "REF_FASTA", "BOWTIE2_INDEX"):
        env.pop(name, None)
    env.update({
        "GENEIN_WORK_ROOT": str(work),
        "EVIDENCE_V2": "true",
        "EVIDENCE_ROOT": str(evidence),
        "EVIDENCE_RUN_ID": run_id,
        "EVIDENCE_COMPOSITE_DB": str(tmp_path / "missing_composite_panel"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    result = subprocess.run(
        [
            "bash", str(ROOT / "scripts/pipeline/run.sh"),
            "--sample", "stagec", "--contigs", str(contigs),
            "--threads", "1", "--evidence-v2", "--evidence-root", str(evidence),
        ],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 65, result.stderr
    log = (work / "logs/stagec_pipeline.log").read_text(encoding="utf-8")
    assert "[DATABASE_PREFLIGHT]" in log
    assert "Banco composto sem manifesto" in log
    assert "[QC_FASTP]" not in log
    assert "[HOST_FILTER]" not in log
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["status"] == "failed"
    assert saved["failed_stage"] == "database_preflight"
    assert saved["failure_type"] == "INPUT_INVALID"
    quality = next(item for item in saved["stages"] if item["id"] == "quality_control")
    assert quality["status"] == "pending"
    assert not (evidence / "runs" / run_id / "SUCCESS.json").exists()
