from pathlib import Path

from orchestrator.dashboard import render_map_elites_dashboard
from orchestrator.models import BehaviorFeatures, Metrics, ProgramCandidate


def test_dashboard_render(tmp_path: Path) -> None:
    candidate = ProgramCandidate(
        id="cand1234",
        parents=(),
        generation=0,
        prompt_arm="mutate.perf_first",
        llm_backend="flash",
        patch_payload={},
        problem_id="sample_problem",
        source_path=str(tmp_path / "dummy.py"),
    )
    candidate.metrics = Metrics(accuracy=0.9, runtime_ms=42.0, robustness=0.8, loc=120)
    candidate.behavior = BehaviorFeatures(coverage_bits=(1, 2), hotspots={}, output_signature="sig")

    snapshot = {
        "state": {
            "pareto_front": [candidate.id],
            "map_elites_cells": {"0,0": candidate.id},
        }
    }
    output = tmp_path / "dashboard.html"

    render_map_elites_dashboard(
        snapshot,
        {candidate.id: candidate},
        complexity_bins=2,
        robustness_bins=2,
        output_path=output,
    )

    assert output.exists()
    contents = output.read_text(encoding="utf-8")
    assert "AutoEvolve Observatory" in contents
    assert candidate.id[:8] in contents
