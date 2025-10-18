"""Utilities for loading problem configuration metadata."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class ProblemSpec:
    problem_id: str
    package: str
    baseline_path: Path


def load_problem_specs(config_path: Path) -> Dict[str, ProblemSpec]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    problems = data.get("problems", [])
    specs: Dict[str, ProblemSpec] = {}
    for entry in problems:
        if not isinstance(entry, dict):
            continue
        problem_id = str(entry.get("id", "")).strip()
        package = str(entry.get("package", "")).strip()
        baseline = entry.get("baseline")
        if not problem_id or not package or not baseline:
            continue
        baseline_path = Path(baseline)
        if not baseline_path.is_absolute():
            candidate = (config_path.parent / baseline_path).resolve()
            if candidate.exists():
                baseline_path = candidate
            else:
                baseline_path = (config_path.parent.parent / baseline_path).resolve()
        specs[problem_id] = ProblemSpec(
            problem_id=problem_id,
            package=package,
            baseline_path=baseline_path,
        )
    if not specs:
        raise ValueError(f"No problem specifications found in {config_path}")
    return specs
