"""Public run adapter over the existing sample and batch execution boundaries.

This module selects inputs, reserves an external output directory and forwards
arguments. Stage execution and Evidence transactions remain in their existing
adapters; execution.json is only a launcher receipt, never a scientific result.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from genein.identity import source_commit, software_version
from .sample import BatchCancelled, ProcessRunner


def source_root() -> Path:
    root = Path(os.environ.get("GENEIN_REPO_ROOT") or Path(__file__).resolve().parents[3]).resolve()
    if not (root / "scripts/pipeline/run_sample.sh").is_file():
        raise ValueError("Pipeline adapters are missing. Use the Gene-In checkout/editable installation or set GENEIN_REPO_ROOT.")
    return root


def _positive_threads(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("threads must be an integer from 1 to 256") from exc
    if not 1 <= result <= 256:
        raise argparse.ArgumentTypeError("threads must be an integer from 1 to 256")
    return result


def register_commands(commands) -> None:
    parser = commands.add_parser("run", help="Run a sample or batch into a new external output directory.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--sample", help="Sample identifier; pair with --r1/--r2, --single or --contigs.")
    target.add_argument("--batch-manifest", help="Existing Evidence TSV manifest; paths inside are relative to the TSV.")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--r1", help="Paired FASTQ mate 1 (requires --r2).")
    inputs.add_argument("--single", help="Single-end FASTQ.")
    inputs.add_argument("--contigs", help="FASTA of previously assembled contigs.")
    parser.add_argument("--r2", help="Paired FASTQ mate 2 (requires --r1).")
    parser.add_argument("--output-root", required=True, help="New directory outside the source tree; existing directories are never overwritten.")
    parser.add_argument("--blast-db", required=True, help="Prepared BLAST database prefix with .db-manifest.json; no automatic download.")
    parser.add_argument("--run-id", help="Run identifier (8–128 safe characters); generated if omitted.")
    parser.add_argument("--threads", type=_positive_threads, default=4)
    parser.add_argument("--assembler", choices=("velvet", "spades", "metaspades"))
    parser.add_argument("--analysis-profile", choices=("default", "assembly-consensus"))
    parser.add_argument("--kmer")
    parser.add_argument("--spades-params", help="Extra existing SPAdes options, e.g. --spades-params='-m 4'.")
    parser.add_argument("--advanced-kmers")
    parser.add_argument("--blast-task", choices=("blastn", "blastn-short"))
    parser.add_argument("--blast-word-size")
    parser.add_argument("--blast-evalue")
    parser.add_argument("--search-profiles", help="Explicit existing search profiles, e.g. A,C; default behavior is preserved.")
    parser.add_argument("--evidence-v2", action="store_true", help="Also export Evidence artifacts (always enabled for the existing batch workflow).")
    parser.add_argument("--evidence-profiles", help="Existing Evidence profile catalog.")
    parser.add_argument("--library-mode", help="Sample library metadata; use --evidence-v2 to export it.")
    parser.add_argument("--umi-mode", help="Sample UMI metadata; use --evidence-v2 to export it.")
    parser.add_argument("--role", choices=("sample", "positive", "negative_extraction", "negative_library", "negative_sequencing"))
    parser.add_argument("--expected-target", help="Required for a positive control.")
    parser.add_argument("--composite-db", help="Curated competitive BLAST panel for explicit profile B.")
    parser.add_argument("--subject-labels")
    parser.add_argument("--panel-fasta")
    parser.add_argument("--panel-index")
    parser.add_argument("--host-name")
    parser.add_argument("--host-index", help="Prepared Bowtie2 host prefix; enables existing host filtering.")
    parser.add_argument("--host-accession")
    parser.add_argument(
        "--host-expected", choices=("true", "false"),
        help=("Whether the declared host is expected. The backward-compatible default is true: "
              "a low alignment rate remains fatal; false permits it with a warning. "
              "Total host saturation is a recognized completed outcome either way."),
    )
    for flag in ("skip-qc", "skip-host-filter", "rescue-mode"):
        parser.add_argument(f"--{flag}", action="store_true")
    parser.set_defaults(handler=run, run_parser=parser)


def _file(value: str) -> str:
    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Entrada ausente ou vazia: {path}")
    return str(path)


def _identifier(root: Path, kind: str, value: str) -> str:
    result = subprocess.run(
        [sys.executable, str(root / "scripts/lib/input_validation.py"), kind, value],
        text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"Invalid {kind}: {value}")
    return result.stdout.strip()


_OOM_TOKENS = (
    "out of memory", "out-of-memory", "memoryerror",
    "cannot allocate memory", "std::bad_alloc", "oom-kill",
)
_KILLED_MESSAGES = {
    "MEMORY_EXHAUSTED": "Falta de memória durante o processamento. Libere memória antes de repetir.",
    "PROCESS_KILLED": "Processo morto por SIGKILL. Pode ter sido encerrado pelo sistema por falta de memória ou por uma ação externa; confira o log do sistema.",
    "PROCESS_TERMINATED": "Processo interrompido por SIGTERM (sinal de término externo).",
}


def _pipeline_log_excerpt(output: Path, limit: int = 200_000) -> str:
    logs = output / "logs"
    if not logs.is_dir():
        return ""
    parts = []
    for path in sorted(logs.glob("*_pipeline.log")):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        parts.append(data[-limit:].decode("utf-8", errors="replace"))
    return "\n".join(parts)


def _database_preflight_message(excerpt: str) -> str:
    default = "Banco BLAST não corresponde ao manifesto; reconstrua o banco antes de analisar."
    for line in reversed(excerpt.splitlines()):
        if "[FATAL]" in line and "[DATABASE_PREFLIGHT]" in line and "—" in line:
            detail = line.split("—", 1)[1].strip()
            if detail:
                return detail
    return default


def classify_launcher_failure(code: int, excerpt: str = "") -> tuple[str, str | None, str | None]:
    """Map a child exit the way the dashboard classifies a killed process.

    Exit 65 stays a database preflight failure. SIGKILL, SIGTERM and an
    out-of-memory trace are read from the exit code or from the pipeline log
    when a wrapper collapses the signal into exit code 1.
    """
    lowered = excerpt.lower()
    if any(token in lowered for token in _OOM_TOKENS):
        return "MEMORY_EXHAUSTED", None, _KILLED_MESSAGES["MEMORY_EXHAUSTED"]
    if code == 137 or "sigkill" in lowered:
        return "PROCESS_KILLED", None, _KILLED_MESSAGES["PROCESS_KILLED"]
    if code == 143 or "sigterm" in lowered:
        return "PROCESS_TERMINATED", None, _KILLED_MESSAGES["PROCESS_TERMINATED"]
    if code == 65:
        return "INPUT_INVALID", "database_preflight", _database_preflight_message(excerpt)
    if code == 130:
        return "CANCELLED", None, None
    return "TOOL_FAILURE", None, None


def _receipt(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _bowtie2_index(prefix: str) -> None:
    """Fail before reserving an output directory when the host index is unusable."""
    base = Path(prefix).expanduser().resolve()
    for extension in ("bt2", "bt2l"):
        if all((base.parent / f"{base.name}.{part}.{extension}").is_file()
               and (base.parent / f"{base.name}.{part}.{extension}").stat().st_size
               for part in ("1", "2", "3", "4", "rev.1", "rev.2")):
            return
    raise ValueError(
        f"Prepared Bowtie2 host index not found at {base}; expected the six .bt2 or .bt2l components. "
        "Build it with scripts/ops/prepare_host_reference.sh before enabling host filtering."
    )


def _host_arguments(args) -> None:
    """Host filtering is explicit: it is never enabled, nor dropped, by accident."""
    if args.host_index:
        if args.skip_host_filter:
            raise ValueError("--host-index enables host filtering; do not combine it with --skip-host-filter.")
        if not args.host_name:
            raise ValueError("--host-index requires --host-name to record which host was filtered.")
        _bowtie2_index(args.host_index)
    elif args.host_name or args.host_accession:
        raise ValueError("--host-name/--host-accession describe a filter that only runs with --host-index.")


def prepare(args, root: Path) -> tuple[Path, list[str], dict[str, str], str]:
    """Validate the invocation before reserving or writing anything."""
    if os.name != "posix":
        raise ValueError("genein run requires Linux/WSL and the Gene-In bioinformatics environment.")
    if bool(args.r1) != bool(args.r2):
        raise ValueError("--r1 and --r2 must be supplied together.")
    if args.batch_manifest:
        if any((args.r1, args.r2, args.single, args.contigs, args.library_mode, args.umi_mode, args.role, args.expected_target)):
            raise ValueError("Batch inputs and sample metadata must come from the batch manifest.")
        if args.skip_qc:
            raise ValueError("The existing batch workflow requires measured post-QC denominators; --skip-qc is only supported for single samples.")
    elif not any((args.r1, args.single, args.contigs)):
        raise ValueError("A sample requires --r1/--r2, --single or --contigs.")
    if args.role == "positive" and not (args.expected_target or "").strip():
        raise ValueError("Controle positivo exige um alvo esperado. Informe --expected-target antes de iniciar a execução.")
    if args.analysis_profile == "assembly-consensus" and args.assembler:
        raise ValueError("--assembler cannot be combined with --analysis-profile assembly-consensus.")
    _host_arguments(args)
    output = Path(args.output_root).expanduser().resolve()
    if output.is_relative_to(root):
        raise ValueError("--output-root must be outside the Gene-In source tree.")
    if output.exists():
        raise ValueError(f"Output directory already exists; choose a new execution directory: {output}")
    run_id = _identifier(root, "run-id", args.run_id or str(uuid.uuid4()))
    db = str(Path(args.blast_db).expanduser().resolve())
    try:
        _file(db + ".db-manifest.json")
    except ValueError as exc:
        raise ValueError(
            f"Banco BLAST sem manifesto preparado neste prefixo: {db}. "
            "Prepare o banco com bash bundle/run.sh db DB=<banco> ou pela "
            "Área avançada → Configuração técnica → Preparar banco viral; "
            "informe o prefixo gerado em --blast-db."
        ) from exc
    if args.composite_db:
        composite = str(Path(args.composite_db).expanduser().resolve())
        try:
            _file(composite + ".db-manifest.json")
        except ValueError as exc:
            raise ValueError("Banco composto sem manifesto .db-manifest.json. Prepare o banco e informe o prefixo validado em --composite-db.") from exc
    env = dict(os.environ)
    # Prevent inherited read inputs from selecting a second input mode. The
    # explicit shell input flags below still take precedence over config files.
    for name in ("SAMPLE_R1", "SAMPLE_R2", "SAMPLE_SINGLE", "CONTIGS", "EVIDENCE_RESERVATION_TOKEN"):
        env.pop(name, None)
    env.update({"GENEIN_WORK_ROOT": str(output), "BLAST_DB": db,
                "EVIDENCE_RUN_ID": run_id, "PYTHONDONTWRITEBYTECODE": "1"})
    # Shell adapters call python3; use the interpreter running this CLI.
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env["GENEIN_ENV_DIR"] = str(Path(sys.executable).parent.parent)
    evidence_root = str(output / "results/evidence")
    options = []
    for name in ("assembler", "analysis_profile", "kmer", "spades_params", "advanced_kmers",
                 "blast_task", "blast_word_size", "blast_evalue", "search_profiles"):
        value = getattr(args, name)
        if value is not None:
            options += ["--" + name.replace("_", "-"), str(value)]
    for name in ("skip_qc", "skip_host_filter", "rescue_mode"):
        if getattr(args, name):
            options.append("--" + name.replace("_", "-"))
    for name, variable in {
        "library_mode": "EVIDENCE_LIBRARY_MODE", "umi_mode": "EVIDENCE_UMI_MODE",
        "role": "EVIDENCE_ROLE", "expected_target": "EVIDENCE_EXPECTED_TARGET",
        "host_name": "HOST_NAME", "host_accession": "HOST_ACCESSION",
    }.items():
        if getattr(args, name) is not None:
            env[variable] = getattr(args, name)
    for name, variable in {
        "composite_db": "EVIDENCE_COMPOSITE_DB", "subject_labels": "EVIDENCE_SUBJECT_LABELS",
        "panel_fasta": "EVIDENCE_PANEL_FASTA", "panel_index": "EVIDENCE_PANEL_INDEX",
        "host_index": "HOST_INDEX_PREFIX",
    }.items():
        if getattr(args, name) is not None:
            env[variable] = str(Path(getattr(args, name)).expanduser().resolve())
    if args.host_index:
        env["HOST_FILTER_ENABLED"] = "true"
    if args.host_expected is not None:
        env["HOST_EXPECTED"] = args.host_expected
    profiles = _file(args.evidence_profiles) if args.evidence_profiles else str(root / "config/evidence_profiles.json")
    if args.batch_manifest:
        command = [sys.executable, str(root / "scripts/pipeline/run_batch.py"),
                   "--batch-manifest", _file(args.batch_manifest), "--run-id", run_id,
                   "--evidence-root", evidence_root, "--profiles", profiles,
                   "--threads", str(args.threads)]
        command += ["--sample-arg=" + token for token in options]
    else:
        sample = _identifier(root, "sample", args.sample)
        command = ["bash", str(root / "scripts/pipeline/run_sample.sh"), "--sample", sample,
                   "--threads", str(args.threads), "--evidence-root", evidence_root,
                   "--evidence-profiles", profiles, *options]
        for name in ("r1", "r2", "single", "contigs"):
            if getattr(args, name):
                command += ["--" + name, _file(getattr(args, name))]
        if args.evidence_v2:
            command.append("--evidence-v2")
    return output, command, env, run_id


def run(args) -> int:
    try:
        root = source_root()
        output, command, env, run_id = prepare(args, root)
        output.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError) as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 2
    # GENEIN_REPO_ROOT can point at a stub used by tests. The version and the
    # commit belong to the tree that contains this software, which carries
    # RELEASE.json in a normal checkout or package.
    identity_root = root if (root / "RELEASE.json").is_file() else Path(__file__).resolve().parents[3]
    receipt = {"schema_version": "1.0", "kind": "genein_launcher_receipt",
               "software_version": software_version(identity_root),
               "source_commit": source_commit(identity_root),
               "run_id": run_id, "source_root": str(root), "output_root": str(output),
               "command": command, "started_at": datetime.now(timezone.utc).isoformat(),
               "status": "running", "scientific_validation": "not_assessed"}
    receipt_path = output / "execution.json"
    _receipt(receipt_path, receipt)
    runner = ProcessRunner(env)
    code = 0
    with runner.signals():
        try:
            runner.run(command)
        except BatchCancelled:
            code = 130
        except subprocess.CalledProcessError as exc:
            code = exc.returncode if exc.returncode > 0 else 128 - exc.returncode
        except OSError as exc:
            print(f"[FATAL] {exc}", file=sys.stderr)
            code = 1
    receipt.update(status="completed" if code == 0 else "cancelled" if code == 130 else "failed",
                   exit_code=code, finished_at=datetime.now(timezone.utc).isoformat())
    if code:
        failure_type, failed_stage, failure_message = classify_launcher_failure(
            code, _pipeline_log_excerpt(output),
        )
        receipt["failure_type"] = failure_type
        if failed_stage:
            receipt["failed_stage"] = failed_stage
        if failure_message:
            receipt["failure_message"] = failure_message
    _receipt(receipt_path, receipt)
    print(f"[RUN_ID] {run_id}")
    print(f"[OUTPUT_ROOT] {output}")
    return code
