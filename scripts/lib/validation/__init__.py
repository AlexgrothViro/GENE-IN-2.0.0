"""Validation harness: engineering, scientific-optimization and contract-selftest tracks."""

from .tracks import TRACKS, TrackSpec, resolve_tracks

__all__ = ["TRACKS", "TrackSpec", "resolve_tracks"]
