"""
Removes the duplicate US-051..US-054 entries appended at the end of prd.json
and re-appends them as US-096..US-099 (after existing US-095).
"""
import json

with open("prd.json", encoding="utf-8") as f:
    prd = json.load(f)

stories = prd["userStories"]

# Extract the 4 test-suite-fix stories (currently at the end with wrong IDs)
test_fix_stories = []
keep_stories = []
for s in stories:
    title = s.get("title", "")
    if any(kw in title for kw in [
        "Fix CSRF token acquisition in test suite",
        "Fix fields parameter encoding",
        "Add fallback_base_url field to Prisma AI Settings",
        "Fix SEC-06 CSRF enforcement",
    ]):
        test_fix_stories.append(s)
    else:
        keep_stories.append(s)

print(f"Stories to re-ID: {[s['id'] for s in test_fix_stories]}")
print(f"Remaining stories: {len(keep_stories)}")

# Assign correct IDs
id_map = {"US-051": "US-096", "US-052": "US-097", "US-053": "US-098", "US-054": "US-099"}
for s in test_fix_stories:
    old_id = s["id"]
    new_id = id_map.get(old_id, old_id)
    s["id"] = new_id
    # Fix dependencies too
    s["dependencies"] = [id_map.get(d, d) for d in s.get("dependencies", [])]
    print(f"  {old_id} -> {new_id}: {s['title'][:60]}")

# Rebuild stories list
prd["userStories"] = keep_stories + test_fix_stories

with open("prd.json", "w", encoding="utf-8") as f:
    json.dump(prd, f, indent=2, ensure_ascii=False)

print(f"\nprd.json updated. Total stories: {len(prd['userStories'])}")
pending = sum(1 for s in prd["userStories"] if not s.get("passes", True))
print(f"Pending (passes=False): {pending}")
print("New story IDs:", [s["id"] for s in test_fix_stories])
