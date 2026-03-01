"""Tests for US-227: Store Employee TIN on Employee DocType and Validate for e-PCB Plus Upload.

Acceptance criteria:
  1. custom_lhdn_tin field exists on Employee DocType + is in custom_field.json fixture
  2. CP39 / e-Data PCB export includes employee TIN column
  3. Payroll raises validation WARNING (not hard block) for blank employee TIN
  4. Pre-submission validation report lists employees with missing TIN
  5. TIN format validated: IG/SG/OG/D/C prefix + 11 digits
"""
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


# ---------------------------------------------------------------------------
# 1. custom_lhdn_tin field on Employee DocType (+ fixture)
# ---------------------------------------------------------------------------

class TestEmployeeTinField(FrappeTestCase):
    """Verify the TIN field exists on Employee and fixture is synced."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.meta = frappe.get_meta("Employee")

    def test_lhdn_tin_field_exists_on_employee(self):
        """custom_lhdn_tin must exist as a Data field on Employee DocType."""
        field = self.meta.get_field("custom_lhdn_tin")
        self.assertIsNotNone(
            field,
            "custom_lhdn_tin field missing from Employee DocType — "
            "required for e-PCB Plus TIN submission",
        )
        self.assertEqual(field.fieldtype, "Data")

    def test_lhdn_tin_custom_field_in_db(self):
        """Employee-custom_lhdn_tin must exist in Custom Field doctype (fixture applied)."""
        self.assertTrue(
            frappe.db.exists("Custom Field", "Employee-custom_lhdn_tin"),
            "Custom Field 'Employee-custom_lhdn_tin' missing — fixture sync may not have run",
        )

    def test_lhdn_tin_field_module(self):
        """custom_lhdn_tin fixture must belong to LHDN Payroll Integration module."""
        cf = frappe.get_doc("Custom Field", "Employee-custom_lhdn_tin")
        self.assertEqual(
            cf.module,
            "LHDN Payroll Integration",
            "custom_lhdn_tin fixture module should be 'LHDN Payroll Integration'",
        )


# ---------------------------------------------------------------------------
# 2. CP39 report includes employee TIN column
# ---------------------------------------------------------------------------

class TestCp39IncludesTin(FrappeTestCase):
    """Verify the CP39 report columns include employee_tin."""

    def test_cp39_columns_include_employee_tin(self):
        """get_columns() must include 'employee_tin' fieldname for e-PCB Plus compliance."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance.cp39_pcb_remittance import (
            get_columns,
        )
        columns = get_columns()
        field_names = [c["fieldname"] for c in columns]
        self.assertIn(
            "employee_tin",
            field_names,
            "CP39 report must include 'employee_tin' column for e-PCB Plus",
        )

    def test_cp39_employee_tin_before_nric(self):
        """employee_tin column must appear before employee_nric (LHDN e-PCB Plus spec order)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance.cp39_pcb_remittance import (
            get_columns,
        )
        columns = get_columns()
        field_names = [c["fieldname"] for c in columns]
        tin_idx = field_names.index("employee_tin")
        nric_idx = field_names.index("employee_nric")
        self.assertLess(tin_idx, nric_idx)


# ---------------------------------------------------------------------------
# 3. TIN format validation
# ---------------------------------------------------------------------------

class TestValidateTinFormat(FrappeTestCase):
    """Unit tests for validate_tin_format() — local format check (no HTTP call)."""

    def _validate(self, tin):
        from lhdn_payroll_integration.utils.tin_validator import validate_tin_format
        return validate_tin_format(tin)

    def test_ig_prefix_valid(self):
        ok, err = self._validate("IG12345678901")
        self.assertTrue(ok, f"Expected valid, got: {err}")
        self.assertIsNone(err)

    def test_sg_prefix_valid(self):
        ok, err = self._validate("SG12345678901")
        self.assertTrue(ok)

    def test_og_prefix_valid(self):
        ok, err = self._validate("OG12345678901")
        self.assertTrue(ok)

    def test_d_prefix_valid(self):
        ok, err = self._validate("D12345678901")
        self.assertTrue(ok)

    def test_c_prefix_valid(self):
        ok, err = self._validate("C12345678901")
        self.assertTrue(ok)

    def test_invalid_prefix_returns_false(self):
        ok, err = self._validate("XX12345678901")
        self.assertFalse(ok)
        self.assertIsNotNone(err)
        self.assertIn("prefix", err.lower())

    def test_too_few_digits_returns_false(self):
        ok, err = self._validate("IG1234567890")
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_too_many_digits_returns_false(self):
        ok, err = self._validate("IG123456789012")
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_letters_in_digit_part_returns_false(self):
        ok, err = self._validate("IG1234567890A")
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_empty_string_returns_false(self):
        ok, err = self._validate("")
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_none_returns_false(self):
        ok, err = self._validate(None)
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_lowercase_prefix_returns_false(self):
        ok, err = self._validate("ig12345678901")
        self.assertFalse(ok)


# ---------------------------------------------------------------------------
# 4. Blank TIN warning on Salary Slip validate (not hard block)
# ---------------------------------------------------------------------------

_WARNING_SVC = "lhdn_payroll_integration.services.employee_tin_warning"


class TestBlankTinWarningOnSalarySlip(FrappeTestCase):
    """warn_missing_employee_tin() issues msgprint warning (not throw) for blank TIN."""

    def _make_doc(self, employee="HR-EMP-001", employee_name="Ahmad"):
        doc = MagicMock()
        doc.employee = employee
        doc.employee_name = employee_name
        return doc

    @patch(f"{_WARNING_SVC}.frappe")
    def test_blank_tin_triggers_msgprint_not_throw(self, mock_frappe):
        """Employee with blank TIN → frappe.msgprint called, NOT frappe.throw."""
        from lhdn_payroll_integration.services.employee_tin_warning import (
            warn_missing_employee_tin,
        )

        mock_frappe.db.get_value.return_value = frappe._dict(
            {"custom_employee_tin": "", "custom_lhdn_tin": ""}
        )
        mock_frappe.throw = MagicMock(
            side_effect=Exception("frappe.throw must NOT be called")
        )

        doc = self._make_doc()
        warn_missing_employee_tin(doc, "validate")

        mock_frappe.msgprint.assert_called_once()
        mock_frappe.throw.assert_not_called()

    @patch(f"{_WARNING_SVC}.frappe")
    def test_blank_tin_warning_mentions_tin(self, mock_frappe):
        """Warning message must mention TIN so HR knows what to fix."""
        from lhdn_payroll_integration.services.employee_tin_warning import (
            warn_missing_employee_tin,
        )

        mock_frappe.db.get_value.return_value = frappe._dict(
            {"custom_employee_tin": "", "custom_lhdn_tin": ""}
        )

        doc = self._make_doc()
        warn_missing_employee_tin(doc, "validate")

        call_args = mock_frappe.msgprint.call_args
        # message could be positional or keyword arg
        message = (
            str(call_args[0][0])
            if call_args[0]
            else str(call_args[1].get("msg", ""))
        )
        self.assertIn("TIN", message)

    @patch(f"{_WARNING_SVC}.frappe")
    def test_populated_lhdn_tin_no_warning(self, mock_frappe):
        """Employee with custom_lhdn_tin set → no msgprint."""
        from lhdn_payroll_integration.services.employee_tin_warning import (
            warn_missing_employee_tin,
        )

        mock_frappe.db.get_value.return_value = frappe._dict(
            {"custom_employee_tin": "", "custom_lhdn_tin": "IG12345678901"}
        )

        doc = self._make_doc()
        warn_missing_employee_tin(doc, "validate")

        mock_frappe.msgprint.assert_not_called()

    @patch(f"{_WARNING_SVC}.frappe")
    def test_none_employee_no_crash(self, mock_frappe):
        """Salary Slip with no employee → no crash, no warning."""
        from lhdn_payroll_integration.services.employee_tin_warning import (
            warn_missing_employee_tin,
        )

        doc = MagicMock()
        doc.employee = None
        warn_missing_employee_tin(doc, "validate")

        mock_frappe.msgprint.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Pre-submission report lists missing TIN employees
# ---------------------------------------------------------------------------

class TestPreSubmissionMissingTinReport(FrappeTestCase):
    """Verify the pre-submission check surfaces employees with missing TIN."""

    _SVC = "lhdn_payroll_integration.lhdn_payroll_integration.api.epcb_preflight"

    def test_missing_tin_appears_in_preflight_gaps(self):
        """Employee with blank TIN appears in get_employee_data_gaps() output."""
        from lhdn_payroll_integration.lhdn_payroll_integration.api.epcb_preflight import (
            get_employee_data_gaps,
        )

        fake_row = frappe._dict({
            "employee": "EMP-001",
            "employee_name": "Ahmad",
            "salary_slip": "SAL-001",
            "tin": "",
            "pcb_category": "1",
            "id_type": "NRIC",
        })

        with patch(f"{self._SVC}.frappe.db.sql", return_value=[fake_row]):
            gaps = get_employee_data_gaps("Test Co", "03", 2026)

        self.assertEqual(len(gaps), 1)
        self.assertTrue(gaps[0]["missing_tin"])
        self.assertIn("TIN missing", gaps[0]["issues"])

    def test_preflight_result_compliant_false_when_tin_missing(self):
        """run_epcb_preflight_check() returns compliant=False when TIN missing."""
        from lhdn_payroll_integration.lhdn_payroll_integration.api.epcb_preflight import (
            run_epcb_preflight_check,
        )

        fake_gap = {
            "employee": "EMP-001",
            "employee_name": "Ahmad",
            "salary_slip": "SAL-001",
            "missing_tin": True,
            "missing_pcb_category": False,
            "missing_id_type": False,
            "issues": ["TIN missing"],
        }
        with patch(f"{self._SVC}.get_employee_data_gaps", return_value=[fake_gap]):
            result = run_epcb_preflight_check("Test Co", "03", 2026)

        self.assertFalse(result["compliant"])
        self.assertEqual(result["gap_count"], 1)
