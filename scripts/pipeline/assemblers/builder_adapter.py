#!/usr/bin/env python3
"""Braço opcional que publica a saída do pacote ``genein-builder`` 0.4.0.

O pacote não faz parte do lock do Gene-In. Este adaptador só corre quando
``ASSEMBLER=builder``. O contrato da 0.4.0 está fixado no commit
``af7cb088b3013df07fd3abfaa23ba89dba42cf6b``. As saídas originais, incluindo
colunas de avisos e manifesto, permanecem em ``builder_raw/``.

``genein-builder run --r1 R1 [--r2 R2] --saida DIR --motor {v1,megahit} [-t N]``

``-t`` só vai com ``--motor megahit``. Entrada simples omite ``--r2``. Não existe
``--single``. ``DIR/fragmentos/`` sai por padrão, com todos os registros da
montagem; ``DIR/contigs.fasta`` repete os de 200 pb ou mais. Por isso o FASTA
publicado sai só das tabelas de fragmentos, uma vez por registro.

A versão gravada vem de ``genein-builder --version``; o commit e o status vêm de
``DIR/manifesto_execucao.json``.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


MIN_PUBLISHED_BP = 20
EXPECTED_DISTRIBUTION = "genein-builder"
EXPECTED_VERSION = "0.4.0"
PINNED_BUILDER_COMMIT = "af7cb088b3013df07fd3abfaa23ba89dba42cf6b"
MOTORS = ("v1", "megahit")
# O adaptador não passa -k: o v1 monta com k = 31. O MEGAHIT usa a própria lista de k.
BUILDER_K = {"v1": "31", "megahit": "NA"}
INSTALL_URL = (
    "git+https://github.com/AlexgrothViro/genein-builder.git@"
    + PINNED_BUILDER_COMMIT
)
MANIFEST_NAME = "manifesto_execucao.json"
# Código 3 da 0.2.0 (decisão 2f): sem k-mer válido ou motor sem registro. Continua falha.
NO_ASSEMBLY_CODE = 3
STATUS_BY_MANIFEST = {
    "ok": "OK",
    "so_fragmentos": "SO_FRAGMENTOS",
    "sem_kmer_valido": "SEM_KMER_VALIDO",
    "sem_registros": "SEM_REGISTROS",
}
STATUS_CODE_0 = ("ok", "so_fragmentos")
STATUS_CODE_3 = ("sem_kmer_valido", "sem_registros")
FRAGMENT_TABLES = (
    ("fragmentos.tsv", "fragmentos.fasta"),
    ("fragmentos_restritos.tsv", "fragmentos_restritos.fasta"),
)
# Faixas da coluna `faixa` da 0.2.0, sem '<' nem '>' no cabeçalho publicado.
FAIXA_TOKENS = {">=200": "ge200", "50-199": "50-199", "31-49": "31-49", "<31": "lt31"}
CONTIG_FAIXA = ">=200"
NO_RESTRICTION = "nenhuma"
DNA_RE = re.compile(r"[ACGTNacgtn]+")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
SAFE_VALUE_RE = re.compile(r"[A-Za-z0-9._+-]*")
TOKEN_RE = re.compile(r"[^A-Za-z0-9._:-]+")
VERSION_RE = re.compile(r"genein-builder\s+([0-9][A-Za-z0-9.]*)")
PROVENANCE_KEYS = (
    "BUILDER_VERSION",
    "BUILDER_COMMIT",
    "BUILDER_MOTOR",
    "BUILDER_STATUS",
    "BUILDER_K",
    "BUILDER_CONTIG_COUNT",
    "BUILDER_FRAGMENT_COUNT",
    "BUILDER_DROPPED_LT20",
)


class BuilderNotInstalled(RuntimeError):
    """O pacote opcional não está disponível neste interpretador."""


class BuilderFailed(RuntimeError):
    """O executável do Builder encerrou com código diferente de zero."""


def install_message() -> str:
    return (
        "genein-builder nao esta instalado.\n"
        "O pacote Python genein-builder "
        f"{EXPECTED_VERSION} e opcional e nao faz parte do lock do Gene-In.\n"
        "Instale-o em ambiente separado (exige acesso ao repositorio privado):\n"
        "  bash bundle/install_builder.sh\n"
        "Sem esse pacote, ASSEMBLER=builder para aqui e nao troca para "
        "velvet, spades ou metaspades.\n"
        f"Commit fixado deste adaptador: {PINNED_BUILDER_COMMIT}.\n"
    )


def query_builder_version(executable: list[str]) -> str:
    """Lê ``genein-builder --version``. ``run --version`` não é aceito pelo Builder."""
    completed = subprocess.run(
        [*executable, "--version"],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return "unavailable"
    match = VERSION_RE.search(completed.stdout or "") or VERSION_RE.search(completed.stderr or "")
    return match.group(1) if match else "unavailable"


def locate_builder() -> list[str]:
    """Resolve o executável sem instalar nada.

    Ordem: ``GENEIN_BUILDER_BIN`` (testes e override), ``genein-builder`` no
    PATH, ``python -m genein_builder_cli.cli`` (o ponto de entrada da 0.2.0;
    o pacote ``genein_builder`` é o núcleo e não tem ``__main__``).
    """
    override = os.environ.get("GENEIN_BUILDER_BIN", "").strip()
    if override:
        path = Path(override)
        if not path.is_file() or not os.access(path, os.X_OK):
            raise BuilderNotInstalled(
                f"GENEIN_BUILDER_BIN nao e um executavel: {override}\n" + install_message()
            )
        return [str(path)]
    bundle = Path(os.environ.get("GENEIN_BUNDLE_DIR", str(Path.home() / ".gene-in-bundle")))
    isolated = bundle / "builder-env" / "bin" / "genein-builder"
    if isolated.is_file() and os.access(isolated, os.X_OK):
        return [str(isolated)]
    found = shutil.which("genein-builder")
    if found:
        return [found]
    if importlib.util.find_spec("genein_builder_cli") is not None:
        return [sys.executable, "-m", "genein_builder_cli.cli"]
    raise BuilderNotInstalled(install_message())


def read_manifest(path: Path) -> dict:
    """``manifesto_execucao.json`` do Builder; {} se faltar ou não for JSON."""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def manifest_commit(manifest: dict) -> str:
    """Commit do Builder instalado, como o manifesto o registra.

    ``árvore suja`` vira ``<HEAD>+arvore_suja``; ``sem git`` vira ``sem_git``.
    """
    commit = str(manifest.get("commit", ""))
    if COMMIT_RE.fullmatch(commit):
        return commit
    if commit == "árvore suja":
        head = str(manifest.get("commit_head", ""))
        return f"{head}+arvore_suja" if COMMIT_RE.fullmatch(head) else "arvore_suja"
    if commit == "sem git":
        return "sem_git"
    return "unavailable"


def _token(value: str, fallback: str) -> str:
    cleaned = TOKEN_RE.sub("_", value).strip("_.-:")
    return cleaned or fallback


def _load_fasta(path: Path | None) -> list[tuple[str, str]]:
    if path is None or not path.is_file() or path.stat().st_size == 0:
        return []
    scripts_lib = Path(__file__).resolve().parents[2] / "lib"
    if str(scripts_lib) not in sys.path:
        sys.path.insert(0, str(scripts_lib))
    from input_validation import iter_fasta

    return [(name, sequence) for name, sequence in iter_fasta(path)]


def _parse_fragment_table(path: Path) -> list[dict]:
    """Lê fragmento, comprimento, faixa e restricao. Linhas '#' e vazias não são dados."""
    if not path.is_file() or path.stat().st_size == 0:
        return []
    header: list[str] | None = None
    parsed: list[dict] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = [cell.strip() for cell in line.split("\t")]
        if header is None:
            header = [cell.lower() for cell in cells]
            if not {"fragmento", "comprimento", "faixa"} <= set(header):
                raise ValueError(
                    f"{path.name} sem colunas fragmento, comprimento e faixa (contrato 0.2.0)"
                )
            continue
        if len(cells) != len(header):
            raise ValueError(f"{path.name}:{line_no} com {len(cells)} colunas; o cabecalho tem {len(header)}")
        row = dict(zip(header, cells))
        identifier = row["fragmento"]
        if not identifier:
            raise ValueError(f"{path.name}:{line_no} sem identificador de fragmento")
        try:
            length = int(row["comprimento"])
        except ValueError as exc:
            raise ValueError(f"{path.name}:{line_no} comprimento invalido") from exc
        if length < 0:
            raise ValueError(f"{path.name}:{line_no} comprimento negativo")
        if row["faixa"] not in FAIXA_TOKENS:
            raise ValueError(f"{path.name}:{line_no} faixa desconhecida: {row['faixa']!r}")
        parsed.append({
            "id": identifier,
            "length": length,
            "faixa": row["faixa"],
            "restricao": row.get("restricao") or NO_RESTRICTION,
        })
    return parsed


def _indexed_fasta(path: Path) -> dict[str, str]:
    return {name: sequence for name, sequence in _load_fasta(path)}


def _collect_fragments(fragment_dir: Path | None) -> tuple[list[dict], int]:
    """Junta cada TSV ao FASTA vizinho. A sequência não está na tabela.

    Todo registro do FASTA precisa de uma linha na tabela: faixa e restricao
    vêm dela.
    """
    if fragment_dir is None or not fragment_dir.is_dir():
        return [], 0
    ordered: list[dict] = []
    dropped_without_sequence = 0
    for table_name, fasta_name in FRAGMENT_TABLES:
        rows = _parse_fragment_table(fragment_dir / table_name)
        sequences = _indexed_fasta(fragment_dir / fasta_name)
        seen: set[str] = set()
        for row in rows:
            seen.add(row["id"])
            sequence = sequences.get(row["id"])
            if sequence is None:
                if row["length"] < MIN_PUBLISHED_BP:
                    dropped_without_sequence += 1
                    continue
                raise ValueError(
                    f"fragmento {row['id']} com comprimento {row['length']} "
                    f"sem sequencia em {fasta_name}"
                )
            ordered.append({**row, "sequence": sequence})
        missing = [identifier for identifier in sequences if identifier not in seen]
        if missing:
            raise ValueError(
                f"{fasta_name}: {len(missing)} registro(s) fora de {table_name}, como {missing[0]}"
            )
    return ordered, dropped_without_sequence


def _normalize_sequence(sequence: str, origin: str) -> str:
    compact = "".join(sequence.split())
    if not DNA_RE.fullmatch(compact):
        raise ValueError(f"sequencia {origin} contem base fora de A/C/G/T/N")
    return compact.upper()


def _check_contigs_in_fragments(contigs: Path | None, fragments: list[dict]) -> None:
    """Cada registro de contigs.fasta tem de estar em fragmentos/ com a mesma sequência."""
    by_id = {fragment["id"]: fragment["sequence"] for fragment in fragments}
    for identifier, sequence in _load_fasta(contigs):
        fragment = by_id.get(identifier)
        if fragment is None or (
            _normalize_sequence(fragment, identifier) != _normalize_sequence(sequence, identifier)
        ):
            raise ValueError(
                f"contig {identifier} de contigs.fasta sem o mesmo registro em fragmentos/; "
                "o FASTA publicado sai so dos fragmentos"
            )


def convert_builder_products(
    contigs: Path | None,
    fragment_dir: Path | None,
    *,
    k: str = BUILDER_K["v1"],
) -> tuple[str, dict[str, int]]:
    """Monta o FASTA publicado e as contagens.

    Só as tabelas de fragmentos entram, na ordem de ``fragmentos.tsv`` e depois
    ``fragmentos_restritos.tsv``. Cada registro de ``contigs.fasta`` (≥ 200 pb)
    está nelas e sai uma vez, com ``class=contig``. Sequências com menos de
    20 pb ficam de fora e são contadas. FASTA de 0 bytes é ausência de
    sequência, não erro.
    """
    fragments, missing_short = _collect_fragments(fragment_dir)
    _check_contigs_in_fragments(contigs, fragments)

    kept: list[str] = []
    seen: set[str] = set()
    counts = {"contigs": 0, "fragments": 0, "dropped_lt20": missing_short}
    for fragment in fragments:
        identifier = fragment["id"]
        normalized = _normalize_sequence(fragment["sequence"], identifier)
        if len(normalized) < MIN_PUBLISHED_BP:
            counts["dropped_lt20"] += 1
            continue
        kind = "contig" if fragment["faixa"] == CONTIG_FAIXA else "fragment"
        token = _token(identifier, kind)
        tail = (
            f"|len={len(normalized)}|faixa={FAIXA_TOKENS[fragment['faixa']]}"
            f"|restricao={_token(fragment['restricao'], NO_RESTRICTION)}|k={k}|tool=genein-builder"
        )
        header = f"builder|class={kind}|source_id={token}{tail}"
        suffix = 2
        while header in seen:
            header = f"builder|class={kind}|source_id={token}~{suffix}{tail}"
            suffix += 1
        seen.add(header)
        kept.append(f">{header}\n{normalized}\n")
        if kind == "contig":
            counts["contigs"] += 1
        else:
            counts["fragments"] += 1
    return "".join(kept), counts


def _safe(value: str) -> str:
    return value if SAFE_VALUE_RE.fullmatch(value) else "unavailable"


def provenance_text(
    status: str,
    counts: dict[str, int] | None = None,
    version: str = "unavailable",
    commit: str = "unavailable",
    motor: str = "v1",
) -> str:
    counts = counts or {"contigs": 0, "fragments": 0, "dropped_lt20": 0}
    fields = {
        "BUILDER_VERSION": _safe(version),
        "BUILDER_COMMIT": _safe(commit),
        "BUILDER_MOTOR": _safe(motor),
        "BUILDER_STATUS": _safe(status),
        "BUILDER_K": BUILDER_K.get(motor, "unavailable"),
        "BUILDER_CONTIG_COUNT": str(counts["contigs"]),
        "BUILDER_FRAGMENT_COUNT": str(counts["fragments"]),
        "BUILDER_DROPPED_LT20": str(counts["dropped_lt20"]),
    }
    return "".join(f'{key}="{fields[key]}"\n' for key in PROVENANCE_KEYS)


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def builder_argv(
    executable: list[str],
    *,
    output: Path,
    read1: Path,
    read2: Path | None,
    motor: str = "v1",
    threads: int | None = None,
) -> list[str]:
    """Chamada da 0.2.0: ``-t`` só com o motor megahit; sem ``--single``."""
    if motor not in MOTORS:
        raise ValueError(f"motor desconhecido: {motor}")
    if threads is not None and motor != "megahit":
        raise ValueError("threads so vale com o motor megahit")
    argv = [*executable, "run", "--r1", str(read1)]
    if read2 is not None:
        argv.extend(["--r2", str(read2)])
    argv.extend(["--saida", str(output), "--motor", motor])
    if threads is not None:
        argv.extend(["-t", str(threads)])
    # O Gene-In aceita qualquer hospedeiro; não declarar um hospedeiro presumido.
    return argv


def publish_converted(outdir: Path, fasta_text: str, provenance: str) -> None:
    write_atomic(outdir / "contigs.fasta", fasta_text)
    write_atomic(outdir / "builder_provenance.env", provenance)


def _forward_builder_output(completed: subprocess.CompletedProcess[str]) -> None:
    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
        if not completed.stderr.endswith("\n"):
            sys.stderr.write("\n")


def _preserve_raw(raw: Path, outdir: Path) -> None:
    preserved = outdir / "builder_raw"
    if preserved.exists():
        archive = outdir / "descarte"
        archive.mkdir(exist_ok=True)
        previous = Path(tempfile.mkdtemp(prefix="builder_raw-", dir=archive))
        preserved.rename(previous / "builder_raw")
    shutil.copytree(raw, preserved)


def _warn_commit(commit: str) -> None:
    if commit != PINNED_BUILDER_COMMIT:
        print(
            f"[AVISO] commit do Builder instalado ({commit}, do manifesto) difere do fixado "
            f"neste adaptador ({PINNED_BUILDER_COMMIT}); fica gravado o instalado.",
            file=sys.stderr,
        )


def run_builder(
    *,
    outdir: Path,
    read1: Path,
    read2: Path | None,
    motor: str = "v1",
    threads: int | None = None,
) -> int:
    outdir.mkdir(parents=True, exist_ok=True)
    provenance_path = outdir / "builder_provenance.env"
    try:
        executable = locate_builder()
    except BuilderNotInstalled as exc:
        write_atomic(provenance_path, provenance_text("MISSING", motor=motor))
        print(exc, file=sys.stderr)
        return 2

    version = query_builder_version(executable)
    if version != EXPECTED_VERSION:
        write_atomic(provenance_path, provenance_text("FAILED", version=version, motor=motor))
        print(
            f"genein-builder instalado: {version}. Este adaptador segue o contrato da "
            f"{EXPECTED_VERSION} (status, faixa, --motor). Nenhum outro montador sera acionado.\n"
            "  bash bundle/install_builder.sh",
            file=sys.stderr,
        )
        return 2
    raw = Path(tempfile.mkdtemp(prefix="genein-builder-"))
    try:
        argv = builder_argv(
            executable, output=raw, read1=read1, read2=read2, motor=motor, threads=threads,
        )
        print("[INFO] genein-builder " + " ".join(argv[1:]), file=sys.stderr)
        completed = subprocess.run(argv, check=False, text=True, capture_output=True)
        _forward_builder_output(completed)
        manifest = read_manifest(raw / MANIFEST_NAME)
        commit = manifest_commit(manifest)
        _warn_commit(commit)
        builder_status = str(manifest.get("status", ""))
        if completed.returncode == NO_ASSEMBLY_CODE and builder_status in STATUS_CODE_3:
            _preserve_raw(raw, outdir)
            write_atomic(
                provenance_path,
                provenance_text(
                    STATUS_BY_MANIFEST[builder_status], version=version, commit=commit, motor=motor,
                ),
            )
            print(
                f"genein-builder encerrou com codigo 3 ({builder_status}). "
                "A falha fica registrada; nenhum outro montador sera acionado.",
                file=sys.stderr,
            )
            return 1
        if completed.returncode != 0:
            write_atomic(
                provenance_path,
                provenance_text("FAILED", version=version, commit=commit, motor=motor),
            )
            print(
                f"genein-builder encerrou com codigo {completed.returncode}. "
                "Nenhum outro montador sera acionado.",
                file=sys.stderr,
            )
            if completed.returncode in (1, 2):
                return completed.returncode
            return 1
        contigs = raw / "contigs.fasta"
        fragment_dir = raw / "fragmentos"
        try:
            if builder_status not in STATUS_CODE_0:
                raise ValueError(f"{MANIFEST_NAME} sem status ok ou so_fragmentos ({builder_status!r})")
            if not fragment_dir.is_dir():
                raise ValueError("fragmentos/ ausente")
            fasta_text, counts = convert_builder_products(
                contigs if contigs.is_file() else None,
                fragment_dir,
                k=BUILDER_K[motor],
            )
        except (OSError, ValueError) as exc:
            write_atomic(
                provenance_path,
                provenance_text("FAILED", version=version, commit=commit, motor=motor),
            )
            print(f"saida do genein-builder invalida: {exc}", file=sys.stderr)
            return 1
        _preserve_raw(raw, outdir)
        status = STATUS_BY_MANIFEST[builder_status]
        publish_converted(outdir, fasta_text, provenance_text(status, counts, version, commit, motor))
        if not fasta_text:
            print(
                "Builder concluiu sem sequencias de 20 pb ou mais. "
                "A saida vazia fica registrada; nao ha troca de montador.",
                file=sys.stderr,
            )
        return 0
    finally:
        shutil.rmtree(raw, ignore_errors=True)


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("deve ser inteiro positivo")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Adaptador opcional do Gene-In Builder")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Confere disponibilidade e versão, sem montar")
    sub.add_parser("install-spec", help="Dependência opcional fixada por commit")

    run = sub.add_parser("run", help="Executa o Builder e publica o FASTA do Gene-In")
    run.add_argument("--sample", required=True)
    run.add_argument("--outdir", type=Path, required=True)
    run.add_argument("--r1", type=Path, required=True)
    run.add_argument("--r2", type=Path)
    run.add_argument("--motor", choices=MOTORS, default="v1")
    run.add_argument("--threads", type=_positive_int, help="so com --motor megahit (vira -t)")

    convert = sub.add_parser("convert", help="Converte contigs e fragmentos ja produzidos")
    convert.add_argument("--contigs", type=Path)
    convert.add_argument("--fragment-dir", type=Path)
    convert.add_argument("--manifest", type=Path, help="manifesto_execucao.json da mesma execucao")
    convert.add_argument("--motor", choices=MOTORS, default="v1")
    convert.add_argument("--out", type=Path, required=True)
    convert.add_argument("--provenance", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "install-spec":
        print(f"{EXPECTED_DISTRIBUTION} @ {INSTALL_URL}")
        return 0
    if args.command == "check":
        try:
            executable = locate_builder()
            version = query_builder_version(executable)
            if version != EXPECTED_VERSION:
                raise BuilderFailed(f"Builder {version}; esta integração exige {EXPECTED_VERSION}.")
        except (BuilderNotInstalled, BuilderFailed, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps({"available": True, "version": version, "command": executable}))
        return 0
    if args.command == "convert":
        try:
            fasta_text, counts = convert_builder_products(
                args.contigs, args.fragment_dir, k=BUILDER_K[args.motor],
            )
        except (OSError, ValueError) as exc:
            print(f"saida do genein-builder invalida: {exc}", file=sys.stderr)
            return 1
        manifest = read_manifest(args.manifest) if args.manifest else {}
        status = STATUS_BY_MANIFEST.get(str(manifest.get("status", "")), "UNRECORDED")
        version = str(manifest.get("genein_builder", "unavailable"))
        write_atomic(args.out, fasta_text)
        write_atomic(
            args.provenance,
            provenance_text(status, counts, version, manifest_commit(manifest), args.motor),
        )
        return 0

    if args.threads is not None and args.motor != "megahit":
        parser.error("--threads so vale com --motor megahit")
    return run_builder(
        outdir=args.outdir, read1=args.r1, read2=args.r2, motor=args.motor, threads=args.threads,
    )


if __name__ == "__main__":
    raise SystemExit(main())
