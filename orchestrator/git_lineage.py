"""Utilities for syncing candidate lineage information to a Git repository."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Mapping

from .models import ProgramCandidate


class GitLineageError(RuntimeError):
    """Raised when lineage synchronisation fails."""


class GitLineageTracker:
    """Writes candidate sources and metadata to a Git repository for auditing."""

    def __init__(self, repo_root: Path, *, configure_user: bool = True) -> None:
        self.repo_root = repo_root
        self.repo_root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.repo_root / ".lineage_index.json"
        self.metadata_dir = self.repo_root / ".lineage"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self._commit_index: Dict[str, str] = {}
        self._ensure_repo(configure_user=configure_user)
        self._load_index()

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            check=check,
            text=True,
            capture_output=True,
        )

    def _ensure_repo(self, *, configure_user: bool) -> None:
        git_dir = self.repo_root / ".git"
        if not git_dir.exists():
            self._run_git("init")
        if configure_user:
            # Configure committer identity if not already configured. Failure is non-fatal.
            for key, value in {
                "user.email": "lineage@example.com",
                "user.name": "AutoEvolve Lineage",
            }.items():
                try:
                    self._run_git("config", key, value)
                except subprocess.CalledProcessError:  # pragma: no cover - defensive
                    continue

    def _load_index(self) -> None:
        if not self.index_path.exists():
            self._commit_index = {}
            return
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:  # pragma: no cover - defensive
            payload = {}
        if isinstance(payload, Mapping):
            self._commit_index = {str(k): str(v) for k, v in payload.items()}
        else:  # pragma: no cover - defensive
            self._commit_index = {}

    def _persist_index(self) -> None:
        self.index_path.write_text(json.dumps(self._commit_index, indent=2), encoding="utf-8")

    def _checkout_branch(self, branch: str) -> None:
        result = self._run_git("rev-parse", "--verify", branch, check=False)
        if result.returncode == 0:
            self._run_git("checkout", branch)
        else:
            self._run_git("checkout", "-b", branch)

    def _stage_path(self, path: Path) -> None:
        relative = path.relative_to(self.repo_root)
        self._run_git("add", str(relative))

    def record_candidate(self, candidate: ProgramCandidate) -> str:
        """Copies candidate artefacts into the Git repo and commits them."""

        if candidate.id in self._commit_index:
            return self._commit_index[candidate.id]

        branch = f"problem-{candidate.problem_id}"
        self._checkout_branch(branch)

        source_path = Path(candidate.source_path)
        if not source_path.exists():
            raise GitLineageError(f"Candidate source missing: {candidate.source_path}")

        target_dir = self.repo_root / candidate.problem_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / source_path.name
        shutil.copy2(source_path, target_path)

        metadata = {
            "candidate_id": candidate.id,
            "parents": list(candidate.parents),
            "prompt_arm": candidate.prompt_arm,
            "problem_id": candidate.problem_id,
            "patch_payload": candidate.patch_payload,
            "generation": candidate.generation,
        }
        metadata_path = self.metadata_dir / f"{candidate.id}.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        self._stage_path(target_path)
        self._stage_path(metadata_path)

        status = self._run_git("status", "--porcelain")
        if not status.stdout.strip():
            # Nothing changed; reuse HEAD commit.
            commit = self._run_git("rev-parse", "HEAD").stdout.strip()
        else:
            message = f"{candidate.problem_id}: candidate {candidate.id}"
            self._run_git("commit", "-m", message)
            commit = self._run_git("rev-parse", "HEAD").stdout.strip()

        self._commit_index[candidate.id] = commit
        self._persist_index()
        return commit

