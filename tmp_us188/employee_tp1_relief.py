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

  YA2025 and later (Budget 2025 + PCB 2025 Spec Amendment):
    All YA2024 caps unchanged, plus:
    disability_self              : RM 7,000  (raised from RM 6,000)
    disability_spouse            : RM 6,000  (raised from RM 5,000)
    housing_loan_interest_500k   : RM 7,000  (NEW — first home ≤RM500K)
    housing_loan_interest_750k   : RM 5,000  (NEW — first home RM500K–RM750K)
    housing_loan SPA date must be between 1 Jan 2025 and 31 Dec 2027 (sunset clause)
    food_waste_composting_machine: RM 2,500  (NEW — PCB 2025 spec amendment, permanent)

  YA2026 and later (TP1(1/2026) Budget 2026 changes):
    All YA2025 caps unchanged, plus:
    children_life_medical_insurance : RM 3,000  (NEW — children life/medical ins.)
    childcare_fees_extended         : RM 3,000  (NEW — ages 6–12 after-school care)
    domestic_tourism                : RM 1,000  (NEW — tourism/cultural attraction,
                                                  YA2026–2027 only, expires 31 Dec 2027)
    vaccine_relief                  : no cap    (NEW — any NPRA-approved vaccine)
    child_relief_autism_oku         : RM 10,000 (NEW — autism/learning disability child,
                                                  raised from RM 6,000 per child)
    Note: children_life_medical_insurance shares the combined RM 3,000 cap with
    life_insurance (both draw from the same ITA insurance relief pool).

EPF i-Topup Combined Relief Cap (US-117):
    voluntary_epf_itopup    : RM 3,000 individual cap
    BUT: life_insurance + children_life_medical_insurance + voluntary_epf_itopup
         combined <= RM 3,000 (shared sub-cap, YA2026+)
    AND: epf_employee (mandatory, RM 4,000) + life_insurance +
         children_life_medical_insurance + voluntary_epf_itopup <= RM 7,000
    This mirrors the KWSP/ITA 1967 relief structure:
      - ITA Section C: mandatory EPF → RM 4,000 relief
      - ITA Section C continuation: EPF voluntary + life insurance → RM 3,000 combined
      - Total EPF + life insurance relief: RM 7,000 maximum

Domestic Tourism Expiry (YA2026–2027 sunset):
    domestic_tourism field may only be claimed for tax_year 2026 and 2027.
    If tax_year > 2027, any domestic_tourism amount is rejected with an error.
    This implements the LHDN time-bounded budget measure effective
    from 1 January 2026 and expiring 31 December 2027.

Fields without caps (caller-supplied figures accepted as-is):
    self_relief, spouse_relief, child_relief_normal, child_relief_disabled,
    socso_employee, annual_zakat (zakat is a tax rebate, not a relief)
    vaccine_relief (YA2026+, no LHDN cap — any NPRA-approved vaccine qualifies)
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
    "voluntary_epf_itopup": 3_000,
    "disability_self": 6_000,
    "disability_spouse": 5_000,
}

# YA2025 caps — Budget 2025 updates + PCB 2025 Spec Amendment
_CAPS_YA2025 = {
    **_CAPS_DEFAULT,
    # Increased disability reliefs (OKU) per PCB 2025 spec amendment
    "disability_self": 7_000,
    "disability_spouse": 6_000,
    # New housing loan interest relief (sunset: SPA 1 Jan 2025 – 31 Dec 2027)
    "housing_loan_interest_500k": 7_000,
    "housing_loan_interest_750k": 5_000,
    # Food waste composting machine (permanent cap, PCB 2025 spec amendment)
    "food_waste_composting_machine": 2_500,
}

# YA2026 caps — TP1(1/2026) Budget 2026 updates
_CAPS_YA2026 = {
    **_CAPS_YA2025,
    # Children's life/medical insurance (NEW — shares combined insurance pool)
    "children_life_medical_insurance": 3_000,
    # Extended childcare for ages 6-12 in Ministry of Education-registered
    # after-school care programmes (previously only age ≤6)
    "childcare_fees_extended": 3_000,
    # Domestic tourism and cultural attraction (YA2026-2027 only, time-bounded)
    "domestic_tourism": 1_000,
    # Autism/learning disability child relief (raised from RM6,000 to RM10,000)
    "child_relief_autism_oku": 10_000,
    # vaccine_relief: no cap — any NPRA-approved vaccine qualifies (no hardcoded list)
    # Intentionally excluded from cap table; unlimited field validated separately
}

# Map of assessment year → caps dict.
# Years not explicitly listed fall back to _CAPS_DEFAULT.
_CAPS_BY_YEAR = {
    2025: _CAPS_YA2025,
    2026: _CAPS_YA2026,
}

# Backward-compat alias used by existing tests (points to _CAPS_DEFAULT)
_CAPS = _CAPS_DEFAULT

# Combined relief cap: life_insurance + children_life_medical_insurance (YA2026+)
# + voluntary_epf_itopup <= this limit
_LIFE_VOLUNTARY_EPF_COMBINED_CAP = 3_000

# Domestic tourism sunset: may not be applied after 31 December 2027
_DOMESTIC_TOURISM_EXPIRY_YEAR = 2027

# YA2026 first effective year — fields below are only available from this year
_YA2026_EFFECTIVE_YEAR = 2026


def _get_caps_for_year(year: int) -> dict:
    """Return the LHDN TP1 cap table for the given assessment year.

    Years >= 2026 use YA2026 caps. Year 2025 uses YA2025 caps.
    All earlier years use the default (YA2024) caps.
    This ensures historical PCB calculations are not affected by future Budget changes.
    """
    year = int(year)
    if year >= 2026:
        return _CAPS_BY_YEAR.get(year, _CAPS_YA2026)
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
    "child_relief_autism_oku",       # YA2026+ — autism/learning disability child
    "life_insurance",
    "children_life_medical_insurance", # YA2026+ — children's life/medical insurance
    "medical_insurance",
    "education_fees_self",
    "sspn",
    "childcare_fees",
    "childcare_fees_extended",       # YA2026+ — ages 6-12 after-school care
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
    "voluntary_epf_itopup",
    "domestic_tourism",              # YA2026-2027 only — time-bounded
    "vaccine_relief",                # YA2026+ — any NPRA-approved vaccine
    "food_waste_composting_machine", # YA2025+ — PCB 2025 spec amendment, permanent RM2,500
]


class EmployeeTP1Relief(Document):
    """Controller for the Employee TP1 Relief DocType."""

    def validate(self):
        self._enforce_unique_per_year()
        self._zero_ya2026_fields_for_pre_2026()
        self._apply_caps()
        self._apply_life_voluntary_epf_combined_cap()
        self._validate_spa_date()
        self._validate_domestic_tourism_expiry()
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

    def _zero_ya2026_fields_for_pre_2026(self):
        """Clear YA2026-only fields when tax_year < 2026.

        Prevents accidental data entry for fields that did not exist before YA2026.
        """
        year = int(self.tax_year or 2024)
        if year >= _YA2026_EFFECTIVE_YEAR:
            return

        ya2026_fields = [
            "children_life_medical_insurance",
            "childcare_fees_extended",
            "domestic_tourism",
            "vaccine_relief",
            "child_relief_autism_oku",
        ]
        for field in ya2026_fields:
            val = float(self.get(field) or 0)
            if val != 0:
                frappe.msgprint(
                    _("{0} is only available from YA2026 onwards. Value cleared for tax year {1}.").format(
                        self.meta.get_label(field), year
                    ),
                    indicator="orange",
                    alert=True,
                )
                self.set(field, 0)

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

    def _apply_life_voluntary_epf_combined_cap(self):
        """Enforce RM 3,000 combined cap on life_insurance + children_life_medical_insurance
        + voluntary_epf_itopup.

        Per ITA 1967, voluntary EPF (i-Topup) and life/children's insurance premiums share
        a single RM 3,000 additional relief pool. YA2026 adds children_life_medical_insurance
        to this pool.

        Trimming priority: voluntary EPF first, then children_life_medical_insurance,
        then life insurance (life insurance takes highest priority).

        This ensures the overall RM 7,000 EPF+life cap is honoured:
            mandatory EPF (RM 4,000) + [life + children_life + voluntary EPF] (RM 3,000)
            = RM 7,000.
        """
        life = float(self.get("life_insurance") or 0)
        children_life = float(self.get("children_life_medical_insurance") or 0)
        voluntary = float(self.get("voluntary_epf_itopup") or 0)
        combined = life + children_life + voluntary
        if combined <= _LIFE_VOLUNTARY_EPF_COMBINED_CAP:
            return

        excess = combined - _LIFE_VOLUNTARY_EPF_COMBINED_CAP
        # Trim voluntary EPF first (lowest priority)
        trim_voluntary = min(excess, voluntary)
        self.voluntary_epf_itopup = max(0.0, voluntary - trim_voluntary)
        excess -= trim_voluntary

        if excess > 0:
            # Trim children_life_medical_insurance second
            trim_children = min(excess, children_life)
            self.children_life_medical_insurance = max(0.0, children_life - trim_children)
            excess -= trim_children

        if excess > 0:
            # Trim life insurance last
            self.life_insurance = max(0.0, life - excess)

        frappe.msgprint(
            _(
                "Life Insurance + Children Life/Medical Insurance + Voluntary EPF (i-Topup) "
                "combined relief capped at RM {0:,.0f} (declared: RM {1:,.2f}). "
                "Adjusted: Life RM {2:,.2f}, Children Ins. RM {3:,.2f}, Voluntary EPF RM {4:,.2f}."
            ).format(
                _LIFE_VOLUNTARY_EPF_COMBINED_CAP,
                combined,
                float(self.life_insurance or 0),
                float(self.get("children_life_medical_insurance") or 0),
                float(self.voluntary_epf_itopup or 0),
            ),
            indicator="orange",
            alert=True,
        )

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

    def _validate_domestic_tourism_expiry(self):
        """Domestic tourism relief expires after 31 December 2027 (YA2026-2027 only).

        This is the LHDN time-bounded measure effective 1 Jan 2026. Any domestic_tourism
        amount claimed for tax_year > 2027 is rejected with a clear error message.
        For tax_year < 2026, the amount is cleared (handled by _zero_ya2026_fields_for_pre_2026).
        """
        amount = float(self.get("domestic_tourism") or 0)
        if amount <= 0:
            return

        year = int(self.tax_year or 2024)
        if year > _DOMESTIC_TOURISM_EXPIRY_YEAR:
            frappe.throw(
                _(
                    "Domestic Tourism and Cultural Attraction relief (RM {0:,.0f}) "
                    "is only available for tax years 2026 and 2027 "
                    "(LHDN time-bounded measure, expires 31 December 2027). "
                    "Current tax year: {1}"
                ).format(amount, year),
                title=_("Domestic Tourism Relief Expired"),
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
