backend: flash
problem: *
intent: repair
island: repair
# Repair prompt
- analyse logs for failing tests or build errors
- propose minimal SEARCH/REPLACE fixes
- ensure fix keeps solve() signature stable
- respond with JSON containing "version": 1 and at least one SEARCH/REPLACE patch
