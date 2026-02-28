"""Tests for US-076: Age-Based EPF/SOCSO/EIS Statutory Rate Transitions at Age 60.

Covers:
- get_statutory_rates_for_employee() in utils/statutory_rates.py
- validate_statutory_rates_before_submit() hook on Salary Slip
- check_approaching_age_60() daily scheduler
- EPF/SOCSO/EIS rate constants for age 60+
"""
from datetime import date
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestAge60RateConstants(FrappeTestCase):
    """Verify age-60 rate constants are exported from statutory_rates."""

    def test_over_60_employee_rate_exported(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            EPF_OVER_60_EMPLOYEE_RATE,
        )
        self.assertAlmostEqual(EPF_OVER_60_EMPLOYEE_RATE, 0.055)

    def test_over_60_employer_rate_exported(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            EPF_OVER_60_EMPLOYER_RATE,
        )
        self.assertAlmostEqual(EPF_OVER_60_EMPLOYER_RATE, 0.04)

    def test_standard_employee_rate_exported(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            EPF_STANDARD_EMPLOYEE_RATE,
        )
        self.assertAlmostEqual(EPF_STANDARD_EMPLOYEE_RATE, 0.11)


# ---------------------------------------------------------------------------
# get_statutory_rates_for_employee()
# ---------------------------------------------------------------------------

class TestGetStatutoryRatesForEmployee(FrappeTestCase):
    """Verify get_statutory_rates_for_employee() returns correct age-based rates."""

    PAYROLL_DATE = date(2025, 6, 15)

    def _mock_employee(self, dob):
        emp = MagicMock()
        emp.date_of_birth = dob
        return emp

    def _dob_for_age(self, age):
        """Return a date_of_birth that makes the employee exactly *age* on PAYROLL_DATE."""
        return date(
            self.PAYROLL_DATE.year - age,
            self.PAYROLL_DATE.month,
            self.PAYROLL_DATE.day,
        )

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates.frappe")
    def test_age_59_returns_standard_rates(self, mock_frappe):
        """Age 59 employee → standard EPF 11%, SOCSO=True, EIS=True, over_60=False."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            get_statutory_rates_for_employee,
        )
        mock_frappe.get_doc.return_value = self._mock_employee(self._dob_for_age(59))

        rates = get_statutory_rates_for_employee("EMP-001", self.PAYROLL_DATE)

        self.assertFalse(rates["over_60"])
        self.assertAlmostEqual(rates["epf_employee_rate"], 0.11)
        self.assertIsNone(rates["epf_employer_rate"])
        self.assertTrue(rates["socso_covered"])
        self.assertTrue(rates["eis_covered"])
        self.assertEqual(rates["age"], 59)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates.frappe")
    def test_age_60_returns_over_60_rates(self, mock_frappe):
        """Age 60 employee → EPF 5.5%/4%, SOCSO=False, EIS=False, over_60=True."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            get_statutory_rates_for_employee,
        )
        mock_frappe.get_doc.return_value = self._mock_employee(self._dob_for_age(60))

        rates = get_statutory_rates_for_employee("EMP-001", self.PAYROLL_DATE)

        self.assertTrue(rates["over_60"])
        self.assertAlmostEqual(rates["epf_employee_rate"], 0.055)
        self.assertAlmostEqual(rates["epf_employer_rate"], 0.04)
        self.assertFalse(rates["socso_covered"])
        self.assertFalse(rates["eis_covered"])
        self.assertEqual(rates["age"], 60)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates.frappe")
    def test_employee_turning_60_on_payroll_date(self, mock_frappe):
        """Employee whose 60th birthday is exactly the payroll date → over-60 rates."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            get_statutory_rates_for_employee,
        )
        dob = date(1965, 6, 15)  # exactly 60 on payroll_date 2025-06-15
        mock_frappe.get_doc.return_value = self._mock_employee(dob)

        rates = get_statutory_rates_for_employee("EMP-001", self.PAYROLL_DATE)

        self.assertTrue(rates["over_60"])
        self.assertAlmostEqual(rates["epf_employee_rate"], 0.055)
        self.assertAlmostEqual(rates["epf_employer_rate"], 0.04)
        self.assertFalse(rates["socso_covered"])
        self.assertFalse(rates["eis_covered"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates.frappe")
    def test_employee_one_day_before_60(self, mock_frappe):
        """Employee who turns 60 one day AFTER payroll date → still pre-transition."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            get_statutory_rates_for_employee,
        )
        # DOB: 2025-06-16 minus 60 years → turns 60 on 2025-06-16, which is after payroll_date
        dob = date(1965, 6, 16)
        mock_frappe.get_doc.return_value = self._mock_employee(dob)

        rates = get_statutory_rates_for_employee("EMP-001", self.PAYROLL_DATE)

        self.assertFalse(rates["over_60"])
        self.assertAlmostEqual(rates["epf_employee_rate"], 0.11)
        self.assertTrue(rates["socso_covered"])
        self.assertTrue(rates["eis_covered"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates.frappe")
    def test_age_65_also_returns_over_60_rates(self, mock_frappe):
        """Age 65 employee → still uses over-60 rates (no upper cutoff)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            get_statutory_rates_for_employee,
        )
        mock_frappe.get_doc.return_value = self._mock_employee(self._dob_for_age(65))

        rates = get_statutory_rates_for_employee("EMP-001", self.PAYROLL_DATE)

        self.assertTrue(rates["over_60"])
        self.assertAlmostEqual(rates["epf_employee_rate"], 0.055)
        self.assertAlmostEqual(rates["epf_employer_rate"], 0.04)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates.frappe")
    def test_return_dict_has_required_keys(self, mock_frappe):
        """Return dict must contain all required keys for both age groups."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            get_statutory_rates_for_employee,
        )
        required_keys = {"epf_employee_rate", "epf_employer_rate", "socso_covered", "eis_covered", "age", "over_60"}

        for age in (30, 59, 60, 65):
            mock_frappe.get_doc.return_value = self._mock_employee(self._dob_for_age(age))
            rates = get_statutory_rates_for_employee("EMP-001", self.PAYROLL_DATE)
            self.assertEqual(required_keys, set(rates.keys()), f"Missing keys for age {age}")


# ---------------------------------------------------------------------------
# validate_statutory_rates_before_submit()
# ---------------------------------------------------------------------------

class TestSalarySlipAgeValidation(FrappeTestCase):
    """Verify before_submit hook warns for over-60 statutory rate mismatches."""

    PAYROLL_DATE = date(2025, 6, 15)

    def _make_salary_slip(self, employee, end_date, deductions=None, gross_pay=5000):
        doc = MagicMock()
        doc.employee = employee
        doc.end_date = end_date
        doc.posting_date = end_date
        doc.gross_pay = gross_pay
        doc.get = MagicMock(return_value=deductions or [])
        return doc

    def _make_deduction_row(self, component, amount):
        row = MagicMock()
        row.salary_component = component
        row.amount = amount
        return row

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.frappe")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.get_statutory_rates_for_employee")
    def test_no_warning_for_under_60(self, mock_get_rates, mock_frappe):
        """Age < 60 → hook returns without any warning."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service import (
            validate_statutory_rates_before_submit,
        )
        mock_get_rates.return_value = {
            "over_60": False, "age": 45,
            "epf_employee_rate": 0.11, "epf_employer_rate": None,
            "socso_covered": True, "eis_covered": True,
        }
        doc = self._make_salary_slip("EMP-001", "2025-06-30")
        validate_statutory_rates_before_submit(doc, "before_submit")
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.frappe")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.get_statutory_rates_for_employee")
    def test_warns_when_socso_nonzero_for_over_60(self, mock_get_rates, mock_frappe):
        """Age >= 60 with SOCSO > 0 → msgprint warning issued."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service import (
            validate_statutory_rates_before_submit,
        )
        mock_get_rates.return_value = {
            "over_60": True, "age": 60,
            "epf_employee_rate": 0.055, "epf_employer_rate": 0.04,
            "socso_covered": False, "eis_covered": False,
        }
        socso_row = self._make_deduction_row("SOCSO Employee", 15.05)
        doc = self._make_salary_slip("EMP-001", "2025-06-30", deductions=[socso_row])

        validate_statutory_rates_before_submit(doc, "before_submit")

        mock_frappe.msgprint.assert_called_once()
        call_args = mock_frappe.msgprint.call_args[0][0]
        self.assertIn("SOCSO", call_args)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.frappe")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.get_statutory_rates_for_employee")
    def test_warns_when_eis_nonzero_for_over_60(self, mock_get_rates, mock_frappe):
        """Age >= 60 with EIS > 0 → msgprint warning issued."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service import (
            validate_statutory_rates_before_submit,
        )
        mock_get_rates.return_value = {
            "over_60": True, "age": 60,
            "epf_employee_rate": 0.055, "epf_employer_rate": 0.04,
            "socso_covered": False, "eis_covered": False,
        }
        eis_row = self._make_deduction_row("EIS Employee", 12.00)
        doc = self._make_salary_slip("EMP-001", "2025-06-30", deductions=[eis_row])

        validate_statutory_rates_before_submit(doc, "before_submit")

        mock_frappe.msgprint.assert_called_once()
        call_args = mock_frappe.msgprint.call_args[0][0]
        self.assertIn("EIS", call_args)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.frappe")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.get_statutory_rates_for_employee")
    def test_no_warning_when_over_60_and_zero_socso_eis(self, mock_get_rates, mock_frappe):
        """Age >= 60 with SOCSO=0 and EIS=0 and correct EPF → no warning."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service import (
            validate_statutory_rates_before_submit,
        )
        mock_get_rates.return_value = {
            "over_60": True, "age": 62,
            "epf_employee_rate": 0.055, "epf_employer_rate": 0.04,
            "socso_covered": False, "eis_covered": False,
        }
        # EPF at 5.5% of 5000 = 275, zero SOCSO/EIS
        epf_row = self._make_deduction_row("EPF Employee", 275.0)
        doc = self._make_salary_slip("EMP-001", "2025-06-30", deductions=[epf_row], gross_pay=5000)

        validate_statutory_rates_before_submit(doc, "before_submit")

        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.frappe")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.get_statutory_rates_for_employee")
    def test_no_exception_propagated_on_error(self, mock_get_rates, mock_frappe):
        """Errors inside the hook are logged, not raised (never block submission)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service import (
            validate_statutory_rates_before_submit,
        )
        mock_get_rates.side_effect = Exception("DB error")
        doc = self._make_salary_slip("EMP-001", "2025-06-30")

        # Must not raise
        try:
            validate_statutory_rates_before_submit(doc, "before_submit")
        except Exception:
            self.fail("validate_statutory_rates_before_submit raised an exception unexpectedly")

        mock_frappe.log_error.assert_called_once()


# ---------------------------------------------------------------------------
# check_approaching_age_60() — daily scheduler
# ---------------------------------------------------------------------------

class TestCheckApproachingAge60(FrappeTestCase):
    """Verify daily scheduler creates ToDo alerts for employees near 60th birthday."""

    def _make_employee_record(self, name, emp_name, days_until_60):
        today = date.today()
        birthday_60 = today + __import__('datetime').timedelta(days=days_until_60)
        # Compute a DOB that gives this birthday
        dob = date(birthday_60.year - 60, birthday_60.month, birthday_60.day)
        return {
            "name": name,
            "employee_name": emp_name,
            "date_of_birth": dob,
            "company": "Test Company",
        }

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.frappe")
    def test_no_alert_for_employee_over_90_days_away(self, mock_frappe):
        """Employee turning 60 in 120 days → no ToDo created."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service import (
            check_approaching_age_60,
        )
        emp = self._make_employee_record("EMP-100", "Ali", 120)
        mock_frappe.get_all.side_effect = [
            [emp],   # Employee query
            [],      # existing ToDo check
        ]
        mock_frappe.get_doc.return_value = MagicMock()

        check_approaching_age_60()

        # get_doc for ToDo insert should NOT be called since 120 > 90 days
        todo_calls = [c for c in mock_frappe.get_doc.call_args_list
                      if c[0] and isinstance(c[0][0], dict) and c[0][0].get("doctype") == "ToDo"]
        self.assertEqual(len(todo_calls), 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.frappe")
    def test_alert_created_for_employee_within_90_days(self, mock_frappe):
        """Employee turning 60 in 60 days → ToDo created."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service import (
            check_approaching_age_60,
        )
        emp = self._make_employee_record("EMP-200", "Tan Ah Kow", 60)
        mock_frappe.get_all.side_effect = [
            [emp],   # Employee query
            [],      # existing ToDo check — none found
        ]
        mock_todo = MagicMock()
        mock_frappe.get_doc.return_value = mock_todo

        check_approaching_age_60()

        todo_calls = [c for c in mock_frappe.get_doc.call_args_list
                      if c[0] and isinstance(c[0][0], dict) and c[0][0].get("doctype") == "ToDo"]
        self.assertEqual(len(todo_calls), 1)
        todo_data = todo_calls[0][0][0]
        self.assertIn("turns 60", todo_data["description"])
        self.assertEqual(todo_data["reference_name"], "EMP-200")
        mock_todo.insert.assert_called_once()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.frappe")
    def test_no_duplicate_todo_when_already_exists(self, mock_frappe):
        """If an open ToDo already exists for this employee, skip creating another."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service import (
            check_approaching_age_60,
        )
        emp = self._make_employee_record("EMP-300", "Rahman", 30)
        mock_frappe.get_all.side_effect = [
            [emp],                    # Employee query
            [{"name": "TODO-001"}],   # existing ToDo found
        ]
        mock_frappe.get_doc.return_value = MagicMock()

        check_approaching_age_60()

        todo_calls = [c for c in mock_frappe.get_doc.call_args_list
                      if c[0] and isinstance(c[0][0], dict) and c[0][0].get("doctype") == "ToDo"]
        self.assertEqual(len(todo_calls), 0, "Should not create duplicate ToDo")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.frappe")
    def test_no_active_employees_no_crash(self, mock_frappe):
        """No active employees → function completes without error."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service import (
            check_approaching_age_60,
        )
        mock_frappe.get_all.return_value = []

        # Should not raise
        check_approaching_age_60()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service.frappe")
    def test_alert_description_mentions_statutory_change(self, mock_frappe):
        """ToDo description must mention EPF and SOCSO changes."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.age_checker_service import (
            check_approaching_age_60,
        )
        emp = self._make_employee_record("EMP-400", "Siti", 45)
        mock_frappe.get_all.side_effect = [
            [emp],
            [],
        ]
        mock_todo = MagicMock()
        mock_frappe.get_doc.return_value = mock_todo

        check_approaching_age_60()

        todo_calls = [c for c in mock_frappe.get_doc.call_args_list
                      if c[0] and isinstance(c[0][0], dict) and c[0][0].get("doctype") == "ToDo"]
        desc = todo_calls[0][0][0]["description"]
        self.assertIn("EPF", desc)
        self.assertIn("SOCSO", desc)
