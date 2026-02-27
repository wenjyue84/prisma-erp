"""7-year LHDN audit retention archival and locking service.

Malaysian Income Tax Act requires 7-year retention of all e-invoice records.
This module provides:
- get_retention_date(dt): calculate retention expiry (submission + 7 years)
- run_retention_archival(): yearly scheduler to mark expired records as archived
- check_retention_lock(doc): before_amend hook to prevent amending archived records
"""

import frappe
from dateutil.relativedelta import relativedelta


def get_retention_date(dt):
	"""Return the retention expiry datetime, 7 years after the given datetime.

	Args:
		dt: datetime of LHDN submission

	Returns:
		datetime: dt + 7 years
	"""
	return dt + relativedelta(years=7)


def run_retention_archival():
	"""Yearly scheduled job: archive LHDN records whose 7-year retention has expired.

	Uses COALESCE(custom_lhdn_validated_datetime, custom_lhdn_submission_datetime, creation)
	so records with status Submitted, Invalid, or Valid are all included in the archival scan.
	"""
	now = frappe.utils.now_datetime()
	cutoff = now - relativedelta(years=7)

	for doctype in ("Salary Slip", "Expense Claim"):
		table = f"tab{doctype}"
		results = frappe.db.sql(
			f"""SELECT name
			FROM `{table}`
			WHERE custom_lhdn_archived = 0
			  AND COALESCE(
			        custom_lhdn_validated_datetime,
			        custom_lhdn_submission_datetime,
			        creation
			      ) < %(cutoff)s""",
			{"cutoff": cutoff},
			as_dict=True,
		)
		for row in results:
			frappe.db.set_value(
				doctype,
				row["name"],
				"custom_lhdn_archived",
				1,
			)

	frappe.db.commit()


def check_retention_lock(doc, method=None):
	"""Before-amend hook: block amendment of archived LHDN records.

	Args:
		doc: the document being amended
		method: Frappe hook method name (unused)

	Raises:
		frappe.ValidationError: if the document is archived
	"""
	if getattr(doc, "custom_lhdn_archived", 0) == 1:
		frappe.throw(
			"This LHDN record is archived for the 7-year audit period and cannot be amended",
			frappe.ValidationError,
		)
