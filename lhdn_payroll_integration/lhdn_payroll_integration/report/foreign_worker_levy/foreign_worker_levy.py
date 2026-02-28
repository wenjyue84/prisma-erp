"""Foreign Worker Levy Script Report.

Lists all foreign workers with their annual FWCMS levy due/paid status
and renewal dates. Supports Company and Year filters.

Per Foreign Workers Levy Act 2021 / Multi-Tier Levy Model (MTLM) effective
January 2025: RM410-RM2,500/year per foreign worker depending on sector
and nationality / local-to-foreign ratio.

US-070: Foreign Worker Levy Tracking.
US-095: MTLM tier calculation added to report columns.
"""
import frappe
from frappe.utils import flt, getdate, today, add_days
from lhdn_payroll_integration.lhdn_payroll_integration.services.fw_levy_service import calculate_fw_levy_tier


OVERDUE_WINDOW_DAYS = 30


def get_columns():
    return [
        {
            "label": "Employee",
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 120,
        },
        {
            "label": "Employee Name",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "Nationality Code",
            "fieldname": "nationality_code",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": "Annual Levy (MYR)",
            "fieldname": "levy_rate",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "Levy Due Date",
            "fieldname": "levy_due_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Receipt Ref",
            "fieldname": "receipt_ref",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": "Paid Amount (MYR)",
            "fieldname": "paid_amount",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "Payment Date",
            "fieldname": "payment_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Levy Status",
            "fieldname": "levy_status",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "MTLM Tier",
            "fieldname": "levy_tier",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": "MTLM Annual Levy (MYR)",
            "fieldname": "mtlm_annual_levy",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 170,
        },
    ]


def get_filters():
    current_year = frappe.utils.getdate().year
    return [
        {
            "fieldname": "company",
            "label": "Company",
            "fieldtype": "Link",
            "options": "Company",
            "reqd": 1,
        },
        {
            "fieldname": "year",
            "label": "Year",
            "fieldtype": "Int",
            "default": current_year,
            "reqd": 1,
        },
    ]


def _get_paid_levies(year):
    """Return dict of {employee: {paid_amount, payment_date}} for the given year."""
    rows = frappe.db.sql(
        """
        SELECT
            employee,
            SUM(levy_amount) AS paid_amount,
            MAX(payment_date) AS payment_date
        FROM `tabForeign Worker Levy Payment`
        WHERE levy_period_year = %(year)s
        GROUP BY employee
        """,
        {"year": year},
        as_dict=True,
    )
    return {r["employee"]: r for r in rows}


def _levy_status(levy_due_date, paid_amount, levy_rate):
    """Determine levy status string."""
    if flt(paid_amount) >= flt(levy_rate) and flt(levy_rate) > 0:
        return "Paid"
    if not levy_due_date:
        return "Not Set"
    due = getdate(levy_due_date)
    today_date = getdate(today())
    if due < today_date:
        return "Overdue"
    threshold = getdate(add_days(today(), OVERDUE_WINDOW_DAYS))
    if due <= threshold:
        return "Due Soon"
    return "Upcoming"


def _get_employees(company):
    """Return list of active foreign workers for the given company."""
    return frappe.db.sql(
        """
        SELECT
            name AS employee,
            employee_name,
            custom_nationality_code AS nationality_code,
            custom_fw_levy_rate AS levy_rate,
            custom_fw_levy_due_date AS levy_due_date,
            custom_fw_levy_receipt_ref AS receipt_ref
        FROM `tabEmployee`
        WHERE company = %(company)s
          AND custom_is_foreign_worker = 1
          AND status = 'Active'
        ORDER BY employee_name ASC
        """,
        {"company": company},
        as_dict=True,
    )


def _get_company_headcounts(company):
    """Return (local_count, foreign_count) from Company custom fields for MTLM tier."""
    try:
        doc = frappe.db.get_value(
            "Company",
            company,
            ["custom_local_employee_count", "custom_foreign_employee_count"],
            as_dict=True,
        )
        if doc:
            return int(doc.get("custom_local_employee_count") or 0), int(doc.get("custom_foreign_employee_count") or 0)
    except Exception:
        pass
    return 0, 0


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    company = filters.get("company")
    year = filters.get("year")

    if not company or not year:
        return []

    employees = _get_employees(company)
    paid_map = _get_paid_levies(year)

    # Compute company MTLM tier once for all workers
    local_count, foreign_count = _get_company_headcounts(company)
    tier_name, mtlm_rate = calculate_fw_levy_tier(local_count, foreign_count)

    rows = []
    for emp in employees:
        payment = paid_map.get(emp["employee"], {})
        paid_amount = flt(payment.get("paid_amount", 0))
        payment_date = payment.get("payment_date")

        status = _levy_status(emp["levy_due_date"], paid_amount, emp["levy_rate"])

        rows.append(
            {
                "employee": emp["employee"],
                "employee_name": emp["employee_name"],
                "nationality_code": emp.get("nationality_code") or "",
                "levy_rate": flt(emp.get("levy_rate") or 0),
                "levy_due_date": emp.get("levy_due_date"),
                "receipt_ref": emp.get("receipt_ref") or "",
                "paid_amount": paid_amount,
                "payment_date": payment_date,
                "levy_status": status,
                "levy_tier": tier_name,
                "mtlm_annual_levy": flt(mtlm_rate),
            }
        )

    return rows


def execute(filters=None):
    return get_columns(), get_data(filters)
