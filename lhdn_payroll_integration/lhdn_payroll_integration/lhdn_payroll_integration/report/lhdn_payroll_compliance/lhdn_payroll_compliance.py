"""LHDN Payroll Compliance Script Report.

Lists all Salary Slips with their LHDN submission status.
Columns: Document Type, Document Name, Employee, Period, Amount, LHDN Status, UUID, Submitted At, Validated At.
"""
import frappe


def get_columns():
    return [
        {
            "label": "Document Type",
            "fieldname": "document_type",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Document Name",
            "fieldname": "document_name",
            "fieldtype": "Dynamic Link",
            "options": "document_type",
            "width": 160,
        },
        {
            "label": "Employee",
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 140,
        },
        {
            "label": "Period",
            "fieldname": "period",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": "Amount (MYR)",
            "fieldname": "amount",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 120,
        },
        {
            "label": "LHDN Status",
            "fieldname": "lhdn_status",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "UUID",
            "fieldname": "uuid",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "Submitted At",
            "fieldname": "submitted_at",
            "fieldtype": "Datetime",
            "width": 160,
        },
        {
            "label": "Validated At",
            "fieldname": "validated_at",
            "fieldtype": "Datetime",
            "width": 160,
        },
    ]


def get_filters():
    return [
        {
            "fieldname": "from_date",
            "label": "From Date",
            "fieldtype": "Date",
            "default": frappe.utils.get_first_day(frappe.utils.nowdate()),
        },
        {
            "fieldname": "to_date",
            "label": "To Date",
            "fieldtype": "Date",
            "default": frappe.utils.get_last_day(frappe.utils.nowdate()),
        },
        {
            "fieldname": "company",
            "label": "Company",
            "fieldtype": "Link",
            "options": "Company",
        },
        {
            "fieldname": "employee",
            "label": "Employee",
            "fieldtype": "Link",
            "options": "Employee",
        },
        {
            "fieldname": "lhdn_status",
            "label": "LHDN Status",
            "fieldtype": "Select",
            "options": "\nPending\nValid\nInvalid\nExempt\nCancelled",
        },
    ]


_STATUS_INDICATOR = {
    "Valid": "green",
    "Pending": "orange",
    "Invalid": "red",
    "Exempt": "grey",
    "Cancelled": "grey",
}


def _build_conditions(filters):
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("ss.start_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("ss.end_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("company"):
        conditions.append("ss.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("employee"):
        conditions.append("ss.employee = %(employee)s")
        values["employee"] = filters["employee"]

    if filters.get("lhdn_status"):
        conditions.append("ss.custom_lhdn_status = %(lhdn_status)s")
        values["lhdn_status"] = filters["lhdn_status"]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, values


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    where, values = _build_conditions(filters)

    sql = f"""
        SELECT
            'Salary Slip'                      AS document_type,
            ss.name                            AS document_name,
            ss.employee                        AS employee,
            CONCAT(ss.start_date, ' - ', ss.end_date) AS period,
            ss.net_pay                         AS amount,
            COALESCE(ss.custom_lhdn_status, 'Pending') AS lhdn_status,
            ss.custom_lhdn_uuid                AS uuid,
            ss.custom_lhdn_submission_datetime AS submitted_at,
            ss.custom_lhdn_validated_datetime  AS validated_at
        FROM `tabSalary Slip` ss
        {where}
        ORDER BY ss.start_date DESC, ss.name ASC
    """

    rows = frappe.db.sql(sql, values, as_dict=True)

    # Attach indicator colour for UI rendering
    for row in rows:
        status = row.get("lhdn_status") or "Pending"
        colour = _STATUS_INDICATOR.get(status, "grey")
        row["lhdn_status"] = f"{colour} {status}"

    return rows


def execute(filters=None):
    return get_columns(), get_data(filters)
