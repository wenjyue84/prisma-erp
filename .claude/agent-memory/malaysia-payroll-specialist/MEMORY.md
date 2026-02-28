# Malaysia Payroll Specialist — Agent Memory

## Project Context
- ERPNext v16 + Frappe app: `lhdn_payroll_integration`
- Location: `lhdn_payroll_integration/` in repo root
- Integrates with MyInvois (LHDN e-invoicing) and payroll tax systems
- 78/78 PRD v2.0 stories complete as of 2026-02-28

## PCB Calculator — Current State & Known Gaps
- File: `lhdn_payroll_integration/services/pcb_calculator.py`
- IMPLEMENTS: Progressive bands AY2024, non-resident 30%, bonus annualisation, gratuity Schedule 6, mid-month proration
- MISSING: TP1/TP2/TP3 relief form handling (only self+spouse+child reliefs hardcoded), Zakat deduction offset, CP38 additional deduction, PCB category codes (1/2/3), YTD recalculation when category changes mid-year, MTD Method 2 (actual YTD), BIK perquisite value reduction to chargeable income

## EA Form — Current State & Known Gaps
- File: `lhdn_payroll_integration/report/ea_form/ea_form.py`
- MISSING: ~20 mandatory disclosure fields from actual Borang EA format (Section B items: perquisites, BIK, gross dividends, pension, gratuity, leave encashment, section 13(1) benefits breakdown). Report only shows 6 columns vs the full EA form specification.

## CP8D / Borang E — Current State & Known Gaps
- Both reports query salary slip data but MISSING: employer reference number, LHDN employer registration (E number), income tax branch code (cawangan), Borang E Section B (director remuneration), employee PCB category field
- No direct e-Filing API submission (only CSV/report output)

## Statutory Reports — Current State
- EPF Borang A: present but location appears duplicate (two path variants)
- SOCSO Borang 8A: present, includes NRIC and SOCSO member number
- EIS Monthly: present
- HRDF Monthly + PSMB/6 Annual: present
- MISSING reports: SOCSO Borang 3 (new employees), SOCSO Borang 4 (termination), EPF i-Akaun file upload format, e-Caruman SOCSO portal format

## Custom Fields — Current State
- Employee: LHDN TIN, ID type/value, MSIC code, is_foreign_worker, nationality_code, bank account, payment means, state code, SST reg, worker type, EPF member#, SOCSO member#, address fields, marital status, children, is_non_resident
- MISSING on Employee: PCB category (1/2/3), TP1 relief amounts, income tax branch code, EIS member number, date of birth (for SOCSO age check), employment commencement date
- MISSING on Salary Slip: CP38 additional deduction field, BIK/perquisite amounts, zakat offset field

## Submission Architecture
- Self-billed e-invoice (type 11) for Contractors and Directors only
- Regular employees (Employee worker type) are EXEMPT — correct per LHDN FAQ
- Services: exemption_filter, submission_service, payload_builder, status_poller, consolidation_service, credit_note_service, cancellation_service, retention_service

## Key Regulatory References (frequently needed)
- PCB computation: LHDN "Kaedah Pengiraan PCB" 2024 (computerised method)
- Borang E: ITA 1967 Section 83, due 31 March
- EA Form: ITA 1967 Section 83A, due 28 February
- CP39 remittance: due 15th of following month
- EPF: EPF Act 1991, contribution tables gazette
- SOCSO: SOCSO Act 1969 (Act 4), ceiling RM6,000
- EIS: Employment Insurance System Act 2017 (Act 800)
- HRDF: PSMB Act 2001, HRD Corp
- Min wage: Minimum Wages Order 2022 (RM1,500 nationwide effective 1 May 2022)
- Employment Act: EA 1955 as amended by Act A1651 (2022)
