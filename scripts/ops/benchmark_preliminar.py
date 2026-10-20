#!/usr/bin/env python3
"""Gera benchmark preliminar (operacional) a partir de artefatos já produzidos."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Benchmark preliminar baseado em resultados existentes.")
    ap.add_argument("--samples", default="DEMO", help="Amostras separadas por vírgula")
    ap.add_argument("--assemblers", default="velvet,metaspades", help="Assemblers separados por vírgula")
    ap.add_argument("--db", default="custom", help="Perfil de DB usado (informativo para notas; PTV é apenas histórico)")
    ap.add_argument("--outdir", default="results/benchmark", help="Diretório de saída")
    return ap.parse_args()


def read_fasta_stats(path: Path) -> Tuple[int, int]:
    contig_count = 0
    max_len = 0
    current_len = 0
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if contig_count > 0 and current_len > max_len:
                    max_len = current_len
                contig_count += 1
                current_len = 0
            else:
                current_len += len(line)
        if contig_count > 0 and current_len > max_len:
            max_len = current_len
    return contig_count, max_len


def count_blast_hits(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        return sum(1 for line in fh if line.strip())


def extract_best_adj_identity(report_path: Path) -> Optional[str]:
    patt = re.compile(r"adj_identity\s*=\s*([0-9]+(?:\.[0-9]+)?)%", re.IGNORECASE)
    with report_path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            m = patt.search(line)
            if m:
                return m.group(1)
    return None


def pick_contigs_path(sample: str, assembler: str, repo_root: Path) -> Optional[Path]:
    candidates: List[Path] = []
    asm = assembler.lower()
    if asm == "velvet":
        candidates.extend(
            [
                repo_root / f"data/assemblies/{sample}_velvet_k31/contigs.fa",
                repo_root / f"data/assemblies/{sample}_velvet/contigs.fa",
            ]
        )
    elif asm in {"spades", "metaspades"}:
        candidates.extend(
            [
                repo_root / f"data/assemblies/{sample}_assembly/contigs.fa",
                repo_root / f"data/assemblies/{sample}_spades/contigs.fasta",
                repo_root / f"data/assemblies/{sample}_spades/contigs.fa",
            ]
        )

    candidates.extend(
        [
            repo_root / f"data/assemblies/{sample}_assembly/contigs.fa",
            repo_root / f"data/assemblies/{sample}_velvet_k31/contigs.fa",
        ]
    )

    for c in candidates:
        if c.is_file() and c.stat().st_size > 0:
            return c
    return None


def write_tsv(rows: List[Dict[str, str]], out_tsv: Path) -> None:
    fields = [
        "sample",
        "assembler",
        "contig_count",
        "max_contig_bp",
        "blast_hits",
        "best_adj_identity",
        "report_status",
        "notes",
    ]
    with out_tsv.open("w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        wr.writeheader()
        for row in rows:
            wr.writerow(row)


def write_markdown(rows: List[Dict[str, str]], out_md: Path, db: str) -> None:
    lines = [
        "# Benchmark preliminar (operacional)",
        "",
        "**Aviso:** este benchmark é preliminar e **não** constitui validação estatística final.",
        "",
        f"DB alvo (informativo): `{db}`",
        "",
        "|sample|assembler|contig_count|max_contig_bp|blast_hits|best_adj_identity|report_status|notes|",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        vals = [r[k] for k in ["sample", "assembler", "contig_count", "max_contig_bp", "blast_hits", "best_adj_identity", "report_status", "notes"]]
        lines.append("|" + "|".join(vals) + "|")
    lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")


def to_num(v: str) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def aggregate(rows: List[Dict[str, str]], key: str) -> Dict[str, float]:
    agg: Dict[str, float] = {}
    for r in rows:
        asm = r["assembler"]
        agg[asm] = agg.get(asm, 0.0) + to_num(r[key])
    return agg


def write_svg_bar(values: Dict[str, float], title: str, out_svg: Path) -> None:
    labels = list(values.keys()) or ["n/a"]
    nums = [values.get(k, 0.0) for k in labels] or [0.0]
    max_v = max(nums) if nums else 1.0
    if max_v <= 0:
        max_v = 1.0

    width, height = 780, 420
    margin_left, margin_bottom, margin_top = 70, 80, 50
    plot_w = width - margin_left - 40
    plot_h = height - margin_top - margin_bottom
    bar_w = max(30, int(plot_w / max(1, len(labels) * 2)))
    gap = bar_w

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width/2}" y="28" text-anchor="middle" font-family="Arial" font-size="18">{title}</text>',
        f'<line x1="{margin_left}" y1="{margin_top+plot_h}" x2="{margin_left+plot_w}" y2="{margin_top+plot_h}" stroke="#333"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top+plot_h}" stroke="#333"/>',
    ]

    x = margin_left + gap // 2
    for label, val in zip(labels, nums):
        h = int((val / max_v) * (plot_h - 10))
        y = margin_top + plot_h - h
        parts.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{h}" fill="#4C78A8"/>')
        parts.append(f'<text x="{x + bar_w/2}" y="{margin_top + plot_h + 18}" text-anchor="middle" font-size="12" font-family="Arial">{label}</text>')
        parts.append(f'<text x="{x + bar_w/2}" y="{y - 6}" text-anchor="middle" font-size="11" font-family="Arial">{val:.0f}</text>')
        x += bar_w + gap

    parts.append("</svg>")
    out_svg.write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    outdir = repo_root / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    samples = [s.strip() for s in args.samples.split(",") if s.strip()]
    assemblers = [a.strip().lower() for a in args.assemblers.split(",") if a.strip()]

    rows: List[Dict[str, str]] = []
    for sample in samples:
        for assembler in assemblers:
            report = repo_root / f"results/reports/{sample}_summary.md"
            blast = repo_root / f"results/blast/{sample}_vs_db.tsv"
            contigs = pick_contigs_path(sample, assembler, repo_root)

            notes: List[str] = []
            report_status = "ok"

            contig_count = "0"
            max_contig_bp = "0"
            if contigs is not None:
                c_count, c_max = read_fasta_stats(contigs)
                contig_count = str(c_count)
                max_contig_bp = str(c_max)
            else:
                report_status = "missing"
                notes.append(f"contigs ausentes; rode make pipeline SAMPLE={sample} ASSEMBLER={assembler}")

            blast_hits = "0"
            if blast.is_file() and blast.stat().st_size > 0:
                blast_hits = str(count_blast_hits(blast))
            else:
                report_status = "missing"
                notes.append(f"BLAST ausente; rode make db DB={args.db} && make pipeline SAMPLE={sample} ASSEMBLER={assembler}")

            best_adj = "NA"
            if report.is_file() and report.stat().st_size > 0:
                val = extract_best_adj_identity(report)
                if val is not None:
                    best_adj = val
            else:
                report_status = "missing"
                notes.append(f"relatório ausente; rode make pipeline SAMPLE={sample} ASSEMBLER={assembler}")

            if report_status == "missing":
                notes.append("ou rode make demo; make db DB=ptv; make pipeline SAMPLE=<sample> ASSEMBLER=<assembler>; make test-demo")

            rows.append(
                {
                    "sample": sample,
                    "assembler": assembler,
                    "contig_count": contig_count,
                    "max_contig_bp": max_contig_bp,
                    "blast_hits": blast_hits,
                    "best_adj_identity": best_adj,
                    "report_status": report_status,
                    "notes": " ; ".join(notes) if notes else "ok",
                }
            )

    write_tsv(rows, outdir / "benchmark_summary.tsv")
    write_markdown(rows, outdir / "benchmark_summary.md", args.db)

    write_svg_bar(aggregate(rows, "contig_count"), "Contigs por assembler", outdir / "contigs_by_assembler.svg")
    write_svg_bar(aggregate(rows, "blast_hits"), "BLAST hits por assembler", outdir / "hits_by_assembler.svg")
    write_svg_bar(aggregate(rows, "max_contig_bp"), "Máx contig (bp) por assembler", outdir / "max_contig_by_assembler.svg")
    print(f"[OK] Benchmark preliminar gerado em: {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
