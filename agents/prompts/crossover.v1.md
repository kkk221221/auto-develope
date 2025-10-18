backend: flash
problem: *
intent: crossover
island: crossover
# Crossover prompt
- merge complementary strengths from parent patches
- resolve conflicting edits conservatively
- emit SEARCH/REPLACE payload anchored by shared context
- respond with JSON containing "version": 1 and at least one SEARCH/REPLACE patch

Checklist:
- Return JSON exactly matching the schema described above with diff_type="sr"
- Ensure payload.replace reproduces the entire EVOLVE block (copy the context block and edit it in full)
- Do not output explanations, markdown, or extra keys
