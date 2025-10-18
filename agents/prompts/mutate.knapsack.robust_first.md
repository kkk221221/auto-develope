backend: flash
problem: knapsack
intent: mutate
island: robustness
# Knapsack robustness arm
- filter invalid items and guard capacity edges
- prefer DP variants with deterministic updates
- emit SEARCH/REPLACE patches anchored on helper functions
- respond with JSON containing "version": 1 and at least one SEARCH/REPLACE patch

Checklist:
- Return JSON exactly matching the schema described above with diff_type="sr"
- Ensure payload.replace reproduces the entire EVOLVE block (copy the context block and edit it in full)
- Do not output explanations, markdown, or extra keys
