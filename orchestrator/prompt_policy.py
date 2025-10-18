"""Prompt bandit policy and prompt metadata utilities."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .models import PromptArm


@dataclass
class PromptMaterialization:
    """Rendered prompt ready for use by an agent backend."""

    name: str
    backend: str
    content: str
    generation: int
    checklist: List[str]


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
            cursor = 0
            if lines and lines[0].startswith("backend:"):
                backend = lines[0].split(":", 1)[1].strip() or "flash"
                cursor = 1
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

    def pick_prompt(self) -> Tuple[str, PromptMaterialization]:
        scored = {
            name: random.betavariate(arm.successes, arm.failures)
            for name, arm in self.arms.items()
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
        arm = self.arms[arm_name]
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
