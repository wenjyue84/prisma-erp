"""Tests for US-041: LHDN Year-End PCB vs Submission Reconciliation Report."""
from unittest.mock import patch, MagicMock

from frappe.tests.utils import FrappeTestCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(
    employee="EMP-001",
    employee_name="Ahmad bin Ali",
    annual_gross=60000.0,
    total_pcb=3600.0,
    submitted=12,
    valid=12,
):
    """Build a mock DB row as returned by _get_salary_slip_aggregates."""
    return {
        "employee": employee,
        "employee_name": employee_name,
        "annual_gross_income": annual_gross,
        "total_pcb_withheld": total_pcb,
        "invoices_submitted": submitted,
        "invoices_valid": valid,
    }


# ---------------------------------------------------------------------------
# Discrepancy detection
# ---------------------------------------------------------------------------

class TestDiscrepancyDetection(FrappeTestCase):
    """Unit tests for _has_discrepancy logic."""

    def _run(self, submitted, valid, pcb):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_yearend_reconciliation.lhdn_yearend_reconciliation import (
            _has_discrepancy,
        )
        row = {
            "invoices_submitted": submitted,
            "invoices_valid": valid,
            "total_pcb_withheld": pcb,
        }
        return _has_discrepancy(row)

    def test_no_discrepancy_when_all_valid(self):
        """12 submitted, 12 valid, PCB > 0 → no discrepancy."""
        self.assertFalse(self._run(12, 12, 3600.0))

    def test_discrepancy_when_some_rejected(self):
        """12 submitted, 10 valid → discrepancy."""
        self.assertTrue(self._run(12, 10, 3600.0))

    def test_discrepancy_when_zero_valid_but_pcb_withheld(self):
        """12 submitted, 0 valid, PCB > 0 → discrepancy."""
        self.assertTrue(self._run(12, 0, 3600.0))

    def test_no_discrepancy_when_zero_submitted_and_zero_pcb(self):
        """0 submitted, 0 valid, 0 PCB → no discrepancy."""
        self.assertFalse(self._run(0, 0, 0.0))

    def test_discrepancy_when_one_slip_invalid(self):
        """1 submitted, 0 valid, PCB > 0 → discrepancy."""
        self.assertTrue(self._run(1, 0, 300.0))

    def test_no_discrepancy_zero_submitted_zero_valid_with_pcb(self):
        """0 submitted, 0 valid, PCB > 0 → no discrepancy (submitted==valid)."""
        # submitted == valid (both 0) but pcb > 0 and valid == 0 → DISCREPANCY
        self.assertTrue(self._run(0, 0, 300.0))


# ---------------------------------------------------------------------------
# Mock 12-month data scenario
# ---------------------------------------------------------------------------

_TWELVE_MONTH_ROWS = [
    {
        "employee": "EMP-001",
        "employee_name": "Ahmad bin Ali",
        "annual_gross_income": 72000.0,
        "total_pcb_withheld": 4320.0,
        "invoices_submitted": 12,
        "invoices_valid": 12,
    },
    {
        "employee": "EMP-002",
        "employee_name": "Siti binti Zainab",
        "annual_gross_income": 60000.0,
        "total_pcb_withheld": 2400.0,
        "invoices_submitted": 12,
        "invoices_valid": 10,   # 2 invoices rejected by LHDN
    },
    {
        "employee": "EMP-003",
        "employee_name": "Rajan s/o Muthu",
        "annual_gross_income": 48000.0,
        "total_pcb_withheld": 0.0,
        "invoices_submitted": 12,
        "invoices_valid": 12,
    },
]


class TestYearEndReconciliationGetData(FrappeTestCase):
    """Test get_data with mocked 12-month dataset."""

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report"
        ".lhdn_yearend_reconciliation.lhdn_yearend_reconciliation.frappe"
    )
    def test_no_company_returns_empty(self, mock_frappe):
        mock_frappe._dict = dict
        from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_yearend_reconciliation.lhdn_yearend_reconciliation import (
            get_data,
        )
        self.assertEqual(get_data({}), [])

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report"
        ".lhdn_yearend_reconciliation.lhdn_yearend_reconciliation._get_salary_slip_aggregates"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report"
        ".lhdn_yearend_reconciliation.lhdn_yearend_reconciliation.frappe"
    )
    def test_discrepancy_flag_set_on_rejected_employee(
        self, mock_frappe, mock_agg
    ):
        """EMP-002 has 2 rejected invoices → discrepancy_flag = 'YES'."""
        mock_frappe._dict = dict
        mock_agg.return_value = [dict(r) for r in _TWELVE_MONTH_ROWS]

        from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_yearend_reconciliation.lhdn_yearend_reconciliation import (
            get_data,
        )
        rows = get_data({"company": "Test Co", "year": 2025})

        emp_002 = next(r for r in rows if r["employee"] == "EMP-002")
        self.assertEqual(emp_002["discrepancy_flag"], "YES")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report"
        ".lhdn_yearend_reconciliation.lhdn_yearend_reconciliation._get_salary_slip_aggregates"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report"
        ".lhdn_yearend_reconciliation.lhdn_yearend_reconciliation.frappe"
    )
    def test_clean_employee_has_no_flag(self, mock_frappe, mock_agg):
        """EMP-001 has all 12 invoices valid → discrepancy_flag = ''."""
        mock_frappe._dict = dict
        mock_agg.return_value = [dict(r) for r in _TWELVE_MONTH_ROWS]

        from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_yearend_reconciliation.lhdn_yearend_reconciliation import (
            get_data,
        )
        rows = get_data({"company": "Test Co", "year": 2025})

        emp_001 = next(r for r in rows if r["employee"] == "EMP-001")
        self.assertEqual(emp_001["discrepancy_flag"], "")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report"
        ".lhdn_yearend_reconciliation.lhdn_yearend_reconciliation._get_salary_slip_aggregates"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report"
        ".lhdn_yearend_reconciliation.lhdn_yearend_reconciliation.frappe"
    )
    def test_zero_pcb_employee_no_flag(self, mock_frappe, mock_agg):
        """EMP-003 has 0 PCB withheld, all valid → no discrepancy."""
        mock_frappe._dict = dict
        mock_agg.return_value = [dict(r) for r in _TWELVE_MONTH_ROWS]

        from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_yearend_reconciliation.lhdn_yearend_reconciliation import (
            get_data,
        )
        rows = get_data({"company": "Test Co", "year": 2025})

        emp_003 = next(r for r in rows if r["employee"] == "EMP-003")
        self.assertEqual(emp_003["discrepancy_flag"], "")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report"
        ".lhdn_yearend_reconciliation.lhdn_yearend_reconciliation._get_salary_slip_aggregates"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report"
        ".lhdn_yearend_reconciliation.lhdn_yearend_reconciliation.frappe"
    )
    def test_returns_three_rows(self, mock_frappe, mock_agg):
        """Full 12-month dataset returns all 3 employees."""
        mock_frappe._dict = dict
        mock_agg.return_value = [dict(r) for r in _TWELVE_MONTH_ROWS]

        from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_yearend_reconciliation.lhdn_yearend_reconciliation import (
            get_data,
        )
        rows = get_data({"company": "Test Co", "year": 2025})
        self.assertEqual(len(rows), 3)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report"
        ".lhdn_yearend_reconciliation.lhdn_yearend_reconciliation._get_salary_slip_aggregates"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report"
        ".lhdn_yearend_reconciliation.lhdn_yearend_reconciliation.frappe"
    )
    def test_gross_income_totals_correct(self, mock_frappe, mock_agg):
        """Annual gross income is propagated correctly for EMP-001."""
        mock_frappe._dict = dict
        mock_agg.return_value = [dict(r) for r in _TWELVE_MONTH_ROWS]

        from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_yearend_reconciliation.lhdn_yearend_reconciliation import (
            get_data,
        )
        rows = get_data({"company": "Test Co", "year": 2025})

        emp_001 = next(r for r in rows if r["employee"] == "EMP-001")
        self.assertAlmostEqual(emp_001["annual_gross_income"], 72000.0, places=2)
        self.assertAlmostEqual(emp_001["total_pcb_withheld"], 4320.0, places=2)


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

class TestYearEndReconciliationColumns(FrappeTestCase):

    def test_columns_include_required_fieldnames(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_yearend_reconciliation.lhdn_yearend_reconciliation import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        for required in [
            "employee",
            "employee_name",
            "annual_gross_income",
            "total_pcb_withheld",
            "invoices_submitted",
            "invoices_valid",
            "discrepancy_flag",
        ]:
            self.assertIn(required, fieldnames, f"Missing column: {required}")

    def test_execute_returns_tuple(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_yearend_reconciliation.lhdn_yearend_reconciliation import (
            execute,
        )
        cols, data = execute({})
        self.assertIsInstance(cols, list)
        self.assertIsInstance(data, list)
        self.assertGreater(len(cols), 0)
