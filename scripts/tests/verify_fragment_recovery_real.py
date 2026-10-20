#!/usr/bin/env python3
"""Functional synthetic verification with real QC, assembly and BLAST tools.

This fixture is not a biological benchmark or a measurement of sensitivity.
Artifacts are retained, including failures, for inspection.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/lib"))
from input_validation import iter_fastq


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reverse_complement(sequence):
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    for tool in ("fastp", "spades.py", "metaspades.py", "velvetg", "blastn", "makeblastdb"):
        if not shutil.which(tool):
            raise SystemExit(f"Missing real tool: {tool}")
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="genein-fragments-", dir=args.artifact_root))
    print(f"ARTIFACTS={work}", flush=True)
    rng = random.Random(20261002)
    target = "".join(rng.choice("ACGT") for _ in range(2400))
    host = "".join(rng.choice("ACGT") for _ in range(2400))
    reference = work / "panel.fa"
    reference.write_text(f">synthetic_target\n{target}\n>synthetic_host\n{host}\n")
    labels = work / "labels.tsv"
    labels.write_text("sseqid\tcategory\ttaxon\tsegment\nsynthetic_target\tTARGET_VIRUS\tfunctional_target\tunsegmented\nsynthetic_host\tHOST\tfunctional_host\tunsegmented\n")
    prefix = work / "panel"
    subprocess.run(["makeblastdb", "-in", str(reference), "-dbtype", "nucl", "-parse_seqids", "-out", str(prefix)],
                   check=True, stdout=subprocess.DEVNULL)
    produced = {path.name: {"size": path.stat().st_size, "sha256": digest(path)}
                for path in work.glob("panel.*") if path != reference}
    Path(str(prefix) + ".db-manifest.json").write_text(json.dumps({
        "schema_version": "1.0", "logical_prefix": str(prefix), "generation_id": "functional-fragments-v1",
        "created_at": "2026-10-02T00:00:00+00:00", "source_fasta": {
            "path": str(reference), "size": reference.stat().st_size, "sha256": digest(reference)},
        "produced_files": produced}, indent=2))
    summary = {"kind": "functional_synthetic_not_biological_validation", "seed": 20261002, "cases": []}
    cases = [("twenty", [20], False, target),
             ("mixed", [20, 34, 54, 74, 100], False, target),
             ("adapter_twenty", [20], True, target),
             ("host_twenty", [20], False, host)]
    for sample, lengths, adapters, genome in cases:
        paths = [work / f"{sample}_R{mate}.fq.gz" for mate in (1, 2)]
        molecule_truth = {}
        with gzip.open(paths[0], "wt") as first, gzip.open(paths[1], "wt") as second:
            for index in range(150):
                length = lengths[index % len(lengths)]
                start = (index * 13) % (len(genome) - length)
                fragment = genome[start:start + length]
                molecule_truth[f"{sample}_{index}/1"] = fragment
                molecule_truth[f"{sample}_{index}/2"] = reverse_complement(fragment)
                for mate, handle, sequence, adapter in (
                    (1, first, fragment, "AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC"),
                    (2, second, reverse_complement(fragment), "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT")):
                    if adapters:
                        sequence = (sequence + adapter + "GCTACGTA" * 20)[:125]
                    handle.write(f"@{sample}_{index}/{mate}\n{sequence}\n+\n{'I' * len(sequence)}\n")
        (work / f"{sample}_molecule_truth.json").write_text(json.dumps(molecule_truth, indent=2))
        output = work / sample
        output.mkdir()
        evidence = output / "results/evidence"
        environment = {**os.environ, "GENEIN_WORK_ROOT": str(output), "BLAST_DB": str(prefix),
                       "EVIDENCE_COMPOSITE_DB": str(prefix), "EVIDENCE_SUBJECT_LABELS": str(labels),
                       "HOST_FILTER_ENABLED": "false", "EVIDENCE_ROOT": str(evidence),
                       "EVIDENCE_RUN_ID": f"fragments-{sample}-0001", "QC_MIN_LEN": "20",
                       "SAMPLE_R1": str(paths[0]), "SAMPLE_R2": str(paths[1]), "SHORT_FRAGMENT_MODE": "true"}
        command = ["bash", str(ROOT / "scripts/pipeline/run.sh"), "--sample", sample,
                   "--analysis-profile", "assembly-consensus", "--threads", "2", "--evidence-v2"]
        if adapters:
            environment.update(QC_ADAPTER_R1="AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC",
                               QC_ADAPTER_R2="AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT")
        if sample == "mixed":
            command.extend(["--spades-params", "--only-assembler -m 4 --phred-offset 33"])
        log = work / f"{sample}.log"
        with log.open("w") as handle:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=handle, stderr=subprocess.STDOUT)
        if result.returncode:
            details = [line for line in log.read_text(errors="replace").splitlines()
                       if any(marker in line for marker in ("[FALTA]", "[ERRO]", "[FATAL]"))]
            raise SystemExit(f"Pipeline falhou ({result.returncode}). Log: {log}\n" + "\n".join(details[-8:]))
        cleaned = output / "data/cleaned" / f"{sample}_R1.clean.fastq.gz"
        clean_records = list(iter_fastq(cleaned))
        observed = {len(sequence) for _, sequence in clean_records}
        if any(sequence != molecule_truth[name] for name, sequence in clean_records):
            raise SystemExit(f"QC changed the known molecule sequence: {sample}")
        if not set(lengths).issubset(observed):
            raise SystemExit(f"QC failed to preserve expected molecule lengths {lengths}; observed={sorted(observed)}; log={log}")
        run = evidence / "runs" / f"fragments-{sample}-0001"
        if not (run / "SUCCESS.json").is_file():
            raise SystemExit(f"Missing transactional completion: {run}")
        manifest = json.loads((run / "candidate_queries.json").read_text())
        short_lengths = {entry["length_bp"] for entry in manifest["queries"].values()
                         if "short_read" in entry["source_counts"]}
        if not set(lengths).issubset(short_lengths):
            raise SystemExit(f"Candidate queries lost short reads: {run}")
        exported = (run / "candidate_sequences.fa").read_text()
        if not exported:
            raise SystemExit(f"No aligned sequences were exported: {run}")
        sample_evidence = json.loads((run / "sample_evidence.json").read_text())
        if sample_evidence.get("scientific_revision") != "scientific_review_20261005_v1":
            raise SystemExit("Scientific revision is missing")
        if sample_evidence["metrics"]["promotion_eligible_candidate_count"] or sample_evidence["metrics"]["qualifying_loci"]:
            raise SystemExit("Availability was incorrectly reported as scientific qualification")
        if sample_evidence["evidence_label"] != "Candidatos recuperados":
            raise SystemExit("Misleading public recovery label")
        if any(row["aligned_reference_bp"] > (row["reference_length"] or float("inf"))
               for row in sample_evidence["reference_coverage"]["by_reference"]):
            raise SystemExit("Nonredundant bases exceed reference length")
        routing = json.loads((run / "blast_routing.json").read_text())
        if routing["routing_policy"] != "fragment_recovery_20_100_v1":
            raise SystemExit("New short routing policy was not recorded")
        if sample == "host_twenty":
            with (run / "competitive_hits.tsv").open() as handle:
                competitive = list(csv.DictReader(handle, delimiter="\t"))
            if any(row["specificity_status"] == "TARGET_SPECIFIC" for row in competitive):
                raise SystemExit("Host-derived fixture was incorrectly marked target-specific")
            if sample_evidence["specificity"]["status"] != "NON_TARGET_BEST":
                raise SystemExit("Host-origin control is not explicitly non-target-best")
            if not any("não alvo" in text for text in sample_evidence["caveats"]):
                raise SystemExit("Host-origin warning is missing")
        exported_records = {}
        current_id = None
        for line in exported.splitlines():
            if line.startswith(">"):
                current_id = line[1:].split()[0]
                exported_records[current_id] = ""
            else:
                exported_records[current_id] += line.strip()
        exported_sequences = set(exported_records.values())
        truth_sequences = set(molecule_truth.values())
        recovered_truth = truth_sequences & exported_sequences
        summary["cases"].append({"sample": sample, "molecule_lengths_bp": lengths,
            "adapter_readthrough": adapters, "qc_lengths_bp": sorted(observed), "run_dir": str(run),
            "qc_sequences_match_molecule_truth": True,
            "truth_sequence_count_unit": "DISTINCT_READ_SEQUENCES_BOTH_ORIENTATIONS_NOT_TEMPLATES",
            "distinct_input_read_sequences": len(truth_sequences),
            "distinct_truth_sequences_exported": len(recovered_truth),
            "distinct_exported_sequences_not_exact_input": len(exported_sequences - truth_sequences),
            "aligned_reference_bp": sample_evidence["metrics"]["total_nonredundant_reference_bp"],
            "qualification_status": sample_evidence["metrics"]["qualification_status"],
            "specificity_status": sample_evidence["specificity"]["status"],
            "candidate_fasta_sha256": digest(run / "candidate_sequences.fa"), "pipeline_exit": result.returncode})
        (work / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(f"PASS {sample}: QC lengths {sorted(observed)}", flush=True)
    print(f"PASS functional fragment recovery; evidence={work / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
