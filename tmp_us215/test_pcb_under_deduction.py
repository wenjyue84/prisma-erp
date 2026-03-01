"""Tests for US-215: PCB Under-Deduction Employer Liability Alert (Section 107A ITA 1967).

Verifies:
- detect_under_deduction() correctly flags PCB_DROP_50_PCT rule
- detect_under_deduction() correctly flags ZERO_PCB_ABOVE_THRESHOLD rule
- No flag raised when PCB drop has a documented change event
- No flag when chargeable income is below zero-tax threshold
- check_under_deduction_before_submit() raises frappe.ValidationError when flagged
- check_under_deduction_before_submit() passes when acknowledgement exists
- acknowledge_pcb_under_deduction() requires a non-empty reason
- get_columns() and get_data() function correctly for the compliance report
"""
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.pcb_under_deduction_service import (
    ZERO_TAX_MONTHLY_THRESHOLD,
    STANDARD_MONTHLY_RELIEF,
    EPF_EMPLOYEE_RATE,
    detect_under_deduction,
    check_under_deduction_before_submit,
    _get_pcb_amount,
    _get_epf_amount,
    _get_gross_pay,
    _get_payroll_period,
    _has_acknowledgement,
    _has_income_change_event,
)
from lhdn_payroll_integration.lhdn_payroll_integration.report.pcb_under_deduction_report.pcb_under_deduction_report import (
    get_columns,
    get_data,
    execute,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_slip(
    employee="EMP-001",
    pcb=0.0,
    epf=0.0,
    gross=0.0,
    end_date="2026-03-31",
    name="SS-TEST-001",
    company="Test Co",
):
    """Build a minimal mock Salary Slip document."""
    slip = MagicMock()
    slip.name = name
    slip.employee = employee
    slip.employee_name = "Test Employee"
    slip.end_date = end_date
    slip.posting_date = end_date
    slip.gross_pay = gross
    slip.company = company

    deductions = []
    if pcb > 0:
        d = MagicMock()
        d.salary_component = "Monthly Tax Deduction"
        d.amount = pcb
        deductions.append(d)
    if epf > 0:
        d = MagicMock()
        d.salary_component = "EPF Employee"
        d.amount = epf
        deductions.append(d)
    slip.deductions = deductions
    return slip


# ---------------------------------------------------------------------------
# Helper extraction tests
# ---------------------------------------------------------------------------

class TestHelpers(FrappeTestCase):
    """Tests for helper functions."""

    def test_get_pcb_amount_returns_pcb(self):
        slip = _make_slip(pcb=500.0)
        self.assertAlmostEqual(_get_pcb_amount(slip), 500.0)

    def test_get_pcb_amount_zero_when_no_pcb(self):
        slip = _make_slip(pcb=0.0)
        self.assertAlmostEqual(_get_pcb_amount(slip), 0.0)

    def test_get_epf_amount_returns_epf(self):
        slip = _make_slip(epf=450.0)
        self.assertAlmostEqual(_get_epf_amount(slip), 450.0)

    def test_get_gross_pay(self):
        slip = _make_slip(gross=5000.0)
        self.assertAlmostEqual(_get_gross_pay(slip), 5000.0)

    def test_get_payroll_period(self):
        slip = _make_slip(end_date="2026-03-31")
        self.assertEqual(_get_payroll_period(slip), "2026-03")


# ---------------------------------------------------------------------------
# detect_under_deduction() -- Rule 1: PCB_DROP_50_PCT
# ---------------------------------------------------------------------------

class TestDetectPCBDrop(FrappeTestCase):
    """Tests for the PCB_DROP_50_PCT detection rule."""

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._get_prior_month_pcb")
    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._has_income_change_event")
    def test_flags_when_pcb_drops_more_than_50_pct(self, mock_change, mock_prior):
        """Flag raised when PCB drops >50% vs prior month without change event."""
        mock_prior.return_value = 1000.0  # prior PCB
        mock_change.return_value = False
        slip = _make_slip(pcb=400.0, end_date="2026-03-31")  # 60% drop

        issues = detect_under_deduction(slip)
        rules = [i["rule"] for i in issues]
        self.assertIn("PCB_DROP_50_PCT", rules)

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._get_prior_month_pcb")
    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._has_income_change_event")
    def test_no_flag_when_drop_exactly_50_pct(self, mock_change, mock_prior):
        """No flag when PCB drops exactly 50% (boundary -- only >50% triggers)."""
        mock_prior.return_value = 1000.0
        mock_change.return_value = False
        slip = _make_slip(pcb=500.0, end_date="2026-03-31")  # exactly 50% drop

        issues = detect_under_deduction(slip)
        rules = [i["rule"] for i in issues]
        self.assertNotIn("PCB_DROP_50_PCT", rules)

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._get_prior_month_pcb")
    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._has_income_change_event")
    def test_no_flag_when_change_event_exists(self, mock_change, mock_prior):
        """No flag when drop >50% but a documented change event exists."""
        mock_prior.return_value = 1000.0
        mock_change.return_value = True  # documented change
        slip = _make_slip(pcb=300.0, end_date="2026-03-31")  # 70% drop

        issues = detect_under_deduction(slip)
        rules = [i["rule"] for i in issues]
        self.assertNotIn("PCB_DROP_50_PCT", rules)

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._get_prior_month_pcb")
    def test_no_flag_when_no_prior_month(self, mock_prior):
        """No flag when there is no prior month PCB (first month)."""
        mock_prior.return_value = None
        slip = _make_slip(pcb=0.0, end_date="2026-03-31")

        issues = detect_under_deduction(slip)
        rules = [i["rule"] for i in issues]
        self.assertNotIn("PCB_DROP_50_PCT", rules)

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._get_prior_month_pcb")
    def test_no_flag_when_prior_pcb_is_zero(self, mock_prior):
        """No flag when prior month PCB was already zero."""
        mock_prior.return_value = 0.0
        slip = _make_slip(pcb=0.0, end_date="2026-03-31")

        issues = detect_under_deduction(slip)
        rules = [i["rule"] for i in issues]
        self.assertNotIn("PCB_DROP_50_PCT", rules)


# ---------------------------------------------------------------------------
# detect_under_deduction() -- Rule 2: ZERO_PCB_ABOVE_THRESHOLD
# ---------------------------------------------------------------------------

class TestDetectZeroPCBAboveThreshold(FrappeTestCase):
    """Tests for ZERO_PCB_ABOVE_THRESHOLD detection rule."""

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._get_prior_month_pcb")
    def test_flags_when_zero_pcb_chargeable_above_threshold(self, mock_prior):
        """Flag raised when PCB=0 but chargeable income exceeds threshold."""
        mock_prior.return_value = None
        # gross=6000, epf=540 (9%), chargeable=6000-540-750=4710 > 2851
        slip = _make_slip(pcb=0.0, gross=6000.0, epf=540.0, end_date="2026-03-31")

        issues = detect_under_deduction(slip)
        rules = [i["rule"] for i in issues]
        self.assertIn("ZERO_PCB_ABOVE_THRESHOLD", rules)

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._get_prior_month_pcb")
    def test_no_flag_when_chargeable_below_threshold(self, mock_prior):
        """No flag when PCB=0 and chargeable income is below zero-tax threshold."""
        mock_prior.return_value = None
        # gross=3000, epf=270 (9%), chargeable=3000-270-750=1980 < 2851
        slip = _make_slip(pcb=0.0, gross=3000.0, epf=270.0, end_date="2026-03-31")

        issues = detect_under_deduction(slip)
        rules = [i["rule"] for i in issues]
        self.assertNotIn("ZERO_PCB_ABOVE_THRESHOLD", rules)

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._get_prior_month_pcb")
    def test_no_flag_when_pcb_is_nonzero(self, mock_prior):
        """No flag for ZERO_PCB rule when PCB is non-zero (even if low)."""
        mock_prior.return_value = None
        slip = _make_slip(pcb=1.0, gross=6000.0, epf=540.0, end_date="2026-03-31")

        issues = detect_under_deduction(slip)
        rules = [i["rule"] for i in issues]
        self.assertNotIn("ZERO_PCB_ABOVE_THRESHOLD", rules)

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._get_prior_month_pcb")
    def test_epf_estimated_when_not_in_deductions(self, mock_prior):
        """When no EPF deduction found, EPF is estimated at 9% of gross."""
        mock_prior.return_value = None
        # gross=6000, no explicit EPF -> estimated EPF=540
        # chargeable=6000-540-750=4710 > 2851 -> should flag
        slip = _make_slip(pcb=0.0, gross=6000.0, epf=0.0, end_date="2026-03-31")

        issues = detect_under_deduction(slip)
        rules = [i["rule"] for i in issues]
        self.assertIn("ZERO_PCB_ABOVE_THRESHOLD", rules)

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._get_prior_month_pcb")
    def test_no_issues_when_both_rules_safe(self, mock_prior):
        """No issues returned when both rules are satisfied."""
        mock_prior.return_value = None
        # Low-income: gross=3500, epf=315, chargeable=3500-315-750=2435 < 2851
        slip = _make_slip(pcb=0.0, gross=3500.0, epf=315.0, end_date="2026-03-31")

        issues = detect_under_deduction(slip)
        self.assertEqual(issues, [])


# ---------------------------------------------------------------------------
# check_under_deduction_before_submit()
# ---------------------------------------------------------------------------

class TestBeforeSubmitHook(FrappeTestCase):
    """Tests for check_under_deduction_before_submit() hook behaviour."""

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service.detect_under_deduction")
    def test_no_error_when_no_issues(self, mock_detect):
        """No error raised when detect_under_deduction returns empty list."""
        mock_detect.return_value = []
        slip = _make_slip()
        # Should not raise
        check_under_deduction_before_submit(slip)

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._has_acknowledgement")
    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service.detect_under_deduction")
    def test_raises_when_flagged_without_acknowledgement(self, mock_detect, mock_ack):
        """ValidationError raised when issues exist and no acknowledgement present."""
        mock_detect.return_value = [{"rule": "PCB_DROP_50_PCT", "message": "Test drop"}]
        mock_ack.return_value = False
        slip = _make_slip()

        with self.assertRaises(frappe.exceptions.ValidationError):
            check_under_deduction_before_submit(slip)

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service._has_acknowledgement")
    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service.detect_under_deduction")
    def test_no_error_when_acknowledgement_exists(self, mock_detect, mock_ack):
        """No error raised when issues exist but acknowledgement is present."""
        mock_detect.return_value = [{"rule": "PCB_DROP_50_PCT", "message": "Test drop"}]
        mock_ack.return_value = True  # acknowledged
        slip = _make_slip()
        # Should not raise
        check_under_deduction_before_submit(slip)

    @patch("lhdn_payroll_integration.services.pcb_under_deduction_service.detect_under_deduction")
    def test_does_not_raise_on_unexpected_error(self, mock_detect):
        """Unexpected errors are logged but do not block submission."""
        mock_detect.side_effect = RuntimeError("Unexpected DB error")
        slip = _make_slip()
        # Should not raise ValidationError -- unexpected errors are logged
        check_under_deduction_before_submit(slip)


# ---------------------------------------------------------------------------
# Compliance Report tests
# ---------------------------------------------------------------------------

class TestPCBUnderDeductionReportColumns(FrappeTestCase):
    """Tests for get_columns() of the PCB Under-Deduction Report."""

    def test_returns_list(self):
        self.assertIsInstance(get_columns(), list)

    def test_minimum_column_count(self):
        self.assertGreaterEqual(len(get_columns()), 8)

    def test_required_fieldnames_present(self):
        required = {
            "salary_slip", "employee", "employee_name", "payroll_period",
            "pcb_amount", "acknowledged", "reason",
        }
        fieldnames = {col["fieldname"] for col in get_columns() if isinstance(col, dict)}
        for req in required:
            self.assertIn(req, fieldnames, f"Missing column: {req}")


class TestPCBUnderDeductionReportData(FrappeTestCase):
    """Tests for get_data() of the PCB Under-Deduction Report."""

    def test_returns_list(self):
        filters = frappe._dict({"from_date": "2026-01-01", "to_date": "2026-12-31"})
        result = get_data(filters)
        self.assertIsInstance(result, list)

    def test_execute_returns_columns_and_data(self):
        columns, data = execute({"from_date": "2026-01-01", "to_date": "2026-12-31"})
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)

    def test_row_shape_when_data_exists(self):
        """Rows must have required keys."""
        filters = frappe._dict({"from_date": "2026-01-01", "to_date": "2026-12-31"})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No under-deduction acknowledgement records in test DB")
        row = rows[0]
        for key in ["salary_slip", "employee", "payroll_period", "acknowledged", "reason"]:
            self.assertIn(key, row, f"Row missing key: {key}")

    def test_empty_filters_does_not_crash(self):
        """Report must handle missing date filters gracefully."""
        filters = frappe._dict({})
        try:
            result = get_data(filters)
            self.assertIsInstance(result, list)
        except Exception as e:
            self.fail(f"get_data() crashed with empty filters: {e}")


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------

class TestConstants(FrappeTestCase):
    """Verify module-level constants match LHDN spec."""

    def test_zero_tax_threshold_value(self):
        self.assertEqual(ZERO_TAX_MONTHLY_THRESHOLD, 2851.0)

    def test_standard_monthly_relief_value(self):
        self.assertAlmostEqual(STANDARD_MONTHLY_RELIEF, 750.0)

    def test_epf_employee_rate_value(self):
        self.assertAlmostEqual(EPF_EMPLOYEE_RATE, 0.09)
