# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

This is a clone of `frappe/frappe_docker`, customised to run **ERPNext v16 + MyInvois (Malaysian LHDN e-invoicing)** locally via Docker. The upstream files (`pwd.yml`, `compose.yaml`) are unchanged; the active setup is entirely in the files added on top.

**Active compose file:** `pwd-myinvois.yml` (NOT `pwd.yml`)
**Active Docker image:** `frappe/erpnext-myinvois:v16` (built from `Dockerfile.myinvois`)
**Site name:** `frontend`
**ERPNext credentials:** `Administrator` / `admin`
**URL:** `http://localhost:8080`

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
