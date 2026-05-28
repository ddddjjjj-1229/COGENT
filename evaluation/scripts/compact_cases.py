from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mentor_eval.data_io import read_jsonl, write_jsonl


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        value = str(item).strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            result.append(value)
    return result


def _build_compact_case(raw: Dict[str, Any]) -> Dict[str, Any]:
    job = raw.get("job", {})
    resume = raw.get("resume", {})
    category = raw.get("category", "")

    required = _dedupe(job.get("required_skills", []))
    claimed = _dedupe(resume.get("claimed_skills", []))
    actual = _dedupe(resume.get("actual_skills", []))

    true_gap = [skill for skill in required if skill.lower() not in {s.lower() for s in actual}]

    presented_info = f"Category: {category}\nClaimed skills: {', '.join(claimed)}"

    return {
        "case_id": raw.get("case_id"),
        "category": category,
        "job": {
            "id": job.get("id"),
            "title": job.get("title"),
            "description": "",
            "required_skills": required,
            "prerequisite_skills": [],
            "source": {},
        },
        "resume": {
            "id": resume.get("id"),
            "text": "",
            "claimed_skills": claimed,
            "actual_skills": actual,
            "foundation_skills": [],
            "source": {},
        },
        "learning_goal": raw.get("learning_goal", ""),
        "presented_info": presented_info,
        "true_knowledge": {
            "claimed_skills": claimed,
            "actual_skills": actual,
            "true_gap_skills": true_gap,
        },
        "learner_information": presented_info,
        "ground_truth": {
            "claimed_skills": claimed,
            "actual_skills": actual,
            "true_gap_skills": true_gap,
        },
        "behavior_trace": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact case files for gap-only evaluation.")
    parser.add_argument("--input", required=True, help="Input JSONL cases file.")
    parser.add_argument("--output", required=True, help="Output JSONL cases file.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    records = read_jsonl(input_path)
    compacted = [_build_compact_case(record) for record in records]
    write_jsonl(output_path, compacted)
    print(f"Wrote {len(compacted)} compact cases to {output_path}")


if __name__ == "__main__":
    main()
