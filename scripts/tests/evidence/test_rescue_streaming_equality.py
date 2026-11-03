"""Equality of the streaming rescue path against the historical in-memory rules.

The disk deduplicator must keep the same coordinate key, the same rank
(-bitscore, evalue, -pident, line) and the first-seen key order. Export and
validation may stream, but they do not drop, rewrite or reorder rows.
"""
import csv
import importlib.util
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))

from blast_router import deduplicate_combined_hits, deduplicate_hit_files
from common import read_fasta, read_tsv
from export_candidate_sequences import export
from validate_run_artifacts import validate_candidate_exports


def reference_dedup(chunks: list[str]) -> str:
    """Historical deduplicate_combined_hits: one dict of every unique line."""
    order = []
    best = {}
    for line in "".join(chunks).splitlines():
        fields = line.split("\t")
        if len(fields) != 16:
            raise ValueError("BLAST output does not match the configured 16-column outfmt")
        qstart, qend, sstart, send = map(int, (fields[6], fields[7], fields[8], fields[9]))
        bitscore, evalue, pident = float(fields[11]), float(fields[10]), float(fields[2])
        key = (
            fields[0], fields[1],
            "+" if (qend - qstart) * (send - sstart) >= 0 else "-",
            min(qstart, qend), max(qstart, qend),
            min(sstart, send), max(sstart, send),
        )
        rank = (-bitscore, evalue, -pident, line)
        if key not in best:
            order.append(key)
            best[key] = (rank, line)
        elif rank < best[key][0]:
            best[key] = (rank, line)
    output = [best[key][1] for key in order]
    return "\n".join(output) + ("\n" if output else "")


def blast_line(qseqid, sseqid, pident, qstart, qend, sstart, send, evalue, bitscore, qlen=100, slen=1000):
    length = abs(qend - qstart) + 1
    nident = int(round(length * float(pident) / 100.0))
    mismatch = length - nident
    return "\t".join(map(str, [
        qseqid, sseqid, pident, length, mismatch, 0, qstart, qend, sstart, send,
        evalue, bitscore, qlen, slen, nident, 0,
    ]))


class RescueStreamingEqualityTests(unittest.TestCase):
    def test_disk_dedup_matches_in_memory_reference(self):
        rng = random.Random(20261019)
        lines = []
        for index in range(400):
            qstart = rng.randint(1, 40)
            qend = qstart + rng.randint(0, 20)
            forward = rng.random() > 0.3
            sstart = rng.randint(1, 500)
            send = sstart + (qend - qstart) if forward else sstart - (qend - qstart)
            if send < 1:
                send = 1
            lines.append(blast_line(
                f"q{index % 17}", f"s{index % 11}",
                f"{rng.choice([90, 95, 100, 95.5])}",
                qstart, qend, sstart, send,
                rng.choice(["1e-8", "1e-2", "0.0", "1.5e-3"]),
                rng.choice([10, 20, 20.5, 40, 40.0]),
            ))
        # A later line with the same coordinates and a better score replaces
        # the text but must stay in the first-seen slot.
        lines.append(blast_line("q0", "s0", "100", 1, 20, 10, 29, "1e-8", 80))
        lines.insert(0, blast_line("q0", "s0", "90", 1, 20, 10, 29, "1e-2", 20))
        # Equal rank keeps the first line. Reverse-strand coordinates collapse
        # to the same key as the forward pair above only when both ends match.
        lines.append(blast_line("q1", "s1", "95", 5, 1, 40, 36, "1e-4", 15))
        whole = "".join(line + "\n" for line in lines)
        cases = [
            [],
            [""],
            ["\n"],
            [whole],
            [whole[:137], whole[137:800], whole[800:]],
            [line + "\n" for line in lines],
            [whole.replace("\n", "\r\n")],
            [whole[:-1]],
        ]
        for chunks in cases:
            try:
                expected = reference_dedup(chunks)
            except ValueError as exc:
                with self.assertRaisesRegex(ValueError, str(exc)):
                    deduplicate_combined_hits(chunks)
            else:
                self.assertEqual(deduplicate_combined_hits(chunks), expected)

    def test_dedup_file_matches_chunk_api_and_keeps_first_slot(self):
        weak = blast_line("q", "s", "90", 1, 20, 10, 29, "1e-2", 20) + "\n"
        other = blast_line("q", "s", "95", 21, 40, 10, 29, "1e-5", 30) + "\n"
        strong = blast_line("q", "s", "100", 1, 20, 10, 29, "1e-8", 40) + "\n"
        chunks = [weak, other, strong]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "a.tsv"
            second = root / "b.tsv"
            first.write_text(weak + other, encoding="utf-8")
            second.write_text(strong, encoding="utf-8")
            out = root / "combined.tsv"
            deduplicate_hit_files([first, second], out)
            text = out.read_text(encoding="utf-8")
        self.assertEqual(text, reference_dedup(chunks))
        rows = text.strip().splitlines()
        self.assertEqual(len(rows), 2)
        self.assertEqual(float(rows[0].split("\t")[11]), 40.0)
        self.assertEqual(float(rows[1].split("\t")[11]), 30.0)

    def test_malformed_line_is_still_rejected(self):
        with self.assertRaisesRegex(ValueError, "16-column"):
            deduplicate_combined_hits(["only\tthree\tfields\n"])

    def test_export_streams_without_changing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            query = "q1"
            sequence = "ACGT" * 5
            fasta = root / "queries.fa"
            fasta.write_text(f">{query}\n{sequence}\n", encoding="utf-8")
            digest = __import__("hashlib").sha256(sequence.encode("ascii")).hexdigest()
            manifest = {
                "schema_version": "1.0",
                "queries": {query: {"length_bp": 20, "sequence_sha256": digest,
                                    "source_counts": {"short_read": 2, "rescue_read": 1}}},
            }
            manifest_path = root / "queries.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            fragments = root / "fragment_evidence.tsv"
            fields = [
                "qseqid", "sseqid", "task", "category", "taxon", "segment", "orientation",
                "qlen", "slen", "hsp_count", "query_intervals", "reference_intervals",
                "query_covered_bp", "reference_covered_bp", "query_coverage", "weighted_pident",
                "identity_covered_bp", "best_evalue", "best_bitscore", "sum_bitscore",
                "adj_identity_raw", "adj_identity", "integrity_flags", "sequence_sha256",
                "sequence_entropy", "n_fraction", "max_homopolymer_fraction",
                "low_complexity_status", "assembly_method",
            ]
            rows = []
            for subject, covered in (("refA", "16"), ("refB", "20")):
                row = {name: "" for name in fields}
                row.update({
                    "qseqid": query, "sseqid": subject, "task": "blastn-short",
                    "category": "UNLABELED", "query_covered_bp": covered,
                    "query_coverage": "0.800000", "weighted_pident": "95.000000",
                    "best_bitscore": "40.000000", "best_evalue": "1e-05",
                    "assembly_method": "read_level",
                })
                rows.append(row)
            with fragments.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            export(fasta, manifest_path, fragments, root / "review")
            table = read_tsv(root / "review" / "candidate_sequences.tsv")
            self.assertEqual([row["sseqid"] for row in table], ["refA", "refB"])
            self.assertEqual(table[0]["aligned_query_bp"], "16")
            self.assertEqual(table[0]["query_origins"], "rescue_read;short_read")
            self.assertEqual(table[0]["sequence_length_bp"], "20")
            self.assertEqual((root / "review" / "candidate_sequences.fa").read_text(encoding="utf-8"),
                             fasta.read_text(encoding="utf-8"))


DECISION_FIELDS = ["qseqid", "sseqid", "pident", "length", "evalue", "bitscore", "qlen", "disposition", "decision_rule"]
CANDIDATE_FIELDS = [
    "qseqid", "sseqid", "pident", "length", "evalue", "bitscore",
    "qlen", "aln_cov", "adj_identity", "evidence_class", "risk_note",
]
FILTER_SCRIPT = ROOT / "scripts" / "pipeline" / "filter_rescue_reads.py"


def raw_blast_row(qseqid, sseqid, pident, length, evalue, bitscore, qlen):
    fields = [""] * 14
    fields[0] = qseqid
    fields[1] = sseqid
    fields[2] = str(pident)
    fields[3] = str(length)
    fields[10] = str(evalue)
    fields[11] = str(bitscore)
    fields[12] = str(qlen)
    return "\t".join(fields)


def reference_filter_texts(raw_text: str) -> tuple[str, str]:
    """Historical in-memory filter: one list of every row, then the ledger."""
    decisions = []
    best_hits = {}
    if raw_text:
        for row in csv.reader(io.StringIO(raw_text), delimiter="\t"):
            if not row or (len(row) == 1 and row[0] == ""):
                continue
            if len(row) < 14:
                decisions.append({"qseqid": row[0] if row else "", "sseqid": row[1] if len(row) > 1 else "", "disposition": "REJECTED_INVALID_ROW", "decision_rule": "BLAST-ROW-REQUIRES-14-COLUMNS"})
                continue
            qseqid, sseqid = row[0], row[1]
            try:
                pident = float(row[2])
                length = int(float(row[3]))
                evalue = float(row[10])
                bitscore = float(row[11])
                qlen = int(float(row[12]))
            except ValueError:
                decisions.append({"qseqid": qseqid, "sseqid": sseqid, "disposition": "REJECTED_INVALID_METRIC", "decision_rule": "NUMERIC-BLAST-METRICS-REQUIRED"})
                continue
            if qlen <= 0:
                decisions.append({"qseqid": qseqid, "sseqid": sseqid, "pident": pident, "length": length, "evalue": evalue, "bitscore": bitscore, "qlen": qlen, "disposition": "REJECTED_INVALID_QUERY_LENGTH", "decision_rule": "POSITIVE-QUERY-LENGTH"})
                continue
            if pident < 90.0:
                rejection = "MINIMUM_IDENTITY"
            elif evalue > 1e-5:
                rejection = "MAXIMUM_EVALUE"
            elif length < 80 and length < (0.8 * qlen):
                rejection = "MINIMUM_ALIGNMENT_LENGTH_AND_QUERY_FRACTION"
            else:
                rejection = ""
            if rejection:
                decisions.append({"qseqid": qseqid, "sseqid": sseqid, "pident": pident, "length": length, "evalue": evalue, "bitscore": bitscore, "qlen": qlen, "disposition": "REJECTED_FILTER", "decision_rule": rejection})
                continue
            aln_cov = length / qlen if qlen > 0 else 0.0
            hit = {
                "qseqid": qseqid, "sseqid": sseqid, "pident": f"{pident:.3f}", "length": length,
                "evalue": evalue, "bitscore": bitscore, "qlen": qlen, "aln_cov": f"{aln_cov:.5f}",
                "adj_identity": f"{(pident * aln_cov):.3f}", "evidence_class": "READ_LEVEL_SIGNAL",
                "risk_note": "sinal_de_leitura_sem_contig",
            }
            if qseqid not in best_hits or bitscore > best_hits[qseqid]["bitscore"]:
                best_hits[qseqid] = hit
            decisions.append({"qseqid": qseqid, "sseqid": sseqid, "pident": pident, "length": length, "evalue": evalue, "bitscore": bitscore, "qlen": qlen, "disposition": "ACCEPTED_PENDING_BEST_HIT_SELECTION", "decision_rule": "PASS-READ-LEVEL-THRESHOLDS"})
    selected_keys = {(qid, hit["sseqid"], hit["bitscore"], hit["length"], float(hit["pident"])) for qid, hit in best_hits.items()}
    for row in decisions:
        if row["disposition"] != "ACCEPTED_PENDING_BEST_HIT_SELECTION":
            continue
        key = (row["qseqid"], row["sseqid"], row["bitscore"], row["length"], row["pident"])
        if key in selected_keys:
            row["disposition"] = "SELECTED_BEST_HIT"
            row["decision_rule"] = "HIGHEST-BITSCORE-PER-QNAME"
            selected_keys.remove(key)
        else:
            row["disposition"] = "ACCEPTED_ALTERNATIVE_NOT_SELECTED"
            row["decision_rule"] = "LOWER-BITSCORE-THAN-SELECTED-QNAME-HIT"
    decision_buffer = io.StringIO(newline="")
    decision_writer = csv.DictWriter(decision_buffer, fieldnames=DECISION_FIELDS, delimiter="\t", lineterminator="\n", extrasaction="ignore")
    decision_writer.writeheader()
    decision_writer.writerows(decisions)
    candidate_buffer = io.StringIO(newline="")
    candidate_writer = csv.DictWriter(candidate_buffer, fieldnames=CANDIDATE_FIELDS, delimiter="\t", lineterminator="\n")
    candidate_writer.writeheader()
    for hit in sorted(best_hits.values(), key=lambda item: -item["bitscore"]):
        copy = dict(hit)
        copy["evalue"] = f"{hit['evalue']:.2e}"
        candidate_writer.writerow(copy)
    return candidate_buffer.getvalue(), decision_buffer.getvalue()


def run_filter(raw: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(FILTER_SCRIPT), "--blast-raw", str(raw), "--out-tsv", str(out)],
        capture_output=True, text=True, check=False,
    )


class RescueFilterEqualityTests(unittest.TestCase):
    def test_streaming_filter_matches_in_memory_reference(self):
        rng = random.Random(20261019)
        lines = [
            raw_blast_row("read-good", "virus_ref", 100, 100, "1e-20", 90, 100),
            raw_blast_row("read-good", "virus_ref", 100, 100, "1e-20", 110, 100),
            raw_blast_row("read-tie", "virus_ref", 95, 90, "1e-8", 40, 100),
            raw_blast_row("read-tie", "other_ref", 96, 90, "1e-8", 40, 100),
            raw_blast_row("read-short-ok", "virus_ref", 100, 20, "1e-8", 20, 20),
            raw_blast_row("read-short-no", "virus_ref", 100, 10, "1e-8", 10, 20),
            raw_blast_row("read-low-id", "virus_ref", 89.9, 100, "1e-20", 80, 100),
            raw_blast_row("read-evalue", "virus_ref", 100, 100, "1e-4", 80, 100),
            raw_blast_row("read-bad-qlen", "virus_ref", 100, 10, "1e-8", 10, 0),
            "only\tthree",
            "q\ts\tnot-a-number\t10\t0\t0\t1\t10\t1\t10\t1e-8\t10\t20\t100",
        ]
        for index in range(40):
            lines.append(raw_blast_row(
                f"q{index % 7}", f"s{index % 3}",
                rng.choice([80, 90, 95.5, 100]),
                rng.choice([10, 16, 20, 80, 100]),
                rng.choice(["1e-8", "1e-5", "1.1e-5", "0.0"]),
                rng.choice([10, 20.5, 40, 40.0]),
                rng.choice([20, 30, 100]),
            ))
        raw_text = "\n".join(lines) + "\n"
        expected_candidates, expected_decisions = reference_filter_texts(raw_text)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw.tsv"
            out = root / "candidates.tsv"
            raw.write_text(raw_text, encoding="utf-8")
            completed = run_filter(raw, out)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(out.read_text(encoding="utf-8"), expected_candidates)
            decisions = out.with_suffix(out.suffix + ".decisions.tsv")
            self.assertEqual(decisions.read_text(encoding="utf-8"), expected_decisions)
            provenance = json.loads((out.with_suffix(out.suffix + ".provenance.json")).read_text(encoding="utf-8"))
        self.assertEqual(provenance["criteria"]["minimum_percent_identity"], 90.0)
        self.assertEqual(provenance["criteria"]["maximum_evalue"], 1e-5)
        self.assertEqual(provenance["criteria"]["minimum_alignment_length_bp"], 80)
        self.assertEqual(provenance["candidate_count"], expected_candidates.count("\n") - 1)

    def test_missing_raw_fails_and_empty_raw_keeps_header_only_output(self):
        header_candidates, header_decisions = reference_filter_texts("")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, prepare in (("missing", None), ("empty", lambda path: path.write_text("", encoding="utf-8"))):
                with self.subTest(name=name):
                    raw = root / f"{name}.tsv"
                    out = root / name / "candidates.tsv"
                    if prepare is not None:
                        prepare(raw)
                    completed = run_filter(raw, out)
                    if name == "missing":
                        # The 2.0.1 distribution tightened this old contract.
                        self.assertNotEqual(completed.returncode, 0)
                        self.assertIn("nao encontrado", completed.stdout + completed.stderr)
                        self.assertFalse(out.exists())
                        continue
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(out.read_text(encoding="utf-8"), header_candidates)
                    decisions = out.with_suffix(out.suffix + ".decisions.tsv")
                    self.assertEqual(decisions.read_text(encoding="utf-8"), header_decisions)

    def test_unreadable_raw_is_a_read_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "not-a-file"
            raw.mkdir()
            self.assertGreater(raw.stat().st_size, 0)
            out = root / "candidates.tsv"
            completed = run_filter(raw, out)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("Erro ao ler arquivo raw BLAST", completed.stderr)
            self.assertNotIn("Erro ao gravar", completed.stderr)

    def test_ledger_write_error_is_not_a_read_error_and_removes_tmp(self):
        spec = importlib.util.spec_from_file_location("filter_rescue_reads_under_test", FILTER_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = module.csv.DictWriter.writerow

        def fail_write(self, row):
            raise OSError("database or disk is full")

        module.csv.DictWriter.writerow = fail_write
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                raw = root / "raw.tsv"
                out = root / "candidates.tsv"
                raw.write_text(raw_blast_row("read-good", "virus_ref", 100, 100, "1e-20", 90, 100) + "\n", encoding="utf-8")
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as caught:
                        previous = sys.argv
                        sys.argv = [str(FILTER_SCRIPT), "--blast-raw", str(raw), "--out-tsv", str(out)]
                        try:
                            module.main()
                        finally:
                            sys.argv = previous
                self.assertEqual(caught.exception.code, 1)
                message = stderr.getvalue()
                self.assertIn("Erro ao gravar ledger de decisoes do resgate", message)
                self.assertIn("database or disk is full", message)
                self.assertNotIn("Erro ao ler arquivo raw BLAST", message)
                leftovers = [path.name for path in root.rglob("*") if path.is_file() and ".tmp." in path.name]
                self.assertEqual(leftovers, [])
        finally:
            module.csv.DictWriter.writerow = original


def reference_validate_candidate_exports(directory: Path) -> list[str]:
    """Historical validator: both TSVs are loaded, then compared row by row."""
    names = ("candidate_queries.json", "candidate_sequences.tsv", "candidate_sequences.fa")
    if not any((directory / name).exists() for name in names):
        return []
    if not all((directory / name).is_file() for name in names):
        return ["candidate recovery exports are incomplete"]
    try:
        manifest = json.loads((directory / names[0]).read_text(encoding="utf-8"))
        if manifest.get("schema_version") != "1.0" or not isinstance(manifest.get("queries"), dict):
            raise ValueError("invalid candidate query manifest")
        metadata = manifest["queries"]
        sequences = read_fasta(directory / names[2])
        rows = read_tsv(directory / names[1])
        fragments = read_tsv(directory / "fragment_evidence.tsv")
        if len(rows) != len(fragments) or set(sequences) != {row["qseqid"] for row in fragments}:
            raise ValueError("candidate exports do not cover every aligned query")
        for row, fragment in zip(rows, fragments):
            query = fragment["qseqid"]
            entry = metadata[query]
            sequence = sequences[query]
            if (hashlib_sha(sequence) != entry["sequence_sha256"] or
                int(entry["length_bp"]) != len(sequence) or
                int(row["sequence_length_bp"]) != len(sequence) or
                row["sequence_sha256"] != entry["sequence_sha256"]):
                raise ValueError(f"candidate sequence/hash/length mismatch: {query}")
            if row["query_origins"] != ";".join(sorted(entry["source_counts"])):
                raise ValueError(f"candidate origin mismatch: {query}")
            if row["aligned_query_bp"] != fragment["query_covered_bp"]:
                raise ValueError(f"candidate aligned length mismatch: {query}")
            for field in ("qseqid", "sseqid", "category", "taxon", "task", "query_coverage",
                          "weighted_pident", "best_bitscore", "best_evalue", "assembly_method"):
                if row[field] != fragment[field]:
                    raise ValueError(f"candidate alignment mismatch for {query}: {field}")
        return []
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
        return [f"invalid candidate recovery exports: {exc}"]


def hashlib_sha(sequence: str) -> str:
    import hashlib
    return hashlib.sha256(sequence.encode("ascii")).hexdigest()


def _review_fixture(root: Path) -> Path:
    query = "q1"
    sequence = "ACGT" * 5
    digest = hashlib_sha(sequence)
    fasta = root / "queries.fa"
    fasta.write_text(f">{query}\n{sequence}\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "queries": {query: {"length_bp": 20, "sequence_sha256": digest,
                            "source_counts": {"short_read": 2, "rescue_read": 1}}},
    }
    manifest_path = root / "queries.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    fields = [
        "qseqid", "sseqid", "task", "category", "taxon", "segment", "orientation",
        "qlen", "slen", "hsp_count", "query_intervals", "reference_intervals",
        "query_covered_bp", "reference_covered_bp", "query_coverage", "weighted_pident",
        "identity_covered_bp", "best_evalue", "best_bitscore", "sum_bitscore",
        "adj_identity_raw", "adj_identity", "integrity_flags", "sequence_sha256",
        "sequence_entropy", "n_fraction", "max_homopolymer_fraction",
        "low_complexity_status", "assembly_method",
    ]
    fragments = root / "fragment_evidence.tsv"
    rows = []
    for subject, covered in (("refA", "16"), ("refB", "20")):
        row = {name: "" for name in fields}
        row.update({
            "qseqid": query, "sseqid": subject, "task": "blastn-short",
            "category": "UNLABELED", "query_covered_bp": covered,
            "query_coverage": "0.800000", "weighted_pident": "95.000000",
            "best_bitscore": "40.000000", "best_evalue": "1e-05",
            "assembly_method": "read_level", "sequence_sha256": digest,
        })
        rows.append(row)
    with fragments.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    review = root / "review"
    export(fasta, manifest_path, fragments, review)
    (review / "fragment_evidence.tsv").write_bytes(fragments.read_bytes())
    return review


class CandidateExportValidationEqualityTests(unittest.TestCase):
    def test_streaming_validator_matches_in_memory_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = _review_fixture(Path(tmp))
            self.assertEqual(validate_candidate_exports(review), reference_validate_candidate_exports(review))
            self.assertEqual(validate_candidate_exports(review), [])
            table = review / "candidate_sequences.tsv"
            text = table.read_text(encoding="utf-8")
            table.write_text(text.replace("\t16\t", "\t15\t", 1), encoding="utf-8")
            streamed = validate_candidate_exports(review)
            historical = reference_validate_candidate_exports(review)
            self.assertEqual(streamed, historical)
            self.assertTrue(streamed)
            table.write_text(text, encoding="utf-8")
            (review / "candidate_sequences.fa").write_text(">other\n" + "A" * 20 + "\n", encoding="utf-8")
            self.assertEqual(
                validate_candidate_exports(review),
                reference_validate_candidate_exports(review),
            )
            (review / "candidate_sequences.fa").unlink()
            self.assertEqual(
                validate_candidate_exports(review),
                ["candidate recovery exports are incomplete"],
            )
            self.assertEqual(
                reference_validate_candidate_exports(review),
                ["candidate recovery exports are incomplete"],
            )

    def test_directory_without_candidate_exports_stays_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.assertEqual(validate_candidate_exports(directory), [])
            self.assertEqual(reference_validate_candidate_exports(directory), [])


def _resource_wrapper() -> str:
    script = (ROOT / "scripts" / "evidence" / "run.sh").read_text(encoding="utf-8")
    start = script.index("# BEGIN resource_shortage\n")
    end = script.index("# END resource_shortage\n")
    return script[start:end]


class ResourceShortageClassificationTests(unittest.TestCase):
    def test_run_sh_classifies_enospc_and_sqlite_disk_full(self):
        function = _resource_wrapper()
        runner = (ROOT / "scripts" / "evidence" / "run.sh").read_text(encoding="utf-8")
        self.assertIn('local failed_command="${EVIDENCE_FAILED_COMMAND:-${BASH_COMMAND:-}}"', runner)
        self.assertNotIn("O tipo de falha permanece TOOL_FAILURE", runner)
        cases = [
            ("sqlite3.OperationalError: database or disk is full\n", 1, "1"),
            ("OSError: [Errno 28] No space left on device\n", 1, "1"),
            ("ENOSPC\n", 1, "1"),
            ("boom\n", 3, "0"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for text, code, shortage in cases:
                with self.subTest(text=text, code=code):
                    probe = r'''
set -euo pipefail
RESOURCE_SHORTAGE=0
EVIDENCE_FAILED_COMMAND=""
__FUNCTION__
set +e
run_recording_stderr python3 -c 'import sys; sys.stderr.write(sys.argv[1]); sys.exit(int(sys.argv[2]))' "$1" "$2"
rc=$?
set -e
printf 'RC=%s\nSHORTAGE=%s\n' "$rc" "$RESOURCE_SHORTAGE"
'''
                    probe = probe.replace("__FUNCTION__", function)
                    completed = subprocess.run(
                        ["bash", "-c", probe, "probe", text, str(code)],
                        capture_output=True, text=True, check=False,
                        env={**os.environ, "TMPDIR": tmp, "OUTDIR": tmp},
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertIn(f"RC={code}", completed.stdout)
                    self.assertIn(f"SHORTAGE={shortage}", completed.stdout)
                    if shortage == "1":
                        self.assertIn("Próximo passo: libere espaço em disco", completed.stderr)
                        self.assertIn(f"TMPDIR={tmp}", completed.stderr)
                    else:
                        self.assertNotIn("Próximo passo: libere espaço em disco", completed.stderr)
                    self.assertEqual(list(Path(tmp).glob(".genein-cmd-err.*")), [])
            quiet = function + r'''
set -euo pipefail
RESOURCE_SHORTAGE=0
run_recording_stderr python3 -c 'import sys; sys.stderr.write("database or disk is full\n")'
printf 'RC=%s\nSHORTAGE=%s\n' "$?" "$RESOURCE_SHORTAGE"
'''
            completed = subprocess.run(
                ["bash", "-c", quiet], capture_output=True, text=True, check=False,
                env={**os.environ, "TMPDIR": tmp, "OUTDIR": tmp},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("RC=0", completed.stdout)
            self.assertIn("SHORTAGE=0", completed.stdout)
            self.assertNotIn("Próximo passo: libere espaço em disco", completed.stderr)

    def test_failed_command_is_the_wrapped_stage_not_the_internal_return(self):
        function = _resource_wrapper()
        with tempfile.TemporaryDirectory() as tmp:
            probe = r'''
set -euo pipefail
RESOURCE_SHORTAGE=0
EVIDENCE_FAILED_COMMAND=""
__FUNCTION__
trap 'printf "FAILED_COMMAND=%s\n" "${EVIDENCE_FAILED_COMMAND:-${BASH_COMMAND:-}}"; exit 0' ERR
run_recording_stderr python3 -c 'import sys; sys.exit(4)'
echo SHOULD_NOT_REACH
'''
            probe = probe.replace("__FUNCTION__", function)
            completed = subprocess.run(
                ["bash", "-c", probe],
                capture_output=True, text=True, check=False,
                env={**os.environ, "TMPDIR": tmp, "OUTDIR": tmp},
            )
            self.assertEqual(list(Path(tmp).glob(".genein-cmd-err.*")), [])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("FAILED_COMMAND=python3 -c import sys; sys.exit(4)", completed.stdout)
        self.assertNotIn('return "$rc"', completed.stdout)
        self.assertNotIn("SHOULD_NOT_REACH", completed.stdout)

    def test_unusable_tmpdir_does_not_fake_disk_full(self):
        function = _resource_wrapper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outdir = root / "outdir"
            outdir.mkdir()
            missing_tmp = root / "missing-tmpdir"
            blocked = root / "blocked-tmpdir"
            blocked.mkdir()
            os.chmod(blocked, 0o500)
            missing_out = root / "missing-outdir"
            cases = [
                ("missing-tmp-success", str(missing_tmp), str(outdir), "import sys; sys.exit(0)", "0", "0"),
                ("blocked-tmp-success", str(blocked), str(outdir), "import sys; sys.exit(0)", "0", "0"),
                ("missing-tmp-other-error", str(missing_tmp), str(outdir), "import sys; sys.stderr.write('boom\\n'); sys.exit(3)", "3", "0"),
                ("missing-out-success", str(root), str(missing_out), "import sys; sys.exit(0)", "0", "0"),
                ("missing-tmp-disk-full", str(missing_tmp), str(outdir), "import sys; sys.stderr.write('database or disk is full\\n'); sys.exit(1)", "1", "1"),
            ]
            for name, tmpdir, capture_dir, program, code, shortage in cases:
                with self.subTest(name=name):
                    probe = r'''
set -euo pipefail
RESOURCE_SHORTAGE=0
EVIDENCE_FAILED_COMMAND=""
__FUNCTION__
set +e
run_recording_stderr python3 -c "$1"
rc=$?
printf 'RC=%s\nSHORTAGE=%s\nCMD=%s\n' "$rc" "$RESOURCE_SHORTAGE" "$EVIDENCE_FAILED_COMMAND"
'''
                    probe = probe.replace("__FUNCTION__", function)
                    completed = subprocess.run(
                        ["bash", "-c", probe, "probe", program],
                        capture_output=True, text=True, check=False,
                        env={**os.environ, "TMPDIR": tmpdir, "OUTDIR": capture_dir},
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertIn(f"RC={code}", completed.stdout)
                    self.assertIn(f"SHORTAGE={shortage}", completed.stdout)
                    if shortage == "1":
                        self.assertIn("Próximo passo: libere espaço em disco", completed.stderr)
                        self.assertIn("database or disk is full", completed.stderr)
                    else:
                        self.assertNotIn("Próximo passo: libere espaço em disco", completed.stderr)
                        self.assertNotIn("disco cheio", completed.stderr)
            self.assertEqual(list(outdir.glob(".genein-cmd-err.*")), [])


if __name__ == "__main__":
    unittest.main()
