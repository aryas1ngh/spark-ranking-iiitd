import json
with open('data/icore_conferences.json') as f:
    data = json.load(f)
diffs = 0
for conf in data['conferences']:
    if conf.get('acronym', '').lower() != conf.get('dblp_key', '').lower():
        diffs += 1
print("Differences between acronym and dblp_key:", diffs)
