# Evaluation data

This directory contains processed benchmark cases used by the COGENT evaluation harness. The raw resume CSV is not included in the anonymous artifact; processed learner-goal cases are provided so that the benchmark input format can be inspected.

Key files:

- `processed/cases_200.jsonl`: main 200-case benchmark file.
- `processed/gap_cases_50_compact.jsonl`: compact skill-gap evaluation subset.
- `processed/gap_cases_4.jsonl`: small smoke-test subset.

Each line is a JSON object containing a learning goal, learner information, job/skill requirements, simulated learner category, and reference skill information used for scoring.
