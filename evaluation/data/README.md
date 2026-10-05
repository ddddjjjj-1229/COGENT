# Evaluation data

This directory contains processed benchmark cases used by the COGENT evaluation harness. The raw resume CSV is not included in the anonymous artifact; processed learner-goal cases are provided so that the benchmark input format can be inspected.

The canonical paper benchmark is the fixed-seed 200-case file:

- 200 cases generated with seed 42.
- Category labels: `consistent` (34%), `overestimation` (33%), and `underestimation` (33%).
- Ten Data Mining target jobs are reused across the benchmark cases.

Key files:

- `processed/cases_200.jsonl`: main 200-case benchmark file.
- `processed/cases.jsonl`: legacy five-case smoke fixture.
- `processed/gap_cases_4.jsonl`: small smoke-test fixture.
- `processed/gap_cases_50.jsonl` and `processed/gap_cases_50_compact.jsonl`: diagnostic subsets; they are not the source for the paper-level tables.

Each line is a JSON object containing a learning goal, learner information, job/skill requirements, simulated learner category, and reference skill information used for scoring.
