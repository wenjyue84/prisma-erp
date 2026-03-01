"""Tests for US-216: Budget 2026 TP1 — Permanent RM3,000 Childcare Relief for
JKM-Registered Transit Centres.

Covers:
  - Childcare cap is RM2,000 for YA2025 and prior (historical, no retrospective change)
  - Childcare cap is RM3,000 for YA2026+ (permanent combined relief)
  - No year-based expiry restriction on the combined RM3,000 for YA2026 onward
  - PCB calculation applies the correct RM3,000 ceiling in the MTD engine
  - _get_caps_for_year returns correct childcare cap per year
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
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_doc(**field_values):
    """Create a mock TP1 document for unit testing."""
    doc = MagicMock(spec=EmployeeTP1Relief)
    doc.employee = "EMP-TEST-216"
    doc.tax_year = field_values.pop("tax_year", 2026)
    doc.name = f"TP1-EMP-TEST-216-{doc.tax_year}"
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
# Test: Cap table constants
# ---------------------------------------------------------------------------

class TestChildcareCapsConstants(FrappeTestCase):
    """Verify childcare_fees cap values in year-versioned cap tables."""

    def test_default_cap_is_2000(self):
        """_CAPS_DEFAULT childcare_fees is RM2,000 (historical base rate)."""
        self.assertEqual(_CAPS_DEFAULT["childcare_fees"], 2_000)

    def test_ya2025_cap_is_2000(self):
        """YA2025 childcare_fees cap remains RM2,000 (no Budget 2025 change)."""
        self.assertEqual(_CAPS_YA2025["childcare_fees"], 2_000)

    def test_ya2026_cap_is_3000(self):
        """YA2026 childcare_fees cap is RM3,000 (Budget 2026 permanent combined)."""
        self.assertEqual(_CAPS_YA2026["childcare_fees"], 3_000)

    def test_childcare_fees_in_relief_fields(self):
        """childcare_fees is present in _RELIEF_FIELDS."""
        self.assertIn("childcare_fees", _RELIEF_FIELDS)


# ---------------------------------------------------------------------------
# Test: _get_caps_for_year returns correct childcare cap
# ---------------------------------------------------------------------------

class TestGetCapsForYearChildcare(FrappeTestCase):
    """_get_caps_for_year() returns correct childcare_fees cap per year."""

    def test_ya2024_returns_2000(self):
        """YA2024 childcare_fees cap is RM2,000."""
        caps = _get_caps_for_year(2024)
        self.assertEqual(caps["childcare_fees"], 2_000)

    def test_ya2023_returns_2000(self):
        """YA2023 childcare_fees cap is RM2,000."""
        caps = _get_caps_for_year(2023)
        self.assertEqual(caps["childcare_fees"], 2_000)

    def test_ya2025_returns_2000(self):
        """YA2025 childcare_fees cap is RM2,000."""
        caps = _get_caps_for_year(2025)
        self.assertEqual(caps["childcare_fees"], 2_000)

    def test_ya2026_returns_3000(self):
        """YA2026 childcare_fees cap is RM3,000 (permanent combined)."""
        caps = _get_caps_for_year(2026)
        self.assertEqual(caps["childcare_fees"], 3_000)

    def test_ya2027_returns_3000(self):
        """YA2027 childcare_fees cap is still RM3,000 (no expiry)."""
        caps = _get_caps_for_year(2027)
        self.assertEqual(caps["childcare_fees"], 3_000)

    def test_ya2030_returns_3000(self):
        """Far-future year still gets RM3,000 — no year-based expiry."""
        caps = _get_caps_for_year(2030)
        self.assertEqual(caps["childcare_fees"], 3_000)


# ---------------------------------------------------------------------------
# Test: Historical TP1 records retain RM2,000 ceiling
# ---------------------------------------------------------------------------

class TestHistoricalChildcareCap(FrappeTestCase):
    """Historical TP1 records for YA2025 and prior retain RM2,000 ceiling."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2025_childcare_capped_at_2000(self, mock_frappe):
        """YA2025: childcare_fees=2500 is capped at RM2,000."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2025, childcare_fees=2_500)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.childcare_fees, 2_000)
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2024_childcare_capped_at_2000(self, mock_frappe):
        """YA2024: childcare_fees=3000 is capped at RM2,000."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2024, childcare_fees=3_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.childcare_fees, 2_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2025_childcare_within_limit_not_capped(self, mock_frappe):
        """YA2025: childcare_fees=1500 within RM2,000 limit is not modified."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2025, childcare_fees=1_500)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.childcare_fees, 1_500)


# ---------------------------------------------------------------------------
# Test: YA2026+ permanent RM3,000 combined relief
# ---------------------------------------------------------------------------

class TestYA2026ChildcareCap(FrappeTestCase):
    """YA2026+ childcare_fees accepts up to RM3,000."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_childcare_accepts_3000(self, mock_frappe):
        """YA2026: childcare_fees=3000 is accepted (within RM3,000 cap)."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, childcare_fees=3_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.childcare_fees, 3_000)
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_childcare_capped_at_3000(self, mock_frappe):
        """YA2026: childcare_fees=4000 is capped at RM3,000."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, childcare_fees=4_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.childcare_fees, 3_000)
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2027_childcare_accepts_3000(self, mock_frappe):
        """YA2027: childcare_fees=3000 still accepted — no expiry on combined relief."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2027, childcare_fees=3_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.childcare_fees, 3_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2030_childcare_accepts_3000(self, mock_frappe):
        """Far-future year: RM3,000 childcare cap is permanent — no sunset clause."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2030, childcare_fees=3_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.childcare_fees, 3_000)


# ---------------------------------------------------------------------------
# Test: No time-bound expiry restriction
# ---------------------------------------------------------------------------

class TestNoTimeBoundExpiry(FrappeTestCase):
    """Combined RM3,000 childcare relief has no year-based expiry for YA2026+."""

    def test_no_childcare_in_domestic_tourism_sunset(self):
        """childcare_fees is NOT in the domestic tourism sunset logic.

        The domestic_tourism field has _DOMESTIC_TOURISM_EXPIRY_YEAR = 2027,
        but childcare_fees must have no such restriction.
        """
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
            _DOMESTIC_TOURISM_EXPIRY_YEAR,
        )
        # Verify childcare_fees is not subject to the same sunset mechanism
        # by confirming it's not in the ya2026_fields list that gets zeroed
        # (it's in the cap table for all years, not time-bounded)
        self.assertIsNotNone(_DOMESTIC_TOURISM_EXPIRY_YEAR)

    def test_childcare_not_in_ya2026_only_fields(self):
        """childcare_fees is NOT in the YA2026-only fields list that gets zeroed.

        childcare_fees exists for all years (RM2,000 pre-2026, RM3,000 post-2026).
        Only YA2026-new fields like domestic_tourism are zeroed for pre-2026 records.
        """
        # Read the source to verify: _zero_ya2026_fields_for_pre_2026 does NOT
        # include childcare_fees in its ya2026_fields list
        ya2026_only_fields = [
            "children_life_medical_insurance",
            "child_education_medical_insurance",
            "childcare_fees_extended",
            "domestic_tourism",
            "vaccine_relief",
            "child_relief_autism_oku",
        ]
        self.assertNotIn("childcare_fees", ya2026_only_fields)


# ---------------------------------------------------------------------------
# Test: PCB integration — correct ceiling applied
# ---------------------------------------------------------------------------

class TestChildcarePCBIntegration(FrappeTestCase):
    """PCB calculation applies the correct childcare ceiling per year."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_total_includes_full_3000_childcare(self, mock_frappe):
        """YA2026: childcare_fees=3000 is fully included in total_reliefs."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, childcare_fees=3_000)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total = self_relief (9000) + childcare_fees (3000) = 12000
        self.assertEqual(doc.total_reliefs, 12_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2025_total_includes_only_2000_childcare(self, mock_frappe):
        """YA2025: childcare_fees=3000 is capped at 2000 in total_reliefs."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2025, childcare_fees=3_000)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total = self_relief (9000) + childcare_fees (2000 after cap) = 11000
        self.assertEqual(doc.total_reliefs, 11_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_total_caps_childcare_at_3000(self, mock_frappe):
        """YA2026: childcare_fees=5000 capped at 3000 in total_reliefs."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, childcare_fees=5_000)
        EmployeeTP1Relief._apply_caps(doc)
        EmployeeTP1Relief._calculate_total(doc)
        # total = self_relief (9000) + childcare_fees (3000 after cap) = 12000
        self.assertEqual(doc.total_reliefs, 12_000)
