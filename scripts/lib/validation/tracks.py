"""Validation track registry and resolution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrackSpec:
    track_id: str
    description: str


TRACKS: dict[str, TrackSpec] = {
    "engineering": TrackSpec(
        track_id="engineering",
        description="Unit tests, regressions, fixtures, contracts and dependency checks.",
    ),
    "synthetic": TrackSpec(
        track_id="synthetic",
        description="Deterministic synthetic benchmark matrices and routing contracts.",
    ),
    "competitive": TrackSpec(
        track_id="competitive",
        description="Competitive specificity, margin and control regressions.",
    ),
    "operational": TrackSpec(
        track_id="operational",
        description="Real-tool smoke and E2E checks on controlled synthetic inputs.",
    ),
    "scientific-optimization": TrackSpec(
        track_id="scientific-optimization",
        description="Parameter sweeps using the configured analysis inputs.",
    ),
    "contract-selftest": TrackSpec(
        track_id="contract-selftest",
        description="Contract self-test: evaluates a parameter set against synthetic samples built by evaluate_contract_sample. NOT an independent scientific validation.",
    ),
    "all-safe": TrackSpec(
        track_id="all-safe",
        description="Combined engineering, synthetic, competitive and operational checks.",
    ),
}


def resolve_tracks(requested: list[str]) -> list[TrackSpec]:
    if not requested:
        raise ValueError("At least one track must be requested.")
    resolved: list[TrackSpec] = []
    seen: set[str] = set()
    for name in requested:
        if name not in TRACKS:
            raise ValueError(f"Unknown Validation track: {name}")
        if name == "all-safe":
            for track_id in ("engineering", "synthetic", "competitive", "operational"):
                track = TRACKS[track_id]
                if track.track_id not in seen:
                    resolved.append(track)
                    seen.add(track.track_id)
            continue
        track = TRACKS[name]
        if track.track_id not in seen:
            resolved.append(track)
            seen.add(track.track_id)
    return resolved
