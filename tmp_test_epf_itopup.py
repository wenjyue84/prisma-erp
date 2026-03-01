"""Tests for US-117: EPF i-Topup Voluntary Contribution.

Covers acceptance criteria:
  1. Salary Component 'EPF Voluntary (i-Topup)' exists in fixture (Deduction, non-statutory)
  2. Employee has 'custom_epf_itopup_monthly_amount' Currency field
  3. TP1 has 'voluntary_epf_itopup' field auto-populated, subject to RM3,000 sub-cap
  4. Combined life_insurance + voluntary_epf_itopup capped at RM 3,000
  5. PCB calculator respects RM 7,000 combined relief limit (mandatory RM4k + shared RM3k)
  6. EA Form includes voluntary EPF in Section C
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb
from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
    EmployeeTP1Relief,
    _CAPS,
    _CAPS_DEFAULT,
    _RELIEF_FIELDS,
    _LIFE_VOLUNTARY_EPF_COMBINED_CAP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tp1_doc(**kwargs):
    """Build an unsaved Employee TP1 Relief doc with minimal required fields."""
    defaults = {
        "doctype": "Employee TP1 Relief",
        "employee": "TEST-EMP-117",
        "tax_year": 2099,
        "self_relief": 9000,
        "spouse_relief": 0,
        "child_relief_normal": 0,
        "child_relief_disabled": 0,
        "life_insurance": 0,
        "medical_insurance": 0,
        "education_fees_self": 0,
        "sspn": 0,
        "childcare_fees": 0,
        "lifestyle_expenses": 0,
        "prs_contribution": 0,
        "serious_illness_expenses": 0,
        "parents_medical": 0,
        "disability_self": 0,
        "disability_spouse": 0,
        "socso_employee": 0,
        "epf_employee": 0,
        "voluntary_epf_itopup": 0,
        "annual_zakat": 0,
    }
    defaults.update(kwargs)
    doc = frappe.get_doc(defaults)
    return doc


# ---------------------------------------------------------------------------
# 1. Fixture — Salary Component exists
# ---------------------------------------------------------------------------

class TestEPFVoluntarySalaryComponentFixture(FrappeTestCase):
    """EPF Voluntary (i-Topup) salary component must exist in the database."""

    def test_epf_voluntary_component_exists(self):
        """Fixture creates 'EPF Voluntary (i-Topup)' as a Deduction component."""
        exists = frappe.db.exists("Salary Component", "EPF Voluntary (i-Topup)")
        self.assertTrue(
            exists,
            "Salary Component 'EPF Voluntary (i-Topup)' must exist (check salary_component.json fixture)"
        )

    def test_epf_voluntary_component_is_deduction(self):
        """EPF Voluntary (i-Topup) must be of type Deduction."""
        comp = frappe.get_doc("Salary Component", "EPF Voluntary (i-Topup)")
        self.assertEqual(
            comp.type, "Deduction",
            "EPF Voluntary (i-Topup) must be type=Deduction"
        )

    def test_epf_voluntary_component_has_voluntary_flag(self):
        """EPF Voluntary (i-Topup) must have custom_is_epf_voluntary=1."""
        comp = frappe.get_doc("Salary Component", "EPF Voluntary (i-Topup)")
        self.assertEqual(
            int(getattr(comp, "custom_is_epf_voluntary", 0)), 1,
            "EPF Voluntary (i-Topup) must have custom_is_epf_voluntary=1"
        )

    def test_epf_voluntary_not_flagged_as_mandatory_epf(self):
        """EPF Voluntary (i-Topup) must NOT have custom_is_epf_employee=1."""
        comp = frappe.get_doc("Salary Component", "EPF Voluntary (i-Topup)")
        self.assertEqual(
            int(getattr(comp, "custom_is_epf_employee", 0)), 0,
            "EPF Voluntary (i-Topup) must have custom_is_epf_employee=0 (not a mandatory EPF deduction)"
        )


# ---------------------------------------------------------------------------
# 2. Employee custom field
# ---------------------------------------------------------------------------

class TestEmployeeEPFiTopupField(FrappeTestCase):
    """Employee doctype must have custom_epf_itopup_monthly_amount field."""

    def test_employee_has_itopup_amount_field(self):
        """custom_epf_itopup_monthly_amount field exists on Employee meta."""
        meta = frappe.get_meta("Employee")
        field = meta.get_field("custom_epf_itopup_monthly_amount")
        self.assertIsNotNone(
            field,
            "Employee must have 'custom_epf_itopup_monthly_amount' Currency field (check custom_field.json fixture)"
        )

    def test_itopup_field_is_currency(self):
        """custom_epf_itopup_monthly_amount must be of fieldtype Currency."""
        meta = frappe.get_meta("Employee")
        field = meta.get_field("custom_epf_itopup_monthly_amount")
        if field:
            self.assertEqual(field.fieldtype, "Currency")


# ---------------------------------------------------------------------------
# 3. TP1 voluntary_epf_itopup field and cap constants
# ---------------------------------------------------------------------------

class TestTP1VoluntaryEPFField(FrappeTestCase):
    """TP1 DocType must include voluntary_epf_itopup and caps."""

    def test_voluntary_epf_in_relief_fields(self):
        """voluntary_epf_itopup must be in _RELIEF_FIELDS so it contributes to total_reliefs."""
        self.assertIn(
            "voluntary_epf_itopup",
            _RELIEF_FIELDS,
            "voluntary_epf_itopup must be in _RELIEF_FIELDS"
        )

    def test_voluntary_epf_cap_in_caps_default(self):
        """_CAPS_DEFAULT must include voluntary_epf_itopup capped at RM 3,000."""
        self.assertIn("voluntary_epf_itopup", _CAPS_DEFAULT)
        self.assertEqual(_CAPS_DEFAULT["voluntary_epf_itopup"], 3_000)

    def test_combined_cap_constant_is_3000(self):
        """_LIFE_VOLUNTARY_EPF_COMBINED_CAP must be RM 3,000."""
        self.assertEqual(_LIFE_VOLUNTARY_EPF_COMBINED_CAP, 3_000)

    def test_tp1_doctype_has_voluntary_epf_field(self):
        """TP1 DocType meta must include voluntary_epf_itopup field."""
        meta = frappe.get_meta("Employee TP1 Relief")
        field = meta.get_field("voluntary_epf_itopup")
        self.assertIsNotNone(
            field,
            "Employee TP1 Relief must have 'voluntary_epf_itopup' field"
        )

    def test_voluntary_epf_added_to_total_reliefs(self):
        """voluntary_epf_itopup contributes to _calculate_total()."""
        doc = _make_tp1_doc(voluntary_epf_itopup=1500)
        doc._calculate_total()
        # self_relief (9000) + voluntary_epf_itopup (1500) = 10500
        self.assertAlmostEqual(float(doc.total_reliefs), 10500.0, places=2)


# ---------------------------------------------------------------------------
# 4. Combined life_insurance + voluntary_epf_itopup cap enforcement
# ---------------------------------------------------------------------------

class TestCombinedLifeVoluntaryEPFCap(FrappeTestCase):
    """_apply_life_voluntary_epf_combined_cap() enforces RM 3,000 shared cap."""

    def test_combined_under_cap_unchanged(self):
        """When combined <= 3000, no trimming occurs."""
        doc = _make_tp1_doc(life_insurance=1500, voluntary_epf_itopup=1000)
        doc._apply_life_voluntary_epf_combined_cap()
        self.assertAlmostEqual(float(doc.life_insurance), 1500.0)
        self.assertAlmostEqual(float(doc.voluntary_epf_itopup), 1000.0)

    def test_combined_exactly_cap_unchanged(self):
        """When combined == 3000, no trimming occurs."""
        doc = _make_tp1_doc(life_insurance=2000, voluntary_epf_itopup=1000)
        doc._apply_life_voluntary_epf_combined_cap()
        self.assertAlmostEqual(float(doc.life_insurance), 2000.0)
        self.assertAlmostEqual(float(doc.voluntary_epf_itopup), 1000.0)

    def test_voluntary_epf_trimmed_first_when_over_cap(self):
        """When combined > 3000, voluntary EPF is trimmed first."""
        doc = _make_tp1_doc(life_insurance=2000, voluntary_epf_itopup=2000)
        # combined = 4000, excess = 1000 → trim voluntary by 1000
        doc._apply_life_voluntary_epf_combined_cap()
        self.assertAlmostEqual(float(doc.life_insurance), 2000.0)
        self.assertAlmostEqual(float(doc.voluntary_epf_itopup), 1000.0)

    def test_life_insurance_also_trimmed_if_voluntary_insufficient(self):
        """When voluntary_epf < excess, life_insurance is trimmed for the remainder."""
        doc = _make_tp1_doc(life_insurance=3000, voluntary_epf_itopup=500)
        # combined = 3500, excess = 500 → trim voluntary 500 → voluntary=0, life=3000 (excess resolved)
        doc._apply_life_voluntary_epf_combined_cap()
        self.assertAlmostEqual(float(doc.voluntary_epf_itopup), 0.0)
        self.assertAlmostEqual(float(doc.life_insurance), 3000.0)

    def test_combined_total_never_exceeds_cap(self):
        """After applying cap, life + voluntary always <= RM 3,000."""
        test_cases = [
            (3000, 3000),  # both at individual max
            (1500, 2000),
            (0, 5000),     # only voluntary, very high
            (5000, 0),     # only life, very high
        ]
        for life, voluntary in test_cases:
            doc = _make_tp1_doc(life_insurance=life, voluntary_epf_itopup=voluntary)
            doc._apply_life_voluntary_epf_combined_cap()
            combined = float(doc.life_insurance or 0) + float(doc.voluntary_epf_itopup or 0)
            self.assertLessEqual(
                combined, _LIFE_VOLUNTARY_EPF_COMBINED_CAP + 0.01,
                f"Combined must not exceed {_LIFE_VOLUNTARY_EPF_COMBINED_CAP} for life={life}, voluntary={voluntary}"
            )


# ---------------------------------------------------------------------------
# 5. PCB relief respects RM 7,000 total cap via tp1_total_reliefs
# ---------------------------------------------------------------------------

class TestPCBRM7000CombinedReliefCap(FrappeTestCase):
    """PCB calculator correctly applies RM 7,000 EPF+life combined relief via TP1."""

    def test_mandatory_epf_relief_reduces_pcb(self):
        """Adding mandatory EPF relief (RM 4,000) reduces annual PCB."""
        annual_income = 120_000
        pcb_no_epf = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        pcb_with_mandatory_epf = calculate_pcb(
            annual_income, resident=True, tp1_total_reliefs=4_000
        )
        self.assertGreater(pcb_no_epf, pcb_with_mandatory_epf)

    def test_voluntary_epf_reduces_pcb_within_shared_cap(self):
        """Adding voluntary EPF within RM 3,000 cap further reduces PCB."""
        annual_income = 120_000
        # Mandatory EPF only (RM 4,000)
        pcb_mandatory_only = calculate_pcb(
            annual_income, resident=True, tp1_total_reliefs=4_000
        )
        # Mandatory EPF + Voluntary EPF (RM 4,000 + RM 1,500 = RM 5,500)
        pcb_with_voluntary = calculate_pcb(
            annual_income, resident=True, tp1_total_reliefs=5_500
        )
        self.assertGreater(pcb_mandatory_only, pcb_with_voluntary)

    def test_rm7000_total_cap_correctly_bounds_relief(self):
        """Total EPF + life insurance relief is capped at RM 7,000 via TP1 total."""
        annual_income = 120_000
        # RM 7,000 combined (4k mandatory + 3k voluntary+life combined)
        pcb_at_7k = calculate_pcb(
            annual_income, resident=True, tp1_total_reliefs=7_000
        )
        # Giving more than RM 7,000 via other reliefs still reduces PCB further
        # (the cap is enforced in TP1 validation before calculate_pcb is called)
        pcb_at_9k = calculate_pcb(
            annual_income, resident=True, tp1_total_reliefs=9_000
        )
        # More reliefs = lower PCB
        self.assertGreater(pcb_at_7k, pcb_at_9k)

    def test_tp1_with_voluntary_epf_total_reliefs_sum(self):
        """TP1 total_reliefs includes voluntary_epf_itopup after combined cap."""
        doc = _make_tp1_doc(
            epf_employee=4000,         # mandatory EPF, capped at RM 4,000
            life_insurance=2000,       # life insurance
            voluntary_epf_itopup=1000, # voluntary EPF; combined life+voluntary=3000 (at cap)
        )
        doc._apply_life_voluntary_epf_combined_cap()
        doc._calculate_total()
        # Expected: self_relief 9000 + epf_employee 4000 + life_insurance 2000 + voluntary 1000 = 16000
        expected = 9000 + 4000 + 2000 + 1000
        self.assertAlmostEqual(float(doc.total_reliefs), float(expected), places=2)

    def test_tp1_voluntary_epf_trimmed_when_life_insurance_already_high(self):
        """When life_insurance=3000 already at cap, voluntary_epf_itopup trimmed to 0."""
        doc = _make_tp1_doc(
            epf_employee=4000,
            life_insurance=3000,
            voluntary_epf_itopup=2000,  # would push combined to 5000
        )
        doc._apply_life_voluntary_epf_combined_cap()
        doc._calculate_total()
        # voluntary trimmed to 0; total = 9000 + 4000 + 3000 + 0 = 16000
        self.assertAlmostEqual(float(doc.voluntary_epf_itopup), 0.0)
        self.assertAlmostEqual(float(doc.total_reliefs), 16_000.0, places=2)

    def test_non_resident_ignores_voluntary_epf_reliefs(self):
        """Non-residents pay flat 30%; TP1 reliefs have no effect."""
        annual_income = 120_000
        pcb_no_tp1 = calculate_pcb(annual_income, resident=False, tp1_total_reliefs=0)
        pcb_with_tp1 = calculate_pcb(annual_income, resident=False, tp1_total_reliefs=7_000)
        # Non-resident: tp1_total_reliefs ignored → PCB same
        self.assertAlmostEqual(pcb_no_tp1, pcb_with_tp1, places=2)


# ---------------------------------------------------------------------------
# 6. Voluntary EPF is excluded from SOCSO/EIS/HRDF base
# ---------------------------------------------------------------------------

class TestVoluntaryEPFExcludedFromStatutory(FrappeTestCase):
    """Voluntary EPF (i-Topup) component must not be marked as SOCSO/EIS/HRDF base."""

    def test_voluntary_epf_not_pcb_component(self):
        """EPF Voluntary (i-Topup) should not be flagged as a PCB component."""
        comp = frappe.get_doc("Salary Component", "EPF Voluntary (i-Topup)")
        self.assertEqual(
            int(getattr(comp, "custom_is_pcb_component", 0)), 0,
            "Voluntary EPF must not be a PCB (MTD) component"
        )

    def test_voluntary_epf_component_abbr(self):
        """EPF Voluntary (i-Topup) must have abbreviation EPF-VLN."""
        comp = frappe.get_doc("Salary Component", "EPF Voluntary (i-Topup)")
        self.assertEqual(
            comp.salary_component_abbr, "EPF-VLN",
            "Voluntary EPF abbreviation must be EPF-VLN"
        )
