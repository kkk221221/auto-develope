backend: flash
problem: shortest_path
intent: mutate
island: robustness
# Shortest path robustness arm
- validate edges and unreachable targets explicitly
- prefer guard clauses over silent failure
- output SEARCH/REPLACE patches with stable anchors
- respond with JSON containing "version": 1 and at least one SEARCH/REPLACE patch
