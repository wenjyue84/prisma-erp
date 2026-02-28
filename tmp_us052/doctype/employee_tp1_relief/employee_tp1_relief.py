"""Employee TP1 Relief DocType controller.

Implements LHDN Borang TP1 — the employee relief declaration form that reduces
monthly PCB/MTD by declaring reliefs beyond the standard personal and child relief.

Each employee may have at most ONE active TP1 record per tax year. The document
is validated to enforce per-category LHDN caps and a unique (employee, tax_year)
constraint.

Relief caps per LHDN TP1 form:
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

Fields without caps (caller-supplied figures accepted as-is):
    self_relief, spouse_relief, child_relief_normal, child_relief_disabled,
    disability_self, socso_employee, annual_zakat (zakat is a tax rebate, not a relief)
"""
import frappe
from frappe import _
from frappe.model.document import Document

# Per-field ceiling caps for LHDN TP1 (RM)
_CAPS = {
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
}

# Fields that contribute to total_reliefs (annual_zakat is a separate tax rebate)
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
    "disability_self",
    "socso_employee",
    "epf_employee",
]


class EmployeeTP1Relief(Document):
    """Controller for the Employee TP1 Relief DocType."""

    def validate(self):
        self._enforce_unique_per_year()
        self._apply_caps()
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
        """Silently cap each field to the LHDN maximum and warn the user."""
        for fieldname, cap in _CAPS.items():
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
