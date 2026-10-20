"""Map Validation optimization parameters to Gene-In pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass


STAGE_ORDER = (
    "initial_blast",
    "locus_building",
    "hsp_aggregation",
    "competitive_search",
    "evidence_classification",
)


@dataclass(frozen=True)
class ParameterSpec:
    parameter: str
    stage: str
    consumer: str
    rerun_from: str
    connected_in_pipeline: bool
    contract_effect: str


PARAMETER_REGISTRY: dict[str, ParameterSpec] = {
    "blast.dual_mode_max_bp": ParameterSpec(
        parameter="blast.dual_mode_max_bp",
        stage="initial_blast",
        consumer="scripts/evidence/blast_router.py:profiles_for_length",
        rerun_from="initial_blast",
        connected_in_pipeline=True,
        contract_effect="blast_routing",
    ),
    "blast.short_max_bp": ParameterSpec(
        parameter="blast.short_max_bp",
        stage="initial_blast",
        consumer="scripts/evidence/blast_router.py:profiles_for_length",
        rerun_from="initial_blast",
        connected_in_pipeline=True,
        contract_effect="blast_routing",
    ),
    "blast.dual_mode_min_bp": ParameterSpec(
        parameter="blast.dual_mode_min_bp",
        stage="initial_blast",
        consumer="scripts/evidence/blast_router.py:profiles_for_length",
        rerun_from="initial_blast",
        connected_in_pipeline=True,
        contract_effect="blast_routing",
    ),
    "specificity.minimum_delta_bitscore": ParameterSpec(
        parameter="specificity.minimum_delta_bitscore",
        stage="competitive_search",
        consumer="scripts/evidence/competitive_hits.py:evaluate",
        rerun_from="competitive_search",
        connected_in_pipeline=True,
        contract_effect="competitive_specificity",
    ),
    "specificity.maximum_qcov_difference_pp": ParameterSpec(
        parameter="specificity.maximum_qcov_difference_pp",
        stage="competitive_search",
        consumer="scripts/evidence/competitive_hits.py:evaluate",
        rerun_from="competitive_search",
        connected_in_pipeline=True,
        contract_effect="competitive_specificity",
    ),
    "locus.minimum_candidate_bp": ParameterSpec(
        parameter="locus.minimum_candidate_bp",
        stage="evidence_classification",
        consumer="scripts/evidence/classify_sample.py:classify",
        rerun_from="evidence_classification",
        connected_in_pipeline=True,
        contract_effect="classification_gates",
    ),
    "locus.gap_bp": ParameterSpec(
        parameter="locus.gap_bp",
        stage="locus_building",
        consumer="scripts/evidence/build_loci.py",
        rerun_from="locus_building",
        connected_in_pipeline=True,
        contract_effect="locus_grouping",
    ),
    "support.minimum_mapq": ParameterSpec(
        parameter="support.minimum_mapq",
        stage="read_remapping",
        consumer="scripts/evidence/map_read_support.sh",
        rerun_from="read_remapping",
        connected_in_pipeline=False,
        contract_effect="none_without_reads",
    ),
    "support.minimum_unique_templates": ParameterSpec(
        parameter="support.minimum_unique_templates",
        stage="read_remapping",
        consumer="scripts/evidence/classify_sample.py:support_passes",
        rerun_from="read_remapping",
        connected_in_pipeline=False,
        contract_effect="none_without_reads",
    ),
}


BLAST_PARAM_KEYS = (
    "blast.short_max_bp",
    "blast.dual_mode_min_bp",
    "blast.dual_mode_max_bp",
)


def changed_connected_parameters(parameters: dict, reference: dict | None) -> list[str]:
    if reference is None:
        return [
            key
            for key in parameters
            if key in PARAMETER_REGISTRY and PARAMETER_REGISTRY[key].connected_in_pipeline
        ]
    return [
        key
        for key in parameters
        if key in PARAMETER_REGISTRY
        and PARAMETER_REGISTRY[key].connected_in_pipeline
        and parameters.get(key) != reference.get(key)
    ]


def minimum_rerun_stage(parameters: dict, reference: dict | None = None) -> str:
    """Earliest stage that must rerun given differences versus a reference set.

    Without a reference this is informational only. Runtime reuse uses cache
    keys of upstream artifacts, not this helper, so identical BLAST parameters
    can share BLAST outputs across classification/specificity sweeps.
    """
    changed = changed_connected_parameters(parameters, reference)
    if not changed:
        return "evidence_classification"
    stages = {PARAMETER_REGISTRY[key].rerun_from for key in changed}
    return min(stages, key=lambda item: STAGE_ORDER.index(item))


def contract_active_parameters(parameters: dict, baseline: dict) -> dict[str, str]:
    active: dict[str, str] = {}
    for key, spec in PARAMETER_REGISTRY.items():
        if parameters.get(key) != baseline.get(key):
            active[key] = spec.contract_effect
    return active
