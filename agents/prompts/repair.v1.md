backend: flash
problem: *
intent: repair
island: repair
# Repair prompt
- analyse logs for failing tests or build errors
- propose minimal SEARCH/REPLACE fixes
- ensure fix keeps solve() signature stable
- respond with JSON containing "version": 1 and at least one SEARCH/REPLACE patch

Checklist:
- Return JSON exactly matching the schema described above with diff_type="sr"
- Ensure payload.replace reproduces the entire EVOLVE block (copy the context block and edit it in full)
- Do not output explanations, markdown, or extra keys
