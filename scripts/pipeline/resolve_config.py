#!/usr/bin/env python3
"""Single configuration resolver for the canonical Gene-In run.

Both ``scripts/pipeline/run.sh`` and ``scripts/evidence/run.sh`` used to
resolve configuration by hand, in bash and in ad hoc repeated subprocess
calls:

* ``pipeline/run.sh`` captured ~27 dashboard/env variables into
  ``INCOMING_*`` copies, ``source``d ``config/picornavirus.env`` on top of
  them, then restored each one with its own ``if [[ -n "$INCOMING_X" ]]``
  block, followed by a second wave of default-and-validate statements and
  ``resolve_path`` calls.
* ``evidence/run.sh`` re-read the same activation policy and evidence
  profile from disk through more than fifteen separate ``python3``
  subprocess calls, one field at a time (``activation_policy.py --field
  ...`` and ``config_value.py --key ...``).

This module is the single place that:

* applies the precedence documented in ``pipeline/run.sh`` (command line
  argument > environment/config-file value > internal safe default) for
  every pipeline-level variable, preserving the pre-existing asymmetry
  between variables that are captured *before* ``config/picornavirus.env``
  is sourced (environment wins over the config file) and variables that
  were never captured that way (the config file wins over a pre-existing
  environment value, because bash's own ``source`` simply overwrites them);
* validates ``THREADS``, ``VELVET_K``, ``ASSEMBLER``, ``BLAST_TASK``,
  ``HOST_FILTER_ENABLED``, ``ROLE``, ``QC_STATUS`` and
  ``HOST_FILTER_STATUS``;
* resolves ``REPO_ROOT``-relative paths exactly like ``resolve_path`` in
  ``scripts/lib/common.sh``;
* loads the activation policy and evidence profile exactly once, reusing
  ``load_public_activation_policy``/``load_experimental_activation_policy``;
* and freezes the result as one ``resolved_config.json`` document that the
  shell only has to read back.

Nothing here ever parses ``config/picornavirus.env`` itself. That file is
sourced by bash, which is the only interpreter that can safely honour
arbitrary shell syntax inside it (command substitution, references to other
variables, conditionals, and so on). ``pipeline/run.sh`` still does that
``source`` itself and only ever hands this module the *resulting* variable
values, as plain strings, through ``--incoming``/``--sourced`` pairs. If a
future config file needs something this module cannot express as a plain
string, bash's own ``source`` will fail exactly as it does today; this
module introduces no new, silent way to misread it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# activation_policy.py lives in ../evidence and analysis_profiles.py lives
# next to this file; make both importable regardless of whether this module
# is run as a script, imported by a test, or (one day) packaged, without
# duplicating either module's logic here.
_THIS_DIR = Path(__file__).resolve().parent
_EVIDENCE_DIR = _THIS_DIR.parent / "evidence"
for _extra_path in (str(_THIS_DIR), str(_EVIDENCE_DIR)):
    if _extra_path not in sys.path:
        sys.path.insert(0, _extra_path)

from activation_policy import (  # noqa: E402
    load_experimental_activation_policy,
    load_public_activation_policy,
    policy_identity,
)
from analysis_profiles import load_profiles, resolve_profile  # noqa: E402


SCHEMA_VERSION = "1.0"

# Variables captured *before* config/picornavirus.env is sourced, so that an
# explicit environment value wins over whatever the config file says (the
# "dashboard priority" rule documented at the top of the historical
# pipeline/run.sh). ``BLAST_DB`` is included because its precedence follows
# the same rule; the DB-identity interaction is handled separately below.
TIER_A_FIELDS = (
    "DB", "DB_QUERY", "BLAST_DB", "ASSEMBLER", "ANALYSIS_PROFILE",
    "HOST_FILTER_ENABLED", "HOST_NAME", "HOST_ACCESSION", "HOST_INDEX_PREFIX",
    "SHORT_FRAGMENT_MODE", "SHORT_FRAGMENT_MIN_LEN", "SHORT_FRAGMENT_MAX_LEN",
    "SHORT_FRAGMENT_DEDUP", "SHORT_FRAGMENT_BLAST", "SHORT_FRAGMENT_WORD_SIZE",
    "SHORT_FRAGMENT_EVALUE", "SHORT_FRAGMENT_MIN_PID", "SHORT_FRAGMENT_MIN_QCOV",
    "EVIDENCE_V2", "EVIDENCE_PROFILES", "EVIDENCE_ROOT", "EVIDENCE_LIBRARY_MODE",
    "EVIDENCE_UMI_MODE", "EVIDENCE_ROLE", "EVIDENCE_EXPECTED_TARGET",
    "EVIDENCE_COMPOSITE_DB", "EVIDENCE_SUBJECT_LABELS", "EVIDENCE_PANEL_FASTA",
    "EVIDENCE_PANEL_INDEX", "EVIDENCE_RUN_ID", "EVIDENCE_BATCH_ID",
    "SEARCH_PROFILES",
)

# Variables that were never captured before sourcing, so the config file (if
# it sets them) already wins over a pre-existing environment value by plain
# bash scoping. Only the post-source value matters here.
TIER_B_FIELDS = (
    "VELVET_K", "THREADS", "SPADES_PARAMS", "ADVANCED_KMERS",
    "BLAST_TASK", "BLAST_WORD_SIZE", "BLAST_EVALUE", "CONTIGS",
    "RAW_DIR", "QC_OUT_DIR", "QC_REPORT_DIR", "HOST_REMOVED_DIR",
    "SAMPLE_R1", "SAMPLE_R2", "SAMPLE_SINGLE",
)

DEFAULTS = {
    "DB_QUERY": "",
    "ASSEMBLER": "velvet",
    "ANALYSIS_PROFILE": "default",
    "HOST_FILTER_ENABLED": "false",
    "HOST_NAME": "",
    "HOST_ACCESSION": "",
    "HOST_INDEX_PREFIX": "",
    "SHORT_FRAGMENT_MODE": "false",
    "SHORT_FRAGMENT_MIN_LEN": "20",
    "SHORT_FRAGMENT_MAX_LEN": "100",
    "SHORT_FRAGMENT_DEDUP": "true",
    "SHORT_FRAGMENT_BLAST": "false",
    "SHORT_FRAGMENT_WORD_SIZE": "7",
    "SHORT_FRAGMENT_EVALUE": "1000",
    "SHORT_FRAGMENT_MIN_PID": "70",
    "SHORT_FRAGMENT_MIN_QCOV": "70",
    "EVIDENCE_V2": "false",
    "EVIDENCE_LIBRARY_MODE": "unknown",
    "EVIDENCE_UMI_MODE": "none",
    "EVIDENCE_ROLE": "sample",
    "EVIDENCE_EXPECTED_TARGET": "",
    "EVIDENCE_COMPOSITE_DB": "",
    "EVIDENCE_SUBJECT_LABELS": "",
    "EVIDENCE_PANEL_FASTA": "",
    "EVIDENCE_PANEL_INDEX": "",
    "EVIDENCE_RUN_ID": "",
    "EVIDENCE_BATCH_ID": "",
    "SEARCH_PROFILES": "",
    "VELVET_K": "31",
    "THREADS": "4",
    "SPADES_PARAMS": "",
    "ADVANCED_KMERS": "",
    "BLAST_TASK": "blastn",
    "BLAST_WORD_SIZE": "11",
    "BLAST_EVALUE": "1e-5",
    "CONTIGS": "",
    "RAW_DIR": "data/raw",
    "QC_OUT_DIR": "data/cleaned",
    "QC_REPORT_DIR": "results/qc",
    "HOST_REMOVED_DIR": "data/host_removed",
    "SAMPLE_R1": "",
    "SAMPLE_R2": "",
    "SAMPLE_SINGLE": "",
}

HOST_FILTER_TRUE = {"true", "1", "yes", "sim"}
HOST_FILTER_FALSE = {"false", "0", "no", "nao"}
ASSEMBLER_CHOICES = {"velvet", "spades", "metaspades", "consensus"}
BLAST_TASK_CHOICES = {"blastn", "blastn-short"}
ROLE_CHOICES = {"sample", "negative_extraction", "negative_library", "negative_sequencing", "positive"}
QC_STATUS_CHOICES = {"unknown", "completed", "explicitly_skipped", "not_applicable"}
HOST_FILTER_STATUS_CHOICES = {
    "unknown", "completed", "disabled_no_host_declared", "explicitly_skipped", "not_applicable",
}


# --- Search profiles (GEN-013) ------------------------------------------
#
# Three *contract labels* for the search that a run performed. They are
# deliberately labels, not new science: each one is nothing but a name for a
# combination of flags this pipeline already had, and the resolver is the one
# place that freezes which of them a run actually used.
#
#   A — the public default: blastn of the assembled contigs against the local
#       BLAST_DB built from DB/DB_QUERY. Always on; it is the pre-existing
#       behaviour and cannot be switched off here.
#   B — competitive panel, driven by the existing EVIDENCE_COMPOSITE_DB /
#       EVIDENCE_SUBJECT_LABELS flags. Off unless the run asks for it.
#   C — short fragments, driven by the existing SHORT_FRAGMENT_MODE /
#       SHORT_FRAGMENT_BLAST flags (blastn-short against the *same* BLAST_DB).
#       Off unless the run asks for it.
#
# The literal product IDs for B and C are still open (see the GEN-013
# ticket), so nothing here invents one: the labels are A/B/C and the mapping
# to the existing flags is recorded alongside them.
SEARCH_PROFILE_CHOICES = ("A", "B", "C")
SEARCH_PROFILE_IDENTITY_PREFIX = "search-profile"


class ConfigError(ValueError):
    """A resolved value fails validation. Mirrors the historical FATAL messages."""


def parse_search_profiles(value: str) -> tuple[str, ...]:
    """Normalise a ``SEARCH_PROFILES``/``--search-profiles`` selection.

    Accepts ``A,C`` / ``a c`` / ``A+C`` and returns a de-duplicated tuple in
    the canonical A, B, C order. An empty selection means "nothing was asked
    for", which is what keeps the public default untouched.
    """
    tokens = [token for token in value.replace("+", ",").replace(" ", ",").split(",") if token]
    selected: list[str] = []
    for token in tokens:
        label = token.strip().upper()
        if label not in SEARCH_PROFILE_CHOICES:
            raise ConfigError(
                f"SEARCH_PROFILES invalido: {token} — Use A, B ou C (ex.: A,C)."
            )
        if label not in selected:
            selected.append(label)
    return tuple(sorted(selected, key=SEARCH_PROFILE_CHOICES.index))


def resolve_path(value: str, repo_root: str) -> str:
    """Match ``resolve_path`` in scripts/lib/common.sh exactly."""
    if not value:
        return value
    if value.startswith("/"):
        return value
    return f"{repo_root}/{value}"


def _layered(cli: str, incoming: str, sourced: str, default: str) -> str:
    for candidate in (cli, incoming, sourced, default):
        if candidate:
            return candidate
    return ""


def _int(name: str, value: str, *, minimum: int, maximum: int | None = None) -> int:
    if not value.isdigit():
        raise ConfigError(f"{name} invalido: {value}")
    number = int(value)
    if number < minimum or (maximum is not None and number > maximum):
        raise ConfigError(f"{name} invalido: {value}")
    return number


def _normalize_host_filter_enabled(value: str) -> str:
    lowered = value.lower()
    if lowered in HOST_FILTER_TRUE:
        return "true"
    if lowered in HOST_FILTER_FALSE:
        return "false"
    raise ConfigError(
        "HOST_FILTER_ENABLED invalido: use true/false (ou 1/0, yes/no, sim/nao)."
    )


def resolve_pipeline_config(
    *,
    repo_root: str,
    incoming: dict[str, str],
    sourced: dict[str, str],
    cli: dict[str, str],
    sample_name: str,
    analysis_profiles_config: str | None = None,
) -> dict:
    """Resolve every pipeline/run.sh configuration variable in one place.

    ``incoming`` holds the values of the env-first variables as bash saw them
    *before* sourcing config/picornavirus.env; ``sourced`` holds every
    tracked variable as bash sees them *after* sourcing it (or unchanged, if
    no config file exists); ``cli`` holds the explicit ``--flag`` overrides
    parsed by run.sh's own argument loop, keyed by the same field names.

    Two resolution orders, named after which source wins:
      ``env_first``    CLI > pre-source env > config file > default
      ``config_first`` CLI > config file > default (pre-source env ignored)

    These are configuration precedence layers. They are unrelated to
    evidence levels or to any scientific classification.
    """

    def env_first(name: str) -> str:
        return _layered(
            cli.get(name, ""), incoming.get(name, ""), sourced.get(name, ""),
            DEFAULTS.get(name, ""),
        )

    def config_first(name: str) -> str:
        return _layered(cli.get(name, ""), "", sourced.get(name, ""), DEFAULTS.get(name, ""))

    # --- DB identity: preserves the historical rule that an explicit
    # env/CLI DB or DB_QUERY discards a stale config-file BLAST_DB, while an
    # explicit env/CLI BLAST_DB always wins regardless. ---
    incoming_db = incoming.get("DB", "")
    incoming_db_query = incoming.get("DB_QUERY", "")
    db_identity_overridden = bool(incoming_db_query) or bool(incoming_db)
    if incoming_db_query and (not incoming_db or incoming_db == "custom"):
        db = "custom"
        db_query = incoming_db_query
    elif incoming_db:
        db = incoming_db
        db_query = ""
    else:
        db = sourced.get("DB", "") or "custom"
        db_query = sourced.get("DB_QUERY", "")
    incoming_blast_db = incoming.get("BLAST_DB", "")
    if incoming_blast_db:
        blast_db = incoming_blast_db
    elif db_identity_overridden:
        blast_db = f"blastdb/{db}"
    else:
        blast_db = sourced.get("BLAST_DB", "") or f"blastdb/{db}"
    blast_db = resolve_path(blast_db, repo_root)

    analysis_profile = env_first("ANALYSIS_PROFILE")
    profiles_catalog = load_profiles(analysis_profiles_config)
    profile_id, profile = resolve_profile(profiles_catalog, analysis_profile)
    analysis_strategy = profile["assembly"]["strategy"]

    assembler_cli = cli.get("ASSEMBLER", "")
    if analysis_strategy == "consensus":
        if assembler_cli:
            raise ConfigError(
                "--assembler não pode ser combinado com o perfil assembly-consensus."
            )
        assembler = "consensus"
    else:
        assembler = env_first("ASSEMBLER")
    if assembler not in ASSEMBLER_CHOICES:
        raise ConfigError(
            f"ASSEMBLER invalido: {assembler} — Use velvet, spades, metaspades ou assembly-consensus."
        )

    blast_task = config_first("BLAST_TASK")
    if blast_task not in BLAST_TASK_CHOICES:
        raise ConfigError(f"BLAST_TASK invalido: {blast_task} — Use blastn ou blastn-short.")

    threads = _int("THREADS", config_first("THREADS"), minimum=1, maximum=256)
    velvet_k = _int("VELVET_K", config_first("VELVET_K"), minimum=15, maximum=127)

    host_filter_enabled = _normalize_host_filter_enabled(env_first("HOST_FILTER_ENABLED"))
    host_index_prefix = resolve_path(env_first("HOST_INDEX_PREFIX"), repo_root)

    contigs = config_first("CONTIGS")
    input_mode = "CONTIGS" if contigs else "READS"
    if contigs:
        contigs = resolve_path(contigs, repo_root)

    raw_dir = resolve_path(config_first("RAW_DIR"), repo_root)
    sample_single = config_first("SAMPLE_SINGLE")
    sample_r1 = config_first("SAMPLE_R1")
    sample_r2 = config_first("SAMPLE_R2")
    if input_mode == "CONTIGS":
        # Contigs clear every read input first, exactly like the historical
        # bash block did before its own mutual-exclusion check — so the
        # check below never fires in this mode.
        sample_single = ""
        sample_r1 = ""
        sample_r2 = ""
    else:
        if sample_single and (sample_r1 or sample_r2):
            raise ConfigError(
                "Use SAMPLE_SINGLE ou SAMPLE_R1/SAMPLE_R2, mas não ambos."
            )
        if sample_single:
            sample_single = resolve_path(sample_single, repo_root)
        else:
            sample_r1 = resolve_path(sample_r1, repo_root) if sample_r1 else f"{raw_dir}/{sample_name}_R1.fastq.gz"
            sample_r2 = resolve_path(sample_r2, repo_root) if sample_r2 else f"{raw_dir}/{sample_name}_R2.fastq.gz"

    evidence_v2 = env_first("EVIDENCE_V2").lower()
    if evidence_v2 not in {"true", "false", "1", "0", "yes"}:
        evidence_v2 = "false"
    evidence_v2 = "true" if evidence_v2 in {"true", "1", "yes"} else "false"

    short_fragment = {
        "mode": env_first("SHORT_FRAGMENT_MODE").lower() == "true",
        "min_len": _int("SHORT_FRAGMENT_MIN_LEN", env_first("SHORT_FRAGMENT_MIN_LEN"), minimum=1),
        "max_len": _int("SHORT_FRAGMENT_MAX_LEN", env_first("SHORT_FRAGMENT_MAX_LEN"), minimum=1),
        "dedup": env_first("SHORT_FRAGMENT_DEDUP").lower() == "true",
        "blast": env_first("SHORT_FRAGMENT_BLAST").lower() == "true",
        "word_size": _int("SHORT_FRAGMENT_WORD_SIZE", env_first("SHORT_FRAGMENT_WORD_SIZE"), minimum=1),
        "evalue": env_first("SHORT_FRAGMENT_EVALUE"),
        "min_pid": _int("SHORT_FRAGMENT_MIN_PID", env_first("SHORT_FRAGMENT_MIN_PID"), minimum=0, maximum=100),
        "min_qcov": _int("SHORT_FRAGMENT_MIN_QCOV", env_first("SHORT_FRAGMENT_MIN_QCOV"), minimum=0, maximum=100),
    }
    composite_db = env_first("EVIDENCE_COMPOSITE_DB")

    # --- Search profile contract (GEN-013) ---
    # Selecting C is the *only* thing that turns SHORT_FRAGMENT_MODE and
    # SHORT_FRAGMENT_BLAST on from here; with no selection the pre-existing
    # values (which default to false) are left exactly as they were, so a run
    # that asks for nothing still performs A and only A. Selecting B never
    # invents a panel: it requires the composite DB the operator curated.
    requested_profiles = parse_search_profiles(env_first("SEARCH_PROFILES"))
    if "C" in requested_profiles:
        short_fragment["mode"] = True
        short_fragment["blast"] = True
    if "B" in requested_profiles and not composite_db:
        raise ConfigError(
            "perfil de busca B exige EVIDENCE_COMPOSITE_DB — "
            "o painel competitivo é curado fora do pipeline e não é criado aqui."
        )
    active_profiles = ["A"]
    if composite_db:
        active_profiles.append("B")
    if short_fragment["mode"] or short_fragment["blast"]:
        active_profiles.append("C")
    search_profile = {
        # What the run asked for ("" = nothing, i.e. the public default),
        # kept next to what it effectively ran so a selection made through
        # the raw flags is still recorded as a profile.
        "requested": ",".join(requested_profiles),
        "selected": "+".join(active_profiles),
        "identity": f"{SEARCH_PROFILE_IDENTITY_PREFIX}:{'+'.join(active_profiles)}",
        "a_active": True,
        "b_active": "B" in active_profiles,
        "c_active": "C" in active_profiles,
        "a_flags": "BLAST_DB,BLAST_TASK,BLAST_WORD_SIZE,BLAST_EVALUE",
        "b_flags": "EVIDENCE_COMPOSITE_DB,EVIDENCE_SUBJECT_LABELS",
        "c_flags": "SHORT_FRAGMENT_MODE,SHORT_FRAGMENT_BLAST",
    }

    resolved = {
        "schema_version": SCHEMA_VERSION,
        "repo_root": repo_root,
        "sample_name": sample_name,
        "input_mode": input_mode,
        "db": db,
        "db_query": db_query,
        "db_identity_overridden": db_identity_overridden,
        "blast_db": blast_db,
        "assembler": assembler,
        "analysis_profile": profile_id,
        "analysis_strategy": analysis_strategy,
        "threads": threads,
        "velvet_k": velvet_k,
        "spades_params": config_first("SPADES_PARAMS"),
        "advanced_kmers": config_first("ADVANCED_KMERS"),
        "blast_task": blast_task,
        "blast_word_size": _int("BLAST_WORD_SIZE", config_first("BLAST_WORD_SIZE"), minimum=1),
        "blast_evalue": config_first("BLAST_EVALUE"),
        "contigs": contigs,
        "host_filter_enabled": host_filter_enabled,
        "host_name": env_first("HOST_NAME"),
        "host_accession": env_first("HOST_ACCESSION"),
        "host_index_prefix": host_index_prefix,
        "raw_dir": raw_dir,
        "qc_out_dir": resolve_path(config_first("QC_OUT_DIR"), repo_root),
        "qc_report_dir": resolve_path(config_first("QC_REPORT_DIR"), repo_root),
        "qc_adapter_r1": env_first("QC_ADAPTER_R1").strip().upper(),
        "qc_adapter_r2": env_first("QC_ADAPTER_R2").strip().upper(),
        "host_removed_dir": resolve_path(config_first("HOST_REMOVED_DIR"), repo_root),
        "sample_r1": sample_r1,
        "sample_r2": sample_r2,
        "sample_single": sample_single,
        "short_fragment": short_fragment,
        "search_profile": search_profile,
        "evidence": {
            "v2": evidence_v2 == "true",
            "profiles": resolve_path(
                env_first("EVIDENCE_PROFILES") or f"{repo_root}/config/evidence_profiles.json", repo_root,
            ),
            "root": resolve_path(
                env_first("EVIDENCE_ROOT") or f"{repo_root}/results/evidence", repo_root,
            ),
            "library_mode": env_first("EVIDENCE_LIBRARY_MODE"),
            "umi_mode": env_first("EVIDENCE_UMI_MODE"),
            "role": env_first("EVIDENCE_ROLE"),
            "expected_target": env_first("EVIDENCE_EXPECTED_TARGET"),
            "composite_db": composite_db,
            "subject_labels": env_first("EVIDENCE_SUBJECT_LABELS"),
            "panel_fasta": env_first("EVIDENCE_PANEL_FASTA"),
            "panel_index": env_first("EVIDENCE_PANEL_INDEX"),
            "run_id": env_first("EVIDENCE_RUN_ID"),
            "batch_id": env_first("EVIDENCE_BATCH_ID"),
            # Reservation tokens are never read from config/picornavirus.env:
            # only an explicit, pre-existing environment value is honoured.
            "reservation_token": incoming.get("EVIDENCE_RESERVATION_TOKEN", ""),
        },
    }
    return resolved


def resolve_evidence_config(
    *,
    activation_policy_path: str | None,
    profiles_path: str | None,
    experimental: bool,
    role: str,
    qc_status: str,
    host_filter_status: str,
) -> dict:
    """Resolve the evidence/run.sh activation policy + thresholds once."""
    if role not in ROLE_CHOICES:
        raise ConfigError(f"invalid role: {role}")
    if qc_status not in QC_STATUS_CHOICES:
        raise ConfigError(f"invalid QC status: {qc_status}")
    if host_filter_status not in HOST_FILTER_STATUS_CHOICES:
        raise ConfigError(f"invalid host filter status: {host_filter_status}")

    if experimental:
        if not activation_policy_path:
            raise ConfigError("experimental activation policy path is required")
        policy = load_experimental_activation_policy(activation_policy_path, profiles_path=profiles_path)
        policy_context = "experimental"
    else:
        policy = load_public_activation_policy(activation_policy_path, profiles_path=profiles_path)
        policy_context = "public"

    identity = policy_identity(policy)
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_context": policy_context,
        "policy_identity": identity,
        "shadow_mode": policy["shadow_mode"],
        "evidence_ceiling": policy["evidence_ceiling"],
        "thresholds": policy["thresholds"],
        "role": role,
        "qc_status": qc_status,
        "host_filter_status": host_filter_status,
    }


def _parse_pairs(pairs: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in pairs:
        name, _, value = pair.partition("=")
        result[name] = value
    return result


def _write_json(path: str, data: dict) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def _cmd_pipeline(args: argparse.Namespace) -> None:
    incoming = _parse_pairs(args.incoming)
    sourced = _parse_pairs(args.sourced)
    cli = _parse_pairs(args.cli)
    resolved = resolve_pipeline_config(
        repo_root=args.repo_root,
        incoming=incoming,
        sourced=sourced,
        cli=cli,
        sample_name=args.sample_name,
        analysis_profiles_config=args.analysis_profiles_config,
    )
    _write_json(args.out, resolved)


def _cmd_evidence(args: argparse.Namespace) -> None:
    experimental = bool(args.experimental_activation_policy)
    activation_policy_path = args.experimental_activation_policy or args.activation_policy
    resolved = resolve_evidence_config(
        activation_policy_path=activation_policy_path,
        profiles_path=args.profiles,
        experimental=experimental,
        role=args.role,
        qc_status=args.qc_status,
        host_filter_status=args.host_filter_status,
    )
    _write_json(args.out, resolved)


def _cmd_get(args: argparse.Namespace) -> None:
    with open(args.in_, "r", encoding="utf-8", errors="strict") as handle:
        data = json.load(handle)
    value = data
    for part in args.field.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(args.field)
        value = value[part]
    if isinstance(value, bool):
        print("true" if value else "false")
    else:
        print(value)


def _cmd_emit_shell(args: argparse.Namespace) -> None:
    """Print ``NAME='value'`` lines suitable for ``eval`` in bash.

    This is the single read-back call that replaces dozens of individual
    ``python3 ... --field X`` spawns: the shell resolves the whole
    configuration once, then reads every field it needs in one pass.
    """
    import shlex

    with open(args.in_, "r", encoding="utf-8", errors="strict") as handle:
        data = json.load(handle)

    def flatten(prefix: str, value: object) -> list[tuple[str, str]]:
        if isinstance(value, dict):
            pairs = []
            for key, item in value.items():
                pairs.extend(flatten(f"{prefix}_{key}" if prefix else key, item))
            return pairs
        if isinstance(value, bool):
            return [(prefix, "true" if value else "false")]
        return [(prefix, "" if value is None else str(value))]

    for name, value in flatten("", data):
        shell_name = name.upper()
        print(f"{shell_name}={shlex.quote(value)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    pipeline = subparsers.add_parser("pipeline", help="resolve scripts/pipeline/run.sh configuration")
    pipeline.add_argument("--repo-root", required=True)
    pipeline.add_argument("--sample-name", required=True)
    pipeline.add_argument("--analysis-profiles-config")
    pipeline.add_argument("--incoming", action="append", default=[], metavar="NAME=VALUE")
    pipeline.add_argument("--sourced", action="append", default=[], metavar="NAME=VALUE")
    pipeline.add_argument("--cli", action="append", default=[], metavar="NAME=VALUE")
    pipeline.add_argument("--out", required=True)
    pipeline.set_defaults(func=_cmd_pipeline)

    evidence = subparsers.add_parser("evidence", help="resolve scripts/evidence/run.sh policy + thresholds")
    policy_group = evidence.add_mutually_exclusive_group()
    policy_group.add_argument("--activation-policy")
    policy_group.add_argument("--experimental-activation-policy", dest="experimental_activation_policy")
    evidence.add_argument("--profiles")
    evidence.add_argument("--role", required=True)
    evidence.add_argument("--qc-status", required=True)
    evidence.add_argument("--host-filter-status", required=True)
    evidence.add_argument("--out", required=True)
    evidence.set_defaults(func=_cmd_evidence)

    get = subparsers.add_parser("get", help="read one field from a resolved_config.json")
    get.add_argument("--in", dest="in_", required=True)
    get.add_argument("--field", required=True)
    get.set_defaults(func=_cmd_get)

    emit_shell = subparsers.add_parser("emit-shell", help="print NAME='value' lines for eval in bash")
    emit_shell.add_argument("--in", dest="in_", required=True)
    emit_shell.set_defaults(func=_cmd_emit_shell)

    args = parser.parse_args()
    try:
        args.func(args)
    except (ConfigError, ValueError, KeyError, FileNotFoundError) as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
