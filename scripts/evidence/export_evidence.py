#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .activation_policy import (
        load_experimental_activation_policy,
        load_public_activation_policy,
    )
    from .common import write_text_atomic
    from .evidence_contract import evidence_label, promote_for_public_output, public_review_label
except ImportError:
    from activation_policy import (
        load_experimental_activation_policy,
        load_public_activation_policy,
    )
    from common import write_text_atomic
    from evidence_contract import evidence_label, promote_for_public_output, public_review_label


def _load_policy(args: argparse.Namespace) -> dict | None:
    """Resolve --activation-policy/--experimental-activation-policy, if given.

    Both public and experimental policies validate identically (Astra: the
    same technical completion path for experiments and public runs); the
    only difference is which record is authoritative for this export. When
    neither flag is given, ``None`` preserves the historical default of
    validating against the active public policy.
    """
    if getattr(args, "experimental_activation_policy", None):
        return load_experimental_activation_policy(
            args.experimental_activation_policy, profiles_path=args.profiles,
        )
    if getattr(args, "activation_policy", None):
        return load_public_activation_policy(args.activation_policy, profiles_path=args.profiles)
    return None


def render(
    data: dict,
    *,
    validated: bool = False,
    compatibility_mode: str | None = None,
    run_dir=None,
) -> str:
    if not validated:
        data = promote_for_public_output(data, compatibility_mode=compatibility_mode)
    if isinstance(data.get("samples"), list):
        raise ValueError("batch evidence must be rendered by summarize_batch.py")
    specificity = data["specificity"].get("status", "NOT_EVALUATED")
    coverage = data["coverage"].get("status", "NOT_EVALUATED")
    controls = data["controls"].get("status", "NOT_EVALUATED")
    candidates = data.get("candidates", [])
    caveats = list(data["caveats"])
    if candidates:
        caveats.insert(0, "As sequências estão disponíveis para triagem humana; recuperação não confirma origem viral nem espécie.")
    caveat_lines = "\n".join(f"- {item}" for item in dict.fromkeys(caveats)) or "- Nenhuma."
    candidate_lines = "\n".join(
        f"- `{item.get('candidate_id', '')}` — referência `{item.get('reference_id', '')}`, "
        f"categoria `{item.get('category', '')}`, locus `{item.get('locus_id', '')}`, "
        f"classe `{item.get('candidate_class', 'NOT_EVALUATED')}`"
        for item in candidates
    ) or "- Nenhum candidato recuperado nas condições avaliadas."
    mode_notice = "**ANÁLISE:** resultados calculados com os parâmetros configurados."
    details = ""
    detailed_artifacts = False
    if run_dir is not None:
        run_path = Path(run_dir)
        detailed_artifacts = any(
            (run_path / name).is_file()
            for name in ("fragment_evidence.tsv", "locus_evidence.tsv", "hsp_evidence.tsv")
        )
        try:
            from .report_details import render_details
        except ImportError:
            from report_details import render_details
        if detailed_artifacts:
            details = render_details(run_path, data)
    candidate_section = (
        f"## Candidatos medidos\n\n{candidate_lines}"
        if not detailed_artifacts
        else "## Candidatos\n\nOs candidatos recuperados e suas métricas aparecem na tabela por locus abaixo."
    )
    return f"""# Gene-In 2.0 — relatório de evidência — {data['sample_id']}

> {mode_notice}

## Estado público

| Dimensão | Valor |
|---|---|
| Run ID | `{data['run_id']}` |
| Execução | `{data['execution_status']}` |
| Resultado da análise | `{public_review_label(data['analysis_outcome'])}` |
| Recuperação | {evidence_label(data)} |
| Rótulo para revisão | `{public_review_label(data['evidence_level'])}` (não representa confirmação viral) |
| Especificidade no painel | `{specificity}` |
| Cobertura | `{coverage}` |
| Controles | `{controls}` |

{candidate_section}

## Observações técnicas

{caveat_lines}

{details}

"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an evidence report")
    parser.add_argument("--json", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--compatibility-mode",
        choices=["explicit_legacy_adaptation"],
    )
    policy_group = parser.add_mutually_exclusive_group()
    policy_group.add_argument("--activation-policy")
    policy_group.add_argument("--experimental-activation-policy")
    parser.add_argument("--profiles")
    args = parser.parse_args()
    policy = _load_policy(args)
    with open(args.json, "r", encoding="utf-8", errors="strict") as handle:
        data = promote_for_public_output(
            json.load(handle), policy=policy, compatibility_mode=args.compatibility_mode,
        )
    write_text_atomic(args.out, render(data, validated=True, run_dir=Path(args.json).resolve().parent))


if __name__ == "__main__":
    main()
