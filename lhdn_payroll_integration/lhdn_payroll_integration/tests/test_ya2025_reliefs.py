"""Tests for US-104: PCB TP1 Relief Table updates for YA2025.

Covers Budget 2025 changes effective from Assessment Year 2025:
  1. New Housing Loan Interest Relief for first home ≤RM500K (max RM7,000)
  2. New Housing Loan Interest Relief for first home RM500K–RM750K (max RM5,000)
  3. SPA date validation (must be 1 Jan 2025 – 31 Dec 2027)
  4. Disabled individual additional relief raised to RM7,000 (from RM6,000)
  5. Disabled spouse additional relief raised to RM6,000 (from RM5,000)
  6. Year-versioned caps: YA2024 records use old caps, YA2025 use new caps
  7. Historical YA2024 calculations remain unaffected
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
    EmployeeTP1Relief,
    _CAPS_DEFAULT,
    _CAPS_YA2025,
    _get_caps_for_year,
    _RELIEF_FIELDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_doc(**kwargs):
    """Build a mock TP1 doc with default zero-valued fields for YA2025."""
    defaults = {
        "employee": "TEST-EMP-YA2025",
        "tax_year": 2025,
        "name": "TP1-TEST-EMP-YA2025-2025",
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
        "housing_loan_interest_500k": 0,
        "housing_loan_interest_750k": 0,
        "spa_date": None,
        "disability_self": 0,
        "disability_spouse": 0,
        "socso_employee": 0,
        "epf_employee": 0,
        "annual_zakat": 0,
        "total_reliefs": 0,
    }
    defaults.update(kwargs)

    doc = MagicMock(spec=EmployeeTP1Relief)
    doc.meta = MagicMock()
    doc.meta.get_label = lambda f: f.replace("_", " ").title()
    doc.name = defaults["name"]

    for key, val in defaults.items():
        setattr(doc, key, val)

    def _get(field, default=None):
        return getattr(doc, field, default)

    def _set(field, val):
        setattr(doc, field, val)

    doc.get = _get
    doc.set = _set
    return doc


# ---------------------------------------------------------------------------
# Tests — _get_caps_for_year() version control
# ---------------------------------------------------------------------------

class TestGetCapsForYear(FrappeTestCase):
    """_get_caps_for_year() returns the correct cap table for each year."""

    def test_ya2024_returns_default_caps(self):
        caps = _get_caps_for_year(2024)
        self.assertEqual(caps["disability_self"], 6_000,
                         "YA2024 disability_self should be RM6,000")
        self.assertEqual(caps["disability_spouse"], 5_000,
                         "YA2024 disability_spouse should be RM5,000")

    def test_ya2023_returns_default_caps(self):
        caps = _get_caps_for_year(2023)
        self.assertEqual(caps["disability_self"], 6_000)

    def test_ya2025_returns_updated_caps(self):
        caps = _get_caps_for_year(2025)
        self.assertEqual(caps["disability_self"], 7_000,
                         "YA2025 disability_self should be RM7,000")
        self.assertEqual(caps["disability_spouse"], 6_000,
                         "YA2025 disability_spouse should be RM6,000")

    def test_ya2026_returns_ya2025_caps(self):
        """YA2026 and later (not separately defined) fall back to YA2025 caps."""
        caps = _get_caps_for_year(2026)
        self.assertEqual(caps["disability_self"], 7_000)
        self.assertEqual(caps["disability_spouse"], 6_000)

    def test_ya2025_has_housing_loan_interest_500k_cap(self):
        caps = _get_caps_for_year(2025)
        self.assertIn("housing_loan_interest_500k", caps,
                      "YA2025 caps must include housing_loan_interest_500k")
        self.assertEqual(caps["housing_loan_interest_500k"], 7_000)

    def test_ya2025_has_housing_loan_interest_750k_cap(self):
        caps = _get_caps_for_year(2025)
        self.assertIn("housing_loan_interest_750k", caps,
                      "YA2025 caps must include housing_loan_interest_750k")
        self.assertEqual(caps["housing_loan_interest_750k"], 5_000)

    def test_ya2024_does_not_have_housing_loan_interest(self):
        """Housing loan interest relief did not exist before YA2025."""
        caps = _get_caps_for_year(2024)
        self.assertNotIn("housing_loan_interest_500k", caps,
                         "YA2024 must not have housing_loan_interest_500k cap")
        self.assertNotIn("housing_loan_interest_750k", caps,
                         "YA2024 must not have housing_loan_interest_750k cap")


# ---------------------------------------------------------------------------
# Tests — disability cap updates (YA2025)
# ---------------------------------------------------------------------------

class TestDisabilityCapUpdates(FrappeTestCase):
    """Budget 2025 raised disability reliefs."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_disability_self_capped_at_7000_for_ya2025(self, mock_frappe):
        """disability_self is capped at RM7,000 (not RM6,000) for YA2025."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(tax_year=2025, disability_self=9_000)
        EmployeeTP1Relief._apply_caps(doc)

        self.assertEqual(doc.disability_self, 7_000,
                         "YA2025 disability_self cap should be RM7,000")
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_disability_self_capped_at_6000_for_ya2024(self, mock_frappe):
        """YA2024 disability_self cap remains at RM6,000 (historical unaffected)."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(tax_year=2024, disability_self=9_000)
        EmployeeTP1Relief._apply_caps(doc)

        self.assertEqual(doc.disability_self, 6_000,
                         "YA2024 disability_self cap should be RM6,000 (old cap)")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_disability_spouse_capped_at_6000_for_ya2025(self, mock_frappe):
        """disability_spouse is capped at RM6,000 for YA2025."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(tax_year=2025, disability_spouse=8_000)
        EmployeeTP1Relief._apply_caps(doc)

        self.assertEqual(doc.disability_spouse, 6_000,
                         "YA2025 disability_spouse cap should be RM6,000")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_disability_spouse_capped_at_5000_for_ya2024(self, mock_frappe):
        """YA2024 disability_spouse cap remains at RM5,000 (historical unaffected)."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(tax_year=2024, disability_spouse=8_000)
        EmployeeTP1Relief._apply_caps(doc)

        self.assertEqual(doc.disability_spouse, 5_000,
                         "YA2024 disability_spouse cap should be RM5,000 (old cap)")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_disability_self_within_7000_not_capped_ya2025(self, mock_frappe):
        """disability_self at exactly RM7,000 is not capped for YA2025."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(tax_year=2025, disability_self=7_000)
        EmployeeTP1Relief._apply_caps(doc)

        self.assertEqual(doc.disability_self, 7_000)
        mock_frappe.msgprint.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — Housing Loan Interest Relief (YA2025)
# ---------------------------------------------------------------------------

class TestHousingLoanInterestRelief(FrappeTestCase):
    """Budget 2025: Housing Loan Interest relief with SPA date validation."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_housing_loan_500k_capped_at_7000(self, mock_frappe):
        """housing_loan_interest_500k is capped at RM7,000 for YA2025."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(tax_year=2025, housing_loan_interest_500k=10_000)
        EmployeeTP1Relief._apply_caps(doc)

        self.assertEqual(doc.housing_loan_interest_500k, 7_000)
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_housing_loan_750k_capped_at_5000(self, mock_frappe):
        """housing_loan_interest_750k is capped at RM5,000 for YA2025."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(tax_year=2025, housing_loan_interest_750k=8_000)
        EmployeeTP1Relief._apply_caps(doc)

        self.assertEqual(doc.housing_loan_interest_750k, 5_000)
        mock_frappe.msgprint.assert_called()

    def test_spa_date_valid_within_window(self):
        """Valid SPA date (2025-06-01) passes validation without error."""
        doc = _make_mock_doc(
            tax_year=2025,
            housing_loan_interest_500k=5_000,
            spa_date="2025-06-01",
        )
        # Should not raise
        EmployeeTP1Relief._validate_spa_date(doc)

    def test_spa_date_first_day_of_window(self):
        """SPA date exactly 1 Jan 2025 is valid."""
        doc = _make_mock_doc(
            tax_year=2025,
            housing_loan_interest_500k=3_000,
            spa_date="2025-01-01",
        )
        EmployeeTP1Relief._validate_spa_date(doc)  # Should not raise

    def test_spa_date_last_day_of_window(self):
        """SPA date exactly 31 Dec 2027 is valid."""
        doc = _make_mock_doc(
            tax_year=2025,
            housing_loan_interest_500k=3_000,
            spa_date="2027-12-31",
        )
        EmployeeTP1Relief._validate_spa_date(doc)  # Should not raise

    def test_spa_date_before_window_raises(self):
        """SPA date before 1 Jan 2025 raises validation error (sunset clause)."""
        doc = _make_mock_doc(
            tax_year=2025,
            housing_loan_interest_500k=5_000,
            spa_date="2024-12-31",
        )
        with self.assertRaises(Exception):
            EmployeeTP1Relief._validate_spa_date(doc)

    def test_spa_date_after_window_raises(self):
        """SPA date after 31 Dec 2027 raises validation error."""
        doc = _make_mock_doc(
            tax_year=2025,
            housing_loan_interest_750k=3_000,
            spa_date="2028-01-01",
        )
        with self.assertRaises(Exception):
            EmployeeTP1Relief._validate_spa_date(doc)

    def test_spa_date_missing_when_housing_claimed_raises(self):
        """Missing SPA date raises error when housing loan interest is non-zero."""
        doc = _make_mock_doc(
            tax_year=2025,
            housing_loan_interest_500k=5_000,
            spa_date=None,
        )
        with self.assertRaises(Exception):
            EmployeeTP1Relief._validate_spa_date(doc)

    def test_spa_date_not_required_when_no_housing_claimed(self):
        """No housing loan interest claimed — SPA date is not required."""
        doc = _make_mock_doc(
            tax_year=2025,
            housing_loan_interest_500k=0,
            housing_loan_interest_750k=0,
            spa_date=None,
        )
        # Should not raise
        EmployeeTP1Relief._validate_spa_date(doc)

    def test_housing_interest_in_ya2024_raises(self):
        """Claiming housing loan interest for YA2024 raises an error."""
        doc = _make_mock_doc(
            tax_year=2024,
            housing_loan_interest_500k=5_000,
            spa_date="2025-06-01",
        )
        with self.assertRaises(Exception):
            EmployeeTP1Relief._validate_spa_date(doc)


# ---------------------------------------------------------------------------
# Tests — _RELIEF_FIELDS includes new YA2025 fields
# ---------------------------------------------------------------------------

class TestReliefFieldsRegistry(FrappeTestCase):
    """_RELIEF_FIELDS must include all new YA2025 relief field names."""

    def test_housing_loan_500k_in_relief_fields(self):
        self.assertIn("housing_loan_interest_500k", _RELIEF_FIELDS,
                      "housing_loan_interest_500k must be in _RELIEF_FIELDS for total calculation")

    def test_housing_loan_750k_in_relief_fields(self):
        self.assertIn("housing_loan_interest_750k", _RELIEF_FIELDS,
                      "housing_loan_interest_750k must be in _RELIEF_FIELDS for total calculation")

    def test_disability_spouse_in_relief_fields(self):
        self.assertIn("disability_spouse", _RELIEF_FIELDS,
                      "disability_spouse must be in _RELIEF_FIELDS for total calculation")


# ---------------------------------------------------------------------------
# Tests — _calculate_total() includes new fields
# ---------------------------------------------------------------------------

class TestCalculateTotalYA2025(FrappeTestCase):
    """_calculate_total() correctly sums new YA2025 relief fields."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_total_includes_housing_loan_500k(self, mock_frappe):
        """housing_loan_interest_500k is included in total_reliefs."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(
            tax_year=2025,
            self_relief=9_000,
            housing_loan_interest_500k=7_000,
        )
        EmployeeTP1Relief._calculate_total(doc)

        self.assertEqual(doc.total_reliefs, 16_000,
                         "Total should include self_relief + housing_loan_interest_500k")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_total_includes_housing_loan_750k(self, mock_frappe):
        """housing_loan_interest_750k is included in total_reliefs."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(
            tax_year=2025,
            self_relief=9_000,
            housing_loan_interest_750k=5_000,
        )
        EmployeeTP1Relief._calculate_total(doc)

        self.assertEqual(doc.total_reliefs, 14_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_total_includes_disability_spouse(self, mock_frappe):
        """disability_spouse is included in total_reliefs."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(
            tax_year=2025,
            self_relief=9_000,
            disability_self=7_000,
            disability_spouse=6_000,
        )
        EmployeeTP1Relief._calculate_total(doc)

        self.assertEqual(doc.total_reliefs, 22_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_total_all_ya2025_fields_combined(self, mock_frappe):
        """All YA2025 new fields contribute to total correctly."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(
            tax_year=2025,
            self_relief=9_000,
            disability_self=7_000,
            disability_spouse=6_000,
            housing_loan_interest_500k=7_000,
            annual_zakat=500,  # Must NOT be included
        )
        EmployeeTP1Relief._calculate_total(doc)

        # 9000 + 7000 + 6000 + 7000 = 29000 (zakat excluded)
        self.assertEqual(doc.total_reliefs, 29_000,
                         "Zakat must be excluded from total_reliefs")


# ---------------------------------------------------------------------------
# Tests — Backward compatibility: YA2024 calculations unaffected
# ---------------------------------------------------------------------------

class TestBackwardCompatibilityYA2024(FrappeTestCase):
    """Historical YA2024 calculations are not affected by YA2025 cap changes."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2024_disability_self_old_cap_still_applies(self, mock_frappe):
        """A YA2024 TP1 record uses the old RM6,000 disability_self cap."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(tax_year=2024, disability_self=7_000)
        EmployeeTP1Relief._apply_caps(doc)

        self.assertEqual(doc.disability_self, 6_000,
                         "YA2024 must still cap disability_self at RM6,000")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2024_disability_spouse_old_cap_still_applies(self, mock_frappe):
        """A YA2024 TP1 record uses the old RM5,000 disability_spouse cap."""
        mock_frappe.db.get_value.return_value = None

        doc = _make_mock_doc(tax_year=2024, disability_spouse=6_000)
        EmployeeTP1Relief._apply_caps(doc)

        self.assertEqual(doc.disability_spouse, 5_000,
                         "YA2024 must still cap disability_spouse at RM5,000")

    def test_ya2024_caps_unchanged_constants(self):
        """_CAPS_DEFAULT constants have not been mutated by YA2025 changes."""
        self.assertEqual(_CAPS_DEFAULT.get("disability_self"), 6_000)
        self.assertEqual(_CAPS_DEFAULT.get("disability_spouse"), 5_000)
        self.assertNotIn("housing_loan_interest_500k", _CAPS_DEFAULT)
        self.assertNotIn("housing_loan_interest_750k", _CAPS_DEFAULT)

    def test_ya2025_caps_have_new_values(self):
        """_CAPS_YA2025 constants reflect the Budget 2025 updates."""
        self.assertEqual(_CAPS_YA2025.get("disability_self"), 7_000)
        self.assertEqual(_CAPS_YA2025.get("disability_spouse"), 6_000)
        self.assertEqual(_CAPS_YA2025.get("housing_loan_interest_500k"), 7_000)
        self.assertEqual(_CAPS_YA2025.get("housing_loan_interest_750k"), 5_000)
