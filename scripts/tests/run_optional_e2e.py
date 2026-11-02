#!/usr/bin/env python3
"""Mechanical FASTQ-to-receipt test, using random strings without organism sources.

Exit 77 means SKIPPED, never PASSED. All executions and failures keep their logs.
No scientific setting or performance criterion is changed by this test.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ("bash", "flock", "make", "gcc", "git", "dos2unix", "fastp", "velveth", "velvetg", "blastn",
         "makeblastdb", "blastdbcmd", "blastdb_aliastool", "bowtie2",
         "bowtie2-build", "bowtie2-inspect", "samtools")
SEED = 20261102
LENGTHS = (20, 25, 30, 40, 50, 65, 80, 100)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fixtures(work: Path) -> dict:
    """Generate a deterministic software fixture, independent of biological data."""
    rng = random.Random(SEED)
    strings = ["".join(rng.choices("ACGT", k=640)) for _ in range(2)]
    primary, panel = work / "primary reference.fa", work / "optional panel.fa"
    primary.write_text(f">fixture_alpha\n{strings[0]}\n", encoding="ascii")
    panel.write_text(primary.read_text() + f">fixture_beta\n{strings[1]}\n", encoding="ascii")
    labels = work / "subject labels.tsv"
    # These are existing file-format enum values, not organism identities.
    labels.write_text("sseqid\tcategory\ttaxon\tsegment\n"
                      "fixture_alpha\tTARGET_VIRUS\tfixture_alpha\tunsegmented\n"
                      "fixture_beta\tSYNTHETIC_SEQUENCE\tfixture_beta\tunsegmented\n", encoding="ascii")
    r1, r2 = work / "input R1.fastq", work / "input R2.fastq"
    counts = Counter()
    complement = str.maketrans("ACGT", "TGCA")
    with r1.open("w") as left, r2.open("w") as right:
        for length in LENGTHS:
            for position in range(0, 391, 5):
                first = strings[0][position:position + length]
                second = strings[0][position + 200 - length:position + 200].translate(complement)[::-1]
                name = f"fixture_{length}_{position}"
                left.write(f"@{name}/1\n{first}\n+\n{'I' * length}\n")
                right.write(f"@{name}/2\n{second}\n+\n{'I' * length}\n")
                counts[length] += 1
    return {"primary": primary, "panel": panel, "labels": labels, "r1": r1, "r2": r2,
            "pairs_by_length": dict(counts)}


def check_run(work: Path, run_id: str, competition: bool, remapping: bool, expected_tools: dict) -> dict:
    """A zero exit alone is insufficient: validate current-run commit and stages."""
    sys.path.insert(0, str(ROOT / "scripts/evidence"))
    from common import validate_artifact_manifest

    final = work / "evidence/runs" / run_id
    receipt = read_json(final / "SUCCESS.json")
    evidence = read_json(final / "sample_evidence.json")
    provenance = read_json(final / "provenance.json")
    state = read_json(final / "run_state.json")
    manifest_path = final / "artifact_manifest.json"
    require(receipt.get("run_id") == run_id == evidence.get("run_id") == state.get("run_id"),
            "receipt, outputs and state must belong to this execution")
    require(receipt.get("status") in {"done", "done_with_warning"}, "run is not complete")
    require(receipt.get("artifact_manifest_sha256") == sha256(manifest_path), "manifest hash mismatch")
    require(receipt.get("sample_evidence_sha256") == sha256(final / "sample_evidence.json"),
            "sample receipt hash mismatch")
    errors = validate_artifact_manifest(final, read_json(manifest_path))
    require(not errors, f"invalid committed artifacts: {errors}")
    require(not (work / "evidence/.staging" / run_id).exists(), "run was not promoted")
    resolved_files = list((work / "tmp").rglob("*.resolved_config.json"))
    require(len(resolved_files) == 1, "missing or ambiguous resolved configuration")
    resolved = read_json(resolved_files[0])
    require(resolved["input_mode"] == "READS", "test bypassed the FASTQ flow")
    profile_path = work / "results/blast" / f"{run_id}_search_profile.json"
    profile = read_json(profile_path)
    require(profile["profiles"]["A"]["active"] is True, "profile A did not run")
    require(profile["profiles"]["B"]["active"] == competition, "profile B state mismatch")
    require(bool(resolved["evidence"]["composite_db"]) == competition, "competition option mismatch")
    require(bool(resolved["evidence"]["panel_index"]) == remapping, "remapping option mismatch")
    require(provenance["parameters"]["run_id"] == run_id, "stale provenance")
    for name in ("python3", "fastp", "blastn", "bowtie2", "samtools"):
        require(provenance["tools"][name]["executable"] == expected_tools[name]["executable"],
                f"{name}: pipeline used a different environment")
        require(provenance["tools"][name]["sha256"] == expected_tools[name]["sha256"],
                f"{name}: executable hash changed")
    stages = {stage["id"]: stage["status"] for stage in state["stages"]}
    require(stages["initial_blast"] == "done", "BLAST stage incomplete")
    if competition:
        require((final / "blast_routing.json").is_file(), "composite search did not run")
        require((final / "blastn.tsv").stat().st_size > 0, "composite BLAST produced no test records")
    if remapping:
        require(stages["read_remapping"] == "done", "remapping was not executed")
        require((final / "bowtie2.log").stat().st_size > 0, "missing real Bowtie2 log")
        require((final / "mapping_reference_check.json").is_file(), "missing mapping identity check")
        bam = final / "read_support.bam"
        require(bam.is_file() and Path(str(bam) + ".bai").is_file(), "missing committed BAM/index")
        count = subprocess.check_output(["samtools", "view", "-c", "-F", "4", str(bam)], text=True)
        require(int(count) > 0, "remapping silently processed no mapped test records")
    else:
        require(stages["read_remapping"] == "warning", "disabled remapping reported as executed")
        require(not (final / "read_support.bam").exists(), "disabled remapping produced a BAM")
    directed = work / "results/blast" / f"{run_id}_vs_db.tsv"
    require(directed.is_file() and directed.stat().st_size > 0, "directed BLAST did not process the fixture")
    return {"status": "PASSED", "run_id": run_id, "competition": competition, "remapping": remapping,
            "profiles": profile["selected"], "receipt": str(final / "SUCCESS.json"),
            "receipt_sha256": sha256(final / "SUCCESS.json"), "artifact_count": receipt["artifact_count"],
            "resolved_config": str(resolved_files[0]), "search_profile": str(profile_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path,
                        default=Path(os.environ.get("GENEIN_TEST_ARTIFACT_ROOT", tempfile.gettempdir())) / "genein-e2e")
    args = parser.parse_args(argv)
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="work with spaces ", dir=args.artifact_root.resolve()))
    manifest_path = work / "e2e-manifest.json"
    manifest = {"schema_version": "1.0", "status": "RUNNING", "scope": "artificial software fixture only",
                "scientific_validation": False, "started_at": datetime.now(timezone.utc).isoformat(),
                "platform": platform.platform(), "python": sys.version, "source": str(ROOT),
                "seed": SEED, "commands": [], "cases": [], "work": str(work)}
    write_json(manifest_path, manifest)
    print(f"[ARTIFACTS] {work}", flush=True)
    missing = [name for name in TOOLS if not shutil.which(name)]
    if os.name != "posix" or missing:
        manifest.update(status="SKIPPED", reason="POSIX and real tools required", missing_tools=missing,
                        finished_at=datetime.now(timezone.utc).isoformat())
        write_json(manifest_path, manifest)
        print(f"[SKIP] E2E não executado; ferramentas ausentes: {', '.join(missing) or 'host POSIX'}. Exit 77.", flush=True)
        return 77

    env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL") if key in os.environ}
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1",
               GENEIN_ENV_DIR=sys.prefix)
    # Prevent check_env.sh from probing a pre-existing bundle in the user's home.
    manifest["runtime_environment"] = {name: env[name] for name in
                                       ("PATH", "GENEIN_ENV_DIR", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE")}

    def run(label: str, command: list[str], overrides: dict | None = None, cwd: Path = ROOT,
            input_file: Path | None = None) -> None:
        log = work / f"{label}.log"
        record = {"label": label, "argv": command, "cwd": str(cwd), "environment": overrides or {}, "log": str(log)}
        if input_file is not None:
            record["stdin"] = {"path": str(input_file), "sha256": sha256(input_file)}
        manifest["commands"].append(record)
        write_json(manifest_path, manifest)
        with log.open("w") as stream:
            stream.write("$ " + shlex.join(command) + "\n")
            stream.flush()
            result = subprocess.run(command, cwd=cwd, env={**env, **(overrides or {})},
                                    input=input_file.read_bytes() if input_file is not None else None,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=600)
        record["returncode"] = result.returncode
        write_json(manifest_path, manifest)
        if result.returncode:
            print(log.read_text(encoding="utf-8", errors="replace")[-4000:], file=sys.stderr, flush=True)
        require(result.returncode == 0, f"{label}: exit {result.returncode}; see {log}")

    try:
        from importlib.metadata import version
        manifest["installed_genein"] = version("genein")
        manifest["source_commit"] = ((ROOT / "SOURCE_COMMIT").read_text().strip() if (ROOT / "SOURCE_COMMIT").is_file()
                                     else subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
        manifest["frozen_config_sha256"] = {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted((ROOT / "config").rglob("*")) if p.is_file()}
        sys.path.insert(0, str(ROOT / "scripts/evidence"))
        from write_provenance import tool_record
        manifest["tools"] = {name: tool_record(name) for name in ("python3", "fastp", "blastn", "makeblastdb", "bowtie2", "bowtie2-build", "samtools", "velveth", "velvetg")}
        fixture = fixtures(work)
        manifest["inputs"] = {name: {"path": str(path), "sha256": sha256(path)} for name, path in fixture.items() if isinstance(path, Path)}
        manifest["pairs_by_length"] = fixture["pairs_by_length"]
        empty_config = work / "empty configuration.env"
        empty_config.touch()
        banks = work / "banks with spaces"
        banks.mkdir()
        primary, composite, index = banks / "primary bank", banks / "competition bank", banks / "mapping index"
        from promote_blast_database import promote
        from verify_blast_database_manifest import verify
        for label, reference, destination in (("primary", fixture["primary"], primary), ("competition", fixture["panel"], composite)):
            # BLAST v5 embeds its physical basename. Keep it unchanged on promotion.
            with tempfile.TemporaryDirectory(prefix="genein-e2e-build-") as temporary:
                run(f"{label}-makeblastdb", ["makeblastdb", "-in", "-", "-title", "software fixture",
                                            "-dbtype", "nucl", "-parse_seqids",
                                            "-out", str(Path(temporary) / "database")], input_file=reference)
                staging = Path(tempfile.mkdtemp(prefix=".bank-staging-", dir=banks))
                for path in Path(temporary).iterdir():
                    shutil.copy2(path, staging / path.name)
            promote(staging, destination, reference, "blastdbcmd", "blastdb_aliastool",
                    Path(str(destination) + ".db-manifest.json"), build_name="database")
            require(verify(destination) > 0, "database manifest empty")
        run("mapping-build", ["bowtie2-build", "--threads", "1", str(fixture["panel"]), str(index)])
        from validate_mapping_reference import validate
        validate(str(index), str(fixture["panel"]), None)
        manifest["database_manifests"] = {str(p): read_json(Path(str(p) + ".db-manifest.json")) for p in (primary, composite)}
        manifest["mapping_index_sha256"] = {str(p): sha256(p) for p in sorted(banks.glob("mapping index.*.bt2*"))}
        require(len(manifest["mapping_index_sha256"]) == 6, "expected six index components")
        for competition, remapping in ((False, False), (False, True), (True, False), (True, True)):
            run_id = f"software-c{int(competition)}-r{int(remapping)}"
            case = work / f"case {run_id}"
            case.mkdir()
            overrides = {"GENEIN_WORK_ROOT": str(case), "GENEIN_CONFIG_FILE": str(empty_config),
                         "BLAST_DB": str(primary), "HOST_FILTER_ENABLED": "false", "EVIDENCE_V2": "true",
                         "EVIDENCE_ROOT": str(case / "evidence"), "EVIDENCE_RUN_ID": run_id,
                         "SAMPLE_R1": str(fixture["r1"]), "SAMPLE_R2": str(fixture["r2"]),
                         "EVIDENCE_COMPETITION_ENABLED": str(competition).lower(),
                         "EVIDENCE_REMAPPING_ENABLED": str(remapping).lower(),
                         "EVIDENCE_COMPOSITE_DB": str(composite), "EVIDENCE_SUBJECT_LABELS": str(fixture["labels"]),
                         "EVIDENCE_PANEL_FASTA": str(fixture["panel"]), "EVIDENCE_PANEL_INDEX": str(index),
                         "SEARCH_PROFILES": "A,B" if competition else "A"}
            run(run_id, ["bash", str(ROOT / "scripts/pipeline/run.sh"), "--sample", run_id,
                         "--analysis-profile", "default", "--assembler", "velvet", "--threads", "1", "--evidence-v2"], overrides)
            manifest["cases"].append(check_run(case, run_id, competition, remapping, manifest["tools"]))
            write_json(manifest_path, manifest)
            print(f"[PASS] {run_id}: código 0, saídas e recibo íntegros", flush=True)
        for item in manifest["inputs"].values():
            require(sha256(Path(item["path"])) == item["sha256"], "input fixture changed between cases")
        for path, digest in manifest["mapping_index_sha256"].items():
            require(sha256(Path(path)) == digest, "mapping index changed during execution")
        for bank in (primary, composite):
            verify(bank)
        current_config = {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted((ROOT / "config").rglob("*")) if p.is_file()}
        require(current_config == manifest["frozen_config_sha256"], "source configuration changed during execution")
        require(len(manifest["cases"]) == 4, "incomplete option matrix")
        manifest["status"] = "PASSED"
        print("[PASS] E2E de software: quatro execuções reais; sem avaliação de desempenho biológico.", flush=True)
        return 0
    except (Exception, KeyboardInterrupt) as error:
        manifest.update(status="FAILED", error=f"{type(error).__name__}: {error}")
        print(f"[FAIL] {manifest['error']}", file=sys.stderr, flush=True)
        return 1
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(manifest_path, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
