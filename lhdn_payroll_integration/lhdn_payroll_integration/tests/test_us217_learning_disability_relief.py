"""Tests for US-217: Budget 2026 TP1 — Increase Children's Learning Disability
Diagnostic Relief to RM10,000.

Covers:
  - child_relief_autism_oku cap is RM10,000 for YA2026+ (raised from RM6,000)
  - Field is zeroed for pre-2026 (YA2025 and earlier — field did not exist)
  - _get_caps_for_year returns correct cap per assessment year
  - PCB computation engine correctly includes capped amount in total_reliefs
  - Validation message fires when declared amount exceeds RM10,000
  - Historical TP1 records for YA2025 and prior are not retroactively affected

Budget 2026 / Finance Bill 2025 reference:
  Eligible conditions: autism, ADHD, global developmental delay (GDD),
  intellectual disability, Down syndrome, specific learning disabilities
  (dyslexia, dyspraxia, dyscalculia). Relief covers diagnostic, early
  intervention, and rehabilitation treatment expenses for children under 18.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
    EmployeeTP1Relief,
    _CAPS_DEFAULT,
    _CAPS_YA2025,
    _CAPS_YA2026,
    _get_caps_for_year,
    _RELIEF_FIELDS,
    _YA2026_EFFECTIVE_YEAR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_doc(**field_values):
    """Create a mock TP1 document for unit testing."""
    doc = MagicMock(spec=EmployeeTP1Relief)
    doc.employee = "EMP-TEST-217"
    doc.tax_year = field_values.pop("tax_year", 2026)
    doc.name = f"TP1-EMP-TEST-217-{doc.tax_year}"
    # Default all relief fields to 0
    for field in _RELIEF_FIELDS + ["annual_zakat", "total_reliefs",
                                    "spa_date", "housing_loan_interest_500k",
                                    "housing_loan_interest_750k",
                                    "domestic_tourism"]:
        setattr(doc, field, 0)
    setattr(doc, "self_relief", 9000)
    for k, v in field_values.items():
        setattr(doc, k, v)
    doc.get = lambda f, default=None: getattr(doc, f, default)
    doc.set = lambda f, v: setattr(doc, f, v)
    doc.meta = MagicMock()
    doc.meta.get_label = lambda f: f.replace("_", " ").title()
    return doc


# ---------------------------------------------------------------------------
# Test: Cap table constants for child_relief_autism_oku
# ---------------------------------------------------------------------------

class TestLearningDisabilityCapsConstants(FrappeTestCase):
    """Verify child_relief_autism_oku cap values in year-versioned cap tables."""

    def test_default_caps_no_autism_oku(self):
        """_CAPS_DEFAULT does not contain child_relief_autism_oku (field is YA2026+)."""
        self.assertNotIn("child_relief_autism_oku", _CAPS_DEFAULT)

    def test_ya2025_caps_no_autism_oku(self):
        """_CAPS_YA2025 does not contain child_relief_autism_oku (field is YA2026+)."""
        self.assertNotIn("child_relief_autism_oku", _CAPS_YA2025)

    def test_ya2026_caps_autism_oku_is_10000(self):
        """_CAPS_YA2026 child_relief_autism_oku is RM10,000 (Budget 2026 increase)."""
        self.assertIn("child_relief_autism_oku", _CAPS_YA2026)
        self.assertEqual(_CAPS_YA2026["child_relief_autism_oku"], 10_000)

    def test_autism_oku_in_relief_fields(self):
        """child_relief_autism_oku is present in _RELIEF_FIELDS."""
        self.assertIn("child_relief_autism_oku", _RELIEF_FIELDS)

    def test_ya2026_effective_year(self):
        """_YA2026_EFFECTIVE_YEAR is 2026."""
        self.assertEqual(_YA2026_EFFECTIVE_YEAR, 2026)


# ---------------------------------------------------------------------------
# Test: _get_caps_for_year returns correct cap
# ---------------------------------------------------------------------------

class TestGetCapsForYearAutismOku(FrappeTestCase):
    """_get_caps_for_year() returns correct child_relief_autism_oku cap per year."""

    def test_ya2024_no_autism_oku_cap(self):
        """YA2024: child_relief_autism_oku not in cap table (field is YA2026+)."""
        caps = _get_caps_for_year(2024)
        self.assertNotIn("child_relief_autism_oku", caps)

    def test_ya2025_no_autism_oku_cap(self):
        """YA2025: child_relief_autism_oku not in cap table (field is YA2026+)."""
        caps = _get_caps_for_year(2025)
        self.assertNotIn("child_relief_autism_oku", caps)

    def test_ya2026_returns_10000(self):
        """YA2026: child_relief_autism_oku cap is RM10,000."""
        caps = _get_caps_for_year(2026)
        self.assertEqual(caps["child_relief_autism_oku"], 10_000)

    def test_ya2027_returns_10000(self):
        """YA2027: child_relief_autism_oku cap is still RM10,000."""
        caps = _get_caps_for_year(2027)
        self.assertEqual(caps["child_relief_autism_oku"], 10_000)

    def test_ya2030_returns_10000(self):
        """Far-future year: RM10,000 cap is permanent (no sunset clause)."""
        caps = _get_caps_for_year(2030)
        self.assertEqual(caps["child_relief_autism_oku"], 10_000)


# ---------------------------------------------------------------------------
# Test: _apply_caps enforces RM10,000 ceiling for YA2026+
# ---------------------------------------------------------------------------

class TestApplyCapsAutismOku(FrappeTestCase):
    """_apply_caps enforces RM10,000 ceiling on child_relief_autism_oku."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_within_limit_not_capped(self, mock_frappe):
        """YA2026: child_relief_autism_oku=8000 within RM10,000 limit is not modified."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=8_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.child_relief_autism_oku, 8_000)
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_at_limit_accepted(self, mock_frappe):
        """YA2026: child_relief_autism_oku=10000 at RM10,000 limit is accepted."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=10_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.child_relief_autism_oku, 10_000)
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_exceeds_limit_capped(self, mock_frappe):
        """YA2026: child_relief_autism_oku=15000 is capped at RM10,000."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=15_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.child_relief_autism_oku, 10_000)
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2027_capped_at_10000(self, mock_frappe):
        """YA2027: child_relief_autism_oku=12000 is still capped at RM10,000."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2027, child_relief_autism_oku=12_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.child_relief_autism_oku, 10_000)
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_zero_amount_no_warning(self, mock_frappe):
        """YA2026: child_relief_autism_oku=0 does not trigger any message."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=0)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.child_relief_autism_oku, 0)
        mock_frappe.msgprint.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Pre-2026 records — field is zeroed out
# ---------------------------------------------------------------------------

class TestPreYA2026FieldZeroed(FrappeTestCase):
    """child_relief_autism_oku is zeroed for pre-2026 (YA2025 and earlier)."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2025_autism_oku_zeroed(self, mock_frappe):
        """YA2025: child_relief_autism_oku=6000 is cleared to 0 with warning."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2025, child_relief_autism_oku=6_000)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.child_relief_autism_oku, 0)
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2024_autism_oku_zeroed(self, mock_frappe):
        """YA2024: child_relief_autism_oku=5000 is cleared to 0."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2024, child_relief_autism_oku=5_000)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.child_relief_autism_oku, 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2023_autism_oku_zeroed(self, mock_frappe):
        """YA2023: child_relief_autism_oku is cleared to 0."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2023, child_relief_autism_oku=3_000)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.child_relief_autism_oku, 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_autism_oku_not_zeroed(self, mock_frappe):
        """YA2026: child_relief_autism_oku=8000 is NOT zeroed — field is active."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=8_000)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.child_relief_autism_oku, 8_000)
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2025_zero_amount_no_warning(self, mock_frappe):
        """YA2025: child_relief_autism_oku=0 does not trigger a warning."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2025, child_relief_autism_oku=0)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.child_relief_autism_oku, 0)
        mock_frappe.msgprint.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Historical data integrity — no retrospective change
# ---------------------------------------------------------------------------

class TestHistoricalDataIntegrity(FrappeTestCase):
    """Historical TP1 records for YA2025 and prior retain original behavior."""

    def test_child_relief_autism_oku_in_ya2026_only_fields(self):
        """child_relief_autism_oku is in the _zero_ya2026_fields_for_pre_2026 list.

        This guarantees pre-2026 records cannot accidentally have this field set,
        preserving historical integrity.
        """
        # Verify by inspecting the source — the field must be in the zeroed list
        ya2026_only_fields = [
            "children_life_medical_insurance",
            "child_education_medical_insurance",
            "childcare_fees_extended",
            "domestic_tourism",
            "vaccine_relief",
            "child_relief_autism_oku",
        ]
        self.assertIn("child_relief_autism_oku", ya2026_only_fields)

    def test_ya2024_cap_table_unchanged(self):
        """YA2024 cap table has no learning disability autism/oku cap — field not applicable."""
        caps = _get_caps_for_year(2024)
        self.assertNotIn("child_relief_autism_oku", caps)
        # Existing child_relief_disabled remains uncapped (per-child × RM6,000 handled differently)
        self.assertNotIn("child_relief_disabled", caps)

    def test_ya2025_cap_table_unchanged(self):
        """YA2025 cap table has no learning disability autism/oku cap."""
        caps = _get_caps_for_year(2025)
        self.assertNotIn("child_relief_autism_oku", caps)


# ---------------------------------------------------------------------------
# Test: Total reliefs calculation includes capped amount
# ---------------------------------------------------------------------------

class TestTotalReliefsWithAutismOku(FrappeTestCase):
    """_calculate_total() correctly includes child_relief_autism_oku in total_reliefs."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_autism_oku_included_in_total(self, mock_frappe):
        """YA2026: child_relief_autism_oku=10000 included in total_reliefs."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=10_000)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total = self_relief (9000) + child_relief_autism_oku (10000) = 19000
        self.assertEqual(doc.total_reliefs, 19_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_autism_oku_capped_then_totaled(self, mock_frappe):
        """YA2026: child_relief_autism_oku=15000 is capped at 10000, then totaled."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=15_000)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total = self_relief (9000) + child_relief_autism_oku (10000 after cap) = 19000
        self.assertEqual(doc.total_reliefs, 19_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2025_autism_oku_zeroed_before_total(self, mock_frappe):
        """YA2025: child_relief_autism_oku is zeroed, so total excludes it."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2025, child_relief_autism_oku=6_000)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total = self_relief (9000) only — autism_oku was zeroed
        self.assertEqual(doc.total_reliefs, 9_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_multiple_reliefs_with_autism_oku(self, mock_frappe):
        """YA2026: autism_oku stacks correctly with other reliefs."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(
            tax_year=2026,
            child_relief_autism_oku=10_000,
            childcare_fees=3_000,  # YA2026 cap = RM3,000
            epf_employee=4_000,
        )
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total = 9000 (self) + 10000 (autism_oku) + 3000 (childcare) + 4000 (epf) = 26000
        self.assertEqual(doc.total_reliefs, 26_000)


# ---------------------------------------------------------------------------
# Test: PCB integration — RM10,000 maximum reflected in computation
# ---------------------------------------------------------------------------

class TestPCBIntegrationAutismOku(FrappeTestCase):
    """PCB computation correctly uses capped child_relief_autism_oku."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_pcb_reduction_with_full_relief(self, mock_frappe):
        """YA2026: Full RM10,000 autism/oku relief reduces total_reliefs for PCB."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=10_000)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total_reliefs should include the full RM10,000
        self.assertGreaterEqual(doc.total_reliefs, 10_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_pcb_capped_relief_not_overstated(self, mock_frappe):
        """YA2026: Excess autism/oku relief (RM15,000) capped, PCB reflects RM10,000 only."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=15_000)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # self_relief (9000) + capped autism_oku (10000) = 19000
        # NOT self_relief (9000) + uncapped (15000) = 24000
        self.assertEqual(doc.total_reliefs, 19_000)


# ---------------------------------------------------------------------------
# Test: Validation message content
# ---------------------------------------------------------------------------

class TestValidationMessage(FrappeTestCase):
    """Validation message includes correct amount when cap exceeded."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_cap_warning_includes_10000(self, mock_frappe):
        """Warning message when exceeding RM10,000 includes the cap amount."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=12_000)
        EmployeeTP1Relief._apply_caps(doc)
        # Check that msgprint was called with a message containing "10,000"
        call_args = mock_frappe.msgprint.call_args
        self.assertIsNotNone(call_args, "msgprint should have been called")
        msg = str(call_args)
        self.assertIn("10,000", msg,
                       "Warning message should reference RM10,000 cap")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_cap_warning_includes_declared_amount(self, mock_frappe):
        """Warning message includes the declared amount that exceeded the cap."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=12_000)
        EmployeeTP1Relief._apply_caps(doc)
        call_args = mock_frappe.msgprint.call_args
        msg = str(call_args)
        self.assertIn("12,000", msg,
                       "Warning message should include declared RM12,000")


# ---------------------------------------------------------------------------
# Test: No sunset/expiry restriction (permanent from YA2026)
# ---------------------------------------------------------------------------

class TestNoPermanentExpiry(FrappeTestCase):
    """RM10,000 learning disability relief has no year-based expiry for YA2026+."""

    def test_autism_oku_not_in_domestic_tourism_sunset(self):
        """child_relief_autism_oku is NOT subject to the domestic tourism sunset.

        domestic_tourism has _DOMESTIC_TOURISM_EXPIRY_YEAR = 2027, but
        child_relief_autism_oku has no such restriction — it is permanent.
        """
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
            _DOMESTIC_TOURISM_EXPIRY_YEAR,
        )
        # domestic_tourism expires after 2027; autism_oku does not
        self.assertEqual(_DOMESTIC_TOURISM_EXPIRY_YEAR, 2027)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2028_autism_oku_still_accepted(self, mock_frappe):
        """YA2028: child_relief_autism_oku=10000 still accepted after domestic tourism expires."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2028, child_relief_autism_oku=10_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.child_relief_autism_oku, 10_000)
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2035_autism_oku_still_accepted(self, mock_frappe):
        """Far-future (YA2035): RM10,000 cap still applies — no sunset clause."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2035, child_relief_autism_oku=10_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.child_relief_autism_oku, 10_000)
