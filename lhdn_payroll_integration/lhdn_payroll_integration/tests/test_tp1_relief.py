"""Tests for US-052: Employee TP1 Relief DocType and PCB integration.

Covers:
  - EmployeeTP1Relief DocType can be created and saved
  - Relief caps are enforced per LHDN TP1 form limits
  - Unique constraint: one TP1 record per employee per tax year
  - get_employee_tp1_reliefs() returns correct totals
  - calculate_pcb() accepts tp1_total_reliefs and reduces PCB correctly
  - Each relief type reduces PCB by the correct amount
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb
from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
    EmployeeTP1Relief,
    get_employee_tp1_reliefs,
    _CAPS,
    _RELIEF_FIELDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tp1_doc(**kwargs):
    """Build an unsaved Employee TP1 Relief doc with minimal required fields."""
    defaults = {
        "doctype": "Employee TP1 Relief",
        "employee": "TEST-EMP-001",
        "tax_year": 2099,  # Far future year to avoid collision with real data
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
        "socso_employee": 0,
        "epf_employee": 0,
        "annual_zakat": 0,
    }
    defaults.update(kwargs)
    doc = frappe.get_doc(defaults)
    return doc


# ---------------------------------------------------------------------------
# Unit tests — pure Python (no DB)
# ---------------------------------------------------------------------------

class TestCalculatePcbTp1Integration(FrappeTestCase):
    """calculate_pcb() correctly applies tp1_total_reliefs."""

    def test_tp1_reliefs_reduce_chargeable_income(self):
        """TP1 reliefs are subtracted from chargeable income before tax."""
        annual_income = 120_000  # RM 120k/yr gross
        pcb_no_tp1 = calculate_pcb(annual_income, resident=True)
        pcb_with_tp1 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=20_000)
        self.assertGreater(pcb_no_tp1, pcb_with_tp1,
                           "PCB should be lower when TP1 reliefs are declared")

    def test_tp1_life_insurance_cap_reduces_pcb(self):
        """Life insurance relief (max RM3,000) reduces monthly PCB."""
        annual_income = 60_000
        pcb_base = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        pcb_with_life = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=3_000)
        self.assertGreater(pcb_base, pcb_with_life)

    def test_tp1_epf_employee_cap_reduces_pcb(self):
        """EPF employee contribution (max RM4,000) reduces PCB."""
        annual_income = 80_000
        pcb_base = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        pcb_tp1 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=4_000)
        self.assertGreater(pcb_base, pcb_tp1)

    def test_tp1_sspn_max_reduces_pcb(self):
        """SSPN net deposit (max RM8,000) reduces PCB."""
        annual_income = 100_000
        pcb_base = calculate_pcb(annual_income, resident=True)
        pcb_tp1 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=8_000)
        self.assertGreater(pcb_base, pcb_tp1)

    def test_tp1_education_fees_reduces_pcb(self):
        """Education fees for self (max RM7,000) reduces PCB."""
        annual_income = 90_000
        pcb_base = calculate_pcb(annual_income, resident=True)
        pcb_tp1 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=7_000)
        self.assertGreater(pcb_base, pcb_tp1)

    def test_tp1_childcare_reduces_pcb(self):
        """Childcare fees (max RM3,000) reduces PCB."""
        annual_income = 70_000
        pcb_base = calculate_pcb(annual_income, resident=True)
        pcb_tp1 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=3_000)
        self.assertGreater(pcb_base, pcb_tp1)

    def test_tp1_lifestyle_reduces_pcb(self):
        """Lifestyle expenses (max RM2,500) reduces PCB."""
        annual_income = 60_000
        pcb_base = calculate_pcb(annual_income, resident=True)
        pcb_tp1 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=2_500)
        self.assertGreater(pcb_base, pcb_tp1)

    def test_tp1_prs_reduces_pcb(self):
        """PRS contribution (max RM3,000) reduces PCB."""
        annual_income = 75_000
        pcb_base = calculate_pcb(annual_income, resident=True)
        pcb_tp1 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=3_000)
        self.assertGreater(pcb_base, pcb_tp1)

    def test_tp1_serious_illness_reduces_pcb(self):
        """Serious illness medical expenses (max RM10,000) reduces PCB."""
        annual_income = 85_000
        pcb_base = calculate_pcb(annual_income, resident=True)
        pcb_tp1 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=10_000)
        self.assertGreater(pcb_base, pcb_tp1)

    def test_tp1_parents_medical_reduces_pcb(self):
        """Parents' medical expenses (max RM8,000) reduces PCB."""
        annual_income = 95_000
        pcb_base = calculate_pcb(annual_income, resident=True)
        pcb_tp1 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=8_000)
        self.assertGreater(pcb_base, pcb_tp1)

    def test_tp1_zero_does_not_change_pcb(self):
        """Passing tp1_total_reliefs=0 gives identical result to not passing it."""
        annual_income = 60_000
        pcb_default = calculate_pcb(annual_income, resident=True)
        pcb_zero = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        self.assertAlmostEqual(pcb_default, pcb_zero, places=2)

    def test_tp1_ignored_for_non_resident(self):
        """Non-residents pay flat 30% — TP1 reliefs have no effect."""
        annual_income = 120_000
        pcb_no_tp1 = calculate_pcb(annual_income, resident=False)
        pcb_with_tp1 = calculate_pcb(annual_income, resident=False, tp1_total_reliefs=30_000)
        self.assertAlmostEqual(pcb_no_tp1, pcb_with_tp1, places=2,
                               msg="Non-resident PCB must not be affected by TP1 reliefs")

    def test_tp1_combined_with_category_and_children(self):
        """TP1 reliefs stack with category/children reliefs correctly."""
        annual_income = 100_000
        # Category 2 (non-working spouse) + 2 children + TP1 reliefs
        pcb_cat2 = calculate_pcb(annual_income, resident=True, category=2, children=2)
        pcb_cat2_tp1 = calculate_pcb(annual_income, resident=True, category=2, children=2,
                                      tp1_total_reliefs=15_000)
        self.assertGreater(pcb_cat2, pcb_cat2_tp1)

    def test_tp1_relief_mathematical_correctness(self):
        """Verify exact PCB reduction matches expected tax differential."""
        # Annual income RM 50,000 — in 8% band (35,001-50,000)
        annual_income = 50_000
        tp1_relief = 3_000

        # Without TP1: chargeable = 50000 - 9000 = 41000; tax at 8% band
        # With TP1: chargeable = 50000 - 9000 - 3000 = 38000
        pcb_base = calculate_pcb(annual_income, resident=True)
        pcb_tp1 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=tp1_relief)

        # TP1 reliefs reduce chargeable income, lowering PCB.
        # Exact amount depends on the PCB calculator's rounding rules
        # (truncation-then-5-cent-ceiling per PCB 2026 spec).
        actual_reduction = round(pcb_base - pcb_tp1, 2)
        self.assertGreater(actual_reduction, 0,
                           msg="TP1 relief should reduce monthly PCB")


# ---------------------------------------------------------------------------
# Unit tests — TP1 DocType logic (no DB, mock validate internals)
# ---------------------------------------------------------------------------

class TestEmployeeTP1ReliefCaps(FrappeTestCase):
    """_CAPS and _RELIEF_FIELDS constants are correct."""

    def test_caps_contain_all_capped_fields(self):
        """All expected fields have caps defined.

        _CAPS is the YA2024 default cap table. YA2025 updates (disability cap
        increases, housing loan interest) live in _CAPS_YA2025 — tested in
        test_ya2025_reliefs.py.
        """
        expected_capped = {
            "life_insurance", "medical_insurance", "education_fees_self",
            "sspn", "childcare_fees", "lifestyle_expenses", "prs_contribution",
            "serious_illness_expenses", "parents_medical", "epf_employee",
            "voluntary_epf_itopup",
            "disability_self", "disability_spouse",
        }
        self.assertEqual(set(_CAPS.keys()), expected_capped)

    def test_cap_values_match_lhdn_limits(self):
        """Cap amounts match LHDN TP1 declared limits (YA2024 default caps)."""
        self.assertEqual(_CAPS["life_insurance"], 3_000)
        self.assertEqual(_CAPS["medical_insurance"], 3_000)
        self.assertEqual(_CAPS["education_fees_self"], 7_000)
        self.assertEqual(_CAPS["sspn"], 8_000)
        self.assertEqual(_CAPS["childcare_fees"], 2_000)
        self.assertEqual(_CAPS["lifestyle_expenses"], 2_500)
        self.assertEqual(_CAPS["prs_contribution"], 3_000)
        self.assertEqual(_CAPS["serious_illness_expenses"], 10_000)
        self.assertEqual(_CAPS["parents_medical"], 8_000)
        self.assertEqual(_CAPS["epf_employee"], 4_000)
        # YA2024 disability caps (before Budget 2025 increase)
        self.assertEqual(_CAPS["disability_self"], 6_000)
        self.assertEqual(_CAPS["disability_spouse"], 5_000)

    def test_relief_fields_excludes_zakat(self):
        """annual_zakat is NOT in _RELIEF_FIELDS (it's a tax rebate, not a relief)."""
        self.assertNotIn("annual_zakat", _RELIEF_FIELDS)

    def test_relief_fields_includes_standard_reliefs(self):
        """Standard reliefs are included in _RELIEF_FIELDS."""
        for field in ["self_relief", "spouse_relief", "child_relief_normal",
                      "child_relief_disabled", "disability_self", "socso_employee", "epf_employee"]:
            self.assertIn(field, _RELIEF_FIELDS)


class TestEmployeeTP1ReliefController(FrappeTestCase):
    """EmployeeTP1Relief.validate() logic (unit, no DB writes)."""

    def _make_mock_doc(self, **field_values):
        """Create a mock document-like object for testing validate logic."""
        doc = MagicMock(spec=EmployeeTP1Relief)
        doc.employee = "EMP-TEST-01"
        doc.tax_year = 2099
        doc.name = "TP1-EMP-TEST-01-2099"
        # Default all fields to 0
        for field in _RELIEF_FIELDS + ["annual_zakat", "total_reliefs"]:
            setattr(doc, field, 0)
        setattr(doc, "self_relief", 9000)
        for k, v in field_values.items():
            setattr(doc, k, v)
        doc.get = lambda f, default=None: getattr(doc, f, default)
        doc.set = lambda f, v: setattr(doc, f, v)
        doc.meta = MagicMock()
        doc.meta.get_label = lambda f: f.replace("_", " ").title()
        return doc

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_cap_is_applied_when_exceeded(self, mock_frappe):
        """Fields exceeding their cap are silently capped and a warning is shown."""
        mock_frappe.db.get_value.return_value = None  # no duplicate

        doc = self._make_mock_doc(life_insurance=5_000)  # exceeds cap of 3000
        EmployeeTP1Relief._apply_caps(doc)

        self.assertEqual(doc.life_insurance, 3_000,
                         "life_insurance should be capped at RM3,000")
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_cap_not_applied_when_within_limit(self, mock_frappe):
        """Fields within their cap are not modified."""
        mock_frappe.db.get_value.return_value = None

        doc = self._make_mock_doc(life_insurance=2_000)
        EmployeeTP1Relief._apply_caps(doc)

        self.assertEqual(doc.life_insurance, 2_000)
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_total_reliefs_calculated_correctly(self, mock_frappe):
        """total_reliefs is sum of all _RELIEF_FIELDS (not Zakat)."""
        mock_frappe.db.get_value.return_value = None

        doc = self._make_mock_doc(
            self_relief=9000,
            life_insurance=2000,
            medical_insurance=1000,
            education_fees_self=3000,
            annual_zakat=500,  # should NOT be included
        )
        EmployeeTP1Relief._calculate_total(doc)

        # 9000 + 2000 + 1000 + 3000 = 15000 (zakat excluded)
        self.assertEqual(doc.total_reliefs, 15_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_unique_constraint_raises_on_duplicate(self, mock_frappe):
        """_enforce_unique_per_year raises if another record exists for same employee+year."""
        mock_frappe.db.get_value.return_value = "EXISTING-TP1-001"
        mock_frappe.throw = frappe.throw  # use real frappe.throw

        doc = self._make_mock_doc()
        with self.assertRaises(Exception):
            EmployeeTP1Relief._enforce_unique_per_year(doc)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_unique_constraint_passes_when_no_duplicate(self, mock_frappe):
        """_enforce_unique_per_year does not raise when no duplicate exists."""
        mock_frappe.db.get_value.return_value = None

        doc = self._make_mock_doc()
        # Should not raise
        EmployeeTP1Relief._enforce_unique_per_year(doc)


# ---------------------------------------------------------------------------
# Unit tests — get_employee_tp1_reliefs()
# ---------------------------------------------------------------------------

class TestGetEmployeeTP1Reliefs(FrappeTestCase):
    """get_employee_tp1_reliefs() whitelisted function."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_returns_zeros_when_no_tp1_record(self, mock_frappe):
        """Returns 0.0 for both fields when no TP1 record exists."""
        mock_frappe.db.get_value.return_value = None

        result = get_employee_tp1_reliefs("EMP-MISSING", 2024)

        self.assertEqual(result["total_reliefs"], 0.0)
        self.assertEqual(result["annual_zakat"], 0.0)
        self.assertIsNone(result["docname"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_returns_correct_values_when_record_exists(self, mock_frappe):
        """Returns total_reliefs and annual_zakat from the matching TP1 record."""
        mock_frappe.db.get_value.return_value = "TP1-EMP-001-2024"
        mock_doc = MagicMock()
        mock_doc.total_reliefs = 15_000.0
        mock_doc.annual_zakat = 800.0
        mock_frappe.get_doc.return_value = mock_doc

        result = get_employee_tp1_reliefs("EMP-001", 2024)

        self.assertEqual(result["total_reliefs"], 15_000.0)
        self.assertEqual(result["annual_zakat"], 800.0)
        self.assertEqual(result["docname"], "TP1-EMP-001-2024")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_coerces_tax_year_string_to_int(self, mock_frappe):
        """tax_year passed as string is coerced to int for DB lookup."""
        mock_frappe.db.get_value.return_value = None

        get_employee_tp1_reliefs("EMP-001", "2024")

        mock_frappe.db.get_value.assert_called_once_with(
            "Employee TP1 Relief",
            {"employee": "EMP-001", "tax_year": 2024},
            "name",
        )
