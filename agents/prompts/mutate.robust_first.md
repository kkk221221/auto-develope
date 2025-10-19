backend: flash
problem: sample_problem
intent: mutate
island: robustness
# Robustness-first mutation
- prefer idempotent SEARCH/REPLACE patches with clear anchors
- add validation and guard rails for malformed inputs
- surface telemetry for error cases in checklist
- respond with JSON containing "version": 1 and SEARCH/REPLACE patches only

Checklist:
- Report metrics for mutate.robust_first
- Return JSON exactly matching the schema described above with diff_type="sr"
- Ensure payload.replace reproduces the entire EVOLVE block (copy the context block and edit it in full)
- Do not output explanations, markdown, or extra keys
