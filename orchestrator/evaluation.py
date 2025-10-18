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
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from .models import BehaviorFeatures, EvaluationResult, Metrics, ProgramCandidate


@dataclass
class TierSpec:
    name: str
    timeout_s: int
    checks: List[str]
    tests: List[str]
    repeats: int = 1
    percentiles: Optional[List[float]] = None
    stress_suites: Optional[List[str]] = None
    max_cyclomatic: Optional[int] = None
    max_runtime_ms: Optional[float] = None


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
        percentiles: Optional[Sequence[float]] = None,
        stress_suites: Optional[Sequence[str]] = None,
    ) -> tuple[Metrics, BehaviorFeatures]:
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
            stress_scores = self._run_stress_suites(
                candidate,
                suites=list(stress_suites or []),
            )
            if stress_scores:
                robustness = (robustness + statistics.fmean(stress_scores)) / 2.0

        metrics = Metrics(
            accuracy=accuracy,
            runtime_ms=runtime_ms,
            memory_peak_mb=memory_peak,
            loc=loc,
            cyclomatic=cyclomatic,
            robustness=robustness,
            llm_style=llm_style,
        )
        hotspots: Dict[str, float] = {"runtime_mean": runtime_ms}
        runtime_percentiles = self._runtime_percentiles(runtimes, percentiles)
        hotspots.update(runtime_percentiles)
        coverage_bits = tuple(sorted({dataset_size, loc, int(cyclomatic)}))
        behavior = BehaviorFeatures(
            coverage_bits=coverage_bits,
            hotspots=hotspots,
            output_signature=f"acc:{accuracy:.3f}/rob:{robustness:.3f}",
        )
        return metrics, behavior

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

    def _run_stress_suites(
        self,
        candidate: ProgramCandidate,
        suites: Sequence[str],
    ) -> List[float]:
        scores: List[float] = []
        for suite in suites:
            dataset = self._stress_samples_for_suite(suite)
            if not dataset:
                continue
            try:
                output = self._execute_solver(candidate.source_path, dataset)
                reference = self._oracle.evaluate_solution(dataset)
                scores.append(self._score_accuracy(output, reference))
            except Exception:  # pragma: no cover - defensive
                scores.append(0.0)
        return scores

    def _stress_samples_for_suite(self, suite: str) -> List:
        if hasattr(self._data_gen, "generate_stress_samples"):
            base = self._data_gen.generate_stress_samples()
        else:  # pragma: no cover - fallback path
            base = [(0, 0), (1000, -999), (-500, 250), (1, 1)]
        if suite.startswith("adversarial") and hasattr(self._data_gen, "generate_adversarial_samples"):
            return self._data_gen.generate_adversarial_samples()
        if suite.startswith("noisy") and hasattr(self._data_gen, "generate_noisy_samples"):
            return self._data_gen.generate_noisy_samples()
        return base

    def _runtime_percentiles(
        self, runtimes: Sequence[float], percentiles: Optional[Sequence[float]]
    ) -> Dict[str, float]:
        if not runtimes or not percentiles:
            return {}
        sorted_runtimes = sorted(runtimes)
        values: Dict[str, float] = {}
        for percentile in percentiles:
            pct = max(0.0, min(1.0, float(percentile)))
            index = int(round((len(sorted_runtimes) - 1) * pct))
            label = f"runtime_p{int(pct * 100):02d}"
            values[label] = sorted_runtimes[index]
        return values

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

        metrics, behavior = await self._run_tests(candidate, spec)
        passed = metrics.accuracy >= 0.8
        if spec.max_cyclomatic and metrics.cyclomatic > spec.max_cyclomatic:
            passed = False
        if spec.max_runtime_ms and metrics.runtime_ms > spec.max_runtime_ms:
            passed = False
        return EvaluationResult(
            candidate_id=candidate.id,
            tier=tier,
            passed=passed,
            metrics=metrics,
            behavior=behavior,
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

    async def _run_tests(self, candidate: ProgramCandidate, spec: TierSpec) -> tuple[Metrics, BehaviorFeatures]:
        dataset_size = self._dataset_size_for_tier(spec.name)
        repeats = spec.repeats or 1
        stress = bool(spec.stress_suites)
        return self.evaluator.evaluate(
            candidate,
            dataset_size=dataset_size,
            repeats=repeats,
            stress=stress,
            percentiles=spec.percentiles,
            stress_suites=spec.stress_suites,
        )

    def _dataset_size_for_tier(self, tier: str) -> int:
        mapping = {"L0": 4, "L1": 16, "L2": 128, "L3": 256}
        return mapping.get(tier, 32)

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
                parsed_value: object
                if value.startswith("[") and value.endswith("]"):
                    inner = value[1:-1].strip()
                    parsed_items: List[object] = []
                    if inner:
                        for item in inner.split(","):
                            cleaned = item.strip().strip('"')
                            if not cleaned:
                                continue
                            try:
                                parsed_items.append(int(cleaned))
                                continue
                            except ValueError:
                                pass
                            try:
                                parsed_items.append(float(cleaned))
                                continue
                            except ValueError:
                                pass
                            parsed_items.append(cleaned)
                    parsed_value = parsed_items
                elif value.lower() in {"true", "false"}:
                    parsed_value = value.lower() == "true"
                else:
                    stripped = value.strip('"')
                    try:
                        parsed_value = int(stripped)
                    except ValueError:
                        try:
                            parsed_value = float(stripped)
                        except ValueError:
                            parsed_value = stripped
                raw[current][key] = parsed_value

    specs: Dict[str, TierSpec] = {}
    
    def _ensure_list(value: object) -> List[object]:
        if isinstance(value, list):
            return value
        if value is None or value == "":
            return []
        return [value]

    def _to_float_list(values: List[object]) -> List[float]:
        result: List[float] = []
        for item in values:
            if isinstance(item, (int, float)):
                result.append(float(item))
            elif isinstance(item, str):
                try:
                    result.append(float(item))
                except ValueError:
                    continue
        return result

    def _to_str_list(values: List[object]) -> List[str]:
        return [str(item) for item in values]

    def _to_optional_int(value: object) -> Optional[int]:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value:
            try:
                return int(value)
            except ValueError:
                return None
        return None

    def _to_optional_float(value: object) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value:
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _int_with_default(value: object, default: int) -> int:
        candidate = _to_optional_int(value)
        return candidate if candidate is not None else default

    for name, payload in raw.items():
        checks = _to_str_list(_ensure_list(payload.get("checks", [])))
        tests = _to_str_list(_ensure_list(payload.get("tests", [])))
        percentiles = _to_float_list(_ensure_list(payload.get("percentiles", [])))
        stress_suites = _to_str_list(_ensure_list(payload.get("stress_suites", [])))
        specs[name] = TierSpec(
            name=name,
            timeout_s=_int_with_default(payload.get("timeout_s"), 60),
            checks=checks,
            tests=tests,
            repeats=_int_with_default(payload.get("repeats"), 1),
            percentiles=percentiles,
            stress_suites=stress_suites,
            max_cyclomatic=_to_optional_int(payload.get("max_cyclomatic")),
            max_runtime_ms=_to_optional_float(payload.get("max_runtime_ms")),
        )
    return specs

