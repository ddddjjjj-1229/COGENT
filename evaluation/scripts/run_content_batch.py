from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mentor_eval.data_io import read_jsonl, write_jsonl
from mentor_eval.runner import run_content_benchmark
from scripts.export_paper_tables import export_content_table
from scripts.rescore_content_results import recompute_content_summary


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_config_paths(config: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(config)
    resolved["processed_cases_file"] = str((PROJECT_ROOT / config["processed_cases_file"]).resolve())
    resolved["output_dir"] = str((PROJECT_ROOT / config["output_dir"]).resolve())
    resolved["input_files"] = {
        name: str((PROJECT_ROOT / rel_path).resolve())
        for name, rel_path in config.get("input_files", {}).items()
    }
    return resolved


def _merge_batch_rows(main_rows_path: Path, batch_rows_path: Path) -> int:
    batch_rows = read_jsonl(batch_rows_path)
    batch_keys = {(row.get("system"), row.get("case_id")) for row in batch_rows}
    existing_rows = [
        row
        for row in read_jsonl(main_rows_path)
        if (row.get("system"), row.get("case_id")) not in batch_keys
    ]
    merged_rows = existing_rows + batch_rows
    write_jsonl(main_rows_path, merged_rows)
    return len(batch_rows)


def _copy_cases_slice(cases_path: Path, batch_cases_path: Path, start: int, limit: int) -> tuple[int, int]:
    cases = read_jsonl(cases_path)
    selected = cases[start : start + limit]
    write_jsonl(batch_cases_path, selected)
    return len(cases), len(selected)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run learning-content evaluation in resumable batches.")
    parser.add_argument("--config", default="config/content_eval_config.json")
    parser.add_argument("--start", type=int, required=True, help="Zero-based case offset for this batch.")
    parser.add_argument("--limit", type=int, default=20, help="Number of cases to run in this batch.")
    parser.add_argument("--reset", action="store_true", help="Clear existing merged content rows before this batch.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary batch files.")
    args = parser.parse_args()

    config_path = (PROJECT_ROOT / args.config).resolve()
    config = _load_config(config_path)
    cases_path = (PROJECT_ROOT / config["processed_cases_file"]).resolve()
    output_dir = (PROJECT_ROOT / config["output_dir"]).resolve()
    tables_dir = output_dir / "tables"
    temp_dir = output_dir / "_content_batch_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    batch_cases_path = temp_dir / f"cases_{args.start}_{args.start + args.limit}.jsonl"
    total_cases, selected_cases = _copy_cases_slice(cases_path, batch_cases_path, args.start, args.limit)
    if selected_cases == 0:
        raise SystemExit(f"No cases selected. Total cases: {total_cases}, start: {args.start}, limit: {args.limit}")

    batch_output_dir = temp_dir / f"out_{args.start}_{args.start + selected_cases}"
    if batch_output_dir.exists():
        shutil.rmtree(batch_output_dir)
    batch_output_dir.mkdir(parents=True, exist_ok=True)

    batch_config = _resolve_config_paths(config)
    batch_config["processed_cases_file"] = str(batch_cases_path.resolve())
    batch_config["output_dir"] = str(batch_output_dir.resolve())
    batch_config.setdefault("content_eval", {})
    batch_config["content_eval"]["max_cases"] = selected_cases

    print(f"Running content batch: cases {args.start}..{args.start + selected_cases - 1} of {total_cases}")
    run_content_benchmark(batch_config)

    main_rows_path = output_dir / "all_content_case_results.jsonl"
    if args.reset and main_rows_path.exists():
        main_rows_path.unlink()
    merged_count = _merge_batch_rows(main_rows_path, batch_output_dir / "all_content_case_results.jsonl")

    content_summary_path = output_dir / "content_summary.json"
    recompute_content_summary(
        input_path=main_rows_path,
        output_path=content_summary_path,
        cases_path=cases_path,
        write_rows_path=main_rows_path,
    )
    export_content_table(content_summary_path, tables_dir)

    if not args.keep_temp:
        shutil.rmtree(batch_output_dir, ignore_errors=True)

    print(f"Merged {merged_count} content rows.")
    print(f"Updated {content_summary_path}")
    print(f"Updated {tables_dir / 'table3_learning_content.md'}")


if __name__ == "__main__":
    main()
