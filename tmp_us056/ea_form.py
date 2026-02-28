"""EA Form (Borang EA) Script Report — US-056 Rebuild.

Full LHDN-prescribed Borang EA format (gazetted under P.U.(A) 107/2021) covering:
- Section A: Employer information (name, address, E-number, branch code)
- Section B: Income breakdown — B1-B12 line items from Salary Component ea_section tagging
- Section C: Statutory deductions — C1 EPF, C2 SOCSO, C3 EIS, C4 PCB, C5 Zakat
- Section D: Tax position (PCB category)

Issuing an incomplete EA Form is a criminal offence under ITA Section 120(1)(b).
"""
import frappe


# EA Section map: (option_value, column_fieldname, column_label)
EA_SECTION_MAP = [
    ("B1 Basic Salary",     "b1_basic_salary",     "B1 – Basic Salary"),
    ("B2 Overtime",         "b2_overtime",          "B2 – Overtime"),
    ("B3 Commission",       "b3_commission",        "B3 – Commission"),
    ("B4 Bonus",            "b4_bonus",             "B4 – Bonus"),
    ("B5 Gratuity",         "b5_gratuity",          "B5 – Gratuity"),
    ("B6 Allowance",        "b6_allowance",         "B6 – Allowance"),
    ("B7 BIK",              "b7_bik",               "B7 – Benefits-in-Kind"),
    ("B8 Leave Encashment", "b8_leave_encashment",  "B8 – Leave Encashment"),
    ("B9 Other Gains",      "b9_other_gains",       "B9 – Other Gains"),
    ("B10 ESOS Gain",       "b10_esos_gain",        "B10 – ESOS Gain"),
    ("B11 Pension",         "b11_pension",          "B11 – Pension"),
]

# All B-section fieldnames for quick lookup
B_SECTION_FIELDNAMES = {opt: fn for opt, fn, _ in EA_SECTION_MAP}


def get_columns():
    cols = [
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
            "width": 180,
        },
        {
            "label": "Year",
            "fieldname": "year",
            "fieldtype": "Data",
            "width": 70,
        },
        # Section A — Employer
        {
            "label": "A – Employer Name",
            "fieldname": "company_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "A – E-Number",
            "fieldname": "employer_e_number",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": "A – Branch Code",
            "fieldname": "branch_code",
            "fieldtype": "Data",
            "width": 110,
        },
    ]

    # Section B — B1 to B11 (tagged earnings)
    for _opt, fn, label in EA_SECTION_MAP:
        cols.append(
            {
                "label": label,
                "fieldname": fn,
                "fieldtype": "Currency",
                "options": "MYR",
                "width": 150,
            }
        )

    # B12 = sum of B1–B11 + untagged earnings
    cols.append(
        {
            "label": "B12 – Total Gross Remuneration",
            "fieldname": "b12_total_gross",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 200,
        }
    )

    # Section C — Statutory Deductions
    cols += [
        {
            "label": "C1 – EPF Employee (KWSP)",
            "fieldname": "c1_epf",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "C2 – SOCSO Employee (PERKESO)",
            "fieldname": "c2_socso",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
        },
        {
            "label": "C3 – EIS Employee",
            "fieldname": "c3_eis",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "C4 – PCB / MTD",
            "fieldname": "c4_pcb",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "C5 – Zakat",
            "fieldname": "c5_zakat",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 130,
        },
    ]

    # Section D — Tax Position
    cols.append(
        {
            "label": "D – PCB Category",
            "fieldname": "pcb_category",
            "fieldtype": "Data",
            "width": 120,
        }
    )

    # Backward-compat aliases (keep old fieldnames so existing integrations don't break)
    cols += [
        {
            "label": "Total Gross (MYR)",
            "fieldname": "total_gross",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "EPF Employee (MYR)",
            "fieldname": "epf_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "SOCSO Employee (MYR)",
            "fieldname": "socso_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "EIS Employee (MYR)",
            "fieldname": "eis_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "PCB Total (MYR)",
            "fieldname": "pcb_total",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "Net Pay (MYR)",
            "fieldname": "net_pay",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
    ]

    return cols


def get_filters():
    current_year = frappe.utils.nowdate()[:4]
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
            "default": int(current_year),
            "reqd": 1,
        },
        {
            "fieldname": "employee",
            "label": "Employee",
            "fieldtype": "Link",
            "options": "Employee",
        },
    ]


def _build_conditions(filters):
    conditions = []
    values = {}

    year = filters.get("year")
    if year:
        conditions.append("YEAR(ss.start_date) = %(year)s")
        values["year"] = int(year)

    if filters.get("company"):
        conditions.append("ss.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("employee"):
        conditions.append("ss.employee = %(employee)s")
        values["employee"] = filters["employee"]

    conditions.append("ss.docstatus = 1")

    where = "WHERE " + " AND ".join(conditions)
    return where, values


def _get_deduction_by_flag(slip_names, flag_fieldname):
    """Sum deduction amounts for all components where the given Check flag = 1."""
    if not slip_names:
        return 0.0
    placeholders = ", ".join(["%s"] * len(slip_names))
    rows = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(sd.amount), 0) AS total
        FROM `tabSalary Detail` sd
        JOIN `tabSalary Component` sc ON sc.name = sd.salary_component
        WHERE sd.parent IN ({placeholders})
          AND sd.parenttype = 'Salary Slip'
          AND sd.parentfield = 'deductions'
          AND sc.`{flag_fieldname}` = 1
        """,
        slip_names,
    )
    return float(rows[0][0]) if rows else 0.0


def _get_deduction_by_name(slip_names, component_name):
    """Sum a deduction component by its exact salary_component name."""
    if not slip_names:
        return 0.0
    placeholders = ", ".join(["%s"] * len(slip_names))
    rows = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(sd.amount), 0) AS total
        FROM `tabSalary Detail` sd
        WHERE sd.parent IN ({placeholders})
          AND sd.parenttype = 'Salary Slip'
          AND sd.parentfield = 'deductions'
          AND sd.salary_component = %s
        """,
        slip_names + [component_name],
    )
    return float(rows[0][0]) if rows else 0.0


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    where, values = _build_conditions(filters)

    # ── Q1: Per-employee base data (net_pay, zakat, pcb_category, slip list) ──
    base_sql = f"""
        SELECT
            ss.employee,
            ss.employee_name,
            YEAR(ss.start_date)                AS year,
            COALESCE(e.custom_pcb_category, '1') AS pcb_category,
            COALESCE(e.custom_annual_zakat, 0)  AS annual_zakat,
            SUM(ss.net_pay)                     AS net_pay,
            GROUP_CONCAT(ss.name)               AS slip_names
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e ON e.name = ss.employee
        {where}
        GROUP BY ss.employee, ss.employee_name, YEAR(ss.start_date),
                 e.custom_pcb_category, e.custom_annual_zakat
        ORDER BY ss.employee_name
    """
    base_rows = frappe.db.sql(base_sql, values, as_dict=True)

    if not base_rows:
        return []

    # ── Section A: Company / Employer info ──
    company_data = frappe._dict()
    company_name_filter = filters.get("company")
    if company_name_filter:
        try:
            cdoc = frappe.db.get_value(
                "Company",
                company_name_filter,
                [
                    "company_name",
                    "custom_employer_e_number",
                    "custom_branch_code",
                    "city",
                    "country",
                ],
                as_dict=True,
            )
            if cdoc:
                company_data = cdoc
        except Exception:
            pass  # Company fields may not exist yet — leave blank

    # ── Q2: Earnings by ea_section per employee (Section B pivot) ──
    # Build filter values for the sub-query
    year_val = int(filters.get("year") or frappe.utils.nowdate()[:4])
    employee_filter = filters.get("employee")

    earnings_where_parts = [
        "sd.parenttype = 'Salary Slip'",
        "sd.parentfield = 'earnings'",
        "ss.docstatus = 1",
        f"YEAR(ss.start_date) = {year_val}",
    ]
    if company_name_filter:
        safe_company = company_name_filter.replace("'", "\\'")
        earnings_where_parts.append(f"ss.company = '{safe_company}'")
    if employee_filter:
        safe_emp = employee_filter.replace("'", "\\'")
        earnings_where_parts.append(f"ss.employee = '{safe_emp}'")

    earnings_where = " AND ".join(earnings_where_parts)

    earnings_sql = f"""
        SELECT
            ss.employee,
            COALESCE(sc.custom_ea_section, '') AS ea_section,
            SUM(sd.amount)                      AS total
        FROM `tabSalary Detail` sd
        JOIN `tabSalary Slip` ss ON sd.parent = ss.name
        LEFT JOIN `tabSalary Component` sc ON sc.name = sd.salary_component
        WHERE {earnings_where}
        GROUP BY ss.employee, sc.custom_ea_section
    """
    earnings_rows = frappe.db.sql(earnings_sql, as_dict=True)

    # Build {employee → {ea_section → total}} dict
    earnings_by_emp = {}
    for er in earnings_rows:
        emp = er.employee
        if emp not in earnings_by_emp:
            earnings_by_emp[emp] = {}
        earnings_by_emp[emp][er.ea_section or ""] = float(er.total or 0)

    # ── Q3: Deductions per employee (Section C) ──
    deductions_by_emp = {}
    for row in base_rows:
        slip_names = [s for s in (row.slip_names or "").split(",") if s]
        emp = row.employee
        deductions_by_emp[emp] = {
            "c1_epf":  _get_deduction_by_flag(slip_names, "custom_is_epf_employee"),
            "c2_socso": _get_deduction_by_name(slip_names, "SOCSO"),
            "c3_eis":   _get_deduction_by_name(slip_names, "EIS"),
            "c4_pcb":  _get_deduction_by_flag(slip_names, "custom_is_pcb_component"),
        }

    # ── Assemble final rows ──
    result = []
    for row in base_rows:
        emp = row.employee
        emp_earnings = earnings_by_emp.get(emp, {})
        emp_deductions = deductions_by_emp.get(emp, {})

        # Section B: B1–B11 from tagged earnings
        section_b = {}
        b_tagged_total = 0.0
        for opt, fn, _label in EA_SECTION_MAP:
            val = emp_earnings.get(opt, 0.0)
            section_b[fn] = val
            b_tagged_total += val

        # Untagged earnings go into b12 but not into any specific Bn bucket
        untagged = emp_earnings.get("", 0.0)
        b12 = b_tagged_total + untagged

        c1 = emp_deductions.get("c1_epf", 0.0)
        c2 = emp_deductions.get("c2_socso", 0.0)
        c3 = emp_deductions.get("c3_eis", 0.0)
        c4 = emp_deductions.get("c4_pcb", 0.0)
        c5 = float(row.annual_zakat or 0)

        result.append(
            frappe._dict(
                {
                    "employee":       emp,
                    "employee_name":  row.employee_name,
                    "year":           row.year,
                    # Section A
                    "company_name":        company_data.get("company_name", ""),
                    "employer_e_number":   company_data.get("custom_employer_e_number", ""),
                    "branch_code":         company_data.get("custom_branch_code", ""),
                    # Section B
                    **section_b,
                    "b12_total_gross": b12,
                    # Section C
                    "c1_epf":   c1,
                    "c2_socso": c2,
                    "c3_eis":   c3,
                    "c4_pcb":   c4,
                    "c5_zakat": c5,
                    # Section D
                    "pcb_category": row.get("pcb_category") or "1",
                    # Backward-compat aliases (keep old field names working)
                    "total_gross":    b12,
                    "epf_employee":   c1,
                    "socso_employee": c2,
                    "eis_employee":   c3,
                    "pcb_total":      c4,
                    "annual_zakat":   c5,
                    "net_pay":        float(row.net_pay or 0),
                }
            )
        )

    return result


def execute(filters=None):
    return get_columns(), get_data(filters)
