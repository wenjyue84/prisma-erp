# PRD: LHDN Payroll Integration — Gap Closure v2.0
<!-- prd_version: 2.0 | status: ACTIVE | last_updated: 2026-02-27 -->

**App:** `lhdn_payroll_integration` (Frappe ERPNext v16)
**Date:** 2026-02-27
**Source:** Specialist gap analysis of existing codebase (post-v1 audit, 78 stories complete)
**Total Stories:** 95 (US-001 to US-050 in v2.0; US-051 to US-095 in v3.0 extension)

---

## Overview

This PRD captures all identified gaps in the existing `lhdn_payroll_integration` Frappe app discovered during a deep code-level compliance audit against LHDN MyInvois v1.1 spec, Malaysian statutory payroll law, and ERPNext integration best practices. The original 78 v1 stories are complete. These 50 stories close critical XML schema errors, broken runtime services, missing statutory forms, and incomplete business logic.

---

## CRITICAL PRIORITY (US-001 to US-005)

### US-001: Add schemeID attribute to all PartyIdentification/ID elements
**Priority:** Critical
**File:** `lhdn_payroll_integration/services/payload_builder.py`

Every `cbc:ID` inside `cac:PartyIdentification` is emitted without the mandatory `schemeID` attribute (LHDN v1.1 spec §6.2). All submissions currently fail LHDN schema validation. Employee has `custom_id_type` (NRIC/Passport/BRN/Army ID) stored but never mapped to `schemeID` in the XML.

**Acceptance Criteria:**
- `_build_invoice_skeleton()` emits `<cbc:ID schemeID="TIN">` for TIN on both Supplier (Employee) and Buyer (Company) parties
- Employee id_type mapped: NRIC→NRIC, Passport→PASSPORT, BRN→BRN, Army ID→ARMY
- All existing tests pass; new test asserts schemeID attribute present in generated XML

---

### US-002: Add AdditionalDocumentReference for NRIC/BRN/Passport registration ID
**Priority:** Critical
**File:** `lhdn_payroll_integration/services/payload_builder.py`

LHDN v1.1 requires `cac:AdditionalDocumentReference` elements to carry the supplier's NRIC/BRN/Passport number separately from the TIN. Employee fields `custom_id_type` and `custom_id_value` are stored but never emitted into XML.

**Acceptance Criteria:**
- Both `build_salary_slip_xml()` and `build_expense_claim_xml()` emit `AdditionalDocumentReference` with id_type, DocumentType, and id_value in ExternalReference/URI
- Works for individual and consolidated invoices
- Test asserts AdditionalDocumentReference node present with correct values

---

### US-003: Fix token expiry check and status poller base_url bug
**Priority:** Critical
**Files:** `submission_service.py`, `status_poller.py`

`get_access_token()` returns cached token unconditionally (LHDN tokens expire after 3600s). Exceptions silently return `""`. `status_poller` passes hardcoded `""` as base_url — all hourly polls fail with ConnectionError.

**Acceptance Criteria:**
- Add `custom_token_expires_at` Datetime field to Company in `custom_field.json`
- Token refreshed if within 5 min of expiry; exceptions logged via `frappe.log_error()`
- `poll_pending_documents()` passes `_get_base_url(doc.company)` not `""`
- `_get_base_url()` accepts company_name parameter
- Tests for token expiry path and empty-token error logging

---

### US-004: Implement PCB/MTD monthly calculation validation
**Priority:** Critical
**Files:** New `lhdn_payroll_integration/services/pcb_calculator.py`

No PCB calculation engine exists. The app relies entirely on HR staff manually entering PCB deduction amounts with no validation against LHDN PCB Schedule (Jadual PCB). MTD Method 1 vs Method 2 not handled.

**Acceptance Criteria:**
- New `pcb_calculator.py` with `calculate_pcb(annual_income, resident=True, married=False, children=0)` implementing LHDN progressive tax scale
- `validate_pcb_amount(doc)` whitelisted function warns (not blocks) if PCB deviates >10% from calculated estimate
- Warning shown on Salary Slip form when PCB appears incorrect
- Tests: single resident, married with children, non-resident flat 30%, zero-income scenarios

---

### US-005: Implement NRIC format validation on Employee save
**Priority:** Critical
**File:** `lhdn_payroll_integration/utils/validation.py`

`custom_id_value` accepts any string up to 20 chars. Malaysian NRIC format is 12 digits (YYMMDDPBXXXX — year, month, day, birth state code, sequence). Incorrectly entered NRICs silently pass through to LHDN causing rejections.

**Acceptance Criteria:**
- `validate_nric(value)` in `validation.py`: exactly 12 digits, valid YYMMDD date portion, valid state/birth code (01-16 local, 21-59 foreign)
- `validate_id_value(id_type, id_value)` dispatcher: NRIC→strict check, Passport→length/alphanumeric, BRN→12-digit numeric
- `validate_document_for_lhdn(employee)` called on Employee `validate` hook via `hooks.py`
- Tests cover valid/invalid NRIC, Passport, BRN inputs

---

## HIGH PRIORITY (US-006 to US-027)

### US-006: Add IssueTime element to Invoice header
**Priority:** High
**File:** `lhdn_payroll_integration/services/payload_builder.py`

LHDN v1.1 requires both `cbc:IssueDate` and `cbc:IssueTime` in the Invoice root. Code emits only IssueDate. Without IssueTime, documents fail schema validation and UBL element ordering is incorrect.

**Acceptance Criteria:**
- `_build_invoice_skeleton()` emits `<cbc:IssueTime>HH:MM:SS</cbc:IssueTime>` immediately after IssueDate
- Time uses `frappe.utils.now_datetime()` formatted as HH:MM:SS
- Element order: ID → IssueDate → IssueTime → InvoiceTypeCode → DocumentCurrencyCode
- Test asserts IssueTime node present in generated XML

---

### US-007: Add InvoicePeriod to individual Salary Slip and Expense Claim invoices
**Priority:** High
**File:** `lhdn_payroll_integration/services/payload_builder.py`

`build_salary_slip_xml()` and `build_expense_claim_xml()` do not emit `cac:InvoicePeriod`. Only consolidated invoices have it. LHDN expects billing period (pay period dates) for payroll self-billed invoices.

**Acceptance Criteria:**
- Both builders add `cac:InvoicePeriod` with `StartDate` = `doc.start_date`, `EndDate` = `doc.end_date`
- Test asserts InvoicePeriod present with correct dates in generated XML

---

### US-008: Fix PCB detection to use custom_is_pcb_component flag
**Priority:** High
**File:** `lhdn_payroll_integration/services/payload_builder.py`

Hardcoded `PCB_COMPONENT_NAMES` frozenset used instead of `custom_is_pcb_component` flag on Salary Component. Non-English PCB component names (e.g. "Cukai Pendapatan") silently excluded from WithholdingTaxTotal.

**Acceptance Criteria:**
- PCB detection checks `frappe.db.get_value("Salary Component", name, "custom_is_pcb_component") == 1` OR name in fallback frozenset
- Hardcoded set retained as fallback with deprecation comment
- Test with custom-named PCB component verifies inclusion in WithholdingTaxTotal

---

### US-009: Fix credit note to use LHDN TIN not ERPNext employee code for Supplier
**Priority:** High
**File:** `lhdn_payroll_integration/services/credit_note_service.py`

Credit note `AccountingSupplierParty/ID` uses `doc.employee` (ERPNext internal code like `EMP-0001`) instead of `employee.custom_lhdn_tin`. LHDN rejects credit notes where supplier TIN does not match original invoice. PostalAddress and PartyTaxScheme also missing from credit note party elements.

**Acceptance Criteria:**
- Credit note Supplier party uses `employee.custom_lhdn_tin` for `cbc:ID`
- `PostalAddress` and `PartyTaxScheme` added to both Supplier and Buyer parties (matching `_build_invoice_skeleton()`)
- Test verifies credit note XML supplier ID matches LHDN TIN

---

### US-010: Fix consolidated invoice to use eligible earnings not net_pay
**Priority:** High
**File:** `lhdn_payroll_integration/services/payload_builder.py`

`build_consolidated_xml()` uses raw `doc.net_pay` for line amounts. Individual invoices filter to eligible earnings (excluding employer statutory + custom-excluded components). Creates reconciliation mismatches.

**Acceptance Criteria:**
- Line amount = sum of eligible earnings excluding EMPLOYER_STATUTORY_COMPONENTS and `custom_lhdn_exclude_from_invoice` components
- Test confirms consolidated line amount matches sum of individual invoice line amounts for same documents

---

### US-011: Wire build_consolidated_xml() into consolidation_service
**Priority:** High
**File:** `lhdn_payroll_integration/services/consolidation_service.py`

`build_consolidated_xml()` exists in payload_builder.py but is NEVER called. `consolidation_service.py` submits each document individually in a loop — defeats purpose of consolidated submission and makes the 7-day deadline logic meaningless.

**Acceptance Criteria:**
- Batch docs (≤RM10,000) submitted as ONE consolidated XML via `build_consolidated_xml(batch_docnames, target_month)`
- High-value (>RM10,000) documents continue to be submitted individually
- Consolidated submission response UUID written to a new `LHDN Consolidation Log` record linked to all batch documents
- All batch documents marked `custom_is_consolidated = 1`
- Test verifies single HTTP call for a batch of 5 eligible salary slips

---

### US-012: Generate CP39 monthly PCB remittance file
**Priority:** High
**Files:** New `lhdn_payroll_integration/report/cp39_pcb_remittance/`

CP39 is mandatory monthly employer PCB remittance format for LHDN's e-PCB portal. Every employer with PCB deductions must submit monthly. Not present anywhere in the app.

**Acceptance Criteria:**
- New Script Report `cp39_pcb_remittance` with filters: Company, Month, Year
- Columns: Employee TIN, IC/Passport Number, Employee Name, Gross Salary, PCB Amount, Period
- CSV export in LHDN e-PCB portal compatible format
- Sources only submitted Salary Slips (docstatus=1) with PCB deduction > 0
- Test verifies output columns and row count

---

### US-013: Generate EA Form (Borang EA) for employees
**Priority:** High
**Files:** New `lhdn_payroll_integration/report/ea_form/`, new Print Format

EA Form is mandatory annual employee tax statement that every employer must provide to employees by 28 February each year (equivalent to Malaysia's W-2). Not present in the app.

**Acceptance Criteria:**
- New Script Report `ea_form` with filters: Company, Employee (optional), Year
- Aggregates all submitted Salary Slips for the year per employee
- Output fields: Total Gross Remuneration, EPF Employee, SOCSO Employee, EIS Employee, PCB Total, Net Pay
- HTML Print Format renders as LHDN-compatible EA Form layout
- Test verifies aggregation accuracy across 12 months

---

### US-014: Generate Borang E (Form E) employer annual return
**Priority:** High
**Files:** New `lhdn_payroll_integration/report/borang_e/`

Borang E is mandatory employer annual return to LHDN due 31 March each year (Income Tax Act 1967, Section 83). Non-compliance carries penalty under Section 120. Company-level summary of all PCB, headcount, and total remuneration.

**Acceptance Criteria:**
- New Script Report `borang_e` with filters: Company, Year
- Output: company details, total employees, total gross remuneration, total PCB withheld, total EPF employer, total SOCSO employer
- CP8D employee list (per-employee annual income + PCB) included as sub-table
- Test verifies company-level totals match sum of individual EA Form data

---

### US-015: Generate EPF Borang A monthly contribution schedule
**Priority:** High
**Files:** New `lhdn_payroll_integration/report/epf_borang_a/`

EPF (KWSP) Borang A is mandatory monthly contribution remittance form listing each employee's contribution. No EPF reporting exists. Required for all employers registered with EPF.

**Acceptance Criteria:**
- New Script Report `epf_borang_a` with filters: Company, Month, Year
- Columns: Employee Name, NRIC, EPF Member Number, Wages, Employee EPF, Employer EPF, Total
- New field `custom_epf_member_number` (Data) on Employee
- CSV export compatible with EPF i-Akaun upload format
- Test verifies contribution amounts per employee

---

### US-016: Generate SOCSO Borang 8A monthly contribution schedule
**Priority:** High
**Files:** New `lhdn_payroll_integration/report/socso_borang_8a/`

SOCSO (PERKESO) Borang 8A is mandatory monthly contribution schedule. No SOCSO reporting exists in the app.

**Acceptance Criteria:**
- New Script Report `socso_borang_8a` with filters: Company, Month, Year
- Columns: Employee Name, NRIC, SOCSO Number, Wages, Employee SOCSO, Employer SOCSO, Total
- New field `custom_socso_member_number` (Data) on Employee
- Test verifies amounts sourced from SOCSO deduction lines

---

### US-017: Generate EIS monthly contribution report
**Priority:** High
**Files:** New `lhdn_payroll_integration/report/eis_monthly/`

EIS (Sistem Insurans Pekerjaan) monthly contributions filed separately via EIS portal. Employer must submit monthly schedule. No EIS report exists.

**Acceptance Criteria:**
- New Script Report `eis_monthly` with filters: Company, Month, Year
- Columns: Employee Name, NRIC, Wages, EIS Employee, EIS Employer, Total
- Sources data from submitted Salary Slips with EIS deduction/earning lines
- Test verifies correct EIS amounts per employee

---

### US-018: Add bonus/irregular payment classification for PCB differentiation
**Priority:** High
**Files:** `custom_field.json`, `payload_builder.py`, `pcb_calculator.py`

LHDN and PCB rules treat irregular payments (bonus, commissions, gratuity) differently from regular salary for PCB calculation. No flag or separate calculation path distinguishes these — causes incorrect PCB treatment.

**Acceptance Criteria:**
- New field `custom_is_irregular_payment` (Check) on Salary Component
- `pcb_calculator.py` accepts `bonus_amount` parameter; applies one-twelfth annualisation rule for bonus PCB per LHDN Schedule
- Test verifies bonus PCB calculation differs from regular salary PCB for same income

---

### US-019: Add non-resident flat-rate 30% tax flag and handling
**Priority:** High
**Files:** `custom_field.json`, `pcb_calculator.py`

Non-resident employees (present in Malaysia fewer than 182 days in a calendar year) are taxed at flat 30%. No `custom_is_non_resident` flag and no flat-rate calculation path exists.

**Acceptance Criteria:**
- New field `custom_is_non_resident` (Check) on Employee; distinct from `custom_is_foreign_worker`
- `pcb_calculator.py` returns 30% flat rate when `resident=False`
- PCB validation warning on Salary Slip uses flat rate for non-residents
- Test covers non-resident 30% calculation vs progressive scale

---

### US-020: Distinguish director fee vs director salary at invoice level
**Priority:** High
**Files:** `custom_field.json`, `exemption_filter.py`

LHDN treats director fees (board service) and director salary (executive role) differently. Both use single `custom_worker_type = Director` with no sub-classification. Default classification code `036` applied uniformly.

**Acceptance Criteria:**
- New field `custom_director_payment_type` (Select: `Director Salary`/`Director Fee`) on Employee, visible only when `custom_worker_type = Director`
- `get_default_classification_code()` returns `036` for Director Fee, `004` for Director Salary
- Test verifies correct classification codes per director payment type in generated XML

---

### US-021: Integrate LHDN TIN validation API before submission
**Priority:** High
**Files:** New `lhdn_payroll_integration/utils/tin_validator.py`, `submission_service.py`

LHDN provides `GET /api/v1.0/taxpayer/validate/{tin}/{idType}/{idValue}`. App never calls it — incorrect TINs discovered only on submission rejection.

**Acceptance Criteria:**
- New `tin_validator.py` with `validate_tin_with_lhdn(company_name, tin, id_type, id_value)` calling LHDN validation API
- Called in `enqueue_salary_slip_submission()` before enqueuing — invalid TIN sets status `Invalid` with error, does not enqueue
- Whitelisted `validate_employee_tin(employee_name)` callable from Employee form button
- Test with mocked HTTP: valid TIN proceeds to enqueue; invalid TIN sets Invalid status

---

### US-022: Add submission failure email notification for HR Manager
**Priority:** High
**File:** `lhdn_payroll_integration/services/submission_service.py`

When Salary Slip marked Invalid after LHDN rejection, no notification reaches HR managers. Silent failures can result in months of non-compliance before detection.

**Acceptance Criteria:**
- `_write_response_to_doc()` sends `frappe.sendmail()` to all users with role `HR Manager` when status set to `Invalid`
- Email includes: document name, employee name, first 500 chars of error log, direct link to document
- New Company field `custom_lhdn_failure_email` (Data) — if set, overrides role lookup
- Email sending errors are swallowed and logged, not re-raised
- Test verifies sendmail called on Invalid status write

---

### US-023: Fix status poller to use per-document company for base_url and token
**Priority:** High
**File:** `lhdn_payroll_integration/services/status_poller.py`

`poll_pending_documents()` passes hardcoded `""` as base_url to `_poll_single_document()`. Multi-company setups poll against wrong endpoint. Token also uses default company credentials.

**Acceptance Criteria:**
- `poll_pending_documents()` passes `_get_base_url(doc.company)` (not `""`) to each poll
- `_get_base_url()` accepts `company_name` parameter; reads from that company's `custom_sandbox_url`/`custom_production_url`
- Token fetched via `get_access_token(doc.company)` per document
- Test verifies Company A documents polled against Company A endpoint, not Company B

---

### US-024: Fix custom_id_type options to match LHDN schemeID vocabulary
**Priority:** High
**File:** `lhdn_payroll_integration/fixtures/custom_field.json`

Option "Business Registration Number" does not match LHDN schemeID value "BRN". When schemeID attribute added (US-001), inconsistent mapping causes XML errors.

**Acceptance Criteria:**
- `custom_id_type` options updated to: `NRIC`, `Passport`, `BRN`, `Army ID`
- Mapping dict in `payload_builder.py`: `{"NRIC": "NRIC", "Passport": "PASSPORT", "BRN": "BRN", "Army ID": "ARMY"}`
- Migration note added to `patches.txt` for records with old value "Business Registration Number"
- Test verifies each id_type produces correct schemeID attribute in generated XML

---

### US-025: Add full PostalAddress fields beyond state code only
**Priority:** High
**Files:** `custom_field.json`, `payload_builder.py`

LHDN v1.1 requires full PostalAddress: AddressLine/Line, CityName, PostalZone, CountrySubentityCode, Country/IdentificationCode. App only emits CountrySubentityCode (state code). Full address required for production compliance.

**Acceptance Criteria:**
- New Employee fields: `custom_address_line1` (Data), `custom_city` (Data), `custom_postcode` (Data)
- New Company fields (if absent): same three fields
- `_add_postal_address()` emits: `AddressLine/Line`, `CityName`, `PostalZone`, `CountrySubentityCode`, `Country/IdentificationCode = MYS`
- Test asserts all address sub-elements present in generated XML

---

### US-026: Add Expense Claims to LHDN compliance report
**Priority:** High
**File:** `lhdn_payroll_integration/report/lhdn_payroll_compliance/lhdn_payroll_compliance.py`

Compliance report queries only `tabSalary Slip`. Expense Claims with LHDN status entirely absent. HR managers have no unified view across both submission types.

**Acceptance Criteria:**
- Report queries both Salary Slip and Expense Claim (UNION or separate sections)
- Doctype column added to distinguish record types
- All existing filters (Company, Status, Date range) apply to both doctypes
- Test verifies Expense Claim rows appear in report output alongside Salary Slip rows

---

### US-027: Build monthly LHDN submission summary report
**Priority:** High
**Files:** New `lhdn_payroll_integration/report/lhdn_monthly_summary/`

No aggregated monthly view exists. Auditors need total submissions per month, count by status (Valid/Invalid/Pending/Exempt), total invoice value MYR, deadline compliance status.

**Acceptance Criteria:**
- New Script Report `lhdn_monthly_summary` with filters: Company, Year
- One row per month (Jan–Dec); columns: Month, Total Submitted, Valid, Invalid, Pending, Exempt, Total Value MYR, Deadline Status
- Deadline Status = `On Time`/`Late`/`Pending` based on 7-calendar-day rule
- Covers both Salary Slips and Expense Claims
- Test verifies monthly aggregation accuracy

---

## MEDIUM PRIORITY (US-028 to US-042)

### US-028: Guard credit note against already-cancelled LHDN document
**Priority:** Medium
**File:** `lhdn_payroll_integration/services/credit_note_service.py`

No check prevents issuing a credit note against an already-cancelled LHDN invoice. LHDN rejects credit notes referencing cancelled documents.

**Acceptance Criteria:**
- Before building credit note XML, check source `custom_lhdn_status != Cancelled`
- Raise `frappe.ValidationError` with descriptive message if source is Cancelled
- Test verifies ValidationError thrown on credit note attempt against Cancelled document

---

### US-029: Make PaymentMeansCode configurable per employee
**Priority:** Medium
**Files:** `custom_field.json`, `payload_builder.py`

`PaymentMeansCode` hardcoded as `30` (credit transfer). LHDN supports 01 (cash), 03 (cheque), 30 (credit transfer), 42 (bank transfer), 48 (debit card). Contractors paid by cheque/cash incorrectly tagged.

**Acceptance Criteria:**
- New field `custom_payment_means_code` (Select: `01 : Cash/03 : Cheque/30 : Credit Transfer/42 : Bank Transfer/48 : Debit Card`) on Employee, default `30 : Credit Transfer`
- `build_salary_slip_xml()` reads this field; falls back to `30` if not set
- Test verifies non-default payment means code appears in generated XML

---

### US-030: Add TaxExemptionReasonCode when TaxCategory ID = E
**Priority:** Medium
**File:** `lhdn_payroll_integration/services/payload_builder.py`

When `TaxCategory/ID = E` (exempt), LHDN v1.1 requires `TaxExemptionReasonCode`. Element currently absent; causes validation failures on stricter LHDN validator configurations.

**Acceptance Criteria:**
- `_add_tax_and_totals()` adds `<cbc:TaxExemptionReasonCode>VATEX-MY-ES-43</cbc:TaxExemptionReasonCode>` immediately after `TaxCategory/ID = E`
- Test asserts TaxExemptionReasonCode element present in generated XML

---

### US-031: Generate CP8D annual employee remuneration return
**Priority:** Medium
**Files:** New `lhdn_payroll_integration/report/cp8d/`

CP8D is the annual return of private employees' remuneration submitted alongside Borang E — machine-readable employee income list for LHDN e-Filing. Not present in app.

**Acceptance Criteria:**
- New Script Report `cp8d` with filters: Company, Year
- Columns: Employee TIN, NRIC, Name, Annual Gross Income, Total PCB, EPF Employee
- CSV export matching LHDN e-Filing CP8D column specification
- Test verifies per-employee annual totals

---

### US-032: Add CP21 workflow for employee cessation and departure from Malaysia
**Priority:** Medium
**Files:** New `lhdn_payroll_integration/doctype/lhdn_cp21/`

CP21 must be filed with LHDN at least 30 days before employee leaves Malaysia or ceases employment. Especially critical for `custom_is_foreign_worker = 1` employees. No CP21 workflow exists.

**Acceptance Criteria:**
- New Doctype `LHDN CP21` linked to Employee with fields: employee, last_working_date, reason (Select: Termination/Resignation/Departure from Malaysia/Death)
- Auto-created when Employee status set to `Left` with `custom_is_foreign_worker = 1`
- Alert shown if `last_working_date` is less than 30 days from today
- HTML Print Format generates LHDN-compatible CP21 document

---

### US-033: Add CP22/CP22A handling for new hire and retirement notifications
**Priority:** Medium
**Files:** New `lhdn_payroll_integration/doctype/lhdn_cp22/`

CP22 must be filed within 30 days of new employee commencement. CP22A covers retirement/resignation for employees age 55+. Neither workflow exists.

**Acceptance Criteria:**
- New Doctype `LHDN CP22` auto-created on Employee creation when `custom_requires_self_billed_invoice = 1`
- Alert shown if not submitted within 30 days of `date_of_joining`
- `LHDN CP22A` created automatically for employees age ≥55 on status change to Left

---

### US-034: Add HRDF levy validation and basic reporting
**Priority:** Medium
**Files:** `custom_field.json`, new `lhdn_payroll_integration/report/hrdf_monthly_levy/`

HRDF levy rates differ by employer size (0.5% for 10+ employees, 1% for 50+). App excludes HRDF from e-Invoice correctly but provides no levy calculation check or reporting.

**Acceptance Criteria:**
- New field `custom_hrdf_levy_rate` (Select: `0.5%/1.0%`) on Company
- New Script Report `hrdf_monthly_levy` showing monthly HRDF liability per employee
- Test verifies levy calculation at 0.5% and 1.0% rates against Company fixture

---

### US-035: Handle leave encashment and gratuity tax exemption in PCB calculation
**Priority:** Medium
**Files:** `custom_field.json`, `pcb_calculator.py`

Leave encashment and gratuity qualify for partial exemption under ITA 1967 Schedule 6 paragraph 25 (RM1,000 per year of service). Without flagging, treated as ordinary income in PCB calculation.

**Acceptance Criteria:**
- New field `custom_is_gratuity_or_leave_encashment` (Check) on Salary Component
- `pcb_calculator.py` applies Schedule 6 para 25 exemption when such component present
- Exempt amount = RM1,000 × years of service; remainder taxable as normal income
- Test verifies exemption reduces taxable income correctly

---

### US-036: Handle mid-month proration for pay period PCB calculation
**Priority:** Medium
**File:** `lhdn_payroll_integration/services/pcb_calculator.py`

LHDN PCB rules require proration when employee joins or leaves mid-month. PCB calculation must use prorated annual income. InvoicePeriod (US-007) reflects actual worked days; PCB should match.

**Acceptance Criteria:**
- `pcb_calculator.py` accepts `worked_days` and `total_days_in_month` parameters; prorates monthly income before annualising
- PCB validation warning uses prorated income when `worked_days < total_days_in_month`
- Test verifies prorated PCB for 15-day month vs full month same income

---

### US-037: Add bulk Submit to LHDN action on Salary Slip list view
**Priority:** Medium
**Files:** New `lhdn_payroll_integration/lhdn_payroll_integration/` client scripts + whitelisted method

No way to submit batch of Salary Slips simultaneously. 50-contractor payroll run requires waiting for individual on_submit hooks.

**Acceptance Criteria:**
- New whitelisted `bulk_enqueue_lhdn_submission(docnames, doctype)` server method
- List view action `Submit to LHDN` on Salary Slip list visible to HR Manager role
- Action shows success count and failure count message
- Test verifies all provided docnames are enqueued with `Pending` status

---

### US-038: Implement LHDN portal document retrieval for audit verification
**Priority:** Medium
**File:** `lhdn_payroll_integration/page/lhdn_dev_tools/lhdn_dev_tools.py`

LHDN provides `GET /api/v1.0/documents/{uuid}/raw` to retrieve the validated XML stored on their portal. No mechanism to compare LHDN stored copy against ERPNext generated XML.

**Acceptance Criteria:**
- New whitelisted `retrieve_lhdn_document(docname, doctype)` calling LHDN raw document endpoint
- Response XML stored in new field `custom_lhdn_raw_document` (Text) on Salary Slip and Expense Claim
- Dev Tools page has `Retrieve from LHDN` button invoking this function
- Test with mocked HTTP verifies UUID used in URL and response stored

---

### US-039: Add nationality field for foreign worker ISO country code
**Priority:** Medium
**Files:** `custom_field.json`, `payload_builder.py`

LHDN guidelines require ISO 3166-1 alpha-2 nationality code for foreign workers. The fixed TIN `EI00000000010` is used for all foreign workers as a placeholder.

**Acceptance Criteria:**
- New field `custom_nationality_code` (Data, 2 chars) on Employee, visible when `custom_is_foreign_worker = 1`
- `_build_invoice_skeleton()` adds nationality code to party identification element for foreign workers
- Test verifies nationality code appears in XML for foreign worker employee

---

### US-040: Define custom_sst_registration_number on Employee in fixture
**Priority:** Medium
**File:** `lhdn_payroll_integration/fixtures/custom_field.json`

`payload_builder.py` reads `employee.custom_sst_registration_number` via `getattr()` but this field is NOT defined in `custom_field.json`. Field only works if `myinvois_erpgulf` coincidentally adds it.

**Acceptance Criteria:**
- New entry in `custom_field.json`: `Employee-custom_sst_registration_number` (Data, optional, insert_after `custom_state_code`)
- Field visible only when `custom_requires_self_billed_invoice = 1`
- Test verifies SST number appears in `PartyTaxScheme/RegistrationName` when set

---

### US-041: Build year-end PCB vs submission reconciliation report
**Priority:** Medium
**Files:** New `lhdn_payroll_integration/report/lhdn_yearend_reconciliation/`

No tool to compare total PCB withheld per employee vs CP39 remittances, or to reconcile submitted vs accepted invoices. Required for Borang E and EA Form verification.

**Acceptance Criteria:**
- New Script Report `lhdn_yearend_reconciliation` with filters: Company, Year
- Columns: Employee, Annual Gross Income, Total PCB Withheld, Invoices Submitted, Invoices Valid, Discrepancy Flag
- Discrepancy Flag raised when PCB total deviates from LHDN-accepted amounts
- Test verifies discrepancy detection logic across mock 12-month data

---

### US-042: Add audit log for manual LHDN resubmissions
**Priority:** Medium
**File:** `lhdn_payroll_integration/services/submission_service.py`

`resubmit_to_lhdn()` is callable by any System Manager but leaves no audit trail (who triggered it, when, on which document).

**Acceptance Criteria:**
- `resubmit_to_lhdn()` creates a new `LHDN Resubmission Log` doctype entry (or uses `frappe.log_error` at INFO level) recording: user, timestamp, doctype, docname
- Log entries viewable from Dev Tools page under Recent Submissions panel
- Test verifies log entry created on manual resubmission

---

## LOW PRIORITY (US-043 to US-050)

### US-043: Fix alpha-only docnames producing duplicate codeNumber
**Priority:** Low
**File:** `lhdn_payroll_integration/services/payload_builder.py`

`prepare_submission_wrapper()` extracts digits from docname for `codeNumber`. All-alpha docnames fall back to `"001"` — duplicate `codeNumber` in batch submissions rejected by LHDN.

**Acceptance Criteria:**
- Fallback uses `hashlib.md5(docname.encode()).hexdigest()[:8]` instead of `"001"` for no-digit docnames
- Test verifies unique codeNumbers generated for multiple alpha-named documents

---

### US-044: Generate HRDF Borang PSMB/6 annual return
**Priority:** Low
**Files:** New `lhdn_payroll_integration/report/hrdf_borang_psmb6/`

HRDF annual return Borang PSMB/6 is due each January. Employers registered with HRDF must submit. Not present.

**Acceptance Criteria:**
- New Script Report `hrdf_borang_psmb6` with filters: Company, Year
- Columns: Total Employees, Total Wages, Total Levy Paid
- PDF-printable export format
- Test verifies levy total matches sum of monthly levy reports

---

### US-045: Add before_amend retention lock to Expense Claim
**Priority:** Low
**Files:** `hooks.py`, `retention_service.py`

Retention lock `before_amend` registered only on Salary Slip, not Expense Claim. Expense Claims with LHDN UUIDs can be amended after 7-year retention period. Retention archival job also only queries Salary Slips.

**Acceptance Criteria:**
- `hooks.py` adds `before_amend: check_retention_lock` for Expense Claim
- `run_retention_archival()` queries both Salary Slips and Expense Claims
- Test verifies ValidationError thrown on `before_amend` for retention-locked Expense Claim

---

### US-046: Add EIS, HRDF, and common allowance salary components to fixture
**Priority:** Low
**File:** `lhdn_payroll_integration/fixtures/salary_component.json`

Fixture seeds only 6 components (Basic Salary, Monthly Tax Deduction, EPF Employee/Employer, SOCSO Employee). Missing: EIS Employee, EIS Employer, HRDF Levy, Transport Allowance, Housing Allowance. New installs require extensive manual setup.

**Acceptance Criteria:**
- Add to `salary_component.json`: EIS Employee (Deduction), EIS - Employer (Deduction), HRDF Levy (Deduction), Transport Allowance (Earning), Housing Allowance (Earning)
- Each has correct `custom_lhdn_classification_code` default and `custom_is_pcb_component = 0`
- Test verifies all new components installed after fixture sync

---

### US-047: Define custom_lhdn_archived field in custom_field.json fixture
**Priority:** Low
**File:** `lhdn_payroll_integration/fixtures/custom_field.json`

`retention_service.py` calls `frappe.db.set_value(..., "custom_lhdn_archived", 1)` but this field is NOT defined in `custom_field.json`. Runtime error or silent failure on yearly archival job.

**Acceptance Criteria:**
- New entry: `Salary Slip-custom_lhdn_archived` (Check, default 0, read_only, insert_after `custom_error_log`)
- Same field added for Expense Claim
- Test verifies retention archival job correctly sets the flag to 1

---

### US-048: Fix retention archival to include Submitted/Invalid records with no validated datetime
**Priority:** Low
**File:** `lhdn_payroll_integration/services/retention_service.py`

Archival filters by `custom_lhdn_validated_datetime` only. Records with status Submitted or Invalid (no validated_datetime) are never archived even after 7 years.

**Acceptance Criteria:**
- `run_retention_archival()` uses `COALESCE(custom_lhdn_validated_datetime, custom_lhdn_submission_datetime, creation)` for 7-year age calculation
- Records with status Submitted, Invalid, Valid all included in archival scan
- Test verifies Submitted records older than 7 years are correctly archived

---

### US-049: Generate standalone CP8D report with LHDN e-Filing format compliance
**Priority:** Low
**Files:** New `lhdn_payroll_integration/report/cp8d_efiling/`

CP8D as a standalone report needs its own column specification matching LHDN e-Filing CP8D format (separate from and in addition to the one included in Borang E).

**Acceptance Criteria:**
- Standalone Script Report `cp8d_efiling` with CSV export matching LHDN e-Filing CP8D column specification precisely
- Year filter, Company filter
- Test verifies column headers match published LHDN CP8D spec

---

### US-050: Add foreign currency conversion to Expense Claim XML builder
**Priority:** Low
**File:** `lhdn_payroll_integration/services/payload_builder.py`

`build_expense_claim_xml()` does not handle foreign currency. Salary slip builder has `conversion_rate` support; expense claim builder does not. Expense Claims in USD/SGD etc. produce incorrect MYR amounts.

**Acceptance Criteria:**
- Builder reads `doc.currency` and `doc.conversion_rate` (default 1 for MYR)
- All sanctioned_amount values converted to MYR before writing to XML
- `TaxCurrencyCode` added when `doc.currency != MYR`
- Test verifies USD Expense Claim produces correct converted MYR amounts in XML

---

# PRD Extension: LHDN Payroll Integration — Full LHDN Compliance v3.0
<!-- prd_version: 3.0 | status: ACTIVE | last_updated: 2026-02-28 -->

**Source:** Deep compliance audit by malaysia-payroll-specialist agent + online research via Gemini CLI (February 2026)
**Basis:** LHDN PCB Guidelines, ITA 1967, Employment Act 1955 (A1651 amendments), EPF Act 1991, SOCSO Act 1969, EIS Act 2017, MyInvois SDK v3.x, Budget 2025, Minimum Wages Order (Feb 2025)
**Total new stories:** 45 (US-051 to US-095)

---

## CRITICAL PRIORITY — PCB Engine Correctness (US-051 to US-058)

### US-051: Add PCB Category Code (1/2/3) on Employee with CP39 and EA Form integration
**Priority:** Critical
**Files:** `fixtures/custom_field.json`, `services/pcb_calculator.py`, `report/cp39_pcb_remittance/cp39_pcb_remittance.py`, `report/ea_form/ea_form.py`

LHDN requires three distinct PCB category codes that produce different tax amounts: Category 1 (single, or married with working spouse), Category 2 (married, non-working spouse — RM4,000 spouse relief), Category 3 (single parent). The current calculator uses a `married=True/False` boolean which approximates Category 1 vs 2 but does not handle Category 3 nor transmit the category in CP39 or EA Form output. LHDN CP39 CSV upload format requires a PCB Category column for each employee row.

**Regulatory Basis:** LHDN Kaedah Pengiraan PCB Guidelines, ITA 1967 Section 83(1). Systematic wrong category causes under/over-deduction and triggers penalties under ITA Section 107C(10) of RM200–RM20,000 per offence.

**Acceptance Criteria:**
- Add `custom_pcb_category` Select (options: `1`, `2`, `3`) to Employee `custom_field.json` with help text describing each category
- `calculate_pcb()` accepts `category` parameter; Category 2 applies spouse relief RM4,000; Category 3 applies the same RM4,000 equivalent for recognised single parents per ITA Section 46A
- CP39 report CSV includes PCB Category column for each employee row
- EA Form report captures and displays the employee's declared category
- Tests cover Category 1, 2, and 3 calculations with the same annual income

---

### US-052: Implement TP1 Employee Relief Declaration DocType and PCB Integration
**Priority:** Critical
**Files:** New `lhdn_payroll_integration/doctype/employee_tp1_relief/`, `services/pcb_calculator.py`, new Print Format

LHDN Borang TP1 allows employees to declare 20+ relief categories to the employer to reduce monthly PCB deduction. The current PCB calculator hardcodes only personal relief (RM9,000), spouse relief (RM4,000), and child relief (RM2,000 each). All other declared reliefs — life insurance, medical insurance, education fees, SSPN, lifestyle, PRS, parents' medical, disability reliefs, SOCSO employee, EPF employee — are ignored, causing systematic PCB over-deduction and employee dissatisfaction.

**Regulatory Basis:** ITA Rules 1994 (IT(P)(E) Rules), Rule 6A — employers must adjust PCB based on TP1 reliefs declared by employees.

**Acceptance Criteria:**
- New DocType `Employee TP1 Relief` with fields: employee, tax_year, self_relief (RM9,000 default), spouse_relief, child_relief_normal (×RM2,000), child_relief_disabled (×RM6,000), life_insurance (max RM3,000), medical_insurance (max RM3,000), education_fees_self (max RM7,000), sspn (max RM8,000), childcare_fees (max RM3,000), lifestyle_expenses (max RM2,500), prs_contribution (max RM3,000), serious_illness_expenses (max RM10,000), parents_medical (max RM8,000), disability_self (RM6,000 if applicable), socso_employee (actual), epf_employee (max RM4,000), annual_zakat (actual, see US-053)
- One active TP1 record per employee per tax year; doctype enforces uniqueness
- `calculate_pcb()` accepts `tp1_total_reliefs` parameter; subtracts from chargeable income before computing tax
- TP1 Print Format generates an LHDN-compatible TP1 declaration form for employee signature
- Tests verify each relief type reduces PCB by the correct amount

---

### US-053: Implement Zakat PCB Offset (Ringgit-for-Ringgit Deduction)
**Priority:** Critical
**Files:** `services/pcb_calculator.py`, `fixtures/custom_field.json`, `report/cp39_pcb_remittance/cp39_pcb_remittance.py`

Zakat paid by Muslim employees reduces PCB payable ringgit-for-ringgit (not just from chargeable income). ITA Section 6A(3) is explicit: `Net PCB = Gross PCB − (annual_zakat / 12)`. The app's module docstring correctly documents this formula but the implementation does not apply it. Zakat also has a dedicated column in the LHDN CP39 CSV upload file that must be populated.

**Regulatory Basis:** ITA 1967 Section 6A(3). Failure to apply Zakat offset means Muslim employees are over-taxed via PCB; employers are liable if they fail to apply declared TP1 amounts.

**Acceptance Criteria:**
- Add `custom_annual_zakat` (Currency) field on Employee — annual Zakat amount declared on TP1
- `calculate_pcb(... , annual_zakat=0)` subtracts `annual_zakat / 12` from calculated monthly PCB; result floored at 0
- CP39 report CSV includes `Zakat Amount` column per employee row
- EA Form Section C5 reflects total annual Zakat
- Tests verify Zakat offset reduces PCB correctly; PCB never goes negative due to Zakat

---

### US-054: Implement CP38 Additional Deduction Fields and Payroll Integration
**Priority:** Critical
**Files:** `fixtures/custom_field.json`, `services/pcb_calculator.py`, `report/cp39_pcb_remittance/cp39_pcb_remittance.py`, `report/borang_e/borang_e.py`

LHDN issues CP38 notices directing employers to deduct additional PCB above normal MTD to recover underpaid tax. This is a legally binding notice under ITA Section 107(1)(b). Non-compliance makes the employer personally liable for the undeducted amount plus 10% surcharge (ITA Section 107(3A)). The CP38 amount is fixed per employee per month (set by LHDN, not calculated), has a notice reference number, and an expiry date.

**Acceptance Criteria:**
- Add to Employee in `custom_field.json`: `custom_cp38_amount` (Currency), `custom_cp38_notice_ref` (Data), `custom_cp38_expiry` (Date)
- Salary Slip PCB total = regular MTD + CP38 amount (when `custom_cp38_expiry >= today`)
- Add `CP38 Additional` column to CP39 CSV report
- Borang E summary shows total CP38 deducted as a separate line from regular PCB
- Tests: CP38 added to PCB when active; ignored when expired; CP39 CSV column populated

---

### US-055: Fix CP39 CSV Format — Add All Mandatory LHDN e-PCB Plus Columns
**Priority:** Critical
**Files:** `lhdn_payroll_integration/report/cp39_pcb_remittance/cp39_pcb_remittance.py`

The LHDN e-PCB Plus portal (which replaced legacy e-PCB in 2024) requires a specific CSV upload format with mandatory columns that the current report is missing. An incomplete CP39 file is rejected on upload, meaning no electronic PCB remittance can be processed. Missing columns: Employer E-Number (header), PCB Category (1/2/3), Zakat Amount, CP38 Additional Deduction, Employee TIN. The file must also use the employer's LHDN E-Number in the header, not the company TIN.

**Regulatory Basis:** LHDN e-PCB Plus upload specification (2024). ITA Section 107(1) requires PCB remittance by 15th of following month.

**Acceptance Criteria:**
- Employer E-Number added to CP39 report header (new `custom_employer_e_number` field on Company, see US-062)
- Columns in correct order: Employer E-Number, Month/Year, Employee TIN, Employee NRIC, Employee Name, PCB Category, Gross Remuneration, EPF Employee, Zakat Amount, CP38 Additional, Total PCB
- Currency amounts formatted to 2 decimal places
- CSV export uses UTF-8 encoding; filename follows LHDN convention
- Tests verify all columns present and populated; verify rejected format is no longer generated

---

### US-056: Rebuild EA Form to Include All Mandatory LHDN Section A/B/C/D Fields
**Priority:** Critical
**Files:** `report/ea_form/ea_form.py`, `print_format/ea_form/ea_form.json`

The current EA Form report produces only 6 columns. The LHDN-prescribed Borang EA format (gazetted under Income Tax (Forms) Rules 2021, P.U.(A) 107/2021) requires full disclosure across Section A (employer), Section B (income breakdown — 12 fields), Section C (statutory deductions — 5 fields), and Section D (tax position). Issuing an incomplete EA Form is a criminal offence under ITA Section 120(1)(b) carrying fines up to RM20,000 or imprisonment.

**Acceptance Criteria:**
- Section A: employer name, address, LHDN employer E-Number (`custom_employer_e_number`), branch code
- Section B: B1 Gross Salary, B2 Gross Overtime, B3 Gross Commissions, B4 Gross Bonuses, B5 Gratuity (with exemption), B6 Allowances (travel/entertainment/car), B7 Benefits-in-Kind (BIK value), B8 Leave Encashment, B9 Other Gains, B10 ESOS/Share Option Gains, B11 Pension/Annuity, B12 Total Remuneration
- Section C: C1 EPF Employee, C2 SOCSO Employee, C3 EIS Employee, C4 Total PCB, C5 Zakat
- Section D: D1 Overpaid PCB rebate, D2 Excess deduction
- Salary Component tagging: new `custom_ea_section` Select field on Salary Component for mapping to B1–B11 (e.g., `B2 Overtime`, `B3 Commission`, `B4 Bonus`)
- Print Format updated to match the LHDN-prescribed layout with section headers
- Tests verify Section B totals equal sum of correctly tagged components per employee

---

### US-057: Update Minimum Wage Validation to RM1,700 (Feb 2025 Rate)
**Priority:** Critical
**Files:** `services/pcb_calculator.py` or new `utils/employment_compliance.py`, `report/lhdn_payroll_compliance/lhdn_payroll_compliance.py`

The Minimum Wages Order (Amendment) 2025 increased the national minimum wage to RM1,700/month (RM8.17/hour) effective 1 February 2025 for companies with ≥5 employees, and 1 August 2025 for all remaining companies. The previous rate was RM1,500/month. No minimum wage check currently exists anywhere in the app. Paying below minimum wage is a criminal offence under Section 99J of the Employment Act with fines up to RM10,000 per contravention.

**Acceptance Criteria:**
- New utility `check_minimum_wage(monthly_salary, employment_type, worked_days, total_days)` in `utils/employment_compliance.py`
- Full-time check: warn if `basic_pay < 1700`
- Hourly check for part-time: warn if `hourly_rate < 8.17` (where hourly_rate = basic_pay / contracted_hours)
- `validate_document_for_lhdn()` in `validation.py` calls this check on Salary Slip `before_submit`
- LHDN Payroll Compliance report adds a Minimum Wage column flagging non-compliant employees
- Add `custom_employment_type` (Select: `Full-time/Part-time/Contract`) on Employee
- Tests: RM1,700 passes; RM1,699 triggers warning; part-time hourly check at RM8.17

---

### US-058: Apply RM400 Personal and Spouse Tax Rebates in PCB Calculator
**Priority:** Critical
**Files:** `services/pcb_calculator.py`

ITA 1967 Section 6A provides tax rebates (not income deductions) that directly reduce computed tax payable: RM400 personal rebate for resident individuals with chargeable income ≤ RM35,000, and RM400 spouse rebate for married individuals (Category 2/3) with the same income threshold. For the majority of Malaysian employees (median household income is well below RM35,000/year), the PCB is systematically overstated by up to RM800/year because the current `calculate_pcb()` function does not apply these rebates.

**Acceptance Criteria:**
- After computing annual tax from progressive scale, apply: `annual_tax = max(0, annual_tax - 400)` when `chargeable_income <= 35000`
- Apply additional `max(0, annual_tax - 400)` when `category in (2, 3)` and `chargeable_income <= 35000`
- Monthly PCB = adjusted annual_tax / 12
- Tests: employee with RM30,000/year chargeable income — verify RM800 total rebate applied; employee with RM36,000/year — verify no rebate

---

## HIGH PRIORITY — PCB Engine Completeness (US-059 to US-061)

### US-059: Implement MTD Method 2 (Year-to-Date Recalculation Formula)
**Priority:** High
**Files:** `services/pcb_calculator.py`, `fixtures/custom_field.json`

LHDN's Computerised PCB (Kaedah Pengiraan Berkomputer) guidelines mandate Method 2 for payroll software. Method 2 computes PCB based on actual YTD income using the formula: `MTD_n = [(P - M) * R + B] / (n+1) - (X/n)` where P = annualised YTD income, M = band floor, R = marginal rate, B = tax on lower bands, n = remaining months, X = PCB already deducted YTD. This is more accurate than Method 1 (simple annualisation) for employees with variable income.

**Regulatory Basis:** LHDN PCB Guidelines, Appendix D (Method 2/Kaedah 2).

**Acceptance Criteria:**
- Add Company-level `custom_pcb_method` Select (Method 1 / Method 2) with default Method 2
- New `calculate_pcb_method2(current_month_gross, ytd_gross, ytd_pcb_deducted, tp1_reliefs, category, month_number, annual_zakat)` function
- Salary Slip custom fields: `custom_ytd_gross` (Currency, read-only), `custom_ytd_pcb_deducted` (Currency, read-only) — auto-populated from prior submitted slips when payroll is run
- `before_submit` hook populates YTD fields by querying submitted slips for same employee, same year, earlier months
- Tests: verify Method 2 converges to same annual tax as Method 1 for constant-income employee; verify Method 2 smooths PCB for employee with variable monthly income

---

### US-060: Implement Benefits-in-Kind (BIK) Prescribed Value Calculation Module
**Priority:** High
**Files:** New `lhdn_payroll_integration/services/bik_calculator.py`, new `lhdn_payroll_integration/doctype/employee_bik_record/`, `report/ea_form/ea_form.py`

BIK provided by employers is taxable employment income under ITA Section 13(1)(b). LHDN prescribes specific annual values for common BIK items (Schedule 3 of ITA 1967 and Public Ruling No. 3/2013, updated 2019). Company car, fuel, driver, accommodation, club memberships must be valued and added to gross income for PCB computation. The current system has no BIK module; BIK omission understates employees' chargeable income and PCB.

**BIK prescribed values (2025):** Company car: RM1,200–RM50,000/year by purchase price bracket; Fuel: RM300/month; Driver: RM600/month; Accommodation: lower of defined value or 30% of gross income; Club membership: actual annual fee; Mobile phone (1st unit + 1 line): fully exempt; Additional phone lines: RM300/year each.

**Acceptance Criteria:**
- New DocType `Employee BIK Record` with fields: employee, payroll_period_year, car_bik_annual (Currency), fuel_bik_monthly (Currency), driver_bik_monthly (Currency), accommodation_bik_monthly (Currency), club_membership_annual (Currency), other_bik_annual (Currency)
- `bik_calculator.py` with `get_annual_car_bik(car_purchase_price)` lookup, `calculate_monthly_bik_total(employee_name, year)` aggregator
- PCB calculation in `pcb_calculator.py` adds monthly BIK value to gross income before computing annual taxable income
- EA Form Section B7 (BIK) populated from BIK records
- Tests: car price RM120,000 returns correct annual BIK; BIK total added to annual income increases PCB correctly

---

### US-061: Implement Perquisite Exemption Thresholds on Salary Components
**Priority:** High
**Files:** `fixtures/custom_field.json`, `fixtures/salary_component.json`, new `utils/exemption_calculator.py`

Certain perquisites are wholly or partially exempt from tax under ITA Section 13(1)(a) and Public Ruling No. 5/2019. Key exemptions: petrol/car allowance up to RM6,000/year (business use), childcare up to RM2,400/year, mobile phone handset (1 unit, fully exempt), group insurance premiums (wholly exempt), medical/dental/optical (wholly exempt). Currently, the PCB calculator adds full allowance amounts to income without applying exemption ceilings, overstating taxable income for most employees.

**Acceptance Criteria:**
- Add to Salary Component `custom_field.json`: `custom_exemption_type` (Select: None / Transport / Childcare / Group Insurance / Medical / Mobile Phone / Other), `custom_annual_exemption_ceiling` (Currency, 0 = unlimited exemption)
- `calculate_taxable_component(component_name, annual_amount)` in `utils/exemption_calculator.py` returns the taxable portion after exemption
- PCB annual income calculation uses taxable portion, not full amount, for exempt components
- Transport Allowance component in fixture gets `custom_exemption_type = Transport`, `custom_annual_exemption_ceiling = 6000`
- Tests: RM8,000 transport allowance → taxable portion = RM2,000; medical benefit → taxable portion = RM0

---

## HIGH PRIORITY — Statutory Forms and Reporting (US-062 to US-076)

### US-062: Add Borang E Mandatory Header Fields (Employer E-Number, Branch Code, Director Section)
**Priority:** High
**Files:** `fixtures/custom_field.json`, `report/borang_e/borang_e.py`

Borang E must include the employer's LHDN E-Number (No. Majikan / Employer Reference), LHDN branch (cawangan), and a PCB category breakdown (number of Category 1/2/3 employees). Section B of Borang E is specifically for director remuneration. Total CP38 deductions must appear as a separate line. These fields are currently absent from both the Company doctype and the Borang E report.

**Regulatory Basis:** ITA 1967 Section 83. Due 31 March annually.

**Acceptance Criteria:**
- Add to Company `custom_field.json`: `custom_employer_e_number` (Data, LHDN employer reference), `custom_lhdn_branch_code` (Data, LHDN cawangan code)
- Borang E report header includes: Company name, Company TIN, Employer E-Number, branch code, tax year
- Summary section: total Category 1 employees, Category 2, Category 3; total regular PCB; total CP38 deductions; total Zakat
- Section B: separate sub-table for director remuneration vs employee remuneration
- Tests verify E-Number and branch code appear in report; director rows segregated

---

### US-063: Implement e-CP39 API Submission to LHDN MyTax / e-PCB Plus
**Priority:** High
**Files:** New `lhdn_payroll_integration/services/ecp39_service.py`, `report/cp39_pcb_remittance/cp39_pcb_remittance.py`

LHDN's e-PCB Plus portal (part of MyTax) accepts programmatic PCB remittance submission. The current system only generates a CSV file that must be manually uploaded. For employers with 50+ employees, LHDN expects electronic submission. The service must authenticate with the LHDN MyTax API (separate OAuth flow from MyInvois), submit the formatted CP39 data, and store the submission reference number.

**Regulatory Basis:** ITA Section 107(1) — PCB remitted by 15th of following month.

**Acceptance Criteria:**
- New `ecp39_service.py` with `submit_cp39_to_lhdn(company_name, month, year)` function
- Authenticates with LHDN MyTax API using company credentials (separate from MyInvois client_id/secret — add `custom_mytax_client_id`, `custom_mytax_client_secret` on Company)
- Packages CP39 data from the CP39 report in LHDN-required pipe-delimited format
- Stores: submission reference number, submission datetime, response status in a new `LHDN CP39 Submission Log` DocType
- CP39 report page gains a "Submit to LHDN e-PCB Plus" button (whitelisted method)
- Tests: mocked HTTP — successful submission stores reference; failed submission logs error and does not create partial records

---

### US-064: Implement CP107 DocType for Foreign Employee Tax Clearance
**Priority:** High
**Files:** New `lhdn_payroll_integration/doctype/lhdn_cp107/`, `services/cp107_service.py`

When a non-citizen employee ceases employment, the employer must withhold the final month's remuneration and apply for a Tax Clearance Letter via CP107 before releasing payment. LHDN responds within 30 working days. Employer becomes jointly liable for the employee's tax if final payment is released without clearance (ITA Section 107A(4)). The existing CP21 DocType handles departure notification but does not implement the CP107 withholding workflow.

**Regulatory Basis:** ITA 1967 Section 107A — mandatory for all non-citizen employees ceasing employment.

**Acceptance Criteria:**
- New DocType `LHDN CP107` with fields: employee, last_working_date, final_month_salary (Currency), withholding_amount (Currency), clearance_letter_date (Date), clearance_reference (Data), status (Select: Draft / Submitted to LHDN / Clearance Received / Payment Released)
- Auto-created when Employee with `custom_is_foreign_worker = 1` status set to Left
- Salary Slip for final month of a foreign worker with open CP107 shows warning banner: "CP107 pending — do not release final payment until clearance received"
- HTML Print Format generates a CP107 application letter
- Tests: auto-creation on foreign employee termination; warning on salary slip

---

### US-065: Implement SOCSO Borang 3 — New Employee Notification to PERKESO
**Priority:** High
**Files:** New `lhdn_payroll_integration/doctype/socso_borang3/`, `services/socso_service.py`

SOCSO Act 1969 Section 19 requires employers to notify PERKESO within 30 days of a new insurable employee commencing employment via Borang 3. This is separate from the LHDN CP22 obligation. The two are parallel new-hire duties to different agencies. Failure to register employees with SOCSO is an offence under the Act.

**Acceptance Criteria:**
- New DocType `SOCSO Borang 3` with fields: employee, date_of_employment, wage_at_commencement (Currency), socso_scheme_category (Select: Category I (Employment Injury only) / Category II (Employment Injury + Invalidity Pension))
- Auto-created on Employee `after_insert` when `employment_type = Permanent or Contract` and employee is Malaysian/PR
- Alert shown (dashboard indicator) if not submitted within 30 days of `date_of_joining`
- PDF print format matching PERKESO Borang 3 layout
- Tests: auto-creation on eligible employee; alert when overdue; no auto-creation for foreign workers (ineligible for SOCSO Category II)

---

### US-066: Implement SOCSO Borang 4 — Employee Termination Notification to PERKESO
**Priority:** High
**Files:** New `lhdn_payroll_integration/doctype/socso_borang4/`, `services/socso_service.py`

SOCSO Act 1969 Section 19 requires employers to notify PERKESO within 30 days of employee termination via Borang 4. Failure to notify means the employer may continue to be liable for SOCSO contributions.

**Acceptance Criteria:**
- New DocType `SOCSO Borang 4` with fields: employee, date_of_termination, reason (Select: Resignation / Termination / Retirement / Death / Contract End), last_wage (Currency)
- Auto-created when Employee status set to Left (for SOCSO-eligible employees)
- Alert if not submitted within 30 days of termination date
- PDF print format matching PERKESO Borang 4 layout
- Tests: auto-creation on eligible employee termination; alert when overdue

---

### US-067: Generate EPF i-Akaun Electronic Upload File
**Priority:** High
**Files:** New `lhdn_payroll_integration/report/epf_borang_a/` (extend existing), or new `services/epf_iakaun_service.py`

The EPF i-Akaun employer portal accepts electronic file uploads for contribution submission. The current EPF Borang A is a screen report only. The i-Akaun upload format is a fixed-width or delimited text file with specific field positions for employer reference, employee NRIC, EPF member number, wages, employee contribution, employer contribution. Manual entry for large headcounts is impractical.

**Regulatory Basis:** EPF Act 1991 Section 43(3).

**Acceptance Criteria:**
- New export option on EPF Borang A report: "Export i-Akaun File" generates a `.txt` file in KWSP i-Akaun upload format
- File includes: employer EPF registration number (add `custom_epf_employer_registration` on Company), employee NRIC (no hyphens), EPF member number, wages, employee EPF amount, employer EPF amount
- Employer contribution uses the 12%/13% differential rate (see US-073)
- Tests: file structure correct for a 3-employee payroll; EPF registration number present in header

---

### US-068: Generate SOCSO and EIS e-Caruman Upload File (PERKESO ASSIST Portal)
**Priority:** High
**Files:** New `services/socso_eis_upload_service.py`, extend existing SOCSO and EIS reports

PERKESO's ASSIST portal accepts a combined SOCSO+EIS contribution file in a specific format. The current SOCSO Borang 8A and EIS monthly reports are screen reports only. Employers need an upload-ready file.

**Regulatory Basis:** SOCSO Act 1969; EIS Act 2017.

**Acceptance Criteria:**
- New export "Export PERKESO e-Caruman File" on both SOCSO and EIS reports
- Combined SOCSO+EIS file format: employer SOCSO number (add `custom_socso_employer_number` on Company), employee NRIC, employee SOCSO number, wages, SOCSO employee, SOCSO employer, EIS employee, EIS employer
- SOCSO uses bracketed table lookup (see US-074); EIS capped at RM6,000 wage ceiling (see US-075)
- Tests: file structure correct; ceiling enforcement visible in export

---

### US-069: Implement Ordinary Rate of Pay (ORP) Calculator and Overtime Validation
**Priority:** High
**Files:** New `utils/employment_compliance.py`, `fixtures/custom_field.json`

Employment Act 1955 Section 60A(3) mandates OT rates: 1.5x for normal day OT, 2.0x for rest day (full day), 3.0x for public holiday. These rates apply to employees earning ≤RM4,000/month. The Ordinary Rate of Pay (ORP) = Monthly Salary / 26 (for daily rate) or Monthly Salary / (contracted hours per month) for hourly rate. No ORP calculation or OT validation exists in the app, making it impossible to verify OT underpayment.

**Acceptance Criteria:**
- `calculate_orp(monthly_salary, contracted_hours_per_month=None)` utility: returns daily ORP if hours not specified (salary/26), hourly ORP if hours specified
- Add `custom_contracted_hours_per_month` (Float, default 191.5) on Employee
- Add `custom_day_type` (Select: `Normal / Rest Day / Public Holiday`) on Salary Component for OT components
- OT validation in `validate_document_for_lhdn()`: warn if OT component amount < orp × hours × statutory multiplier for employees earning ≤RM4,000/month
- Tests: verify 1.5x, 2x, 3x multiplier warnings at correct salary thresholds

---

### US-070: Implement Foreign Worker Levy Tracking (FWCMS / Multi-Tier Levy Model)
**Priority:** High
**Files:** New `lhdn_payroll_integration/doctype/foreign_worker_levy/`, `fixtures/custom_field.json`

The Foreign Workers Levy Act 2021 requires employers to pay an annual FWCMS levy per foreign worker (RM410–RM2,500/year, varying by sector, source country, and dependency ratio tier). The Multi-Tier Levy Model (MTLM) effective 1 January 2025 sets levy rates based on the employer's local-to-foreign worker ratio. Non-payment leads to immigration enforcement. The current app uses `custom_is_foreign_worker = 1` on Employee only for e-invoice TIN substitution and does not track levy obligations.

**Acceptance Criteria:**
- Add to Employee: `custom_fw_levy_rate` (Currency, annual levy amount), `custom_fw_levy_due_date` (Date), `custom_fw_levy_receipt_ref` (Data)
- New DocType `Foreign Worker Levy Payment` with fields: employee, levy_period_year, levy_amount, payment_date, receipt_number
- New Script Report `foreign_worker_levy` with Company and Year filters — lists all foreign employees, levy amounts due/paid, renewal dates
- Dashboard alert for foreign workers whose levy is overdue or due within 30 days
- Tests: report shows levy status; overdue detection logic correct

---

### US-071: Implement Payroll Bank Disbursement File Generator (Maybank + CIMB + DuitNow ISO 20022)
**Priority:** High
**Files:** New `lhdn_payroll_integration/services/bank_disbursement_service.py`, new DocType `Payroll Bank Disbursement`

A payroll system without bank disbursement file generation forces manual bank transfers for every employee, making the system impractical for payroll operations. Malaysian payroll files must conform to each bank's portal format. The PayNet DuitNow Bulk ISO 20022 `pain.001.001.03` format with `SALA` purpose code is the emerging standard (hard migration deadline November 2025 for H2H/SFTP gateways).

**Bank formats required:**
- **Maybank M2E**: Pipe-delimited, 5-digit org code, employee name/IC/account/amount fields
- **CIMB BizChannel**: CSV with Header/Detail/Footer structure, bank validation tool compatible
- **DuitNow Bulk (ISO 20022)**: XML `pain.001.001.03` with `<PmtInfId>SALA</PmtInfId>` purpose code, employee DuitNow ID (NRIC or account), `EndToEndId` (max 35 chars)

**Acceptance Criteria:**
- New DocType `Payroll Bank Disbursement` linked to Payroll Entry with: bank (Select: Maybank / CIMB / Public Bank / RHB / DuitNow Bulk), disbursement_date, total_amount
- Add Employee fields: `custom_bank_name` (Select: Maybank/CIMB/Public Bank/RHB/Other), `custom_bank_code` (Data, 8-digit PayNet code), `custom_account_type` (Savings/Current)
- `generate_bank_file(payroll_entry_name, bank)` service returns file bytes for download
- Generate Payroll Entry "Generate Bank File" button visible to Payroll Officer role
- Tests: Maybank file has correct pipe format; DuitNow XML validates against pain.001.001.03 schema; SALA purpose code present

---

### US-072: Fix HRDF Levy Rate — 1% Mandatory for All Employers with ≥10 Employees
**Priority:** High
**Files:** `fixtures/custom_field.json`, `report/hrdf_monthly_levy/hrdf_monthly_levy.py`

The current `custom_hrdf_levy_rate` Select field offers "0.5% for 10-49 employees, 1.0% for 50+", which is factually incorrect. HRD Corp regulations (Human Resources Development Act 2001, amended 2021) prescribe 1% for ALL employers with 10+ Malaysian employees in mandatory sectors, regardless of headcount above 10. The 0.5% voluntary option applies only to companies with 5–9 employees choosing to participate voluntarily. Systematic underpayment at 0.5% creates HRD Corp surcharge liability.

**Acceptance Criteria:**
- Update `custom_hrdf_levy_rate` description and options: `0.5% (Voluntary — 5–9 employees)`, `1.0% (Mandatory — 10+ employees)`
- Add `custom_hrdf_mandatory_sector` (Check) on Company — enforce 1% when checked and headcount ≥ 10
- `hrdf_monthly_levy.py` warns if the levy rate in use does not match the mandatory rate for the company's headcount
- Tests: 10-employee company in mandatory sector uses 1%, not 0.5%; 7-employee company allows 0.5% voluntary

---

### US-073: Enforce EPF Employer Rate Differential (13% for Salary ≤RM5,000, 12% for >RM5,000)
**Priority:** High
**Files:** New `utils/statutory_rates.py`, `report/epf_borang_a/`, `fixtures/salary_component.json`

The EPF employer contribution rate has a differential: 13% for employees earning ≤RM5,000/month, 12% for earnings >RM5,000/month (effective from EPF Contribution Rate Revision 2022). The current fixture seeds a single "EPF - Employer" salary component with no rate differential logic. Employers paying 12% for employees below RM5,000 are underpaying EPF — KWSP can impose a late payment dividend surcharge under EPF Act Section 45.

**Acceptance Criteria:**
- New `calculate_epf_employer_rate(monthly_gross)` in `utils/statutory_rates.py` returns 0.13 if gross ≤ 5000, else 0.12
- EPF Borang A report validates employer EPF amount against the correct rate for each employee; flags discrepancies
- Salary component validation hook warns when `EPF - Employer` component amount deviates from the statutory rate by >5%
- Tests: employee at RM5,000 → employer 13%; employee at RM5,001 → employer 12%

---

### US-074: Implement SOCSO Contribution Bracketed Table Lookup (Jadual Kadar Caruman)
**Priority:** High
**Files:** New `utils/statutory_rates.py`, `report/socso_borang_8a/`, `fixtures/custom_field.json`

SOCSO contributions are NOT a straight percentage — they are fixed amounts determined by wage bracket per the SOCSO First Schedule (Jadual Kadar Caruman), with 72 wage brackets from RM0 to RM6,000+. The ceiling wage is RM6,000/month (updated October 2024, previously RM5,000). Using wrong contribution amounts (even slightly) risks both under- and over-deduction. The SOCSO Borang 8A report currently passes through whatever amounts were entered without validation.

**Acceptance Criteria:**
- `calculate_socso_contribution(wages, scheme='both')` in `utils/statutory_rates.py` implements the First Schedule table (embed as constant dict or fixture); returns `{'employee': x, 'employer': y}`
- Wage ceiling capped at RM6,000 (updated from RM5,000 as per October 2024 amendment)
- SOCSO Borang 8A validation: warn if reported SOCSO amounts deviate >5% from scheduled amounts for the wage bracket
- Tests: wages at RM1,500, RM3,000, RM5,500, RM6,000, RM6,001 (ceiling applies to RM6,001 case) → correct scheduled amounts returned

---

### US-075: Enforce EIS Contribution Ceiling (RM6,000) and Age/Foreign Worker Exemptions
**Priority:** High
**Files:** `utils/statutory_rates.py`, `report/eis_monthly/`

EIS (SIP) under Employment Insurance System Act 2017, Second Schedule: 0.2% employee + 0.2% employer on insured wages capped at RM6,000/month. Employees aged <18 or ≥60 are exempt. Foreign workers are NOT covered. These exemptions and the updated ceiling (October 2024, aligned with SOCSO) are not currently enforced — the EIS monthly report passes through whatever salary component amounts were entered.

**Acceptance Criteria:**
- `calculate_eis_contribution(wages, date_of_birth, is_foreign)` in `utils/statutory_rates.py`: returns 0 if foreign or age <18 or age ≥60; else `min(wages, 6000) * 0.002`
- Age calculated from Employee `date_of_birth` vs payroll period
- EIS monthly report validates amounts against the calculation; flags employees incorrectly included (foreign workers, out-of-age-range) or with wrong ceiling
- Tests: foreign worker → 0; age 17 → 0; age 60 → 0; wages RM7,000 → EIS on RM6,000 only

---

### US-076: Implement Age-Based EPF/SOCSO/EIS Statutory Rate Transitions at Age 60
**Priority:** High
**Files:** `utils/statutory_rates.py`, hooks on Salary Slip

At age 60, statutory contribution rules change significantly: EPF employee rate changes to 0% (or 5.5% statutory/0% minimum effective 2021 amendments for over-60 employees); EPF employer rate drops to 4%; SOCSO coverage ceases; EIS coverage ceases. The system has no age-tracking logic — employees who turn 60 mid-year will continue to have wrong statutory deductions applied until manually corrected.

**Regulatory Basis:** EPF Act 1991, Third Schedule; SOCSO Act 1969 (coverage limit age 60); EIS Act 2017.

**Acceptance Criteria:**
- `get_statutory_rates_for_employee(employee_name, payroll_date)` in `utils/statutory_rates.py` returns correct EPF/SOCSO/EIS rates based on employee age at payroll date
- `before_submit` hook on Salary Slip warns if EPF/SOCSO/EIS component amounts do not match age-appropriate statutory rates
- Dashboard alert on Employee record when employee is within 3 months of turning 60 (to allow employer preparation)
- Tests: employee who turns 60 in the payroll month — verify transition rates applied; employee aged 59 — pre-transition rates

---

## MEDIUM PRIORITY — Additional Compliance and Statutory (US-077 to US-091)

### US-077: Implement TP3 Carry-Forward Declaration for New Hires (Prior Employer YTD)
**Priority:** Medium
**Files:** New `lhdn_payroll_integration/doctype/employee_tp3/`, `services/pcb_calculator.py`

When an employee joins mid-year having worked for a previous employer, PCB calculation must account for income and PCB already deducted by the previous employer in the same calendar year. Without TP3 data, the new employer's PCB calculator starts from zero, understating the employee's annualised income and under-deducting PCB — potentially causing the employee to owe tax at year-end. The employee submits Borang TP3 to the new employer with their prior income and PCB details.

**Regulatory Basis:** LHDN TP3 form (Pemberitahuan Pendapatan Bagi Tahun Semasa) — submitted by employee to new employer.

**Acceptance Criteria:**
- New DocType `Employee TP3 Declaration` with fields: employee, tax_year, previous_employer_name, previous_employer_tin, prior_gross_income (Currency), prior_epf_deducted (Currency), prior_pcb_deducted (Currency), joining_month
- `calculate_pcb()` / `calculate_pcb_method2()` accepts `tp3_prior_gross`, `tp3_prior_pcb` parameters; adds prior income to YTD for annualisation; subtracts prior PCB from YTD PCB deducted
- CP22 workflow triggers a reminder to collect TP3 from new employee if joining month is not January
- Tests: employee joining in July with RM30,000 prior income — verify annualised income uses combined figure; PCB correctly adjusted

---

### US-078: Extend CP8D with Income Type Breakdown (Bonus, Commission, Gratuity, Other)
**Priority:** Medium
**Files:** `report/cp8d/cp8d.py`, `report/cp8d_efiling/cp8d_efiling.py`

The LHDN CP8D e-Filing specification (2024 revision) requires separate columns for income sub-categories: Total Gross Income, Gross Bonus/Commission, Gross Gratuity, Other Income, Total EPF, Total PCB. The current CP8D reports submit only three income figures. Incomplete CP8D data can trigger LHDN queries on employer submissions.

**Acceptance Criteria:**
- Extend both `cp8d.py` and `cp8d_efiling.py` with additional columns sourced from the EA Section tagging (US-056): bonus (B4), commissions (B3), gratuity (B5, after exemption), other (B9)
- CSV export format matches the LHDN e-Filing CP8D 2024 column specification exactly
- Tests: employee with bonus and commission components — verify amounts appear in correct columns

---

### US-079: Implement CP58 Agent/Dealer Non-Employment Income Statement
**Priority:** Medium
**Files:** New `lhdn_payroll_integration/report/cp58_agent_statement/`

ITA 1967 Section 83A(1A) and P.U.(A) 220/2019 require payers to issue Borang CP58 to agents, dealers, and distributors who receive commission/incentive payments, by 31 March each year. This covers contractors and commission agents who are NOT employees and thus do not receive EA Forms. Relevant for companies with sales agent networks, franchise distributors, or referral programs.

**Acceptance Criteria:**
- New Script Report `cp58_agent_statement` with Company and Year filters
- Queries Expense Claims and additional payment records tagged to contractors (non-employees) with payment type `Commission`
- Output per agent: Agent Name, NRIC/Registration Number, Payment Amount, Month, Total Annual
- Print Format matching the LHDN-prescribed CP58 layout
- Tests: contractor with 3 commission payments — correct annual total in CP58

---

### US-080: Track Maternity/Paternity Leave and Validate Maternity Pay Rate
**Priority:** Medium
**Files:** New `utils/employment_compliance.py`, `fixtures/custom_field.json`, `report/lhdn_payroll_compliance/`

Employment Act 1955 Section 37 (A1651 amendment): 98 consecutive days maternity leave. Section 60FA: 7 consecutive days paternity leave for up to 5 live births. Maternity allowance must be paid at the Ordinary Rate of Pay. The system has no mechanism to track leave taken, validate payment, or alert HR when limits are approached or exceeded.

**Acceptance Criteria:**
- Add to Employee: `custom_maternity_leave_taken` (Int, cumulative days), `custom_paternity_leave_taken` (Int, cumulative days), `custom_paternity_births_claimed` (Int, max 5)
- `validate_maternity_pay(salary_slip)` checks: maternity pay line amount ≥ ORP × days taken; days taken ≤ 98 per confinement
- Payroll Compliance report adds a Leave Compliance section flagging over-entitlement or underpayment
- Tests: maternity pay below ORP triggers warning; days >98 triggers warning; paternity claims >5 births triggers warning

---

### US-081: Implement Working Hours Compliance Check (45-Hour Weekly Limit, EA 1955)
**Priority:** Medium
**Files:** `utils/employment_compliance.py`, `fixtures/custom_field.json`

Employment Act 1955 Section 60A(1) post-2022: maximum 45 hours per week (reduced from 48). Excessive OT can cause total monthly hours to breach legal limits. No automated check exists.

**Acceptance Criteria:**
- Add to Employee: `custom_contracted_weekly_hours` (Float, default 45)
- `validate_weekly_hours(salary_slip)` calculates total hours worked (contracted + OT) and warns if any week exceeds 45 hours or if total OT hours exceed monthly statutory limit
- Payroll Compliance report shows working hours compliance flag per employee
- Tests: 46-hour week triggers warning; 45-hour week passes

---

### US-082: Implement Termination and Lay-Off Benefits Calculator
**Priority:** Medium
**Files:** New `utils/employment_compliance.py`, `lhdn_payroll_integration/doctype/lhdn_cp22a/lhdn_cp22a.py`

Employment (Termination and Lay-Off Benefits) Regulations 1980: statutory minimum termination payment is 10 days' wages per year of service for <2 years, 15 days for 2–5 years, 20 days for >5 years. Without a calculator, HR may inadvertently underpay, creating Employment Act liability.

**Acceptance Criteria:**
- `calculate_termination_benefits(employee, termination_date)` utility: calculates years of service, determines applicable rate, returns `statutory_minimum_termination_pay` in RM
- CP22A DocType extended with fields: `years_of_service` (Float, auto-calculated), `statutory_minimum_termination_pay` (Currency, auto-populated), `actual_termination_pay` (Currency, manual), `underpayment_warning` (Read Only — shows if actual < statutory)
- Tests: 1 year 6 months → 10 days/year rate; 3 years → 15 days/year rate; 7 years → 20 days/year rate

---

### US-083: Implement Expatriate Gross-Up Calculator and DTA Country Table
**Priority:** Medium
**Files:** New `lhdn_payroll_integration/services/expatriate_service.py`, `fixtures/custom_field.json`

Expatriates on tax-equalised packages require an iterative gross-up to find the gross salary that produces the desired net after Malaysian tax. The 182-day residency rule determines resident vs non-resident tax treatment. Double Tax Agreement (DTA) countries (Singapore, UK, US, Australia, etc.) may provide treaty exemptions or reduced rates.

**Acceptance Criteria:**
- Add to Employee: `custom_dta_country` (Select — ISO country codes with DTA agreements), `custom_is_tax_equalised` (Check), `custom_malaysia_presence_days` (Int, YTD — triggers residency check)
- `calculate_gross_up(desired_net, annual_reliefs, category, max_iterations=50)` iterative solver
- DTA country list with key treaty provisions (183-day rule, reduced WHT rates) stored as a fixture or system setting
- Tests: gross-up for net RM10,000/month converges to correct gross; residency test flags non-resident at <182 days

---

### US-084: Implement ESOS / Share Option Gain Calculation and EA Form B10
**Priority:** Medium
**Files:** New `lhdn_payroll_integration/doctype/employee_share_option/`, `report/ea_form/`

ITA 1967 Section 25 and Public Ruling No. 1/2021: gains from ESOS/ESPP exercise are taxable employment income in the year of exercise. Gain = (Market Price on exercise date - Exercise Price) × shares exercised. This must be included in annual income for PCB computation and disclosed in EA Form Section B10.

**Acceptance Criteria:**
- New DocType `Employee Share Option Exercise` with fields: employee, grant_date, exercise_date, exercise_price (Currency), market_price_on_exercise (Currency), shares_exercised (Int), taxable_gain (Currency, auto-calculated)
- `taxable_gain` added to annual income for PCB calculation in the exercise month (treated as irregular/bonus payment — apply annualisation rule from US-018)
- EA Form B10 populated from share option exercise records for the year
- Tests: exercise 1,000 shares at RM2 exercise price, RM5 market price → taxable gain RM3,000 added to income

---

### US-085: Implement Approved Pension Scheme Full Retirement Gratuity Exemption
**Priority:** Medium
**Files:** `services/pcb_calculator.py`, `fixtures/custom_field.json`

ITA 1967 Schedule 6, paragraph 30: retirement gratuity paid from an approved company pension scheme to an employee retiring at age 55 (or compulsory retirement at 60) is FULLY exempt from tax. The current `pcb_calculator.py` implements only the partial RM1,000/year exemption (para 25), missing the full exemption for approved scheme retirees.

**Acceptance Criteria:**
- Add to Employee: `custom_approved_pension_scheme` (Check) — marks employee as member of an LHDN-approved pension scheme
- `calculate_pcb()`: if `custom_approved_pension_scheme = True` and employee age ≥55 and payment tagged as gratuity → exempt 100% of gratuity (not just RM1,000/year)
- EA Form B5 reflects the applied exemption amount
- Tests: age 55 with approved scheme — full gratuity exempt; age 55 without approved scheme — RM1,000/year exemption only

---

### US-086: Assess and Implement XAdES XML Digital Signature for MyInvois Self-Billed Phase 2
**Priority:** Medium
**Files:** `services/payload_builder.py`, new `utils/xml_signer.py`

MyInvois e-Invoice Guidelines (LHDN SDK v3.x) state that API submissions must use XAdES standard with RSA-SHA256 hashing and certificates issued by MSC Trustgate or DigiCert Malaysia. Phase 2 implementors (RM25M–RM100M revenue, mandatory from 1 January 2025) are now live. If digital signature is now required for self-billed payroll e-invoices, the current `payload_builder.py` which emits no `ds:Signature` element will produce non-compliant XML.

**Acceptance Criteria:**
- Review LHDN MyInvois SDK v3.2 release notes to confirm whether `ds:Signature` is mandatory for self-billed invoices
- If mandatory: add `utils/xml_signer.py` implementing XAdES BeS signature using `lxml` and `xmlsec` libraries; add `custom_digital_cert_path` and `custom_digital_cert_password` (Password) fields on Company
- If not yet mandatory: add a configuration flag `custom_enable_xml_signature` (Check, default off) on Company and prepare the signing utility as an optional feature
- Tests: signed XML validates against XAdES schema; signature verification using certificate public key succeeds

---

### US-087: Build Employee Self-Service Portal for Payslips, EA Forms, and TP1 Submission
**Priority:** Medium
**Files:** New `lhdn_payroll_integration/templates/pages/employee_portal.html`, `lhdn_payroll_integration/api/employee_portal.py`

Employment Act 1955 Section 25A requires employers to provide wage slips. A self-service portal reduces HR workload for payslip distribution and EA form issuance. Employees should be able to view payslips, download EA Forms, and submit TP1 relief declarations online without emailing HR.

**Acceptance Criteria:**
- Frappe Web Page `/employee-portal` accessible by employees via their ERPNext user account (Employee linked to User)
- Portal shows: all submitted Salary Slips for logged-in employee, EA Form PDF download for any past year, YTD earnings summary, current TP1 declarations
- TP1 online submission form creates/updates `Employee TP1 Relief` record for current year
- Access restricted to the employee's own records via `frappe.session.user` validation
- Tests: employee A cannot access employee B's records; TP1 form submission creates correct DocType record

---

### US-088: Implement PCB Change Audit Trail DocType
**Priority:** Medium
**Files:** New `lhdn_payroll_integration/doctype/pcb_change_log/`

ITA 1967 Section 82 requires employers to maintain records for 7 years. Best practice: any change to PCB amount (manual override on Salary Slip, TP1 relief update, CP38 addition/expiry, category change) should be logged with reason, user, and timestamp. Auditors examining PCB discrepancies need a clear change history.

**Acceptance Criteria:**
- New DocType `PCB Change Log` with fields: employee, payroll_period, change_type (Select: TP1 Update / CP38 Applied / Category Change / Manual Override / Recalculation), old_pcb_amount (Currency), new_pcb_amount (Currency), reason (Text), changed_by (Link to User), change_datetime
- Automatically created whenever PCB component on Salary Slip changes after initial save
- PCB Change Log viewable from Employee record (linked list view)
- Tests: updating TP1 relief creates log entry; CP38 expiry creates log entry

---

### US-089: Generate DuitNow Bulk Payroll File (ISO 20022 pain.001.001.03 with SALA Purpose Code)
**Priority:** Medium
**Files:** `services/bank_disbursement_service.py` (extend from US-071)

PayNet hard migration deadline for ISO 20022 on H2H/SFTP gateways is November 2025. CIMB, Maybank, and RHB are all upgrading their gateways to XML-native by Q4 2025. The DuitNow Bulk ISO 20022 `pain.001.001.03` format with `SALA` purpose code will become the de-facto Malaysian payroll disbursement standard, replacing legacy IBG flat files.

**Acceptance Criteria:**
- `generate_duitnow_bulk_xml(payroll_entry_name)` generates an ISO 20022 `pain.001.001.03` XML file
- `<PmtInf>/<PmtTpInf>/<CtgyPurp>/<Cd>SALA</Cd>` mandatory purpose code for payroll transactions
- `<CdtTrfTxInf>/<Cdtr>/<Id>/<PrvtId>/<Othr>/<Id>` uses DuitNow ID (employee NRIC or registered mobile)
- `<EndToEndId>` unique per transaction, max 35 chars (e.g., `PAYROLL-{slip_name}-{YYYYMM}`)
- Tests: generated XML validates against pain.001.001.03 schema; SALA purpose code present; EndToEndId within 35 chars

---

### US-090: Implement Foreign Worker EPF Mandatory Contribution (Effective October 2025)
**Priority:** Medium
**Files:** `utils/statutory_rates.py`, `report/epf_borang_a/`, `fixtures/salary_component.json`

EPF Board announced mandatory EPF contributions for non-citizen employees (foreign workers) starting October 2025: employer 2% + employee 2% (initial rates, stepping up over time). Previously, foreign workers were exempt from EPF contributions. This affects all employers with foreign workers — new salary components must be added and the EPF rate calculator must return the correct rates for foreign vs Malaysian employees.

**Regulatory Basis:** EPF (Amendment) 2024 announcement, effective October 2025.

**Acceptance Criteria:**
- `calculate_epf_employer_rate(monthly_gross, is_foreign, payroll_date)` returns 2% for foreign workers when `payroll_date >= 2025-10-01`; otherwise existing 12%/13% differential for citizens/PRs
- Add salary components: `EPF Employee (Foreign Worker)` (Deduction, 2%) and `EPF Employer (Foreign Worker)` (Deduction, 2%)
- EPF Borang A report includes foreign worker rows with correct contribution rates
- Tests: October 2025 foreign worker payroll → 2%/2% rates; September 2025 → 0%; Malaysian employee unaffected

---

### US-091: Enforce SOCSO/EIS Wage Ceiling Update to RM6,000 (October 2024 Amendment)
**Priority:** Medium
**Files:** `utils/statutory_rates.py`, `report/socso_borang_8a/`, `report/eis_monthly/`

SOCSO and EIS insured salary ceiling was updated from RM5,000 to RM6,000/month effective October 2024. Employers who have not updated their payroll system continue to cap contributions at RM5,000, causing systematic underpayment. This is distinct from the contribution table enforcement (US-074) — it is specifically a ceiling value update.

**Acceptance Criteria:**
- `SOCSO_WAGE_CEILING` and `EIS_WAGE_CEILING` constants in `utils/statutory_rates.py` updated to RM6,000 with an effective date comment (October 2024)
- SOCSO and EIS reports validate against the correct ceiling
- Tests: employee with RM5,500 wages — SOCSO/EIS contributions computed on RM5,500 (not RM5,000); RM6,500 wages → contributions on RM6,000

---

## LOW PRIORITY (US-092 to US-095)

### US-092: Implement LHDN MyInvois Webhook Callback Handler
**Priority:** Low
**Files:** New `lhdn_payroll_integration/api/lhdn_webhook.py`, `hooks.py`

LHDN MyInvois SDK changelog (Q1 2025) announces webhook support for document status push notifications, eliminating the need for hourly polling. Webhooks would reduce unnecessary API calls and provide real-time status updates.

**Acceptance Criteria:**
- New whitelisted API endpoint `/api/method/lhdn_payroll_integration.api.lhdn_webhook.receive_status_callback` accepting POST from LHDN
- Validates `X-LHDN-Signature` header (HMAC-SHA256 using webhook secret stored on Company)
- Updates document status immediately on receiving callback
- Add `custom_lhdn_webhook_secret` (Password) on Company
- Tests: valid callback → document status updated; invalid signature → 401 rejected

---

### US-093: Add Sabah/Sarawak Labour Ordinance Flag on Employee
**Priority:** Low
**Files:** `fixtures/custom_field.json`, `utils/employment_compliance.py`

Employees in Sabah (Labour Ordinance Cap. 67) and Sarawak (Cap. 76) are governed by different employment ordinances that may have different annual leave entitlements and overtime rules compared to the Peninsular Malaysia Employment Act 1955.

**Acceptance Criteria:**
- Add `custom_labour_jurisdiction` (Select: Peninsular Malaysia / Sabah / Sarawak) on Employee — auto-set based on state code if address recorded
- OT and leave validation logic (US-069, US-080) applies correct jurisdiction rules based on this field
- Tests: Sabah employee uses Sabah Ordinance OT multipliers where they differ from EA 1955

---

### US-094: Add EC Form Variant for Statutory/Government Body Employers
**Priority:** Low
**Files:** New `report/ec_form/`, `print_format/ec_form/`

ITA 1967 Section 83A — Borang EC is the government/statutory body equivalent of the EA Form. If any Prisma clients are statutory bodies, GLCs, or government-linked companies, they must issue EC Forms instead of EA Forms.

**Acceptance Criteria:**
- New Script Report `ec_form` cloning EA Form structure with EC-specific field labels and layout per LHDN EC Form gazetted format
- Company-level flag `custom_is_statutory_employer` (Check) — switches default to EC Form generation
- Tests: statutory employer generates EC Form headers; non-statutory employer uses EA Form

---

### US-095: Implement Multi-Tier Levy Model (MTLM) Rate Calculation for Foreign Workers
**Priority:** Low
**Files:** `lhdn_payroll_integration/doctype/foreign_worker_levy/` (extend from US-070)

The Multi-Tier Levy Model (MTLM) effective January 2025 sets foreign worker levy rates based on the employer's dependency ratio (local:foreign worker headcount ratio). Higher dependency = higher levy rate. Tier 1 (low dependency): RM410/year; Tier 2 (medium): RM1,230/year; Tier 3 (high): RM2,500/year — varies by sector and source country.

**Acceptance Criteria:**
- `calculate_fw_levy_tier(local_headcount, foreign_headcount, sector)` utility returning levy rate per worker
- Foreign Worker Levy report shows tier calculation and total annual levy liability
- Tests: dependency ratio above Tier 3 threshold returns highest rate

---
