# PRD: LHDN Payroll Integration — Gap Closure v2.0
<!-- prd_version: 2.0 | status: ACTIVE | last_updated: 2026-02-27 -->

**App:** `lhdn_payroll_integration` (Frappe ERPNext v16)
**Date:** 2026-02-27
**Source:** Specialist gap analysis of existing codebase (post-v1 audit, 78 stories complete)
**Total Stories:** 50 (US-001 to US-050)

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
