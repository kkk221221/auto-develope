backend: flash
problem: sample_problem
intent: mutate
island: robustness
# Robustness-first mutation
1. (1.35) prefer idempotent SEARCH/REPLACE patches with clear anchors
2. (1.40) add validation and guard rails for malformed inputs
3. (1.45) surface telemetry for error cases in checklist

Checklist:
- Report metrics for mutate.robust_first