"""EC Form (Borang EC) Script Report — US-094.

ITA 1967 Section 83A — Borang EC is the government/statutory body equivalent of
EA Form. Statutory bodies, GLCs, and government-linked companies must issue EC
Forms instead of EA Forms. EC Form has the same structure but different headers
and field labels.

This report reuses the EA Form data pipeline and substitutes EC-specific labels.
"""
import frappe

from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form.ea_form import (
    EA_SECTION_MAP,
    get_data,
    get_filters,
)

EC_SECTION_MAP = [
    (opt, fn, label.replace("B", "EC-B", 1))
    for opt, fn, label in EA_SECTION_MAP
]


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
        # Section A — Employer (EC labels)
        {
            "label": "A – Employer Name (EC Form)",
            "fieldname": "company_name",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": "A – E-Number (EC Form)",
            "fieldname": "employer_e_number",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": "A – Branch Code (EC Form)",
            "fieldname": "branch_code",
            "fieldtype": "Data",
            "width": 120,
        },
    ]

    # Section B — EC-B1 to EC-B11 (same fieldnames, EC labels)
    for _opt, fn, label in EC_SECTION_MAP:
        cols.append(
            {
                "label": label,
                "fieldname": fn,
                "fieldtype": "Currency",
                "options": "MYR",
                "width": 160,
            }
        )

    # EC-B12 = sum of EC-B1–EC-B11 + untagged earnings
    cols.append(
        {
            "label": "EC-B12 – Total Gross Remuneration",
            "fieldname": "b12_total_gross",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 220,
        }
    )

    # Section C — Statutory Deductions (EC labels)
    cols += [
        {
            "label": "EC-C1 – EPF Employee (KWSP)",
            "fieldname": "c1_epf",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 170,
        },
        {
            "label": "EC-C2 – SOCSO Employee (PERKESO)",
            "fieldname": "c2_socso",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 190,
        },
        {
            "label": "EC-C3 – EIS Employee",
            "fieldname": "c3_eis",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "EC-C4 – PCB / MTD",
            "fieldname": "c4_pcb",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "EC-C5 – Zakat",
            "fieldname": "c5_zakat",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
        },
    ]

    # Gratuity Exemption
    cols.append(
        {
            "label": "EC-B5 – Gratuity Exempt (Sch.6 Para 30)",
            "fieldname": "b5_gratuity_exempt",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 210,
        }
    )

    # Section D — Tax Position
    cols.append(
        {
            "label": "EC-D – PCB Category",
            "fieldname": "pcb_category",
            "fieldtype": "Data",
            "width": 130,
        }
    )

    return cols


def execute(filters=None):
    return get_columns(), get_data(filters)
