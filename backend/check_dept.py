import json, re
with open('data/irins_publications.json') as f:
    data = json.load(f)
def normalize_name(name): return re.sub(r'[^a-z]', '', name.lower())
with open('data/faculty.json') as f:
    fac_data = json.load(f)
existing = {normalize_name(f['name']) for f in fac_data['institutions'][0]['faculty']}
count = 0
for fac in data['faculty']:
    if normalize_name(fac['name']) not in existing:
        dept = fac.get("department", "").lower()
        print(fac['name'], "|", fac.get("department", ""))
        if "computer science" in dept or "cse" in dept:
            count += 1
print("Total matching CS logic:", count)
