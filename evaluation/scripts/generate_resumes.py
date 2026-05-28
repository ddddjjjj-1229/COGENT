#!/usr/bin/env python
"""Generate synthetic resume data from job descriptions for testing."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mentor_eval.data_io import load_jobs


def generate_synthetic_resumes(jobs_path: str | Path, output_path: str | Path, count: int = 200) -> None:
    """Generate synthetic resumes from job data."""
    jobs = load_jobs(jobs_path)
    
    resumes = []
    for i in range(min(count, len(jobs))):
        job = jobs[i]
        
        # Generate a synthetic resume based on the job description
        # Vary the skill levels to create different learner profiles
        required = job.required_skills[:3] if job.required_skills else ["Python", "Data Analysis"]
        some_skills = job.prerequisite_skills[:2] if job.prerequisite_skills else ["Communication", "Problem Solving"]
        
        # Create a claimed skills list (some accurate, some inflated)
        claimed = list(required[:2]) + [some_skills[0]] if some_skills else list(required[:2])
        
        # Actual skills (subset of claimed, plus some hidden)
        actual = claimed[:1] + some_skills + ["analytical thinking"]
        
        text = f"""
Professional Summary:
Experienced professional with expertise in {', '.join(actual[:2])}.

Key Skills:
{', '.join(claimed)}

Experience:
- 3+ years of experience with {actual[0] if actual else 'software development'}
- Proficiency in {actual[1] if len(actual) > 1 else 'data analysis'}
- Strong background in {some_skills[0] if some_skills else 'team collaboration'}

Education:
Bachelor's degree in relevant field
"""
        
        resume = {
            "id": f"resume_{i+1:04d}",
            "text": text.strip(),
            "claimed_skills": claimed,
            "actual_skills": actual,
            "foundation_skills": some_skills,
        }
        resumes.append(resume)
    
    # Write as JSONL
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        for resume in resumes:
            f.write(json.dumps(resume, ensure_ascii=False) + "\n")
    
    print(f"Generated {len(resumes)} synthetic resumes to {output_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate synthetic resume data.")
    parser.add_argument("--jobs", default="sample/job/ai_jobs_market_2025_2026.csv", help="Path to jobs CSV file")
    parser.add_argument("--output", default="data/raw/resumes.jsonl", help="Output path for resumes JSONL")
    parser.add_argument("--count", type=int, default=200, help="Number of resumes to generate")
    
    args = parser.parse_args()
    
    jobs_path = Path(args.jobs).resolve()
    if not jobs_path.exists():
        print(f"Jobs file not found: {jobs_path}")
        exit(1)
    
    output_path = Path(args.output).resolve()
    generate_synthetic_resumes(jobs_path, output_path, args.count)
