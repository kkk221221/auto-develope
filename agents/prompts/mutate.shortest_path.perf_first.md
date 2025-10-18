backend: flash
problem: shortest_path
intent: mutate
island: performance
# Shortest path performance arm
- favour adjacency lists and priority queues
- include telemetry on relaxation counts
- keep replacements focused within EVOLVE block
- respond with JSON containing "version": 1 and at least one SEARCH/REPLACE patch

Checklist:
- Return JSON exactly matching the schema described above with diff_type="sr"
- Ensure payload.replace reproduces the entire EVOLVE block (copy the context block and edit it in full)
- Do not output explanations, markdown, or extra keys
