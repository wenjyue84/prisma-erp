# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

This is a clone of `frappe/frappe_docker`, customised to run **ERPNext v16 + MyInvois (Malaysian LHDN e-invoicing)** locally via Docker. The upstream files (`pwd.yml`, `compose.yaml`) are unchanged; the active setup is entirely in the files added on top.

**Active compose file:** `pwd-myinvois.yml` (NOT `pwd.yml`)
**Active Docker image:** `wenjyue/erpnext-myinvois:v16` (DockerHub) / `frappe/erpnext-myinvois:v16` (local build from `Dockerfile.myinvois`)
**Site name:** `frontend`
**ERPNext credentials:** `Administrator` / `admin`
**Local URL:** `http://localhost:8080`
**Production URL:** `https://prismaerp.click` (CloudFront → EC2)

### Current Desk Home Labels

The visible workspace labels on `http://localhost:8080/desk` are customised and should be treated as the current source of truth for user-facing documentation and screenshots.

Current Desk home labels:

- `E-Invoice`
- `ESS Mobile`
- `Framework`
- `LHDN Payroll`
- `Accounting`
- `Assets`
- `Buying`
- `Manufacturing`
- `Projects`
- `Quality`
- `Selling`
- `Stock`
- `Subcontracting`
- `ERP Settings`
- `HR`

Notes:

- `E-Invoice` is the visible Desk label for the MyInvois / Malaysia compliance area.
- `Framework` is a curated umbrella tile rather than a raw upstream module name.
- `HR` is the top-level HR tile currently shown on Desk; older screenshots or dumps may still expose lower-level HRMS workspaces such as `Payroll`, `Leaves`, `Expenses`, `Performance`, or `Tax & Benefits`.

### Custom apps in this repo

| App | Path | Description |
|-----|------|-------------|
| `lhdn_payroll_integration` | `lhdn_payroll_integration/` | Malaysian payroll compliance — PCB, EPF, SOCSO, EIS, TP1/TP3 forms, LHDN e-invoicing, gig workers, Budget 2026. **325 user stories, 177 passing, 4,000+ test methods across 167 test files and 74 service modules.** |
| `prisma_assistant` | `prisma_assistant/` | AI chat widget for ERPNext desk (Frappe app). Vision, markdown, localStorage history. |
| `myinvois_erpgulf` | (baked in image) | LHDN MyInvois e-invoicing integration (upstream). |

## Commands

### Start / Stop

```bash
# Start (uses persisted Docker volumes — site already initialised)
docker compose -f pwd-myinvois.yml up -d

# Stop (preserves data)
docker compose -f pwd-myinvois.yml down

# Destroy everything including data
docker compose -f pwd-myinvois.yml down -v
```

### Rebuild the custom image

Required after any change to `Dockerfile.myinvois` (e.g. updating myinvois to a newer commit):

```bash
docker build -f Dockerfile.myinvois -t frappe/erpnext-myinvois:v16 .
docker compose -f pwd-myinvois.yml down
docker compose -f pwd-myinvois.yml up -d
```

### Bench commands (run inside backend container)

```bash
# Shell into the backend container
docker exec -it prisma-erp-backend-1 bash

# Common bench commands (all need --site frontend)
bench --site frontend list-apps
bench --site frontend install-app <app_name>
bench --site frontend migrate
bench --site frontend clear-cache
bench --site frontend console          # Interactive Python REPL with frappe context

# Run a one-off Python function
bench --site frontend execute <module.function>
```

### Run test data seed

```bash
# Copy updated script then re-run
docker cp setup_test_data.py prisma-erp-backend-1:/home/frappe/frappe-bench/apps/frappe/frappe/setup_test_data.py
docker exec prisma-erp-backend-1 bash -c "cd /home/frappe/frappe-bench && bench --site frontend execute frappe.setup_test_data.run"
```

### Deploy frappe_patches (login.js etc.)

Frappe serves `login.js` from `templates/includes/login/`, **not** `www/`. Always copy to the correct path:

```bash
# Local
docker cp frappe_patches/login.js prisma-erp-backend-1:/home/frappe/frappe-bench/apps/frappe/frappe/templates/includes/login/login.js
docker compose -f pwd-myinvois.yml exec backend bench --site frontend clear-cache
docker compose -f pwd-myinvois.yml exec backend bench --site frontend clear-website-cache
docker compose -f pwd-myinvois.yml restart backend frontend
```

### View logs

```bash
docker compose -f pwd-myinvois.yml logs -f backend
docker compose -f pwd-myinvois.yml logs -f create-site   # first-run site init
```

## Architecture

### Docker service layout

All services use the `frappe/erpnext-myinvois:v16` image except `db` (MariaDB 10.6) and `redis-*` (Redis 6.2):

| Service | Role |
|---------|------|
| `frontend` | nginx reverse proxy → port 8080 |
| `backend` | Gunicorn (Frappe/ERPNext app server) on port 8000 |
| `websocket` | Node.js Socket.IO server on port 9000 |
| `scheduler` | Frappe background scheduler |
| `queue-long` / `queue-short` | RQ workers |
| `configurator` | One-time init: writes `common_site_config.json` |
| `create-site` | One-time init: `bench new-site` (skips on restart if site exists) |

Persistent data lives in Docker named volumes: `sites`, `logs`, `db-data`, `redis-queue-data`.

### MyInvois (LHDN) integration

The app `myinvois_erpgulf` (v2.1, installed at `/home/frappe/frappe-bench/apps/myinvois_erpgulf/`) adds:

- **Custom fields on Company** (LHDN Malaysia Setup tab): `custom_company_tin_number`, `custom_client_id`, `custom_client_secret`, `custom_integration_type` (Sandbox/Production), `custom_sandbox_url`, `custom_production_url`, `custom_enable_lhdn_invoice`, `custom_version` (1.0/1.1)
- **Custom fields on Customer**: `custom_customer_tin_number`, `custom_customer__registrationicpassport_type`, `custom_customer_registrationicpassport_number`
- **Custom fields on Sales Invoice**: `custom_malaysia_tax_category`, `custom_invoicetype_code`, `custom_customer_tin_number`, `custom_lhdn_status`, `custom_is_submit_to_lhdn`, `custom_einvoice_qr`
- **Doc events**: hooks on `before_submit`, `on_submit`, `on_cancel`, `after_submit` of Sales Invoice and Purchase Invoice — these call the LHDN API when an invoice is submitted
- **LHDN Success Log** doctype for submission audit trail
- **Reports**: LHDN Sales Status, LHDN Purchase Status, LHDN VAT Report

The LHDN API call flow: `on_submit` → `taxpayerlogin.get_access_token()` (uses `custom_client_id`/`custom_client_secret` from Company) → `after_submit` → `createxml.after_submit()` generates UBL XML and submits to MyInvois API.

### Why `bench get-app` was replaced in Dockerfile.myinvois

`bench get-app` internally uses `uv pip install` which fails to resolve `frappe`'s git-pinned `pypika` dependency. The workaround is a manual `git clone` + `pip install --no-deps` (safe because `frappe` is already in the venv).

### Image rebuild gotcha — nginx stale DNS

After restarting services, nginx may cache the old backend IP. Fix:

```bash
docker compose -f pwd-myinvois.yml restart frontend
```

## Test Data (`setup_test_data.py`)

Idempotent seed script. Re-running skips already-existing records. Creates:

1. **Company "Arising Packaging"** — populated with test LHDN fields (Sandbox, TIN `C12345678901`)
2. **Tax template "SST 8% - AP"** — 10% on `GST - AP` account
3. **Corporate customer** — Tech Solutions Sdn Bhd (TIN `C56789012345`, BRN)
4. **Individual customer** — Ahmad bin Abdullah (TIN `IG12345678901`, NRIC)
5. **Two draft Sales Invoices** — one per customer, with all myinvois fields set

> ⚠️ `custom_client_id` and `custom_client_secret` on the Company are placeholder values. Replace them with real LHDN sandbox credentials before clicking "Taxpayer Login" or submitting an invoice.

## Select field values (myinvois)

These fields have specific option strings — use the full string including code prefix:

| Field | Valid values |
|-------|-------------|
| `custom_invoicetype_code` | `"01 :  Invoice"`, `"02 : Credit Note"`, `"03 :  Debit Note"`, `"04 :  Refund Note"` |
| `custom_malaysia_tax_category` | `"01 : Sales Tax"`, `"02 : Service Tax"`, `"03 :  Tourism Tax"`, `"06  : Not Applicable"`, `"E  : Tax exemption (where applicable)"` |
| `custom_integration_type` | `"Sandbox"`, `"Production"` |
| `custom_version` | `"1.0"`, `"1.1"` |

## Production deployment

The `compose.yaml` + `overrides/` system is for production. Combine a base `compose.yaml` with overlay files:

```bash
# Example: MariaDB + HTTPS + Traefik
docker compose \
  -f compose.yaml \
  -f overrides/compose.mariadb.yaml \
  -f overrides/compose.https.yaml \
  -f overrides/compose.traefik-ssl.yaml \
  up -d
```

Copy `example.env` → `.env` and set `ERPNEXT_VERSION`, `DB_PASSWORD`, `FRAPPE_SITE_NAME_HEADER` before production deploy. See `docs/` for full production guide.

## SPIRAL — Autonomous Compliance Research Loop

Self-iterating loop that discovers Malaysian payroll compliance requirements, generates user stories, and implements them autonomously. **External tool** at `~/.ai/Skills/spiral/` ([wenjyue84/spiral](https://github.com/wenjyue84/spiral)). Ralph (implementation engine) is bundled inside the spiral repo at `spiral/ralph/`. Project config in `spiral.config.sh`.

### Phases per iteration

| Phase | Name | Action |
|-------|------|--------|
| R | RESEARCH | Claude agent searches LHDN/government sources → `.spiral/_research_output.json` (uses Gemini web search) |
| T | TEST SYNTH | `synthesize_tests.py` → `.spiral/_test_stories_output.json` |
| M | MERGE | `merge_stories.py` deduplicates + patches `prd.json` |
| G | GATE | Human checkpoint: proceed / skip / quit (or auto via `--gate`) |
| I | IMPLEMENT | `ralph.sh` implementation loop (parallel worktree workers supported) |
| V | VALIDATE | HTTP test suite; fresh report for check_done |
| C | CHECK DONE | Exit if all stories pass, else loop |

### Usage

```bash
# Fully autonomous (research → merge → implement)
bash ~/.ai/Skills/spiral/spiral.sh 20 --gate proceed

# Research-only (adds stories, skips implementation)
bash ~/.ai/Skills/spiral/spiral.sh 1 --gate skip

# Parallel implementation with 3 workers
bash ~/.ai/Skills/spiral/spiral.sh 5 --gate proceed --ralph-workers 3

# Skip research, implement only
bash ~/.ai/Skills/spiral/spiral.sh 5 --gate proceed --skip-research

# Crash recovery: re-running resumes from last checkpoint (.spiral/_checkpoint.json)
```

### Key flags

| Flag | Default | Description |
|------|---------|-------------|
| `--gate proceed\|skip\|quit` | interactive | Auto-answer gate prompts |
| `--ralph-iters N` | 120 | Max inner implementation iterations |
| `--ralph-workers N` | 1 | Parallel worktree workers (>1 = parallel mode) |
| `--skip-research` | off | Skip Phase R, run T+M+I only |
| `--capacity-limit N` | 50 | Skip Phase R if pending stories exceed threshold |
| `--no-monitor` | on | Disable per-worker terminal windows |
| `--config PATH` | `spiral.config.sh` | Override config file location |

### Project-specific files

| File | Purpose |
|------|---------|
| `spiral.config.sh` | Project config (Python path, deploy cmd, patch dirs, Gemini prompts) |
| `scripts/spiral/research_prompt.md` | LHDN-specific research prompt template |
| `.spiral/` | Runtime scratch (gitignored): checkpoint, logs, research output |

## EC2 Deploy Script

`bash deploy-ec2.sh` — one-command hot-deploy without image rebuild. Runs `git pull`, `docker cp` both apps into backend, assets into frontend, `sync_fixtures`, `clear-cache`, restarts workers.

```bash
# From local laptop
ssh -i prisma-erp-key.pem ubuntu@122.248.223.69 "cd prisma-erp && bash deploy-ec2.sh"
```

## Wake-on-Demand Infrastructure

- **Domain:** `prismaerp.click` (Route 53 → CloudFront → EC2)
- **When EC2 is stopped:** CloudFront 502/503/504 errors redirect to `/wakeup` → Lambda starts EC2 → polls `/login` readiness → redirects to site
- **EC2 auto-stop:** cron checks nginx idle every 5 min, shuts down after 15 min idle
- **EC2 auto-start:** systemd service auto-starts Docker Compose on boot
- **Infra files:** `infra/wake-on-demand/` (lambda_function.py, auto-stop.sh, deploy.sh)

## Key files

| File | Purpose |
|------|---------|
| `pwd-myinvois.yml` | Active compose (image: wenjyue/erpnext-myinvois:v16) |
| `Dockerfile.myinvois` | Source for DockerHub image rebuild |
| `prd.json` | Product requirements — 325 user stories (source of truth) |
| `progress.txt` | Human-readable implementation log |
| `spiral.config.sh` | SPIRAL project config (sources external `~/.ai/Skills/spiral/spiral.sh`) |
| `deploy-ec2.sh` | EC2 hot-deploy script |
| `setup_test_data.py` | LHDN test data seed |
| `prisma-erp-key.pem` | SSH key for EC2 (chmod 600) |

<!-- gitnexus:start -->
# GitNexus MCP

This project is indexed by GitNexus as **prisma-erp** (13855 symbols, 28160 relationships, 300 execution flows).

GitNexus provides a knowledge graph over this codebase — call chains, blast radius, execution flows, and semantic search.

## Always Start Here

For any task involving code understanding, debugging, impact analysis, or refactoring, you must:

1. **Read `gitnexus://repo/{name}/context`** — codebase overview + check index freshness
2. **Match your task to a skill below** and **read that skill file**
3. **Follow the skill's workflow and checklist**

> If step 1 warns the index is stale, run `npx gitnexus analyze` in the terminal first.

## Skills

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/refactoring/SKILL.md` |

## Tools Reference

| Tool | What it gives you |
|------|-------------------|
| `query` | Process-grouped code intelligence — execution flows related to a concept |
| `context` | 360-degree symbol view — categorized refs, processes it participates in |
| `impact` | Symbol blast radius — what breaks at depth 1/2/3 with confidence |
| `detect_changes` | Git-diff impact — what do your current changes affect |
| `rename` | Multi-file coordinated rename with confidence-tagged edits |
| `cypher` | Raw graph queries (read `gitnexus://repo/{name}/schema` first) |
| `list_repos` | Discover indexed repos |

## Resources Reference

Lightweight reads (~100-500 tokens) for navigation:

| Resource | Content |
|----------|---------|
| `gitnexus://repo/{name}/context` | Stats, staleness check |
| `gitnexus://repo/{name}/clusters` | All functional areas with cohesion scores |
| `gitnexus://repo/{name}/cluster/{clusterName}` | Area members |
| `gitnexus://repo/{name}/processes` | All execution flows |
| `gitnexus://repo/{name}/process/{processName}` | Step-by-step trace |
| `gitnexus://repo/{name}/schema` | Graph schema for Cypher |

## Graph Schema

**Nodes:** File, Function, Class, Interface, Method, Community, Process
**Edges (via CodeRelation.type):** CALLS, IMPORTS, EXTENDS, IMPLEMENTS, DEFINES, MEMBER_OF, STEP_IN_PROCESS

```cypher
MATCH (caller)-[:CodeRelation {type: 'CALLS'}]->(f:Function {name: "myFunc"})
RETURN caller.name, caller.filePath
```

<!-- gitnexus:end -->
