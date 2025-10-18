"""Prompt bandit policy and prompt metadata utilities."""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from .models import PromptArm


@dataclass
class PromptTemplate:
    name: str
    backend: str
    content: str


class PromptBandit:
    """Implements Thompson sampling over prompt template arms."""

    def __init__(self, arms: Dict[str, PromptArm], templates: Dict[str, PromptTemplate]) -> None:
        self.arms = arms
        self.templates = templates

    @classmethod
    def from_directory(cls, directory: str) -> "PromptBandit":
        arms: Dict[str, PromptArm] = {}
        templates: Dict[str, PromptTemplate] = {}
        for path in Path(directory).glob("*.md"):
            with open(path, "r", encoding="utf-8") as handle:
                header = handle.readline().strip()
                backend = "flash"
                if header.startswith("backend:"):
                    backend = header.split(":", 1)[1].strip()
                content = header + "\n" + handle.read()
            name = path.stem
            arms[name] = PromptArm(name=name, template_path=str(path))
            templates[name] = PromptTemplate(name=name, backend=backend, content=content)
        if not arms:
            raise ValueError(f"No prompt templates found in {directory}")
        return cls(arms=arms, templates=templates)

    def pick_prompt(self) -> Tuple[str, PromptTemplate]:
        scored = {
            name: random.betavariate(arm.successes, arm.failures)
            for name, arm in self.arms.items()
        }
        chosen_name = max(scored, key=scored.get)
        return chosen_name, self.templates[chosen_name]

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
