# PRD: LHDN-Compliant Payroll e-Invoicing Integration for ERPNext
<!-- prd_version: 1.0 | status: DRAFT | last_updated: 2026-02-26 -->
<!-- source_doc: docs/ERPNext LHDN Payroll E-Invoice Integration.md -->

---

## 0. Document Metadata

| Field | Value |
|---|---|
| **Project** | `lhdn_payroll_integration` — Frappe custom app |
| **ERPNext target** | v16 (also v15 compatible) |
| **Dependency** | `myinvois_erpgulf` app by ERPGulf (must be installed first) |
| **Mandate** | LHDN MyInvois, Malaysian e-Invoice, YA 2026+ |
| **Implementor** | Autonomous LLM coding agent |
| **Reference** | LHDN e-Invoice SDK v1.1 · MyInvois API · Frappe docs |

### How to read this PRD

- **Phases** are ordered by dependency — implement top to bottom.
- **User Stories** are numbered `US-NNN` and atomic. Each story maps to one logical unit of work.
- **Data Contracts** define exact field names, types, and valid values — do not infer.
- **Decision Trees** use `IF / ELSE IF / ELSE / END` pseudo-code — implement exactly.
- **Acceptance Criteria** are testable assertions (`GIVEN / WHEN / THEN`).
- Code blocks marked `[EXACT]` must be implemented as written; blocks marked `[PATTERN]` illustrate structure only.

---

## 1. Problem Statement & Scope

### 1.1 What this app does

When an ERPNext HR manager submits a **Salary Slip** or approves an **Expense Claim**, this app:

1. Evaluates whether the document is in scope for LHDN e-Invoice (most standard employees are **exempt**)
2. If in scope: asynchronously builds a UBL 2.1 JSON payload and submits it to LHDN via `myinvois_erpgulf`
3. Writes the LHDN response (UUID, status, QR code) back to the ERPNext document
4. Handles Status 1 polling, Status 3 error parsing, retries with exponential backoff
5. Supports cancellation (72-hour window) and credit note guidance
6. Runs a monthly consolidation job for grace-period batch submissions (code 004)

### 1.2 Scope boundaries

| In Scope | Out of Scope |
|---|---|
| Salary Slip (self-billed, contractors/agents) | Standard employee Salary Slips (exempt) |
| Expense Claim (contractor/reimbursement pathway) | Standard employee expense internal records |
| Self-billed e-Invoice generation | Outbound sales e-Invoices (handled by base myinvois_erpgulf) |
| Consolidated e-Invoice (grace period, code 004) | Purchase Invoice submission |
| LHDN sandbox + production environments | Production deployment infrastructure |
| Status polling + error parsing | Manual LHDN portal interaction |
| On-cancel workflow with 72h check | Modifying core ERPNext/HRMS/myinvois_erpgulf files |

### 1.3 Regulatory context (Phase 4 — current)

- **Grace period**: Phase 4 taxpayers (RM1M–RM5M turnover) → grace until **31 Dec 2026**
- **During grace period**: Consolidated monthly submission (code 004) is permitted
- **Post grace period**: Real-time per-document submission mandatory
- **High-value override**: Any single transaction > **RM 10,000** requires individual e-Invoice regardless of grace period
- **Self-billed mandate**: Payer assumes supplier role when payee cannot issue their own e-Invoice

---

## 2. Architecture Blueprint

### 2.1 Custom App Directory Structure

```
lhdn_payroll_integration/                  ← git root / bench app root
├── setup.py
├── MANIFEST.in
├── requirements.txt                       ← pin: frappe, myinvois_erpgulf
└── lhdn_payroll_integration/             ← Python package
    ├── __init__.py
    ├── hooks.py                           ← ALL hooks defined here
    ├── modules.txt                        ← "LHDN Payroll Integration"
    ├── patches.txt
    ├── config/
    │   └── desktop.py
    ├── fixtures/                          ← exported via bench export-fixtures
    │   ├── custom_fields.json             ← all custom field definitions
    │   └── lhdn_msic_codes.json           ← MSIC code master data
    ├── lhdn_payroll_integration/          ← module folder
    │   └── module_def.json
    ├── services/                          ← business logic layer
    │   ├── __init__.py
    │   ├── exemption_filter.py            ← US-007
    │   ├── payload_builder.py             ← US-009, US-010, US-019
    │   ├── submission_service.py          ← US-011, US-012
    │   ├── status_poller.py               ← US-013, US-014
    │   ├── retry_service.py               ← US-015
    │   ├── consolidation_service.py       ← US-018, US-019
    │   └── cancellation_service.py        ← US-016, US-017
    └── utils/
        ├── __init__.py
        ├── validation.py                  ← US-008 input guards
        ├── decimal_utils.py               ← precise monetary arithmetic
        └── date_utils.py                  ← UTC ISO 8601 formatting
```

### 2.2 Integration Points with `myinvois_erpgulf`

> **Critical rule**: Never modify `myinvois_erpgulf` source files.

**Architecture reality** (confirmed via repo inspection):
`myinvois_erpgulf`'s submission pipeline (`original.py`, `createxml.py`) is tightly coupled to the `Sales Invoice` DocType. Its XML-building functions (`company_data()`, `customer_data()`, `invoice_line_item()`) each accept a `sales_invoice_doc` Frappe document object — they cannot be cleanly called with a Salary Slip.

**Chosen approach: Borrow token, own the XML.**
This app will:
1. Use `taxpayerlogin.get_access_token()` — the only cleanly reusable function — to obtain a bearer token stored in `Company.custom_bearer_token`.
2. Build its own UBL 2.1 XML using Python's `xml.etree.ElementTree` (same spec, own code).
3. POST directly to the LHDN submission endpoint (same HTTP call that `original.py` makes).

```python
# [EXACT] — the only myinvois_erpgulf import this app needs
from myinvois_erpgulf.myinvois_erpgulf.taxpayerlogin import get_access_token
```

**How `get_access_token(doc)` works** (confirmed):
- `doc` = Company name (string) or dict with `"name"` key
- Reads `Company.custom_client_id`, `Company.custom_client_secret`, `Company.custom_integration_type`
- POSTs to `{custom_sandbox_url or custom_production_url}/connect/token` with `grant_type=client_credentials`
- Saves returned `access_token` to `Company.custom_bearer_token` and returns the full token response dict
- Token lifetime: **60 minutes** — cache and reuse, do not generate per-request

**HTTP submission format** (what myinvois_erpgulf's `submission_url()` does — replicate this):
```python
import hashlib, base64

xml_bytes = xml_string.encode("utf-8")
doc_hash = hashlib.sha256(xml_bytes).hexdigest()
encoded_xml = base64.b64encode(xml_bytes).decode("utf-8")

payload = {
    "documents": [{
        "format":       "XML",
        "document":     encoded_xml,       # base64 of raw XML bytes
        "documentHash": doc_hash,          # SHA-256 hex of raw XML bytes
        "codeNumber":   _extract_code_number(docname),  # numeric suffix of name
    }]
}
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type":  "application/json",
}
response = requests.post(submission_url, json=payload, headers=headers, timeout=30)
```

**API response structure** (HTTP 202):
```json
{
  "submissionUid": "HJSD13P2H4B14SD5MLSDFSD54",
  "acceptedDocuments": [{"uuid": "...", "invoiceCodeNumber": "001"}],
  "rejectedDocuments": [{"invoiceCodeNumber": "002", "error": {"code": "CF327", ...}}]
}
```

**UBL XML namespaces** (must be exact for LHDN to accept):
```python
# [EXACT] — declare these on the root element
NS = {
    "":    "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
}
```

### 2.3 Dependency Graph

```
[ERPNext HRMS]
    Salary Slip (on_submit) ──→ [hooks.py: enqueue_salary_slip_submission]
    Expense Claim (on_submit) ─→ [hooks.py: enqueue_expense_claim_submission]
    Salary Slip (on_cancel) ──→ [hooks.py: handle_salary_slip_cancel]
                                        │
                                        ▼
                               [exemption_filter.py]
                               (standard employee? → EXIT)
                                        │
                                        ▼ (if in-scope)
                               frappe.enqueue → Redis queue
                                        │
                                        ▼ (background worker)
                               [payload_builder.py]
                               UBL 2.1 dict construction
                                        │
                                        ▼
                               [submission_service.py]
                               calls myinvois_erpgulf → LHDN API
                                        │
                          ┌─────────────┴─────────────┐
                    Status 1                     Status 2/3
                  (Pending)                   (Valid/Invalid)
                       │                            │
                       ▼                            ▼
              [status_poller.py]          write UUID/QR/status
              hourly scheduled job        back to Frappe doc
```

### 2.4 hooks.py Structure

```python
# [EXACT] lhdn_payroll_integration/hooks.py

app_name = "lhdn_payroll_integration"
app_title = "LHDN Payroll Integration"
app_publisher = "Prisma Technology"
app_description = "LHDN MyInvois self-billed e-Invoice integration for payroll"
app_version = "1.0.0"
app_license = "MIT"

# Document event hooks — observer pattern
doc_events = {
    "Salary Slip": {
        "on_submit": "lhdn_payroll_integration.services.submission_service.enqueue_salary_slip_submission",
        "on_cancel": "lhdn_payroll_integration.services.cancellation_service.handle_salary_slip_cancel",
    },
    "Expense Claim": {
        "on_submit": "lhdn_payroll_integration.services.submission_service.enqueue_expense_claim_submission",
        "on_cancel": "lhdn_payroll_integration.services.cancellation_service.handle_expense_claim_cancel",
    },
}

# Scheduled jobs
scheduler_events = {
    "hourly": [
        "lhdn_payroll_integration.services.status_poller.poll_pending_documents",
    ],
    "monthly": [
        "lhdn_payroll_integration.services.consolidation_service.run_monthly_consolidation",
    ],
}

# Install/migrate hooks
after_install = "lhdn_payroll_integration.install.after_install"
after_migrate = "lhdn_payroll_integration.install.after_migrate"

# Fixtures to auto-import
fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "LHDN Payroll Integration"]]},
    {"dt": "LHDN MSIC Code"},
]
```

---

## 3. Implementation Phases

Implement in this exact order — each phase depends on the previous.

| Phase | Name | Stories | Deliverable |
|---|---|---|---|
| **1** | Foundation | US-001 – US-006 | App scaffold + all custom fields + MSIC master |
| **2** | Core Submission | US-007 – US-012 | End-to-end self-billed submission (async) |
| **3** | Status Management | US-013 – US-015 | Polling + error parsing + retry |
| **4** | Cancellation | US-016 – US-017 | Cancel flow + credit note guard |
| **5** | Consolidation | US-018 – US-019 | Monthly batch (code 004) |
| **6** | Hardening | US-020 – US-022 | Env toggle + RBAC + 5 mandatory tests |

---

## 4. User Stories

---

### Phase 1: Foundation

---

#### US-001 — Create custom app scaffold

**As a** developer,
**I want** a Frappe custom app named `lhdn_payroll_integration`,
**so that** all integration code is isolated from core ERPNext and `myinvois_erpgulf`.

**Implementation notes:**
- Run: `bench new-app lhdn_payroll_integration` (inside Docker container)
- Set `app_name`, `app_title`, `app_publisher` in `hooks.py` as shown in §2.4
- Add `myinvois_erpgulf` and `hrms` as dependencies in `requirements.txt`
- Install: `bench --site frontend install-app lhdn_payroll_integration`

**Acceptance criteria:**
```
GIVEN the app is installed
WHEN `bench --site frontend list-apps` is run
THEN `lhdn_payroll_integration` appears in the output
```

**Files to create:**
- `lhdn_payroll_integration/hooks.py` (full content per §2.4)
- `lhdn_payroll_integration/modules.txt` (single line: `LHDN Payroll Integration`)
- `lhdn_payroll_integration/install.py` (stub `after_install` and `after_migrate`)

---

#### US-002 — Add custom fields to Employee DocType

**As a** system, **I need** Employee records to carry LHDN tax metadata,
**so that** the payload builder can read TIN, ID type, MSIC code, and submission flag.

**Custom fields to add** (all under module `LHDN Payroll Integration`, insert after field `employment_type`):

| `fieldname` | `label` | `fieldtype` | `options` / `default` | `mandatory_depends_on` | Notes |
|---|---|---|---|---|---|
| `custom_lhdn_section` | LHDN Malaysia Setup | Section Break | — | — | Section header |
| `custom_requires_self_billed_invoice` | Requires Self-Billed e-Invoice | Check | 0 | — | **Master boolean**: if unchecked, entire submission is skipped |
| `custom_lhdn_tin` | Tax Identification Number (TIN) | Data | — | `eval:doc.custom_requires_self_billed_invoice` | Validated: `^IG\d{11}$` (individual) or `^[A-Z]\d{9}0$` (non-individual) |
| `custom_id_type` | ID Document Type | Select | NRIC\nPassport\nBusiness Registration Number\nArmy ID | `eval:doc.custom_requires_self_billed_invoice` | — |
| `custom_id_value` | ID Document Number | Data | — | `eval:doc.custom_requires_self_billed_invoice` | Max 20 chars |
| `custom_msic_code` | MSIC Code | Link | LHDN MSIC Code | — | Default: `78300` (standard HR) |
| `custom_is_foreign_worker` | Foreign Worker / Non-Resident | Check | 0 | — | When checked → TIN auto-set to `EI00000000010` on save |
| `custom_bank_account_number` | Bank Account Number | Data | — | — | Max 150 chars (LHDN validation rule) |

**Implementation:**

Define these in `fixtures/custom_fields.json` as a JSON array of Custom Field doctype records. Use `frappe.reload_doc` in `after_install` to apply.

**Acceptance criteria:**
```
GIVEN the app is installed and migrated
WHEN an Employee record is opened in the UI
THEN the "LHDN Malaysia Setup" section is visible with all 7 fields above
AND checking "Requires Self-Billed e-Invoice" makes TIN, ID Type, ID Value mandatory
```

---

#### US-003 — Add custom fields to Salary Component DocType

**As a** finance team member, **I need** each Salary Component to carry an LHDN classification code,
**so that** the payload builder knows which of the 45 LHDN codes to assign each line item.

| `fieldname` | `label` | `fieldtype` | `options` |
|---|---|---|---|
| `custom_lhdn_classification_code` | LHDN Classification Code | Select | See §7.1 for full option string list |

**Default value rule:** If blank, the submission service treats the component as `TAX_EXEMPT` (tax type "E") and does not assign a classification code — log a warning but do not block submission.

**Acceptance criteria:**
```
GIVEN a Salary Component record
WHEN the LHDN Classification Code dropdown is clicked
THEN all codes from §7.1 appear as options
AND saving the component with a code persists it to the database
```

---

#### US-004 — Add custom fields to Salary Slip DocType

**As a** system, **I need** Salary Slips to store LHDN response data,
**so that** finance teams can track submission status and access QR codes.

| `fieldname` | `label` | `fieldtype` | `read_only` | Notes |
|---|---|---|---|---|
| `custom_lhdn_section` | LHDN e-Invoice Status | Section Break | 0 | — |
| `custom_lhdn_status` | LHDN Status | Select | 1 | Options: `\nPending\nSubmitted\nValid\nInvalid\nExempt\nCancelled` |
| `custom_lhdn_uuid` | LHDN Document UUID | Data | 1 | Returned by API on submission |
| `custom_lhdn_submission_datetime` | Submitted to LHDN At | Datetime | 1 | UTC timestamp of successful enqueue |
| `custom_lhdn_validated_datetime` | Validated by LHDN At | Datetime | 1 | UTC timestamp when Status 2 received |
| `custom_lhdn_qr_code` | e-Invoice QR Code | HTML | 1 | Render `<img src="..." />` from API response |
| `custom_lhdn_qr_url` | QR Code URL | Data | 1 | Raw URL for programmatic use |
| `custom_error_log` | LHDN Validation Errors | Text Editor | 1 | Raw JSON error from Status 3 response |
| `custom_retry_count` | Retry Attempts | Int | 1 | Default 0; incremented by retry service |
| `custom_is_consolidated` | Included in Consolidated Batch | Check | 1 | Set to 1 when processed by consolidation job |

**Acceptance criteria:**
```
GIVEN a Salary Slip is submitted and processed by the background worker
WHEN the document is reopened
THEN custom_lhdn_status is "Pending" (Status 1), "Valid" (Status 2), or "Invalid" (Status 3)
AND custom_lhdn_uuid contains a non-empty UUID string if status is not "Invalid"
```

---

#### US-005 — Add custom fields to Expense Claim DocType

**As a** system, **I need** Expense Claims to store LHDN response data and employee-provided receipt details,
**so that** reimbursement claims can be audited for e-Invoice compliance.

| `fieldname` | `label` | `fieldtype` | `read_only` | Notes |
|---|---|---|---|---|
| `custom_lhdn_section` | LHDN e-Invoice | Section Break | 0 | — |
| `custom_expense_category` | Expense e-Invoice Category | Select | 0 | Options: `\nSelf-Billed Required\nEmployee Receipt Provided\nOverseas - Exempt` |
| `custom_employee_receipt_uuid` | Employee's Receipt UUID | Data | 0 | For "Employee Receipt Provided" path: LHDN UUID from employee's personal receipt |
| `custom_employee_receipt_qr_url` | Employee's Receipt QR URL | Data | 0 | QR URL from employee's personal receipt |
| `custom_lhdn_status` | LHDN Status | Select | 1 | Same options as Salary Slip |
| `custom_lhdn_uuid` | LHDN Document UUID | Data | 1 | — |
| `custom_lhdn_qr_url` | QR Code URL | Data | 1 | — |
| `custom_error_log` | LHDN Validation Errors | Text Editor | 1 | — |
| `custom_retry_count` | Retry Attempts | Int | 1 | Default 0 |

**Acceptance criteria:**
```
GIVEN an Expense Claim with custom_expense_category = "Overseas - Exempt"
WHEN the claim is submitted
THEN no LHDN API call is made
AND custom_lhdn_status is set to "Exempt"
```

---

#### US-006 — Create LHDN MSIC Code DocType and seed data

**As a** system, **I need** a lookup table of LHDN-approved Malaysia Standard Industrial Classification (MSIC) codes,
**so that** Employee records can link to valid codes for payload population.

**DocType spec:**

| DocType name | `LHDN MSIC Code` |
|---|---|
| `name` (fieldname) | MSIC code, e.g., `78300` |
| `code` | Data, mandatory, e.g., `78300` |
| `description` | Data, mandatory, e.g., `Labour supply services` |
| `sector` | Data, e.g., `Services` |

**Seed data (minimum required — include in `fixtures/lhdn_msic_codes.json`):**

```json
[
  {"code": "78300", "description": "Labour supply services", "sector": "Services"},
  {"code": "00000", "description": "Not Applicable", "sector": "General"},
  {"code": "46900", "description": "Non-specialised wholesale trade", "sector": "Trade"},
  {"code": "74909", "description": "Other professional services n.e.c.", "sector": "Professional"}
]
```

> Full MSIC code list: https://sdk.myinvois.hasil.gov.my/codes/msic-codes/
> Agent: Fetch and include all codes in the fixture file.

**Acceptance criteria:**
```
GIVEN the app is installed
WHEN bench --site frontend console is opened
THEN frappe.get_all("LHDN MSIC Code") returns at least 4 records
AND the Employee "MSIC Code" Link field can select "78300 - Labour supply services"
```

---

### Phase 2: Core Submission

---

#### US-007 — Exemption filter service

**As a** system, **I need** an exemption filter that determines if a document requires LHDN submission,
**so that** standard employees are never submitted to LHDN.

**File:** `lhdn_payroll_integration/services/exemption_filter.py`

**Decision Tree:**

```
FUNCTION should_submit_to_lhdn(doctype, docname) → bool:

  IF doctype == "Salary Slip":
    employee = frappe.get_doc("Employee", doc.employee)
    IF employee.custom_requires_self_billed_invoice == False:
      RETURN False                          # standard employment income — exempt
    IF doc.net_pay <= 0:
      RETURN False                          # zero or negative slip — skip
    RETURN True

  ELSE IF doctype == "Expense Claim":
    IF doc.custom_expense_category == "Overseas - Exempt":
      RETURN False                          # foreign receipt — exempt
    IF doc.custom_expense_category == "Employee Receipt Provided":
      RETURN False                          # employee holds the receipt — exempt
    IF doc.custom_expense_category == "Self-Billed Required":
      employee = frappe.get_doc("Employee", doc.employee)
      IF employee.custom_requires_self_billed_invoice == False:
        RETURN False
      RETURN True
    RETURN False                            # uncategorised — safe default: skip

  RETURN False
```

**Acceptance criteria:**
```
GIVEN an Employee with custom_requires_self_billed_invoice = False
WHEN should_submit_to_lhdn("Salary Slip", slip.name) is called
THEN it returns False

GIVEN an Employee with custom_requires_self_billed_invoice = True
WHEN should_submit_to_lhdn("Salary Slip", slip.name) is called
THEN it returns True
```

---

#### US-008 — Salary Slip and Expense Claim submission hooks

**As a** system, **I need** `on_submit` hooks that run the exemption filter and enqueue the background job,
**so that** submission is decoupled from the database transaction.

**File:** `lhdn_payroll_integration/services/submission_service.py`

```python
# [EXACT]
import frappe
from lhdn_payroll_integration.services.exemption_filter import should_submit_to_lhdn
from lhdn_payroll_integration.utils.validation import validate_document_name_length


def enqueue_salary_slip_submission(doc, method):
    if not should_submit_to_lhdn("Salary Slip", doc.name):
        frappe.db.set_value("Salary Slip", doc.name, "custom_lhdn_status", "Exempt")
        return

    validate_document_name_length(doc.name)  # raises ValidationError if > 50 chars

    frappe.enqueue(
        "lhdn_payroll_integration.services.submission_service.process_salary_slip",
        queue="short",
        timeout=300,
        is_async=True,
        enqueue_after_commit=True,   # CRITICAL: wait for DB commit
        docname=doc.name,
    )
    frappe.db.set_value("Salary Slip", doc.name, "custom_lhdn_status", "Pending")


def enqueue_expense_claim_submission(doc, method):
    if not should_submit_to_lhdn("Expense Claim", doc.name):
        frappe.db.set_value("Expense Claim", doc.name, "custom_lhdn_status", "Exempt")
        return

    validate_document_name_length(doc.name)

    frappe.enqueue(
        "lhdn_payroll_integration.services.submission_service.process_expense_claim",
        queue="short",
        timeout=300,
        is_async=True,
        enqueue_after_commit=True,
        docname=doc.name,
    )
    frappe.db.set_value("Expense Claim", doc.name, "custom_lhdn_status", "Pending")
```

**Critical:** `enqueue_after_commit=True` ensures the background worker only runs after MariaDB commits the Salary Slip, preventing `DoesNotExistError` in the worker.

**Acceptance criteria:**
```
GIVEN a standard employee Salary Slip is submitted
WHEN on_submit fires
THEN custom_lhdn_status is "Exempt" and NO job is queued

GIVEN a contractor Salary Slip is submitted
WHEN on_submit fires
THEN custom_lhdn_status is "Pending" and a job appears in the Redis queue
```

---

#### US-009 — Payload builder: Salary Slip → self-billed UBL JSON

**As a** background worker, **I need** a function that maps a Salary Slip to a LHDN-compliant UBL 2.1 JSON payload,
**so that** `myinvois_erpgulf` can sign and transmit it.

**File:** `lhdn_payroll_integration/services/payload_builder.py`

**Self-billed data inversion rule:**
> In a self-billed e-Invoice, the **Employer (payer) = Buyer**, the **Contractor/Agent (payee) = Supplier**.

**Architecture note**: LHDN accepts UBL 2.1 **XML** (not a JSON dict). The XML is base64-encoded and submitted inside a JSON wrapper. This app builds XML using Python's `xml.etree.ElementTree`.

```python
# [PATTERN] — build_salary_slip_xml(docname: str) → str (raw XML string)
import hashlib
import base64
import xml.etree.ElementTree as ET
from decimal import Decimal
import frappe
from lhdn_payroll_integration.utils.decimal_utils import quantize, assert_totals_balance
from lhdn_payroll_integration.utils.date_utils import to_lhdn_datetime, to_lhdn_date
from lhdn_payroll_integration.utils.validation import validate_tin, sanitize_description

# UBL 2.1 namespaces — must be exact
UBL_NS  = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC_NS  = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS  = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
EXT_NS  = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"

ET.register_namespace("",    UBL_NS)
ET.register_namespace("cac", CAC_NS)
ET.register_namespace("cbc", CBC_NS)
ET.register_namespace("ext", EXT_NS)

cbc = lambda tag: f"{{{CBC_NS}}}{tag}"
cac = lambda tag: f"{{{CAC_NS}}}{tag}"


def build_salary_slip_xml(docname: str) -> str:
    """Returns raw UBL 2.1 XML string for a self-billed Salary Slip."""
    doc      = frappe.get_doc("Salary Slip", docname)
    employee = frappe.get_doc("Employee", doc.employee)
    company  = frappe.get_doc("Company", doc.company)

    # Totals — do NOT use doc.ytd_net_pay or compute_year_to_date() (v16 bug)
    total_excl = sum(quantize(Decimal(str(e.amount))) for e in doc.earnings)
    total_tax  = Decimal("0.00")
    total_incl = quantize(total_excl + total_tax)
    assert_totals_balance(total_excl, total_tax, total_incl)

    version = frappe.conf.get("lhdn_einvoice_version", "1.1")
    invoice_id = doc.name[:50]

    root = ET.Element(f"{{{UBL_NS}}}Invoice")
    _sub(root, cbc("ID"),               invoice_id)
    _sub(root, cbc("IssueDate"),        to_lhdn_date(doc.posting_date))
    _sub(root, cbc("IssueTime"),        to_lhdn_datetime(time_only=True))
    _sub(root, cbc("InvoiceTypeCode"),  "11", listVersionID=version)  # 11 = Self-Billed Invoice
    _sub(root, cbc("DocumentCurrencyCode"), doc.currency or "MYR")
    _sub(root, cbc("TaxCurrencyCode"),  doc.currency or "MYR")

    # Billing period
    period = ET.SubElement(root, cac("InvoicePeriod"))
    _sub(period, cbc("StartDate"), to_lhdn_date(doc.start_date))
    _sub(period, cbc("EndDate"),   to_lhdn_date(doc.end_date))

    # Supplier = Payee = Contractor/Agent (data inversion)
    supplier_tin = "EI00000000010" if employee.custom_is_foreign_worker \
                   else validate_tin(employee.custom_lhdn_tin, employee.custom_id_type)
    _build_party(root, "AccountingSupplierParty",
        name=employee.employee_name,
        tin=supplier_tin,
        id_scheme=_map_id_scheme(employee.custom_id_type),
        id_value=employee.custom_id_value or "000000000000",
        msic=employee.custom_msic_code or "00000",
        address=_get_employee_address(employee),
        contact=employee.cell_number or "NA",
    )

    # Buyer = Payer = Employer
    _build_party(root, "AccountingCustomerParty",
        name=company.company_name,
        tin=company.custom_company_tin_number,
        id_scheme="BRN",
        id_value=company.company_registration_number or company.tax_id or "000000000000",
        msic=company.custom_msic_code_ or "00000",
        address=_get_company_address(company),
        contact=company.phone_no or "NA",
    )

    # Tax total (all exempt for payroll)
    tax_total_el = ET.SubElement(root, cac("TaxTotal"))
    _sub(tax_total_el, cbc("TaxAmount"), str(total_tax), currencyID=doc.currency or "MYR")
    subtotal_el = ET.SubElement(tax_total_el, cac("TaxSubtotal"))
    _sub(subtotal_el, cbc("TaxableAmount"), str(total_excl), currencyID=doc.currency or "MYR")
    _sub(subtotal_el, cbc("TaxAmount"),     str(total_tax),  currencyID=doc.currency or "MYR")
    cat_el = ET.SubElement(subtotal_el, cac("TaxCategory"))
    _sub(cat_el, cbc("ID"), "E")           # E = Tax Exempt
    _sub(cat_el, cbc("Percent"), "0.00")
    _sub(cat_el, cbc("TaxExemptionReason"), "Employment income — payroll e-Invoice")
    scheme_el = ET.SubElement(cat_el, cac("TaxScheme"))
    _sub(scheme_el, cbc("ID"), "OTH", schemeAgencyID="6", schemeID="UN/ECE 5153")

    # Legal monetary total
    lmt_el = ET.SubElement(root, cac("LegalMonetaryTotal"))
    _sub(lmt_el, cbc("LineExtensionAmount"), str(total_excl),  currencyID=doc.currency or "MYR")
    _sub(lmt_el, cbc("TaxExclusiveAmount"),  str(total_excl),  currencyID=doc.currency or "MYR")
    _sub(lmt_el, cbc("TaxInclusiveAmount"),  str(total_incl),  currencyID=doc.currency or "MYR")
    _sub(lmt_el, cbc("PayableAmount"),       str(total_incl),  currencyID=doc.currency or "MYR")

    # Invoice lines — one per earning component (do NOT read YTD aggregates)
    for idx, earning in enumerate(doc.earnings, start=1):
        component = frappe.get_doc("Salary Component", earning.salary_component)
        amount    = quantize(Decimal(str(earning.amount)))
        class_code = component.custom_lhdn_classification_code or "022"

        line_el = ET.SubElement(root, cac("InvoiceLine"))
        _sub(line_el, cbc("ID"), str(idx))
        qty_el = _sub(line_el, cbc("InvoicedQuantity"), "1", unitCode="C62")
        _sub(line_el, cbc("LineExtensionAmount"), str(amount), currencyID=doc.currency or "MYR")

        item_el = ET.SubElement(line_el, cac("Item"))
        _sub(item_el, cbc("Description"), sanitize_description(earning.salary_component))
        class_el = ET.SubElement(item_el, cac("CommodityClassification"))
        _sub(class_el, cbc("ItemClassificationCode"), class_code, listID="CLASS")

        price_el = ET.SubElement(line_el, cac("Price"))
        _sub(price_el, cbc("PriceAmount"), str(amount), currencyID=doc.currency or "MYR")

    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def prepare_submission_wrapper(xml_string: str, doc_name: str) -> dict:
    """Wrap XML in the LHDN submission JSON format: base64 + SHA-256 hash."""
    xml_bytes   = xml_string.encode("utf-8")
    doc_hash    = hashlib.sha256(xml_bytes).hexdigest()
    encoded_xml = base64.b64encode(xml_bytes).decode("utf-8")
    code_number = "".join(filter(str.isdigit, doc_name)) or "001"  # numeric suffix
    return {
        "documents": [{
            "format":       "XML",
            "document":     encoded_xml,
            "documentHash": doc_hash,
            "codeNumber":   code_number[:50],
        }]
    }


# Helper: sub-element with optional attributes
def _sub(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, tag, **attrs)
    if text is not None:
        el.text = str(text)
    return el
```

**Mathematical integrity rule (CRITICAL):**
> Use Python `decimal.Decimal` for ALL monetary calculations.
> Never use `float`. Quantize to 2 decimal places using `ROUND_HALF_UP`.
> Verify: `TotalExcludingTax + TotalTaxAmount == TotalIncludingTax` before returning.
> If mismatch, raise `frappe.ValidationError` with message including the amounts.

**V16 payroll bug workaround:**
> Do NOT call `doc.compute_year_to_date()` or read `ytd_net_pay`.
> Calculate totals exclusively from `doc.earnings` child table.
> See §8 for full bug description.

**Acceptance criteria:**
```
GIVEN a Salary Slip for contractor Ahmad with net_pay = 5000.00
WHEN build_salary_slip_payload(slip.name) is called
THEN the returned dict has _eInvoiceTypeCode = "11"
AND SupplierTIN = employee.custom_lhdn_tin
AND BuyerTIN = company.custom_company_tin_number
AND TotalExcludingTax + TotalTaxAmount == TotalIncludingTax (exact Decimal equality)
AND all monetary strings have exactly 2 decimal places
```

---

#### US-010 — Payload builder: Expense Claim → self-billed UBL JSON

**As a** background worker, **I need** a function that maps a self-billed Expense Claim to a LHDN payload,
**so that** qualifying contractor expense claims are submitted.

**File:** `lhdn_payroll_integration/services/payload_builder.py` (additional function)

**Logic:**
- Same buyer/supplier inversion as US-009
- Line items come from `doc.expenses` child table (Expense Claim Detail)
- Each line's `expense_type` links to Expense Type doctype — add `custom_lhdn_classification_code` to Expense Type as well (add to Phase 1 fixtures, classification code `027` for Reimbursement is typical)
- Use `doc.total_claimed_amount` as gross, `doc.total_sanctioned_amount` as net payable

**Acceptance criteria:**
```
GIVEN an Expense Claim with custom_expense_category = "Self-Billed Required"
WHEN build_expense_claim_payload(claim.name) is called
THEN the returned dict has _eInvoiceTypeCode = "11"
AND line items correspond to doc.expenses rows
AND TotalIncludingTax == doc.total_sanctioned_amount (Decimal)
```

---

#### US-011 — Submission service: call myinvois_erpgulf and handle response

**As a** background worker, **I need** a function that sends the payload to `myinvois_erpgulf` and handles the response,
**so that** LHDN status, UUID, and QR code are written back to ERPNext.

**File:** `lhdn_payroll_integration/services/submission_service.py`

```python
# [PATTERN]
import requests
from myinvois_erpgulf.myinvois_erpgulf.taxpayerlogin import get_access_token


def process_salary_slip(docname: str):
    """Background worker entry point for Salary Slip submission."""
    try:
        xml_string = build_salary_slip_xml(docname)
        doc = frappe.get_doc("Salary Slip", docname)
        wrapper = prepare_submission_wrapper(xml_string, docname)
        response = _post_to_lhdn(doc.company, wrapper)
        _write_response_to_doc("Salary Slip", docname, response)
    except (requests.ConnectionError, requests.Timeout) as e:
        schedule_retry("Salary Slip", docname, e)
    except Exception as e:
        frappe.log_error(f"LHDN submission failed for {docname}: {e}", "LHDN Submission")
        frappe.db.set_value("Salary Slip", docname, {
            "custom_lhdn_status": "Invalid",
            "custom_error_log": str(e),
        })


def _post_to_lhdn(company_name: str, wrapper: dict) -> dict:
    """POST wrapper JSON to LHDN API. Returns parsed response dict."""
    # Get token — myinvois_erpgulf caches it in Company.custom_bearer_token
    token_response = get_access_token(company_name)
    token = token_response.get("access_token") or \
            frappe.db.get_value("Company", company_name, "custom_bearer_token")

    company = frappe.get_doc("Company", company_name)
    env = frappe.conf.get("lhdn_environment", "sandbox")
    base_url = frappe.conf.get(f"lhdn_{env}_url") or \
               (company.custom_sandbox_url if env == "sandbox" else company.custom_production_url)

    url = f"{base_url.rstrip('/')}/api/v1.0/documentsubmissions"
    resp = requests.post(
        url,
        json=wrapper,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if resp.status_code == 401:
        # Token expired — refresh once and retry
        token_response = get_access_token(company_name)
        token = token_response["access_token"]
        resp = requests.post(url, json=wrapper,
                             headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                             timeout=30)
    resp.raise_for_status()
    return resp.json()


def _write_response_to_doc(doctype: str, docname: str, lhdn_response: dict):
    """Parse LHDN 202 response and write UUID/status back to Frappe document.

    LHDN 202 response shape:
    {
      "submissionUid": "HJSD...",
      "acceptedDocuments": [{"uuid": "...", "invoiceCodeNumber": "001"}],
      "rejectedDocuments": [{"invoiceCodeNumber": "001", "error": {...}}]
    }
    """
    accepted = lhdn_response.get("acceptedDocuments", [])
    rejected  = lhdn_response.get("rejectedDocuments", [])
    submission_uid = lhdn_response.get("submissionUid", "")

    if accepted:
        doc_uuid = accepted[0].get("uuid", "")
        update_fields = {
            "custom_lhdn_uuid": doc_uuid,
            "custom_lhdn_submission_datetime": frappe.utils.now_datetime(),
            "custom_lhdn_status": "Submitted",   # Status 1 — poll for final status
        }
    elif rejected:
        update_fields = {
            "custom_lhdn_status": "Invalid",
            "custom_error_log": _format_rejection_errors(rejected[0]),
        }
    else:
        update_fields = {"custom_lhdn_status": "Invalid", "custom_error_log": str(lhdn_response)}

    frappe.db.set_value(doctype, docname, update_fields)
    return submission_uid   # for immediate polling if needed
```

**Acceptance criteria:**
```
GIVEN a valid payload is submitted to the LHDN sandbox
WHEN the API returns status 1
THEN custom_lhdn_status = "Submitted" and custom_lhdn_uuid is non-empty

GIVEN a valid payload is submitted to the LHDN sandbox
WHEN the API returns status 2
THEN custom_lhdn_status = "Valid" and custom_lhdn_qr_url is non-empty
AND custom_lhdn_validated_datetime is set
```

---

#### US-012 — Input validation and sanitization

**As a** system, **I need** pre-flight validation before payload submission,
**so that** avoidable API rejections (data format errors) are caught early.

**File:** `lhdn_payroll_integration/utils/validation.py`

**Validation rules** (implement all — these are LHDN API-enforced):

| Rule | Implementation |
|---|---|
| TIN format: individual | Regex `^IG\d{11}$` — raise `ValidationError` if fails |
| TIN format: non-individual | Regex `^[A-Z]\d{8,9}0$` — raise `ValidationError` if fails |
| TIN: foreign worker | Inject `EI00000000010` — do not validate |
| Doc name length | `len(docname) <= 50` — if longer, apply SHA-256 truncation to 50 chars and log warning |
| Bank account length | `len(account) <= 150` — truncate silently with warning |
| Date fields | Must be `YYYY-MM-DD` format — never "N/A" or empty string |
| Description field | Strip internal HR remarks, performance scores, non-taxable identifiers |
| Monetary precision | All amounts must have exactly 2 decimal places |

**Acceptance criteria:**
```
GIVEN an employee with TIN "IG12345" (wrong length)
WHEN validate_tin("IG12345") is called
THEN frappe.ValidationError is raised with a descriptive message

GIVEN a doc name "HR-SAL-2026-0001-VERY-LONG-NAME-EXCEEDING-FIFTY-CHARACTERS-12345"
WHEN validate_document_name_length(name) is called
THEN the function returns a truncated name of exactly 50 characters
AND logs a frappe.logger warning
```

---

### Phase 3: Status Management

---

#### US-013 — Status polling scheduler

**As a** system, **I need** an hourly job that queries LHDN for the status of all "Submitted" (Status 1) documents,
**so that** documents are eventually updated to "Valid" or "Invalid".

**File:** `lhdn_payroll_integration/services/status_poller.py`

**Logic:**
```python
# [PATTERN]
def poll_pending_documents():
    for doctype in ["Salary Slip", "Expense Claim"]:
        pending = frappe.get_all(
            doctype,
            filters={"custom_lhdn_status": "Submitted"},
            fields=["name", "custom_lhdn_uuid"],
            limit=100,   # process in batches to avoid timeouts
        )
        for doc in pending:
            if not doc.custom_lhdn_uuid:
                continue
            try:
                status = get_document_status(doc.custom_lhdn_uuid)
                _write_response_to_doc(doctype, doc.name, status)
            except Exception as e:
                frappe.log_error(f"LHDN polling failed for {doc.name}: {e}", "LHDN Poller")
```

**Acceptance criteria:**
```
GIVEN a Salary Slip with custom_lhdn_status = "Submitted" and a valid UUID
WHEN poll_pending_documents() runs
THEN the LHDN API is queried with that UUID
AND if response is status 2, custom_lhdn_status is updated to "Valid"
AND if response is status 3, custom_lhdn_status is updated to "Invalid" and error_log is populated
```

---

#### US-014 — Error log parser for Status 3 (Invalid) responses

**As a** finance manager, **I need** LHDN validation errors displayed in plain language on the Salary Slip,
**so that** I can correct the data and re-submit without reading raw JSON.

**File:** `lhdn_payroll_integration/services/status_poller.py` (additional function)

**Expected LHDN Status 3 response format:**
```json
{
  "status": 3,
  "errors": [
    {
      "code": "CF204",
      "message": "Invalid TIN format",
      "field": "SupplierTIN",
      "value": "IG123"
    }
  ]
}
```

**Formatted output** (written to `custom_error_log`):
```
LHDN Validation Failed — 2 error(s)

[CF204] SupplierTIN: Invalid TIN format (submitted: "IG123")
[CF301] InvoiceTotalTax: Mathematical mismatch — TotalExclTax + TaxAmount ≠ TotalInclTax
```

**Acceptance criteria:**
```
GIVEN a Status 3 response with 2 errors
WHEN _format_error_log(response) is called
THEN the returned string has exactly 2 error lines in [CODE] field: message format
AND the raw JSON is appended below for debugging
```

---

#### US-015 — Retry with exponential backoff

**As a** system, **I need** failed submissions (network errors, HTTP 5xx) to be retried with exponential backoff,
**so that** transient LHDN outages do not cause permanent data loss.

**File:** `lhdn_payroll_integration/services/retry_service.py`

**Backoff formula:** `wait_seconds = min(2 ** retry_count * 60, 3600)` (max 1 hour)

**Retry cap:** 5 attempts maximum. After 5, set `custom_lhdn_status = "Invalid"` and write error log `"Max retries exceeded — manual intervention required"`.

**Trigger:** Only on network-level exceptions (`requests.ConnectionError`, `requests.Timeout`, HTTP 500/502/503). Do NOT retry on `ValidationError` or Status 3.

```python
# [PATTERN]
def schedule_retry(doctype: str, docname: str, error: Exception):
    doc = frappe.get_doc(doctype, docname)
    retry_count = (doc.custom_retry_count or 0) + 1

    if retry_count > 5:
        frappe.db.set_value(doctype, docname, {
            "custom_lhdn_status": "Invalid",
            "custom_error_log": "Max retries exceeded — manual intervention required",
        })
        return

    wait_seconds = min(2 ** retry_count * 60, 3600)
    frappe.db.set_value(doctype, docname, "custom_retry_count", retry_count)

    frappe.enqueue(
        f"lhdn_payroll_integration.services.submission_service.process_{doctype.lower().replace(' ', '_')}",
        queue="long",
        timeout=300,
        is_async=True,
        at=frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=wait_seconds),
        docname=docname,
    )
```

**Acceptance criteria:**
```
GIVEN a network timeout occurs during submission
WHEN _handle_submission_failure is called with a ConnectionError
THEN custom_retry_count is incremented by 1
AND a new job is queued with a delay of 2^retry_count * 60 seconds
AND custom_lhdn_status remains "Pending" (not "Invalid")

GIVEN retry_count reaches 5
WHEN the next failure occurs
THEN custom_lhdn_status = "Invalid"
AND custom_error_log = "Max retries exceeded — manual intervention required"
AND no further jobs are queued
```

---

### Phase 4: Cancellation

---

#### US-016 — Salary Slip cancellation hook with 72-hour window check

**As a** HR manager, **I need** the system to check whether a LHDN-submitted Salary Slip can be cancelled directly,
**so that** LHDN immutability rules are enforced.

**File:** `lhdn_payroll_integration/services/cancellation_service.py`

**Decision Tree:**
```
FUNCTION handle_salary_slip_cancel(doc, method):

  IF doc.custom_lhdn_status NOT IN ["Valid", "Submitted"]:
    RETURN    # not submitted — allow native Frappe cancel to proceed

  validated_at = doc.custom_lhdn_validated_datetime OR doc.custom_lhdn_submission_datetime
  hours_elapsed = (now_datetime() - validated_at).total_seconds() / 3600

  IF hours_elapsed <= 72:
    # Within window — call LHDN cancellation API
    enqueue cancellation job (async, enqueue_after_commit=True)
    frappe.msgprint("Cancellation submitted to LHDN. Status will update when confirmed.")

  ELSE:
    # Outside window — block native cancel, guide user
    frappe.throw(
      "This e-Invoice was validated more than 72 hours ago and cannot be directly cancelled "
      "with LHDN. Please create a Credit Note (Sales Invoice with type = Credit Note) to "
      "reverse this transaction. See LHDN Specific Guideline §4.2 for procedure.",
      exc=frappe.ValidationError
    )
```

**Acceptance criteria:**
```
GIVEN a Salary Slip with custom_lhdn_validated_datetime = 10 hours ago
WHEN the cancel button is clicked
THEN a LHDN cancellation API call is enqueued
AND frappe.msgprint shows confirmation message

GIVEN a Salary Slip with custom_lhdn_validated_datetime = 96 hours ago
WHEN the cancel button is clicked
THEN frappe.ValidationError is raised with credit note guidance
AND the Salary Slip status is NOT changed
```

---

#### US-017 — Async cancellation job

**As a** background worker, **I need** a job that calls the LHDN cancellation endpoint and updates the document,
**so that** the UI is not blocked while waiting for LHDN API response.

**File:** `lhdn_payroll_integration/services/cancellation_service.py`

**Logic:**
1. Call `cancel_invoice(uuid=doc.custom_lhdn_uuid)` from `myinvois_erpgulf`
2. On success: set `custom_lhdn_status = "Cancelled"` and allow `doc.cancel()` to proceed (call `frappe.get_doc(doctype, docname).cancel()`)
3. On LHDN API rejection: set `custom_error_log = api_error_message`, do NOT cancel the Frappe doc

**Acceptance criteria:**
```
GIVEN the LHDN cancellation API returns success
WHEN process_cancellation(docname) completes
THEN custom_lhdn_status = "Cancelled"
AND the Frappe document is cancelled (docstatus = 2)

GIVEN the LHDN cancellation API returns an error
WHEN process_cancellation(docname) completes
THEN custom_lhdn_status remains "Valid"
AND custom_error_log contains the API error message
AND the Frappe document remains submitted (docstatus = 1)
```

---

### Phase 5: Consolidated e-Invoice

---

#### US-018 — Monthly consolidation scheduler

**As a** system, **I need** a monthly job that aggregates all pending self-billed documents into a single consolidated payload,
**so that** Phase 4 grace period taxpayers can comply without per-document real-time submission.

**File:** `lhdn_payroll_integration/services/consolidation_service.py`

**Trigger:** Monthly scheduled job (runs on the 1st of each month, processes the previous month).
**Eligibility:** Only documents where `custom_lhdn_status = "Pending"` and `custom_is_consolidated = 0` for the target month.
**High-value override:** Any single document with `total_amount > 10000` must be submitted individually — exclude from consolidation batch.

**Acceptance criteria:**
```
GIVEN 50 Salary Slips with custom_lhdn_status = "Pending" from January 2026
AND none exceed RM 10,000
WHEN run_monthly_consolidation() executes on Feb 1
THEN a single consolidated payload is built with classification code "004"
AND all 50 slips have custom_is_consolidated = 1
AND all 50 slips have custom_lhdn_status updated to match the batch submission response

GIVEN 1 Salary Slip of RM 15,000 and 20 slips of RM 2,000 from January 2026
WHEN run_monthly_consolidation() executes
THEN the RM 15,000 slip is submitted individually (type "11")
AND only the 20 × RM 2,000 slips are in the consolidated batch
```

---

#### US-019 — Consolidated payload builder (code 004)

**As a** background worker, **I need** a function that aggregates multiple documents into a single classification 004 payload,
**so that** a single LHDN submission covers an entire month's worth of self-billed transactions.

**File:** `lhdn_payroll_integration/services/payload_builder.py` (additional function)

**Key differences from individual payload (US-009):**

| Field | Individual (US-009) | Consolidated (US-019) |
|---|---|---|
| `_eInvoiceTypeCode` | `"11"` | `"11"` (Self-Billed, but consolidated) |
| `ItemClassificationCode` | `"037"` or specific | `"004"` (Consolidated) |
| `_eInvoiceCode` | Original doc name | `CONSOL-{company}-{YYYY-MM}` |
| Buyer contact | Actual number | `"NA"` (permitted by SDK during grace period) |
| Line items | Per salary component | Per source document (one line per Salary Slip) |
| `BillingPeriodStartDate` | Slip start date | First day of target month |
| `BillingPeriodEndDate` | Slip end date | Last day of target month |

**Line item description format:**
```
"Self-billed commission/payroll — {doc.name} — {employee.employee_name} — {slip.end_date}"
```

**Acceptance criteria:**
```
GIVEN a list of 10 Salary Slip names
WHEN build_consolidated_payload(docnames, target_month="2026-01") is called
THEN the returned dict has ItemClassificationCode = "004"
AND has exactly 10 line items
AND TotalIncludingTax == sum of all slip net_pay amounts (Decimal)
```

---

### Phase 6: Hardening

---

#### US-020 — Environment toggle: sandbox vs production

**As a** system administrator, **I need** the LHDN endpoint URLs to be configurable without code changes,
**so that** the same app can run in sandbox (testing) or production mode.

**Implementation:**

In `common_site_config.json` (set via `bench set-config`):

```json
{
  "lhdn_environment": "sandbox",
  "lhdn_sandbox_url": "https://preprod-api.myinvois.hasil.gov.my",
  "lhdn_production_url": "https://api.myinvois.hasil.gov.my",
  "lhdn_einvoice_version": "1.1"
}
```

Read in code:
```python
env = frappe.conf.get("lhdn_environment", "sandbox")
base_url = frappe.conf.get(f"lhdn_{env}_url")
```

**Acceptance criteria:**
```
GIVEN lhdn_environment = "sandbox" in site config
WHEN any LHDN API call is made
THEN the request URL starts with "https://preprod-api.myinvois.hasil.gov.my"

GIVEN lhdn_environment = "production" in site config
WHEN any LHDN API call is made
THEN the request URL starts with "https://api.myinvois.hasil.gov.my"
```

---

#### US-021 — Role-based access control

**As a** system administrator, **I need** LHDN-sensitive fields and actions to be restricted by role,
**so that** only authorized personnel can view UUIDs, QR codes, or trigger resubmissions.

**RBAC rules** (implement via Frappe Permissions framework):

| Action | Allowed Roles |
|---|---|
| View `custom_lhdn_uuid` | HR Manager, System Manager |
| View `custom_lhdn_qr_code` / `custom_lhdn_qr_url` | HR Manager, System Manager |
| View `custom_error_log` | HR Manager, System Manager |
| Manually trigger resubmission (custom button) | System Manager only |
| Toggle `custom_requires_self_billed_invoice` on Employee | HR Manager, System Manager |

**Acceptance criteria:**
```
GIVEN a user with role "HR User" (not HR Manager)
WHEN they open a Salary Slip
THEN custom_lhdn_uuid field is not visible

GIVEN a user with role "HR Manager"
WHEN they open a Salary Slip
THEN all custom_lhdn_* fields are visible
```

---

#### US-022 — Mandatory test scenarios

**As a** QA engineer, **I need** all 5 LHDN-mandated test cases to pass in the sandbox environment,
**so that** the integration is validated before production deployment.

| Test ID | Scenario | Expected Result |
|---|---|---|
| **T-01** | Submit standard employee Salary Slip | `custom_lhdn_status = "Exempt"`, no API call |
| **T-02** | Submit contractor Salary Slip (valid TIN) | `custom_lhdn_status = "Valid"`, UUID and QR code populated |
| **T-03** | Submit contractor Salary Slip (malformed TIN `IG123`) | `custom_lhdn_status = "Invalid"`, `custom_error_log` contains LHDN error message |
| **T-04** | Submit contractor Salary Slip, simulate network timeout | Job remains in RQ queue, `custom_retry_count = 1`, status stays "Pending" |
| **T-05** | Run `run_monthly_consolidation()` manually | All pending slips (< RM10K) merged into one code-004 payload, submitted successfully |

**Implementation notes for T-03:**
- Use a sandbox TIN that is intentionally invalid, or temporarily override validation to pass a bad TIN to the API.

**Implementation notes for T-04:**
- Mock `requests.post` to raise `requests.Timeout` on first call only.

---

## 5. Data Contracts

### 5.1 Custom Field Definitions Summary

All custom fields are defined in `fixtures/custom_fields.json`. Key rules:
- `module`: always `"LHDN Payroll Integration"`
- `insert_after`: chain fields in logical order
- `read_only`: set to `1` for all API-response fields (`custom_lhdn_*` except `custom_requires_self_billed_invoice` and `custom_lhdn_tin`)
- `translatable`: `0` for all

### 5.2 UBL 2.1 JSON Payload Contract

**Self-Billed Invoice (type "11") — required fields:**

```json
{
  "_eInvoiceVersion": "1.1",
  "_eInvoiceTypeCode": "11",
  "_eInvoiceCode": "string, max 50 chars",
  "_eInvoiceOriginalCode": "",
  "_eInvoiceDateTime": "YYYY-MM-DDTHH:MM:SSZ",
  "InvoiceCurrencyCode": "MYR",
  "CurrencyExchangeRate": "1.00",
  "BillingPeriodStartDate": "YYYY-MM-DD",
  "BillingPeriodEndDate": "YYYY-MM-DD",

  "SupplierName": "string",
  "SupplierTIN": "string, validated format",
  "SupplierRegistrationNumber": "string, '000000000000' if none",
  "SupplierIDType": "NRIC | Passport | BRN | ARMY",
  "SupplierAddress": {
    "AddressLine0": "string",
    "AddressLine1": "string",
    "AddressLine2": "string",
    "PostalZone": "string",
    "CityName": "string",
    "State": "string (2-digit LHDN code, e.g. '14')",
    "Country": "string (ISO 3166-1 alpha-3, e.g. 'MYS')"
  },
  "SupplierMSICCode": "string, 5 digits",
  "SupplierBusinessActivityDescription": "string",
  "SupplierContactNumber": "string or 'NA'",
  "SupplierBankAccountNumber": "string, max 150 chars",

  "BuyerName": "string",
  "BuyerTIN": "string",
  "BuyerRegistrationNumber": "string",
  "BuyerIDType": "BRN",
  "BuyerAddress": { "...same structure as Supplier..." },
  "BuyerContactNumber": "string or 'NA'",

  "TotalExcludingTax": "string, 2dp",
  "TotalTaxAmount": "string, 2dp",
  "TotalIncludingTax": "string, 2dp",
  "TotalPayableAmount": "string, 2dp",

  "InvoiceLines": [
    {
      "ID": "string (line number)",
      "InvoicedQuantity": {"_": "1", "unitCode": "C62"},
      "LineExtensionAmount": {"_": "string, 2dp", "currencyID": "MYR"},
      "ItemClassificationCode": {"_": "037", "listID": "CLASS"},
      "ItemDescription": "string",
      "UnitPrice": {"_": "string, 2dp", "currencyID": "MYR"},
      "TaxType": "E",
      "TaxRate": "0.00",
      "TaxAmount": "0.00",
      "Subtotal": "string, 2dp"
    }
  ]
}
```

### 5.3 LHDN API Response Contract

**Success response:**
```json
{
  "status": 2,
  "uuid": "LHDN-2026-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX",
  "qr_url": "https://myinvois.hasil.gov.my/qr/...",
  "submission_uid": "string"
}
```

**Error response (Status 3):**
```json
{
  "status": 3,
  "errors": [
    {
      "code": "CF204",
      "message": "Human-readable description",
      "field": "FieldName",
      "value": "submitted_value"
    }
  ]
}
```

---

## 6. Business Logic Decision Trees

### 6.1 Complete Submission Filter

```
INPUT: doctype (str), doc (Frappe Document object)
OUTPUT: action ("exempt" | "individual" | "consolidate")

IF doctype == "Salary Slip":
  employee = get Employee by doc.employee
  IF employee.custom_requires_self_billed_invoice == False → RETURN "exempt"
  IF doc.net_pay <= 0 → RETURN "exempt"
  IF doc.net_pay > 10000 → RETURN "individual"  # high-value override
  IF site_config.lhdn_grace_period_active == True → RETURN "consolidate"
  RETURN "individual"

IF doctype == "Expense Claim":
  IF doc.custom_expense_category == "Overseas - Exempt" → RETURN "exempt"
  IF doc.custom_expense_category == "Employee Receipt Provided" → RETURN "exempt"
  IF doc.custom_expense_category == "Self-Billed Required":
    employee = get Employee by doc.employee
    IF employee.custom_requires_self_billed_invoice == False → RETURN "exempt"
    IF doc.total_sanctioned_amount > 10000 → RETURN "individual"
    IF site_config.lhdn_grace_period_active == True → RETURN "consolidate"
    RETURN "individual"
  RETURN "exempt"

RETURN "exempt"
```

### 6.2 TIN Validation Logic

```
INPUT: tin (str), is_foreign_worker (bool), id_type (str)
OUTPUT: validated_tin (str)

IF is_foreign_worker == True → RETURN "EI00000000010"

IF tin is None or tin == "":
  RAISE ValidationError("TIN is required for self-billed e-Invoice")

tin = tin.strip().upper()

IF id_type in ["NRIC", "Passport", "Army ID"]:
  # Individual TIN format
  IF NOT regex.match("^IG\d{11}$", tin):
    RAISE ValidationError(f"Individual TIN must be IG followed by 11 digits. Got: {tin}")

ELSE:
  # Non-individual (BRN) TIN format
  IF NOT regex.match("^[A-Z]\d{8,9}0$", tin):
    RAISE ValidationError(f"Non-individual TIN must end with 0. Got: {tin}")

RETURN tin
```

### 6.3 Cancellation Window Logic

```
INPUT: doc (Salary Slip with custom_lhdn_validated_datetime)
OUTPUT: allowed (bool), reason (str)

IF doc.custom_lhdn_status NOT IN ["Valid", "Submitted"]:
  RETURN True, "not_submitted"

reference_time = doc.custom_lhdn_validated_datetime
  OR doc.custom_lhdn_submission_datetime
  OR RAISE ValidationError("Cannot determine submission time")

hours_elapsed = (now_utc() - reference_time).total_seconds() / 3600

IF hours_elapsed <= 72:
  RETURN True, "within_window"
ELSE:
  RETURN False, "past_window — issue Credit Note instead"
```

---

## 7. Reference Data

### 7.1 LHDN Classification Codes (Payroll-relevant)

| Code | Description | ERPNext Use Case |
|---|---|---|
| `004` | Consolidated e-Invoice | Monthly batch submission during grace period |
| `027` | Reimbursement | Expense Claim line items (employer-to-employee reimbursement) |
| `032` | Foreign income | Self-billed for non-resident foreign contractors without Malaysian TIN |
| `037` | Self-billed — Monetary payment to agents/dealers/distributors | Commission payouts, performance bonuses to agents |
| `044` | Vouchers, gift cards, loyalty points | Non-monetary benefits / perquisites to staff |
| `045` | Self-billed — Non-monetary payment to agents/dealers/distributors | In-kind incentives (goods, travel) to agents |

**Salary Component `custom_lhdn_classification_code` options string** (verified against LHDN SDK codes):
```
022 : Others
024 : Private retirement scheme or deferred annuity scheme
027 : Reimbursement
032 : Foreign income
036 : Self-billed - Others
037 : Self-billed - Monetary payment to agents, dealers or distributors
040 : Voluntary contribution to approved provident fund
044 : Vouchers, gift cards, loyalty points
045 : Self-billed - Non-monetary payment to agents, dealers or distributors
```

**Recommended defaults by component type:**
- Regular salary/wage components → `022 : Others`
- Commission/agent fee components → `037 : Self-billed - Monetary payment to agents, dealers or distributors`
- General self-billed payroll components → `036 : Self-billed - Others`
- Expense reimbursements → `027 : Reimbursement`
- EPF voluntary top-up → `040 : Voluntary contribution to approved provident fund`

### 7.2 Malaysian Statutory Rates 2026

| Contribution | Employee Rate | Employer Rate | Wage Ceiling | Notes |
|---|---|---|---|---|
| **EPF (Citizens/PR)** | 11% | 13% (≤RM5,000) / 12% (>RM5,000) | None | Tabular brackets; use official EPF schedule |
| **EPF (Foreign Workers)** | 2% | 2% | None | Effective from Oct 2025 |
| **SOCSO/PERKESO** | ~0.5% | ~1.75% | RM 6,000/month | Use exact tabular rates, not % |
| **EIS/SIP** | 0.2% | 0.2% | RM 6,000/month | Use exact tabular rates |
| **PCB/MTD** | Progressive | N/A | N/A | Use LHDN Computerised Calculation Method 2026 |

**PCB/MTD 2026 progressive brackets** (chargeable income per year — source: LHDN official AY 2026):

| Chargeable Income (RM) | Rate | Cumulative Tax (RM) |
|---|---|---|
| 0 – 5,000 | 0% | 0 |
| 5,001 – 20,000 | 1% | 150 |
| 20,001 – 35,000 | 3% | 600 |
| 35,001 – 50,000 | 6% | 1,500 |
| 50,001 – 70,000 | 11% | 3,700 |
| 70,001 – 100,000 | 19% | 9,400 |
| 100,001 – 400,000 | 25% | 84,400 |
| 400,001 – 600,000 | 26% | 136,400 |
| 600,001 – 2,000,000 | 28% | 528,400 |
| > 2,000,000 | 30% | 528,400 + 30% of excess |

Standard individual relief: **RM 9,000** (applied before tax calculation).
Tax rebate: **RM 400** if chargeable income ≤ RM 35,000.
Spec: `hasil.gov.my/media/arvlrzh5/spesifikasi-kaedah-pengiraan-berkomputer-pcb-2026.pdf`

### 7.3 LHDN State Codes (Malaysia)

| Code | State |
|---|---|
| `01` | Johor |
| `02` | Kedah |
| `03` | Kelantan |
| `04` | Melaka |
| `05` | Negeri Sembilan |
| `06` | Pahang |
| `07` | Pulau Pinang |
| `08` | Perak |
| `09` | Perlis |
| `10` | Selangor |
| `11` | Terengganu |
| `12` | Sabah |
| `13` | Sarawak |
| `14` | Wilayah Persekutuan Kuala Lumpur |
| `15` | Wilayah Persekutuan Labuan |
| `16` | Wilayah Persekutuan Putrajaya |

### 7.4 API Endpoints

| Environment | Base URL |
|---|---|
| **Sandbox** | `https://preprod-api.myinvois.hasil.gov.my` |
| **Production** | `https://api.myinvois.hasil.gov.my` |

| Action | Method | Path |
|---|---|---|
| # | Action | Method | Path |
|---|---|---|---|
| 1 | Get access token | POST | `/connect/token` |
| 2 | Validate taxpayer TIN | GET | `/einvoicingapi/01-validate-taxpayer-tin/` |
| 3 | Submit documents (1–100/call) | POST | `/api/v1.0/documentsubmissions` |
| 4 | Get submission status | GET | `/api/v1.0/documentsubmissions/{submissionUid}` |
| 5 | Get document details | GET | `/api/v1.0/documents/{uuid}/details` |
| 6 | Get document raw XML | GET | `/api/v1.0/documents/{uuid}/raw` |
| 7 | Cancel document (issuer) | PUT | `/api/v1.0/documents/{uuid}/state` — body: `{"status":"cancelled","reason":"..."}` |
| 8 | Reject document (buyer) | PUT | `/api/v1.0/documents/{uuid}/state` — body: `{"status":"rejected","reason":"..."}` |

**Rate limits:** 100 req/min per Client ID · Token lifetime: 60 min (cache and reuse)
**Submission constraints:** Max 100 docs/call · Max 5 MB total · Max 300 KB/doc · 10-min duplicate dedup window

**TLS requirement:** TLS 1.2 or higher. Do not pin certificates — rely on OS trust store to survive LHDN certificate rotations.

---

## 8. Known Issues & Workarounds

### 8.1 ERPNext v16 Payroll Aggregation Bug

**Issue:** `frappe.exceptions.PermissionError: Invalid field format for SELECT: sum(net_pay) as net_sum`

**Trigger:** `compute_year_to_date()` function in `hrms/payroll/doctype/salary_slip/salary_slip.py` uses a raw SQL aggregation that fails in ERPNext v16's new query builder.

**Root cause:** The query builder in v16 does not allow raw `SUM(field)` expressions in the same way v15 did. The `PermissionError` is misleadingly named — it is actually a query format error.

**GitHub issue:** https://github.com/frappe/hrms/issues/3769

**Workaround for this app:**
> **Never** read `doc.year_to_date`, `doc.ytd_net_pay`, or call `doc.compute_year_to_date()` from within this app's payload builder. Calculate all financial totals directly from `doc.earnings` (child table) using Python iteration + `decimal.Decimal`. This bypasses the buggy aggregation entirely.

```python
# [EXACT] — Safe way to get total from child table
from decimal import Decimal
total = sum(Decimal(str(row.amount)) for row in doc.earnings)
```

### 8.2 myinvois_erpgulf pip/uv install failure

**Issue:** `bench get-app` for `myinvois_erpgulf` fails because `uv pip install` cannot resolve the git-pinned `pypika` dependency required by `frappe`.

**Workaround (already applied in `Dockerfile.myinvois`):**
```dockerfile
RUN git clone https://github.com/ERPGulf/myinvois.git /tmp/myinvois && \
    /home/frappe/frappe-bench/env/bin/pip install --no-deps /tmp/myinvois
```

### 8.3 nginx stale DNS after container restart

**Symptom:** After `docker compose restart`, the frontend nginx proxy returns 502 because it has cached the old backend container IP.

**Fix:**
```bash
docker compose -f pwd-myinvois.yml restart frontend
```

---

## 9. Testing Specification

### 9.1 Unit Tests

Place in `lhdn_payroll_integration/tests/`:

| Test file | Tests |
|---|---|
| `test_exemption_filter.py` | Standard employee → exempt; contractor → in-scope; overseas expense → exempt |
| `test_payload_builder.py` | TIN inversion, decimal precision, doc name truncation, missing MSIC default |
| `test_validation.py` | TIN regex (individual, non-individual, foreign worker), date format, bank account truncation |
| `test_decimal_utils.py` | `0.1 + 0.2 != 0.3` does NOT occur; ROUND_HALF_UP applied correctly |
| `test_cancellation.py` | 72h boundary: 71h59m → allowed, 72h01m → blocked |

### 9.2 Integration Tests (Sandbox)

Run against LHDN pre-production environment using real API credentials.

| Test ID | Scenario | Pass Condition |
|---|---|---|
| T-01 | Submit standard employee slip | `custom_lhdn_status = "Exempt"`, zero API calls |
| T-02 | Submit contractor slip (valid data) | `custom_lhdn_status = "Valid"`, UUID non-empty, QR URL valid |
| T-03 | Submit contractor slip (bad TIN) | `custom_lhdn_status = "Invalid"`, `custom_error_log` non-empty |
| T-04 | Network timeout during submission | `custom_retry_count = 1`, status = "Pending", retry job in queue |
| T-05 | Monthly consolidation job | One code-004 payload submitted, all eligible slips marked `custom_is_consolidated = 1` |

---

## Appendix A: Implementation Checklist

```
Phase 1
[ ] US-001: bench new-app + hooks.py scaffold
[ ] US-002: Employee custom fields (7 fields)
[ ] US-003: Salary Component custom field (1 field)
[ ] US-004: Salary Slip custom fields (10 fields)
[ ] US-005: Expense Claim custom fields (9 fields)
[ ] US-006: LHDN MSIC Code DocType + fixture data

Phase 2
[ ] US-007: exemption_filter.py
[ ] US-008: submission hooks (on_submit, enqueue)
[ ] US-009: payload_builder.py — Salary Slip
[ ] US-010: payload_builder.py — Expense Claim
[ ] US-011: submission_service.py — myinvois facade + response writer
[ ] US-012: validation.py — all 8 validation rules

Phase 3
[ ] US-013: status_poller.py — hourly scheduler
[ ] US-014: error log formatter
[ ] US-015: retry_service.py — exponential backoff

Phase 4
[ ] US-016: cancellation_service.py — 72h check
[ ] US-017: async cancellation job

Phase 5
[ ] US-018: consolidation_service.py — monthly scheduler + RM10K filter
[ ] US-019: consolidated payload builder (code 004)

Phase 6
[ ] US-020: env toggle (sandbox/production site config)
[ ] US-021: RBAC permission rules
[ ] US-022: All 5 integration tests passing in sandbox
```

---

## Appendix B: Decimal Utility Reference

```python
# [EXACT] lhdn_payroll_integration/utils/decimal_utils.py
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


TWOPLACES = Decimal("0.01")


def quantize(value) -> Decimal:
    """Safely convert any numeric value to 2dp Decimal."""
    try:
        return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    except InvalidOperation as e:
        raise ValueError(f"Cannot convert {value!r} to Decimal: {e}")


def assert_totals_balance(excl_tax: Decimal, tax: Decimal, incl_tax: Decimal):
    """Raise ValueError if excl_tax + tax != incl_tax."""
    computed = quantize(excl_tax + tax)
    if computed != quantize(incl_tax):
        raise ValueError(
            f"LHDN total mismatch: {excl_tax} + {tax} = {computed}, "
            f"but TotalIncludingTax = {incl_tax}"
        )
```

---

## Appendix C: Date Utility Reference

```python
# [EXACT] lhdn_payroll_integration/utils/date_utils.py
from datetime import timezone
import frappe


def to_lhdn_datetime() -> str:
    """Return current UTC time in ISO 8601 format required by LHDN API."""
    now = frappe.utils.now_datetime().replace(tzinfo=timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def to_lhdn_date(date_value) -> str:
    """Convert a Frappe date (string or date object) to YYYY-MM-DD string."""
    if hasattr(date_value, "strftime"):
        return date_value.strftime("%Y-%m-%d")
    if isinstance(date_value, str) and len(date_value) >= 10:
        return date_value[:10]   # trim time portion if present
    raise ValueError(f"Cannot format date: {date_value!r} — must not be 'N/A' or empty")
```
