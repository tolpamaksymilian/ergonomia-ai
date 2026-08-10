"""Deterministic candidate ranking without learned models."""

from __future__ import annotations

from ..schemas import CandidatePosture


def ranking_score(candidate: CandidatePosture) -> float:
    return (
        candidate.severity * 0.50
        + min(candidate.duration_context_seconds / 5.0, 1.0) * 0.20
        + candidate.quality * 0.25
        + min(candidate.frequency / 5.0, 1.0) * 0.05
    )


def rank_candidates(candidates: list[CandidatePosture]) -> list[CandidatePosture]:
    return sorted(
        candidates,
        key=lambda item: (-ranking_score(item), item.timestamp_seconds, item.frame_position),
    )
