"""HTML dashboard generation for archive and prompt telemetry exports."""
from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, MutableMapping, Sequence

from .models import ProgramCandidate


def render_map_elites_dashboard(
    archive_snapshot: Mapping[str, object],
    candidates: Mapping[str, ProgramCandidate],
    *,
    complexity_bins: int,
    robustness_bins: int,
    output_path: Path,
) -> None:
    """Render a minimal HTML dashboard showing MAP-Elites occupancy and metrics."""

    state = archive_snapshot.get("state", {})
    pareto_front = []
    map_cells: MutableMapping[str, str] = {}
    if isinstance(state, Mapping):
        pareto_raw = state.get("pareto_front", [])
        if isinstance(pareto_raw, list):
            pareto_front = [str(item) for item in pareto_raw]
        map_raw = state.get("map_elites_cells", {})
        if isinstance(map_raw, Mapping):
            map_cells = {str(key): str(value) for key, value in map_raw.items()}

    timestamp = datetime.now(timezone.utc).isoformat()
    rows: list[str] = []
    rows.append("<table class='grid'>")
    rows.append("<caption>MAP-Elites Occupancy</caption>")
    for robustness in reversed(range(robustness_bins)):
        rows.append("<tr>")
        for complexity in range(complexity_bins):
            key = f"{complexity},{robustness}"
            candidate_id = map_cells.get(key)
            if candidate_id and candidate_id in candidates:
                candidate = candidates[candidate_id]
                cell = _format_candidate(candidate)
            elif candidate_id:
                cell = f"<div class='unknown'>Unknown {html.escape(candidate_id[:8])}</div>"
            else:
                cell = "<div class='empty'>∅</div>"
            rows.append(f"<td>{cell}</td>")
        rows.append("</tr>")
    rows.append("</table>")

    pareto_section = _render_pareto_section(pareto_front, candidates)

    template = f"""
<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <title>AutoEvolve Dashboard</title>
    <style>
      body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #0b1e2d; color: #f0f4f8; }}
      h1 {{ margin-bottom: 0.5rem; }}
      table.grid {{ border-collapse: collapse; margin-bottom: 2rem; width: 100%; }}
      table.grid td {{ border: 1px solid rgba(255,255,255,0.1); padding: 0.75rem; vertical-align: top; min-width: 10%; }}
      table.grid caption {{ caption-side: top; font-weight: 600; margin-bottom: 0.75rem; }}
      .candidate {{ font-size: 0.9rem; line-height: 1.4; }}
      .candidate strong {{ display: block; font-size: 1rem; color: #8ae9ff; }}
      .unknown {{ color: #ffbe76; }}
      .empty {{ color: rgba(255,255,255,0.35); text-align: center; }}
      .pareto-list {{ list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }}
      .pareto-card {{ border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 0.75rem; background: rgba(255,255,255,0.03); }}
      footer {{ margin-top: 2rem; font-size: 0.8rem; color: rgba(255,255,255,0.6); }}
    </style>
  </head>
  <body>
    <h1>AutoEvolve Observatory</h1>
    <p>Rendered at <code>{timestamp}</code></p>
    {''.join(rows)}
    {pareto_section}
    <footer>Updated automatically from <code>.artifacts/map_elites.json</code>.</footer>
  </body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(template, encoding="utf-8")


def _format_candidate(candidate: ProgramCandidate) -> str:
    metrics = candidate.metrics
    return """
<div class='candidate'>
  <strong>{id}</strong>
  <div>Acc: {acc:.3f}</div>
  <div>Runtime: {runtime:.1f} ms</div>
  <div>Robust: {robust:.3f}</div>
  <div>LOC: {loc}</div>
</div>
""".format(
        id=html.escape(candidate.id[:10]),
        acc=metrics.accuracy,
        runtime=metrics.runtime_ms,
        robust=metrics.robustness,
        loc=metrics.loc,
    )


def _render_pareto_section(front: Sequence[str], candidates: Mapping[str, ProgramCandidate]) -> str:
    if not front:
        return "<section><h2>Pareto Front</h2><p>No candidates yet.</p></section>"
    items = []
    for candidate_id in front:
        candidate = candidates.get(candidate_id)
        if not candidate:
            continue
        items.append(
            """
<li class='pareto-card'>
  <strong>{id}</strong>
  <div>Problem: {problem}</div>
  <div>Accuracy: {acc:.3f}</div>
  <div>Runtime: {runtime:.1f} ms</div>
  <div>Robustness: {robust:.3f}</div>
</li>
""".format(
                id=html.escape(candidate.id[:10]),
                problem=html.escape(candidate.problem_id),
                acc=candidate.metrics.accuracy,
                runtime=candidate.metrics.runtime_ms,
                robust=candidate.metrics.robustness,
            )
        )
    if not items:
        return "<section><h2>Pareto Front</h2><p>No tracked candidates found.</p></section>"
    return """
<section>
  <h2>Pareto Front</h2>
  <ul class='pareto-list'>
    {items}
  </ul>
</section>
""".format(items="".join(items))
