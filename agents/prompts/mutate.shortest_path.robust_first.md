backend: flash
problem: shortest_path
intent: mutate
island: robustness
# Shortest path robustness arm
- validate edges and unreachable targets explicitly
- prefer guard clauses over silent failure
- output SEARCH/REPLACE patches with stable anchors
- respond with JSON containing "version": 1 and at least one SEARCH/REPLACE patch

Checklist:
- Return JSON exactly matching the schema described above with diff_type="sr"
- Ensure payload.replace reproduces the entire EVOLVE block (copy the context block and edit it in full)
- Do not output explanations, markdown, or extra keys
