#!/usr/bin/env python
import csv
from collections import defaultdict

categories = defaultdict(int)
with open('sample/job/ai_jobs_market_2025_2026.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cat = row.get('job_category', 'Unknown')
        categories[cat] += 1

print("Job Categories Distribution:")
print("-" * 40)
for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
    print(f"{cat}: {count}")
print("-" * 40)
print(f"Total categories: {len(categories)}")
print(f"Total jobs: {sum(categories.values())}")
