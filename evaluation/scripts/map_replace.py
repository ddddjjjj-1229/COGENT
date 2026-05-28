from pathlib import Path
import json, sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mentor_eval.data_io import read_jsonl, write_jsonl

base = Path('data/processed')
source200 = base / 'cases_200.jsonl'
target4 = base / 'gap_cases_4.jsonl'

if not source200.exists() or not target4.exists():
    print('missing files', source200.exists(), target4.exists())
    sys.exit(1)

cases200 = read_jsonl(source200)
map_by_job = {c['job']['id']: c['resume'].get('claimed_skills', []) for c in cases200}

cases4 = read_jsonl(target4)
changed=0
for raw in cases4:
    jobid = raw.get('job', {}).get('id')
    if jobid in map_by_job and any(str(x).isdigit() for x in raw.get('resume', {}).get('claimed_skills', [])):
        new_claimed = map_by_job[jobid]
        raw['resume']['claimed_skills'] = new_claimed
        # set actual similarly if numeric
        if any(str(x).isdigit() for x in raw['resume'].get('actual_skills', [])):
            raw['resume']['actual_skills'] = new_claimed[:2] if new_claimed else []
        # update presented info and ground truth
        raw['presented_info'] = raw['resume'].get('text','') + '\nClaimed skills: ' + ', '.join(raw['resume']['claimed_skills'])
        raw['learner_information'] = raw['presented_info']
        if 'true_knowledge' in raw:
            raw['true_knowledge']['claimed_skills'] = raw['resume']['claimed_skills']
            raw['true_knowledge']['actual_skills'] = raw['resume'].get('actual_skills', raw['resume']['claimed_skills'])
        if 'ground_truth' in raw:
            raw['ground_truth']['claimed_skills'] = raw['resume']['claimed_skills']
            raw['ground_truth']['actual_skills'] = raw['resume'].get('actual_skills', raw['resume']['claimed_skills'])
        changed+=1

write_jsonl(target4, cases4)
print('changed', changed)
