"""Prompt bandit policy and prompt metadata utilities."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .models import PromptArm


@dataclass
class PromptMaterialization:
    """Rendered prompt ready for use by an agent backend."""

    name: str
    backend: str
    content: str
    generation: int
    checklist: List[str]

    def with_context(self, context: Sequence[str] | str) -> "PromptMaterialization":
        """Return a copy of the prompt augmented with additional context."""

        if isinstance(context, str):
            context_lines = [context]
        else:
            context_lines = [str(item) for item in context]
        if not context_lines:
            return self
        augmented = "\n".join([self.content, "", "Context:", *context_lines])
        return PromptMaterialization(
            name=self.name,
            backend=self.backend,
            content=augmented,
            generation=self.generation,
            checklist=list(self.checklist),
        )


@dataclass
class PromptGenome:
    """Mutable prompt template tracked by the bandit."""

    name: str
    backend: str
    title: str
    instructions: List[str]
    checklist: List[str] = field(default_factory=list)
    temperature: float = 0.7
    generation: int = 0
    history: List[float] = field(default_factory=list)

    def materialise(self) -> PromptMaterialization:
        """Render the prompt with lightweight mutations for diversity."""

        instructions = list(self.instructions)
        random.shuffle(instructions)
        header = [f"backend: {self.backend}", self.title]
        lines: List[str] = header[:]
        for idx, instruction in enumerate(instructions, 1):
            emphasis = 1.0 + (idx * 0.05) + (0.5 - self.temperature)
            lines.append(f"{idx}. ({emphasis:.2f}) {instruction}")
        if self.checklist:
            lines.append("")
            lines.append("Checklist:")
            for item in self.checklist:
                lines.append(f"- {item}")
        content = "\n".join(lines)
        return PromptMaterialization(
            name=self.name,
            backend=self.backend,
            content=content,
            generation=self.generation,
            checklist=list(self.checklist),
        )

    def evolve(self, reward: float) -> None:
        """Update template weights/checklists based on the observed reward."""

        self.history.append(reward)
        self.temperature = min(1.0, max(0.2, self.temperature + 0.2 * (0.5 - reward)))
        if reward < 0.35 and len(self.instructions) > 1:
            rotated = self.instructions.pop(0)
            self.instructions.append(rotated)
        elif reward > 0.75:
            random.shuffle(self.instructions)
        if reward < 0.5:
            failure_note = f"Re-evaluate failure modes (reward={reward:.2f})"
            if failure_note not in self.checklist:
                self.checklist.append(failure_note)
        self.generation += 1

    def to_payload(self) -> Dict[str, Any]:
        """Serialises the genome to JSON-friendly primitives."""

        return {
            "name": self.name,
            "backend": self.backend,
            "title": self.title,
            "instructions": list(self.instructions),
            "checklist": list(self.checklist),
            "temperature": self.temperature,
            "generation": self.generation,
            "history": list(self.history),
        }

    def apply_payload(self, payload: Mapping[str, Any]) -> None:
        """Restores mutable fields from a payload."""

        self.backend = str(payload.get("backend", self.backend))
        self.title = str(payload.get("title", self.title))
        instructions = payload.get("instructions")
        if isinstance(instructions, list):
            self.instructions = [str(item) for item in instructions]
        checklist = payload.get("checklist")
        if isinstance(checklist, list):
            self.checklist = [str(item) for item in checklist]
        try:
            self.temperature = float(payload.get("temperature", self.temperature))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            pass
        try:
            self.generation = int(payload.get("generation", self.generation))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            pass
        history = payload.get("history")
        if isinstance(history, list):
            cleaned: List[float] = []
            for item in history:
                try:
                    cleaned.append(float(item))
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    continue
            self.history = cleaned


class PromptBandit:
    """Implements Thompson sampling over prompt template arms with meta evolution."""

    def __init__(self, arms: Dict[str, PromptArm], templates: Dict[str, PromptGenome]) -> None:
        self.arms = arms
        self.templates = templates

    @classmethod
    def from_directory(cls, directory: str) -> "PromptBandit":
        arms: Dict[str, PromptArm] = {}
        templates: Dict[str, PromptGenome] = {}
        for path in Path(directory).glob("*.md"):
            with open(path, "r", encoding="utf-8") as handle:
                lines = [line.rstrip("\n") for line in handle]
            backend = "flash"
            problem_id = "sample_problem"
            intent = "mutate"
            island: str | None = None
            cursor = 0
            while cursor < len(lines) and ":" in lines[cursor] and not lines[cursor].startswith("-"):
                key, value = lines[cursor].split(":", 1)
                key = key.strip().lower()
                value = value.strip()
                if key == "backend":
                    backend = value or "flash"
                elif key == "problem":
                    problem_id = value or "sample_problem"
                elif key == "intent":
                    intent = value or "mutate"
                elif key == "island":
                    island = value or None
                else:
                    break
                cursor += 1
            title = lines[cursor].strip() if cursor < len(lines) else f"Prompt {path.stem}"
            instructions: List[str] = []
            checklist: List[str] = []
            for raw_line in lines[cursor + 1 :]:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                if stripped.lower().startswith("checklist:"):
                    continue
                if stripped.startswith("-"):
                    instructions.append(stripped.lstrip("- "))
                elif stripped.startswith("*"):
                    checklist.append(stripped.lstrip("* "))
                else:
                    instructions.append(stripped)
            if not checklist:
                checklist = [f"Report metrics for {path.stem}"]
            name = path.stem
            arms[name] = PromptArm(name=name, template_path=str(path))
            arms[name].problem_id = problem_id
            arms[name].intent = intent
            arms[name].island = island
            templates[name] = PromptGenome(
                name=name,
                backend=backend,
                title=title,
                instructions=instructions or ["Use EVOLVE-BLOCK mutations"],
                checklist=checklist,
            )
        if not arms:
            raise ValueError(f"No prompt templates found in {directory}")
        return cls(arms=arms, templates=templates)

    def pick_prompt(
        self,
        *,
        intent: str = "mutate",
        problem_id: str | None = None,
        exclude_island: str | None = None,
        prefer_island: str | None = None,
    ) -> Tuple[str, PromptMaterialization]:
        candidates = [
            (name, arm)
            for name, arm in self.arms.items()
            if arm.intent == intent
            and (problem_id is None or arm.problem_id in {problem_id, "*"})
        ]
        if exclude_island:
            filtered = [item for item in candidates if item[1].island != exclude_island]
            if filtered:
                candidates = filtered
        if prefer_island:
            preferred = [item for item in candidates if item[1].island == prefer_island]
            if preferred:
                candidates = preferred
        if not candidates:
            if intent != "mutate":
                raise ValueError(f"No prompt arms available for intent {intent}")
            candidates = list(self.arms.items())
        scored = {
            name: random.betavariate(arm.successes, arm.failures)
            for name, arm in candidates
        }
        chosen_name = max(scored, key=lambda candidate: scored[candidate])
        materialised = self.templates[chosen_name].materialise()
        return chosen_name, materialised

    def backend_for_arm(self, arm_name: str) -> str:
        template = self.templates.get(arm_name)
        if template:
            return template.backend
        return "flash"

    def update_reward(self, arm_name: str, reward: float) -> None:
        arm = self.arms.get(arm_name)
        if not arm:
            return
        clipped = max(0.0, min(1.0, reward))
        decay = max(0.0, (arm.horizon_generations - 1) / max(arm.horizon_generations, 1))
        arm.successes = 1.0 + decay * (arm.successes - 1.0) + clipped
        arm.failures = 1.0 + decay * (arm.failures - 1.0) + (1.0 - clipped)
        arm.recent_reward = clipped
        if arm_name in self.templates:
            self.templates[arm_name].evolve(clipped)

    def ingest_feedback(self, arm_name: str, failure_tags: Iterable[str]) -> None:
        template = self.templates.get(arm_name)
        if not template:
            return
        for tag in failure_tags:
            note = f"Investigate {tag}"
            if note not in template.checklist:
                template.checklist.append(note)

    def island_for_arm(self, arm_name: str) -> str | None:
        arm = self.arms.get(arm_name)
        return arm.island if arm else None

    def problem_for_arm(self, arm_name: str) -> str | None:
        arm = self.arms.get(arm_name)
        return arm.problem_id if arm else None

    def snapshot(self) -> Dict[str, Any]:
        """Returns a JSON-serialisable snapshot of the bandit state."""

        arms_payload = {
            name: {
                "name": arm.name,
                "template_path": arm.template_path,
                "problem_id": arm.problem_id,
                "intent": arm.intent,
                "island": arm.island,
                "successes": arm.successes,
                "failures": arm.failures,
                "recent_reward": arm.recent_reward,
                "horizon_generations": arm.horizon_generations,
            }
            for name, arm in self.arms.items()
        }
        templates_payload = {
            name: genome.to_payload() for name, genome in self.templates.items()
        }
        return {
            "arms": arms_payload,
            "templates": templates_payload,
        }

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        """Restores bandit state from a snapshot payload."""

        arms_payload = snapshot.get("arms", {})
        if isinstance(arms_payload, Mapping):
            for name, payload in arms_payload.items():
                if not isinstance(payload, Mapping):
                    continue
                arm = self.arms.get(name)
                if arm is None:
                    arm = PromptArm(name=name, template_path=str(payload.get("template_path", "")))
                    self.arms[name] = arm
                arm.problem_id = str(payload.get("problem_id", arm.problem_id))
                arm.intent = str(payload.get("intent", arm.intent))
                island_value = payload.get("island")
                arm.island = str(island_value) if island_value is not None else None
                try:
                    arm.successes = float(payload.get("successes", arm.successes))
                    arm.failures = float(payload.get("failures", arm.failures))
                    arm.recent_reward = float(payload.get("recent_reward", arm.recent_reward))
                    arm.horizon_generations = int(payload.get("horizon_generations", arm.horizon_generations))
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    continue
        templates_payload = snapshot.get("templates", {})
        if isinstance(templates_payload, Mapping):
            for name, payload in templates_payload.items():
                if not isinstance(payload, Mapping):
                    continue
                genome = self.templates.get(name)
                if genome is None:
                    backend = str(payload.get("backend", "flash"))
                    title = str(payload.get("title", f"Prompt {name}"))
                    instructions = payload.get("instructions")
                    if isinstance(instructions, list) and instructions:
                        inst = [str(item) for item in instructions]
                    else:
                        inst = ["Use EVOLVE-BLOCK mutations"]
                    checklist = payload.get("checklist")
                    if isinstance(checklist, list):
                        check = [str(item) for item in checklist]
                    else:
                        check = [f"Report metrics for {name}"]
                    genome = PromptGenome(
                        name=name,
                        backend=backend,
                        title=title,
                        instructions=inst,
                        checklist=check,
                    )
                    self.templates[name] = genome
                genome.apply_payload(payload)

    def telemetry(self) -> Dict[str, Any]:
        """Returns a structured view of bandit arm performance."""

        arms = {
            name: {
                "problem_id": arm.problem_id,
                "intent": arm.intent,
                "island": arm.island,
                "successes": arm.successes,
                "failures": arm.failures,
                "recent_reward": arm.recent_reward,
                "temperature": self.templates[name].temperature
                if name in self.templates
                else None,
            }
            for name, arm in self.arms.items()
        }
        templates = {
            name: {
                "generation": genome.generation,
                "history": list(genome.history),
                "checklist": list(genome.checklist),
            }
            for name, genome in self.templates.items()
        }
        return {"arms": arms, "templates": templates}

    def export_telemetry(self, output_path: Path) -> None:
        """Writes telemetry to disk for dashboards or analytics."""

        payload = self.telemetry()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
