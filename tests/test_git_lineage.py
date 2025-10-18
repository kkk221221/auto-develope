import json
from pathlib import Path

from orchestrator.git_lineage import GitLineageTracker
from orchestrator.models import ProgramCandidate


def _make_candidate(tmp_path: Path) -> ProgramCandidate:
    source_path = tmp_path / "candidate.py"
    source_path.write_text("print('hello')\n", encoding="utf-8")
    return ProgramCandidate(
        id="candidate-1",
        parents=(),
        generation=0,
        prompt_arm="mutate.test",
        llm_backend="flash",
        patch_payload={"diff_type": "sr", "payload": "print('hello')"},
        problem_id="sample_problem",
        source_path=str(source_path),
    )


def test_git_lineage_tracker_records_candidate(tmp_path: Path) -> None:
    repo = tmp_path / "lineage"
    tracker = GitLineageTracker(repo)
    candidate = _make_candidate(tmp_path)

    commit = tracker.record_candidate(candidate)

    assert commit
    index_path = repo / ".lineage_index.json"
    assert index_path.exists()
    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    assert index_data[candidate.id] == commit

    metadata_path = repo / ".lineage" / f"{candidate.id}.json"
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["candidate_id"] == candidate.id


def test_git_lineage_tracker_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "lineage"
    tracker = GitLineageTracker(repo)
    candidate = _make_candidate(tmp_path)

    first = tracker.record_candidate(candidate)
    second = tracker.record_candidate(candidate)

    assert first == second
