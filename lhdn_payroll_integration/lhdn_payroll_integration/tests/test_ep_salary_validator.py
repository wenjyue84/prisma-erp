"""Tests for US-142: Employment Pass Minimum Salary Threshold Validator.

Covers:
1. get_ep_threshold: returns correct minimum for Cat I/II/III
2. get_ep_threshold: returns None when no threshold record exists
3. get_ep_threshold: respects effective_date (returns None before policy date)
4. validate_ep_salary_before_submit: non-EP holder (Not Applicable) is skipped
5. validate_ep_salary_before_submit: EP holder above threshold passes
6. validate_ep_salary_before_submit: EP holder below threshold without justification raises
7. validate_ep_salary_before_submit: EP holder below threshold WITH justification allowed
8. validate_ep_salary_before_submit: period before effective date is skipped
9. EP categories constant contains Cat I, Cat II, Cat III
10. get_ep_holder_compliance: returns list structure (no crash when no employees)
"""
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_salary_validator import (
    EP_CATEGORIES,
    EP_POLICY_EFFECTIVE_DATE,
    get_ep_holder_compliance,
    get_ep_threshold,
    validate_ep_salary_before_submit,
)


class TestEPThresholdLookup(FrappeTestCase):
    """Tests for get_ep_threshold()."""

    def setUp(self):
        # Seed threshold records for testing
        for category, minimum in [
            ("Cat I", 20000.0),
            ("Cat II", 10000.0),
            ("Cat III", 5000.0),
        ]:
            if not frappe.db.exists("EP Salary Threshold", category):
                doc = frappe.get_doc(
                    {
                        "doctype": "EP Salary Threshold",
                        "category": category,
                        "minimum_salary_rm": minimum,
                        "effective_date": "2026-06-01",
                    }
                )
                doc.insert(ignore_permissions=True)
        frappe.db.commit()

    def test_cat_i_threshold(self):
        """Cat I minimum should be RM20,000."""
        threshold = get_ep_threshold("Cat I", "2026-06-01")
        self.assertEqual(threshold, 20000.0)

    def test_cat_ii_threshold(self):
        """Cat II minimum should be RM10,000."""
        threshold = get_ep_threshold("Cat II", "2026-06-01")
        self.assertEqual(threshold, 10000.0)

    def test_cat_iii_threshold(self):
        """Cat III minimum should be RM5,000."""
        threshold = get_ep_threshold("Cat III", "2026-06-01")
        self.assertEqual(threshold, 5000.0)

    def test_threshold_before_effective_date_returns_none(self):
        """Threshold lookup before effective date should return None."""
        threshold = get_ep_threshold("Cat I", "2026-05-31")
        self.assertIsNone(threshold)

    def test_threshold_for_unknown_category_returns_none(self):
        """Unknown category should return None."""
        threshold = get_ep_threshold("Cat X", "2026-06-01")
        self.assertIsNone(threshold)

    def test_threshold_on_effective_date(self):
        """Threshold on exactly effective_date should be returned."""
        threshold = get_ep_threshold("Cat III", EP_POLICY_EFFECTIVE_DATE)
        self.assertIsNotNone(threshold)
        self.assertGreater(threshold, 0)

    def test_threshold_after_effective_date(self):
        """Threshold on date after effective_date should still be returned."""
        threshold = get_ep_threshold("Cat II", "2026-12-31")
        self.assertIsNotNone(threshold)
        self.assertEqual(threshold, 10000.0)


class TestEPSalaryValidation(FrappeTestCase):
    """Tests for validate_ep_salary_before_submit()."""

    def _make_slip(self, ep_category, gross_pay, period_end, justification=""):
        """Build a minimal mock Salary Slip doc."""
        doc = MagicMock()
        doc.employee = "EMP001"
        doc.employee_name = "Test Expatriate"
        doc.name = "SLIP-TEST-001"
        doc.gross_pay = gross_pay
        doc.end_date = period_end
        doc.get = lambda field, default=None: {
            "end_date": period_end,
            "period_end": period_end,
            "custom_ep_override_justification": justification,
        }.get(field, default)
        return doc

    def _mock_ep_category(self, category):
        """Patch frappe.db.get_value to return given EP category."""
        return patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ep_salary_validator.frappe.db.get_value",
            return_value=category,
        )

    def _mock_threshold(self, threshold_value):
        """Patch get_ep_threshold to return a fixed value."""
        return patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ep_salary_validator.get_ep_threshold",
            return_value=threshold_value,
        )

    def test_non_ep_holder_skipped(self):
        """Employee with 'Not Applicable' EP category should not be validated."""
        doc = self._make_slip("Not Applicable", 3000.0, "2026-06-15")
        with self._mock_ep_category("Not Applicable"):
            # Should not raise
            validate_ep_salary_before_submit(doc)

    def test_no_ep_category_skipped(self):
        """Employee with no EP category should not be validated."""
        doc = self._make_slip(None, 3000.0, "2026-06-15")
        with self._mock_ep_category(None):
            validate_ep_salary_before_submit(doc)

    def test_ep_holder_above_threshold_passes(self):
        """Cat I EP holder with gross >= RM20,000 should pass."""
        doc = self._make_slip("Cat I", 25000.0, "2026-06-15")
        with self._mock_ep_category("Cat I"), self._mock_threshold(20000.0):
            validate_ep_salary_before_submit(doc)  # Must not raise

    def test_ep_holder_exactly_at_threshold_passes(self):
        """Cat II EP holder with gross == RM10,000 (exactly at threshold) should pass."""
        doc = self._make_slip("Cat II", 10000.0, "2026-06-15")
        with self._mock_ep_category("Cat II"), self._mock_threshold(10000.0):
            validate_ep_salary_before_submit(doc)

    def test_ep_holder_below_threshold_raises(self):
        """Cat I EP holder with gross < RM20,000 and no justification should raise."""
        doc = self._make_slip("Cat I", 15000.0, "2026-06-15", justification="")
        with self._mock_ep_category("Cat I"), self._mock_threshold(20000.0):
            with self.assertRaises(frappe.exceptions.ValidationError):
                validate_ep_salary_before_submit(doc)

    def test_ep_holder_below_threshold_with_justification_allowed(self):
        """Cat I EP holder below threshold WITH justification should be allowed."""
        doc = self._make_slip(
            "Cat I",
            15000.0,
            "2026-06-15",
            justification="Increment letter dated 1 Jul pending MyTax update",
        )
        with self._mock_ep_category("Cat I"), self._mock_threshold(20000.0):
            with patch(
                "lhdn_payroll_integration.lhdn_payroll_integration.services.ep_salary_validator.frappe.get_doc",
                return_value=MagicMock(insert=MagicMock()),
            ):
                validate_ep_salary_before_submit(doc)  # Must not raise

    def test_period_before_effective_date_skipped(self):
        """EP holder with period_end before 2026-06-01 should not be validated."""
        doc = self._make_slip("Cat I", 5000.0, "2026-05-31")
        with self._mock_ep_category("Cat I"), self._mock_threshold(None):
            validate_ep_salary_before_submit(doc)  # Should not raise (threshold is None)

    def test_no_threshold_configured_skipped(self):
        """When no threshold record exists, validation should be skipped."""
        doc = self._make_slip("Cat I", 1000.0, "2026-06-15")
        with self._mock_ep_category("Cat I"), self._mock_threshold(None):
            validate_ep_salary_before_submit(doc)  # Should not raise


class TestEPConstants(FrappeTestCase):
    """Tests for module-level constants."""

    def test_ep_categories_set(self):
        """EP_CATEGORIES should contain all three categories."""
        self.assertIn("Cat I", EP_CATEGORIES)
        self.assertIn("Cat II", EP_CATEGORIES)
        self.assertIn("Cat III", EP_CATEGORIES)

    def test_ep_policy_effective_date(self):
        """EP_POLICY_EFFECTIVE_DATE should be June 1, 2026."""
        self.assertEqual(EP_POLICY_EFFECTIVE_DATE, "2026-06-01")


class TestEPHolderComplianceReport(FrappeTestCase):
    """Tests for get_ep_holder_compliance()."""

    def test_returns_list(self):
        """get_ep_holder_compliance should return a list."""
        result = get_ep_holder_compliance("2026-06-01")
        self.assertIsInstance(result, list)

    def test_compliance_row_structure(self):
        """Each row must contain required keys."""
        required_keys = {
            "employee", "employee_name", "ep_category", "ep_number",
            "ep_expiry_date", "latest_gross", "minimum_required",
            "compliant", "days_to_expiry",
        }
        result = get_ep_holder_compliance("2026-06-01")
        for row in result:
            for key in required_keys:
                self.assertIn(key, row, f"Missing key '{key}' in compliance row")
