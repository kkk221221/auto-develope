"""Utilities for extracting behavioral descriptors from evaluation outputs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import BehaviorFeatures, EvaluationResult


@dataclass(frozen=True)
class BehaviorExtractorConfig:
    coverage_length: int = 0


def extract_behavior_features(result: EvaluationResult) -> BehaviorFeatures:
    """Derives behavior features using available evaluation artifacts."""

    coverage_bits: Iterable[int]
    if result.behavior:
        return result.behavior

    coverage_bits = []
    if result.metrics.loc:
        coverage_bits = [min(result.metrics.loc, 64)]

    hotspots = {"main": result.metrics.runtime_ms}
    output_signature = f"acc:{result.metrics.accuracy:.3f}/rob:{result.metrics.robustness:.3f}"
    return BehaviorFeatures(
        coverage_bits=tuple(coverage_bits),
        hotspots=hotspots,
        output_signature=output_signature,
    )

