"""e-CP39 Service — Programmatic PCB Remittance Submission to LHDN MyTax / e-PCB Plus.

ITA Section 107(1): PCB must be remitted to LHDN by the 15th of the following month.
For employers with 50+ employees, LHDN expects electronic submission via e-PCB Plus API.

Flow:
  1. Authenticate with LHDN MyTax API using Company's custom_mytax_client_id / secret
  2. Pull CP39 data from existing report module
  3. Format as pipe-delimited payload (employer_e_number|month_year|tin|nric|name|category|gross|epf|zakat|cp38|pcb)
  4. POST to e-PCB Plus endpoint
  5. Store submission reference + response in LHDN CP39 Submission Log
"""
import json

import frappe
import requests
from frappe.utils import now_datetime

from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance.cp39_pcb_remittance import (
	get_data,
)

# --- LHDN MyTax API endpoints (sandbox) ---
_MYTAX_TOKEN_URL = "https://mytax.hasil.gov.my/api/auth/token"
_MYTAX_CP39_SUBMIT_URL = "https://mytax.hasil.gov.my/api/epcb/cp39/submit"


def _get_mytax_access_token(company_name):
	"""Obtain OAuth bearer token from LHDN MyTax API.

	Reads custom_mytax_client_id and custom_mytax_client_secret from Company.
	Raises frappe.ValidationError if credentials are missing.
	"""
	client_id = frappe.db.get_value("Company", company_name, "custom_mytax_client_id")
	client_secret = frappe.db.get_value("Company", company_name, "custom_mytax_client_secret")

	if not client_id or not client_secret:
		frappe.throw(
			f"MyTax API credentials missing on Company {company_name}. "
			"Please set custom_mytax_client_id and custom_mytax_client_secret.",
			frappe.ValidationError,
		)

	resp = requests.post(
		_MYTAX_TOKEN_URL,
		data={
			"grant_type": "client_credentials",
			"client_id": client_id,
			"client_secret": client_secret,
		},
		timeout=30,
	)

	if resp.status_code != 200:
		frappe.throw(
			f"MyTax authentication failed (HTTP {resp.status_code}): {resp.text}",
			frappe.AuthenticationError,
		)

	return resp.json().get("access_token", "")


def _build_pipe_delimited_payload(company_name, month, year):
	"""Build pipe-delimited CP39 payload from the CP39 PCB remittance report.

	Format per row:
	  employer_e_number|month_year|tin|nric|name|category|gross|epf|zakat|cp38|pcb
	"""
	month_str = str(month).zfill(2)
	filters = frappe._dict({"company": company_name, "month": month_str, "year": int(year)})
	rows = get_data(filters)

	lines = []
	for row in rows:
		line = "|".join([
			str(row.get("employer_e_number", "")),
			str(row.get("month_year", "")),
			str(row.get("employee_tin", "")),
			str(row.get("employee_nric", "")),
			str(row.get("employee_name", "")),
			str(row.get("pcb_category", "")),
			"{:.2f}".format(float(row.get("gross_remuneration") or 0)),
			"{:.2f}".format(float(row.get("epf_employee") or 0)),
			"{:.2f}".format(float(row.get("zakat_amount") or 0)),
			"{:.2f}".format(float(row.get("cp38_amount") or 0)),
			"{:.2f}".format(float(row.get("total_pcb") or 0)),
		])
		lines.append(line)

	return lines


def _store_submission_log(company_name, month, year, status, submission_reference, response_message, employees_count):
	"""Create an LHDN CP39 Submission Log record."""
	log = frappe.new_doc("LHDN CP39 Submission Log")
	log.company = company_name
	log.month = str(month).zfill(2)
	log.year = int(year)
	log.status = status
	log.submission_reference = submission_reference or ""
	log.submission_datetime = now_datetime()
	log.response_message = response_message or ""
	log.employees_count = employees_count
	log.insert(ignore_permissions=True)
	frappe.db.commit()
	return log.name


def submit_cp39_to_lhdn(company_name, month, year):
	"""Submit CP39 PCB remittance data to LHDN MyTax e-PCB Plus API.

	Args:
		company_name (str): ERPNext Company name (must have MyTax credentials)
		month (str|int): Month number (1-12 or '01'-'12')
		year (int): 4-digit year

	Returns:
		dict with keys: success (bool), log_name (str), reference (str), message (str)
	"""
	try:
		# Step 1: Authenticate
		access_token = _get_mytax_access_token(company_name)

		# Step 2: Build payload
		lines = _build_pipe_delimited_payload(company_name, month, year)

		if not lines:
			log_name = _store_submission_log(
				company_name, month, year,
				status="Failed",
				submission_reference="",
				response_message="No CP39 data found for the selected period.",
				employees_count=0,
			)
			return {
				"success": False,
				"log_name": log_name,
				"reference": "",
				"message": "No CP39 data found for the selected period.",
			}

		# Step 3: POST to e-PCB Plus
		payload = {
			"company": company_name,
			"month": str(month).zfill(2),
			"year": int(year),
			"records": lines,
		}

		resp = requests.post(
			_MYTAX_CP39_SUBMIT_URL,
			json=payload,
			headers={"Authorization": f"Bearer {access_token}"},
			timeout=60,
		)

		# Step 4: Parse response
		if resp.status_code in (200, 201):
			resp_data = resp.json() if resp.text else {}
			reference = resp_data.get("submissionReference") or resp_data.get("reference_number") or ""
			log_name = _store_submission_log(
				company_name, month, year,
				status="Submitted",
				submission_reference=reference,
				response_message=json.dumps(resp_data),
				employees_count=len(lines),
			)
			return {
				"success": True,
				"log_name": log_name,
				"reference": reference,
				"message": f"CP39 submitted successfully. Reference: {reference}",
			}
		else:
			error_msg = f"HTTP {resp.status_code}: {resp.text}"
			log_name = _store_submission_log(
				company_name, month, year,
				status="Failed",
				submission_reference="",
				response_message=error_msg,
				employees_count=len(lines),
			)
			return {
				"success": False,
				"log_name": log_name,
				"reference": "",
				"message": error_msg,
			}

	except frappe.ValidationError:
		raise
	except frappe.AuthenticationError:
		raise
	except Exception as exc:
		error_msg = str(exc)
		try:
			log_name = _store_submission_log(
				company_name, month, year,
				status="Failed",
				submission_reference="",
				response_message=error_msg,
				employees_count=0,
			)
		except Exception:
			log_name = ""
		return {
			"success": False,
			"log_name": log_name,
			"reference": "",
			"message": error_msg,
		}
