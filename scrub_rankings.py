import json
import re

def is_workshop(title, venue_full):
    pattern = r'\b(demo|poster|student abstract|doctoral consortium|extended abstract|tutorial|workshop|companion)\b'
    if re.search(pattern, title.lower()):
        return True
    if venue_full and "adjunct" in venue_full.lower():
        return True
    if venue_full and re.search(pattern, venue_full.lower()):
        return True
    return False

def main():
    with open('data/rankings.json', 'r') as f:
        data = json.load(f)
    
    removed_count = 0
    for inst in data.get('institutions', []):
        for fac in inst.get('faculty', []):
            valid_pubs = []
            for pub in fac.get('publications', []):
                if is_workshop(pub.get('title', ''), pub.get('venue_full', '')):
                    print(f"Removing: {pub.get('title')} ({pub.get('venue_full')})")
                    removed_count += 1
                else:
                    valid_pubs.append(pub)
            
            # Recalculate if changed
            if len(valid_pubs) != len(fac.get('publications', [])):
                fac['publications'] = valid_pubs
                fac['total_matched'] = len(valid_pubs)
                
                score = 0.0
                astar = 0
                a = 0
                journal = 0
                for p in valid_pubs:
                    score += p.get('adjusted_count', 0)
                    r = p.get('venue_rank', '')
                    if r == 'A*':
                        astar += 1
                    elif r == 'A':
                        a += 1
                    elif r == 'Journal':
                        journal += 1
                fac['score'] = round(score, 4)
                fac['papers_astar'] = astar
                fac['papers_a'] = a
                fac['papers_journal'] = journal
                
    with open('data/rankings.json', 'w') as f:
        json.dump(data, f, indent=2)
        
    print(f"Removed {removed_count} workshop papers from rankings.json")

if __name__ == '__main__':
    main()
