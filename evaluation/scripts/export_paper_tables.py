from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


SYSTEM_LABELS = {
    "dirprompt": "DirPrompt",
    "genmentor_original": "GenMentor",
    "no_mastery_ablation": "No-mastery",
    "no_tot_ablation": "No-ToT",
    "genmentor_improved": "COGENT",
}

MAIN_ORDER = ["dirprompt", "genmentor_original", "no_mastery_ablation", "genmentor_improved"]
SKILL_ORDER = ["dirprompt", "genmentor_original", "genmentor_improved"]
CONTENT_ORDER = ["dirprompt", "genmentor_original", "no_tot_ablation", "genmentor_improved"]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, int):
        return str(value)
    if value is None:
        return "-"
    return str(value)


def _summary(summary: dict[str, Any], system: str) -> dict[str, Any]:
    return summary.get(system, {}).get("summary", {})


def _rows(summary: dict[str, Any], systems: list[str], columns: list[tuple[str, str]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for system in systems:
        if system not in summary:
            continue
        data = _summary(summary, system)
        rows.append([SYSTEM_LABELS.get(system, system), *[_fmt(data.get(key)) for key, _ in columns]])
    return rows


def _skill_precision(data: dict[str, Any]) -> float | None:
    precision = data.get("goal_skill_precision")
    if isinstance(precision, (int, float)):
        return round(float(precision), 4)
    return None


def _skill_mapping_rows(summary: dict[str, Any], systems: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for system in systems:
        if system not in summary:
            continue
        data = _summary(summary, system)
        rows.append(
            [
                SYSTEM_LABELS.get(system, system),
                _fmt(data.get("goal_skill_recall", data.get("gap_recall"))),
                _fmt(_skill_precision(data)),
            ]
        )
    return rows


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def export_main_tables(summary_path: Path, output_dir: Path) -> None:
    summary = _load_json(summary_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    path_columns = [
        ("progression_likert", "Progression"),
        ("engagement_likert", "Engagement"),
        ("personalization_likert", "Personalization"),
    ]

    skill_headers = ["Method", "Recall", "Precision"]
    path_headers = ["Method", *[label for _, label in path_columns]]
    skill_rows = _skill_mapping_rows(summary, SKILL_ORDER)
    path_rows = _rows(summary, MAIN_ORDER, path_columns)

    skill_md = "# Table 1: Evaluation results on goal-to-skill mapping\n\n" + _markdown_table(skill_headers, skill_rows) + "\n"
    path_md = "# Table 2: Evaluation results on learning path\n\n" + _markdown_table(path_headers, path_rows) + "\n"

    (output_dir / "table1_goal_to_skill.md").write_text(skill_md, encoding="utf-8")
    (output_dir / "table2_learning_path.md").write_text(path_md, encoding="utf-8")
    _write_csv(output_dir / "table1_goal_to_skill.csv", skill_headers, skill_rows)
    _write_csv(output_dir / "table2_learning_path.csv", path_headers, path_rows)

    print(skill_md)
    print(path_md)


def export_content_table(summary_path: Path, output_dir: Path) -> None:
    summary = _load_json(summary_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    content_columns = [
        ("content_goal_relevance_likert", "Goal Relevance"),
        ("content_quality_likert", "Content Quality"),
        ("content_engagement_likert", "Engagement"),
        ("content_personalization_likert", "Personalization"),
    ]
    headers = ["Method", *[label for _, label in content_columns]]
    rows = _rows(summary, CONTENT_ORDER, content_columns)

    content_md = "# Table 3: Evaluation results on learning content\n\n" + _markdown_table(headers, rows) + "\n"
    (output_dir / "table3_learning_content.md").write_text(content_md, encoding="utf-8")
    _write_csv(output_dir / "table3_learning_content.csv", headers, rows)

    print(content_md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export paper-style evaluation tables from summary JSON.")
    parser.add_argument("--summary", required=True, help="Path to summary.json or content_summary.json.")
    parser.add_argument("--mode", choices=["main", "content"], required=True, help="Which table format to export.")
    parser.add_argument("--output-dir", default="", help="Directory for exported markdown/csv files.")
    args = parser.parse_args()

    summary_path = Path(args.summary).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else summary_path.parent / "tables"
    if args.mode == "main":
        export_main_tables(summary_path, output_dir)
    else:
        export_content_table(summary_path, output_dir)
    print(f"Saved tables to {output_dir}")


if __name__ == "__main__":
    main()
