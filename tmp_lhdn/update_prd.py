"""Add new user stories to prd.json — run with: python tmp_lhdn/update_prd.py"""
import json
import sys
import os

prd_path = os.path.join(os.path.dirname(__file__), '..', 'prd.json')

with open(prd_path, 'r', encoding='utf-8') as f:
    prd = json.load(f)

existing_ids = {s['id'] for s in prd['userStories']}
print(f"Current story count: {len(prd['userStories'])}")

new_stories = [
    {
        "id": "US-039",
        "title": "Sync comprehensive salary components as lhdn_payroll_integration fixtures",
        "priority": 68,
        "description": (
            "The EC2 instance has 10 salary components (including EPF Employee, EPF Employer, "
            "SOCSO Employee, SOCSO Employer, Monthly Tax Deduction, Basic Salary) while a fresh "
            "local install only has 4 ERPNext defaults. Add all LHDN-relevant salary components "
            "as fixtures in the lhdn_payroll_integration app so that any fresh install automatically "
            "gets the complete set. Mark employer components with custom_lhdn_exclude_from_invoice=1 "
            "and PCB component with custom_is_pcb_component=1 in the fixture JSON. Merge to main."
        ),
        "acceptanceCriteria": [
            "lhdn_payroll_integration/fixtures/salary_component.json exists with all 6 LHDN salary components",
            "Components: Basic Salary (Earning), Monthly Tax Deduction (Deduction), EPF Employee (Deduction), SOCSO Employee (Deduction), EPF - Employer (Deduction, exclude_from_invoice=1), SOCSO - Employer (Deduction, exclude_from_invoice=1)",
            "hooks.py fixtures list includes 'Salary Component'",
            "Running bench --site frontend migrate or install-app on a fresh site creates these components",
            "Local and EC2 instances both show 10+ salary components after fixture import",
            "seed_payroll_demo.py is also run on localhost to create demo employees and salary slips",
            "Changes committed and merged to main branch"
        ],
        "technicalNotes": [
            "Export from EC2: bench --site frontend export-fixtures --app lhdn_payroll_integration",
            "Or manually create fixtures/salary_component.json with the 6 component definitions",
            "Add 'Salary Component' to fixtures list in hooks.py",
            "Run: docker cp tmp_lhdn/seed_payroll_demo.py prisma-erp-backend-1:/home/frappe/frappe-bench/apps/frappe/frappe/seed_payroll_demo.py",
            "Run: docker exec prisma-erp-backend-1 bash -c 'bench --site frontend execute frappe.seed_payroll_demo.run'"
        ],
        "dependencies": ["US-034"],
        "estimatedComplexity": "small",
        "passes": False
    },
    {
        "id": "UT-035",
        "title": "Write failing tests for LHDN Payroll Compliance report",
        "priority": 69,
        "description": (
            "Write a test that calls the LHDN Payroll Compliance report get_columns() and get_data() "
            "functions directly and asserts: correct column names (Document Type, Document Name, "
            "Employee, Period, Amount, LHDN Status, UUID, Submitted At, Validated At), "
            "get_data() returns rows for submitted Salary Slips with expected lhdn_status values."
        ),
        "acceptanceCriteria": [
            "Test file exists at lhdn_payroll_integration/tests/test_compliance_report.py",
            "Tests fail before the report module is created",
            "Tests assert get_columns() returns at least 8 columns with correct fieldnames",
            "Tests assert get_data() returns rows matching submitted Salary Slips"
        ],
        "technicalNotes": [
            "Report path: lhdn_payroll_integration/lhdn_payroll_integration/report/lhdn_payroll_compliance/",
            "Files needed: __init__.py, lhdn_payroll_compliance.json, lhdn_payroll_compliance.py",
            "Report type: Script Report (not Tabular — gives more control)"
        ],
        "dependencies": ["US-039"],
        "estimatedComplexity": "small",
        "passes": False
    },
    {
        "id": "US-035",
        "title": "Create LHDN Payroll Compliance script report",
        "priority": 70,
        "description": (
            "Create a Frappe Script Report named 'LHDN Payroll Compliance' that lists all Salary Slips "
            "and Expense Claims with their LHDN submission status. Columns: Document Type, Document Name, "
            "Employee, Period, Amount (MYR), LHDN Status, UUID, Submitted At, Validated At. "
            "Filters: from_date, to_date, company, employee, lhdn_status. "
            "LHDN Status column uses indicator colors: green=Valid, orange=Pending, red=Invalid, grey=Exempt."
        ),
        "acceptanceCriteria": [
            "Report appears under HR > Reports > LHDN Payroll Compliance",
            "All 9 columns present with correct fieldnames and labels",
            "Filters: from_date, to_date, company (Link), employee (Link), lhdn_status (Select)",
            "Data includes both Salary Slip and Expense Claim rows (UNION query)",
            "LHDN Status uses frappe indicator colors via the indicator column",
            "UT-035 tests pass"
        ],
        "technicalNotes": [
            "File: lhdn_payroll_integration/lhdn_payroll_integration/report/lhdn_payroll_compliance/lhdn_payroll_compliance.py",
            "JSON: lhdn_payroll_compliance.json with report_type: Script Report",
            "Use frappe.db.sql() UNION on tabSalary Slip and tabExpense Claim",
            "Add report to lhdn_payroll_integration/lhdn_payroll_integration/module.txt if not auto-discovered"
        ],
        "dependencies": ["UT-035"],
        "estimatedComplexity": "medium",
        "passes": False
    },
    {
        "id": "UT-036",
        "title": "Write failing tests for Re-submit to LHDN server action",
        "priority": 71,
        "description": (
            "Write tests for the resubmit_to_lhdn whitelisted function: "
            "(1) raises PermissionError if caller is not System Manager, "
            "(2) raises ValidationError if LHDN Status is not Invalid or Submitted, "
            "(3) resets custom_lhdn_status to Pending and calls frappe.enqueue when conditions met."
        ),
        "acceptanceCriteria": [
            "Test file: lhdn_payroll_integration/tests/test_resubmit_action.py",
            "Tests fail before implementation",
            "Covers: permission check, status precondition, status reset to Pending, enqueue call"
        ],
        "technicalNotes": [
            "Function: resubmit_to_lhdn(docname, doctype) in submission_service.py",
            "Decorator: @frappe.whitelist()",
            "Use unittest.mock.patch for frappe.enqueue and frappe.get_roles"
        ],
        "dependencies": ["US-035"],
        "estimatedComplexity": "small",
        "passes": False
    },
    {
        "id": "US-036",
        "title": "Add resubmit_to_lhdn whitelisted action for stuck Invalid submissions",
        "priority": 72,
        "description": (
            "Add a @frappe.whitelist() function resubmit_to_lhdn(docname, doctype) to submission_service.py "
            "that System Manager can call to reset LHDN Status to Pending and re-enqueue the submission job. "
            "This fixes stuck Invalid or network-failed submissions without requiring cancel+resubmit."
        ),
        "acceptanceCriteria": [
            "resubmit_to_lhdn(docname, doctype) in submission_service.py with @frappe.whitelist()",
            "Raises PermissionError if user lacks System Manager role",
            "Raises ValidationError if custom_lhdn_status not in [Invalid, Submitted]",
            "Sets custom_lhdn_status = Pending and saves before enqueue",
            "Enqueues process_salary_slip or process_expense_claim based on doctype",
            "UT-036 tests pass"
        ],
        "technicalNotes": [
            "Add to lhdn_payroll_integration/services/submission_service.py",
            "Use frappe.has_permission() or check 'System Manager' in frappe.get_roles()",
            "frappe.enqueue() with queue='short'"
        ],
        "dependencies": ["UT-036"],
        "estimatedComplexity": "small",
        "passes": False
    },
    {
        "id": "UT-037",
        "title": "Write failing tests for LHDN Payroll workspace fixture",
        "priority": 73,
        "description": (
            "Write a test that loads the workspace fixture JSON and asserts: "
            "name='LHDN Payroll', module='LHDN Payroll Integration', "
            "at least 4 shortcuts present (Salary Slip, Expense Claim, LHDN Payroll Compliance, Background Jobs)."
        ),
        "acceptanceCriteria": [
            "Test file: lhdn_payroll_integration/tests/test_workspace.py",
            "Asserts workspace fixture JSON has correct name and module",
            "Asserts at least 4 shortcut links",
            "Tests fail before workspace fixture is created"
        ],
        "technicalNotes": [
            "Workspace fixture: lhdn_payroll_integration/fixtures/workspace.json",
            "Or as a DocType folder: lhdn_payroll_integration/workspace/lhdn_payroll/",
            "Add 'Workspace' to hooks.py fixtures list"
        ],
        "dependencies": ["US-036"],
        "estimatedComplexity": "small",
        "passes": False
    },
    {
        "id": "US-037",
        "title": "Create LHDN Payroll workspace page with curated shortcuts",
        "priority": 74,
        "description": (
            "Create a Frappe Workspace named 'LHDN Payroll' under module 'LHDN Payroll Integration' "
            "with shortcuts to: Salary Slip (filtered to Contractor/Director), Expense Claim, "
            "LHDN Payroll Compliance report, Background Jobs. "
            "Also include a Number Card showing count of Pending LHDN submissions."
        ),
        "acceptanceCriteria": [
            "Workspace 'LHDN Payroll' visible after bench migrate or app install",
            "Contains shortcuts: Salary Slip, Expense Claim, LHDN Payroll Compliance, Background Jobs",
            "Workspace JSON in fixtures/workspace.json and listed in hooks.py fixtures",
            "UT-037 tests pass"
        ],
        "technicalNotes": [
            "Create lhdn_payroll_integration/fixtures/workspace.json",
            "Frappe Workspace doctype: name, module, shortcuts[] array with type, label, link_to",
            "Add 'Workspace' to hooks.py fixtures list"
        ],
        "dependencies": ["UT-037"],
        "estimatedComplexity": "medium",
        "passes": False
    },
    {
        "id": "UT-038",
        "title": "Write failing tests for LHDN Salary Slip print format",
        "priority": 75,
        "description": (
            "Write tests that verify the LHDN print format: "
            "(1) print format JSON file exists with correct doc_type=Salary Slip, "
            "(2) HTML template contains custom_lhdn_uuid reference, "
            "(3) HTML template contains custom_lhdn_qr_code reference, "
            "(4) HTML template has a conditional LHDN Compliant badge for status=Valid."
        ),
        "acceptanceCriteria": [
            "Test file: lhdn_payroll_integration/tests/test_print_format.py",
            "Tests assert print format JSON has doc_type=Salary Slip",
            "Tests assert HTML template contains all required LHDN field references",
            "Tests fail before print format files are created"
        ],
        "technicalNotes": [
            "Print format folder: lhdn_payroll_integration/print_format/lhdn_salary_slip_einvoice/",
            "Files: lhdn_salary_slip_einvoice.json + lhdn_salary_slip_einvoice.html",
            "Test reads the files directly and checks string content"
        ],
        "dependencies": ["US-037"],
        "estimatedComplexity": "small",
        "passes": False
    },
    {
        "id": "US-038",
        "title": "Create LHDN-compliant Salary Slip print format with UUID and QR code",
        "priority": 76,
        "description": (
            "Create a Frappe print format 'LHDN Salary Slip e-Invoice' for Salary Slip doctype. "
            "Shows: employee name, department, period, gross pay, net pay, deductions breakdown, "
            "LHDN UUID (if not Exempt), green 'LHDN e-Invoice Compliant' badge (when status=Valid), "
            "QR code image from custom_lhdn_qr_code field. Professional A4 layout suitable for payslip distribution."
        ),
        "acceptanceCriteria": [
            "Print format 'LHDN Salary Slip e-Invoice' appears in Salary Slip > Print options",
            "Shows standard payslip fields: employee, period, earnings, deductions, net pay",
            "Shows LHDN UUID if custom_lhdn_status is not Exempt",
            "Shows green 'LHDN e-Invoice Compliant' badge when custom_lhdn_status == Valid",
            "Renders custom_lhdn_qr_code HTML field when present",
            "UT-038 tests pass"
        ],
        "technicalNotes": [
            "Folder: lhdn_payroll_integration/lhdn_payroll_integration/print_format/lhdn_salary_slip_einvoice/",
            "JSON: standard Frappe print format with module, doc_type, disabled=0",
            "HTML: Jinja2 template using doc.custom_lhdn_status, doc.custom_lhdn_uuid, doc.custom_lhdn_qr_code",
            "Use {% if doc.custom_lhdn_status == 'Valid' %} for conditional badge"
        ],
        "dependencies": ["UT-038"],
        "estimatedComplexity": "medium",
        "passes": False
    }
]

added = 0
for story in new_stories:
    if story['id'] not in existing_ids:
        prd['userStories'].append(story)
        existing_ids.add(story['id'])
        added += 1
        print(f"  Added: {story['id']} - {story['title']}")
    else:
        print(f"  Skip (exists): {story['id']}")

with open(prd_path, 'w', encoding='utf-8') as f:
    json.dump(prd, f, indent=2, ensure_ascii=False)

print(f"\nDone. Added {added} stories. Total: {len(prd['userStories'])}")
