"""candidate_summary.tsv keeps one best hit and leaves the full table unchanged."""
import gzip
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))
from common import sha256_text
from export_candidate_sequences import export, titles_from_blast_db, titles_from_fasta
from validate_run_artifacts import validate_candidate_exports

_BLAST_TOOLS = ("makeblastdb", "blastdbcmd", "blastn")
_QUERY = (
    "CAGATTTTCATATTATGCAGAAAATCTACTTCGCCTGATACGAGTCGGTTATCTTCGGATACTGTATAGTCCCACCTGGTGATCCTATGCTTGTGAGTACCCAGAAAATAGCGACGGACCGCGGTGTTAAGTGTCGAGCTACATCACTTCTCATGTAGCCAGAAGGCTGCAACTCATCGACTCTATGTAGTGACCGCGTC"
)
_OTHER = (
    "GATGTCAAACCCCGGGGGGAGCTCAGATATCCGATACAGGGATGAAGAAATAACCTCATCCCATTGGTGACGAAAGGTTGTAAGTAGCTGGCCGCCGAGATAGCTGAGCGGCGAACCACTAGAAAAGGTTCAGACCCCGGAGCCCAGCCGTCACGATTGTTATGCGTATAAGCCCGGTTCACTACGTCCGTTCTGGCAAG"
)
_REFERENCE = (
    ">PTV1 Porcine teschovirus 1 strain X, complete genome\n"
    f"{_QUERY}\n"
    ">NC_009999.1 Other virus isolate Y, partial genome\n"
    f"{_OTHER}\n"
)


def test_summary_is_one_best_hit_and_full_table_keeps_every_row(tmp_path):
    queries = tmp_path / "queries.fa"
    queries.write_text(">q1\nAAAA\n>q2\nCCCC\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "1.0", "queries": {
        "q1": {"length_bp": 4, "sequence_sha256": sha256_text("AAAA"), "source_counts": {"read": 1}},
        "q2": {"length_bp": 4, "sequence_sha256": sha256_text("CCCC"), "source_counts": {"contig": 1}},
    }}), encoding="utf-8")
    fragments = tmp_path / "fragment_evidence.tsv"
    header = "\t".join([
        "qseqid", "sseqid", "category", "taxon", "task", "query_covered_bp", "query_coverage",
        "weighted_pident", "best_bitscore", "best_evalue", "assembly_method",
    ])
    # q1 has a weak hit first and a stronger hit later. q2 has a single hit.
    body = "\n".join([
        "q1\tweak\tREVIEW\ttaxon-w\tblastn\t4\t1\t70\t10\t1e-1\tvelvet",
        "q2\tonly\tREVIEW\ttaxon-2\tblastn\t4\t1\t90\t20\t1e-5\tspades",
        "q1\tstrong\tREVIEW\ttaxon-s\tblastn-short\t4\t1\t80\t40\t1e-8\tvelvet",
        "q1\ttie\tREVIEW\ttaxon-t\tblastn\t4\t1\t99\t40\t1e-3\tvelvet",
    ])
    fragments.write_text(header + "\n" + body + "\n", encoding="utf-8")
    out = tmp_path / "out"
    export(queries, manifest, fragments, out)
    full = (out / "candidate_sequences.tsv").read_text(encoding="utf-8").splitlines()
    assert full[0].split("\t")[:1] == ["qseqid"]
    assert [line.split("\t")[0] for line in full[1:]] == ["q1", "q2", "q1", "q1"]
    assert len(full) == 5
    summary = (out / "candidate_summary.tsv").read_text(encoding="utf-8").splitlines()
    assert summary[0].endswith("\treference_description\tmin_evalue\thit_row_count")
    rows = [line.split("\t") for line in summary[1:]]
    assert [row[0] for row in rows] == ["q1", "q2"]
    by_query = {row[0]: row for row in rows}
    # bitscore 40 beats 10; equal bitscore then lower e-value (1e-8) beats 1e-3.
    assert by_query["q1"][4] == "strong"
    assert by_query["q1"][-3] == ""
    assert by_query["q1"][-2] == "1e-8"
    assert by_query["q1"][-1] == "3"
    assert by_query["q2"][4] == "only"
    assert by_query["q2"][-2] == "1e-5"
    assert by_query["q2"][-1] == "1"
    (out / "fragment_evidence.tsv").write_bytes(fragments.read_bytes())
    assert validate_candidate_exports(out) == []


def test_summary_keeps_bitscore_winner_and_fills_taxon_from_the_title(tmp_path):
    queries = tmp_path / "queries.fa"
    queries.write_text(">q1\nAAAA\n>q2\nCCCC\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "1.0", "queries": {
        "q1": {"length_bp": 4, "sequence_sha256": sha256_text("AAAA"), "source_counts": {"read": 1}},
        "q2": {"length_bp": 4, "sequence_sha256": sha256_text("CCCC"), "source_counts": {"contig": 1}},
    }}), encoding="utf-8")
    fragments = tmp_path / "fragment_evidence.tsv"
    header = "\t".join([
        "qseqid", "sseqid", "category", "taxon", "task", "query_covered_bp", "query_coverage",
        "weighted_pident", "best_bitscore", "best_evalue", "assembly_method",
    ])
    # The bitscore winner is not the smallest e-value. q2 already has a label.
    body = "\n".join([
        "q1\thigh\tUNLABELED\t\tblastn\t4\t1\t80\t50\t1e-2\tspades",
        "q1\tdeep\tUNLABELED\t\tblastn\t4\t1\t70\t10\t1e-20\tspades",
        "q2\tlabeled\tREVIEW\tPorcine teschovirus 1\tblastn\t4\t1\t90\t20\t1e-5\tspades",
    ])
    fragments.write_text(header + "\n" + body + "\n", encoding="utf-8")
    reference = tmp_path / "reference.fa"
    reference.write_text(
        ">high Porcine teschovirus 1 strain X, complete genome\nATGC\n"
        ">deep Other virus isolate Y, partial genome\nATGC\n"
        ">labeled Something else, complete genome\nATGC\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    export(queries, manifest, fragments, out, reference_fasta=reference)
    summary = (out / "candidate_summary.tsv").read_text(encoding="utf-8").splitlines()
    by_query = {line.split("\t")[0]: line.split("\t") for line in summary[1:]}
    assert by_query["q1"][4] == "high"
    assert by_query["q1"][6] == "Porcine teschovirus 1"
    assert by_query["q1"][5] == "UNLABELED"
    assert by_query["q1"][-3] == "Porcine teschovirus 1 strain X, complete genome"
    assert by_query["q1"][-2] == "1e-20"
    assert by_query["q1"][12] == "1e-2"
    assert by_query["q2"][6] == "Porcine teschovirus 1"
    assert by_query["q2"][-3] == "Something else, complete genome"
    full = (out / "candidate_sequences.tsv").read_text(encoding="utf-8")
    assert "reference_description" not in full.splitlines()[0]
    assert full.splitlines()[1].split("\t")[6] == ""
    (out / "fragment_evidence.tsv").write_bytes(fragments.read_bytes())
    assert validate_candidate_exports(out) == []


def _makeblastdb(fasta: Path, prefix: Path, parse_seqids: bool) -> None:
    command = ["makeblastdb", "-in", str(fasta), "-dbtype", "nucl", "-out", str(prefix)]
    if parse_seqids:
        command.append("-parse_seqids")
    built = subprocess.run(command, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr


def _blastn_sseqid(query: Path, prefix: Path) -> str:
    hit = subprocess.run(
        ["blastn", "-query", str(query), "-db", str(prefix), "-outfmt", "6 sseqid", "-max_target_seqs", "1"],
        capture_output=True, text=True, check=False,
    )
    assert hit.returncode == 0, hit.stderr
    assert hit.stdout.strip(), hit.stderr
    return hit.stdout.splitlines()[0].split("\t")[0]


@pytest.mark.skipif(
    not all(shutil.which(name) for name in _BLAST_TOOLS),
    reason="BLAST+ ausente",
)
def test_summary_fills_taxon_from_a_real_blast_database(tmp_path):
    fasta = tmp_path / "reference.fa"
    fasta.write_text(_REFERENCE, encoding="utf-8")
    query = tmp_path / "query.fa"
    query.write_text(f">q1\n{_QUERY}\n", encoding="utf-8")
    sequence = _QUERY
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "1.0", "queries": {
        "q1": {"length_bp": len(sequence), "sequence_sha256": sha256_text(sequence), "source_counts": {"read": 1}},
    }}), encoding="utf-8")
    queries = tmp_path / "queries.fa"
    queries.write_text(f">q1\n{sequence}\n", encoding="utf-8")
    header = "\t".join([
        "qseqid", "sseqid", "category", "taxon", "task", "query_covered_bp", "query_coverage",
        "weighted_pident", "best_bitscore", "best_evalue", "assembly_method",
    ])
    for name, parse_seqids in (("unparsed", False), ("parsed", True)):
        prefix = tmp_path / name / "local"
        prefix.parent.mkdir()
        _makeblastdb(fasta, prefix, parse_seqids)
        sseqid = _blastn_sseqid(query, prefix)
        catalog = titles_from_blast_db(prefix)
        assert sseqid in catalog, (name, sseqid, sorted(catalog))
        fragments = tmp_path / f"{name}.tsv"
        fragments.write_text(
            header + f"\nq1\t{sseqid}\tUNLABELED\t\tblastn\t{len(sequence)}\t1\t100\t80\t1e-8\tspades\n",
            encoding="utf-8",
        )
        out = tmp_path / name / "out"
        export(queries, manifest, fragments, out, blast_db=prefix)
        row = (out / "candidate_summary.tsv").read_text(encoding="utf-8").splitlines()[1].split("\t")
        assert row[4] == sseqid
        assert row[5] == "UNLABELED"
        assert row[6] == "Porcine teschovirus 1", (name, row[6], row[-3])
        assert "Porcine teschovirus 1 strain X" in row[-3]
        full = (out / "candidate_sequences.tsv").read_text(encoding="utf-8").splitlines()[1].split("\t")
        assert full[6] == ""


def test_titles_from_fasta_survives_latin1_and_gzip(tmp_path, capsys):
    latin = tmp_path / "latin1.fa"
    latin.write_bytes(b">PTV1 v\xedrus, complete genome\nATGC\n")
    catalog = titles_from_fasta(latin)
    assert "PTV1" in catalog
    description, taxon = catalog["PTV1"]
    assert "complete genome" in description or "v" in description
    assert taxon

    compressed = tmp_path / "refs.fa.gz"
    compressed.write_bytes(gzip.compress(
        b">NC_1 Other virus isolate Y, partial genome\nAAAA\n"
    ))
    gzip_catalog = titles_from_fasta(compressed)
    assert "NC_1" in gzip_catalog
    assert "Other virus" in gzip_catalog["NC_1"][0]

    broken = tmp_path / "broken.fa.gz"
    broken.write_bytes(b"not a gzip stream")
    assert titles_from_fasta(broken) == {}
    warning = capsys.readouterr().err
    assert "[AVISO]" in warning
    assert "Descrições de referência ficam vazias" in warning

    queries = tmp_path / "queries.fa"
    queries.write_text(">q1\nAAAA\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "1.0", "queries": {
        "q1": {"length_bp": 4, "sequence_sha256": sha256_text("AAAA"), "source_counts": {"read": 1}},
    }}), encoding="utf-8")
    fragments = tmp_path / "fragment_evidence.tsv"
    header = "\t".join([
        "qseqid", "sseqid", "category", "taxon", "task", "query_covered_bp", "query_coverage",
        "weighted_pident", "best_bitscore", "best_evalue", "assembly_method",
    ])
    fragments.write_text(header + "\nq1\tPTV1\tUNLABELED\t\tblastn\t4\t1\t100\t80\t1e-8\tspades\n", encoding="utf-8")
    out = tmp_path / "out"
    export(queries, manifest, fragments, out, reference_fasta=latin)
    row = (out / "candidate_summary.tsv").read_text(encoding="utf-8").splitlines()[1].split("\t")
    assert row[0] == "q1"
    assert row[-3]
