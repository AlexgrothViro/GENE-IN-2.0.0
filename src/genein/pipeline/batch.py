"""Sequential Evidence batch orchestration; state and commit contracts stay intact."""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

from .sample import BatchCancelled, ProcessRunner, execute_sample
from .state_api import RunStateApi


def metrics_root(repo_root: Path, work_root: str | None, sample_id: str) -> Path:
    """Directory that holds measured post-QC reports for this batch.

    The CLI sets ``GENEIN_WORK_ROOT`` to the output directory, and the pipeline
    writes ``results/qc`` there. The same variable, when exported only to keep
    reference FASTA and indexes outside the source, does not contain those
    reports. In that case the batch repository remains the metrics root.
    """
    if work_root and sample_id:
        candidate = Path(work_root)
        if (candidate / "results" / "qc" / f"{sample_id}_fastp.json").is_file():
            return candidate
    return repo_root


class Batch:
    def __init__(self, args, repo_root: Path, runner: ProcessRunner):
        self.args = args
        self.repo_root = repo_root
        self.runner = runner
        self.scripts = repo_root / "scripts/evidence"
        self.policy = repo_root / "config/evidence_activation.json"
        self.root = Path(args.evidence_root)
        self.profiles = Path(args.profiles)
        self.run_id = args.run_id or str(uuid.uuid4())
        self.stage_id = "input_validation"
        self.owned = False
        self.committed = False
        self.state_api = RunStateApi(self.scripts, self.policy, self.profiles)

    def command(self, script, *args, **kwargs):
        return self.runner.run([sys.executable, self.scripts / script, *args], **kwargs)

    def stage(self, stage_id, status, message=None):
        self.stage_id = stage_id
        self.state_api.stage(self.state_file, stage_id, status, message)

    def interrupted(self, cancelled: bool):
        if not self.owned or self.committed:
            return
        status = "cancelled" if cancelled else "failed"
        failure = "CANCELLED" if cancelled else "TOOL_FAILURE"
        message = ("Lote cancelado; resultados parciais não foram promovidos." if cancelled
                   else "Lote interrompido; artefatos permaneceram em staging.")
        operations = []
        if not cancelled:
            operations.append(lambda: self.state_api.write_failure_evidence(
                self.state_file, self.staging, f"Batch Evidence V2 failed: {self.stage_id}",
            ))
        operations.append(lambda: self.state_api.stage(
            self.state_file, self.stage_id, status, message, failure_type=failure,
        ))
        operations.append(lambda: self.state_api.status(
            self.state_file, status, failure_type=failure,
            failed_stage=self.stage_id, failure_message=message,
        ))
        for operation in operations:
            try:
                operation()
            # Mirrors the previous subprocess boundary: any of these failing
            # must stay best-effort so the original failure is still reported.
            except (OSError, ValueError, TimeoutError) as exc:
                print(f"[WARN] unable to record batch interruption: {exc}", file=sys.stderr)

    def reserve(self):
        self.run_id = self.runner.run([
            sys.executable, self.repo_root / "scripts/lib/input_validation.py",
            "run-id", self.run_id,
        ], capture=True)
        self.state_file = self.root / "state" / f"{self.run_id}.json"
        self.staging = self.root / ".staging" / self.run_id
        self.final = self.root / "runs" / self.run_id
        for directory in (self.state_file.parent, self.staging.parent, self.final.parent):
            directory.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=f".manifest.{self.run_id}.", dir=self.staging.parent)
        os.close(descriptor)
        validated = Path(name)
        try:
            self.command("validate_manifest.py", "--manifest", self.args.batch_manifest, "--out", validated)
            with validated.open(encoding="utf-8", newline="") as handle:
                self.rows = list(csv.DictReader(handle, delimiter="\t"))
            if not self.rows:
                raise ValueError("batch has no samples")
            self.batch_id = self.rows[0]["batch_id"]
            samples = [row["sample_id"] for row in self.rows]
            token = self.runner.env.get("EVIDENCE_RESERVATION_TOKEN", "")
            if self.final.exists() or self.staging.exists():
                raise ValueError(f"run id already has staging or final artifacts: {self.run_id}")
            self.runner.checkpoint()
            if self.state_file.exists():
                if not token:
                    raise ValueError(f"run id already exists: {self.run_id}")
                self.state_api.adopt(
                    self.state_file, run_id=self.run_id, action="evidence_batch",
                    samples=samples, batch_id=self.batch_id, reservation_token=token,
                    staging=self.staging, final=self.final,
                )
            else:
                if token:
                    raise ValueError(f"reserved run state is missing: {self.run_id}")
                self.state_api.init(self.state_file, self.run_id, "evidence_batch", samples, self.batch_id)
            # As in the existing adapters, only the atomic staging winner owns cleanup.
            self.staging.mkdir()
            self.owned = True
            self.runner.checkpoint()
            (self.staging / "samples").mkdir()
            (self.staging / "work").mkdir()
            self.normalized = self.staging / "work/manifest.tsv"
            validated.replace(self.normalized)
            self.runner.run(["cp", self.normalized, self.staging / "batch_manifest.tsv"])
        finally:
            validated.unlink(missing_ok=True)

    def execute(self):
        self.reserve()
        self.stage("input_validation", "done", "Manifesto e entradas validados.")
        run_map = self.staging / "work/run_map.tsv"
        self.stage("quality_control", "running", "Processando amostras do lote em runs isolados.")
        with run_map.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["sample_id", "run_id"])
            handle.flush()
            for row in self.rows:
                self.runner.checkpoint()
                child_id = f"{self.run_id}-{row['sample_id']}"
                writer.writerow([row["sample_id"], child_id])
                handle.flush()
                execute_sample(repo_root=self.repo_root, row=row, run_id=child_id,
                               profiles=self.profiles, evidence_root=self.root,
                               threads=self.args.threads, runner=self.runner, options=self.args.sample_arg)
                child_run = self.root / "runs" / child_id
                if child_run.is_dir():
                    self.runner.run(["cp", "-a", child_run,
                                     self.staging / "samples" / row["sample_id"]])
                else:
                    # Uma amostra pode encerrar com exit 0 sem abrir transação de
                    # Evidence — é o caso da saturação total pelo hospedeiro, em que
                    # o pipeline reconhece o desfecho e não promove FASTQ vazio. Antes
                    # desta guarda o `cp` falhava e abortava o LOTE INTEIRO por causa
                    # de uma amostra que terminou corretamente. Ausência de diretório
                    # é registrada, nunca silenciada, e nunca tratada como negativo
                    # biológico: quem classifica o desfecho é o recibo externo.
                    (self.staging / "samples" / row["sample_id"]).mkdir(parents=True, exist_ok=True)
                    print(f"[BATCH] {row['sample_id']}: sem transação de Evidence "
                          f"(run {child_id} ausente); desfecho no recibo externo da amostra.")

        for stage_id in ("quality_control", "assembly", "initial_blast", "hsp_aggregation",
                         "locus_building", "competitive_search", "read_remapping", "coverage"):
            self.stage(stage_id, "done", "Concluído nos runs-filhos transacionais.")
        metrics = self.staging / "work/metrics.tsv"
        measured = metrics_root(
            self.repo_root, self.runner.env.get("GENEIN_WORK_ROOT"), self.rows[0]["sample_id"],
        )
        self.command("collect_batch_metrics.py", "--manifest", self.normalized, "--repo-root", measured,
                     "--evidence-root", self.root, "--run-map", run_map, "--out", metrics)
        ratio = self.command("config_value.py", "--activation-policy", self.policy, "--profiles", self.profiles,
                             "--key", "controls.provisional_sample_to_negative_ratio", capture=True)
        statuses = self.staging / "control_status.tsv"
        self.stage("controls", "running")
        self.command("evaluate_controls.py", "--manifest", self.normalized, "--sample-metrics", metrics,
                     "--provisional-ratio", ratio, "--out", statuses)
        self.command("apply_control_status.py", "--statuses", statuses, "--evidence-root", self.staging,
                     "--activation-policy", self.policy, "--profiles", self.profiles)
        self.stage("controls", "done", "Estados de controle aplicados somente à cópia transacional do lote.")
        self.stage("evidence_classification", "running")
        provenance = []
        for field in ("shadow_mode", "profile_version", "activation_record_id"):
            # Preserve the existing public-policy provenance lookup.
            value = self.command("activation_policy.py", "public", "--field", field, capture=True)
            provenance += ["--value", f"{field}={value}"]
        self.command("write_provenance.py", "--config", self.profiles, "--out", self.staging / "provenance.json",
                     "--artifact", f"e1_activation_policy={self.policy}",
                     "--artifact", f"batch_manifest={self.staging / 'batch_manifest.tsv'}",
                     "--value", f"run_id={self.run_id}", "--value", f"batch_id={self.batch_id}",
                     *provenance, "--value", f"child_run_count={len(self.rows)}")
        self.command("summarize_batch.py", "--batch-id", self.batch_id, "--run-id", self.run_id,
                     "--root", self.staging, "--run-map", run_map, "--statuses", statuses,
                     "--out", self.staging / "batch_evidence.json", "--report", self.staging / "batch_report.md")
        self.stage("evidence_classification", "done")
        self.stage("report_export", "done", "Relatório do lote exportado.")
        self.runner.checkpoint()
        # Do not tear down the existing locked rename/SUCCESS/state transaction.
        # Cancellation before this boundary wins; a complete commit wins afterward.
        self.command("finalize_batch.py", "--state", self.state_file, "--staging", self.staging,
                     "--final", self.final, "--run-map", run_map, allow_cancel=False)
        self.committed = True
        # Preserve the adapters' cancellation exit code without overwriting a
        # terminal commit when the request races with locked finalization.
        self.runner.checkpoint()
        print(f"[OK] Batch Evidence V2 promoted: {self.final}")
        print(f"[RUN_ID] {self.run_id}")


def main(argv=None, *, repo_root: Path) -> int:
    parser = argparse.ArgumentParser(description="Internal Evidence batch orchestrator")
    parser.add_argument("--batch-manifest", required=True)
    parser.add_argument("--profiles", default=str(repo_root / "config/evidence_profiles.json"))
    parser.add_argument("--threads", default=os.environ.get("THREADS") or "4")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--evidence-root", default=str(repo_root / "results/evidence"))
    parser.add_argument("--sample-arg", action="append", default=[], help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    runner = ProcessRunner(dict(os.environ))
    batch = Batch(args, repo_root, runner)
    with runner.signals():
        try:
            batch.execute()
        except BatchCancelled:
            batch.interrupted(True)
            return 130
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            batch.interrupted(False)
            print(f"[FATAL] {exc}", file=sys.stderr)
            if isinstance(exc, subprocess.CalledProcessError):
                return exc.returncode if exc.returncode > 0 else 128 - exc.returncode
            return 1 if batch.owned else 2
    return 0
