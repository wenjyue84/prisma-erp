"""Tests for US-247: EIS Amendment 2025 — Payroll Validation.

Prohibit Employer EIS Contribution Recovery from Employee Wages.

Acceptance criteria:
- Blocking error if deduction has custom_is_eis_component=1 AND is_employer_contribution=1
- LHDN Payroll Compliance Report rows show employer_recoverable='No', employee_recoverable='Yes'
- Pre-migration helper returns violating salary structures
- EIS ceiling of RM6,000 applied to compliance calculations
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch

from lhdn_payroll_integration.lhdn_payroll_integration.services.eis_recovery_validator import (
    validate_no_employer_eis_deduction,
    get_eis_compliance_rows,
    get_employer_eis_violation_salary_structures,
    EIS_EMPLOYER_RECOVERY_ERROR,
    EIS_WAGE_CEILING,
    EIS_EMPLOYER_RATE,
    EIS_EMPLOYEE_RATE,
)


def _make_component(name, is_eis, is_employer):
    """Create a mock salary component row."""
    comp = MagicMock()
    comp.get.side_effect = lambda key, default=None: {
        "salary_component": name,
        "abbr": name,
        "custom_is_eis_component": 1 if is_eis else 0,
        "is_employer_contribution": 1 if is_employer else 0,
    }.get(key, default)
    return comp


def _make_salary_slip(deductions):
    """Create a mock Salary Slip document with given deductions."""
    doc = MagicMock()
    doc.get.side_effect = lambda key, default=None: {
        "doctype": "Salary Slip",
        "deductions": deductions,
    }.get(key, default)
    return doc


class TestEisRecoveryValidatorConstants(FrappeTestCase):
    """Verify module-level constants for EIS rates and ceiling."""

    def test_eis_wage_ceiling(self):
        """EIS wage ceiling must be RM6,000."""
        self.assertEqual(EIS_WAGE_CEILING, 6000.0)

    def test_eis_employer_rate(self):
        """Employer EIS rate must be 0.4%."""
        self.assertAlmostEqual(EIS_EMPLOYER_RATE, 0.004, places=4)

    def test_eis_employee_rate(self):
        """Employee EIS rate must be 0.2%."""
        self.assertAlmostEqual(EIS_EMPLOYEE_RATE, 0.002, places=4)

    def test_error_message_template_contains_placeholder(self):
        """Error message template must include '{component}' placeholder."""
        self.assertIn("{component}", EIS_EMPLOYER_RECOVERY_ERROR)


class TestValidateNoEmployerEisDeduction(FrappeTestCase):
    """Unit tests for validate_no_employer_eis_deduction()."""

    def test_employer_eis_deduction_raises_validation_error(self):
        """Salary Slip with employer EIS deduction must raise ValidationError."""
        eis_employer = _make_component("EIS - Employer", is_eis=True, is_employer=True)
        doc = _make_salary_slip([eis_employer])
        with self.assertRaises(frappe.ValidationError):
            validate_no_employer_eis_deduction(doc)

    def test_employee_eis_deduction_passes(self):
        """Employee EIS deduction (is_employer_contribution=0) must not raise."""
        eis_employee = _make_component("EIS", is_eis=True, is_employer=False)
        doc = _make_salary_slip([eis_employee])
        # Must not raise
        validate_no_employer_eis_deduction(doc)

    def test_non_eis_employer_component_passes(self):
        """Non-EIS employer contribution component must not raise."""
        socso_employer = _make_component("SOCSO - Employer", is_eis=False, is_employer=True)
        doc = _make_salary_slip([socso_employer])
        validate_no_employer_eis_deduction(doc)

    def test_empty_deductions_passes(self):
        """Salary Slip with no deductions must not raise."""
        doc = _make_salary_slip([])
        validate_no_employer_eis_deduction(doc)

    def test_none_deductions_passes(self):
        """Salary Slip where deductions returns None must not raise."""
        doc = MagicMock()
        doc.get.return_value = None
        validate_no_employer_eis_deduction(doc)

    def test_error_message_contains_component_name(self):
        """ValidationError message must name the offending component."""
        eis_employer = _make_component("EIS - Employer", is_eis=True, is_employer=True)
        doc = _make_salary_slip([eis_employer])
        try:
            validate_no_employer_eis_deduction(doc)
            self.fail("Expected ValidationError not raised")
        except frappe.ValidationError as exc:
            self.assertIn("EIS - Employer", str(exc))

    def test_mixed_components_raises_on_employer_eis(self):
        """Salary Slip with both valid and illegal EIS components must still raise."""
        eis_employee = _make_component("EIS", is_eis=True, is_employer=False)
        eis_employer = _make_component("EIS Employer", is_eis=True, is_employer=True)
        doc = _make_salary_slip([eis_employee, eis_employer])
        with self.assertRaises(frappe.ValidationError):
            validate_no_employer_eis_deduction(doc)

    def test_method_param_ignored(self):
        """method parameter must be accepted but ignored (Frappe hook signature)."""
        doc = _make_salary_slip([])
        validate_no_employer_eis_deduction(doc, method="before_submit")


class TestGetEisComplianceRows(FrappeTestCase):
    """Unit tests for get_eis_compliance_rows()."""

    def _patch_frappe_db(self, mock_rows):
        return patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.eis_recovery_validator.frappe"
        )

    def test_employer_recoverable_is_no(self):
        """Compliance rows must have employer_recoverable='No'."""
        mock_row = {
            "salary_slip": "SS-001",
            "employee": "EMP001",
            "employee_name": "Ahmad",
            "period": "2025-01-01 to 2025-01-31",
            "wages": 5000.0,
        }
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.eis_recovery_validator.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe._dict = frappe._dict
            rows = get_eis_compliance_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["employer_recoverable"], "No")

    def test_employee_recoverable_is_yes(self):
        """Compliance rows must have employee_recoverable='Yes'."""
        mock_row = {
            "salary_slip": "SS-001",
            "employee": "EMP001",
            "employee_name": "Ahmad",
            "period": "2025-01-01 to 2025-01-31",
            "wages": 5000.0,
        }
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.eis_recovery_validator.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe._dict = frappe._dict
            rows = get_eis_compliance_rows()
        self.assertEqual(rows[0]["employee_recoverable"], "Yes")

    def test_eis_rates_correct(self):
        """Compliance rows must show 0.40% employer and 0.20% employee rates."""
        mock_row = {
            "salary_slip": "SS-001",
            "employee": "EMP001",
            "employee_name": "Ahmad",
            "period": "2025-01-01 to 2025-01-31",
            "wages": 5000.0,
        }
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.eis_recovery_validator.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe._dict = frappe._dict
            rows = get_eis_compliance_rows()
        row = rows[0]
        self.assertEqual(row["eis_employer_rate"], "0.40%")
        self.assertEqual(row["eis_employee_rate"], "0.20%")
        # 5000 * 0.004 = 20.00; 5000 * 0.002 = 10.00
        self.assertAlmostEqual(row["eis_employer_amount"], 20.00, places=2)
        self.assertAlmostEqual(row["eis_employee_amount"], 10.00, places=2)

    def test_eis_ceiling_applied_at_6000(self):
        """EIS calculation must cap wages at RM6,000."""
        mock_row = {
            "salary_slip": "SS-002",
            "employee": "EMP002",
            "employee_name": "Siti",
            "period": "2025-02-01 to 2025-02-28",
            "wages": 10000.0,
        }
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.eis_recovery_validator.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe._dict = frappe._dict
            rows = get_eis_compliance_rows()
        row = rows[0]
        # Capped at 6000: 6000 * 0.004 = 24.00; 6000 * 0.002 = 12.00
        self.assertAlmostEqual(row["eis_employer_amount"], 24.00, places=2)
        self.assertAlmostEqual(row["eis_employee_amount"], 12.00, places=2)

    def test_empty_result_returns_empty_list(self):
        """No salary slips returns empty list."""
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.eis_recovery_validator.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = []
            mock_frappe._dict = frappe._dict
            rows = get_eis_compliance_rows()
        self.assertEqual(rows, [])

    def test_filters_accepted(self):
        """get_eis_compliance_rows must accept filter dict without error."""
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.eis_recovery_validator.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = []
            mock_frappe._dict = frappe._dict
            rows = get_eis_compliance_rows(
                frappe._dict({"company": "Test Co", "month": "3", "year": "2025"})
            )
        self.assertEqual(rows, [])


class TestGetEmployerEisViolationSalaryStructures(FrappeTestCase):
    """Unit tests for get_employer_eis_violation_salary_structures()."""

    def test_returns_list(self):
        """Function must return a list (possibly empty)."""
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.eis_recovery_validator.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = []
            result = get_employer_eis_violation_salary_structures()
        self.assertIsInstance(result, list)

    def test_returns_violation_structures(self):
        """Returns dicts with salary_structure, company, salary_component, abbr."""
        mock_violation = {
            "salary_structure": "SS-Std",
            "company": "Test Co",
            "salary_component": "EIS - Employer",
            "abbr": "EISE",
        }
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.eis_recovery_validator.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_violation]
            result = get_employer_eis_violation_salary_structures()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["salary_structure"], "SS-Std")
        self.assertEqual(result[0]["salary_component"], "EIS - Employer")

    def test_db_exception_returns_empty_list(self):
        """If DB query fails, returns empty list gracefully."""
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.eis_recovery_validator.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.side_effect = Exception("DB error")
            result = get_employer_eis_violation_salary_structures()
        self.assertEqual(result, [])
