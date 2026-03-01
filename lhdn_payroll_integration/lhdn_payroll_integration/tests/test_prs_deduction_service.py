"""Tests for US-109: Integrate Private Retirement Scheme (PRS) Voluntary Deduction
with TP1 RM3,000 Relief.

Covers:
  - PRS salary component fixture: type Deduction, voluntary, non-statutory
  - PRS YTD accumulation per employee per year, capped at RM3,000 for relief
  - TP1 prs_contribution field auto-populated from YTD PRS total
  - PRS provider name and account number on Employee custom fields
  - EA Form includes PRS deduction in Part D
  - PRS deduction does NOT reduce EPF/SOCSO/EIS contribution base
  - PRS annual relief cap is RM3,000 (separate from EPF + life insurance RM7,000)
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock, call

from lhdn_payroll_integration.services.prs_deduction_service import (
    PRS_ANNUAL_RELIEF_CAP,
    PRS_COMPONENT_NAME,
    get_prs_ytd_total,
    get_prs_relief_amount,
    sync_prs_to_tp1,
    get_prs_for_ea_form,
    get_prs_employee_details,
    validate_prs_deduction_on_slip,
)


# ---------------------------------------------------------------------------
# Test: Constants
# ---------------------------------------------------------------------------

class TestPrsConstants(FrappeTestCase):
    """Verify PRS service constants are correctly defined."""

    def test_annual_relief_cap_is_3000(self):
        """PRS annual relief cap is RM3,000 per LHDN."""
        self.assertEqual(PRS_ANNUAL_RELIEF_CAP, 3_000)

    def test_component_name(self):
        """PRS salary component name matches fixture."""
        self.assertEqual(PRS_COMPONENT_NAME, "Private Retirement Scheme (PRS)")

    def test_cap_is_separate_from_epf_life(self):
        """PRS RM3,000 relief is separate from EPF + life insurance RM7,000 bucket."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
            _CAPS_DEFAULT,
        )
        # PRS has its own RM3,000 cap entry in the TP1 cap table
        self.assertEqual(_CAPS_DEFAULT["prs_contribution"], 3_000)
        # EPF employee has a separate RM4,000 cap
        self.assertEqual(_CAPS_DEFAULT["epf_employee"], 4_000)
        # Life insurance has a separate RM3,000 cap
        self.assertEqual(_CAPS_DEFAULT["life_insurance"], 3_000)


# ---------------------------------------------------------------------------
# Test: Salary Component Fixture
# ---------------------------------------------------------------------------

class TestPrsSalaryComponentFixture(FrappeTestCase):
    """Verify PRS salary component is correctly defined in fixtures."""

    def test_prs_component_in_fixture(self):
        """PRS component exists in salary_component.json fixture."""
        import json
        import os
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures", "salary_component.json"
        )
        with open(fixture_path) as f:
            components = json.load(f)
        prs = [c for c in components if c["name"] == "Private Retirement Scheme (PRS)"]
        self.assertEqual(len(prs), 1)

    def test_prs_is_deduction_type(self):
        """PRS component is type Deduction."""
        import json
        import os
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures", "salary_component.json"
        )
        with open(fixture_path) as f:
            components = json.load(f)
        prs = [c for c in components if c["name"] == "Private Retirement Scheme (PRS)"][0]
        self.assertEqual(prs["type"], "Deduction")

    def test_prs_is_voluntary(self):
        """PRS component is marked as voluntary (custom_is_prs_voluntary=1)."""
        import json
        import os
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures", "salary_component.json"
        )
        with open(fixture_path) as f:
            components = json.load(f)
        prs = [c for c in components if c["name"] == "Private Retirement Scheme (PRS)"][0]
        self.assertEqual(prs.get("custom_is_prs_voluntary"), 1)

    def test_prs_is_not_pcb_component(self):
        """PRS is not a PCB/MTD component (voluntary, not statutory)."""
        import json
        import os
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures", "salary_component.json"
        )
        with open(fixture_path) as f:
            components = json.load(f)
        prs = [c for c in components if c["name"] == "Private Retirement Scheme (PRS)"][0]
        self.assertEqual(prs.get("custom_is_pcb_component"), 0)

    def test_prs_abbreviation(self):
        """PRS component abbreviation is PRS."""
        import json
        import os
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures", "salary_component.json"
        )
        with open(fixture_path) as f:
            components = json.load(f)
        prs = [c for c in components if c["name"] == "Private Retirement Scheme (PRS)"][0]
        self.assertEqual(prs["salary_component_abbr"], "PRS")


# ---------------------------------------------------------------------------
# Test: YTD Total (get_prs_ytd_total)
# ---------------------------------------------------------------------------

class TestGetPrsYtdTotal(FrappeTestCase):
    """Test PRS YTD total from submitted Salary Slips."""

    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_returns_ytd_total_from_db(self, mock_frappe):
        """Returns the sum of PRS deductions from submitted slips."""
        mock_frappe.db.sql.return_value = [(1500.0,)]
        result = get_prs_ytd_total("EMP-001", 2026)
        self.assertEqual(result, 1500.0)
        # Verify SQL was called with correct params
        args = mock_frappe.db.sql.call_args
        self.assertIn("EMP-001", args[0][1])
        self.assertIn(2026, args[0][1])
        self.assertIn("Private Retirement Scheme (PRS)", args[0][1])

    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_returns_zero_when_no_slips(self, mock_frappe):
        """Returns 0.0 when no Salary Slips have PRS deduction."""
        mock_frappe.db.sql.return_value = [(0.0,)]
        result = get_prs_ytd_total("EMP-002", 2026)
        self.assertEqual(result, 0.0)

    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_returns_zero_when_no_result(self, mock_frappe):
        """Returns 0.0 when db.sql returns empty."""
        mock_frappe.db.sql.return_value = []
        result = get_prs_ytd_total("EMP-003", 2026)
        self.assertEqual(result, 0.0)

    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_coerces_year_to_int(self, mock_frappe):
        """Year parameter is coerced to int."""
        mock_frappe.db.sql.return_value = [(500.0,)]
        result = get_prs_ytd_total("EMP-001", "2026")
        self.assertEqual(result, 500.0)
        args = mock_frappe.db.sql.call_args
        self.assertIn(2026, args[0][1])


# ---------------------------------------------------------------------------
# Test: PRS Relief Amount (get_prs_relief_amount)
# ---------------------------------------------------------------------------

class TestGetPrsReliefAmount(FrappeTestCase):
    """Test PRS relief capped at RM3,000."""

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_ytd_total")
    def test_under_cap(self, mock_ytd):
        """Relief equals YTD when under RM3,000."""
        mock_ytd.return_value = 2000.0
        result = get_prs_relief_amount("EMP-001", 2026)
        self.assertEqual(result, 2000.0)

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_ytd_total")
    def test_at_cap(self, mock_ytd):
        """Relief equals RM3,000 when YTD equals cap."""
        mock_ytd.return_value = 3000.0
        result = get_prs_relief_amount("EMP-001", 2026)
        self.assertEqual(result, 3000.0)

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_ytd_total")
    def test_over_cap(self, mock_ytd):
        """Relief capped at RM3,000 when YTD exceeds cap."""
        mock_ytd.return_value = 5000.0
        result = get_prs_relief_amount("EMP-001", 2026)
        self.assertEqual(result, 3000.0)

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_ytd_total")
    def test_zero_ytd(self, mock_ytd):
        """Relief is 0 when no PRS deductions."""
        mock_ytd.return_value = 0.0
        result = get_prs_relief_amount("EMP-001", 2026)
        self.assertEqual(result, 0.0)

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_ytd_total")
    def test_slightly_over_cap(self, mock_ytd):
        """Relief is exactly RM3,000 when YTD is RM3,001."""
        mock_ytd.return_value = 3001.0
        result = get_prs_relief_amount("EMP-001", 2026)
        self.assertEqual(result, 3000.0)


# ---------------------------------------------------------------------------
# Test: Sync PRS to TP1 (sync_prs_to_tp1)
# ---------------------------------------------------------------------------

class TestSyncPrsToTp1(FrappeTestCase):
    """Test auto-population of TP1 prs_contribution field."""

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_relief_amount")
    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_updates_tp1_when_record_exists(self, mock_frappe, mock_relief):
        """Updates TP1 prs_contribution when TP1 record exists and value changed."""
        mock_relief.return_value = 2500.0
        mock_frappe.db.get_value.return_value = "TP1-EMP-001-2026"
        mock_doc = MagicMock()
        mock_doc.prs_contribution = 0.0
        mock_frappe.get_doc.return_value = mock_doc

        result = sync_prs_to_tp1("EMP-001", 2026)

        self.assertTrue(result["updated"])
        self.assertEqual(result["amount"], 2500.0)
        self.assertEqual(result["docname"], "TP1-EMP-001-2026")
        self.assertEqual(mock_doc.prs_contribution, 2500.0)
        mock_doc.save.assert_called_once_with(ignore_permissions=True)

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_relief_amount")
    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_no_update_when_value_same(self, mock_frappe, mock_relief):
        """Does not save TP1 when prs_contribution already matches."""
        mock_relief.return_value = 2500.0
        mock_frappe.db.get_value.return_value = "TP1-EMP-001-2026"
        mock_doc = MagicMock()
        mock_doc.prs_contribution = 2500.0
        mock_frappe.get_doc.return_value = mock_doc
        # flt mock
        from frappe.utils import flt as real_flt

        result = sync_prs_to_tp1("EMP-001", 2026)

        self.assertFalse(result["updated"])
        mock_doc.save.assert_not_called()

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_relief_amount")
    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_no_tp1_record(self, mock_frappe, mock_relief):
        """Returns updated=False when no TP1 record exists."""
        mock_relief.return_value = 1000.0
        mock_frappe.db.get_value.return_value = None

        result = sync_prs_to_tp1("EMP-001", 2026)

        self.assertFalse(result["updated"])
        self.assertIsNone(result["docname"])
        self.assertEqual(result["amount"], 1000.0)


# ---------------------------------------------------------------------------
# Test: PRS for EA Form (get_prs_for_ea_form)
# ---------------------------------------------------------------------------

class TestGetPrsForEaForm(FrappeTestCase):
    """Test EA Form PRS deduction amount (raw YTD, not capped)."""

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_ytd_total")
    def test_returns_raw_ytd(self, mock_ytd):
        """EA Form shows raw PRS YTD, not capped at RM3,000."""
        mock_ytd.return_value = 4500.0
        result = get_prs_for_ea_form("EMP-001", 2026)
        self.assertEqual(result, 4500.0)

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_ytd_total")
    def test_zero_when_no_prs(self, mock_ytd):
        """EA Form shows 0 when no PRS deductions."""
        mock_ytd.return_value = 0.0
        result = get_prs_for_ea_form("EMP-001", 2026)
        self.assertEqual(result, 0.0)


# ---------------------------------------------------------------------------
# Test: Employee PRS Details (get_prs_employee_details)
# ---------------------------------------------------------------------------

class TestGetPrsEmployeeDetails(FrappeTestCase):
    """Test PRS provider/account lookup from Employee."""

    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_returns_provider_and_account(self, mock_frappe):
        """Returns PRS provider name and account number."""
        mock_frappe.db.get_value.return_value = {
            "custom_prs_provider_name": "AmInvest",
            "custom_prs_account_number": "PRS-12345678",
        }
        result = get_prs_employee_details("EMP-001")
        self.assertEqual(result["provider_name"], "AmInvest")
        self.assertEqual(result["account_number"], "PRS-12345678")

    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_returns_empty_when_no_employee(self, mock_frappe):
        """Returns empty strings when employee not found."""
        mock_frappe.db.get_value.return_value = None
        result = get_prs_employee_details("EMP-NONEXIST")
        self.assertEqual(result["provider_name"], "")
        self.assertEqual(result["account_number"], "")

    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_handles_null_fields(self, mock_frappe):
        """Returns empty strings when PRS fields are null on Employee."""
        mock_frappe.db.get_value.return_value = {
            "custom_prs_provider_name": None,
            "custom_prs_account_number": None,
        }
        result = get_prs_employee_details("EMP-001")
        self.assertEqual(result["provider_name"], "")
        self.assertEqual(result["account_number"], "")


# ---------------------------------------------------------------------------
# Test: Validate PRS Deduction on Slip (validate_prs_deduction_on_slip)
# ---------------------------------------------------------------------------

class TestValidatePrsDeductionOnSlip(FrappeTestCase):
    """Test PRS deduction validation on Salary Slip."""

    def _make_slip(self, prs_amount=0.0, start_date="2026-01-01"):
        """Create a mock Salary Slip with PRS deduction."""
        slip = MagicMock()
        slip.employee = "EMP-001"
        slip.start_date = start_date

        prs_detail = MagicMock()
        prs_detail.salary_component = "Private Retirement Scheme (PRS)"
        prs_detail.amount = prs_amount

        other_detail = MagicMock()
        other_detail.salary_component = "EPF Employee"
        other_detail.amount = 500.0

        slip.deductions = [other_detail, prs_detail] if prs_amount else [other_detail]
        return slip

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_ytd_total")
    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_no_validation_when_no_prs(self, mock_frappe, mock_ytd):
        """No validation when slip has no PRS deduction."""
        slip = self._make_slip(prs_amount=0)
        validate_prs_deduction_on_slip(slip)
        mock_ytd.assert_not_called()

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_ytd_total")
    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_warns_when_ytd_exceeds_cap(self, mock_frappe, mock_ytd):
        """Warns when projected YTD exceeds RM3,000 cap."""
        mock_ytd.return_value = 2800.0
        mock_frappe._ = lambda x: x  # identity for translation
        slip = self._make_slip(prs_amount=500.0)
        validate_prs_deduction_on_slip(slip)
        mock_frappe.msgprint.assert_called_once()
        msg = mock_frappe.msgprint.call_args[0][0]
        self.assertIn("3,300.00", msg)  # 2800 + 500 = 3300

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_ytd_total")
    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_no_warning_when_under_cap(self, mock_frappe, mock_ytd):
        """No warning when projected YTD is under RM3,000."""
        mock_ytd.return_value = 1000.0
        mock_frappe._ = lambda x: x
        slip = self._make_slip(prs_amount=250.0)
        validate_prs_deduction_on_slip(slip)
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.services.prs_deduction_service.get_prs_ytd_total")
    @patch("lhdn_payroll_integration.services.prs_deduction_service.frappe")
    def test_no_warning_when_exactly_at_cap(self, mock_frappe, mock_ytd):
        """No warning when projected YTD equals exactly RM3,000."""
        mock_ytd.return_value = 2750.0
        mock_frappe._ = lambda x: x
        slip = self._make_slip(prs_amount=250.0)
        validate_prs_deduction_on_slip(slip)
        mock_frappe.msgprint.assert_not_called()


# ---------------------------------------------------------------------------
# Test: TP1 Relief Field Exists for PRS
# ---------------------------------------------------------------------------

class TestTp1PrsReliefField(FrappeTestCase):
    """Verify TP1 DocType has prs_contribution in relief fields and cap table."""

    def test_prs_in_relief_fields(self):
        """prs_contribution is listed in _RELIEF_FIELDS."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
            _RELIEF_FIELDS,
        )
        self.assertIn("prs_contribution", _RELIEF_FIELDS)

    def test_prs_cap_in_default_caps(self):
        """prs_contribution has RM3,000 cap in _CAPS_DEFAULT."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
            _CAPS_DEFAULT,
        )
        self.assertEqual(_CAPS_DEFAULT["prs_contribution"], 3_000)

    def test_prs_cap_in_ya2025_caps(self):
        """prs_contribution cap is RM3,000 in YA2025."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
            _CAPS_YA2025,
        )
        self.assertEqual(_CAPS_YA2025["prs_contribution"], 3_000)

    def test_prs_cap_in_ya2026_caps(self):
        """prs_contribution cap is RM3,000 in YA2026."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
            _CAPS_YA2026,
        )
        self.assertEqual(_CAPS_YA2026["prs_contribution"], 3_000)


# ---------------------------------------------------------------------------
# Test: Custom Field Fixtures for PRS
# ---------------------------------------------------------------------------

class TestPrsCustomFieldFixtures(FrappeTestCase):
    """Verify PRS custom fields exist in fixture for Employee."""

    def _load_custom_fields(self):
        import json
        import os
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures", "custom_field.json"
        )
        with open(fixture_path) as f:
            return json.load(f)

    def test_prs_section_exists(self):
        """PRS section break exists on Employee."""
        fields = self._load_custom_fields()
        section = [f for f in fields if f["fieldname"] == "custom_prs_section"]
        self.assertEqual(len(section), 1)
        self.assertEqual(section[0]["dt"], "Employee")
        self.assertEqual(section[0]["fieldtype"], "Section Break")

    def test_prs_provider_name_field(self):
        """PRS provider name field exists on Employee."""
        fields = self._load_custom_fields()
        field = [f for f in fields if f["fieldname"] == "custom_prs_provider_name"]
        self.assertEqual(len(field), 1)
        self.assertEqual(field[0]["dt"], "Employee")
        self.assertEqual(field[0]["fieldtype"], "Data")

    def test_prs_account_number_field(self):
        """PRS account number field exists on Employee."""
        fields = self._load_custom_fields()
        field = [f for f in fields if f["fieldname"] == "custom_prs_account_number"]
        self.assertEqual(len(field), 1)
        self.assertEqual(field[0]["dt"], "Employee")
        self.assertEqual(field[0]["fieldtype"], "Data")

    def test_prs_voluntary_flag_on_salary_component(self):
        """custom_is_prs_voluntary Check field exists on Salary Component."""
        fields = self._load_custom_fields()
        field = [f for f in fields if f["fieldname"] == "custom_is_prs_voluntary"]
        self.assertEqual(len(field), 1)
        self.assertEqual(field[0]["dt"], "Salary Component")
        self.assertEqual(field[0]["fieldtype"], "Check")


# ---------------------------------------------------------------------------
# Test: EA Form PRS Column
# ---------------------------------------------------------------------------

class TestEaFormPrsColumn(FrappeTestCase):
    """Verify EA Form report includes PRS in deductions section."""

    def test_d1_prs_column_exists(self):
        """EA Form has d1_prs column for PRS deduction."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form.ea_form import get_columns
        cols = get_columns()
        prs_cols = [c for c in cols if c["fieldname"] == "d1_prs"]
        self.assertEqual(len(prs_cols), 1)
        self.assertEqual(prs_cols[0]["fieldtype"], "Currency")
        self.assertIn("PRS", prs_cols[0]["label"])


# ---------------------------------------------------------------------------
# Test: PRS Does NOT Affect Statutory Contribution Base
# ---------------------------------------------------------------------------

class TestPrsDoesNotAffectStatutoryBase(FrappeTestCase):
    """PRS is applied after statutory deductions — does not reduce EPF/SOCSO/EIS base."""

    def test_prs_not_epf_employee(self):
        """PRS component is NOT flagged as EPF employee deduction."""
        import json
        import os
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures", "salary_component.json"
        )
        with open(fixture_path) as f:
            components = json.load(f)
        prs = [c for c in components if c["name"] == "Private Retirement Scheme (PRS)"][0]
        self.assertNotEqual(prs.get("custom_is_epf_employee"), 1)

    def test_prs_not_excluded_from_invoice(self):
        """PRS deduction is not excluded from e-invoice (visible on payslip)."""
        import json
        import os
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures", "salary_component.json"
        )
        with open(fixture_path) as f:
            components = json.load(f)
        prs = [c for c in components if c["name"] == "Private Retirement Scheme (PRS)"][0]
        self.assertEqual(prs.get("custom_lhdn_exclude_from_invoice"), 0)
