#!/usr/bin/env python3
"""Bounded operational A/B vs frozen collector B0, using real BLAST/Bowtie2.

No biological validation: synthetic favorable panel and real-output collection only.
Run in the scientific environment; never downloads inputs or modifies Builder.
"""
from __future__ import annotations
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
BASE = "18c686310e52ca87ee3a5ca46d9ff73952914263"
COLLECTOR = ROOT / "scripts/pipeline/collect_candidate_queries.py"


def command(args, log):
    with log.open("a") as output:
        subprocess.run(list(map(str, args)), cwd=ROOT, check=True, stdout=output, stderr=subprocess.STDOUT)


def load_collectors():
    baseline = types.ModuleType("collector_B0")
    baseline.__file__ = str(COLLECTOR)
    text = subprocess.check_output(["git", "show", f"{BASE}:scripts/pipeline/collect_candidate_queries.py"], cwd=ROOT, text=True)
    exec(compile(text, str(COLLECTOR), "exec"), baseline.__dict__)
    spec = importlib.util.spec_from_file_location("collector_after", COLLECTOR)
    after = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(after)
    return baseline, after


def write_fastq(path, records):
    path.write_text("".join(f"@{name}\n{seq}\n+\n{'I' * len(seq)}\n" for name, seq in records))


def bundle(directory, sequences, manifest):
    directory.mkdir()
    (directory / "queries.fa").write_text("".join(f">{name}\n{seq}\n" for name, seq in sequences.items()))
    (directory / "queries.json").write_text(json.dumps(manifest))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--builder-manifest", type=Path)
    args = parser.parse_args()
    for tool in ("blastn", "blastdbcmd", "makeblastdb", "bowtie2", "bowtie2-build", "samtools"):
        if not shutil.which(tool):
            raise SystemExit(f"Missing required real tool: {tool}")
    work = args.artifact_root.resolve()
    work.mkdir(parents=True, exist_ok=False)
    log = work / "commands.log"
    rng = random.Random(20261111)
    genome = "".join(rng.choice("ACGT") for _ in range(1770))
    host = "".join(rng.choice("ACGT") for _ in range(1770))
    panel = work / "panel.fa"
    # An exact second target ensures that the A/B exercises ambiguity/ties.
    panel.write_text(f">virus_a\n{genome}\n>virus_b\n{genome}\n>host\n{host}\n")
    labels = work / "labels.tsv"
    labels.write_text("sseqid\tcategory\ttaxon\tsegment\nvirus_a\tTARGET_VIRUS\tsynthetic_a\tunsegmented\nvirus_b\tTARGET_VIRUS\tsynthetic_b\tunsegmented\nhost\tHOST\tsynthetic_host\tunsegmented\n")
    command(["makeblastdb", "-in", panel, "-dbtype", "nucl", "-parse_seqids", "-out", work / "panel"], log)
    command([sys.executable, ROOT / "scripts/tests/write_blast_fixture_manifest.py", work / "panel"], log)
    command(["bowtie2-build", "--threads", "1", panel, work / "panel_map"], log)
    contigs = work / "empty.fa"
    contigs.touch()
    paths = [work / "R1.fq", work / "R2.fq"]
    for mate, path in enumerate(paths, 1):
        records = [(f"pair{i}/{mate}", genome[100 + i * 160 + mate * 10:100 + i * 160 + mate * 10 + n])
                   for i, n in enumerate((20, 34, 54, 74, 100))]
        write_fastq(path, records)
    baseline, after = load_collectors()
    before_queries, before_manifest = baseline.collect(contigs, fastqs=paths)
    after_queries, after_manifest = after.collect(contigs, fastqs=paths)
    assert before_queries == after_queries, "20–100 bp FASTA changed"
    assert {q: x["source_counts"] for q, x in before_manifest["queries"].items()} == {
        q: x["source_counts"] for q, x in after_manifest["queries"].items()}
    results = {}
    for label, sequences, manifest in (("before", before_queries, before_manifest), ("after", after_queries, after_manifest)):
        directory = work / label
        bundle(directory, sequences, manifest)
        command(["bash", ROOT / "scripts/evidence/run.sh", "--sample", "sizeAB", "--queries", directory / "queries.fa",
                 "--query-manifest", directory / "queries.json", "--profiles", ROOT / "config/evidence_profiles.json",
                 "--evidence-root", directory / "evidence", "--run-id", "coletor-size-ab-0001",
                 "--composite-db", work / "panel", "--subject-labels", labels, "--threads", "1",
                 "--panel-fasta", panel, "--panel-index", work / "panel_map", "--r1", paths[0], "--r2", paths[1],
                 "--library-mode", "shotgun", "--umi-mode", "none"], log)
        results[label] = directory / "evidence/runs/coletor-size-ab-0001"
    equal_files = ["blastn-short.tsv", "blastn.tsv", "fragment_evidence.tsv", "locus_evidence.tsv",
                   "competitive_hits.tsv", "read_support.tsv", "coverage.tsv", "hsp_evidence.tsv", "template_lineage.tsv"]
    for name in equal_files:
        assert (results["before"] / name).read_bytes() == (results["after"] / name).read_bytes(), f"A/B changed {name}"
    old, new = [json.loads((results[x] / "sample_evidence.json").read_text()) for x in ("before", "after")]
    for field in ("candidates", "evidence_level", "analysis_outcome", "specificity", "coverage"):
        assert old[field] == new[field], f"A/B changed {field}"
    with (results["after"] / "competitive_hits.tsv").open() as handle:
        tied_rows = sum(len(json.loads(row["target_evidence_json"])) > 1
                        for row in csv.DictReader(handle, delimiter="\t"))
    assert tied_rows > 0, "A/B fixture did not exercise competing target taxa"
    summary = {"tied_rows_before": tied_rows, "tied_rows_after": tied_rows, "base_sha": BASE, "short_queries_before": len(before_queries), "short_queries_after": len(after_queries),
               "identical_files": equal_files, "candidate_count_before": len(old["candidates"]),
               "candidate_count_after": len(new["candidates"]), "level_before": old["evidence_level"], "level_after": new["evidence_level"],
               "short_scientific_differences": 0}
    # Long reads, assembled contig and complete synthetic genome remain whole.
    long_contigs = work / "long_contigs.fa"
    long_contigs.write_text(f">contig350\n{genome[400:750]}\n>complete_synthetic_genome1770\n{genome}\n")
    long_paths = [work / "longR1.fq", work / "longR2.fq"]
    reverse = genome[100:250].translate(str.maketrans("ACGT", "TGCA"))[::-1]
    write_fastq(long_paths[0], [("long_pair/1", genome[50:200])] * 2)
    write_fastq(long_paths[1], [("long_pair/2", reverse)] * 2)
    bq, _ = baseline.collect(long_contigs, fastqs=long_paths)
    nq, nm = after.collect(long_contigs, fastqs=long_paths)
    directory = work / "long"
    bundle(directory, nq, nm)
    command([sys.executable, ROOT / "scripts/evidence/blast_router.py", "--query", directory / "queries.fa",
             "--db", work / "panel", "--profiles", ROOT / "config/evidence_profiles.json", "--recover-short-fragments",
             "--threads", "1", "--out-short", directory / "short.tsv", "--out-conventional", directory / "long.tsv",
             "--provenance", directory / "routing.json"], log)
    routing = json.loads((directory / "routing.json").read_text())
    assert all(row["profiles"] == ["conventional"] for row in routing["assignments"])
    assert sorted(row["length"] for row in routing["assignments"]) == [150, 150, 350, 1770]
    assert routing["profiles"]["conventional"]["word_size"] == 11
    assert not (directory / "short.tsv").read_text()
    hit_ids = {line.split("\t")[0] for line in (directory / "long.tsv").read_text().splitlines()}
    assert hit_ids == set(nq), "Long sequences not all searched"
    # A unique mapping panel measures template deduplication (the short A/B
    # panel intentionally has identical references and ambiguous mapping).
    unique_panel = work / "unique.fa"
    unique_panel.write_text(f">virus_a\n{genome}\n>host\n{host}\n")
    command(["makeblastdb", "-in", unique_panel, "-dbtype", "nucl", "-parse_seqids", "-out", work / "unique"], log)
    command([sys.executable, ROOT / "scripts/tests/write_blast_fixture_manifest.py", work / "unique"], log)
    command(["bowtie2-build", "--threads", "1", unique_panel, work / "unique_map"], log)
    command(["bash", ROOT / "scripts/evidence/run.sh", "--sample", "longSize", "--queries", directory / "queries.fa",
             "--query-manifest", directory / "queries.json", "--profiles", ROOT / "config/evidence_profiles.json",
             "--evidence-root", directory / "evidence", "--run-id", "coletor-long-pair-0001",
             "--composite-db", work / "unique", "--subject-labels", labels, "--threads", "1",
             "--panel-fasta", unique_panel, "--panel-index", work / "unique_map",
             "--r1", long_paths[0], "--r2", long_paths[1], "--library-mode", "shotgun", "--umi-mode", "none"], log)
    final = directory / "evidence/runs/coletor-long-pair-0001"
    with (final / "read_support.tsv").open() as handle:
        support = list(csv.DictReader(handle, delimiter="\t"))
    assert support, "No long-read support measured"
    max_templates = max(int(row["unique_templates"]) for row in support)
    max_starts = max(int(row["distinct_starts"]) for row in support)
    assert max_templates == 1, f"Duplicate long pair inflated templates: {max_templates}"
    # A paired template legitimately has two read starts in the existing
    # contract. Compare with the very same pair without duplicate occurrences.
    single_paths = [work / "singleR1.fq", work / "singleR2.fq"]
    write_fastq(single_paths[0], [("long_pair/1", genome[50:200])])
    write_fastq(single_paths[1], [("long_pair/2", reverse)])
    sq, sm = after.collect(long_contigs, fastqs=single_paths)
    single_dir = work / "long_single_pair"
    bundle(single_dir, sq, sm)
    command(["bash", ROOT / "scripts/evidence/run.sh", "--sample", "longSize", "--queries", single_dir / "queries.fa",
             "--query-manifest", single_dir / "queries.json", "--profiles", ROOT / "config/evidence_profiles.json",
             "--evidence-root", single_dir / "evidence", "--run-id", "coletor-long-pair-0001",
             "--composite-db", work / "unique", "--subject-labels", labels, "--threads", "1",
             "--panel-fasta", unique_panel, "--panel-index", work / "unique_map",
             "--r1", single_paths[0], "--r2", single_paths[1], "--library-mode", "shotgun", "--umi-mode", "none"], log)
    single_support = single_dir / "evidence/runs/coletor-long-pair-0001/read_support.tsv"
    with single_support.open() as handle:
        single_rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(single_rows) == len(support)
    for duplicate, original in zip(support, single_rows):
        for key in ("query_ids", "locus_id", "unique_templates", "distinct_starts", "support_status"):
            assert duplicate[key] == original[key], f"Duplicate long pair changed {key}"
        # Bowtie2 can flag repeated input names as discordant; this may reduce
        # proper-pair support, never create independent templates or starts.
        assert int(duplicate["proper_pair_templates"]) <= int(original["proper_pair_templates"])
    report = (final / "evidence_report.md").read_text()
    assert report.startswith("# Gene-In") and "Rota longa" in report
    summary.update(long_queries_before=len(bq), long_queries_after=len(nq), long_lengths=[150,150,350,1770],
                   long_read_occurrences=4, long_max_templates=max_templates, long_max_starts=max_starts)
    if args.builder_manifest:
        kwargs = after.builder_inputs(args.builder_manifest)
        real_before, _ = baseline.collect(kwargs["contigs"], kwargs["short_fasta"], kwargs["fastqs"])
        real_after, real_manifest = after.collect(**kwargs)
        real_dir = work / "builder_real"
        bundle(real_dir, real_after, real_manifest)
        long_occurrences = sum(entry["source_counts"].get("long_read", 0) for entry in real_manifest["queries"].values())
        assert long_occurrences == 3078, f"Unexpected SRR17241648 read count: {long_occurrences}"
        summary.update(real_queries_before=len(real_before), real_queries_after=len(real_after),
                       real_unassembled_reads_before=0, real_unassembled_reads_after=long_occurrences,
                       real_balance=real_manifest["routing_summary"])
    (work / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
