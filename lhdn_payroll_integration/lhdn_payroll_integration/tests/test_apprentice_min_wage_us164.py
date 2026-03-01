"""Tests for US-164: Extend Minimum Wage Enforcement to Apprenticeship Contract Workers.

NWCC Amendment Act 2025, effective 1 August 2025:
- 'Apprentice' and 'Contract Trainee' employee types must receive >= RM1,700/month
- Domestic workers remain the sole exempt category
- No false positives for historical payroll runs before 1 August 2025

Covers:
- APPRENTICE_TYPES and DOMESTIC_WORKER_TYPES constants
- check_minimum_wage_with_headcount() with Apprentice / Contract Trainee types
- Pre-enforcement date: no validation
- Post-enforcement date: RM1,700 floor, regardless of headcount
- Domestic worker: always exempt
- Integration: _validate_salary_slip_minimum_wage dispatches correctly
"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.employment_compliance import (
    APPRENTICE_ENFORCEMENT_DATE,
    APPRENTICE_TYPES,
    DOMESTIC_WORKER_TYPES,
    check_minimum_wage_with_headcount,
)


class TestApprenticeConstants(FrappeTestCase):
    """Verify the new US-164 constants are exported and correct."""

    def test_apprentice_types_contains_apprentice(self):
        self.assertIn("Apprentice", APPRENTICE_TYPES)

    def test_apprentice_types_contains_contract_trainee(self):
        self.assertIn("Contract Trainee", APPRENTICE_TYPES)

    def test_domestic_worker_types_contains_domestic_worker(self):
        self.assertIn("Domestic Worker", DOMESTIC_WORKER_TYPES)

    def test_apprentice_enforcement_date_is_aug_2025(self):
        self.assertEqual(APPRENTICE_ENFORCEMENT_DATE, "2025-08-01")


class TestApprenticePreEnforcement(FrappeTestCase):
    """Before 1 August 2025, apprentice salaries are not validated."""

    def _check(self, emp_type, date_str, salary, headcount=1):
        return check_minimum_wage_with_headcount(
            monthly_salary=salary,
            period_end_date=date_str,
            employer_headcount=headcount,
            employment_type=emp_type,
        )

    def test_apprentice_before_aug_2025_below_minimum_is_compliant(self):
        result = self._check("Apprentice", "2025-07-31", 1000)
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_apprentice_jul_2025_micro_employer_compliant(self):
        result = self._check("Apprentice", "2025-07-31", 800, headcount=2)
        self.assertTrue(result["compliant"])
        self.assertTrue(result["grace_period"])

    def test_contract_trainee_before_aug_2025_is_compliant(self):
        result = self._check("Contract Trainee", "2025-06-30", 1200)
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_apprentice_before_aug_2025_large_employer_still_compliant(self):
        """Even large employers: apprentices not covered before Aug 2025."""
        result = self._check("Apprentice", "2025-07-31", 1500, headcount=100)
        self.assertTrue(result["compliant"])

    def test_apprentice_exact_boundary_jul_31_compliant(self):
        result = self._check("Apprentice", "2025-07-31", 500)
        self.assertTrue(result["compliant"])

    def test_apprentice_before_any_enforcement_2025_jan(self):
        result = self._check("Apprentice", "2025-01-31", 100)
        self.assertTrue(result["compliant"])


class TestApprenticePostEnforcement(FrappeTestCase):
    """From 1 August 2025, apprentices and contract trainees must get >= RM1,700."""

    def _check(self, emp_type, date_str, salary, headcount=1):
        return check_minimum_wage_with_headcount(
            monthly_salary=salary,
            period_end_date=date_str,
            employer_headcount=headcount,
            employment_type=emp_type,
        )

    def test_apprentice_aug_2025_below_minimum_fails(self):
        result = self._check("Apprentice", "2025-08-01", 1500)
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])

    def test_apprentice_aug_2025_at_minimum_passes(self):
        result = self._check("Apprentice", "2025-08-01", 1700)
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_apprentice_aug_2025_above_minimum_passes(self):
        result = self._check("Apprentice", "2025-08-31", 2000)
        self.assertTrue(result["compliant"])

    def test_contract_trainee_aug_2025_below_minimum_fails(self):
        result = self._check("Contract Trainee", "2025-08-01", 1400)
        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])

    def test_contract_trainee_aug_2025_at_minimum_passes(self):
        result = self._check("Contract Trainee", "2025-08-01", 1700)
        self.assertTrue(result["compliant"])

    def test_apprentice_jan_2026_below_minimum_fails(self):
        result = self._check("Apprentice", "2026-01-31", 1000)
        self.assertFalse(result["compliant"])

    def test_apprentice_post_enforcement_micro_employer_still_fails(self):
        """Micro-employer (1 employee) is NOT exempt for apprentices from Aug 2025."""
        result = self._check("Apprentice", "2025-08-01", 1200, headcount=1)
        self.assertFalse(result["compliant"])

    def test_exact_boundary_aug_1_enforced(self):
        result_before = self._check("Apprentice", "2025-07-31", 1000)
        result_after = self._check("Apprentice", "2025-08-01", 1000)
        self.assertTrue(result_before["compliant"])
        self.assertFalse(result_after["compliant"])

    def test_warning_message_mentions_nwcc_amendment(self):
        result = self._check("Apprentice", "2025-08-31", 1500)
        self.assertIn("1500", result["warning"])
        self.assertIn("1700", result["warning"])
        self.assertIn("NWCC", result["warning"])

    def test_result_minimum_is_1700_post_enforcement(self):
        result = self._check("Apprentice", "2025-08-31", 1500)
        self.assertEqual(result["minimum"], 1700.0)

    def test_result_actual_reflects_salary(self):
        result = self._check("Contract Trainee", "2025-08-31", 1400)
        self.assertEqual(result["actual"], 1400.0)

    def test_result_grace_period_false_post_enforcement(self):
        result = self._check("Apprentice", "2025-08-31", 1500)
        self.assertFalse(result["grace_period"])


class TestDomesticWorkerExemption(FrappeTestCase):
    """Domestic workers are always exempt from minimum wage validation."""

    def _check(self, emp_type, date_str, salary, headcount=10):
        return check_minimum_wage_with_headcount(
            monthly_salary=salary,
            period_end_date=date_str,
            employer_headcount=headcount,
            employment_type=emp_type,
        )

    def test_domestic_worker_before_aug_2025_exempt(self):
        result = self._check("Domestic Worker", "2025-01-31", 800)
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_domestic_worker_after_aug_2025_exempt(self):
        result = self._check("Domestic Worker", "2025-09-30", 500)
        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])

    def test_domestic_worker_large_employer_still_exempt(self):
        result = self._check("Domestic Worker", "2026-01-31", 300, headcount=100)
        self.assertTrue(result["compliant"])

    def test_domestic_worker_minimum_is_none(self):
        result = self._check("Domestic Worker", "2025-08-31", 500)
        self.assertIsNone(result["minimum"])

    def test_domestic_worker_not_grace_period(self):
        """Exempt due to type, not grace period — grace_period flag should be False."""
        result = self._check("Domestic Worker", "2025-08-31", 500)
        self.assertFalse(result["grace_period"])

    def test_domestic_worker_mohr_exempt_false(self):
        result = self._check("Domestic Worker", "2025-08-31", 500)
        self.assertFalse(result["mohr_exempt"])

    def test_domestic_type_variants_exempt(self):
        """All variant spellings of domestic worker type are exempt."""
        for emp_type in ["Domestic Worker", "Domestic", "Domestic Help"]:
            result = self._check(emp_type, "2025-08-31", 500)
            self.assertTrue(result["compliant"], f"Expected exempt for '{emp_type}'")


class TestApprenticeResultStructure(FrappeTestCase):
    """Result dict has all required keys in all apprentice code paths."""

    REQUIRED_KEYS = ["compliant", "warning", "employment_type", "minimum", "actual",
                     "grace_period", "mohr_exempt"]

    def _assert_keys(self, result):
        for key in self.REQUIRED_KEYS:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_pre_enforcement_result_has_all_keys(self):
        result = check_minimum_wage_with_headcount(
            monthly_salary=1000, period_end_date="2025-07-31",
            employer_headcount=1, employment_type="Apprentice",
        )
        self._assert_keys(result)

    def test_post_enforcement_fail_result_has_all_keys(self):
        result = check_minimum_wage_with_headcount(
            monthly_salary=1000, period_end_date="2025-08-31",
            employer_headcount=1, employment_type="Apprentice",
        )
        self._assert_keys(result)

    def test_post_enforcement_pass_result_has_all_keys(self):
        result = check_minimum_wage_with_headcount(
            monthly_salary=1700, period_end_date="2025-08-31",
            employer_headcount=1, employment_type="Apprentice",
        )
        self._assert_keys(result)

    def test_domestic_exempt_result_has_all_keys(self):
        result = check_minimum_wage_with_headcount(
            monthly_salary=500, period_end_date="2025-08-31",
            employer_headcount=5, employment_type="Domestic Worker",
        )
        self._assert_keys(result)


class TestApprenticeValidationIntegration(FrappeTestCase):
    """Integration: _validate_salary_slip_minimum_wage handles apprentice type correctly."""

    def _make_doc(self, gross_pay, period_end, emp_type="Apprentice", mohr_ref=None):
        doc = MagicMock()
        data = {
            "doctype": "Salary Slip",
            "base_gross_pay": gross_pay,
            "gross_pay": gross_pay,
            "employee": "EMP-TRAINEE-001",
            "period_end": period_end,
            "company": "Test Co",
            "custom_mohr_exemption_ref": mohr_ref,
        }
        doc.get = lambda key, default=None: data.get(key, default)
        doc.doctype = "Salary Slip"
        return doc

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_apprentice_post_aug_below_wage_throws(self, mock_frappe):
        """Apprentice post-Aug 2025 below RM1,700 triggers hard ValidationError."""
        mock_frappe.db.exists.return_value = True
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Apprentice",
            "custom_contracted_hours_per_month": None,
        }.get(key, default)
        mock_frappe.get_cached_doc.return_value = emp
        mock_frappe.db.count.return_value = 2

        doc = self._make_doc(1200, "2025-08-31")
        from lhdn_payroll_integration.utils.validation import _validate_salary_slip_minimum_wage
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_called_once()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_apprentice_pre_aug_below_wage_no_warning(self, mock_frappe):
        """Apprentice before Aug 2025 — no warning, not yet enforced."""
        mock_frappe.db.exists.return_value = True
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Apprentice",
            "custom_contracted_hours_per_month": None,
        }.get(key, default)
        mock_frappe.get_cached_doc.return_value = emp
        mock_frappe.db.count.return_value = 1

        doc = self._make_doc(800, "2025-07-31")
        from lhdn_payroll_integration.utils.validation import _validate_salary_slip_minimum_wage
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_not_called()
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_domestic_worker_below_wage_no_error(self, mock_frappe):
        """Domestic worker below RM1,700 — always exempt, no error."""
        mock_frappe.db.exists.return_value = True
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Domestic Worker",
            "custom_contracted_hours_per_month": None,
        }.get(key, default)
        mock_frappe.get_cached_doc.return_value = emp
        mock_frappe.db.count.return_value = 5

        doc = self._make_doc(500, "2025-08-31", emp_type="Domestic Worker")
        from lhdn_payroll_integration.utils.validation import _validate_salary_slip_minimum_wage
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_not_called()
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.utils.validation.frappe")
    def test_contract_trainee_post_aug_below_wage_throws(self, mock_frappe):
        """Contract Trainee post-Aug 2025 below RM1,700 triggers hard ValidationError."""
        mock_frappe.db.exists.return_value = True
        emp = MagicMock()
        emp.get = lambda key, default=None: {
            "custom_employment_type": "Contract Trainee",
            "custom_contracted_hours_per_month": None,
        }.get(key, default)
        mock_frappe.get_cached_doc.return_value = emp
        mock_frappe.db.count.return_value = 3

        doc = self._make_doc(1500, "2025-09-30", emp_type="Contract Trainee")
        from lhdn_payroll_integration.utils.validation import _validate_salary_slip_minimum_wage
        _validate_salary_slip_minimum_wage(doc)
        mock_frappe.throw.assert_called_once()
