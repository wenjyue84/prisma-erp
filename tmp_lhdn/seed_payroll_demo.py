"""LHDN Payroll Demo Data Seed Script

Idempotent: skip any record that already exists.
Defines a run() function at module level for bench --site frontend execute.
"""
import frappe


def _has_field(doctype, fieldname):
    """Check if a custom or standard field exists on a doctype."""
    meta = frappe.get_meta(doctype)
    return meta.get_field(fieldname) is not None


def _set_if_exists(doc, fieldname, value):
    """Set a field only if it exists on the document's doctype."""
    if _has_field(doc.doctype, fieldname):
        setattr(doc, fieldname, value)


COMPANY = "Arising Packaging"
CURRENCY = "MYR"

RESULTS = {
    "created": [],
    "skipped": [],
    "errors": [],
}


def _create_msic_code():
    """Create MSIC code 62010 (Computer programming activities) if it doesn't exist."""
    if frappe.db.exists("LHDN MSIC Code", "62010"):
        RESULTS["skipped"].append("LHDN MSIC Code: 62010")
        return "62010"

    msic = frappe.new_doc("LHDN MSIC Code")
    msic.name = "62010"
    msic.code = "62010"
    msic.description = "Computer programming activities"
    msic.sector = "Technology"
    msic.insert(ignore_permissions=True)
    frappe.db.commit()
    RESULTS["created"].append("LHDN MSIC Code: 62010 (Computer programming activities)")
    return "62010"


def _create_department():
    """Create 'Operations' department under Arising Packaging."""
    dept_name = "Operations - AP"
    if frappe.db.exists("Department", dept_name):
        RESULTS["skipped"].append(f"Department: {dept_name}")
        return dept_name

    dept = frappe.new_doc("Department")
    dept.department_name = "Operations"
    dept.company = COMPANY
    dept.is_group = 0
    dept.insert(ignore_permissions=True)
    frappe.db.commit()
    RESULTS["created"].append(f"Department: {dept.name}")
    return dept.name


def _create_employee_ahmad(department, msic_code):
    """Create Ahmad Farid bin Malik — Employee type."""
    name = "Ahmad Farid bin Malik"
    if frappe.db.exists("Employee", {"employee_name": name}):
        existing = frappe.db.get_value("Employee", {"employee_name": name}, "name")
        RESULTS["skipped"].append(f"Employee: {existing} ({name})")
        return existing

    emp = frappe.new_doc("Employee")
    emp.employee_name = name
    emp.first_name = "Ahmad Farid"
    emp.last_name = "bin Malik"
    emp.gender = "Male"
    emp.date_of_birth = "1987-01-01"
    emp.company = COMPANY
    emp.department = department
    emp.date_of_joining = "2023-01-01"
    emp.status = "Active"

    # LHDN custom fields
    _set_if_exists(emp, "custom_worker_type", "Employee")
    _set_if_exists(emp, "custom_requires_self_billed_invoice", 0)
    _set_if_exists(emp, "custom_lhdn_tin", "IG87654321001")
    _set_if_exists(emp, "custom_id_type", "NRIC")
    _set_if_exists(emp, "custom_id_value", "870101145678")
    _set_if_exists(emp, "custom_msic_code", msic_code)
    _set_if_exists(emp, "custom_is_foreign_worker", 0)
    _set_if_exists(emp, "custom_bank_account_number", "1234567890")
    _set_if_exists(emp, "custom_state_code", "01 : Johor")

    emp.insert(ignore_permissions=True)
    frappe.db.commit()
    RESULTS["created"].append(f"Employee: {emp.name} ({name}) — Worker Type: Employee")
    return emp.name


def _create_employee_raj(department, msic_code):
    """Create Raj Kumar a/l Selvam — Contractor type."""
    name = "Raj Kumar a/l Selvam"
    if frappe.db.exists("Employee", {"employee_name": name}):
        existing = frappe.db.get_value("Employee", {"employee_name": name}, "name")
        RESULTS["skipped"].append(f"Employee: {existing} ({name})")
        return existing

    emp = frappe.new_doc("Employee")
    emp.employee_name = name
    emp.first_name = "Raj Kumar"
    emp.last_name = "a/l Selvam"
    emp.gender = "Male"
    emp.date_of_birth = "1998-02-02"
    emp.company = COMPANY
    emp.department = department
    emp.date_of_joining = "2023-06-01"
    emp.status = "Active"

    # LHDN custom fields — Contractor is in-scope for self-billed e-Invoice
    _set_if_exists(emp, "custom_worker_type", "Contractor")
    _set_if_exists(emp, "custom_requires_self_billed_invoice", 1)
    _set_if_exists(emp, "custom_lhdn_tin", "IG98765432001")
    _set_if_exists(emp, "custom_id_type", "NRIC")
    _set_if_exists(emp, "custom_id_value", "980202145678")
    _set_if_exists(emp, "custom_msic_code", msic_code)
    _set_if_exists(emp, "custom_is_foreign_worker", 0)
    _set_if_exists(emp, "custom_state_code", "01 : Johor")

    emp.insert(ignore_permissions=True)
    frappe.db.commit()
    RESULTS["created"].append(f"Employee: {emp.name} ({name}) — Worker Type: Contractor")
    return emp.name


def _create_salary_component(name, component_type, abbr, classification_code=None, exclude_from_invoice=0):
    """Create a Salary Component if it doesn't already exist."""
    if frappe.db.exists("Salary Component", name):
        RESULTS["skipped"].append(f"Salary Component: {name}")
        return name

    sc = frappe.new_doc("Salary Component")
    sc.salary_component = name
    sc.salary_component_abbr = abbr
    sc.type = component_type  # "Earning" or "Deduction"
    sc.is_tax_applicable = 0
    sc.is_flexible_benefit = 0

    # LHDN custom fields
    if classification_code and _has_field("Salary Component", "custom_lhdn_classification_code"):
        sc.custom_lhdn_classification_code = classification_code

    if _has_field("Salary Component", "custom_lhdn_exclude_from_invoice"):
        sc.custom_lhdn_exclude_from_invoice = exclude_from_invoice

    sc.insert(ignore_permissions=True)
    frappe.db.commit()
    RESULTS["created"].append(
        f"Salary Component: {name} (type={component_type}, exclude_from_invoice={exclude_from_invoice})"
    )
    return name


def _create_all_salary_components():
    """Create all required salary components."""
    components = {}

    # Earnings
    components["basic"] = _create_salary_component(
        "Basic Salary", "Earning", "BS",
        classification_code=None,
        exclude_from_invoice=0,
    )

    # Deductions — PCB (Monthly Tax Deduction)
    # payload_builder detects PCB by name from PCB_COMPONENT_NAMES frozenset
    components["pcb"] = _create_salary_component(
        "Monthly Tax Deduction", "Deduction", "PCB",
        classification_code=None,
        exclude_from_invoice=0,
    )

    # Deductions — Employee statutory (part of employment cost, not excluded)
    components["epf_ee"] = _create_salary_component(
        "EPF Employee", "Deduction", "EPF-EE",
        exclude_from_invoice=0,
    )

    components["socso_ee"] = _create_salary_component(
        "SOCSO Employee", "Deduction", "SOCSO-EE",
        exclude_from_invoice=0,
    )

    # Deductions — Employer statutory contributions.
    # Names match EMPLOYER_STATUTORY_COMPONENTS frozenset in payload_builder.py:
    # 'EPF - Employer', 'SOCSO - Employer' — must use these exact names.
    # Also set custom_lhdn_exclude_from_invoice=1 as belt-and-suspenders.
    components["epf_er"] = _create_salary_component(
        "EPF - Employer", "Deduction", "EPF-ER",
        exclude_from_invoice=1,
    )

    components["socso_er"] = _create_salary_component(
        "SOCSO - Employer", "Deduction", "SOCSO-ER",
        exclude_from_invoice=1,
    )

    return components


def _create_salary_structure(components):
    """Create 'LHDN Demo Structure' salary structure."""
    struct_name = "LHDN Demo Structure"
    if frappe.db.exists("Salary Structure", struct_name):
        RESULTS["skipped"].append(f"Salary Structure: {struct_name}")
        return struct_name

    ss = frappe.new_doc("Salary Structure")
    ss.name = struct_name
    ss.company = COMPANY
    ss.currency = CURRENCY
    ss.is_active = "Yes"
    ss.payroll_frequency = "Monthly"

    # Earnings
    ss.append("earnings", {
        "salary_component": components["basic"],
        "abbr": "BS",
        "amount": 5000,
        "formula": "",
    })

    # Deductions
    ss.append("deductions", {
        "salary_component": components["pcb"],
        "abbr": "PCB",
        "amount": 250,
        "formula": "",
    })
    ss.append("deductions", {
        "salary_component": components["epf_ee"],
        "abbr": "EPF-EE",
        "amount": 550,
        "formula": "",
    })
    ss.append("deductions", {
        "salary_component": components["socso_ee"],
        "abbr": "SOCSO-EE",
        "amount": 25,
        "formula": "",
    })
    ss.append("deductions", {
        "salary_component": components["epf_er"],
        "abbr": "EPF-ER",
        "amount": 550,
        "formula": "",
    })
    ss.append("deductions", {
        "salary_component": components["socso_er"],
        "abbr": "SOCSO-ER",
        "amount": 25,
        "formula": "",
    })

    ss.insert(ignore_permissions=True)
    frappe.db.commit()
    RESULTS["created"].append(f"Salary Structure: {struct_name}")
    return struct_name


def _create_salary_structure_assignment(employee_id, struct_name):
    """Assign salary structure to Ahmad Farid with base = 5000 MYR."""
    existing = frappe.db.exists("Salary Structure Assignment", {
        "employee": employee_id,
        "salary_structure": struct_name,
    })
    if existing:
        RESULTS["skipped"].append(f"Salary Structure Assignment: {employee_id} -> {struct_name}")
        return existing

    ssa = frappe.new_doc("Salary Structure Assignment")
    ssa.employee = employee_id
    ssa.salary_structure = struct_name
    ssa.company = COMPANY
    ssa.from_date = "2025-01-01"
    ssa.base = 5000
    ssa.currency = CURRENCY
    ssa.docstatus = 1  # Must be submitted to be effective

    ssa.insert(ignore_permissions=True)
    ssa.submit()
    frappe.db.commit()
    RESULTS["created"].append(f"Salary Structure Assignment: {ssa.name} ({employee_id} @ 5000 MYR/mo)")
    return ssa.name


def _create_holiday_list():
    """Create a 2026 holiday list and assign it via Holiday List Assignment (HRMS v16 way)."""
    hl_name = "LHDN Demo Holidays 2026"

    if not frappe.db.exists("Holiday List", hl_name):
        hl = frappe.new_doc("Holiday List")
        hl.holiday_list_name = hl_name
        hl.from_date = "2026-01-01"
        hl.to_date = "2026-12-31"
        # Malaysian public holidays 2026
        for hday in [
            ("2026-01-01", "New Year's Day"),
            ("2026-02-01", "Federal Territory Day"),
            ("2026-05-01", "Labour Day"),
            ("2026-08-31", "National Day"),
            ("2026-09-16", "Malaysia Day"),
            ("2026-12-25", "Christmas Day"),
        ]:
            hl.append("holidays", {"holiday_date": hday[0], "description": hday[1]})
        hl.total_holidays = len(hl.holidays)
        hl.insert(ignore_permissions=True)
        frappe.db.commit()
        RESULTS["created"].append(f"Holiday List: {hl_name}")
    else:
        RESULTS["skipped"].append(f"Holiday List: {hl_name}")

    # Create Holiday List Assignment for the company (HRMS v16 uses HLA, not Company.default_holiday_list)
    hla_exists = frappe.db.exists("Holiday List Assignment", {
        "assigned_to": COMPANY,
        "holiday_list": hl_name,
        "docstatus": 1,
    })
    if not hla_exists:
        hla = frappe.new_doc("Holiday List Assignment")
        hla.applicable_for = "Company"
        hla.assigned_to = COMPANY
        hla.holiday_list = hl_name
        hla.from_date = "2026-01-01"
        hla.insert(ignore_permissions=True)
        hla.submit()
        frappe.db.commit()
        RESULTS["created"].append(f"Holiday List Assignment: {COMPANY} -> {hl_name} from 2026-01-01")
    else:
        RESULTS["skipped"].append(f"Holiday List Assignment: {COMPANY} -> {hl_name}")

    return hl_name


def _create_expense_type():
    """Create 'Travel' expense claim type if it doesn't exist."""
    if frappe.db.exists("Expense Claim Type", "Travel"):
        # Update LHDN classification if field exists and not already set
        if _has_field("Expense Claim Type", "custom_lhdn_classification_code"):
            existing = frappe.get_doc("Expense Claim Type", "Travel")
            if not getattr(existing, "custom_lhdn_classification_code", None):
                existing.custom_lhdn_classification_code = "027 : Reimbursement"
                existing.save(ignore_permissions=True)
                frappe.db.commit()
                RESULTS["created"].append("Expense Claim Type: Travel (updated LHDN classification=027)")
                return "Travel"
        RESULTS["skipped"].append("Expense Claim Type: Travel")
        return "Travel"

    ect = frappe.new_doc("Expense Claim Type")
    ect.expense_type = "Travel"
    ect.description = "Travel and transport expenses"
    if _has_field("Expense Claim Type", "custom_lhdn_classification_code"):
        ect.custom_lhdn_classification_code = "027 : Reimbursement"
    ect.insert(ignore_permissions=True)
    frappe.db.commit()
    RESULTS["created"].append("Expense Claim Type: Travel (LHDN classification=027)")
    return "Travel"


def _create_salary_slip(employee_id, struct_name, components):
    """Create one DRAFT Salary Slip for Ahmad Farid for 2026-01."""
    existing = frappe.db.get_value("Salary Slip", {
        "employee": employee_id,
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "docstatus": ["!=", 2],
    }, "name")
    if existing:
        RESULTS["skipped"].append(f"Salary Slip: {existing} (Ahmad Farid, 2026-01)")
        return existing

    slip = frappe.new_doc("Salary Slip")
    slip.employee = employee_id
    slip.company = COMPANY
    slip.salary_structure = struct_name
    slip.currency = CURRENCY
    slip.exchange_rate = 1
    slip.start_date = "2026-01-01"
    slip.end_date = "2026-01-31"
    slip.posting_date = "2026-01-31"
    slip.payroll_frequency = "Monthly"

    # Earnings
    slip.append("earnings", {
        "salary_component": components["basic"],
        "abbr": "BS",
        "amount": 5000,
    })

    # Deductions (employee-side only — employer contributions are not on individual slip)
    slip.append("deductions", {
        "salary_component": components["pcb"],
        "abbr": "PCB",
        "amount": 250,
    })
    slip.append("deductions", {
        "salary_component": components["epf_ee"],
        "abbr": "EPF-EE",
        "amount": 550,
    })
    slip.append("deductions", {
        "salary_component": components["socso_ee"],
        "abbr": "SOCSO-EE",
        "amount": 25,
    })

    slip.gross_pay = 5000
    slip.total_deduction = 825   # 250 + 550 + 25
    slip.net_pay = 4175          # 5000 - 825

    slip.insert(ignore_permissions=True)
    frappe.db.commit()
    RESULTS["created"].append(
        f"Salary Slip: {slip.name} (Ahmad Farid, 2026-01, gross=5000, net=4175 MYR) — DRAFT"
    )
    return slip.name


def _create_expense_claim(employee_id, expense_type):
    """Create one DRAFT Expense Claim for Ahmad Farid."""
    existing = frappe.db.get_value("Expense Claim", {
        "employee": employee_id,
        "posting_date": "2026-01-15",
        "docstatus": ["!=", 2],
    }, "name")
    if existing:
        RESULTS["skipped"].append(f"Expense Claim: {existing} (Ahmad Farid, 2026-01-15)")
        return existing

    # Resolve payable account
    payable_account = frappe.db.get_value(
        "Account",
        {"account_type": "Payable", "company": COMPANY, "is_group": 0},
        "name",
    )

    # Resolve expense account — try Expense Account type first, then Indirect Expenses
    expense_account = frappe.db.get_value(
        "Account",
        {"account_type": "Expense Account", "company": COMPANY, "is_group": 0},
        "name",
    )
    if not expense_account:
        expense_account = frappe.db.get_value(
            "Account",
            {"account_type": "Indirect Expense", "company": COMPANY, "is_group": 0},
            "name",
        )
    if not expense_account:
        # Fall back to any account with Expenses in the name
        all_accounts = frappe.get_all(
            "Account",
            filters={"company": COMPANY, "is_group": 0},
            fields=["name", "account_type"],
        )
        for acc in all_accounts:
            if "expense" in acc.name.lower():
                expense_account = acc.name
                break

    ec = frappe.new_doc("Expense Claim")
    ec.employee = employee_id
    ec.company = COMPANY
    ec.posting_date = "2026-01-15"
    ec.expense_approver = "Administrator"
    ec.title = "Client visit KL - Jan 2026"
    ec.currency = CURRENCY
    ec.exchange_rate = 1

    if payable_account:
        ec.payable_account = payable_account

    expense_row = {
        "expense_date": "2026-01-15",
        "expense_type": expense_type,
        "description": "Client visit KL",
        "amount": 500,
        "sanctioned_amount": 500,
    }
    if expense_account:
        expense_row["default_account"] = expense_account

    ec.append("expenses", expense_row)
    ec.total_claimed_amount = 500
    ec.total_sanctioned_amount = 500

    # LHDN custom fields on Expense Claim
    # Ahmad Farid is an Employee (not Contractor), so per exemption_filter.py
    # he would be exempt from self-billed e-Invoice. Set accordingly.
    _set_if_exists(ec, "custom_expense_category", "Employee Receipt Provided")

    ec.insert(ignore_permissions=True)
    frappe.db.commit()
    RESULTS["created"].append(
        f"Expense Claim: {ec.name} (Ahmad Farid, 2026-01-15, 500 MYR, Travel) — DRAFT"
    )
    return ec.name


def run():
    """Main entry point — called via bench --site frontend execute."""
    print("\n" + "=" * 60)
    print("LHDN Payroll Demo Data Seed")
    print("=" * 60)

    # 0. MSIC Code
    print("\n[0/8] Creating LHDN MSIC Code 62010...")
    msic_code = _create_msic_code()
    print(f"  -> {msic_code}")

    # 1. Department
    print("\n[1/8] Creating Department...")
    department = _create_department()
    print(f"  -> {department}")

    # 2. Employee Ahmad Farid (regular Employee)
    print("\n[2/8] Creating Employee Ahmad Farid bin Malik (Employee)...")
    ahmad_id = _create_employee_ahmad(department, msic_code)
    print(f"  -> {ahmad_id}")

    # 3. Employee Raj Kumar (Contractor)
    print("\n[3/8] Creating Employee Raj Kumar a/l Selvam (Contractor)...")
    raj_id = _create_employee_raj(department, msic_code)
    print(f"  -> {raj_id}")

    # 4. Salary Components
    print("\n[4/8] Creating Salary Components...")
    components = _create_all_salary_components()
    for k, v in components.items():
        print(f"  -> {k}: {v}")

    # 5. Salary Structure
    print("\n[5/8] Creating Salary Structure...")
    struct_name = _create_salary_structure(components)
    print(f"  -> {struct_name}")

    # 6. Salary Structure Assignment
    print("\n[6/8] Creating Salary Structure Assignment (Ahmad Farid)...")
    ssa_name = _create_salary_structure_assignment(ahmad_id, struct_name)
    print(f"  -> {ssa_name}")

    # 7. Holiday List (needed for Salary Slip validation)
    print("\n[7/8] Creating Holiday List 2026 and assigning to company...")
    hl_name = _create_holiday_list()
    print(f"  -> {hl_name}")

    # 7b. Expense Claim Type
    print("\n[7b/8] Creating Expense Claim Type: Travel...")
    expense_type = _create_expense_type()
    print(f"  -> {expense_type}")

    # 8a. Salary Slip (draft)
    print("\n[8a/8] Creating Salary Slip (DRAFT) for Ahmad Farid, 2026-01...")
    slip_name = _create_salary_slip(ahmad_id, struct_name, components)
    print(f"  -> {slip_name}")

    # 8b. Expense Claim (draft)
    print("\n[8b/8] Creating Expense Claim (DRAFT) for Ahmad Farid, 2026-01-15...")
    ec_name = _create_expense_claim(ahmad_id, expense_type)
    print(f"  -> {ec_name}")

    # Summary
    print("\n" + "=" * 60)
    print("SEED COMPLETE — SUMMARY")
    print("=" * 60)

    if RESULTS["created"]:
        print(f"\n  CREATED ({len(RESULTS['created'])}):")
        for r in RESULTS["created"]:
            print(f"    + {r}")

    if RESULTS["skipped"]:
        print(f"\n  SKIPPED — already exists ({len(RESULTS['skipped'])}):")
        for r in RESULTS["skipped"]:
            print(f"    ~ {r}")

    if RESULTS["errors"]:
        print(f"\n  ERRORS ({len(RESULTS['errors'])}):")
        for r in RESULTS["errors"]:
            print(f"    ! {r}")

    print(f"\n  Ahmad Farid (Employee) ID  : {ahmad_id}")
    print(f"  Raj Kumar   (Contractor) ID: {raj_id}")
    print(f"  Salary Slip (DRAFT)        : {slip_name}")
    print(f"  Expense Claim (DRAFT)      : {ec_name}")
    print()
    print("  IMPORTANT NOTES:")
    print("  - Ahmad Farid = Worker Type 'Employee' => always EXEMPT from LHDN")
    print("    per exemption_filter.py. His Salary Slip will get custom_lhdn_status=Exempt.")
    print("  - Raj Kumar = Worker Type 'Contractor' + custom_requires_self_billed_invoice=1")
    print("    => IN SCOPE for LHDN self-billed e-Invoice on submit.")
    print("  - Submit Ahmad's Salary Slip to see the LHDN hook fire (status=Exempt).")
    print("  - Create a Salary Slip for Raj Kumar and submit to trigger UBL XML generation.")
    print("=" * 60 + "\n")

    return {
        "created": RESULTS["created"],
        "skipped": RESULTS["skipped"],
        "errors": RESULTS["errors"],
        "ahmad_employee_id": ahmad_id,
        "raj_employee_id": raj_id,
        "salary_slip": slip_name,
        "expense_claim": ec_name,
    }
