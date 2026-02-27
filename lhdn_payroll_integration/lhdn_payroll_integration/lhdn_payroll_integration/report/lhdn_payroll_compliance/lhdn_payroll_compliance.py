"""LHDN Payroll Compliance Script Report.

Lists Salary Slips and Expense Claims with their LHDN submission status.
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
    """Build WHERE clauses for Salary Slip and Expense Claim subqueries.

    Both subqueries share the same parameter dict since they filter on the
    same logical values (same company, same employee, same date range, same status).
    The date field aliases differ: SS uses start_date/end_date; EC uses posting_date.

    Returns (ss_where, ec_where, values).
    """
    ss_conds = []
    ec_conds = []
    values = {}

    if filters.get("from_date"):
        ss_conds.append("ss.start_date >= %(from_date)s")
        ec_conds.append("ec.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        ss_conds.append("ss.end_date <= %(to_date)s")
        ec_conds.append("ec.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("company"):
        ss_conds.append("ss.company = %(company)s")
        ec_conds.append("ec.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("employee"):
        ss_conds.append("ss.employee = %(employee)s")
        ec_conds.append("ec.employee = %(employee)s")
        values["employee"] = filters["employee"]

    if filters.get("lhdn_status"):
        ss_conds.append("ss.custom_lhdn_status = %(lhdn_status)s")
        ec_conds.append("ec.custom_lhdn_status = %(lhdn_status)s")
        values["lhdn_status"] = filters["lhdn_status"]

    ss_where = ("WHERE " + " AND ".join(ss_conds)) if ss_conds else ""
    ec_where = ("WHERE " + " AND ".join(ec_conds)) if ec_conds else ""
    return ss_where, ec_where, values


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    ss_where, ec_where, values = _build_conditions(filters)

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
        {ss_where}

        UNION ALL

        SELECT
            'Expense Claim'                    AS document_type,
            ec.name                            AS document_name,
            ec.employee                        AS employee,
            ec.posting_date                    AS period,
            ec.total_claimed_amount            AS amount,
            COALESCE(ec.custom_lhdn_status, 'Pending') AS lhdn_status,
            ec.custom_lhdn_uuid                AS uuid,
            NULL                               AS submitted_at,
            NULL                               AS validated_at
        FROM `tabExpense Claim` ec
        {ec_where}

        ORDER BY document_name ASC
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
