"""Tests for US-209: TP1(1/2026) — Capture New Domestic Tourism Attraction
Expenses Relief (RM1,000) in Employee PCB Declaration.

Covers:
  - domestic_tourism cap is RM1,000 in YA2026 cap table
  - domestic_tourism absent from pre-YA2026 cap tables
  - domestic_tourism present in _RELIEF_FIELDS for PCB deduction
  - Field zeroed for pre-2026 tax years (not retroactive)
  - Field rejected (frappe.throw) for post-2027 tax years (sunset clause)
  - Field accepted for YA2026 and YA2027 within RM1,000 cap
  - Amounts above RM1,000 silently capped with user warning
  - total_reliefs correctly includes capped domestic tourism amount
  - Validation message references correct maximum
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
    _DOMESTIC_TOURISM_EXPIRY_YEAR,
    _YA2026_EFFECTIVE_YEAR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_doc(**field_values):
    """Create a mock TP1 document for unit testing."""
    doc = MagicMock(spec=EmployeeTP1Relief)
    doc.employee = "EMP-TEST-209"
    doc.tax_year = field_values.pop("tax_year", 2026)
    doc.name = f"TP1-EMP-TEST-209-{doc.tax_year}"
    # Default all relief fields to 0
    for field in _RELIEF_FIELDS + ["annual_zakat", "total_reliefs",
                                    "spa_date", "housing_loan_interest_500k",
                                    "housing_loan_interest_750k"]:
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
# Test: Cap table constants
# ---------------------------------------------------------------------------

class TestDomesticTourismCapConstants(FrappeTestCase):
    """Verify domestic_tourism cap values in year-versioned cap tables."""

    def test_default_caps_no_domestic_tourism(self):
        """_CAPS_DEFAULT (YA2024 and earlier) does NOT have domestic_tourism."""
        self.assertNotIn("domestic_tourism", _CAPS_DEFAULT)

    def test_ya2025_caps_no_domestic_tourism(self):
        """_CAPS_YA2025 does NOT have domestic_tourism (pre-Budget 2026)."""
        self.assertNotIn("domestic_tourism", _CAPS_YA2025)

    def test_ya2026_caps_has_domestic_tourism_1000(self):
        """_CAPS_YA2026 has domestic_tourism capped at RM1,000."""
        self.assertIn("domestic_tourism", _CAPS_YA2026)
        self.assertEqual(_CAPS_YA2026["domestic_tourism"], 1_000)

    def test_domestic_tourism_in_relief_fields(self):
        """domestic_tourism is present in _RELIEF_FIELDS for PCB deduction."""
        self.assertIn("domestic_tourism", _RELIEF_FIELDS)

    def test_expiry_year_is_2027(self):
        """Domestic tourism sunset year is 2027."""
        self.assertEqual(_DOMESTIC_TOURISM_EXPIRY_YEAR, 2027)

    def test_effective_year_is_2026(self):
        """YA2026 effective year constant is 2026."""
        self.assertEqual(_YA2026_EFFECTIVE_YEAR, 2026)


# ---------------------------------------------------------------------------
# Test: _get_caps_for_year returns correct domestic tourism cap
# ---------------------------------------------------------------------------

class TestGetCapsForYearDomesticTourism(FrappeTestCase):
    """_get_caps_for_year() returns correct domestic_tourism cap per year."""

    def test_ya2024_no_domestic_tourism_cap(self):
        """YA2024: domestic_tourism not in cap table."""
        caps = _get_caps_for_year(2024)
        self.assertNotIn("domestic_tourism", caps)

    def test_ya2025_no_domestic_tourism_cap(self):
        """YA2025: domestic_tourism not in cap table."""
        caps = _get_caps_for_year(2025)
        self.assertNotIn("domestic_tourism", caps)

    def test_ya2026_domestic_tourism_cap_1000(self):
        """YA2026: domestic_tourism cap is RM1,000."""
        caps = _get_caps_for_year(2026)
        self.assertEqual(caps["domestic_tourism"], 1_000)

    def test_ya2027_domestic_tourism_cap_1000(self):
        """YA2027: domestic_tourism cap is RM1,000 (still within sunset window)."""
        caps = _get_caps_for_year(2027)
        self.assertEqual(caps["domestic_tourism"], 1_000)

    def test_ya2028_domestic_tourism_cap_still_in_table(self):
        """YA2028+: cap table still has domestic_tourism=1000 (expiry is
        handled by _validate_domestic_tourism_expiry, not by removing from caps)."""
        caps = _get_caps_for_year(2028)
        self.assertEqual(caps["domestic_tourism"], 1_000)


# ---------------------------------------------------------------------------
# Test: Pre-2026 zeroing — field not retroactively applied
# ---------------------------------------------------------------------------

class TestDomesticTourismPreYA2026Zeroing(FrappeTestCase):
    """domestic_tourism is zeroed for pre-2026 tax years."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2025_domestic_tourism_zeroed(self, mock_frappe):
        """YA2025: domestic_tourism=500 is cleared to 0 with user warning."""
        mock_frappe.db.get_value.return_value = None
        mock_frappe._ = lambda s, *a, **kw: s.format(*a, **kw) if a else s
        doc = _make_mock_doc(tax_year=2025, domestic_tourism=500)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.domestic_tourism, 0)
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2024_domestic_tourism_zeroed(self, mock_frappe):
        """YA2024: domestic_tourism=1000 is cleared to 0."""
        mock_frappe.db.get_value.return_value = None
        mock_frappe._ = lambda s, *a, **kw: s.format(*a, **kw) if a else s
        doc = _make_mock_doc(tax_year=2024, domestic_tourism=1_000)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.domestic_tourism, 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2025_domestic_tourism_zero_not_warned(self, mock_frappe):
        """YA2025: domestic_tourism=0 does NOT trigger any warning."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2025, domestic_tourism=0)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.domestic_tourism, 0)
        # No msgprint since value was already 0
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_domestic_tourism_not_zeroed(self, mock_frappe):
        """YA2026: domestic_tourism is NOT zeroed (field is available)."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, domestic_tourism=800)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.domestic_tourism, 800)


# ---------------------------------------------------------------------------
# Test: Post-2027 sunset — _validate_domestic_tourism_expiry
# ---------------------------------------------------------------------------

class TestDomesticTourismExpiry(FrappeTestCase):
    """domestic_tourism rejected for tax years after 2027 (sunset clause)."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2028_domestic_tourism_throws(self, mock_frappe):
        """YA2028: domestic_tourism=500 triggers frappe.throw (expired)."""
        mock_frappe._ = lambda s, *a, **kw: s.format(*a, **kw) if a else s
        doc = _make_mock_doc(tax_year=2028, domestic_tourism=500)
        EmployeeTP1Relief._validate_domestic_tourism_expiry(doc)
        mock_frappe.throw.assert_called_once()
        call_args = mock_frappe.throw.call_args
        self.assertIn("2027", call_args[0][0])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2030_domestic_tourism_throws(self, mock_frappe):
        """YA2030: far-future year still rejected."""
        mock_frappe._ = lambda s, *a, **kw: s.format(*a, **kw) if a else s
        doc = _make_mock_doc(tax_year=2030, domestic_tourism=1_000)
        EmployeeTP1Relief._validate_domestic_tourism_expiry(doc)
        mock_frappe.throw.assert_called_once()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2027_domestic_tourism_accepted(self, mock_frappe):
        """YA2027: domestic_tourism=1000 does NOT throw (within sunset window)."""
        doc = _make_mock_doc(tax_year=2027, domestic_tourism=1_000)
        EmployeeTP1Relief._validate_domestic_tourism_expiry(doc)
        mock_frappe.throw.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_domestic_tourism_accepted(self, mock_frappe):
        """YA2026: domestic_tourism=1000 does NOT throw (first eligible year)."""
        doc = _make_mock_doc(tax_year=2026, domestic_tourism=1_000)
        EmployeeTP1Relief._validate_domestic_tourism_expiry(doc)
        mock_frappe.throw.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2028_zero_amount_no_throw(self, mock_frappe):
        """YA2028: domestic_tourism=0 does NOT throw (no claim = no issue)."""
        doc = _make_mock_doc(tax_year=2028, domestic_tourism=0)
        EmployeeTP1Relief._validate_domestic_tourism_expiry(doc)
        mock_frappe.throw.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_throw_message_includes_amount_and_year(self, mock_frappe):
        """Error message references the declared amount and current tax year."""
        mock_frappe._ = lambda s, *a, **kw: s.format(*a, **kw) if a else s
        doc = _make_mock_doc(tax_year=2029, domestic_tourism=750)
        EmployeeTP1Relief._validate_domestic_tourism_expiry(doc)
        msg = mock_frappe.throw.call_args[0][0]
        self.assertIn("750", msg)
        self.assertIn("2029", msg)
        self.assertIn("2027", msg)


# ---------------------------------------------------------------------------
# Test: Cap enforcement — amounts above RM1,000 silently capped
# ---------------------------------------------------------------------------

class TestDomesticTourismCapEnforcement(FrappeTestCase):
    """domestic_tourism amounts above RM1,000 are capped with user warning."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_1500_capped_at_1000(self, mock_frappe):
        """YA2026: domestic_tourism=1500 is capped at RM1,000."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, domestic_tourism=1_500)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.domestic_tourism, 1_000)
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_1000_not_capped(self, mock_frappe):
        """YA2026: domestic_tourism=1000 at exactly the cap — not modified."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, domestic_tourism=1_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.domestic_tourism, 1_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_500_within_cap(self, mock_frappe):
        """YA2026: domestic_tourism=500 within limit — not modified, no warning."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, domestic_tourism=500)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.domestic_tourism, 500)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2027_2000_capped_at_1000(self, mock_frappe):
        """YA2027: domestic_tourism=2000 is capped at RM1,000."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2027, domestic_tourism=2_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.domestic_tourism, 1_000)
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_cap_warning_includes_amount_info(self, mock_frappe):
        """Cap warning message includes both declared and cap amounts."""
        mock_frappe._ = lambda s, *a, **kw: s.format(*a, **kw) if a else s
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, domestic_tourism=1_500)
        EmployeeTP1Relief._apply_caps(doc)
        call_args = mock_frappe.msgprint.call_args
        msg = call_args[0][0]
        self.assertIn("1,000", msg)
        self.assertIn("1,500", msg)


# ---------------------------------------------------------------------------
# Test: PCB integration — total_reliefs includes domestic tourism
# ---------------------------------------------------------------------------

class TestDomesticTourismPCBIntegration(FrappeTestCase):
    """PCB calculation correctly deducts domestic tourism from chargeable income."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_total_includes_domestic_tourism(self, mock_frappe):
        """YA2026: domestic_tourism=800 is included in total_reliefs."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, domestic_tourism=800)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total = self_relief (9000) + domestic_tourism (800) = 9800
        self.assertEqual(doc.total_reliefs, 9_800)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_total_with_capped_domestic_tourism(self, mock_frappe):
        """YA2026: domestic_tourism=1500 capped to 1000, total_reliefs reflects cap."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, domestic_tourism=1_500)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total = self_relief (9000) + domestic_tourism (1000 after cap) = 10000
        self.assertEqual(doc.total_reliefs, 10_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_total_with_max_domestic_tourism(self, mock_frappe):
        """YA2026: domestic_tourism=1000 fully included in total_reliefs."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, domestic_tourism=1_000)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total = self_relief (9000) + domestic_tourism (1000) = 10000
        self.assertEqual(doc.total_reliefs, 10_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2025_total_excludes_domestic_tourism(self, mock_frappe):
        """YA2025: domestic_tourism is zeroed, so total_reliefs only has self_relief."""
        mock_frappe.db.get_value.return_value = None
        mock_frappe._ = lambda s, *a, **kw: s.format(*a, **kw) if a else s
        doc = _make_mock_doc(tax_year=2025, domestic_tourism=500)
        # First zero pre-2026 fields, then cap, then total
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # domestic_tourism zeroed, total = self_relief (9000)
        self.assertEqual(doc.total_reliefs, 9_000)
        self.assertEqual(doc.domestic_tourism, 0)


# ---------------------------------------------------------------------------
# Test: Combined scenario — multiple reliefs with domestic tourism
# ---------------------------------------------------------------------------

class TestDomesticTourismCombinedScenarios(FrappeTestCase):
    """Combined scenarios: domestic tourism alongside other reliefs."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_multiple_reliefs_with_tourism(self, mock_frappe):
        """YA2026: domestic_tourism + childcare + lifestyle all included correctly."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(
            tax_year=2026,
            domestic_tourism=800,
            childcare_fees=2_500,
            lifestyle_expenses=2_000,
        )
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total = 9000 + 800 + 2500 + 2000 = 14300
        self.assertEqual(doc.total_reliefs, 14_300)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_tourism_does_not_affect_other_caps(self, mock_frappe):
        """domestic_tourism cap is independent — does not share pool with others."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(
            tax_year=2026,
            domestic_tourism=1_000,
            life_insurance=3_000,
            medical_insurance=3_000,
        )
        EmployeeTP1Relief._apply_caps(doc)
        # domestic_tourism stays at 1000 (its own cap)
        self.assertEqual(doc.domestic_tourism, 1_000)
        # life and medical have their own caps
        self.assertEqual(doc.life_insurance, 3_000)
        self.assertEqual(doc.medical_insurance, 3_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2027_tourism_last_eligible_year(self, mock_frappe):
        """YA2027: last year of domestic tourism — accepted and included in total."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2027, domestic_tourism=1_000)
        EmployeeTP1Relief._validate_domestic_tourism_expiry(doc)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        mock_frappe.throw.assert_not_called()
        self.assertEqual(doc.domestic_tourism, 1_000)
        self.assertEqual(doc.total_reliefs, 10_000)
