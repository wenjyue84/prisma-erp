"""Tests for EPF Akaun Fleksibel Three-Account Contribution Split (US-154).

Acceptance Criteria verified:
1. Three-account split: Akaun Persaraan 75%, Akaun Sejahtera 15%, Akaun Fleksibel 10%
2. Employee EPF (11% or 9%) and employer EPF (12% or 13%) both split correctly
3. Above-55 legacy employees get two-account split (70% / 30%)
4. Unit test: RM1,000 EPF splits as RM750 / RM150 / RM100
5. Rounding: totals never exceed original amount; fleksibel absorbs rounding remainder
"""

from datetime import date
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_account_split_service import (
    AKAUN_PERSARAAN_RATE,
    AKAUN_SEJAHTERA_RATE,
    AKAUN_FLEKSIBEL_RATE,
    AKAUN_1_LEGACY_RATE,
    AKAUN_2_LEGACY_RATE,
    EPF_THREE_ACCOUNT_START,
    compute_epf_account_split,
    get_epf_split_for_salary_slip,
    is_three_account_applicable,
)

PAYROLL_DATE_POST = date(2025, 1, 31)   # After 11 May 2024 — three-account applies
PAYROLL_DATE_PRE = date(2024, 1, 31)    # Before 11 May 2024 — legacy two-account


class TestEPFThreeAccountConstants(FrappeTestCase):
    """Verify that the rate constants match KWSP policy."""

    def test_three_account_start_date(self):
        self.assertEqual(EPF_THREE_ACCOUNT_START, date(2024, 5, 11))

    def test_rates_sum_to_one(self):
        total = AKAUN_PERSARAAN_RATE + AKAUN_SEJAHTERA_RATE + AKAUN_FLEKSIBEL_RATE
        self.assertAlmostEqual(total, 1.0, places=10)

    def test_persaraan_rate_is_75pct(self):
        self.assertAlmostEqual(AKAUN_PERSARAAN_RATE, 0.75, places=10)

    def test_sejahtera_rate_is_15pct(self):
        self.assertAlmostEqual(AKAUN_SEJAHTERA_RATE, 0.15, places=10)

    def test_fleksibel_rate_is_10pct(self):
        self.assertAlmostEqual(AKAUN_FLEKSIBEL_RATE, 0.10, places=10)

    def test_legacy_rates_sum_to_one(self):
        total = AKAUN_1_LEGACY_RATE + AKAUN_2_LEGACY_RATE
        self.assertAlmostEqual(total, 1.0, places=10)


class TestIsThreeAccountApplicable(FrappeTestCase):
    """Test applicability check by payroll date."""

    def test_before_11_may_2024_returns_false(self):
        self.assertFalse(is_three_account_applicable(date(2024, 5, 10)))

    def test_on_11_may_2024_returns_true(self):
        self.assertTrue(is_three_account_applicable(date(2024, 5, 11)))

    def test_after_11_may_2024_returns_true(self):
        self.assertTrue(is_three_account_applicable(date(2025, 3, 1)))

    def test_string_date_accepted(self):
        self.assertTrue(is_three_account_applicable("2025-01-31"))

    def test_none_defaults_to_today(self):
        # Today is after 11 May 2024, so should be True
        result = is_three_account_applicable(None)
        self.assertTrue(result)


class TestComputeEPFAccountSplit_ThreeAccount(FrappeTestCase):
    """Test the three-account split computation (post 11 May 2024)."""

    def test_rm1000_splits_as_750_150_100(self):
        """Acceptance criteria: RM1,000 splits as RM750 / RM150 / RM100."""
        result = compute_epf_account_split(1000.0, employee_doc=None, payroll_date=PAYROLL_DATE_POST)
        self.assertFalse(result["use_legacy"])
        accounts = result["accounts"]
        self.assertEqual(len(accounts), 3)

        amounts = {acc["name"]: acc["amount"] for acc in accounts}
        self.assertEqual(amounts["Akaun Persaraan (Retirement)"], 750.0)
        self.assertEqual(amounts["Akaun Sejahtera (Well-being)"], 150.0)
        self.assertEqual(amounts["Akaun Fleksibel (Flexible)"], 100.0)

    def test_total_does_not_exceed_input(self):
        for amount in [1000.0, 550.0, 333.33, 0.01, 99.99]:
            result = compute_epf_account_split(amount, payroll_date=PAYROLL_DATE_POST)
            total = sum(acc["amount"] for acc in result["accounts"])
            self.assertAlmostEqual(total, amount, places=2,
                                   msg=f"Total mismatch for input {amount}")

    def test_zero_epf_returns_zero_splits(self):
        result = compute_epf_account_split(0.0, payroll_date=PAYROLL_DATE_POST)
        for acc in result["accounts"]:
            self.assertEqual(acc["amount"], 0.0)

    def test_three_accounts_returned(self):
        result = compute_epf_account_split(500.0, payroll_date=PAYROLL_DATE_POST)
        self.assertEqual(len(result["accounts"]), 3)

    def test_account_names_present(self):
        result = compute_epf_account_split(500.0, payroll_date=PAYROLL_DATE_POST)
        names = [acc["name"] for acc in result["accounts"]]
        self.assertIn("Akaun Persaraan (Retirement)", names)
        self.assertIn("Akaun Sejahtera (Well-being)", names)
        self.assertIn("Akaun Fleksibel (Flexible)", names)

    def test_rates_match_kwsp_policy(self):
        result = compute_epf_account_split(1000.0, payroll_date=PAYROLL_DATE_POST)
        rates = {acc["name"]: acc["rate"] for acc in result["accounts"]}
        self.assertAlmostEqual(rates["Akaun Persaraan (Retirement)"], 0.75)
        self.assertAlmostEqual(rates["Akaun Sejahtera (Well-being)"], 0.15)
        self.assertAlmostEqual(rates["Akaun Fleksibel (Flexible)"], 0.10)

    def test_employer_contribution_13pct_split(self):
        """Employer EPF at 13% of RM5000 = RM650 splits correctly."""
        employer_epf = 650.0
        result = compute_epf_account_split(employer_epf, payroll_date=PAYROLL_DATE_POST)
        accounts = {acc["name"]: acc["amount"] for acc in result["accounts"]}
        # RM650 * 75% = RM487.50, * 15% = RM97.50, * 10% = RM65
        self.assertAlmostEqual(accounts["Akaun Persaraan (Retirement)"], 487.50, places=2)
        self.assertAlmostEqual(accounts["Akaun Sejahtera (Well-being)"], 97.50, places=2)
        self.assertAlmostEqual(accounts["Akaun Fleksibel (Flexible)"], 65.0, places=2)


class TestComputeEPFAccountSplit_LegacyPreDate(FrappeTestCase):
    """Test that payroll dates before 11 May 2024 use legacy two-account split."""

    def test_pre_date_returns_legacy(self):
        result = compute_epf_account_split(1000.0, payroll_date=PAYROLL_DATE_PRE)
        self.assertTrue(result["use_legacy"])
        self.assertEqual(len(result["accounts"]), 2)

    def test_pre_date_legacy_amounts(self):
        result = compute_epf_account_split(1000.0, payroll_date=PAYROLL_DATE_PRE)
        amounts = {acc["name"]: acc["amount"] for acc in result["accounts"]}
        self.assertEqual(amounts["Akaun 1 (Persaraan)"], 700.0)
        self.assertEqual(amounts["Akaun 2 (Kesejahteraan)"], 300.0)


class TestComputeEPFAccountSplit_Above55Legacy(FrappeTestCase):
    """Test that above-55 employees with custom_epf_three_account=0 use legacy split."""

    def _make_employee(self, dob, three_account_flag=None):
        emp = MagicMock()
        emp.date_of_birth = dob
        emp.custom_epf_three_account = three_account_flag
        return emp

    def test_above55_with_flag_false_uses_legacy(self):
        """Employee aged 58, custom_epf_three_account=0 → legacy split."""
        dob = date(1967, 1, 1)  # ~58 years old in 2025
        emp = self._make_employee(dob, three_account_flag=0)
        result = compute_epf_account_split(1000.0, employee_doc=emp, payroll_date=PAYROLL_DATE_POST)
        self.assertTrue(result["use_legacy"])

    def test_above55_with_flag_true_uses_three_account(self):
        """Employee aged 58 but enrolled in three-account → three-account split."""
        dob = date(1967, 1, 1)
        emp = self._make_employee(dob, three_account_flag=1)
        result = compute_epf_account_split(1000.0, employee_doc=emp, payroll_date=PAYROLL_DATE_POST)
        self.assertFalse(result["use_legacy"])

    def test_below55_never_uses_legacy(self):
        """Employee aged 35 → always three-account after 11 May 2024."""
        dob = date(1990, 6, 15)
        emp = self._make_employee(dob, three_account_flag=0)
        result = compute_epf_account_split(1000.0, employee_doc=emp, payroll_date=PAYROLL_DATE_POST)
        self.assertFalse(result["use_legacy"])

    def test_none_employee_uses_three_account(self):
        """No employee doc → defaults to three-account (post 11 May 2024)."""
        result = compute_epf_account_split(1000.0, employee_doc=None, payroll_date=PAYROLL_DATE_POST)
        self.assertFalse(result["use_legacy"])


class TestGetEPFSplitForSalarySlip(FrappeTestCase):
    """Test the salary slip integration helper."""

    def _make_slip(self, employee_epf=1000.0, employer_epf=1300.0):
        """Create a mock Salary Slip with EPF components."""
        slip = MagicMock()
        slip.employee = "EMP-TEST-001"
        slip.end_date = "2025-01-31"
        slip.posting_date = "2025-01-31"

        # Employee EPF in deductions
        deduction_row = MagicMock()
        deduction_row.salary_component = "EPF Employee"
        deduction_row.amount = employee_epf

        # Employer EPF in earnings (as non-deductible)
        earning_row = MagicMock()
        earning_row.salary_component = "EPF Employer"
        earning_row.amount = employer_epf

        slip.get = lambda key, default=None: (
            [deduction_row] if key == "deductions" else
            [earning_row] if key == "earnings" else
            default
        )
        return slip

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_account_split_service.frappe")
    def test_employee_epf_extracted_correctly(self, mock_frappe):
        mock_frappe.get_doc.return_value = MagicMock(
            date_of_birth=None,
            custom_epf_three_account=None,
        )
        slip = self._make_slip(employee_epf=1000.0, employer_epf=0.0)
        result = get_epf_split_for_salary_slip(slip)
        self.assertAlmostEqual(result["employee_epf_total"], 1000.0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_account_split_service.frappe")
    def test_employer_epf_extracted_correctly(self, mock_frappe):
        mock_frappe.get_doc.return_value = MagicMock(
            date_of_birth=None,
            custom_epf_three_account=None,
        )
        slip = self._make_slip(employee_epf=0.0, employer_epf=1300.0)
        result = get_epf_split_for_salary_slip(slip)
        self.assertAlmostEqual(result["employer_epf_total"], 1300.0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_account_split_service.frappe")
    def test_split_returned_for_employee_epf(self, mock_frappe):
        mock_frappe.get_doc.return_value = MagicMock(
            date_of_birth=None,
            custom_epf_three_account=None,
        )
        slip = self._make_slip(employee_epf=1000.0, employer_epf=0.0)
        result = get_epf_split_for_salary_slip(slip)
        emp_split = result["employee_split"]
        self.assertFalse(emp_split["use_legacy"])
        amounts = {acc["name"]: acc["amount"] for acc in emp_split["accounts"]}
        self.assertEqual(amounts["Akaun Persaraan (Retirement)"], 750.0)
        self.assertEqual(amounts["Akaun Sejahtera (Well-being)"], 150.0)
        self.assertEqual(amounts["Akaun Fleksibel (Flexible)"], 100.0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_account_split_service.frappe")
    def test_use_legacy_false_for_standard_employee(self, mock_frappe):
        mock_frappe.get_doc.return_value = MagicMock(
            date_of_birth=None,
            custom_epf_three_account=None,
        )
        slip = self._make_slip()
        result = get_epf_split_for_salary_slip(slip)
        self.assertFalse(result["use_legacy"])


class TestPayslipHTMLContainsEPFSplit(FrappeTestCase):
    """Verify the EA S61 payslip HTML template references EPF account split fields."""

    def _html(self):
        import os
        html_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "print_format",
            "ea_s61_payslip",
            "ea_s61_payslip.html",
        )
        self.assertTrue(os.path.exists(html_path), f"HTML not found: {html_path}")
        with open(html_path, encoding="utf-8") as f:
            return f.read()

    def test_html_references_akaun_persaraan(self):
        html = self._html()
        self.assertIn("Persaraan", html, "Payslip HTML must reference Akaun Persaraan")

    def test_html_references_akaun_sejahtera(self):
        html = self._html()
        self.assertIn("Sejahtera", html, "Payslip HTML must reference Akaun Sejahtera")

    def test_html_references_akaun_fleksibel(self):
        html = self._html()
        self.assertIn("Fleksibel", html, "Payslip HTML must reference Akaun Fleksibel")

    def test_html_references_epf_split_service(self):
        html = self._html()
        self.assertIn("epf_account_split", html,
                      "Payslip HTML must call epf_account_split_service")
