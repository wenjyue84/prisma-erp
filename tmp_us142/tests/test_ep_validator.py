"""Tests for US-142: Employment Pass Minimum Salary Threshold Validator.

ESD revised thresholds effective 2026-06-01:
  Cat I   : RM 20,000 / month
  Cat II  : RM 10,000 / month
  Cat III : RM  5,000 / month

Acceptance criteria tested here:
1. EP category fields exist on Employee (custom fields)
2. EP override justification field on Salary Slip
3. EP Salary Threshold DocType is importable / exists
4. EP Override Log DocType is importable / exists
5. get_ep_category_minimum returns correct floor by category and date
6. Salary slip below threshold is blocked (validate_ep_salary_before_submit raises)
7. Salary slip above threshold passes without error
8. Override justification allows bypass and creates EP Override Log record
9. Policy not applied before 2026-06-01
10. "Not Applicable" EP category is never blocked
11. get_ep_expiry_alerts is callable
12. Report get_columns / execute are callable
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch
from datetime import date


class TestEPSalaryThresholdDocType(FrappeTestCase):
    """EP Salary Threshold DocType must be installed."""

    def test_doctype_exists(self):
        """EP Salary Threshold DocType must be registered."""
        result = frappe.db.exists("DocType", "EP Salary Threshold")
        self.assertTrue(result, "EP Salary Threshold DocType must exist after migrate")

    def test_ep_override_log_doctype_exists(self):
        """EP Override Log DocType must be registered."""
        result = frappe.db.exists("DocType", "EP Override Log")
        self.assertTrue(result, "EP Override Log DocType must exist after migrate")


class TestEPSalaryThresholdConstants(FrappeTestCase):
    """Verify EP policy constants exported by ep_validator_service."""

    def test_policy_effective_date(self):
        """EP_POLICY_EFFECTIVE_DATE must be 2026-06-01."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            EP_POLICY_EFFECTIVE_DATE,
        )
        self.assertEqual(EP_POLICY_EFFECTIVE_DATE, date(2026, 6, 1))

    def test_get_ep_category_minimum_importable(self):
        """get_ep_category_minimum must be importable."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            get_ep_category_minimum,
        )
        result = get_ep_category_minimum("Cat I", date(2026, 6, 1))
        self.assertIsInstance(result, float)


class TestGetEPCategoryMinimum(FrappeTestCase):
    """Unit tests for get_ep_category_minimum — tests default threshold fallback."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            get_ep_category_minimum,
        )
        self.get_min = get_ep_category_minimum

    def test_cat_i_minimum_from_june_2026(self):
        """Cat I minimum must be 20,000 from 2026-06-01."""
        with patch("frappe.get_all", return_value=[]):
            result = self.get_min("Cat I", date(2026, 6, 1))
        self.assertAlmostEqual(result, 20000.0)

    def test_cat_ii_minimum_from_june_2026(self):
        """Cat II minimum must be 10,000 from 2026-06-01."""
        with patch("frappe.get_all", return_value=[]):
            result = self.get_min("Cat II", date(2026, 6, 1))
        self.assertAlmostEqual(result, 10000.0)

    def test_cat_iii_minimum_from_june_2026(self):
        """Cat III minimum must be 5,000 from 2026-06-01."""
        with patch("frappe.get_all", return_value=[]):
            result = self.get_min("Cat III", date(2026, 6, 1))
        self.assertAlmostEqual(result, 5000.0)

    def test_not_applicable_returns_zero(self):
        """Not Applicable EP category → minimum = 0 (no restriction)."""
        with patch("frappe.get_all", return_value=[]):
            result = self.get_min("Not Applicable", date(2026, 6, 1))
        self.assertAlmostEqual(result, 0.0)

    def test_none_ep_category_returns_zero(self):
        """None EP category → minimum = 0."""
        with patch("frappe.get_all", return_value=[]):
            result = self.get_min(None, date(2026, 6, 1))
        self.assertAlmostEqual(result, 0.0)

    def test_before_june_2026_default_zero(self):
        """Before policy effective date → minimum = 0 (no validation)."""
        with patch("frappe.get_all", return_value=[]):
            result = self.get_min("Cat I", date(2026, 5, 31))
        self.assertAlmostEqual(result, 0.0)

    def test_doctype_threshold_overrides_default(self):
        """If DocType has a threshold row, it should be used over hardcoded default."""
        mock_row = MagicMock()
        mock_row.minimum_salary = 25000.0
        with patch("frappe.get_all", return_value=[mock_row]):
            result = self.get_min("Cat I", date(2026, 6, 1))
        self.assertAlmostEqual(result, 25000.0)

    def test_july_2026_still_applies_minimum(self):
        """Policy applies on any date >= 2026-06-01, e.g. July 2026."""
        with patch("frappe.get_all", return_value=[]):
            result = self.get_min("Cat II", date(2026, 7, 15))
        self.assertAlmostEqual(result, 10000.0)


class TestValidateEPSalaryBeforeSubmit(FrappeTestCase):
    """Tests for validate_ep_salary_before_submit hook behaviour."""

    def _make_slip(self, gross_pay, end_date, employee="EMP-001",
                   employee_name="Test Expatriate", justification=""):
        slip = MagicMock()
        slip.employee = employee
        slip.employee_name = employee_name
        slip.gross_pay = gross_pay
        slip.end_date = end_date
        slip.name = "SAL-TEST-001"
        slip.custom_ep_override_justification = justification
        return slip

    def _make_emp(self, category="Cat II", ep_number="EP123456", expiry=None):
        emp = MagicMock()
        emp.custom_ep_category = category
        emp.custom_ep_number = ep_number
        emp.custom_ep_expiry_date = expiry or date(2027, 1, 1)
        return emp

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_all", return_value=[])
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_doc")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.throw")
    def test_below_threshold_blocked(self, mock_throw, mock_get_doc, mock_get_all):
        """EP holder below category minimum → frappe.throw called."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            validate_ep_salary_before_submit,
        )
        mock_get_doc.return_value = self._make_emp(category="Cat II")
        slip = self._make_slip(gross_pay=8000.0, end_date=date(2026, 6, 30))
        validate_ep_salary_before_submit(slip)
        mock_throw.assert_called_once()
        call_args = mock_throw.call_args[0][0]
        self.assertIn("Cat II", call_args)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_all", return_value=[])
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_doc")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.throw")
    def test_above_threshold_passes(self, mock_throw, mock_get_doc, mock_get_all):
        """EP holder at or above category minimum → no throw."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            validate_ep_salary_before_submit,
        )
        mock_get_doc.return_value = self._make_emp(category="Cat II")
        slip = self._make_slip(gross_pay=12000.0, end_date=date(2026, 6, 30))
        validate_ep_salary_before_submit(slip)
        mock_throw.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_all", return_value=[])
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_doc")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.throw")
    def test_not_applicable_never_blocked(self, mock_throw, mock_get_doc, mock_get_all):
        """Not Applicable EP category → never blocked regardless of salary."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            validate_ep_salary_before_submit,
        )
        mock_get_doc.return_value = self._make_emp(category="Not Applicable")
        slip = self._make_slip(gross_pay=100.0, end_date=date(2026, 6, 30))
        validate_ep_salary_before_submit(slip)
        mock_throw.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_all", return_value=[])
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_doc")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.throw")
    def test_before_policy_date_not_blocked(self, mock_throw, mock_get_doc, mock_get_all):
        """Period ending before 2026-06-01 → no EP salary check at all."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            validate_ep_salary_before_submit,
        )
        mock_get_doc.return_value = self._make_emp(category="Cat I")
        slip = self._make_slip(gross_pay=5000.0, end_date=date(2026, 5, 31))
        validate_ep_salary_before_submit(slip)
        mock_throw.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_all", return_value=[])
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_doc")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.throw")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service._log_ep_override")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.msgprint")
    def test_override_justification_bypasses_block(self, mock_msg, mock_log, mock_throw,
                                                    mock_get_doc, mock_get_all):
        """Override justification prevents throw and calls _log_ep_override."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            validate_ep_salary_before_submit,
        )
        mock_get_doc.return_value = self._make_emp(category="Cat III")
        slip = self._make_slip(
            gross_pay=3000.0,
            end_date=date(2026, 6, 30),
            justification="Salary increment letter dated 2026-05-15 pending MyTax update."
        )
        validate_ep_salary_before_submit(slip)
        mock_throw.assert_not_called()
        mock_log.assert_called_once()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_all", return_value=[])
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_doc")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.throw")
    def test_cat_i_below_20000_blocked(self, mock_throw, mock_get_doc, mock_get_all):
        """Cat I employee with RM 15,000 is blocked (< RM 20,000 minimum)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            validate_ep_salary_before_submit,
        )
        mock_get_doc.return_value = self._make_emp(category="Cat I")
        slip = self._make_slip(gross_pay=15000.0, end_date=date(2026, 8, 31))
        validate_ep_salary_before_submit(slip)
        mock_throw.assert_called_once()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_all", return_value=[])
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_doc")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.throw")
    def test_cat_i_at_20000_not_blocked(self, mock_throw, mock_get_doc, mock_get_all):
        """Cat I employee with exactly RM 20,000 passes (meets minimum)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            validate_ep_salary_before_submit,
        )
        mock_get_doc.return_value = self._make_emp(category="Cat I")
        slip = self._make_slip(gross_pay=20000.0, end_date=date(2026, 6, 30))
        validate_ep_salary_before_submit(slip)
        mock_throw.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_all", return_value=[])
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_doc")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.throw")
    def test_end_date_as_string(self, mock_throw, mock_get_doc, mock_get_all):
        """validate_ep_salary_before_submit handles end_date as ISO string."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            validate_ep_salary_before_submit,
        )
        mock_get_doc.return_value = self._make_emp(category="Cat III")
        slip = self._make_slip(gross_pay=100.0, end_date="2026-06-30")
        validate_ep_salary_before_submit(slip)
        mock_throw.assert_called_once()  # 100 < 5000


class TestEPExpiryAlerts(FrappeTestCase):
    """Tests for get_ep_expiry_alerts."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_all", return_value=[])
    def test_empty_return_when_no_ep_holders(self, mock_get_all):
        """Returns empty list when no EP holders have upcoming expiry."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            get_ep_expiry_alerts,
        )
        result = get_ep_expiry_alerts(days_ahead=90)
        self.assertIsInstance(result, list)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_all")
    def test_returns_sorted_by_days_to_expiry(self, mock_get_all):
        """Results sorted ascending by days_to_expiry."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            get_ep_expiry_alerts,
        )
        from datetime import timedelta
        today = date.today()
        mock_get_all.return_value = [
            MagicMock(
                name="EMP-001",
                employee_name="Alice",
                custom_ep_category="Cat I",
                custom_ep_number="EP111",
                custom_ep_expiry_date=(today + timedelta(days=60)).strftime("%Y-%m-%d"),
            ),
            MagicMock(
                name="EMP-002",
                employee_name="Bob",
                custom_ep_category="Cat II",
                custom_ep_number="EP222",
                custom_ep_expiry_date=(today + timedelta(days=30)).strftime("%Y-%m-%d"),
            ),
        ]
        result = get_ep_expiry_alerts(days_ahead=90)
        self.assertEqual(len(result), 2)
        self.assertLessEqual(result[0]["days_to_expiry"], result[1]["days_to_expiry"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service.frappe.get_all")
    def test_alert_dict_has_required_keys(self, mock_get_all):
        """Each alert dict must have employee, ep_category, ep_expiry_date, days_to_expiry."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
            get_ep_expiry_alerts,
        )
        from datetime import timedelta
        today = date.today()
        mock_get_all.return_value = [
            MagicMock(
                name="EMP-001",
                employee_name="Alice",
                custom_ep_category="Cat I",
                custom_ep_number="EP111",
                custom_ep_expiry_date=(today + timedelta(days=45)).strftime("%Y-%m-%d"),
            ),
        ]
        result = get_ep_expiry_alerts(days_ahead=90)
        self.assertEqual(len(result), 1)
        alert = result[0]
        for key in ("employee", "employee_name", "ep_category", "ep_number", "ep_expiry_date", "days_to_expiry"):
            self.assertIn(key, alert, f"Key '{key}' missing from alert dict")


class TestEPSalaryComplianceReport(FrappeTestCase):
    """Tests for Expatriate EP Salary Compliance report."""

    def test_get_columns_importable(self):
        """get_columns must be importable and return a list."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.expatriate_ep_salary_compliance.expatriate_ep_salary_compliance import (
            get_columns,
        )
        cols = get_columns()
        self.assertIsInstance(cols, list)
        self.assertGreater(len(cols), 0)

    def test_get_columns_has_required_fields(self):
        """Report columns must include employee, ep_category, current_salary, category_minimum, compliance_status."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.expatriate_ep_salary_compliance.expatriate_ep_salary_compliance import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = {c["fieldname"] for c in cols}
        for required in ("employee", "ep_category", "current_salary", "category_minimum", "compliance_status"):
            self.assertIn(required, fieldnames, f"Column '{required}' missing from report")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.expatriate_ep_salary_compliance.expatriate_ep_salary_compliance.frappe.get_all", return_value=[])
    def test_execute_returns_columns_and_data(self, mock_get_all):
        """execute() must return (columns, data) tuple."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.expatriate_ep_salary_compliance.expatriate_ep_salary_compliance import (
            execute,
        )
        result = execute()
        self.assertEqual(len(result), 2)
        columns, data = result
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)

    def test_ep_days_to_expiry_column_present(self):
        """Report must include days_to_expiry column for EP renewal alerts."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.expatriate_ep_salary_compliance.expatriate_ep_salary_compliance import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("days_to_expiry", fieldnames,
                      "days_to_expiry column required for EP expiry surfacing in compliance dashboard")


class TestEPCustomFields(FrappeTestCase):
    """Verify EP custom fields are applied to Employee and Salary Slip."""

    def test_employee_has_ep_category_field(self):
        """Employee DocType must have custom_ep_category custom field."""
        result = frappe.db.exists("Custom Field", "Employee-custom_ep_category")
        self.assertTrue(result, "Employee-custom_ep_category custom field must exist")

    def test_employee_has_ep_number_field(self):
        """Employee DocType must have custom_ep_number custom field."""
        result = frappe.db.exists("Custom Field", "Employee-custom_ep_number")
        self.assertTrue(result, "Employee-custom_ep_number custom field must exist")

    def test_employee_has_ep_expiry_date_field(self):
        """Employee DocType must have custom_ep_expiry_date custom field."""
        result = frappe.db.exists("Custom Field", "Employee-custom_ep_expiry_date")
        self.assertTrue(result, "Employee-custom_ep_expiry_date custom field must exist")

    def test_salary_slip_has_ep_override_field(self):
        """Salary Slip must have custom_ep_override_justification custom field."""
        result = frappe.db.exists("Custom Field", "Salary Slip-custom_ep_override_justification")
        self.assertTrue(result, "Salary Slip-custom_ep_override_justification custom field must exist")

    def test_ep_category_fixture_has_correct_options(self):
        """custom_ep_category field options must include Cat I, Cat II, Cat III."""
        import json
        import os
        fixture_path = os.path.join(
            frappe.get_app_path("lhdn_payroll_integration"),
            "fixtures", "custom_field.json"
        )
        with open(fixture_path, encoding="utf-8") as f:
            fields = json.load(f)
        ep_cat = next((fld for fld in fields if fld.get("fieldname") == "custom_ep_category"
                       and fld.get("dt") == "Employee"), None)
        self.assertIsNotNone(ep_cat, "Employee-custom_ep_category not in fixture")
        options = ep_cat.get("options", "")
        for cat in ("Cat I", "Cat II", "Cat III"):
            self.assertIn(cat, options, f"'{cat}' missing from custom_ep_category options")


class TestHookRegistration(FrappeTestCase):
    """Verify validate_ep_salary_before_submit is registered in hooks."""

    def test_ep_validator_in_salary_slip_before_submit_hooks(self):
        """ep_validator_service.validate_ep_salary_before_submit must be in hooks before_submit."""
        import lhdn_payroll_integration.lhdn_payroll_integration.hooks as app_hooks
        doc_events = getattr(app_hooks, "doc_events", {})
        ss_hooks = doc_events.get("Salary Slip", {})
        before_submit = ss_hooks.get("before_submit", [])
        if isinstance(before_submit, str):
            before_submit = [before_submit]
        ep_hooks = [h for h in before_submit if "ep_validator" in h]
        self.assertTrue(
            len(ep_hooks) > 0,
            "ep_validator_service.validate_ep_salary_before_submit must be in Salary Slip before_submit"
        )
