"""CP58 Agent/Dealer Non-Employment Income Statement — US-079.

ITA 1967 Section 83A(1A) and P.U.(A) 220/2019 require payers to issue
Borang CP58 to agents, dealers, and distributors who receive commission/
incentive payments by 31 March each year.

Covers contractors and commission agents who are NOT employees.

Columns:
  Agent Name, NRIC/Reg No, TIN, Jan-Dec monthly amounts, Total Annual.
"""
import frappe


def get_columns():
    months = [
        ("Jan", "jan"), ("Feb", "feb"), ("Mar", "mar"), ("Apr", "apr"),
        ("May", "may"), ("Jun", "jun"), ("Jul", "jul"), ("Aug", "aug"),
        ("Sep", "sep"), ("Oct", "oct"), ("Nov", "nov"), ("Dec", "dec"),
    ]
    cols = [
        {
            "label": "Agent Name",
            "fieldname": "payee_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "NRIC / Registration No",
            "fieldname": "payee_nric_reg",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "TIN",
            "fieldname": "payee_tin",
            "fieldtype": "Data",
            "width": 160,
        },
    ]
    for label, fieldname in months:
        cols.append(
            {
                "label": label,
                "fieldname": fieldname,
                "fieldtype": "Currency",
                "options": "MYR",
                "width": 110,
            }
        )
    cols.append(
        {
            "label": "Total Annual (MYR)",
            "fieldname": "total_annual",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        }
    )
    return cols


def get_filters():
    current_year = frappe.utils.getdate().year
    return [
        {
            "fieldname": "company",
            "label": "Company",
            "fieldtype": "Link",
            "options": "Company",
            "reqd": 0,
        },
        {
            "fieldname": "year",
            "label": "Year",
            "fieldtype": "Int",
            "default": current_year,
        },
    ]


def _build_conditions(filters):
    conditions = [
        "ec.docstatus = 1",
        "ec.custom_payee_type = 'Contractor'",
        "ec.custom_payment_category IN ('Commission', 'Service Fee')",
    ]
    values = {}

    if filters.get("company"):
        conditions.append("ec.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("year"):
        try:
            year_val = int(filters["year"])
        except (ValueError, TypeError):
            year_val = None
        if year_val:
            conditions.append("YEAR(ec.posting_date) = %(year)s")
            values["year"] = year_val

    where = "WHERE " + " AND ".join(conditions)
    return where, values


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    where, values = _build_conditions(filters)

    sql = """
        SELECT
            COALESCE(ec.custom_payee_name, '')       AS payee_name,
            COALESCE(ec.custom_payee_nric_reg, '')   AS payee_nric_reg,
            COALESCE(ec.custom_payee_tin, '')        AS payee_tin,
            SUM(CASE WHEN MONTH(ec.posting_date) = 1  THEN ec.total_claimed_amount ELSE 0 END) AS `jan`,
            SUM(CASE WHEN MONTH(ec.posting_date) = 2  THEN ec.total_claimed_amount ELSE 0 END) AS `feb`,
            SUM(CASE WHEN MONTH(ec.posting_date) = 3  THEN ec.total_claimed_amount ELSE 0 END) AS `mar`,
            SUM(CASE WHEN MONTH(ec.posting_date) = 4  THEN ec.total_claimed_amount ELSE 0 END) AS `apr`,
            SUM(CASE WHEN MONTH(ec.posting_date) = 5  THEN ec.total_claimed_amount ELSE 0 END) AS `may`,
            SUM(CASE WHEN MONTH(ec.posting_date) = 6  THEN ec.total_claimed_amount ELSE 0 END) AS `jun`,
            SUM(CASE WHEN MONTH(ec.posting_date) = 7  THEN ec.total_claimed_amount ELSE 0 END) AS `jul`,
            SUM(CASE WHEN MONTH(ec.posting_date) = 8  THEN ec.total_claimed_amount ELSE 0 END) AS `aug`,
            SUM(CASE WHEN MONTH(ec.posting_date) = 9  THEN ec.total_claimed_amount ELSE 0 END) AS `sep`,
            SUM(CASE WHEN MONTH(ec.posting_date) = 10 THEN ec.total_claimed_amount ELSE 0 END) AS `oct`,
            SUM(CASE WHEN MONTH(ec.posting_date) = 11 THEN ec.total_claimed_amount ELSE 0 END) AS `nov`,
            SUM(CASE WHEN MONTH(ec.posting_date) = 12 THEN ec.total_claimed_amount ELSE 0 END) AS `dec`,
            SUM(ec.total_claimed_amount)             AS total_annual
        FROM `tabExpense Claim` ec
        {where}
        GROUP BY ec.custom_payee_name, ec.custom_payee_nric_reg, ec.custom_payee_tin
        ORDER BY ec.custom_payee_name ASC
    """.format(where=where)

    rows = frappe.db.sql(sql, values, as_dict=True)
    return list(rows)


def execute(filters=None):
    return get_columns(), get_data(filters)
