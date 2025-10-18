backend: flash
problem: sample_problem
intent: mutate
island: performance
# Performance-first mutation
- explore loop fusion or caching to reduce runtime
- keep SEARCH/REPLACE patch minimal and reversible
- maintain accuracy while optimising throughput
- respond with JSON containing "version": 1 and at least one SEARCH/REPLACE patch

Checklist:
- Return JSON exactly matching the schema described above with diff_type="sr"
- Ensure payload.replace reproduces the entire EVOLVE block (copy the context block and edit it in full)
- Do not output explanations, markdown, or extra keys
