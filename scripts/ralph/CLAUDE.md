# Ralph Autonomous Agent — Frappe/ERPNext/Docker Instructions

You are running as part of Ralph, an autonomous agent loop.
Your job is to implement **ONE SINGLE USER STORY** from `prd.json`, then exit.

---

## Project Context

- **Project:** `lhdn_payroll_integration` — LHDN Malaysian e-Invoice Frappe custom app
- **Docker container:** `prisma-erp-backend-1`
- **Bench dir (inside container):** `/home/frappe/frappe-bench`
- **App path (inside container):** `/home/frappe/frappe-bench/apps/lhdn_payroll_integration/`
- **Site name:** `frontend`
- **Compose file:** `pwd-myinvois.yml`
- **ERPNext URL:** `http://localhost:8080` (Administrator / admin)

---

## Critical Rules

1. **ONE STORY ONLY** — Pick the highest-priority story with `passes: false` whose dependencies are all `passes: true`
2. **Verify Docker first** — Check container is running before any work
3. **TDD gate per story type:**
   - `type: "TEST"` (UT-NNN) → bench run-tests must **FAIL** = success (red phase)
   - `type: "IMPL"` (US-NNN) → bench run-tests must **PASS** = success (green phase)
   - `type: "INTG"` (US-022) → all 5 sandbox scenarios must pass
4. **Mark `passes: true`** only when verification succeeds
5. **Document learnings** in `progress.txt`
6. **Commit** after marking complete

---

## Step-by-Step Workflow

### Step 1 — Read Context
```bash
head -60 progress.txt                     # codebase patterns, previous learnings
[[ -f _specialist_context.md ]] && echo "--- Frappe Developer Specialist (file map) ---" && cat _specialist_context.md
[[ -f _retry_context.md ]] && echo "--- Qwen Failure Diagnosis (previous attempt) ---" && cat _retry_context.md
cat prd.json | jq '.userStories[] | select(.passes == false) | {id, title, priority, type, dependencies}' | head -40
```

### Step 2 — Pick Next Story
- Highest priority where `passes: false` AND all items in `dependencies[]` have `passes: true`
- Read the full story: `description`, `acceptanceCriteria`, `technicalNotes`, `type`

### Step 3 — Check Docker
```bash
docker ps --format '{{.Names}}' | grep prisma-erp-backend-1
```
If not running:
```bash
docker compose -f pwd-myinvois.yml up -d
sleep 10
```

### Step 4 — Implement the Story

#### For `type: "TEST"` stories (UT-NNN) — Write Failing Tests
1. Get the test file path from `technicalNotes` (e.g. `tests/test_app_scaffold.py`)
2. Write the complete test file with all classes and methods listed in `technicalNotes`
3. Use `FrappeTestCase` as base class: `from frappe.tests.utils import FrappeTestCase`
4. Import the modules you are testing — these will cause `ImportError` since impl doesn't exist yet
5. Copy the file into the container:
   ```bash
   docker cp ./LOCALFILE prisma-erp-backend-1:/home/frappe/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/tests/test_XXX.py
   ```
6. Run bench tests and **confirm it FAILS**:
   ```bash
   docker exec prisma-erp-backend-1 bash -c \
     "cd /home/frappe/frappe-bench && bench --site frontend run-tests --module lhdn_payroll_integration.tests.test_XXX" \
     && echo "⚠ UNEXPECTED PASS — do not mark passes:true" \
     || echo "✓ EXPECTED FAIL — red phase confirmed, mark passes:true"
   ```
7. If it FAILS (exit code ≠ 0) → mark `passes: true`
8. If it unexpectedly PASSES → investigate, do NOT mark complete

#### For `type: "IMPL"` stories (US-NNN) — Implement and Go Green
1. Write all production Python files locally, then docker cp them to the container
2. If story adds fixtures or DocTypes, run `bench migrate` and `bench clear-cache`
3. Find the `[TDD GREEN]` line in `acceptanceCriteria` — that has the exact bench command
4. Run bench tests and **confirm PASSES**:
   ```bash
   docker exec prisma-erp-backend-1 bash -c \
     "cd /home/frappe/frappe-bench && bench --site frontend run-tests --module lhdn_payroll_integration.tests.test_XXX"
   # Must exit 0 — zero failures, zero errors
   ```
5. If all tests pass → mark `passes: true`
6. If tests fail → debug and fix; do NOT mark complete until green

#### For `type: "INTG"` story (US-022)
- Requires real LHDN sandbox credentials on the Company doc
- If credentials are missing, document in `progress.txt` and exit

---

## Docker File Operations

### Write a file to the container
```bash
# Write content locally first (e.g. to ./tmp_lhdn/services/exemption_filter.py)
# Then docker cp:
docker cp ./tmp_lhdn/services/exemption_filter.py \
  prisma-erp-backend-1:/home/frappe/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/services/exemption_filter.py
```

### Run bench commands
```bash
docker exec prisma-erp-backend-1 bash -c "cd /home/frappe/frappe-bench && bench --site frontend <cmd>"
```

### Common bench commands
```bash
# Migrate (apply fixtures/schema changes)
bench --site frontend migrate

# Clear cache
bench --site frontend clear-cache

# List installed apps
bench --site frontend list-apps

# Run specific test module
bench --site frontend run-tests --module lhdn_payroll_integration.tests.test_XXX

# Run all app tests
bench --site frontend run-tests --app lhdn_payroll_integration

# Install app (US-001 only)
bench --site frontend install-app lhdn_payroll_integration
```

---

## Special Case: UT-001 (First Story — No App Yet)

UT-001 has `dependencies: []` and runs before US-001 (which creates the app with `bench new-app`).

Approach for UT-001:
1. Run `bench new-app lhdn_payroll_integration` inside container to create the scaffold
2. Do NOT install the app yet (that's US-001's job)
3. Create `tests/__init__.py` and `tests/test_app_scaffold.py` in the new app
4. Run `bench --site frontend run-tests --module lhdn_payroll_integration.tests.test_app_scaffold`
5. It will FAIL (app not installed to site → ImportError or no test discovery) → red phase ✓

```bash
docker exec prisma-erp-backend-1 bash -c \
  "cd /home/frappe/frappe-bench && bench new-app lhdn_payroll_integration"
```
When prompted interactively:
- App title: LHDN Payroll Integration
- App description: LHDN MyInvois payroll e-Invoice compliance
- App publisher: Prisma Technology
- App email: admin@prismatechnology.com
- App license: MIT

If `bench new-app` is interactive (requires TTY), use:
```bash
docker exec -it prisma-erp-backend-1 bash
# Then inside: cd /home/frappe/frappe-bench && bench new-app lhdn_payroll_integration
```

---

## Special Case: US-001 (App Scaffold)

US-001 installs the app and configures hooks.py, modules.txt, install.py.

```bash
# Install app to site
docker exec prisma-erp-backend-1 bash -c \
  "cd /home/frappe/frappe-bench && bench --site frontend install-app lhdn_payroll_integration"

# Verify
docker exec prisma-erp-backend-1 bash -c \
  "cd /home/frappe/frappe-bench && bench --site frontend list-apps"
```

Key files to write after install:
- `lhdn_payroll_integration/hooks.py` — doc_events, scheduler_events, fixtures
- `lhdn_payroll_integration/modules.txt` — `LHDN Payroll Integration`
- `lhdn_payroll_integration/install.py` — after_install(), after_migrate() stubs
- Create dirs: `services/`, `utils/`, `fixtures/`, `tests/`

---

## prd.json Update

```bash
# Mark story complete
jq '(.userStories[] | select(.id == "STORY_ID") | .passes) = true' prd.json > prd.json.tmp
mv prd.json.tmp prd.json
```

---

## progress.txt Documentation

```markdown
## Iteration [N] — [STORY_ID]: [STORY_TITLE]

**Type:** TEST | IMPL | INTG
**TDD Phase:** RED (fail confirmed) | GREEN (pass confirmed)
**Bench command:** `bench --site frontend run-tests --module ...`
**Result:** FAIL / PASS

### Files created/modified
- `/home/frappe/frappe-bench/apps/lhdn_payroll_integration/...`

### Patterns discovered
- [Frappe/Docker patterns useful for future stories]

### Gotchas
- [Issues encountered and how resolved]
```

---

## Commit Format

```bash
git add -A
git commit -m "feat: [STORY_ID] - [STORY_TITLE]

TDD [RED|GREEN]: bench --site frontend run-tests --module lhdn_payroll_integration.tests.test_XXX

Story: [STORY_ID]
Type: TEST|IMPL

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Stop Conditions

Exit this iteration when:
1. ✓ Story verified (bench FAIL for UT / bench PASS for US) → prd.json updated → committed → **EXIT**
2. ✗ Docker not running after start attempt → document in progress.txt → **EXIT**
3. ✗ Cannot complete story after debugging → leave `passes: false` → document failure → **EXIT**
4. ✗ INTG story missing LHDN sandbox credentials → document and **EXIT**

---

Now read `prd.json` and `progress.txt`, pick the next story, and implement it!
