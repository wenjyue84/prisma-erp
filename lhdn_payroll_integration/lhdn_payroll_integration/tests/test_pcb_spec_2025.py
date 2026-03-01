"""Tests for US-188: PCB 2025 Specification Amendment.

Covers the LHDN PCB Computerised Calculation Method Specification 2025
(Spesifikasi Kaedah Pengiraan Berkomputer PCB 2025):

  1. OKU disability relief amounts updated (RM7,000 self / RM6,000 spouse)
     — already covered in test_ya2025_reliefs.py; verified here for completeness
  2. Food waste composting machine relief (RM2,500 permanent cap) — NEW YA2025
  3. PCB_SPEC_VERSION constant in pcb_calculator — "2025 Spec Compliant"
  4. Combined OKU + composting machine scenario reduces PCB correctly for YA2025
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
    EmployeeTP1Relief,
    _CAPS_YA2025,
    _CAPS_DEFAULT,
    _RELIEF_FIELDS,
    _get_caps_for_year,
)
from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb, PCB_SPEC_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_doc(**kwargs):
    """Build a mock TP1 doc with zero-valued fields for YA2025."""
    defaults = {
        "employee": "TEST-EMP-US188",
        "tax_year": 2025,
        "name": "TP1-TEST-EMP-US188-2025",
        "self_relief": 9000,
        "spouse_relief": 0,
        "child_relief_normal": 0,
        "child_relief_disabled": 0,
        "child_relief_autism_oku": 0,
        "life_insurance": 0,
        "children_life_medical_insurance": 0,
        "medical_insurance": 0,
        "education_fees_self": 0,
        "sspn": 0,
        "childcare_fees": 0,
        "childcare_fees_extended": 0,
        "lifestyle_expenses": 0,
        "prs_contribution": 0,
        "serious_illness_expenses": 0,
        "parents_medical": 0,
        "housing_loan_interest_500k": 0,
        "housing_loan_interest_750k": 0,
        "spa_date": None,
        "disability_self": 0,
        "disability_spouse": 0,
        "socso_employee": 0,
        "epf_employee": 0,
        "voluntary_epf_itopup": 0,
        "annual_zakat": 0,
        "domestic_tourism": 0,
        "vaccine_relief": 0,
        "food_waste_composting_machine": 0,
        "total_reliefs": 0,
    }
    defaults.update(kwargs)

    doc = MagicMock(spec=EmployeeTP1Relief)
    doc.meta = MagicMock()
    doc.meta.get_label = lambda f: f.replace("_", " ").title()
    doc.name = defaults["name"]

    for key, val in defaults.items():
        setattr(doc, key, val)

    doc.get = lambda f, default=None: getattr(doc, f, default)
    doc.set = lambda f, v: setattr(doc, f, v)
    return doc


# ---------------------------------------------------------------------------
# 1. PCB_SPEC_VERSION constant
# ---------------------------------------------------------------------------

class TestPCBSpecVersion(FrappeTestCase):
    """PCB_SPEC_VERSION is set to '2025 Spec Compliant' for audit reference."""

    def test_pcb_spec_version_is_2025_spec_compliant(self):
        """PCB_SPEC_VERSION equals '2025 Spec Compliant'."""
        self.assertEqual(PCB_SPEC_VERSION, "2025 Spec Compliant")

    def test_pcb_spec_version_is_string(self):
        """PCB_SPEC_VERSION is a string type."""
        self.assertIsInstance(PCB_SPEC_VERSION, str)


# ---------------------------------------------------------------------------
# 2. Food waste composting machine relief cap (RM 2,500, permanent, YA2025)
# ---------------------------------------------------------------------------

class TestFoodWasteCompostingMachineRelief(FrappeTestCase):
    """food_waste_composting_machine field — RM 2,500 permanent cap from YA2025."""

    def test_food_waste_in_ya2025_caps(self):
        """food_waste_composting_machine is in YA2025 caps at RM 2,500."""
        self.assertIn("food_waste_composting_machine", _CAPS_YA2025,
                      "food_waste_composting_machine must be in _CAPS_YA2025")
        self.assertEqual(_CAPS_YA2025["food_waste_composting_machine"], 2_500)

    def test_food_waste_not_in_default_caps(self):
        """food_waste_composting_machine is NOT in default (YA2024) caps."""
        self.assertNotIn("food_waste_composting_machine", _CAPS_DEFAULT,
                         "food_waste_composting_machine was not available before YA2025")

    def test_food_waste_in_ya2025_via_get_caps_for_year(self):
        """_get_caps_for_year(2025) includes food_waste_composting_machine."""
        caps = _get_caps_for_year(2025)
        self.assertIn("food_waste_composting_machine", caps)
        self.assertEqual(caps["food_waste_composting_machine"], 2_500)

    def test_food_waste_in_ya2026_caps(self):
        """food_waste_composting_machine is inherited into YA2026 caps (permanent)."""
        caps = _get_caps_for_year(2026)
        self.assertIn("food_waste_composting_machine", caps,
                      "food_waste_composting_machine must persist into YA2026 caps")
        self.assertEqual(caps["food_waste_composting_machine"], 2_500)

    def test_food_waste_not_in_ya2024_caps(self):
        """_get_caps_for_year(2024) does NOT include food_waste_composting_machine."""
        caps = _get_caps_for_year(2024)
        self.assertNotIn("food_waste_composting_machine", caps)

    def test_food_waste_in_relief_fields(self):
        """food_waste_composting_machine is in _RELIEF_FIELDS for total calculation."""
        self.assertIn("food_waste_composting_machine", _RELIEF_FIELDS)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_food_waste_capped_at_2500_ya2025(self, mock_frappe):
        """food_waste_composting_machine is capped at RM 2,500 for YA2025."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2025, food_waste_composting_machine=5_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.food_waste_composting_machine, 2_500)
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_food_waste_within_cap_unchanged(self, mock_frappe):
        """food_waste_composting_machine within RM 2,500 is not modified."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2025, food_waste_composting_machine=1_800)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.food_waste_composting_machine, 1_800)
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_food_waste_not_capped_for_ya2024(self, mock_frappe):
        """food_waste_composting_machine is not in YA2024 caps — value passes through."""
        mock_frappe.db.get_value.return_value = None
        # For YA2024, the field is not in caps — the value is accepted as-is
        # (field should ideally not be visible on pre-YA2025 records, but
        # the controller does not explicitly zero it the way YA2026 fields are zeroed)
        doc = _make_mock_doc(tax_year=2024, food_waste_composting_machine=1_000)
        # _apply_caps only caps fields that appear in the year's caps table
        # For YA2024, food_waste is not capped — no msgprint expected
        EmployeeTP1Relief._apply_caps(doc)
        # Value should remain as-is (no cap applied for pre-2025)
        self.assertEqual(doc.food_waste_composting_machine, 1_000)


# ---------------------------------------------------------------------------
# 3. OKU disability relief — YA2025 values (PCB 2025 spec alignment)
# ---------------------------------------------------------------------------

class TestOKUReliefYA2025Spec(FrappeTestCase):
    """OKU disability relief amounts as per PCB 2025 spec amendment."""

    def test_disability_self_cap_is_7000_in_ya2025(self):
        """_CAPS_YA2025 disability_self is RM 7,000 (raised from RM 6,000)."""
        self.assertEqual(_CAPS_YA2025["disability_self"], 7_000)

    def test_disability_spouse_cap_is_6000_in_ya2025(self):
        """_CAPS_YA2025 disability_spouse is RM 6,000 (raised from RM 5,000)."""
        self.assertEqual(_CAPS_YA2025["disability_spouse"], 6_000)

    def test_disability_self_cap_was_6000_in_ya2024(self):
        """YA2024 disability_self remains RM 6,000 (historical)."""
        caps = _get_caps_for_year(2024)
        self.assertEqual(caps["disability_self"], 6_000)

    def test_disability_spouse_cap_was_5000_in_ya2024(self):
        """YA2024 disability_spouse remains RM 5,000 (historical)."""
        caps = _get_caps_for_year(2024)
        self.assertEqual(caps["disability_spouse"], 5_000)


# ---------------------------------------------------------------------------
# 4. Combined OKU + composting machine scenario — PCB reduction for YA2025
# ---------------------------------------------------------------------------

class TestCombinedOKUAndCompostingPCB(FrappeTestCase):
    """Combined OKU + composting machine relief reduces PCB correctly."""

    def test_oku_disability_reduces_pcb(self):
        """OKU disability_self relief (as tp1_total_reliefs) reduces PCB for YA2025."""
        annual_income = 80_000
        pcb_no_oku = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        pcb_with_oku = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=7_000)
        self.assertGreater(pcb_no_oku, pcb_with_oku,
                           "PCB must decrease when OKU disability relief is declared")

    def test_composting_machine_reduces_pcb(self):
        """food_waste_composting_machine (as tp1_total_reliefs) reduces PCB for YA2025."""
        annual_income = 75_000
        pcb_no_composting = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        pcb_with_composting = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=2_500)
        self.assertGreater(pcb_no_composting, pcb_with_composting,
                           "PCB must decrease when composting machine relief is declared")

    def test_combined_oku_and_composting_reduces_pcb(self):
        """Combined OKU (RM7,000) + composting (RM2,500) = RM9,500 total relief
        results in lower PCB than either relief alone."""
        annual_income = 80_000
        pcb_oku_only = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=7_000)
        pcb_combined = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=9_500)
        self.assertGreater(pcb_oku_only, pcb_combined,
                           "Combined OKU + composting relief must give lower PCB than OKU alone")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_total_reliefs_includes_composting_machine(self, mock_frappe):
        """_calculate_total() includes food_waste_composting_machine in total."""
        doc = _make_mock_doc(
            tax_year=2025,
            self_relief=9_000,
            disability_self=7_000,
            food_waste_composting_machine=2_500,
        )
        EmployeeTP1Relief._calculate_total(doc)
        # 9000 + 7000 + 2500 = 18500
        self.assertEqual(doc.total_reliefs, 18_500)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_annual_zakat_excluded_when_composting_present(self, mock_frappe):
        """annual_zakat remains excluded from total even when composting relief is present."""
        doc = _make_mock_doc(
            tax_year=2025,
            self_relief=9_000,
            food_waste_composting_machine=2_500,
            annual_zakat=1_000,  # Must NOT be included
        )
        EmployeeTP1Relief._calculate_total(doc)
        # 9000 + 2500 = 11500 (zakat excluded)
        self.assertEqual(doc.total_reliefs, 11_500,
                         "Zakat must not be included in total_reliefs")
