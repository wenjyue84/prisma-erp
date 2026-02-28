"""Tests for US-077: TP3 Carry-Forward Declaration for New Hires.

Verifies:
- get_tp3_for_employee() returns correct prior income and PCB data
- calculate_pcb_method2() uses combined YTD when tp3_prior_gross/pcb provided
- Employee joining July with RM30,000 prior income — annualised income uses combined figure
- CP22 workflow triggers TP3 reminder when joining month is not January
- CP22 workflow does NOT trigger reminder when joining month is January
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.services.tp3_service import (
    get_tp3_for_employee,
    requires_tp3_collection,
)
from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb_method2
from lhdn_payroll_integration.services.cp22_service import handle_employee_after_insert


class TestGetTP3ForEmployee(FrappeTestCase):
    """Tests for get_tp3_for_employee() service function."""

    @patch("lhdn_payroll_integration.services.tp3_service.frappe")
    def test_returns_prior_data_when_record_exists(self, mock_frappe):
        """get_tp3_for_employee should return prior_gross and prior_pcb from TP3 record."""
        mock_frappe.db.get_value.return_value = {
            "prior_gross_income": 30000.0,
            "prior_pcb_deducted": 1500.0,
            "prior_epf_deducted": 1800.0,
            "joining_month": 7,
        }

        result = get_tp3_for_employee("HR-EMP-001", 2024)

        self.assertEqual(result["prior_gross"], 30000.0)
        self.assertEqual(result["prior_pcb"], 1500.0)
        self.assertEqual(result["prior_epf"], 1800.0)
        self.assertEqual(result["joining_month"], 7)

    @patch("lhdn_payroll_integration.services.tp3_service.frappe")
    def test_returns_zeros_when_no_record(self, mock_frappe):
        """get_tp3_for_employee should return zeros when no TP3 record found."""
        mock_frappe.db.get_value.return_value = None

        result = get_tp3_for_employee("HR-EMP-002", 2024)

        self.assertEqual(result["prior_gross"], 0.0)
        self.assertEqual(result["prior_pcb"], 0.0)
        self.assertEqual(result["prior_epf"], 0.0)
        self.assertIsNone(result["joining_month"])

    @patch("lhdn_payroll_integration.services.tp3_service.frappe")
    def test_handles_none_values_gracefully(self, mock_frappe):
        """get_tp3_for_employee should coerce None fields to 0.0."""
        mock_frappe.db.get_value.return_value = {
            "prior_gross_income": None,
            "prior_pcb_deducted": None,
            "prior_epf_deducted": None,
            "joining_month": 3,
        }

        result = get_tp3_for_employee("HR-EMP-003", 2024)

        self.assertEqual(result["prior_gross"], 0.0)
        self.assertEqual(result["prior_pcb"], 0.0)
        self.assertEqual(result["prior_epf"], 0.0)

    @patch("lhdn_payroll_integration.services.tp3_service.frappe")
    def test_queries_correct_employee_and_year(self, mock_frappe):
        """get_tp3_for_employee should query by employee and tax_year."""
        mock_frappe.db.get_value.return_value = None

        get_tp3_for_employee("HR-EMP-004", 2025)

        mock_frappe.db.get_value.assert_called_once_with(
            "Employee TP3 Declaration",
            {"employee": "HR-EMP-004", "tax_year": 2025},
            ["prior_gross_income", "prior_pcb_deducted", "prior_epf_deducted", "joining_month"],
            as_dict=True,
        )


class TestCalculatePCBMethod2WithTP3(FrappeTestCase):
    """Tests for calculate_pcb_method2() with TP3 prior employer data."""

    def test_tp3_prior_gross_added_to_ytd_for_annualisation(self):
        """Employee joining July with RM30,000 prior income — annualised income uses combined figure.

        Scenario: Employee joined in July (month 7). Current employer paid RM5,000/month.
        YTD from current employer = RM5,000 (July only).
        Prior employer gross = RM30,000 (Jan–Jun).
        Combined YTD = RM35,000. Annualised = 35,000 * 12 / 7 = RM60,000.

        Without TP3: annualised = 5,000 * 12 / 7 ≈ RM8,571 (severely understated).
        With TP3: annualised = 35,000 * 12 / 7 = RM60,000 (correct combined figure).
        """
        # With TP3: combined annualised = 35,000 * 12 / 7 = 60,000
        pcb_with_tp3 = calculate_pcb_method2(
            ytd_gross=5000.0,
            ytd_pcb_deducted=0.0,
            month_number=7,
            tp3_prior_gross=30000.0,
            tp3_prior_pcb=1500.0,
        )

        # Without TP3: annualised = 5,000 * 12 / 7 ≈ 8,571
        pcb_without_tp3 = calculate_pcb_method2(
            ytd_gross=5000.0,
            ytd_pcb_deducted=0.0,
            month_number=7,
        )

        # PCB with TP3 should be significantly higher (combined income is much larger)
        self.assertGreater(pcb_with_tp3, pcb_without_tp3)

    def test_tp3_prior_pcb_offset_against_annual_tax(self):
        """Prior PCB deducted by previous employer reduces current employer's obligation.

        An employee who has already paid PCB to a prior employer should have that
        amount offset so the total annual PCB is not double-charged.
        """
        # With prior PCB already paid — obligation is reduced
        pcb_with_prior = calculate_pcb_method2(
            ytd_gross=5000.0,
            ytd_pcb_deducted=0.0,
            month_number=7,
            tp3_prior_gross=30000.0,
            tp3_prior_pcb=2000.0,  # prior employer already deducted 2000
        )

        # Without prior PCB offset — full obligation falls on current employer
        pcb_without_prior = calculate_pcb_method2(
            ytd_gross=5000.0,
            ytd_pcb_deducted=0.0,
            month_number=7,
            tp3_prior_gross=30000.0,
            tp3_prior_pcb=0.0,
        )

        # When prior PCB is accounted for, current employer deducts less
        self.assertLessEqual(pcb_with_prior, pcb_without_prior)

    def test_zero_tp3_values_produce_same_result_as_no_tp3(self):
        """calculate_pcb_method2 with tp3=0 should produce same result as without tp3 params."""
        pcb_no_tp3 = calculate_pcb_method2(
            ytd_gross=10000.0,
            ytd_pcb_deducted=500.0,
            month_number=5,
        )
        pcb_zero_tp3 = calculate_pcb_method2(
            ytd_gross=10000.0,
            ytd_pcb_deducted=500.0,
            month_number=5,
            tp3_prior_gross=0.0,
            tp3_prior_pcb=0.0,
        )
        self.assertEqual(pcb_no_tp3, pcb_zero_tp3)

    def test_tp3_annualised_income_calculation(self):
        """Verify the exact annualised income with TP3 data.

        Employee joins July (month 7):
        - Current employer YTD gross: RM5,000
        - Prior employer gross (TP3): RM30,000
        - Combined YTD: RM35,000
        - Annualised: 35,000 * 12 / 7 = RM60,000
        - Chargeable: 60,000 - 9,000 (self relief) = RM51,000
        - Tax on RM51,000: 1,800 + (51,000 - 50,000) * 13% = RM1,930
        - Remaining months: 13 - 7 = 6
        - Prior PCB from TP3: RM1,500
        - PCB this month: max(0, (1,930 - 1,500) / 6) = 430/6 ≈ RM71.67
        """
        pcb = calculate_pcb_method2(
            ytd_gross=5000.0,
            ytd_pcb_deducted=0.0,
            month_number=7,
            tp3_prior_gross=30000.0,
            tp3_prior_pcb=1500.0,
        )
        # Expected: (1,930 - 1,500) / 6 = 71.67
        self.assertAlmostEqual(pcb, 71.67, places=1)

    def test_non_resident_with_tp3(self):
        """Non-resident employee: TP3 prior gross and prior PCB both applied correctly."""
        pcb_with_tp3 = calculate_pcb_method2(
            ytd_gross=5000.0,
            ytd_pcb_deducted=0.0,
            month_number=7,
            resident=False,
            tp3_prior_gross=30000.0,
            tp3_prior_pcb=9000.0,
        )
        # Non-resident: 30% flat on annualised combined
        # annualised = 35,000 * 12 / 7 = 60,000
        # annual_tax = 60,000 * 0.30 = 18,000
        # remaining = 6
        # pcb = (18,000 - 9,000) / 6 = 1,500
        self.assertAlmostEqual(pcb_with_tp3, 1500.0, places=2)


class TestRequiresTP3Collection(FrappeTestCase):
    """Tests for requires_tp3_collection() helper."""

    @patch("lhdn_payroll_integration.services.tp3_service.frappe")
    def test_mid_year_joiner_requires_tp3(self, mock_frappe):
        """Employee joining in month > 1 requires TP3 collection."""
        mock_frappe.db.get_value.return_value = {
            "prior_gross_income": 30000.0,
            "prior_pcb_deducted": 1500.0,
            "prior_epf_deducted": 1800.0,
            "joining_month": 7,
        }

        result = requires_tp3_collection("HR-EMP-005", 2024)
        self.assertTrue(result)

    @patch("lhdn_payroll_integration.services.tp3_service.frappe")
    def test_january_joiner_does_not_require_tp3(self, mock_frappe):
        """Employee joining in January (month 1) does not require TP3 collection."""
        mock_frappe.db.get_value.return_value = {
            "prior_gross_income": 0.0,
            "prior_pcb_deducted": 0.0,
            "prior_epf_deducted": 0.0,
            "joining_month": 1,
        }

        result = requires_tp3_collection("HR-EMP-006", 2024)
        self.assertFalse(result)


class TestCP22TP3Reminder(FrappeTestCase):
    """Tests for TP3 reminder triggered via CP22 workflow."""

    def _make_employee_mock(self, requires_self_billed=1, date_of_joining=None, employee_name="Test"):
        mock = MagicMock()
        mock.name = "HR-EMP-99901"
        mock.employee_name = employee_name
        mock.custom_requires_self_billed_invoice = requires_self_billed
        mock.date_of_joining = date_of_joining or "2024-07-01"
        mock.date_of_birth = "1990-01-01"
        mock.get = lambda field, default=None: getattr(mock, field, default)
        return mock

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_tp3_reminder_shown_when_joining_month_not_january(self, mock_frappe):
        """CP22 workflow triggers TP3 reminder when joining month is not January."""
        mock_frappe.db.exists.return_value = False
        mock_cp22 = MagicMock()
        mock_cp22.name = "CP22-2024-00001"
        mock_cp22.filing_deadline = "2024-07-31"
        mock_frappe.new_doc.return_value = mock_cp22

        emp = self._make_employee_mock(date_of_joining="2024-07-01")
        handle_employee_after_insert(emp, "after_insert")

        # frappe.msgprint called at least twice: once for CP22, once for TP3
        self.assertGreaterEqual(mock_frappe.msgprint.call_count, 2)
        # Verify TP3 message was included
        call_args_list = mock_frappe.msgprint.call_args_list
        tp3_calls = [c for c in call_args_list if "TP3" in str(c) or "tp3" in str(c).lower() or "Borang" in str(c)]
        self.assertTrue(len(tp3_calls) > 0, "TP3 reminder message not found in msgprint calls")

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_tp3_reminder_not_shown_for_january_joiner(self, mock_frappe):
        """CP22 workflow does NOT trigger TP3 reminder when joining month is January."""
        mock_frappe.db.exists.return_value = False
        mock_cp22 = MagicMock()
        mock_cp22.name = "CP22-2024-00001"
        mock_cp22.filing_deadline = "2024-01-31"
        mock_frappe.new_doc.return_value = mock_cp22

        emp = self._make_employee_mock(date_of_joining="2024-01-15")
        handle_employee_after_insert(emp, "after_insert")

        # Only the CP22 creation message — no TP3 reminder
        self.assertEqual(mock_frappe.msgprint.call_count, 1)
        call_args_list = mock_frappe.msgprint.call_args_list
        tp3_calls = [c for c in call_args_list if "TP3" in str(c) or "Borang" in str(c)]
        self.assertEqual(len(tp3_calls), 0, "TP3 reminder should NOT be shown for January joiner")

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_tp3_reminder_not_shown_when_flag_not_set(self, mock_frappe):
        """TP3 reminder is not shown when CP22 is not created (flag not set)."""
        emp = self._make_employee_mock(requires_self_billed=0, date_of_joining="2024-07-01")
        handle_employee_after_insert(emp, "after_insert")

        # No msgprint at all (including TP3)
        mock_frappe.msgprint.assert_not_called()
