"""EC Form (Borang EC) Script Report — US-094.

ITA 1967 Section 83A — Borang EC is the government/statutory body equivalent
of Borang EA. Statutory bodies, GLCs, and government-linked companies must issue
EC Forms instead of EA Forms. The structure is identical to EA Form but with
EC-specific header text and labels.

EC Form headers differ from EA Form:
- Report title: "EC Form" instead of "EA Form"
- Section A label: "Employer (Statutory Body / Government)" vs "Employer"
- Statutory employer flag: Company.custom_is_statutory_employer
"""
from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form.ea_form import (
    get_columns as _ea_get_columns,
    get_data as _ea_get_data,
)

# EC Form title used in header rows / column labels
EC_FORM_TITLE = "EC Form (Borang EC)"
EA_FORM_TITLE = "EA Form (Borang EA)"

# EC-specific Section A label override
EC_SECTION_A_LABEL = "A – Employer (Statutory Body / Government)"
EA_SECTION_A_LABEL = "A – Employer Name"


def get_columns():
    """Return EC Form columns, substituting EC-specific label for Section A."""
    cols = _ea_get_columns()
    for col in cols:
        if col.get("label") == EA_SECTION_A_LABEL:
            col["label"] = EC_SECTION_A_LABEL
    return cols


def get_data(filters=None):
    """Return EC Form data using the same logic as EA Form."""
    return _ea_get_data(filters)


def execute(filters=None):
    return get_columns(), get_data(filters)
