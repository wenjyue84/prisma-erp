"""Tests for US-101: Salary Advance Loan Module with Employment Act S.22/24 50% Cap.

Covers:
- SalaryAdvanceLoan DocType (outstanding_balance, projected_clearance_date, apply_repayment)
- salary_advance_service.compute_advance_repayment_for_salary_slip()
  - Active loan detection
  - 50% deduction cap enforcement
  - Advance repayment row injection
  - Loan balance update (apply_repayment)
- Active Salary Advances report (execute())
"""
from unittest.mock import MagicMock, patch, call
from frappe.tests.utils import FrappeTestCase


# ---------------------------------------------------------------------------
# DocType controller tests
# ---------------------------------------------------------------------------

class TestSalaryAdvanceLoanController(FrappeTestCase):
    """Tests for SalaryAdvanceLoan controller logic."""

    def _make_loan(self, amount=5000, repayment=1000, outstanding=None, status="Active"):
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.salary_advance_loan.salary_advance_loan import SalaryAdvanceLoan
        loan = SalaryAdvanceLoan.__new__(SalaryAdvanceLoan)
        # Minimal Document-like init
        loan.amount = amount
        loan.repayment_amount_per_period = repayment
        loan.outstanding_balance = outstanding if outstanding is not None else amount
        loan.status = status
        loan.repayment_history = []
        loan.name = "SAL-ADV-001"
        return loan

    def test_doctype_importable(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.salary_advance_loan.salary_advance_loan import SalaryAdvanceLoan
        self.assertTrue(SalaryAdvanceLoan is not None)

    def test_child_doctype_importable(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.salary_advance_repayment.salary_advance_repayment import SalaryAdvanceRepayment
        self.assertTrue(SalaryAdvanceRepayment is not None)

    def test_apply_repayment_reduces_outstanding_balance(self):
        """apply_repayment() should reduce outstanding_balance by the deducted amount."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.salary_advance_loan.salary_advance_loan import SalaryAdvanceLoan
        loan = self._make_loan(amount=5000, repayment=1000, outstanding=5000)
        loan.append = MagicMock()
        with patch.object(loan, "save"):
            loan.apply_repayment(1000, "SS-001", "Jan 2025", "2025-01-31")
        self.assertAlmostEqual(loan.outstanding_balance, 4000)

    def test_apply_repayment_adds_history_row(self):
        """apply_repayment() should append a repayment_history row."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.salary_advance_loan.salary_advance_loan import SalaryAdvanceLoan
        loan = self._make_loan(amount=5000, repayment=1000, outstanding=5000)
        loan.repayment_history = []

        def mock_append(table, row):
            loan.repayment_history.append(row)

        loan.append = mock_append
        with patch.object(loan, "save"):
            loan.apply_repayment(1000, "SS-001", "Jan 2025", "2025-01-31")

        self.assertEqual(len(loan.repayment_history), 1)
        row = loan.repayment_history[0]
        self.assertEqual(row["salary_slip"], "SS-001")
        self.assertAlmostEqual(row["amount_deducted"], 1000)
        self.assertAlmostEqual(row["balance_after"], 4000)

    def test_apply_repayment_marks_fully_repaid_when_balance_zero(self):
        """When outstanding drops to 0, status should become 'Fully Repaid'."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.salary_advance_loan.salary_advance_loan import SalaryAdvanceLoan
        loan = self._make_loan(amount=1000, repayment=1000, outstanding=800)
        loan.append = MagicMock()
        with patch.object(loan, "save"):
            loan.apply_repayment(800, "SS-002", "Feb 2025", "2025-02-28")
        self.assertEqual(loan.status, "Fully Repaid")
        self.assertAlmostEqual(loan.outstanding_balance, 0)

    def test_apply_repayment_does_not_go_negative(self):
        """outstanding_balance should floor at 0, never go negative."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.salary_advance_loan.salary_advance_loan import SalaryAdvanceLoan
        loan = self._make_loan(outstanding=200)
        loan.append = MagicMock()
        with patch.object(loan, "save"):
            loan.apply_repayment(500, "SS-003", "Mar 2025", "2025-03-31")
        self.assertGreaterEqual(loan.outstanding_balance, 0)


# ---------------------------------------------------------------------------
# Service: compute_advance_repayment_for_salary_slip
# ---------------------------------------------------------------------------

class TestComputeAdvanceRepayment(FrappeTestCase):
    """Tests for salary_advance_service.compute_advance_repayment_for_salary_slip()."""

    def _make_slip(self, employee="EMP-001", gross_pay=10000, deductions=None):
        slip = MagicMock()
        slip.employee = employee
        slip.gross_pay = gross_pay
        slip.end_date = "2025-01-31"
        slip.posting_date = "2025-01-31"
        slip.name = "SS-TEST-001"
        slip_deductions = list(deductions or [])
        slip.get = lambda field, default=None: slip_deductions if field == "deductions" else default
        slip.deductions = slip_deductions
        slip.append = MagicMock(side_effect=lambda table, row: slip_deductions.append(MagicMock(**row)))
        return slip

    def _make_loan_doc(self, name="SAL-ADV-001", outstanding=5000, repayment=1000, advance_date="2025-01-01"):
        loan = MagicMock()
        loan.name = name
        loan.outstanding_balance = outstanding
        loan.repayment_amount_per_period = repayment
        loan.advance_date = advance_date
        return loan

    def test_no_active_loans_does_nothing(self):
        """No active loans -> no deduction rows appended."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services import salary_advance_service
        slip = self._make_slip()
        with patch.object(salary_advance_service, "_get_active_loans", return_value=[]):
            salary_advance_service.compute_advance_repayment_for_salary_slip(slip)
        slip.append.assert_not_called()

    def test_advance_repayment_row_appended_for_active_loan(self):
        """Active loan -> repayment deduction row is appended to the slip."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services import salary_advance_service

        loan = self._make_loan_doc(outstanding=5000, repayment=1000)
        slip = self._make_slip(gross_pay=10000, deductions=[])

        with patch.object(salary_advance_service, "_get_active_loans", return_value=[loan]), \
             patch.object(salary_advance_service, "_ensure_advance_component_exists"), \
             patch.object(salary_advance_service, "_remove_advance_rows"), \
             patch.object(salary_advance_service, "_sum_statutory_deductions", return_value=0.0), \
             patch("lhdn_payroll_integration.lhdn_payroll_integration.services.salary_advance_service.frappe") as mock_frappe:

            salary_advance_service.compute_advance_repayment_for_salary_slip(slip)

        slip.append.assert_called_once()
        call_args = slip.append.call_args[0]
        self.assertEqual(call_args[0], "deductions")
        row = call_args[1]
        self.assertEqual(row["salary_component"], salary_advance_service.ADVANCE_REPAYMENT_COMPONENT)
        self.assertAlmostEqual(row["amount"], 1000.0)

    def test_50_percent_cap_limits_advance_deduction(self):
        """When statutory deductions near 50% cap, advance deduction is capped at remaining headroom."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services import salary_advance_service

        # gross = 10000, 50% cap = 5000
        # existing statutory deductions = 4500 -> headroom = 500
        # scheduled repayment = 1000 -> actual deducted should be 500 (capped)
        loan = self._make_loan_doc(outstanding=5000, repayment=1000)
        slip = self._make_slip(gross_pay=10000, deductions=[])

        with patch.object(salary_advance_service, "_get_active_loans", return_value=[loan]), \
             patch.object(salary_advance_service, "_ensure_advance_component_exists"), \
             patch.object(salary_advance_service, "_remove_advance_rows"), \
             patch.object(salary_advance_service, "_sum_statutory_deductions", return_value=4500.0), \
             patch("lhdn_payroll_integration.lhdn_payroll_integration.services.salary_advance_service.frappe") as mock_frappe:

            salary_advance_service.compute_advance_repayment_for_salary_slip(slip)

        slip.append.assert_called_once()
        row = slip.append.call_args[0][1]
        self.assertAlmostEqual(row["amount"], 500.0)  # headroom = 5000 - 4500 = 500

    def test_cap_fully_reached_no_advance_deducted(self):
        """When statutory deductions already equal or exceed 50% cap, no advance is deducted."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services import salary_advance_service

        # gross = 10000, 50% cap = 5000, existing statutory = 5000 -> headroom = 0
        loan = self._make_loan_doc(outstanding=5000, repayment=1000)
        slip = self._make_slip(gross_pay=10000, deductions=[])

        with patch.object(salary_advance_service, "_get_active_loans", return_value=[loan]), \
             patch.object(salary_advance_service, "_ensure_advance_component_exists"), \
             patch.object(salary_advance_service, "_remove_advance_rows"), \
             patch.object(salary_advance_service, "_sum_statutory_deductions", return_value=5000.0), \
             patch("lhdn_payroll_integration.lhdn_payroll_integration.services.salary_advance_service.frappe") as mock_frappe:

            salary_advance_service.compute_advance_repayment_for_salary_slip(slip)

        slip.append.assert_not_called()

    def test_outstanding_balance_caps_deduction(self):
        """Actual deducted should not exceed outstanding balance."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services import salary_advance_service

        # outstanding = 300, scheduled = 1000, headroom = 5000 -> deduct 300 (min of three)
        loan = self._make_loan_doc(outstanding=300, repayment=1000)
        slip = self._make_slip(gross_pay=10000, deductions=[])

        with patch.object(salary_advance_service, "_get_active_loans", return_value=[loan]), \
             patch.object(salary_advance_service, "_ensure_advance_component_exists"), \
             patch.object(salary_advance_service, "_remove_advance_rows"), \
             patch.object(salary_advance_service, "_sum_statutory_deductions", return_value=0.0), \
             patch("lhdn_payroll_integration.lhdn_payroll_integration.services.salary_advance_service.frappe") as mock_frappe:

            salary_advance_service.compute_advance_repayment_for_salary_slip(slip)

        row = slip.append.call_args[0][1]
        self.assertAlmostEqual(row["amount"], 300.0)

    def test_no_employee_returns_early(self):
        """Slip with no employee should not process any loans."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services import salary_advance_service

        slip = self._make_slip(employee=None)
        with patch.object(salary_advance_service, "_get_active_loans") as mock_get:
            salary_advance_service.compute_advance_repayment_for_salary_slip(slip)
        mock_get.assert_not_called()

    def test_zero_gross_pay_returns_early(self):
        """Slip with gross_pay = 0 should not process any loans."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services import salary_advance_service

        slip = self._make_slip(gross_pay=0)
        with patch.object(salary_advance_service, "_get_active_loans") as mock_get:
            salary_advance_service.compute_advance_repayment_for_salary_slip(slip)
        mock_get.assert_not_called()

    def test_multiple_loans_processed_oldest_first(self):
        """Multiple active loans processed oldest first, headroom consumed across loans."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services import salary_advance_service

        # gross = 10000, cap = 5000, statutory = 3000, headroom = 2000
        # Loan A: repayment=1000 -> deduct 1000, headroom now 1000
        # Loan B: repayment=1500 -> deduct 1000 (capped by remaining headroom)
        loan_a = self._make_loan_doc("SAL-ADV-A", outstanding=5000, repayment=1000, advance_date="2025-01-01")
        loan_b = self._make_loan_doc("SAL-ADV-B", outstanding=5000, repayment=1500, advance_date="2025-02-01")
        slip = self._make_slip(gross_pay=10000, deductions=[])

        appended = []
        slip.append = MagicMock(side_effect=lambda tbl, row: appended.append(row))

        with patch.object(salary_advance_service, "_get_active_loans", return_value=[loan_a, loan_b]), \
             patch.object(salary_advance_service, "_ensure_advance_component_exists"), \
             patch.object(salary_advance_service, "_remove_advance_rows"), \
             patch.object(salary_advance_service, "_sum_statutory_deductions", return_value=3000.0), \
             patch("lhdn_payroll_integration.lhdn_payroll_integration.services.salary_advance_service.frappe") as mock_frappe:

            salary_advance_service.compute_advance_repayment_for_salary_slip(slip)

        self.assertEqual(len(appended), 2)
        self.assertAlmostEqual(appended[0]["amount"], 1000.0)  # Loan A full repayment
        self.assertAlmostEqual(appended[1]["amount"], 1000.0)  # Loan B capped at remaining headroom


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestSalaryAdvanceServiceHelpers(FrappeTestCase):
    """Tests for helper functions in salary_advance_service."""

    def test_sum_statutory_deductions_sums_known_components(self):
        """_sum_statutory_deductions() sums EPF/SOCSO/EIS/PCB components."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.salary_advance_service import (
            _sum_statutory_deductions,
            STATUTORY_DEDUCTION_COMPONENTS,
        )
        epf = MagicMock(); epf.salary_component = "EPF Employee"; epf.amount = 1100
        socso = MagicMock(); socso.salary_component = "SOCSO Employee"; socso.amount = 19.75
        eis = MagicMock(); eis.salary_component = "EIS Employee"; eis.amount = 11
        pcb = MagicMock(); pcb.salary_component = "Monthly Tax Deduction"; pcb.amount = 500
        other = MagicMock(); other.salary_component = "Other Deduction"; other.amount = 100

        slip = MagicMock()
        slip.get = lambda field, default=None: [epf, socso, eis, pcb, other] if field == "deductions" else default

        total = _sum_statutory_deductions(slip)
        self.assertAlmostEqual(total, 1100 + 19.75 + 11 + 500, places=2)

    def test_sum_statutory_deductions_excludes_advance_component(self):
        """_sum_statutory_deductions() does NOT include advance repayment rows."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.salary_advance_service import (
            _sum_statutory_deductions,
            ADVANCE_REPAYMENT_COMPONENT,
        )
        advance = MagicMock(); advance.salary_component = ADVANCE_REPAYMENT_COMPONENT; advance.amount = 1000

        slip = MagicMock()
        slip.get = lambda field, default=None: [advance] if field == "deductions" else default

        self.assertAlmostEqual(_sum_statutory_deductions(slip), 0.0)

    def test_remove_advance_rows_removes_correct_rows(self):
        """_remove_advance_rows() removes only advance repayment rows, keeps others."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.salary_advance_service import (
            _remove_advance_rows,
            ADVANCE_REPAYMENT_COMPONENT,
        )
        advance_row = MagicMock(); advance_row.salary_component = ADVANCE_REPAYMENT_COMPONENT
        epf_row = MagicMock(); epf_row.salary_component = "EPF Employee"

        slip = MagicMock()
        slip.deductions = [advance_row, epf_row]
        slip.get = lambda field, default=None: slip.deductions if field == "deductions" else default

        _remove_advance_rows(slip)
        self.assertEqual(len(slip.deductions), 1)
        self.assertEqual(slip.deductions[0].salary_component, "EPF Employee")

    def test_advance_repayment_component_name_constant(self):
        """ADVANCE_REPAYMENT_COMPONENT constant should be defined."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.salary_advance_service import (
            ADVANCE_REPAYMENT_COMPONENT,
        )
        self.assertIsInstance(ADVANCE_REPAYMENT_COMPONENT, str)
        self.assertTrue(len(ADVANCE_REPAYMENT_COMPONENT) > 0)

    def test_statutory_deduction_components_includes_key_types(self):
        """STATUTORY_DEDUCTION_COMPONENTS includes EPF, SOCSO, EIS, MTD."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.salary_advance_service import (
            STATUTORY_DEDUCTION_COMPONENTS,
        )
        self.assertIn("EPF Employee", STATUTORY_DEDUCTION_COMPONENTS)
        self.assertIn("SOCSO Employee", STATUTORY_DEDUCTION_COMPONENTS)
        self.assertIn("EIS Employee", STATUTORY_DEDUCTION_COMPONENTS)
        self.assertIn("Monthly Tax Deduction", STATUTORY_DEDUCTION_COMPONENTS)


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------

class TestActiveSalaryAdvancesReport(FrappeTestCase):
    """Tests for Active Salary Advances script report."""

    def test_report_importable(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.active_salary_advances.active_salary_advances import execute
        self.assertTrue(callable(execute))

    def test_report_columns_structure(self):
        """Report should return columns list with required fields."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.active_salary_advances.active_salary_advances import execute

        with patch("lhdn_payroll_integration.lhdn_payroll_integration.report.active_salary_advances.active_salary_advances.frappe") as mock_frappe:
            mock_frappe.get_all.return_value = []
            columns, data = execute({})

        fieldnames = [c["fieldname"] for c in columns]
        self.assertIn("employee", fieldnames)
        self.assertIn("outstanding_balance", fieldnames)
        self.assertIn("repayment_amount_per_period", fieldnames)
        self.assertIn("projected_clearance_date", fieldnames)
        self.assertIn("status", fieldnames)

    def test_report_returns_active_loans_by_default(self):
        """Report filters on status='Active' when no status filter provided."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.active_salary_advances.active_salary_advances import execute

        with patch("lhdn_payroll_integration.lhdn_payroll_integration.report.active_salary_advances.active_salary_advances.frappe") as mock_frappe:
            mock_frappe.get_all.return_value = [{"name": "SAL-ADV-001", "status": "Active"}]
            columns, data = execute({})

        call_kwargs = mock_frappe.get_all.call_args[1]
        self.assertEqual(call_kwargs["filters"].get("status"), "Active")

    def test_report_data_matches_frappe_records(self):
        """Report data rows come directly from frappe.get_all result."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.active_salary_advances.active_salary_advances import execute

        records = [
            {"name": "SAL-ADV-001", "employee": "EMP-001", "outstanding_balance": 4000},
        ]
        with patch("lhdn_payroll_integration.lhdn_payroll_integration.report.active_salary_advances.active_salary_advances.frappe") as mock_frappe:
            mock_frappe.get_all.return_value = records
            columns, data = execute({})

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["employee"], "EMP-001")
