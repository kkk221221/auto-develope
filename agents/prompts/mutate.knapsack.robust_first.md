backend: flash
problem: knapsack
intent: mutate
island: robustness
# Knapsack robustness arm
- filter invalid items and guard capacity edges
- prefer DP variants with deterministic updates
- emit SEARCH/REPLACE patches anchored on helper functions
