from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mentor_eval.data_io import _infer_resume_skill_sets, _build_resume_summary, read_jsonl, write_jsonl


def repair(path: Path) -> None:
    records = read_jsonl(path)
    changed = 0
    out = []
    for raw in records:
        resume = raw.get("resume", {})
        source = resume.get("source", {})
        claimed, actual, foundation = _infer_resume_skill_sets(source)
        # if the original claimed looks like numeric placeholders, replace
        orig_claimed = resume.get("claimed_skills", [])
        if any(str(x).isdigit() for x in orig_claimed):
            resume["claimed_skills"] = claimed
            changed += 1
        orig_actual = resume.get("actual_skills", [])
        if any(str(x).isdigit() for x in orig_actual):
            resume["actual_skills"] = actual
        orig_found = resume.get("foundation_skills", [])
        if any(str(x).isdigit() for x in orig_found):
            resume["foundation_skills"] = foundation

        # rebuild presented_info and learner text if empty or numeric
        text = resume.get("text", "")
        if not text or any(tok.isdigit() for tok in text.split()):
            resume["text"] = _build_resume_summary(source, resume["claimed_skills"], resume["actual_skills"], resume["foundation_skills"])[:1000]

        # update related top-level fields
        raw["resume"] = resume
        # update presented_info / learner_information
        presented = raw.get("presented_info", "")
        if not presented or any(tok.isdigit() for tok in presented.split()):
            presented = resume["text"]
            if resume.get("claimed_skills"):
                presented = f"{presented}\nClaimed skills: {', '.join(resume['claimed_skills'])}"
            raw["presented_info"] = presented
            raw["learner_information"] = presented

        # update true_knowledge and ground_truth
        tg = raw.get("true_knowledge", raw.get("ground_truth", {}))
        tg["claimed_skills"] = resume.get("claimed_skills", tg.get("claimed_skills", []))
        tg["actual_skills"] = resume.get("actual_skills", tg.get("actual_skills", []))
        tg["foundation_gaps"] = resume.get("foundation_skills", tg.get("foundation_gaps", []))
        raw["true_knowledge"] = tg
        raw["ground_truth"] = tg

        out.append(raw)

    write_jsonl(path, out)
    print(f"Repaired {changed} records and wrote {len(out)} cases to {path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='data/processed/gap_cases_4.jsonl')
    args = parser.parse_args()
    repair(Path(args.input))
