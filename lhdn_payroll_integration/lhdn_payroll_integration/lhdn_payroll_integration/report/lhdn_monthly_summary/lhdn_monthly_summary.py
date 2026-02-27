"""LHDN Monthly Submission Summary Script Report.

Groups LHDN-submitted Salary Slips and Expense Claims by calendar month.
One row per month (Jan-Dec) for the selected year.

Columns: Month, Total Submitted, Valid, Invalid, Pending, Exempt,
         Total Value MYR, Deadline Status.

Deadline Status uses the LHDN 7-calendar-day rule:
  - Pending  : today is on or before the submission deadline for that month
  - On Time  : deadline has passed and no Pending documents remain
  - Late     : deadline has passed and Pending documents still exist
"""
import calendar
from datetime import date

import frappe
from lhdn_payroll_integration.lhdn_payroll_integration.services.consolidation_service import (
	get_consolidation_deadline,
)

MONTH_NAMES = [
	"", "January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]


def get_columns():
	return [
		{
			"label": "Month",
			"fieldname": "month",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": "Total Submitted",
			"fieldname": "total_submitted",
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"label": "Valid",
			"fieldname": "valid_count",
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"label": "Invalid",
			"fieldname": "invalid_count",
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"label": "Pending",
			"fieldname": "pending_count",
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"label": "Exempt",
			"fieldname": "exempt_count",
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"label": "Total Value MYR",
			"fieldname": "total_value",
			"fieldtype": "Currency",
			"options": "MYR",
			"width": 140,
		},
		{
			"label": "Deadline Status",
			"fieldname": "deadline_status",
			"fieldtype": "Data",
			"width": 120,
		},
	]


def get_data(filters=None):
	if filters is None:
		filters = frappe._dict()

	year = int(filters.get("year") or date.today().year)
	company = filters.get("company")

	values = {"year": year}
	company_filter_ss = ""
	company_filter_ec = ""
	if company:
		company_filter_ss = "AND ss.company = %(company)s"
		company_filter_ec = "AND ec.company = %(company)s"
		values["company"] = company

	sql = f"""
		SELECT
			month_num,
			COUNT(*) AS total_submitted,
			SUM(CASE WHEN lhdn_status = 'Valid' THEN 1 ELSE 0 END) AS valid_count,
			SUM(CASE WHEN lhdn_status = 'Invalid' THEN 1 ELSE 0 END) AS invalid_count,
			SUM(CASE WHEN lhdn_status = 'Pending' THEN 1 ELSE 0 END) AS pending_count,
			SUM(CASE WHEN lhdn_status = 'Exempt' THEN 1 ELSE 0 END) AS exempt_count,
			SUM(amount) AS total_value
		FROM (
			SELECT
				MONTH(ss.posting_date) AS month_num,
				ss.net_pay AS amount,
				COALESCE(ss.custom_lhdn_status, 'Pending') AS lhdn_status
			FROM `tabSalary Slip` ss
			WHERE YEAR(ss.posting_date) = %(year)s
				AND ss.docstatus = 1
				{company_filter_ss}

			UNION ALL

			SELECT
				MONTH(ec.posting_date) AS month_num,
				ec.total_claimed_amount AS amount,
				COALESCE(ec.custom_lhdn_status, 'Pending') AS lhdn_status
			FROM `tabExpense Claim` ec
			WHERE YEAR(ec.posting_date) = %(year)s
				AND ec.docstatus = 1
				{company_filter_ec}
		) AS combined
		GROUP BY month_num
		ORDER BY month_num
	"""

	db_rows = frappe.db.sql(sql, values, as_dict=True)
	db_by_month = {int(r.month_num): r for r in db_rows}

	today = date.today()
	result = []

	for m in range(1, 13):
		target_month = f"{year:04d}-{m:02d}"
		deadline = get_consolidation_deadline(target_month)

		if m in db_by_month:
			row_data = db_by_month[m]
			total = int(row_data.total_submitted or 0)
			valid = int(row_data.valid_count or 0)
			invalid = int(row_data.invalid_count or 0)
			pending = int(row_data.pending_count or 0)
			exempt = int(row_data.exempt_count or 0)
			total_value = float(row_data.total_value or 0)
		else:
			total = valid = invalid = pending = exempt = 0
			total_value = 0.0

		# 7-day rule: deadline = last day of month + 7 days
		if today <= deadline:
			deadline_status = "Pending"
		elif pending > 0:
			deadline_status = "Late"
		else:
			deadline_status = "On Time"

		result.append({
			"month": MONTH_NAMES[m],
			"total_submitted": total,
			"valid_count": valid,
			"invalid_count": invalid,
			"pending_count": pending,
			"exempt_count": exempt,
			"total_value": total_value,
			"deadline_status": deadline_status,
		})

	return result


def execute(filters=None):
	return get_columns(), get_data(filters)
