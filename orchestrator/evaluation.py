"""Evaluation helpers for executing tier cascades on candidate programs."""
from __future__ import annotations

import ast
import importlib
import importlib.util
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from types import ModuleType
from typing import Dict, Iterable, List, Optional

from .models import EvaluationResult, Metrics, ProgramCandidate


@dataclass
class TierSpec:
    name: str
    timeout_s: int
    checks: List[str]
    tests: List[str]
    repeats: int = 1
    percentiles: Optional[List[float]] = None
    stress_suites: Optional[List[str]] = None


class ProblemEvaluator:
    """Executes problem-specific evaluations for a candidate program."""

    def __init__(self, problem_package: str) -> None:
        self.problem_package = problem_package
        self._data_gen = importlib.import_module(f"{problem_package}.data_gen")
        self._oracle = importlib.import_module(f"{problem_package}.oracle")

    def evaluate(
        self,
        candidate: ProgramCandidate,
        dataset_size: int,
        stress: bool = False,
        repeats: int = 1,
    ) -> Metrics:
        scores: List[float] = []
        runtimes: List[float] = []
        for _ in range(repeats):
            samples = self._data_gen.generate_samples(dataset_size)
            start = perf_counter()
            candidate_score = self._execute_solver(candidate.source_path, samples)
            runtime_ms = (perf_counter() - start) * 1000
            reference_score = self._oracle.evaluate_solution(samples)
            scores.append(self._score_accuracy(candidate_score, reference_score))
            runtimes.append(runtime_ms)

        accuracy = statistics.fmean(scores)
        runtime_ms = statistics.fmean(runtimes)
        robustness = self._measure_robustness(candidate)
        loc = self._count_loc(candidate.source_path)
        cyclomatic = self._estimate_cyclomatic(candidate.source_path)
        llm_style = self._estimate_style(candidate.source_path)
        memory_peak = max(runtimes) / 100.0 if runtimes else 0.0

        if stress:
            stress_samples = [(0, 0), (1000, -999), (-500, 250), (1, 1)]
            try:
                stress_output = self._execute_solver(candidate.source_path, stress_samples)
                stress_ref = self._oracle.evaluate_solution(stress_samples)
                stress_score = self._score_accuracy(stress_output, stress_ref)
            except Exception:  # pragma: no cover - defensive
                stress_score = 0.0
            robustness = (robustness + stress_score) / 2.0

        return Metrics(
            accuracy=accuracy,
            runtime_ms=runtime_ms,
            memory_peak_mb=memory_peak,
            loc=loc,
            cyclomatic=cyclomatic,
            robustness=robustness,
            llm_style=llm_style,
        )

    def _execute_solver(self, source_path: str, samples: Iterable) -> float:
        module = self._load_module(source_path)
        if not hasattr(module, "solve"):
            raise AttributeError("Candidate module must define solve()")
        solve = getattr(module, "solve")
        return float(solve(samples))

    def _load_module(self, source_path: str) -> ModuleType:
        module_name = f"candidate_{Path(source_path).stem}_{hash(source_path) & 0xFFFF:x}"
        spec = importlib.util.spec_from_file_location(module_name, source_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load candidate module from {source_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def _score_accuracy(self, candidate_score: float, reference_score: float) -> float:
        denom = max(abs(reference_score), 1.0)
        delta = abs(candidate_score - reference_score) / denom
        return max(0.0, 1.0 - delta)

    def _measure_robustness(self, candidate: ProgramCandidate) -> float:
        samples: List = [(1, 2), (3, 4), (0, 0)]
        try:
            _ = self._execute_solver(candidate.source_path, samples)
            _ = self._execute_solver(candidate.source_path, [])
        except Exception:
            return 0.0
        return 1.0

    def _count_loc(self, source_path: str) -> int:
        source = Path(source_path).read_text(encoding="utf-8")
        return sum(1 for line in source.splitlines() if line.strip() and not line.strip().startswith("#"))

    def _estimate_cyclomatic(self, source_path: str) -> float:
        tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
        complexity = 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.And, ast.Or, ast.Try)):
                complexity += 1
        return float(complexity)

    def _estimate_style(self, source_path: str) -> float:
        source = Path(source_path).read_text(encoding="utf-8")
        avg_len = statistics.fmean(len(line) for line in source.splitlines() if line)
        return max(0.0, min(1.0, 1.2 - avg_len / 120))


class TierExecutor:
    """Runs configured tier actions for candidates and returns evaluation results."""

    def __init__(self, tier_specs: Dict[str, TierSpec], evaluator: ProblemEvaluator) -> None:
        self.tier_specs = tier_specs
        self.evaluator = evaluator

    async def run(self, candidate: ProgramCandidate, tier: str) -> EvaluationResult:
        spec = self.tier_specs[tier]
        checks_passed = await self._run_checks(candidate, spec.checks)
        if not checks_passed:
            return EvaluationResult(
                candidate_id=candidate.id,
                tier=tier,
                passed=False,
                metrics=Metrics(),
            )

        metrics = await self._run_tests(candidate, spec)
        passed = metrics.accuracy >= 0.8
        return EvaluationResult(
            candidate_id=candidate.id,
            tier=tier,
            passed=passed,
            metrics=metrics,
        )

    async def _run_checks(self, candidate: ProgramCandidate, checks: Iterable[str]) -> bool:
        for check in checks:
            if check == "lint" and not await self._lint(candidate):
                return False
            if check == "typecheck" and not await self._typecheck(candidate):
                return False
            if check == "ast_rules" and not await self._ast_rules(candidate):
                return False
        return True

    async def _run_tests(self, candidate: ProgramCandidate, spec: TierSpec) -> Metrics:
        dataset_size = 8 if spec.name == "L1" else 32
        repeats = spec.repeats or 1
        stress = bool(spec.stress_suites)
        return self.evaluator.evaluate(candidate, dataset_size=dataset_size, repeats=repeats, stress=stress)

    async def _lint(self, candidate: ProgramCandidate) -> bool:
        try:
            compile(Path(candidate.source_path).read_text(encoding="utf-8"), candidate.source_path, "exec")
        except SyntaxError:
            return False
        return True

    async def _typecheck(self, candidate: ProgramCandidate) -> bool:
        tree = ast.parse(Path(candidate.source_path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "solve":
                if not node.returns:
                    return False
        return True

    async def _ast_rules(self, candidate: ProgramCandidate) -> bool:
        banned = {"os", "subprocess"}
        tree = ast.parse(Path(candidate.source_path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name.split(".")[0] in banned for alias in node.names):
                    return False
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in banned:
                    return False
        return True


def load_tier_specs(config_path: Path) -> Dict[str, TierSpec]:
    raw: Dict[str, Dict[str, object]] = {}
    current: Optional[str] = None
    with open(config_path, "r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not line.startswith(" "):
                if not stripped.endswith(":"):
                    raise ValueError(f"Invalid tier definition line: {line}")
                current = stripped[:-1]
                raw[current] = {}
            else:
                if current is None:
                    raise ValueError("Encountered property before tier declaration")
                key, value = stripped.split(":", 1)
                value = value.strip()
                if value.startswith("[") and value.endswith("]"):
                    inner = value[1:-1].strip()
                    if inner:
                        parsed_value = [item.strip().strip('"') for item in inner.split(",")]
                    else:
                        parsed_value = []
                elif value.lower() in {"true", "false"}:
                    parsed_value = value.lower() == "true"
                elif value.isdigit():
                    parsed_value = int(value)
                else:
                    parsed_value = value.strip('"')
                raw[current][key] = parsed_value

    specs: Dict[str, TierSpec] = {}
    for name, payload in raw.items():
        specs[name] = TierSpec(
            name=name,
            timeout_s=int(payload.get("timeout_s", 60)),
            checks=list(payload.get("checks", [])),
            tests=list(payload.get("tests", [])),
            repeats=int(payload.get("repeats", 1)),
            percentiles=payload.get("percentiles"),
            stress_suites=payload.get("stress_suites"),
        )
    return specs

