#!/usr/bin/env python3
"""Append US-051 to US-095 (v3.0 stories) to prd.json."""
import json, pathlib

PRD_PATH = pathlib.Path(__file__).parent.parent / "prd.json"

NEW_STORIES = [
  # ─── CRITICAL ───────────────────────────────────────────────────────────────
  {
    "id": "US-051",
    "title": "Add PCB Category Code (1/2/3) on Employee with CP39 and EA Form integration",
    "priority": "critical",
    "description": "LHDN requires three distinct PCB category codes: Category 1 (single or married with working spouse), Category 2 (married non-working spouse — RM4,000 spouse relief), Category 3 (single parent). The current calculator uses married=True/False which does not handle Category 3, nor transmit the category in CP39 or EA Form. LHDN CP39 CSV upload format requires a PCB Category column. Wrong category causes systematic under/over-deduction triggering penalties under ITA Section 107C(10) of RM200-RM20,000 per offence.",
    "acceptanceCriteria": [
      "Add custom_pcb_category Select (options: 1, 2, 3) to Employee custom_field.json",
      "calculate_pcb() accepts category parameter; Category 2 applies spouse relief RM4,000; Category 3 applies RM4,000 for single parents per ITA Section 46A",
      "CP39 report CSV includes PCB Category column for each employee row",
      "EA Form report captures and displays the employee declared category",
      "Tests cover Category 1, 2, and 3 calculations with same annual income producing correct PCB"
    ],
    "technicalNotes": [
      "Files: fixtures/custom_field.json, services/pcb_calculator.py, report/cp39_pcb_remittance/cp39_pcb_remittance.py, report/ea_form/ea_form.py",
      "Add custom_pcb_category Select field on Employee doctype",
      "Update calculate_pcb(annual_income, resident=True, category=1, children=0, tp1_reliefs=0, annual_zakat=0)",
      "Category 1: no spouse relief; Category 2: spouse_relief=4000; Category 3: spouse_equiv=4000"
    ],
    "dependencies": ["US-004"],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-052",
    "title": "Implement TP1 Employee Relief Declaration DocType and PCB Integration",
    "priority": "critical",
    "description": "LHDN Borang TP1 allows employees to declare 20+ relief categories to reduce monthly PCB. The current PCB calculator hardcodes only personal relief (RM9,000), spouse (RM4,000), and child relief. All other declared reliefs — life insurance, medical insurance, education fees, SSPN, childcare, lifestyle, PRS, serious illness, parents medical, disability, SOCSO employee, EPF employee — are ignored, causing systematic PCB over-deduction. Regulatory basis: ITA Rules 1994 (IT(P)(E) Rules), Rule 6A.",
    "acceptanceCriteria": [
      "New DocType Employee TP1 Relief with fields: employee, tax_year, self_relief (RM9000), spouse_relief, child_relief_normal, child_relief_disabled, life_insurance (max 3000), medical_insurance (max 3000), education_fees_self (max 7000), sspn (max 8000), childcare_fees (max 3000), lifestyle_expenses (max 2500), prs_contribution (max 3000), serious_illness_expenses (max 10000), parents_medical (max 8000), disability_self, socso_employee, epf_employee (max 4000), annual_zakat",
      "One active TP1 record per employee per tax year enforced by unique constraint",
      "calculate_pcb() accepts tp1_total_reliefs parameter; subtracts from chargeable income before computing tax",
      "TP1 Print Format generates an LHDN-compatible TP1 declaration form for employee signature",
      "Tests verify each relief type reduces PCB by correct amount"
    ],
    "technicalNotes": [
      "New DocType: lhdn_payroll_integration/doctype/employee_tp1_relief/",
      "Files: employee_tp1_relief.json, employee_tp1_relief.py",
      "Apply ceiling caps for each relief per LHDN TP1 form limits",
      "get_employee_tp1_reliefs(employee, tax_year) whitelisted function sums all relief fields",
      "Update pcb_calculator.calculate_pcb() to accept tp1_total_reliefs kwarg"
    ],
    "dependencies": ["US-051"],
    "estimatedComplexity": "large",
    "passes": False
  },
  {
    "id": "US-053",
    "title": "Implement Zakat PCB Offset (Ringgit-for-Ringgit Deduction)",
    "priority": "critical",
    "description": "ITA 1967 Section 6A(3): Zakat reduces PCB payable ringgit-for-ringgit (not just from chargeable income). Net PCB = Gross PCB - (annual_zakat / 12). The app module docstring correctly documents this formula but the implementation does not apply it. Zakat has a dedicated column in LHDN CP39 CSV upload that must be populated. Failure to offset means Muslim employees are over-taxed via PCB.",
    "acceptanceCriteria": [
      "Add custom_annual_zakat (Currency) field on Employee",
      "calculate_pcb(... , annual_zakat=0) subtracts annual_zakat/12 from calculated monthly PCB; result floored at 0",
      "CP39 report CSV includes Zakat Amount column per employee row",
      "EA Form Section C5 reflects total annual Zakat",
      "Tests verify Zakat offset reduces PCB correctly; PCB never goes negative"
    ],
    "technicalNotes": [
      "Files: fixtures/custom_field.json, services/pcb_calculator.py, report/cp39_pcb_remittance/cp39_pcb_remittance.py, report/ea_form/ea_form.py",
      "Add custom_annual_zakat Currency field to Employee in custom_field.json",
      "In calculate_pcb(): monthly_zakat = annual_zakat / 12; net_pcb = max(0, monthly_pcb - monthly_zakat)",
      "CP39 query must JOIN Employee to get annual_zakat for each row"
    ],
    "dependencies": ["US-051"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-054",
    "title": "Implement CP38 Additional Deduction Fields and Payroll Integration",
    "priority": "critical",
    "description": "LHDN issues CP38 notices directing employers to deduct additional PCB above normal MTD to recover underpaid tax (ITA Section 107(1)(b)). Non-compliance makes employer personally liable for undeducted amount plus 10% surcharge (ITA Section 107(3A)). The CP38 amount is fixed per employee per month, has a notice reference number and an expiry date. No CP38 fields exist anywhere in the app.",
    "acceptanceCriteria": [
      "Add to Employee in custom_field.json: custom_cp38_amount (Currency), custom_cp38_notice_ref (Data), custom_cp38_expiry (Date)",
      "Salary Slip PCB total = regular MTD + CP38 amount when custom_cp38_expiry >= today",
      "Add CP38 Additional column to CP39 CSV report",
      "Borang E summary shows total CP38 deducted as a separate line from regular PCB",
      "Tests: CP38 added to PCB when active; ignored when expired; CP39 CSV column populated"
    ],
    "technicalNotes": [
      "Files: fixtures/custom_field.json, services/pcb_calculator.py, report/cp39_pcb_remittance/cp39_pcb_remittance.py, report/borang_e/borang_e.py",
      "Add three custom fields to Employee: cp38_amount, cp38_notice_ref, cp38_expiry",
      "PCB on salary slip: get_cp38_amount(employee) checks if expiry >= today and returns amount",
      "CP39 query: LEFT JOIN Employee to get cp38_amount for rows where active"
    ],
    "dependencies": ["US-053"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-055",
    "title": "Fix CP39 CSV Format — Add All Mandatory LHDN e-PCB Plus Columns",
    "priority": "critical",
    "description": "The LHDN e-PCB Plus portal (which replaced legacy e-PCB in 2024) requires a specific CSV upload format with mandatory columns the current report is missing. An incomplete CP39 file is rejected on upload, meaning no electronic PCB remittance can be processed. Missing columns: PCB Category (1/2/3), Zakat Amount, CP38 Additional Deduction, Employee TIN. The file header must also include the employer E-Number.",
    "acceptanceCriteria": [
      "Employer E-Number in CP39 report header (uses custom_employer_e_number from Company — see US-062)",
      "Columns in correct order: Employer E-Number, Month/Year, Employee TIN, Employee NRIC, Employee Name, PCB Category, Gross Remuneration, EPF Employee, Zakat Amount, CP38 Additional, Total PCB",
      "Currency amounts formatted to 2 decimal places",
      "CSV export uses UTF-8 encoding",
      "Tests verify all columns present and populated with correct values"
    ],
    "technicalNotes": [
      "File: lhdn_payroll_integration/report/cp39_pcb_remittance/cp39_pcb_remittance.py",
      "Add columns: pcb_category, zakat_amount, cp38_amount to the report query and output",
      "JOIN Employee table to get custom_pcb_category, custom_annual_zakat/12, custom_cp38_amount",
      "Format: amounts as '{:.2f}'.format(amount)",
      "Company E-Number: frappe.db.get_value('Company', company, 'custom_employer_e_number')"
    ],
    "dependencies": ["US-053", "US-054"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-056",
    "title": "Rebuild EA Form to Include All Mandatory LHDN Section A/B/C/D Fields",
    "priority": "critical",
    "description": "The current EA Form report produces only 6 columns. The LHDN-prescribed Borang EA format (gazetted under P.U.(A) 107/2021) requires full disclosure across Section A (employer), Section B (income breakdown — 12 line items B1-B12), Section C (statutory deductions — 5 items), and Section D (tax position). Issuing an incomplete EA Form is a criminal offence under ITA Section 120(1)(b) carrying fines up to RM20,000 or imprisonment.",
    "acceptanceCriteria": [
      "Add custom_ea_section Select field on Salary Component with options: B1 Basic Salary, B2 Overtime, B3 Commission, B4 Bonus, B5 Gratuity, B6 Allowance, B7 BIK, B8 Leave Encashment, B9 Other Gains, B10 ESOS Gain, B11 Pension",
      "EA Form report aggregates salary components by ea_section per employee per year",
      "Section A: employer name, address, custom_employer_e_number, branch code",
      "Section B: B1-B12 line items from component tagging; B12 = sum of B1-B11",
      "Section C: C1 EPF, C2 SOCSO, C3 EIS, C4 PCB total, C5 Zakat",
      "Print Format updated to match LHDN-prescribed layout with section headers",
      "Tests verify Section B totals match sum of correctly tagged components"
    ],
    "technicalNotes": [
      "Files: fixtures/custom_field.json (add custom_ea_section on Salary Component), report/ea_form/ea_form.py, print_format/ea_form/ea_form.json",
      "Add custom_ea_section Select field to Salary Component in fixtures",
      "ea_form.py: query Salary Detail joined to Salary Component, group by ea_section",
      "Pivot results so each Section B line is a column in the report",
      "Add employer fields Section A from Company doctype"
    ],
    "dependencies": ["US-062"],
    "estimatedComplexity": "large",
    "passes": False
  },
  {
    "id": "US-057",
    "title": "Update Minimum Wage Validation to RM1,700 (Feb 2025 Amendment)",
    "priority": "critical",
    "description": "The Minimum Wages Order (Amendment) 2025 increased the national minimum wage to RM1,700/month (RM8.17/hour) effective 1 February 2025 for companies with 5+ employees, and 1 August 2025 for all remaining companies. Previous rate was RM1,500/month. No minimum wage check currently exists. Paying below minimum wage is a criminal offence under Employment Act Section 99J with fines up to RM10,000 per contravention.",
    "acceptanceCriteria": [
      "New utility check_minimum_wage(monthly_salary, employment_type, worked_days, total_days) in utils/employment_compliance.py",
      "Full-time check: warn if basic_pay < 1700",
      "Part-time hourly check: warn if hourly_rate < 8.17 where hourly_rate = basic_pay / contracted_hours",
      "validate_document_for_lhdn() in validation.py calls this check on Salary Slip before_submit",
      "LHDN Payroll Compliance report adds Minimum Wage column flagging non-compliant employees",
      "Add custom_employment_type Select (Full-time/Part-time/Contract) on Employee",
      "Tests: RM1,700 passes; RM1,699 triggers warning; part-time hourly check at RM8.17"
    ],
    "technicalNotes": [
      "New file: utils/employment_compliance.py",
      "MINIMUM_WAGE_MONTHLY = 1700; MINIMUM_WAGE_HOURLY = 8.17",
      "Add custom_employment_type and custom_contracted_hours_per_month to Employee custom_field.json",
      "In validation.py validate_document_for_lhdn(doc): if doc.doctype == 'Salary Slip', call check_minimum_wage()",
      "Compliance report: add column flagging employees where any month's basic < 1700"
    ],
    "dependencies": [],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-058",
    "title": "Apply RM400 Personal and Spouse Tax Rebates in PCB Calculator",
    "priority": "critical",
    "description": "ITA 1967 Section 6A provides tax rebates that directly reduce computed tax payable: RM400 personal rebate for residents with chargeable income <= RM35,000, and RM400 spouse rebate for married individuals (Category 2/3) with same threshold. For majority of Malaysian employees (median income well below RM35,000/year), PCB is systematically overstated by up to RM800/year because calculate_pcb() does not apply these rebates.",
    "acceptanceCriteria": [
      "After computing annual tax from progressive scale: apply annual_tax = max(0, annual_tax - 400) when chargeable_income <= 35000",
      "Apply additional max(0, annual_tax - 400) when category in (2, 3) and chargeable_income <= 35000",
      "Monthly PCB = adjusted annual_tax / 12",
      "Tests: employee RM30,000/year chargeable income — verify RM800 total rebate applied (Category 2); employee RM36,000/year — verify no rebate"
    ],
    "technicalNotes": [
      "File: services/pcb_calculator.py",
      "After computing annual_tax from progressive bands, apply personal rebate then spouse rebate",
      "PERSONAL_REBATE = 400; REBATE_INCOME_LIMIT = 35000",
      "Logic: if chargeable_income <= REBATE_INCOME_LIMIT: annual_tax = max(0, annual_tax - PERSONAL_REBATE); if category in [2,3]: annual_tax = max(0, annual_tax - PERSONAL_REBATE)"
    ],
    "dependencies": ["US-051"],
    "estimatedComplexity": "small",
    "passes": False
  },
  # ─── HIGH ────────────────────────────────────────────────────────────────────
  {
    "id": "US-059",
    "title": "Implement MTD Method 2 (Year-to-Date Recalculation Formula)",
    "priority": "high",
    "description": "LHDN Computerised PCB guidelines mandate Method 2 for payroll software. Method 2 computes PCB based on actual YTD income: MTD_n = [(P-M)*R+B]/(n+1) - (X/n) where P=annualised YTD income, M=band floor, R=marginal rate, B=tax on lower bands, n=remaining months, X=PCB already deducted YTD. This is more accurate than Method 1 for employees with variable income. Regulatory basis: LHDN PCB Guidelines, Appendix D.",
    "acceptanceCriteria": [
      "Add Company-level custom_pcb_method Select (Method 1 / Method 2) with default Method 2",
      "New calculate_pcb_method2(current_month_gross, ytd_gross, ytd_pcb_deducted, tp1_reliefs, category, month_number, annual_zakat) function",
      "Salary Slip custom fields: custom_ytd_gross (Currency, read-only), custom_ytd_pcb_deducted (Currency, read-only) — auto-populated from prior submitted slips",
      "before_submit hook populates YTD fields by querying submitted slips for same employee, same year, earlier months",
      "Tests: verify Method 2 gives same annual tax as Method 1 for constant-income employee; verify Method 2 smooths PCB for variable-income employee"
    ],
    "technicalNotes": [
      "Files: services/pcb_calculator.py, fixtures/custom_field.json, hooks.py",
      "Add custom_pcb_method to Company; add custom_ytd_gross and custom_ytd_pcb_deducted to Salary Slip",
      "calculate_pcb_method2(): annualised_income = ytd_gross * (12/month_number); then apply Method 2 formula",
      "YTD query: frappe.db.sql('SELECT SUM(gross_pay), SUM(pcb_deducted) FROM tabSalary Slip WHERE employee=%s AND year=%s AND end_date<%s AND docstatus=1')"
    ],
    "dependencies": ["US-051", "US-052"],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-060",
    "title": "Implement Benefits-in-Kind (BIK) Prescribed Value Calculation Module",
    "priority": "high",
    "description": "BIK provided by employers is taxable employment income under ITA Section 13(1)(b). LHDN prescribes specific annual values for common BIK items (Public Ruling No. 3/2013 updated 2019). Company car (RM1,200-RM50,000/year by price bracket), fuel (RM300/month), driver (RM600/month), accommodation (30% of gross income), club memberships (actual fee). BIK omission understates chargeable income and PCB — LHDN audits routinely identify this.",
    "acceptanceCriteria": [
      "New DocType Employee BIK Record with fields: employee, payroll_period_year, car_bik_annual, fuel_bik_monthly, driver_bik_monthly, accommodation_bik_monthly, club_membership_annual, other_bik_annual",
      "bik_calculator.py with get_annual_car_bik(car_purchase_price) lookup table and calculate_monthly_bik_total(employee_name, year) aggregator",
      "PCB calculation adds monthly BIK value to gross income before computing annual taxable income",
      "EA Form Section B7 (BIK) populated from BIK records",
      "Tests: car price RM120,000 returns correct annual BIK; BIK total increases PCB correctly"
    ],
    "technicalNotes": [
      "New files: services/bik_calculator.py, doctype/employee_bik_record/employee_bik_record.json + .py",
      "CAR_BIK_TABLE = {50000: 1200, 75000: 2400, 100000: 3600, ...} — lookup by max price bracket",
      "FUEL_BIK_MONTHLY = 300; DRIVER_BIK_MONTHLY = 600",
      "calculate_monthly_bik_total() returns sum/12 of annual BIK items plus monthly items",
      "Integrate into pcb_calculator by adding get_bik_for_employee() call before annual_income calculation"
    ],
    "dependencies": ["US-056"],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-061",
    "title": "Implement Perquisite Exemption Thresholds on Salary Components",
    "priority": "high",
    "description": "Certain perquisites are partially exempt from tax under ITA Section 13(1)(a) and Public Ruling No. 5/2019. Key exemptions: petrol/car allowance up to RM6,000/year (business use), childcare up to RM2,400/year, mobile phone handset (1 unit, fully exempt), group insurance premiums (wholly exempt), medical/dental/optical (wholly exempt). Currently PCB calculator adds full allowance amounts to income without applying exemption ceilings, overstating taxable income.",
    "acceptanceCriteria": [
      "Add to Salary Component custom_field.json: custom_exemption_type Select (None/Transport/Childcare/Group Insurance/Medical/Mobile Phone/Other), custom_annual_exemption_ceiling (Currency, 0=unlimited)",
      "calculate_taxable_component(component_name, annual_amount) in utils/exemption_calculator.py returns taxable portion after exemption",
      "PCB annual income uses taxable portion not full amount for exempt components",
      "Transport Allowance component in fixture: custom_exemption_type=Transport, custom_annual_exemption_ceiling=6000",
      "Tests: RM8,000 transport allowance → taxable RM2,000; medical benefit → taxable RM0"
    ],
    "technicalNotes": [
      "New file: utils/exemption_calculator.py",
      "def calculate_taxable_component(component_name, annual_amount, exemption_type, ceiling): if ceiling == 0: return 0; return max(0, annual_amount - ceiling)",
      "Update pcb_calculator to call calculate_taxable_component for each earning before summing annual_income",
      "Update salary_component.json fixture to add exemption fields to Transport Allowance and Housing Allowance"
    ],
    "dependencies": ["US-004"],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-062",
    "title": "Add Borang E Mandatory Header Fields (Employer E-Number, Branch Code, Director Section)",
    "priority": "high",
    "description": "Borang E must include the employer LHDN E-Number (No. Majikan), LHDN branch (cawangan), and PCB category breakdown (number of Category 1/2/3 employees). Section B covers director remuneration separately from employee remuneration. Total CP38 deductions appear as a separate line. These fields are currently absent from both Company doctype and Borang E report. Regulatory basis: ITA 1967 Section 83, due 31 March annually.",
    "acceptanceCriteria": [
      "Add to Company custom_field.json: custom_employer_e_number (Data, LHDN employer reference), custom_lhdn_branch_code (Data, cawangan code)",
      "Borang E report header: Company name, TIN, Employer E-Number, branch code, tax year",
      "Summary section: total Category 1/2/3 employees; total regular PCB; total CP38 deductions; total Zakat",
      "Section B: separate sub-table for director remuneration vs employee remuneration",
      "Tests verify E-Number and branch code appear in report; director rows segregated"
    ],
    "technicalNotes": [
      "Files: fixtures/custom_field.json, report/borang_e/borang_e.py",
      "Add LHDN Employer Setup section to Company doctype via custom_field.json",
      "Borang E query: JOIN Employee to get custom_pcb_category; COUNT GROUP BY category",
      "Director detection: Employee.custom_worker_type == 'Director'"
    ],
    "dependencies": [],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-063",
    "title": "Implement e-CP39 API Submission to LHDN MyTax / e-PCB Plus",
    "priority": "high",
    "description": "LHDN e-PCB Plus portal accepts programmatic PCB remittance submission. Current system only generates CSV that must be manually uploaded. For employers with 50+ employees, LHDN expects electronic submission. The service must authenticate with LHDN MyTax API (separate OAuth from MyInvois), submit formatted CP39 data, and store the submission reference number. Regulatory basis: ITA Section 107(1) — PCB remitted by 15th of following month.",
    "acceptanceCriteria": [
      "New ecp39_service.py with submit_cp39_to_lhdn(company_name, month, year) function",
      "Authenticates with LHDN MyTax API using custom_mytax_client_id and custom_mytax_client_secret from Company",
      "Packages CP39 data in LHDN-required pipe-delimited format and POSTs to endpoint",
      "Stores submission reference, datetime, response status in new LHDN CP39 Submission Log DocType",
      "CP39 report page gains Submit to LHDN e-PCB Plus button (whitelisted method)",
      "Tests (mocked HTTP): successful submission stores reference; failed submission logs error"
    ],
    "technicalNotes": [
      "New files: services/ecp39_service.py, doctype/lhdn_cp39_submission_log/",
      "Add to Company: custom_mytax_client_id (Data), custom_mytax_client_secret (Password)",
      "Pipe-delimited format: employer_e_number|month_year|tin|nric|name|category|gross|epf|zakat|cp38|pcb",
      "Use existing get_access_token() pattern but for MyTax endpoint"
    ],
    "dependencies": ["US-055", "US-062"],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-064",
    "title": "Implement CP107 DocType for Foreign Employee Tax Clearance Workflow",
    "priority": "high",
    "description": "When a non-citizen employee ceases employment, employer must withhold final month remuneration and apply for Tax Clearance Letter via CP107 before releasing payment. LHDN responds within 30 working days. Employer becomes jointly liable for employee tax if final payment released without clearance (ITA Section 107A(4)). Existing CP21 DocType handles departure notification but does not implement the CP107 withholding workflow.",
    "acceptanceCriteria": [
      "New DocType LHDN CP107 with fields: employee, last_working_date, final_month_salary, withholding_amount, clearance_letter_date, clearance_reference, status (Draft/Submitted to LHDN/Clearance Received/Payment Released)",
      "Auto-created when Employee with custom_is_foreign_worker=1 status set to Left",
      "Salary Slip for final month of foreign worker with open CP107 shows warning banner",
      "HTML Print Format generates CP107 application letter",
      "Tests: auto-creation on foreign employee termination; warning on final salary slip"
    ],
    "technicalNotes": [
      "New files: doctype/lhdn_cp107/lhdn_cp107.json + lhdn_cp107.py, services/cp107_service.py",
      "hooks.py: Employee on_update → cp107_service.handle_foreign_employee_left(doc)",
      "In handle_foreign_employee_left: if custom_is_foreign_worker and status==Left, create LHDN CP107",
      "In submission_service: before enqueuing salary slip, check for open CP107 for same employee"
    ],
    "dependencies": [],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-065",
    "title": "Implement SOCSO Borang 3 — New Employee Notification to PERKESO",
    "priority": "high",
    "description": "SOCSO Act 1969 Section 19 requires employers to notify PERKESO within 30 days of new insurable employee commencement via Borang 3. Separate from LHDN CP22. Failure to register employees with SOCSO is a criminal offence under the Act. Foreign workers are ineligible for Category II (Invalidity Pension); only Category I (Employment Injury) applies to some foreign workers.",
    "acceptanceCriteria": [
      "New DocType SOCSO Borang 3 with fields: employee, date_of_employment, wage_at_commencement, socso_scheme_category (Category I / Category II)",
      "Auto-created on Employee after_insert when employment_type is Permanent or Contract and employee is Malaysian/PR",
      "Dashboard alert if not submitted within 30 days of date_of_joining",
      "PDF print format matching PERKESO Borang 3 layout",
      "Tests: auto-creation on eligible employee; alert when overdue; no auto-creation for foreign workers"
    ],
    "technicalNotes": [
      "New files: doctype/socso_borang3/socso_borang3.json + socso_borang3.py, services/socso_service.py",
      "hooks.py: Employee after_insert → socso_service.handle_new_employee_socso(doc)",
      "Eligibility: not custom_is_foreign_worker, and custom_employment_type in ['Permanent', 'Contract']",
      "Overdue check: check_overdue_socso_borang3() in daily scheduler"
    ],
    "dependencies": ["US-057"],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-066",
    "title": "Implement SOCSO Borang 4 — Employee Termination Notification to PERKESO",
    "priority": "high",
    "description": "SOCSO Act 1969 Section 19 requires employers to notify PERKESO within 30 days of employee termination via Borang 4. Failure to notify means employer may continue to be billed for SOCSO contributions for the terminated employee.",
    "acceptanceCriteria": [
      "New DocType SOCSO Borang 4 with fields: employee, date_of_termination, reason (Resignation/Termination/Retirement/Death/Contract End), last_wage",
      "Auto-created when Employee status set to Left for SOCSO-eligible employees",
      "Alert if not submitted within 30 days of termination date",
      "PDF print format matching PERKESO Borang 4 layout",
      "Tests: auto-creation on eligible employee termination; alert when overdue"
    ],
    "technicalNotes": [
      "New files: doctype/socso_borang4/socso_borang4.json + socso_borang4.py",
      "Extend socso_service.py: handle_employee_termination_socso(doc)",
      "hooks.py: Employee on_update → socso_service.handle_employee_termination_socso(doc)",
      "Trigger: doc.status == 'Left' and previous status != 'Left'"
    ],
    "dependencies": ["US-065"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-067",
    "title": "Generate EPF i-Akaun Electronic Upload File",
    "priority": "high",
    "description": "EPF i-Akaun employer portal accepts electronic file uploads for contribution submission. Current EPF Borang A is a screen report only. The i-Akaun upload format requires employer EPF registration number, employee NRIC (no hyphens), EPF member number, wages, employee and employer contribution amounts. Manual entry for large headcounts is impractical. Regulatory basis: EPF Act 1991 Section 43(3).",
    "acceptanceCriteria": [
      "Export i-Akaun File option on EPF Borang A report generates a .txt file in KWSP i-Akaun upload format",
      "File includes: custom_epf_employer_registration (add to Company), employee NRIC (no hyphens), EPF member number, wages, employee EPF, employer EPF",
      "Employer contribution uses 12%/13% differential rate per US-073",
      "Tests: file structure correct for 3-employee payroll; EPF registration number in header"
    ],
    "technicalNotes": [
      "Files: report/epf_borang_a/epf_borang_a.py (extend), fixtures/custom_field.json",
      "Add custom_epf_employer_registration (Data) to Company",
      "i-Akaun format: fixed-width or pipe-delimited, check EPF portal spec",
      "Add export button to EPF Borang A report via report.json add_total_row + custom download"
    ],
    "dependencies": ["US-073"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-068",
    "title": "Generate SOCSO and EIS e-Caruman Upload File (PERKESO ASSIST Portal)",
    "priority": "high",
    "description": "PERKESO ASSIST portal accepts combined SOCSO+EIS contribution files in a specific format. Current SOCSO Borang 8A and EIS monthly reports are screen reports only. Employers need upload-ready files. Regulatory basis: SOCSO Act 1969; EIS Act 2017.",
    "acceptanceCriteria": [
      "Export PERKESO e-Caruman File option on SOCSO and EIS reports generates upload-ready file",
      "Combined file: custom_socso_employer_number (add to Company), employee NRIC, SOCSO number, wages, SOCSO employee, SOCSO employer, EIS employee, EIS employer",
      "SOCSO uses bracketed table lookup per US-074; EIS capped at RM6,000 wage ceiling per US-075",
      "Tests: file structure correct; ceiling enforcement visible in export"
    ],
    "technicalNotes": [
      "New file: services/socso_eis_upload_service.py",
      "Add custom_socso_employer_number (Data) to Company in custom_field.json",
      "File format: check PERKESO ASSIST portal specification for exact column order and delimiters",
      "Call calculate_socso_contribution() and calculate_eis_contribution() from utils/statutory_rates.py"
    ],
    "dependencies": ["US-074", "US-075"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-069",
    "title": "Implement Ordinary Rate of Pay (ORP) Calculator and Overtime Validation",
    "priority": "high",
    "description": "Employment Act 1955 Section 60A(3) mandates OT rates: 1.5x normal day, 2.0x rest day (full day), 3.0x public holiday. These apply to employees earning <=RM4,000/month. The Ordinary Rate of Pay (ORP) = Monthly Salary / 26 (daily) or / contracted_hours (hourly). No ORP calculation or OT validation exists. OT underpayment is both an Employment Act offence and creates PCB under-deduction.",
    "acceptanceCriteria": [
      "calculate_orp(monthly_salary, contracted_hours_per_month=None) utility in utils/employment_compliance.py",
      "Add custom_day_type Select (Normal/Rest Day/Public Holiday) on Salary Component for OT components",
      "OT validation in validate_document_for_lhdn(): warn if OT component < orp * hours * statutory_multiplier for employees earning <=RM4,000/month",
      "Tests: verify 1.5x/2x/3x multiplier warnings triggered at correct salary thresholds"
    ],
    "technicalNotes": [
      "File: utils/employment_compliance.py (extend), fixtures/custom_field.json",
      "OT_MULTIPLIERS = {'Normal': 1.5, 'Rest Day': 2.0, 'Public Holiday': 3.0}",
      "ORP daily = monthly_salary / 26; ORP hourly = monthly_salary / contracted_hours",
      "Add custom_ot_hours_claimed (Float) to Salary Component for OT components to enable validation"
    ],
    "dependencies": ["US-057"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-070",
    "title": "Implement Foreign Worker Levy Tracking (FWCMS / Multi-Tier Levy Model)",
    "priority": "high",
    "description": "Foreign Workers Levy Act 2021 requires annual FWCMS levy per foreign worker (RM410-RM2,500/year depending on sector and nationality). Multi-Tier Levy Model (MTLM) effective January 2025 sets rates based on local-to-foreign worker ratio. Non-payment leads to immigration enforcement. custom_is_foreign_worker exists but is only used for e-invoice TIN substitution. Levy obligations are not tracked anywhere.",
    "acceptanceCriteria": [
      "Add to Employee: custom_fw_levy_rate (Currency, annual levy), custom_fw_levy_due_date (Date), custom_fw_levy_receipt_ref (Data)",
      "New DocType Foreign Worker Levy Payment: employee, levy_period_year, levy_amount, payment_date, receipt_number",
      "New Script Report foreign_worker_levy with Company and Year filters — lists all foreign employees with levy amounts due/paid and renewal dates",
      "Dashboard alert for foreign workers with levy overdue or due within 30 days",
      "Tests: report shows levy status; overdue detection logic correct"
    ],
    "technicalNotes": [
      "New files: doctype/foreign_worker_levy_payment/, report/foreign_worker_levy/",
      "Add three fields to Employee in custom_field.json, visible only when custom_is_foreign_worker=1",
      "Overdue check in daily scheduler: query Employee where custom_is_foreign_worker=1 and custom_fw_levy_due_date <= today+30",
      "Report: LEFT JOIN to Foreign Worker Levy Payment to show paid/unpaid status"
    ],
    "dependencies": [],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-071",
    "title": "Implement Payroll Bank Disbursement File Generator (Maybank + CIMB + DuitNow)",
    "priority": "high",
    "description": "A payroll system without bank disbursement file generation forces manual bank transfers, making the system impractical for payroll operations. Malaysian payroll files must conform to bank portal formats. The PayNet DuitNow Bulk ISO 20022 pain.001.001.03 format with SALA purpose code is the emerging standard (PayNet migration deadline November 2025). Maybank M2E and CIMB BizChannel are the two highest market share legacy formats.",
    "acceptanceCriteria": [
      "New DocType Payroll Bank Disbursement linked to Payroll Entry with bank Select (Maybank/CIMB/Public Bank/RHB/DuitNow Bulk), disbursement_date, total_amount",
      "Add Employee fields: custom_bank_name Select, custom_bank_code (8-digit PayNet code), custom_account_type (Savings/Current)",
      "generate_bank_file(payroll_entry_name, bank) service returns file bytes for download",
      "Maybank format: pipe-delimited Name|IC|Account|Amount with 5-digit org code header",
      "CIMB format: CSV with Header/Detail/Footer structure",
      "Generate Payroll Entry Generate Bank File button visible to Payroll Officer role",
      "Tests: Maybank file has correct pipe format; CIMB has correct Header/Detail/Footer"
    ],
    "technicalNotes": [
      "New files: services/bank_disbursement_service.py, doctype/payroll_bank_disbursement/",
      "Add custom_bank_name, custom_bank_code, custom_account_type to Employee in custom_field.json",
      "Maybank M2E format: pipe-delimited, ORG_CODE|PAY_DATE|NAME|NRIC|ACCOUNT|AMOUNT per line",
      "CIMB: HEADER: H|date|org_code; DETAIL: D|name|account|amount; FOOTER: T|count|total",
      "Add custom_maybank_org_code and custom_cimb_org_code to Company"
    ],
    "dependencies": [],
    "estimatedComplexity": "large",
    "passes": False
  },
  {
    "id": "US-072",
    "title": "Fix HRDF Levy Rate — 1% Mandatory for All Employers with 10+ Employees",
    "priority": "high",
    "description": "The current custom_hrdf_levy_rate field offers '0.5% for 10-49 employees, 1.0% for 50+' which is factually incorrect. HRD Corp regulations (HRD Act 2001 amended 2021) prescribe 1% for ALL employers with 10+ Malaysian employees in mandatory sectors regardless of headcount above 10. The 0.5% voluntary option only applies to companies with 5-9 employees choosing to join voluntarily. Systematic underpayment at 0.5% creates HRD Corp surcharge liability.",
    "acceptanceCriteria": [
      "Update custom_hrdf_levy_rate options to: '0.5% (Voluntary — 5-9 employees)' and '1.0% (Mandatory — 10+ employees)'",
      "Add custom_hrdf_mandatory_sector (Check) on Company — enforce 1% when checked and headcount >= 10",
      "hrdf_monthly_levy.py warns if the levy rate in use does not match mandatory rate for company headcount",
      "Tests: 10-employee company in mandatory sector uses 1%; 7-employee company allows 0.5%"
    ],
    "technicalNotes": [
      "Files: fixtures/custom_field.json, report/hrdf_monthly_levy/hrdf_monthly_levy.py",
      "Update the options string for custom_hrdf_levy_rate on Company",
      "Add custom_hrdf_mandatory_sector Check field on Company",
      "In report: compare custom_hrdf_levy_rate against expected rate based on employee count and mandatory_sector flag"
    ],
    "dependencies": [],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-073",
    "title": "Enforce EPF Employer Rate Differential (13% for Salary <=RM5,000, 12% for >RM5,000)",
    "priority": "high",
    "description": "EPF employer contribution rate: 13% for employees earning <=RM5,000/month, 12% for earnings >RM5,000/month (EPF Contribution Rate Revision 2022). Current fixture seeds a single EPF - Employer component with no rate differential logic. Employers paying 12% for employees below RM5,000 are underpaying EPF — KWSP can impose late payment dividend surcharge under EPF Act Section 45.",
    "acceptanceCriteria": [
      "New calculate_epf_employer_rate(monthly_gross) in utils/statutory_rates.py returns 0.13 if gross <= 5000, else 0.12",
      "EPF Borang A report validates employer EPF amount against correct rate per employee; flags discrepancies",
      "Salary component validation hook warns when EPF - Employer component deviates from statutory rate by >5%",
      "Tests: employee at RM5,000 → employer 13%; employee at RM5,001 → employer 12%"
    ],
    "technicalNotes": [
      "New file: utils/statutory_rates.py",
      "EPF_EMPLOYER_RATE_HIGH = 0.13 (for monthly_gross <= 5000); EPF_EMPLOYER_RATE_LOW = 0.12",
      "EPF_LOWER_SALARY_THRESHOLD = 5000",
      "Add validation in report/epf_borang_a/epf_borang_a.py: compare actual vs expected"
    ],
    "dependencies": [],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-074",
    "title": "Implement SOCSO Contribution Bracketed Table Lookup (Jadual Kadar Caruman)",
    "priority": "high",
    "description": "SOCSO contributions are NOT a straight percentage — they are fixed amounts determined by wage bracket per SOCSO First Schedule (Jadual Kadar Caruman), with 72 wage brackets from RM0 to RM6,000+. Ceiling wage is RM6,000/month (updated October 2024). Using wrong contribution amounts risks both under- and over-deduction. SOCSO Borang 8A currently passes through whatever amounts were entered without validation.",
    "acceptanceCriteria": [
      "calculate_socso_contribution(wages, scheme='both') in utils/statutory_rates.py implements the First Schedule table; returns {'employee': x, 'employer': y}",
      "Wage ceiling capped at RM6,000 (updated from RM5,000 — October 2024 amendment)",
      "SOCSO Borang 8A validation warns if reported SOCSO amounts deviate >5% from scheduled amounts",
      "Tests: wages at RM1,500, RM3,000, RM5,500, RM6,000, RM6,001 return correct scheduled amounts"
    ],
    "technicalNotes": [
      "File: utils/statutory_rates.py",
      "Embed SOCSO_TABLE as dict of wage ranges to (employee_amount, employer_amount) tuples",
      "SOCSO_WAGE_CEILING = 6000 (updated October 2024)",
      "calculate_socso_contribution(wages): wages = min(wages, SOCSO_WAGE_CEILING); find bracket; return amounts"
    ],
    "dependencies": ["US-073"],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-075",
    "title": "Enforce EIS Contribution Ceiling (RM6,000) and Age/Foreign Worker Exemptions",
    "priority": "high",
    "description": "EIS (SIP) under EIS Act 2017 Second Schedule: 0.2% employee + 0.2% employer on insured wages capped at RM6,000/month. Employees aged <18 or >=60 are exempt. Foreign workers are NOT covered. Ceiling updated October 2024 (aligned with SOCSO). These exemptions and updated ceiling are not enforced — EIS monthly report passes through whatever salary component amounts were entered.",
    "acceptanceCriteria": [
      "calculate_eis_contribution(wages, date_of_birth, is_foreign) in utils/statutory_rates.py: returns 0 if foreign or age<18 or age>=60; else min(wages, 6000) * 0.002",
      "EIS monthly report validates amounts against calculation; flags exempt employees incorrectly included or wrong ceiling",
      "Tests: foreign worker → 0; age 17 → 0; age 60 → 0; wages RM7,000 → EIS on RM6,000 only"
    ],
    "technicalNotes": [
      "File: utils/statutory_rates.py (extend from US-073/US-074)",
      "EIS_WAGE_CEILING = 6000; EIS_RATE = 0.002",
      "Age calculation: from datetime import date; age = (payroll_date - date_of_birth).days // 365",
      "report/eis_monthly/eis_monthly.py: validate each row against calculate_eis_contribution()"
    ],
    "dependencies": ["US-074"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-076",
    "title": "Implement Age-Based EPF/SOCSO/EIS Statutory Rate Transitions at Age 60",
    "priority": "high",
    "description": "At age 60, statutory contribution rules change: EPF employee rate changes to 5.5% statutory (or 0% minimum elected); EPF employer rate drops to 4%; SOCSO coverage ceases; EIS coverage ceases. The system has no age-tracking logic — employees who turn 60 mid-year will have wrong deductions until manually corrected. Regulatory basis: EPF Act 1991 Third Schedule; SOCSO Act 1969; EIS Act 2017.",
    "acceptanceCriteria": [
      "get_statutory_rates_for_employee(employee_name, payroll_date) in utils/statutory_rates.py returns correct EPF/SOCSO/EIS rates based on employee age at payroll date",
      "before_submit hook on Salary Slip warns if EPF/SOCSO/EIS component amounts do not match age-appropriate statutory rates",
      "Dashboard alert on Employee record when employee is within 3 months of turning 60",
      "Tests: employee turning 60 in payroll month — verify transition rates applied; age 59 — pre-transition rates"
    ],
    "technicalNotes": [
      "File: utils/statutory_rates.py (extend), hooks.py",
      "EPF_OVER_60_EMPLOYEE_RATE = 0.055; EPF_OVER_60_EMPLOYER_RATE = 0.04",
      "In get_statutory_rates_for_employee(): get employee.date_of_birth, calculate age, return rate dict",
      "Daily scheduler: check_approaching_age_60() — query employees where date_of_birth within 90 days of 60th birthday"
    ],
    "dependencies": ["US-075"],
    "estimatedComplexity": "small",
    "passes": False
  },
  # ─── MEDIUM ──────────────────────────────────────────────────────────────────
  {
    "id": "US-077",
    "title": "Implement TP3 Carry-Forward Declaration for New Hires (Prior Employer YTD)",
    "priority": "medium",
    "description": "When employee joins mid-year having worked for a previous employer, PCB calculation must account for income and PCB already deducted by the previous employer. Without TP3 data, new employer's calculator starts from zero, understating annualised income and under-deducting PCB. Employee submits Borang TP3 to new employer with prior income and PCB details. Regulatory basis: LHDN TP3 form.",
    "acceptanceCriteria": [
      "New DocType Employee TP3 Declaration: employee, tax_year, previous_employer_name, previous_employer_tin, prior_gross_income, prior_epf_deducted, prior_pcb_deducted, joining_month",
      "calculate_pcb()/calculate_pcb_method2() accepts tp3_prior_gross and tp3_prior_pcb; adds prior income to YTD for annualisation; subtracts prior PCB from YTD PCB deducted",
      "CP22 workflow triggers reminder to collect TP3 when joining month is not January",
      "Tests: employee joining July with RM30,000 prior income — annualised income uses combined figure"
    ],
    "technicalNotes": [
      "New files: doctype/employee_tp3_declaration/",
      "get_tp3_for_employee(employee, tax_year) returns prior_gross and prior_pcb for the year",
      "In calculate_pcb_method2(): ytd_gross += tp3_prior_gross; ytd_pcb_deducted += tp3_prior_pcb"
    ],
    "dependencies": ["US-059"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-078",
    "title": "Extend CP8D with Income Type Breakdown (Bonus, Commission, Gratuity, Other)",
    "priority": "medium",
    "description": "LHDN CP8D e-Filing specification (2024 revision) requires separate columns for income sub-categories: Total Gross Income, Gross Bonus/Commission, Gross Gratuity, Other Income, Total EPF, Total PCB. Current CP8D reports submit only three income figures. Incomplete CP8D data can trigger LHDN queries on employer submissions.",
    "acceptanceCriteria": [
      "Extend cp8d.py and cp8d_efiling.py with additional columns from EA Section tagging (US-056): bonus (B4), commissions (B3), gratuity (B5 after exemption), other (B9)",
      "CSV export format matches LHDN e-Filing CP8D 2024 column specification",
      "Tests: employee with bonus and commission components — verify amounts in correct columns"
    ],
    "technicalNotes": [
      "Files: report/cp8d/cp8d.py, report/cp8d_efiling/cp8d_efiling.py",
      "Query Salary Detail JOIN Salary Component WHERE custom_ea_section IN ('B3 Commission', 'B4 Bonus', 'B5 Gratuity', 'B9 Other Gains')",
      "Sum by ea_section per employee per year and add as separate columns"
    ],
    "dependencies": ["US-056"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-079",
    "title": "Implement CP58 Agent/Dealer Non-Employment Income Statement",
    "priority": "medium",
    "description": "ITA 1967 Section 83A(1A) and P.U.(A) 220/2019 require payers to issue Borang CP58 to agents, dealers, and distributors who receive commission/incentive payments by 31 March each year. Covers contractors and commission agents who are NOT employees. Relevant for companies with sales agent networks or referral programs.",
    "acceptanceCriteria": [
      "New Script Report cp58_agent_statement with Company and Year filters",
      "Queries Expense Claims and payment records tagged to contractors (non-employees) with payment type Commission",
      "Output per agent: Agent Name, NRIC/Registration Number, Payment Amount by Month, Total Annual",
      "Print Format matching LHDN-prescribed CP58 layout",
      "Tests: contractor with 3 commission payments — correct annual total in CP58"
    ],
    "technicalNotes": [
      "New files: report/cp58_agent_statement/cp58_agent_statement.json + .py, print_format/cp58/",
      "Add custom_payee_type Select (Employee/Contractor) and custom_payment_category (Commission/Service Fee) on Expense Claim",
      "Query: SELECT payee, nric, SUM(amount) FROM Expense Claim WHERE payee_type=Contractor GROUP BY payee"
    ],
    "dependencies": [],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-080",
    "title": "Track Maternity/Paternity Leave and Validate Maternity Pay Rate",
    "priority": "medium",
    "description": "Employment Act 1955 Section 37 (A1651): 98 consecutive days maternity leave. Section 60FA: 7 consecutive days paternity leave for up to 5 live births. Maternity allowance must be paid at Ordinary Rate of Pay. System has no mechanism to track leave taken, validate payment, or alert HR when limits are approached. Underpaying maternity allowance is an Employment Act offence.",
    "acceptanceCriteria": [
      "Add to Employee: custom_maternity_leave_taken (Int, cumulative days), custom_paternity_leave_taken (Int), custom_paternity_births_claimed (Int, max 5)",
      "validate_maternity_pay(salary_slip) checks: maternity pay >= ORP * days_taken; days_taken <= 98 per confinement",
      "Payroll Compliance report adds Leave Compliance section flagging over-entitlement or underpayment",
      "Tests: maternity pay below ORP triggers warning; days >98 triggers warning; paternity claims >5 births triggers warning"
    ],
    "technicalNotes": [
      "Files: fixtures/custom_field.json, utils/employment_compliance.py",
      "MATERNITY_LEAVE_DAYS = 98; PATERNITY_LEAVE_DAYS = 7; MAX_PATERNITY_BIRTHS = 5",
      "validate_maternity_pay(): get ORP via calculate_orp(employee.basic_salary); check maternity component >= ORP * days"
    ],
    "dependencies": ["US-069"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-081",
    "title": "Implement Working Hours Compliance Check (45-Hour Weekly Limit)",
    "priority": "medium",
    "description": "Employment Act 1955 Section 60A(1) post-2022 amendment: maximum 45 hours per week (reduced from 48). Excessive OT can cause total monthly hours to breach legal limits. Penalty for exceeding working hours: Employment Act offence. No automated check exists in the system.",
    "acceptanceCriteria": [
      "validate_weekly_hours(salary_slip) calculates total hours (contracted + OT) and warns if any implied week exceeds 45 hours",
      "Payroll Compliance report shows working hours compliance flag per employee",
      "Add custom_contracted_weekly_hours (Float, default 45) on Employee",
      "Tests: 46-hour week triggers warning; 45-hour week passes"
    ],
    "technicalNotes": [
      "File: utils/employment_compliance.py (extend)",
      "MAX_WEEKLY_HOURS = 45",
      "OT hours from Salary Detail where custom_day_type is set",
      "Total monthly contracted hours + OT hours, divided by 4.33 weeks for average weekly hours"
    ],
    "dependencies": ["US-069"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-082",
    "title": "Implement Termination and Lay-Off Benefits Calculator",
    "priority": "medium",
    "description": "Employment (Termination and Lay-Off Benefits) Regulations 1980: statutory minimum termination payment is 10 days wages per year of service for <2 years, 15 days for 2-5 years, 20 days for >5 years. Without a calculator, HR may inadvertently underpay, creating Employment Act liability. Currently CP22A DocType has no benefits calculation.",
    "acceptanceCriteria": [
      "calculate_termination_benefits(employee, termination_date) in utils/employment_compliance.py: calculates years of service, determines rate, returns statutory_minimum",
      "CP22A DocType extended with: years_of_service (Float, auto-calculated), statutory_minimum_termination_pay (Currency, auto-populated), actual_termination_pay (Currency, manual), underpayment_warning (Read Only)",
      "Tests: 1y6m → 10 days/year rate; 3 years → 15 days/year; 7 years → 20 days/year"
    ],
    "technicalNotes": [
      "Files: utils/employment_compliance.py, doctype/lhdn_cp22a/lhdn_cp22a.py",
      "TERMINATION_RATE = {2: 10, 5: 15, 999: 20} — days per year of service by service bracket",
      "years_of_service = (termination_date - employee.date_of_joining).days / 365",
      "daily_rate = employee.ctc / (12 * 26); statutory_minimum = daily_rate * rate_days * years"
    ],
    "dependencies": [],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-083",
    "title": "Implement Expatriate Gross-Up Calculator and DTA Country Table",
    "priority": "medium",
    "description": "Expatriates on tax-equalised packages require iterative gross-up to find gross salary that produces desired net after Malaysian tax. The 182-day residency rule determines resident vs non-resident treatment. Double Tax Agreement (DTA) countries (Singapore, UK, US, Australia) may provide treaty exemptions. No gross-up calculation or DTA lookup exists.",
    "acceptanceCriteria": [
      "Add to Employee: custom_dta_country Select (ISO country codes with DTA agreements), custom_is_tax_equalised (Check), custom_malaysia_presence_days (Int, YTD)",
      "calculate_gross_up(desired_net, annual_reliefs, category, max_iterations=50) iterative solver in services/expatriate_service.py",
      "DTA country list with key treaty provisions (183-day rule) stored as fixture or system setting",
      "Tests: gross-up for net RM10,000/month converges to correct gross; residency test flags non-resident at <182 days"
    ],
    "technicalNotes": [
      "New file: services/expatriate_service.py",
      "Iterative solver: start with gross = desired_net / (1 - marginal_rate); iterate until |computed_net - desired_net| < 0.01",
      "DTA_COUNTRIES dict: {country_code: {treaty_rate, days_threshold, notes}}",
      "custom_malaysia_presence_days on Employee tracks YTD days for 182-day residency rule"
    ],
    "dependencies": ["US-051"],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-084",
    "title": "Implement ESOS/Share Option Gain Calculation and EA Form B10",
    "priority": "medium",
    "description": "ITA 1967 Section 25 and Public Ruling No. 1/2021: gains from ESOS/ESPP exercise are taxable employment income in year of exercise. Gain = (Market Price on exercise date - Exercise Price) x shares exercised. Must be included in annual income for PCB and disclosed in EA Form Section B10. No ESOS module exists.",
    "acceptanceCriteria": [
      "New DocType Employee Share Option Exercise: employee, grant_date, exercise_date, exercise_price, market_price_on_exercise, shares_exercised, taxable_gain (auto-calculated)",
      "taxable_gain added to annual income for PCB in exercise month (treated as irregular payment using annualisation rule)",
      "EA Form B10 populated from share option exercise records for the year",
      "Tests: exercise 1,000 shares at RM2 exercise price, RM5 market price → taxable gain RM3,000 added to income"
    ],
    "technicalNotes": [
      "New files: doctype/employee_share_option_exercise/",
      "taxable_gain = (market_price_on_exercise - exercise_price) * shares_exercised",
      "Add to PCB calculation: get_esos_gain_for_month(employee, month, year) and treat as bonus income",
      "EA Form query: SELECT SUM(taxable_gain) FROM employee_share_option_exercise WHERE employee=%s AND YEAR(exercise_date)=%s"
    ],
    "dependencies": ["US-018"],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-085",
    "title": "Implement Approved Pension Scheme Full Retirement Gratuity Exemption",
    "priority": "medium",
    "description": "ITA 1967 Schedule 6 paragraph 30: retirement gratuity from an approved company pension scheme for employee retiring at age 55 (or compulsory retirement at 60) is FULLY exempt. Current pcb_calculator.py only implements partial RM1,000/year exemption (para 25), missing full exemption for approved scheme retirees.",
    "acceptanceCriteria": [
      "Add custom_approved_pension_scheme (Check) on Employee",
      "calculate_pcb(): if custom_approved_pension_scheme=True and age>=55 and payment tagged as gratuity → exempt 100% of gratuity",
      "EA Form B5 reflects applied exemption amount",
      "Tests: age 55 with approved scheme — full gratuity exempt; age 55 without approved scheme — RM1,000/year only"
    ],
    "technicalNotes": [
      "Files: fixtures/custom_field.json, services/pcb_calculator.py, report/ea_form/ea_form.py",
      "Add custom_approved_pension_scheme Check to Employee",
      "In calculate_pcb(): check if approved_pension_scheme and age >= 55 and gratuity_amount > 0; if so exempt_gratuity = gratuity_amount (not years * 1000)"
    ],
    "dependencies": ["US-035"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-086",
    "title": "Assess and Implement XAdES XML Digital Signature for MyInvois Self-Billed Phase 2",
    "priority": "medium",
    "description": "MyInvois e-Invoice Guidelines (LHDN SDK v3.x) state API submissions must use XAdES standard with RSA-SHA256 and certificates from MSC Trustgate or DigiCert Malaysia. Phase 2 implementors (RM25M-RM100M revenue, mandatory from January 2025) are now live. If digital signature is required for self-billed payroll e-invoices, payload_builder.py which emits no ds:Signature element will produce non-compliant XML.",
    "acceptanceCriteria": [
      "Add custom_enable_xml_signature (Check, default off) on Company and custom_digital_cert_path (Data), custom_digital_cert_password (Password)",
      "New utils/xml_signer.py implementing XAdES BeS signature using lxml with xmlsec if available",
      "payload_builder.py applies signature when custom_enable_xml_signature=1 on Company",
      "Tests: signed XML validates against XAdES schema; unsigned XML still works when flag off"
    ],
    "technicalNotes": [
      "New file: utils/xml_signer.py",
      "Try import xmlsec; if not available, log warning and skip signing",
      "XAdES BeS: C14N canonicalization + RSA-SHA256; include SignedProperties in signature",
      "Add xmlsec to requirements.txt with note that it requires libxml2 native library"
    ],
    "dependencies": [],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-087",
    "title": "Build Employee Self-Service Portal for Payslips, EA Forms, and TP1 Submission",
    "priority": "medium",
    "description": "Employment Act 1955 Section 25A requires employers to provide wage slips. A self-service portal reduces HR workload for payslip distribution and EA form issuance. Employees should be able to view payslips, download EA Forms, and submit TP1 relief declarations online without emailing HR.",
    "acceptanceCriteria": [
      "Frappe Web Page /employee-portal accessible by employees via ERPNext user account (Employee linked to User)",
      "Portal shows: all submitted Salary Slips for logged-in employee, EA Form PDF download for past years, YTD earnings summary, current TP1 declarations",
      "TP1 online submission form creates/updates Employee TP1 Relief record for current year",
      "Access restricted to employee own records via frappe.session.user validation",
      "Tests: employee A cannot access employee B records; TP1 form submission creates correct DocType record"
    ],
    "technicalNotes": [
      "New files: templates/pages/employee_portal.html, api/employee_portal.py (whitelisted methods)",
      "employee_portal.py: get_my_payslips() — frappe.db.get_list('Salary Slip', filters={'employee': get_employee_for_user()})",
      "get_employee_for_user(): frappe.db.get_value('Employee', {'user_id': frappe.session.user})",
      "Permission check in every API method: if requested employee != logged-in employee: frappe.throw('Not permitted')"
    ],
    "dependencies": ["US-052"],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-088",
    "title": "Implement PCB Change Audit Trail DocType",
    "priority": "medium",
    "description": "ITA 1967 Section 82 requires employers to maintain records for 7 years. Any change to PCB amount (manual override, TP1 relief update, CP38 addition/expiry, category change) should be logged with reason, user, and timestamp. Auditors examining PCB discrepancies need a clear change history.",
    "acceptanceCriteria": [
      "New DocType PCB Change Log: employee, payroll_period, change_type (TP1 Update/CP38 Applied/Category Change/Manual Override/Recalculation), old_pcb_amount, new_pcb_amount, reason, changed_by, change_datetime",
      "Automatically created whenever PCB component on Salary Slip changes after initial save",
      "PCB Change Log viewable from Employee record in linked list view",
      "Tests: updating TP1 relief creates log entry; CP38 expiry creates log entry"
    ],
    "technicalNotes": [
      "New files: doctype/pcb_change_log/pcb_change_log.json + pcb_change_log.py",
      "Create PCB change log in Salary Slip on_update when PCB component amount changes",
      "Compare old vs new PCB component value from doc.get_doc_before_save()"
    ],
    "dependencies": ["US-052", "US-054"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-089",
    "title": "Generate DuitNow Bulk Payroll File (ISO 20022 pain.001.001.03 with SALA Purpose Code)",
    "priority": "medium",
    "description": "PayNet hard migration deadline for ISO 20022 on H2H/SFTP gateways is November 2025. DuitNow Bulk ISO 20022 pain.001.001.03 with SALA purpose code will become the de-facto Malaysian payroll disbursement standard, replacing legacy IBG flat files. CIMB, Maybank, and RHB are upgrading gateways to XML-native by Q4 2025.",
    "acceptanceCriteria": [
      "generate_duitnow_bulk_xml(payroll_entry_name) generates ISO 20022 pain.001.001.03 XML file",
      "<PmtInf>/<PmtTpInf>/<CtgyPurp>/<Cd>SALA</Cd> mandatory purpose code for payroll",
      "<CdtTrfTxInf>/<Cdtr>/<Id> uses DuitNow ID (employee NRIC or registered mobile)",
      "<EndToEndId> unique per transaction max 35 chars (e.g. PAYROLL-{slip_name}-{YYYYMM})",
      "Tests: generated XML validates against pain.001.001.03 schema; SALA code present; EndToEndId within 35 chars"
    ],
    "technicalNotes": [
      "File: services/bank_disbursement_service.py (extend from US-071)",
      "Use lxml to build ISO 20022 XML with correct namespace: urn:iso:std:iso:20022:tech:xsd:pain.001.001.03",
      "Group payments by debtor account (company bank account) in one PmtInf block",
      "EndToEndId = f'PAYROLL-{docname[:15]}-{YYYYMM}'[:35]"
    ],
    "dependencies": ["US-071"],
    "estimatedComplexity": "medium",
    "passes": False
  },
  {
    "id": "US-090",
    "title": "Implement Foreign Worker EPF Mandatory Contribution (Effective October 2025)",
    "priority": "medium",
    "description": "EPF Board announced mandatory EPF contributions for non-citizen employees starting October 2025: employer 2% + employee 2% (initial rates). Previously foreign workers were exempt. This affects all employers with foreign workers — new salary components and updated rate calculator needed.",
    "acceptanceCriteria": [
      "calculate_epf_employer_rate(monthly_gross, is_foreign, payroll_date) returns 2% for foreign workers when payroll_date >= 2025-10-01; else existing 12%/13% for citizens/PRs",
      "Add salary components: EPF Employee (Foreign Worker) (Deduction, 2%) and EPF Employer (Foreign Worker) (Deduction, 2%) to fixtures",
      "EPF Borang A report includes foreign worker rows with correct 2% contribution rates from October 2025",
      "Tests: October 2025 foreign worker payroll → 2%/2%; September 2025 → 0%; Malaysian employee unaffected"
    ],
    "technicalNotes": [
      "File: utils/statutory_rates.py (extend calculate_epf_employer_rate)",
      "from datetime import date; FOREIGN_WORKER_EPF_START = date(2025, 10, 1)",
      "FOREIGN_WORKER_EPF_RATE = 0.02",
      "Add two new salary components to fixtures/salary_component.json"
    ],
    "dependencies": ["US-073"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-091",
    "title": "Enforce SOCSO/EIS Wage Ceiling Update to RM6,000 (October 2024 Amendment)",
    "priority": "medium",
    "description": "SOCSO and EIS insured salary ceiling updated from RM5,000 to RM6,000/month effective October 2024. Employers who have not updated continue to cap at RM5,000, causing systematic underpayment. This is a ceiling value update distinct from the contribution table enforcement in US-074/US-075.",
    "acceptanceCriteria": [
      "SOCSO_WAGE_CEILING and EIS_WAGE_CEILING constants in utils/statutory_rates.py set to 6000 with effective date comment (October 2024)",
      "SOCSO and EIS reports validate against correct ceiling",
      "Tests: employee RM5,500 — SOCSO/EIS on RM5,500 (not RM5,000); employee RM6,500 → contributions on RM6,000"
    ],
    "technicalNotes": [
      "File: utils/statutory_rates.py",
      "Ensure SOCSO_WAGE_CEILING = 6000 (already set in US-074 but confirm here)",
      "EIS_WAGE_CEILING = 6000 (already set in US-075 but add explicit comment with effective date)"
    ],
    "dependencies": ["US-074", "US-075"],
    "estimatedComplexity": "small",
    "passes": False
  },
  # ─── LOW ─────────────────────────────────────────────────────────────────────
  {
    "id": "US-092",
    "title": "Implement LHDN MyInvois Webhook Callback Handler",
    "priority": "low",
    "description": "LHDN MyInvois SDK changelog (Q1 2025) announces webhook support for document status push notifications, eliminating need for hourly polling. Webhooks would reduce unnecessary API calls and provide real-time status updates.",
    "acceptanceCriteria": [
      "New whitelisted API endpoint /api/method/lhdn_payroll_integration.api.lhdn_webhook.receive_status_callback accepting POST from LHDN",
      "Validates X-LHDN-Signature header (HMAC-SHA256 using webhook secret from Company)",
      "Updates document status immediately on receiving callback",
      "Add custom_lhdn_webhook_secret (Password) on Company",
      "Tests: valid callback → document status updated; invalid signature → 401 rejected"
    ],
    "technicalNotes": [
      "New file: api/lhdn_webhook.py",
      "import hmac, hashlib; verify: hmac.compare_digest(computed_sig, received_sig)",
      "Webhook secret: frappe.db.get_value('Company', company, 'custom_lhdn_webhook_secret')",
      "Register endpoint in hooks.py: website_route_rules"
    ],
    "dependencies": [],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-093",
    "title": "Add Sabah/Sarawak Labour Jurisdiction Flag on Employee",
    "priority": "low",
    "description": "Employees in Sabah (Labour Ordinance Cap. 67) and Sarawak (Cap. 76) may be governed by different employment ordinances with varying annual leave entitlements and overtime rules compared to Peninsular Malaysia Employment Act 1955.",
    "acceptanceCriteria": [
      "Add custom_labour_jurisdiction Select (Peninsular Malaysia/Sabah/Sarawak) on Employee — auto-set based on state code if address recorded",
      "OT and leave validation logic (US-069, US-080) applies correct jurisdiction rules based on this field",
      "Tests: Sabah employee uses Sabah Ordinance rules where they differ from EA 1955"
    ],
    "technicalNotes": [
      "File: fixtures/custom_field.json",
      "custom_labour_jurisdiction linked to custom_state_code: if state_code in [12, 15] → Sabah; [13, 16] → Sarawak",
      "SABAH_ORDINANCE_RULES dict with overrides for annual leave first year etc."
    ],
    "dependencies": ["US-069"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-094",
    "title": "Add EC Form Variant for Statutory/Government Body Employers",
    "priority": "low",
    "description": "ITA 1967 Section 83A — Borang EC is the government/statutory body equivalent of EA Form. If any Prisma clients are statutory bodies, GLCs, or government-linked companies, they must issue EC Forms instead of EA Forms. EC Form has the same structure but different headers and field labels.",
    "acceptanceCriteria": [
      "New Script Report ec_form cloning EA Form structure with EC-specific field labels and layout",
      "Company-level custom_is_statutory_employer (Check) — switches default to EC Form generation",
      "Tests: statutory employer generates EC Form headers; non-statutory employer uses EA Form"
    ],
    "technicalNotes": [
      "New files: report/ec_form/ec_form.json + ec_form.py",
      "EC Form: reuse same ea_form.py logic but substitute EC-specific header text",
      "Add custom_is_statutory_employer Check to Company in custom_field.json"
    ],
    "dependencies": ["US-056"],
    "estimatedComplexity": "small",
    "passes": False
  },
  {
    "id": "US-095",
    "title": "Implement Multi-Tier Levy Model (MTLM) Rate Calculation for Foreign Workers",
    "priority": "low",
    "description": "Multi-Tier Levy Model (MTLM) effective January 2025 sets foreign worker levy rates based on employer dependency ratio (local:foreign worker ratio). Higher dependency = higher levy rate. Tier 1 (low dependency): RM410/year; Tier 2 (medium): RM1,230/year; Tier 3 (high): RM2,500/year. Extends the base foreign worker levy tracking in US-070.",
    "acceptanceCriteria": [
      "calculate_fw_levy_tier(local_headcount, foreign_headcount, sector) utility returning levy rate per worker",
      "Foreign Worker Levy report shows tier calculation and total annual levy liability",
      "Tests: dependency ratio above Tier 3 threshold returns highest rate"
    ],
    "technicalNotes": [
      "File: doctype/foreign_worker_levy_payment/ (extend from US-070)",
      "MTLM_TIERS = {'Tier 1': (0.0, 0.15, 410), 'Tier 2': (0.15, 0.30, 1230), 'Tier 3': (0.30, 1.0, 2500)}",
      "dependency_ratio = foreign_headcount / (local_headcount + foreign_headcount)",
      "Add to Company: custom_local_employee_count and custom_foreign_employee_count for MTLM calculation"
    ],
    "dependencies": ["US-070"],
    "estimatedComplexity": "small",
    "passes": False
  }
]

def main():
    data = json.loads(PRD_PATH.read_text(encoding="utf-8"))
    existing_ids = {s["id"] for s in data["userStories"]}

    added = 0
    for story in NEW_STORIES:
        if story["id"] not in existing_ids:
            data["userStories"].append(story)
            added += 1
            print(f"  + {story['id']}: {story['title']}")
        else:
            print(f"  ~ {story['id']}: already exists, skipped")

    # Update metadata
    data["overview"] = (
        "Gap closure PRD v3.0 for lhdn_payroll_integration Frappe app. "
        "US-001 to US-050 (v2.0) are complete. "
        "US-051 to US-095 (v3.0) add full LHDN compliance: PCB categories, TP1/TP3 reliefs, "
        "Zakat/CP38 offsets, complete EA Form, RM1,700 minimum wage, BIK module, "
        "SOCSO/EPF/EIS rate enforcement, bank disbursement files, statutory forms, "
        "and Employment Act compliance checks."
    )
    data["goals"] = [
        "Implement correct PCB Category (1/2/3), TP1 reliefs, Zakat offset, CP38 additional deduction",
        "Fix CP39 CSV format to match LHDN e-PCB Plus upload specification with all mandatory columns",
        "Rebuild EA Form with all mandatory Section A/B/C/D fields per P.U.(A) 107/2021",
        "Update minimum wage validation to RM1,700 (Feb 2025 amendment)",
        "Implement SOCSO bracketed table, EPF rate differential, EIS ceiling enforcement",
        "Add bank disbursement files: Maybank IBG, CIMB IBG, DuitNow ISO 20022 pain.001.001.03",
        "Implement SOCSO Borang 3/4, EPF i-Akaun export, PERKESO e-Caruman export",
        "Add foreign worker levy tracking, CP107 tax clearance, age-based statutory transitions"
    ]

    PRD_PATH.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone — {added} new stories added. Total: {len(data['userStories'])} stories.")

if __name__ == "__main__":
    main()
