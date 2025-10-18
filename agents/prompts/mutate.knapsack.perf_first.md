backend: flash
problem: knapsack
intent: mutate
island: performance
# Knapsack performance arm
- explore dense DP or bitset accelerations
- ensure loops run forwards for cache friendliness
- keep modifications within EVOLVE block only
- respond with JSON containing "version": 1 and at least one SEARCH/REPLACE patch
