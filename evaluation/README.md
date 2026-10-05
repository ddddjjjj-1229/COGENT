# COGENT Evaluation Protocol

This folder contains the evaluation harness and supporting materials used to document the experimental protocol for COGENT. It is intended to make the evaluation setup inspectable for anonymous review.

## What is included

- `mentor_eval/`: core evaluation package, including adapters, scoring logic, LLM-as-judge utilities, and case loading.
- `scripts/`: scripts for running skill-gap, path-planning, content-generation, ablation, rescoring, and table-export workflows.
- `config/`: JSON configuration files for the reported evaluation settings. API keys are not stored in these files; they are read from environment variables such as `DASHSCOPE_API_KEY`.
- `data/processed/`: processed learner-goal cases used by the evaluation harness.
- `results/paper_tables/`: instructions for regenerating tables from the current scoring pipeline.
- `sample/job/`: non-sensitive job-target metadata used for case construction.

## What is not included

The full raw resume CSV and local runtime outputs are not included in this anonymous artifact. The processed cases needed to inspect the benchmark inputs are included under `data/processed/`. Baseline services must be run separately if full end-to-end re-execution is desired.

## Running an evaluation

From this `evaluation/` directory, configure the model API key first, for example:

```bash
export DASHSCOPE_API_KEY=your-key
```

Then run one of the configuration files:

```bash
python scripts/run_evaluation.py --config config/gap_eval_config.json
python scripts/run_evaluation.py --config config/full_eval_config.json
python scripts/run_evaluation.py --config config/content_eval_config.json
```

The configuration files assume that the compared system endpoints are available locally. In the released artifact, the key `genmentor_improved` is the internal evaluation identifier for the COGENT system endpoint, while `genmentor_original` denotes the baseline GenMentor endpoint.

The canonical paper benchmark is `data/processed/cases_200.jsonl`: 200 fixed-seed cases with the
categories `consistent`, `overestimation`, and `underestimation`. All paper evaluation configs,
rescore scripts, ablation scripts, and table exports use this file. The five-case and 50-case
files are smoke or diagnostic subsets only.

## Reported aggregate tables

Paper-level aggregate tables can be regenerated into:

```text
results/paper_tables/
```

These files are included to document the reported values without requiring reviewers to rerun all API-based evaluations.

Table exports read the aggregate values produced by the scoring pipeline directly. They do not
apply fixed penalties, minimum-score floors, or post-hoc method-order calibration.
