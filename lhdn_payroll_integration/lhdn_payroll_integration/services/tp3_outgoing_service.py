"""TP3 Outgoing Service — YTD Income Statement for Departing Employees.

Generates Borang TP3 (outgoing) when an employee leaves mid-year.
The TP3 is an employer-to-employee document: NOT submitted to LHDN.
It allows the next employer to factor prior YTD income into their PCB
calculation (Method 2).

Regulatory basis: LHDN Borang TP3; Income Tax Act 1967 employer obligations.
7-year document retention per LHDN audit requirements.

US-143: Auto-Generate TP3 YTD Income Statement for Departing Employees.
"""

import frappe


def generate_outgoing_tp3(employee: str, tax_year: int, last_working_date: str = None) -> str:
	"""Create an Employee Outgoing TP3 record for a departing employee.

	Aggregates all submitted Salary Slips for the employee between
	1 January and last_working_date (or today if not provided) in the
	given tax_year.

	Args:
		employee: Employee document name (e.g. 'HR-EMP-00001').
		tax_year: Calendar year (e.g. 2025).
		last_working_date: ISO date string of last working day.
			If None, uses employee relieving_date or today.

	Returns:
		Name (ID) of the created Employee Outgoing TP3 document.
	"""
	from frappe.utils import today, getdate

	if not last_working_date:
		relieving = frappe.db.get_value("Employee", employee, "relieving_date")
		last_working_date = str(relieving) if relieving else today()

	ytd = get_ytd_payroll_totals(employee, tax_year, last_working_date)

	emp_doc = frappe.db.get_value(
		"Employee",
		employee,
		["employee_name", "company",
		 "custom_nric_passport_no", "custom_employee_tax_file_number"],
		as_dict=True,
	)
	if not emp_doc:
		frappe.throw(f"Employee {employee} not found.")

	company_doc = frappe.db.get_value(
		"Company",
		emp_doc.company,
		["company_name", "custom_company_tin_number"],
		as_dict=True,
	)

	doc = frappe.new_doc("Employee Outgoing TP3")
	doc.employee = employee
	doc.employee_name = emp_doc.employee_name or ""
	doc.company = emp_doc.company
	doc.tax_year = int(tax_year)
	doc.last_working_date = last_working_date
	doc.status = "Generated"

	doc.employee_nric = (emp_doc.custom_nric_passport_no or "")
	doc.employee_tax_file_number = (emp_doc.custom_employee_tax_file_number or "")

	if company_doc:
		doc.employer_name = company_doc.company_name or ""
		doc.employer_tin = company_doc.custom_company_tin_number or ""

	doc.ytd_basic_salary = ytd.get("ytd_basic_salary", 0.0)
	doc.ytd_gross_allowances = ytd.get("ytd_gross_allowances", 0.0)
	doc.ytd_bik_value = ytd.get("ytd_bik_value", 0.0)
	doc.ytd_epf_employee = ytd.get("ytd_epf_employee", 0.0)
	doc.ytd_socso = ytd.get("ytd_socso", 0.0)
	doc.ytd_eis = ytd.get("ytd_eis", 0.0)
	doc.ytd_zakat = ytd.get("ytd_zakat", 0.0)
	doc.ytd_cp38 = ytd.get("ytd_cp38", 0.0)
	doc.ytd_pcb = ytd.get("ytd_pcb", 0.0)

	doc.notes = (
		"IMPORTANT: This TP3 is an employer-to-employee document only. "
		"Do NOT submit to LHDN. Retain for 7 years per LHDN audit requirements."
	)

	doc.insert(ignore_permissions=True)
	return doc.name


def get_ytd_payroll_totals(employee: str, tax_year: int, cutoff_date: str = None) -> dict:
	"""Aggregate YTD payroll figures from submitted Salary Slips.

	Queries all submitted (docstatus=1) Salary Slips for the given employee
	from 1 January of tax_year up to cutoff_date (or year-end if not given).

	Args:
		employee: Employee document name.
		tax_year: Calendar year.
		cutoff_date: Upper bound date (inclusive). Defaults to 31 Dec of tax_year.

	Returns:
		dict with keys: ytd_basic_salary, ytd_gross_allowances, ytd_bik_value,
			ytd_epf_employee, ytd_socso, ytd_eis, ytd_zakat, ytd_cp38, ytd_pcb.
	"""
	from_date = f"{tax_year}-01-01"
	to_date = cutoff_date or f"{tax_year}-12-31"

	slips = frappe.db.get_all(
		"Salary Slip",
		filters={
			"employee": employee,
			"docstatus": 1,
			"start_date": [">=", from_date],
			"end_date": ["<=", to_date],
		},
		fields=[
			"gross_pay",
			"custom_ytd_basic_salary",
			"custom_bik_value",
			"custom_epf_employee",
			"custom_socso_employee",
			"custom_eis_employee",
			"custom_zakat_deducted",
			"custom_cp38_deducted",
			"custom_pcb_amount",
			"total_deduction",
		],
	)

	totals = {
		"ytd_basic_salary": 0.0,
		"ytd_gross_allowances": 0.0,
		"ytd_bik_value": 0.0,
		"ytd_epf_employee": 0.0,
		"ytd_socso": 0.0,
		"ytd_eis": 0.0,
		"ytd_zakat": 0.0,
		"ytd_cp38": 0.0,
		"ytd_pcb": 0.0,
	}

	for slip in slips:
		totals["ytd_basic_salary"] += float(slip.get("custom_ytd_basic_salary") or 0)
		totals["ytd_gross_allowances"] += float(slip.get("gross_pay") or 0)
		totals["ytd_bik_value"] += float(slip.get("custom_bik_value") or 0)
		totals["ytd_epf_employee"] += float(slip.get("custom_epf_employee") or 0)
		totals["ytd_socso"] += float(slip.get("custom_socso_employee") or 0)
		totals["ytd_eis"] += float(slip.get("custom_eis_employee") or 0)
		totals["ytd_zakat"] += float(slip.get("custom_zakat_deducted") or 0)
		totals["ytd_cp38"] += float(slip.get("custom_cp38_deducted") or 0)
		totals["ytd_pcb"] += float(slip.get("custom_pcb_amount") or 0)

	return totals


def handle_employee_left_tp3(doc, method):
	"""Hook: auto-flag departing employee for outgoing TP3 generation.

	Triggered on Employee 'on_update' when status is set to 'Left'.
	Creates an Employee Outgoing TP3 record if one does not already exist
	for the current tax year.
	"""
	if doc.status != "Left":
		return

	from frappe.utils import getdate, today

	cessation = (
		getdate(doc.relieving_date) if doc.relieving_date else getdate(today())
	)
	tax_year = cessation.year

	# Avoid duplicate
	if frappe.db.exists(
		"Employee Outgoing TP3",
		{"employee": doc.name, "tax_year": tax_year},
	):
		return

	try:
		tp3_name = generate_outgoing_tp3(
			employee=doc.name,
			tax_year=tax_year,
			last_working_date=str(cessation),
		)
		frappe.msgprint(
			f"Outgoing TP3 <b>{tp3_name}</b> generated for {doc.employee_name}. "
			f"Hand this to the departing employee for their next employer's PCB calculation. "
			f"<br><b>Note:</b> Do NOT submit to LHDN. Retain 7 years per audit requirements.",
			title="Outgoing TP3 Generated",
			indicator="green",
		)
	except Exception as e:
		frappe.log_error(f"Failed to generate outgoing TP3 for {doc.name}: {e}", "TP3 Outgoing")
