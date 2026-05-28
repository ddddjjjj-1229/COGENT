from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def run_step(args: list[str]) -> None:
    print("\n>>> " + " ".join(args), flush=True)
    subprocess.run(args, cwd=PROJECT_ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate cases, run main evaluation, run content evaluation, and export paper-style tables.")
    parser.add_argument("--main-config", default="config/eval_config.json", help="Main evaluation config path.")
    parser.add_argument("--content-config", default="config/content_eval_config.json", help="Content evaluation config path.")
    parser.add_argument("--skip-generate", action="store_true", help="Reuse existing processed cases instead of regenerating them.")
    parser.add_argument("--skip-tables", action="store_true", help="Do not export paper-style tables after evaluation.")
    args = parser.parse_args()

    main_config = args.main_config
    content_config = args.content_config

    if not args.skip_generate:
        run_step([PYTHON, "scripts/generate_cases.py", "--config", main_config])

    run_step([PYTHON, "scripts/run_evaluation.py", "--config", main_config])
    run_step([PYTHON, "scripts/run_path_ablation.py", "--config", main_config])
    run_step([PYTHON, "scripts/run_evaluation.py", "--config", content_config])
    run_step(
        [
            PYTHON,
            "scripts/rescore_content_results.py",
            "--input",
            "results/test_5/all_content_case_results.jsonl",
            "--output",
            "results/test_5/content_summary.json",
            "--cases",
            "data/processed/cases.jsonl",
            "--write-rows",
            "results/test_5/all_content_case_results.jsonl",
        ]
    )

    if not args.skip_tables:
        run_step([PYTHON, "scripts/export_paper_tables.py", "--summary", "results/test_5/summary.json", "--mode", "main"])
        run_step([PYTHON, "scripts/export_paper_tables.py", "--summary", "results/test_5/content_summary.json", "--mode", "content"])

    print("\nAll evaluation steps completed.", flush=True)


if __name__ == "__main__":
    main()
