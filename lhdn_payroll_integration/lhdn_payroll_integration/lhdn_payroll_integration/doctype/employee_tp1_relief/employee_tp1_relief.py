"""Employee TP1 Relief DocType controller.

Implements LHDN Borang TP1 — the employee relief declaration form that reduces
monthly PCB/MTD by declaring reliefs beyond the standard personal and child relief.

Each employee may have at most ONE active TP1 record per tax year. The document
is validated to enforce per-category LHDN caps (version-controlled by assessment
year) and a unique (employee, tax_year) constraint.

Relief caps — version-controlled by Assessment Year (YA):

  YA2024 and earlier:
    life_insurance          : RM 3,000
    medical_insurance       : RM 3,000
    education_fees_self     : RM 7,000
    sspn                    : RM 8,000
    childcare_fees          : RM 3,000
    lifestyle_expenses      : RM 2,500
    prs_contribution        : RM 3,000
    serious_illness_expenses: RM 10,000
    parents_medical         : RM 8,000
    epf_employee            : RM 4,000
    disability_self         : RM 6,000
    disability_spouse       : RM 5,000

  YA2025 and later (Budget 2025 changes):
    All YA2024 caps unchanged, plus:
    disability_self              : RM 7,000  (raised from RM 6,000)
    disability_spouse            : RM 6,000  (raised from RM 5,000)
    housing_loan_interest_500k   : RM 7,000  (NEW — first home ≤RM500K)
    housing_loan_interest_750k   : RM 5,000  (NEW — first home RM500K–RM750K)
    housing_loan SPA date must be between 1 Jan 2025 and 31 Dec 2027 (sunset clause)

Fields without caps (caller-supplied figures accepted as-is):
    self_relief, spouse_relief, child_relief_normal, child_relief_disabled,
    socso_employee, annual_zakat (zakat is a tax rebate, not a relief)
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

# ---------------------------------------------------------------------------
# Year-versioned cap tables
# ---------------------------------------------------------------------------

# Default caps (YA2024 and earlier)
_CAPS_DEFAULT = {
    "life_insurance": 3_000,
    "medical_insurance": 3_000,
    "education_fees_self": 7_000,
    "sspn": 8_000,
    "childcare_fees": 3_000,
    "lifestyle_expenses": 2_500,
    "prs_contribution": 3_000,
    "serious_illness_expenses": 10_000,
    "parents_medical": 8_000,
    "epf_employee": 4_000,
    "disability_self": 6_000,
    "disability_spouse": 5_000,
}

# YA2025 caps — Budget 2025 updates
_CAPS_YA2025 = {
    **_CAPS_DEFAULT,
    # Increased disability reliefs
    "disability_self": 7_000,
    "disability_spouse": 6_000,
    # New housing loan interest relief (sunset: SPA 1 Jan 2025 – 31 Dec 2027)
    "housing_loan_interest_500k": 7_000,
    "housing_loan_interest_750k": 5_000,
}

# Map of assessment year → caps dict.
# Years not explicitly listed fall back to _CAPS_DEFAULT.
_CAPS_BY_YEAR = {
    2025: _CAPS_YA2025,
}

# Backward-compat alias used by existing tests (points to _CAPS_DEFAULT)
_CAPS = _CAPS_DEFAULT


def _get_caps_for_year(year: int) -> dict:
    """Return the LHDN TP1 cap table for the given assessment year.

    Years >= 2025 use YA2025 caps. All earlier years use the default (YA2024) caps.
    This ensures historical PCB calculations are not affected by future Budget changes.
    """
    year = int(year)
    if year >= 2025:
        return _CAPS_BY_YEAR.get(year, _CAPS_YA2025)
    return _CAPS_DEFAULT


# ---------------------------------------------------------------------------
# Relief fields that contribute to total_reliefs (annual_zakat is excluded —
# it is a ringgit-for-ringgit tax rebate handled separately in PCB)
# ---------------------------------------------------------------------------

_RELIEF_FIELDS = [
    "self_relief",
    "spouse_relief",
    "child_relief_normal",
    "child_relief_disabled",
    "life_insurance",
    "medical_insurance",
    "education_fees_self",
    "sspn",
    "childcare_fees",
    "lifestyle_expenses",
    "prs_contribution",
    "serious_illness_expenses",
    "parents_medical",
    "housing_loan_interest_500k",
    "housing_loan_interest_750k",
    "disability_self",
    "disability_spouse",
    "socso_employee",
    "epf_employee",
]


class EmployeeTP1Relief(Document):
    """Controller for the Employee TP1 Relief DocType."""

    def validate(self):
        self._enforce_unique_per_year()
        self._apply_caps()
        self._validate_spa_date()
        self._calculate_total()

    def _enforce_unique_per_year(self):
        """Ensure at most one TP1 record per employee per tax year."""
        existing = frappe.db.get_value(
            "Employee TP1 Relief",
            {"employee": self.employee, "tax_year": self.tax_year, "name": ("!=", self.name)},
            "name",
        )
        if existing:
            frappe.throw(
                _(
                    "An Employee TP1 Relief record already exists for {0} in tax year {1}: {2}"
                ).format(self.employee, self.tax_year, existing),
                title=_("Duplicate TP1 Record"),
            )

    def _apply_caps(self):
        """Silently cap each field to the LHDN maximum for the declaration year and warn the user."""
        year = int(self.tax_year or 2024)
        caps = _get_caps_for_year(year)
        for fieldname, cap in caps.items():
            raw = float(self.get(fieldname) or 0)
            if raw > cap:
                frappe.msgprint(
                    _("{0} capped at RM {1:,.0f} (declared: RM {2:,.0f})").format(
                        self.meta.get_label(fieldname), cap, raw
                    ),
                    indicator="orange",
                    alert=True,
                )
                self.set(fieldname, cap)

    def _validate_spa_date(self):
        """Housing loan interest relief requires SPA date between 1 Jan 2025 and 31 Dec 2027.

        This is the Budget 2025 sunset clause. If either housing loan interest field is
        non-zero, an SPA date must be provided and must fall within the qualifying window.
        Housing loan interest fields only apply for YA2025+; for earlier years they must be 0.
        """
        has_housing = (
            float(self.get("housing_loan_interest_500k") or 0) > 0
            or float(self.get("housing_loan_interest_750k") or 0) > 0
        )
        if not has_housing:
            return

        year = int(self.tax_year or 2024)
        if year < 2025:
            frappe.throw(
                _(
                    "Housing Loan Interest relief (Budget 2025) is only available for "
                    "assessment year 2025 and later. Current tax year: {0}"
                ).format(year),
                title=_("Invalid Relief Year"),
            )

        if not self.spa_date:
            frappe.throw(
                _("SPA Date is required when claiming Housing Loan Interest relief."),
                title=_("Missing SPA Date"),
            )

        spa = getdate(self.spa_date)
        min_date = getdate("2025-01-01")
        max_date = getdate("2027-12-31")
        if spa < min_date or spa > max_date:
            frappe.throw(
                _(
                    "Housing Loan Interest relief is only available for SPA dated between "
                    "1 Jan 2025 and 31 Dec 2027 (Budget 2025 sunset clause). "
                    "SPA date provided: {0}"
                ).format(self.spa_date),
                title=_("Invalid SPA Date"),
            )

    def _calculate_total(self):
        """Sum all relief fields (excl. Zakat) into total_reliefs."""
        total = sum(float(self.get(f) or 0) for f in _RELIEF_FIELDS)
        self.total_reliefs = total


@frappe.whitelist()
def get_employee_tp1_reliefs(employee: str, tax_year: int) -> dict:
    """Return the total TP1 reliefs for an employee in a given tax year.

    Looks up the Employee TP1 Relief record for (employee, tax_year).
    Returns a dict with ``total_reliefs`` (float) and ``annual_zakat`` (float).
    Both are 0.0 when no TP1 record exists.

    Args:
        employee: Employee document name.
        tax_year: Assessment year (int or str coercible to int).

    Returns:
        dict:
            - total_reliefs (float): Sum of all capped TP1 relief fields (excl. Zakat).
            - annual_zakat (float): Zakat amount for ringgit-for-ringgit rebate.
            - docname (str | None): Name of the TP1 record, or None if not found.
    """
    tax_year = int(tax_year)
    doc_name = frappe.db.get_value(
        "Employee TP1 Relief",
        {"employee": employee, "tax_year": tax_year},
        "name",
    )
    if not doc_name:
        return {"total_reliefs": 0.0, "annual_zakat": 0.0, "docname": None}

    doc = frappe.get_doc("Employee TP1 Relief", doc_name)
    return {
        "total_reliefs": float(doc.total_reliefs or 0),
        "annual_zakat": float(doc.annual_zakat or 0),
        "docname": doc_name,
    }
