from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mentor_eval.runner import run_benchmark
from mentor_eval.runner import run_content_benchmark
from mentor_eval.runner import run_skill_gap_benchmark


def load_config(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GenMentor evaluation benchmark.")
    parser.add_argument("--config", default="config/eval_config.json", help="Path to the evaluation config file.")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    project_root = config_path.parent.parent
    config = load_config(config_path)
    config["processed_cases_file"] = str((project_root / config["processed_cases_file"]).resolve())
    config["output_dir"] = str((project_root / config["output_dir"]).resolve())
    config["input_files"] = {
        name: str((project_root / rel_path).resolve())
        for name, rel_path in config["input_files"].items()
    }
    evaluation_mode = config.get("evaluation_mode", "full")
    if evaluation_mode == "skill_gap":
        results = run_skill_gap_benchmark(config)
    elif evaluation_mode == "content":
        results = run_content_benchmark(config)
    else:
        results = run_benchmark(config)
    summary_file = "content_summary.json" if evaluation_mode == "content" else "summary.json"
    summary_path = Path(config["output_dir"]) / summary_file
    print(f"Saved evaluation summary to {summary_path}")
    print(json.dumps(results, ensure_ascii=False, indent=2)[:8000])


if __name__ == "__main__":
    main()
