"""TP3 Service — Prior Employer Year-to-Date Declaration helpers.

Provides lookup functions for Borang TP3 data used in PCB Method 2
calculations when an employee joins mid-year with income from a previous employer.

Regulatory basis: LHDN Borang TP3 (prior employment income declaration).
"""

import frappe


def get_tp3_for_employee(employee: str, tax_year: int) -> dict:
	"""Return prior employer YTD income and PCB data for an employee.

	Queries the Employee TP3 Declaration DocType for a record matching
	the given employee and tax year.

	Args:
		employee: Employee document name (e.g. 'HR-EMP-00001').
		tax_year: Calendar year (e.g. 2024).

	Returns:
		dict with keys:
			prior_gross (float): Total prior gross income (RM). 0.0 if no record.
			prior_pcb   (float): Total prior PCB deducted (RM). 0.0 if no record.
			prior_epf   (float): Total prior EPF deducted (RM). 0.0 if no record.
			joining_month (int): Month of joining (1–12). None if no record.
	"""
	try:
		result = frappe.db.get_value(
			"Employee TP3 Declaration",
			{"employee": employee, "tax_year": int(tax_year)},
			["prior_gross_income", "prior_pcb_deducted", "prior_epf_deducted", "joining_month"],
			as_dict=True,
		)
		if not result:
			return {"prior_gross": 0.0, "prior_pcb": 0.0, "prior_epf": 0.0, "joining_month": None}

		return {
			"prior_gross": float(result.get("prior_gross_income") or 0),
			"prior_pcb": float(result.get("prior_pcb_deducted") or 0),
			"prior_epf": float(result.get("prior_epf_deducted") or 0),
			"joining_month": result.get("joining_month"),
		}
	except Exception:
		return {"prior_gross": 0.0, "prior_pcb": 0.0, "prior_epf": 0.0, "joining_month": None}


def requires_tp3_collection(employee: str, tax_year: int) -> bool:
	"""Return True if the employee joined mid-year and TP3 should be collected.

	An employee who joins in February or later (joining_month != 1) may have
	prior employment income that must be declared via Borang TP3 to prevent
	under-deduction of PCB.

	Args:
		employee: Employee document name.
		tax_year: Calendar year.

	Returns:
		bool: True if TP3 collection is required (joining month > 1).
	"""
	data = get_tp3_for_employee(employee, tax_year)
	joining_month = data.get("joining_month")
	if joining_month is None:
		# Fall back to employee date_of_joining if no TP3 record
		doj = frappe.db.get_value("Employee", employee, "date_of_joining")
		if doj:
			import datetime
			if isinstance(doj, str):
				doj = datetime.date.fromisoformat(str(doj)[:10])
			if getattr(doj, "year", None) == int(tax_year):
				return doj.month > 1
		return False
	return int(joining_month) > 1
