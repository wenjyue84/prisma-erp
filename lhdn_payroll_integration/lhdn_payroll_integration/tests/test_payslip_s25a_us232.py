"""Tests for US-232: Employment Act S.25A Digital Payslip Mandatory Fields Validator.

Verifies:
1. Service module and functions are importable.
2. check_s25a_fields() returns errors for each missing mandatory field.
3. validate_s25a_mandatory_fields() raises ValidationError when fields are missing.
4. validate_s25a_mandatory_fields() passes for a complete salary slip.
5. run_s25a_audit() is callable and returns a list.
6. Print format includes gender and citizenship status (S.25A fields).
7. Compliance validator hook is registered in hooks.py before_submit.
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

PRINT_FORMAT_HTML = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "print_format",
    "ea_s61_payslip",
    "ea_s61_payslip.html",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_slip(**overrides):
    """Build a minimal mock Salary Slip namespace for unit testing."""
    defaults = dict(
        name="SAL-TEST-001",
        employee="EMP-001",
        employee_name="Ahmad bin Abdullah",
        start_date="2026-01-01",
        end_date="2026-01-31",
        posting_date="2026-01-31",
        gross_pay=5000.0,
        net_pay=4200.0,
        company="Test Company Sdn Bhd",
        deductions=[
            SimpleNamespace(salary_component="EPF Employee", amount=550.0),
            SimpleNamespace(salary_component="SOCSO Employee", amount=29.75),
            SimpleNamespace(salary_component="EIS Employee", amount=11.0),
            SimpleNamespace(salary_component="Monthly Tax Deduction", amount=209.25),
        ],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# 1. Importability
# ---------------------------------------------------------------------------

class TestS25AServiceImportable(FrappeTestCase):
    """Service module and key functions must be importable."""

    def test_module_importable(self):
        try:
            from lhdn_payroll_integration.lhdn_payroll_integration.services import (
                payslip_s25a_service,
            )
            self.assertIsNotNone(payslip_s25a_service)
        except ImportError as e:
            self.fail(f"Cannot import payslip_s25a_service: {e}")

    def test_check_s25a_fields_callable(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.payslip_s25a_service import (
            check_s25a_fields,
        )
        self.assertTrue(callable(check_s25a_fields))

    def test_validate_hook_callable(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.payslip_s25a_service import (
            validate_s25a_mandatory_fields,
        )
        self.assertTrue(callable(validate_s25a_mandatory_fields))

    def test_run_s25a_audit_callable(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.payslip_s25a_service import (
            run_s25a_audit,
        )
        self.assertTrue(callable(run_s25a_audit))


# ---------------------------------------------------------------------------
# 2. check_s25a_fields — individual field validation
# ---------------------------------------------------------------------------

class TestCheckS25AFields(FrappeTestCase):
    """check_s25a_fields() must return errors for each missing mandatory field."""

    def _check(self, **overrides):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.payslip_s25a_service import (
            check_s25a_fields,
        )
        slip = _make_slip(**overrides)
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services."
            "payslip_s25a_service._get_employee_field",
            return_value="901231-01-1234",
        ):
            return check_s25a_fields(slip)

    def test_complete_slip_has_no_errors(self):
        errors = self._check()
        self.assertEqual(errors, [], f"Expected no errors, got: {errors}")

    def test_missing_employee_name_flagged(self):
        errors = self._check(employee_name=None)
        self.assertTrue(
            any("employee_name" in e or "full name" in e.lower() for e in errors),
            f"Expected employee_name error, got: {errors}",
        )

    def test_missing_ic_flagged(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.payslip_s25a_service import (
            check_s25a_fields,
        )
        slip = _make_slip()
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services."
            "payslip_s25a_service._get_employee_field",
            return_value=None,  # no IC value
        ):
            errors = check_s25a_fields(slip)
        self.assertTrue(
            any("IC" in e or "passport" in e.lower() or "custom_id_value" in e for e in errors),
            f"Expected IC/passport error, got: {errors}",
        )

    def test_missing_start_date_flagged(self):
        errors = self._check(start_date=None)
        self.assertTrue(
            any("start_date" in e or "wage period start" in e.lower() for e in errors),
            f"Expected start_date error, got: {errors}",
        )

    def test_missing_end_date_flagged(self):
        errors = self._check(end_date=None)
        self.assertTrue(
            any("end_date" in e or "wage period end" in e.lower() for e in errors),
            f"Expected end_date error, got: {errors}",
        )

    def test_missing_posting_date_flagged(self):
        errors = self._check(posting_date=None)
        self.assertTrue(
            any("posting_date" in e or "payment date" in e.lower() for e in errors),
            f"Expected posting_date error, got: {errors}",
        )

    def test_zero_gross_pay_flagged(self):
        errors = self._check(gross_pay=0)
        self.assertTrue(
            any("gross" in e.lower() for e in errors),
            f"Expected gross_pay error, got: {errors}",
        )

    def test_none_net_pay_flagged(self):
        errors = self._check(net_pay=None)
        self.assertTrue(
            any("net_pay" in e or "net pay" in e.lower() for e in errors),
            f"Expected net_pay error, got: {errors}",
        )

    def test_missing_epf_deduction_flagged(self):
        deductions = [
            SimpleNamespace(salary_component="SOCSO Employee", amount=29.75),
            SimpleNamespace(salary_component="EIS Employee", amount=11.0),
            SimpleNamespace(salary_component="Monthly Tax Deduction", amount=209.25),
        ]
        errors = self._check(deductions=deductions)
        self.assertTrue(
            any("EPF" in e or "KWSP" in e for e in errors),
            f"Expected EPF error, got: {errors}",
        )

    def test_missing_socso_deduction_flagged(self):
        deductions = [
            SimpleNamespace(salary_component="EPF Employee", amount=550.0),
            SimpleNamespace(salary_component="EIS Employee", amount=11.0),
            SimpleNamespace(salary_component="Monthly Tax Deduction", amount=209.25),
        ]
        errors = self._check(deductions=deductions)
        self.assertTrue(
            any("SOCSO" in e or "PERKESO" in e for e in errors),
            f"Expected SOCSO error, got: {errors}",
        )

    def test_missing_eis_deduction_flagged(self):
        deductions = [
            SimpleNamespace(salary_component="EPF Employee", amount=550.0),
            SimpleNamespace(salary_component="SOCSO Employee", amount=29.75),
            SimpleNamespace(salary_component="Monthly Tax Deduction", amount=209.25),
        ]
        errors = self._check(deductions=deductions)
        self.assertTrue(
            any("EIS" in e for e in errors),
            f"Expected EIS error, got: {errors}",
        )

    def test_multiple_missing_fields_all_reported(self):
        errors = self._check(employee_name=None, start_date=None, end_date=None)
        self.assertGreaterEqual(len(errors), 3, f"Expected ≥3 errors, got: {errors}")


# ---------------------------------------------------------------------------
# 3. validate_s25a_mandatory_fields — ValidationError behavior
# ---------------------------------------------------------------------------

class TestValidateS25AHook(FrappeTestCase):
    """validate_s25a_mandatory_fields() raises ValidationError for missing fields."""

    def _validate(self, **overrides):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.payslip_s25a_service import (
            validate_s25a_mandatory_fields,
        )
        slip = _make_slip(**overrides)
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services."
            "payslip_s25a_service._get_employee_field",
            return_value="901231-01-1234",
        ):
            validate_s25a_mandatory_fields(slip)

    def test_valid_slip_does_not_raise(self):
        try:
            self._validate()
        except frappe.ValidationError as e:
            self.fail(f"Unexpected ValidationError for complete slip: {e}")

    def test_missing_employee_name_raises(self):
        with self.assertRaises(frappe.ValidationError):
            self._validate(employee_name=None)

    def test_missing_start_date_raises(self):
        with self.assertRaises(frappe.ValidationError):
            self._validate(start_date=None)

    def test_missing_end_date_raises(self):
        with self.assertRaises(frappe.ValidationError):
            self._validate(end_date=None)

    def test_missing_posting_date_raises(self):
        with self.assertRaises(frappe.ValidationError):
            self._validate(posting_date=None)

    def test_zero_gross_pay_raises(self):
        with self.assertRaises(frappe.ValidationError):
            self._validate(gross_pay=0.0)

    def test_error_message_cites_s25a(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.payslip_s25a_service import (
            validate_s25a_mandatory_fields,
        )
        slip = _make_slip(employee_name=None)
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services."
            "payslip_s25a_service._get_employee_field",
            return_value="901231-01-1234",
        ):
            try:
                validate_s25a_mandatory_fields(slip)
                self.fail("Expected ValidationError not raised")
            except frappe.ValidationError as e:
                self.assertIn("S.25A", str(e), "Error must cite 'Employment Act S.25A'")


# ---------------------------------------------------------------------------
# 4. run_s25a_audit — audit function
# ---------------------------------------------------------------------------

class TestRunS25AAudit(FrappeTestCase):
    """run_s25a_audit() must return a list (empty is fine for unit tests)."""

    def test_returns_list(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.payslip_s25a_service import (
            run_s25a_audit,
        )
        with patch("frappe.get_all", return_value=[]):
            result = run_s25a_audit("2026-01-01", "2026-01-31")
        self.assertIsInstance(result, list)

    def test_failing_slip_included_in_audit(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.payslip_s25a_service import (
            run_s25a_audit,
        )
        mock_slip_row = {
            "name": "SAL-001",
            "employee": "EMP-001",
            "employee_name": "Ahmad",
            "posting_date": "2026-01-31",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "gross_pay": 5000.0,
            "net_pay": 4200.0,
        }
        # Mock a Salary Slip doc with missing employee_name
        mock_doc = _make_slip(employee_name=None)
        with patch("frappe.get_all", return_value=[mock_slip_row]):
            with patch("frappe.get_doc", return_value=mock_doc):
                with patch(
                    "lhdn_payroll_integration.lhdn_payroll_integration.services."
                    "payslip_s25a_service._get_employee_field",
                    return_value=None,
                ):
                    result = run_s25a_audit("2026-01-01", "2026-01-31")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "SAL-001")
        self.assertTrue(len(result[0]["errors"]) > 0)

    def test_compliant_slip_excluded_from_audit(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.payslip_s25a_service import (
            run_s25a_audit,
        )
        mock_slip_row = {
            "name": "SAL-002",
            "employee": "EMP-002",
            "employee_name": "Siti binti Ahmad",
            "posting_date": "2026-01-31",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "gross_pay": 6000.0,
            "net_pay": 5000.0,
        }
        mock_doc = _make_slip()
        with patch("frappe.get_all", return_value=[mock_slip_row]):
            with patch("frappe.get_doc", return_value=mock_doc):
                with patch(
                    "lhdn_payroll_integration.lhdn_payroll_integration.services."
                    "payslip_s25a_service._get_employee_field",
                    return_value="901231-01-1234",
                ):
                    result = run_s25a_audit("2026-01-01", "2026-01-31")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# 5. Print format includes gender and citizenship (S.25A mandatory fields)
# ---------------------------------------------------------------------------

class TestS25APrintFormatCompliance(FrappeTestCase):
    """EA S.61 payslip HTML template must include S.25A mandatory fields."""

    def _html(self):
        self.assertTrue(os.path.exists(PRINT_FORMAT_HTML),
                        f"Print format HTML missing: {PRINT_FORMAT_HTML}")
        with open(PRINT_FORMAT_HTML) as f:
            return f.read()

    def test_gender_field_present(self):
        html = self._html()
        self.assertIn("gender", html,
                      "Print format must include gender field (EA S.25A mandatory)")

    def test_citizenship_status_present(self):
        html = self._html()
        # citizenship derived from custom_is_foreign_worker flag
        self.assertIn("citizenship", html.lower(),
                      "Print format must reference citizenship status (EA S.25A mandatory)")

    def test_wage_period_start_end_present(self):
        html = self._html()
        self.assertIn("start_date", html, "Print format must show wage period start")
        self.assertIn("end_date", html, "Print format must show wage period end")

    def test_employee_name_present(self):
        html = self._html()
        self.assertIn("employee_name", html, "Print format must show employee name")

    def test_deductions_itemized_loop(self):
        html = self._html()
        self.assertIn("doc.deductions", html,
                      "Deductions must be itemised individually via loop, not as single total")

    def test_gross_pay_present(self):
        html = self._html()
        self.assertIn("gross_pay", html, "Print format must show gross_pay")

    def test_net_pay_present(self):
        html = self._html()
        self.assertIn("net_pay", html, "Print format must show net_pay")

    def test_payment_date_present(self):
        html = self._html()
        self.assertIn("posting_date", html, "Print format must show payment date")

    def test_employer_name_present(self):
        html = self._html()
        self.assertIn("doc.company", html, "Print format must show employer name")


# ---------------------------------------------------------------------------
# 6. Hook registration in hooks.py
# ---------------------------------------------------------------------------

class TestS25AHookRegistration(FrappeTestCase):
    """validate_s25a_mandatory_fields must be registered in hooks.py before_submit."""

    def test_hook_registered_in_before_submit(self):
        hooks_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "hooks.py",
        )
        self.assertTrue(os.path.exists(hooks_path), f"hooks.py not found: {hooks_path}")
        with open(hooks_path) as f:
            content = f.read()
        self.assertIn(
            "payslip_s25a_service",
            content,
            "payslip_s25a_service must be referenced in hooks.py",
        )
        self.assertIn(
            "validate_s25a_mandatory_fields",
            content,
            "validate_s25a_mandatory_fields must be registered in hooks.py",
        )
