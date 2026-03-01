"""Tests for US-310: PERKESO LINDUNG 24/7 Employee Second-Category Contribution Deduction Engine.

The Employees' Social Security (Amendment) Bill 2025 (passed 2 December 2025) introduces
the LINDUNG 24/7 Non-Occupational Accident Scheme, requiring BOTH employers AND employees
to contribute to Second Category. Contribution rates are pending gazette (expected Q1/Q2 2026).

Test coverage:
  - Module constants (field names, labels, warning text)
  - is_lindung_gazette_active() activation date guard
  - get_pre_gazette_warning() compliance warning message
  - is_pending_gazette() gazette status check
  - compute_lindung_employee_contribution() pre- and post-gazette
  - compute_lindung_employer_contribution() pre- and post-gazette
  - get_gazette_alert_message() HR Manager alert content
  - get_perkeso_assist_lindung_amounts() PERKESO ASSIST e-Caruman integration
"""
from unittest.mock import patch, MagicMock
from frappe.tests.utils import FrappeTestCase


class TestLindungConstants(FrappeTestCase):
    """Module-level constants match LINDUNG 24/7 specification."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service import (
            LINDUNG_PENDING_GAZETTE_FIELD,
            LINDUNG_EMPLOYEE_RATE_FIELD,
            LINDUNG_EMPLOYER_RATE_FIELD,
            LINDUNG_ACTIVATION_DATE_FIELD,
            LINDUNG_EMPLOYEE_DEDUCTION_LABEL,
            LINDUNG_EMPLOYER_COST_LABEL,
            PRE_GAZETTE_WARNING,
            PERKESO_ASSIST_COLUMN,
            PERKESO_ASSIST_EMPLOYER_COLUMN,
        )
        self.pending_field = LINDUNG_PENDING_GAZETTE_FIELD
        self.ee_rate_field = LINDUNG_EMPLOYEE_RATE_FIELD
        self.er_rate_field = LINDUNG_EMPLOYER_RATE_FIELD
        self.activation_field = LINDUNG_ACTIVATION_DATE_FIELD
        self.ee_label = LINDUNG_EMPLOYEE_DEDUCTION_LABEL
        self.er_label = LINDUNG_EMPLOYER_COST_LABEL
        self.warning = PRE_GAZETTE_WARNING
        self.perkeso_col = PERKESO_ASSIST_COLUMN
        self.perkeso_er_col = PERKESO_ASSIST_EMPLOYER_COLUMN

    def test_pending_gazette_field_name(self):
        self.assertEqual(self.pending_field, "lindung_24_7_pending_gazette")

    def test_employee_rate_field_name(self):
        self.assertEqual(self.ee_rate_field, "lindung_24_7_employee_rate")

    def test_employer_rate_field_name(self):
        self.assertEqual(self.er_rate_field, "lindung_24_7_employer_rate")

    def test_activation_date_field_name(self):
        self.assertEqual(self.activation_field, "lindung_24_7_activation_date")

    def test_employee_deduction_label_contains_lindung(self):
        self.assertIn("LINDUNG 24/7", self.ee_label)

    def test_employee_deduction_label_contains_employee(self):
        self.assertIn("Employee", self.ee_label)

    def test_employer_cost_label_contains_lindung(self):
        self.assertIn("LINDUNG 24/7", self.er_label)

    def test_pre_gazette_warning_not_empty(self):
        self.assertIsInstance(self.warning, str)
        self.assertGreater(len(self.warning), 0)

    def test_pre_gazette_warning_mentions_not_gazetted(self):
        self.assertIn("not yet gazetted", self.warning.lower())

    def test_pre_gazette_warning_mentions_deduction_not_applied(self):
        self.assertIn("not applied", self.warning.lower())

    def test_perkeso_assist_column_contains_lindung(self):
        self.assertIn("LINDUNG", self.perkeso_col)

    def test_perkeso_assist_employer_column_contains_lindung(self):
        self.assertIn("LINDUNG", self.perkeso_er_col)


class TestGazetteActiveCheck(FrappeTestCase):
    """is_lindung_gazette_active() gazette activation date guard."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service import (
            is_lindung_gazette_active,
        )
        self.is_active = is_lindung_gazette_active

    def _make_settings(self, pending=1, employee_rate=0.0, activation_date=None):
        mock_settings = MagicMock()
        def get_val(key, default=None):
            return {
                "lindung_24_7_pending_gazette": pending,
                "lindung_24_7_employee_rate": employee_rate,
                "lindung_24_7_activation_date": activation_date,
            }.get(key, default)
        mock_settings.get = get_val
        return mock_settings

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_false_when_pending_gazette_true(self, mock_frappe):
        """Gazette flag set → deductions dormant regardless of rate and date."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=1, employee_rate=0.005, activation_date="2026-06-01"
        )
        self.assertFalse(self.is_active("2026-07-01"))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_false_when_rate_is_zero(self, mock_frappe):
        """Gazette cleared but no rate entered → deductions dormant."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, employee_rate=0.0, activation_date="2026-06-01"
        )
        self.assertFalse(self.is_active("2026-07-01"))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_false_when_activation_date_not_set(self, mock_frappe):
        """Rate entered but no activation date → deductions dormant."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, employee_rate=0.005, activation_date=None
        )
        self.assertFalse(self.is_active("2026-07-01"))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_false_before_activation_date(self, mock_frappe):
        """Payroll date before activation date → deductions dormant."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, employee_rate=0.005, activation_date="2026-07-01"
        )
        self.assertFalse(self.is_active("2026-06-30"))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_true_on_activation_date(self, mock_frappe):
        """Payroll date exactly on activation date → deductions active."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, employee_rate=0.005, activation_date="2026-07-01"
        )
        self.assertTrue(self.is_active("2026-07-01"))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_true_after_activation_date(self, mock_frappe):
        """Payroll date after activation date → deductions active."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, employee_rate=0.005, activation_date="2026-07-01"
        )
        self.assertTrue(self.is_active("2026-08-15"))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_false_when_settings_raises_exception(self, mock_frappe):
        """Settings unavailable → safe default is dormant (False)."""
        mock_frappe.get_single.side_effect = Exception("Settings not found")
        self.assertFalse(self.is_active("2026-07-01"))


class TestPreGazetteWarning(FrappeTestCase):
    """get_pre_gazette_warning() returns the correct compliance warning."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service import (
            get_pre_gazette_warning,
        )
        self.get_warning = get_pre_gazette_warning

    def test_returns_non_empty_string(self):
        warning = self.get_warning()
        self.assertIsInstance(warning, str)
        self.assertGreater(len(warning), 0)

    def test_warning_mentions_lindung(self):
        warning = self.get_warning()
        self.assertIn("LINDUNG", warning)

    def test_warning_mentions_not_gazetted(self):
        warning = self.get_warning()
        self.assertIn("not yet gazetted", warning.lower())

    def test_warning_mentions_deduction_not_applied(self):
        warning = self.get_warning()
        self.assertIn("not applied", warning.lower())


class TestIsPendingGazette(FrappeTestCase):
    """is_pending_gazette() gazette status helper."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service import (
            is_pending_gazette,
        )
        self.check = is_pending_gazette

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_true_when_pending_flag_set(self, mock_frappe):
        mock_settings = MagicMock()
        mock_settings.get.return_value = 1
        mock_frappe.get_single.return_value = mock_settings
        self.assertTrue(self.check())

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_false_when_gazette_published(self, mock_frappe):
        mock_settings = MagicMock()
        mock_settings.get.return_value = 0
        mock_frappe.get_single.return_value = mock_settings
        self.assertFalse(self.check())

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_true_on_exception(self, mock_frappe):
        """If settings unavailable, default to pending (safe)."""
        mock_frappe.get_single.side_effect = Exception("Settings unavailable")
        self.assertTrue(self.check())


class TestComputeEmployeeContribution(FrappeTestCase):
    """compute_lindung_employee_contribution() accuracy and gazette guard."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service import (
            compute_lindung_employee_contribution,
        )
        self.compute = compute_lindung_employee_contribution

    def _make_settings(self, pending=0, ee_rate=0.005, er_rate=0.005, activation_date="2026-01-01"):
        mock_settings = MagicMock()
        def get_val(key, default=None):
            return {
                "lindung_24_7_pending_gazette": pending,
                "lindung_24_7_employee_rate": ee_rate,
                "lindung_24_7_employer_rate": er_rate,
                "lindung_24_7_activation_date": activation_date,
            }.get(key, default)
        mock_settings.get = get_val
        return mock_settings

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_dict_with_required_keys(self, mock_frappe):
        mock_frappe.get_single.return_value = self._make_settings(pending=1)
        result = self.compute(3000.0, "2026-07-01")
        for key in ("amount", "rate", "active", "warning", "label"):
            self.assertIn(key, result, f"Missing key: {key}")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_zero_when_gazette_pending(self, mock_frappe):
        """Acceptance criterion: pre-gazette payroll runs → zero deduction."""
        mock_frappe.get_single.return_value = self._make_settings(pending=1)
        result = self.compute(3000.0, "2026-07-01")
        self.assertAlmostEqual(result["amount"], 0.00, places=2)
        self.assertFalse(result["active"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_warning_present_when_gazette_pending(self, mock_frappe):
        """Acceptance criterion: pre-gazette payroll displays compliance warning."""
        mock_frappe.get_single.return_value = self._make_settings(pending=1)
        result = self.compute(3000.0, "2026-07-01")
        self.assertGreater(len(result["warning"]), 0)
        self.assertIn("not yet gazetted", result["warning"].lower())

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_computes_correct_amount_when_active(self, mock_frappe):
        """RM3,000 gross × 0.5% rate = RM15.00 employee deduction."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, ee_rate=0.005, activation_date="2026-01-01"
        )
        result = self.compute(3000.0, "2026-07-01")
        self.assertAlmostEqual(result["amount"], 15.00, places=2)
        self.assertTrue(result["active"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_computes_5000_at_half_percent(self, mock_frappe):
        """RM5,000 × 0.5% = RM25.00."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, ee_rate=0.005, activation_date="2026-01-01"
        )
        result = self.compute(5000.0, "2026-07-01")
        self.assertAlmostEqual(result["amount"], 25.00, places=2)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_computes_1000_at_point_3_percent(self, mock_frappe):
        """RM1,000 × 0.3% = RM3.00."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, ee_rate=0.003, activation_date="2026-01-01"
        )
        result = self.compute(1000.0, "2026-07-01")
        self.assertAlmostEqual(result["amount"], 3.00, places=2)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_empty_warning_when_active(self, mock_frappe):
        """Active gazette → no pre-gazette warning."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, ee_rate=0.005, activation_date="2026-01-01"
        )
        result = self.compute(3000.0, "2026-07-01")
        self.assertEqual(result["warning"], "")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_label_is_lindung_employee(self, mock_frappe):
        """Payslip deduction label must be 'LINDUNG 24/7 (Employee)'."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, ee_rate=0.005, activation_date="2026-01-01"
        )
        result = self.compute(3000.0, "2026-07-01")
        self.assertIn("LINDUNG 24/7", result["label"])
        self.assertIn("Employee", result["label"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_rate_returned_matches_config(self, mock_frappe):
        """Returned rate must match the gazette rate from settings."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, ee_rate=0.005, activation_date="2026-01-01"
        )
        result = self.compute(3000.0, "2026-07-01")
        self.assertAlmostEqual(result["rate"], 0.005, places=4)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_zero_gross_pay_gives_zero_amount(self, mock_frappe):
        """Zero gross pay → zero deduction."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, ee_rate=0.005, activation_date="2026-01-01"
        )
        result = self.compute(0.0, "2026-07-01")
        self.assertAlmostEqual(result["amount"], 0.00, places=2)


class TestComputeEmployerContribution(FrappeTestCase):
    """compute_lindung_employer_contribution() accuracy and gazette guard."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service import (
            compute_lindung_employer_contribution,
        )
        self.compute = compute_lindung_employer_contribution

    def _make_settings(self, pending=0, ee_rate=0.005, er_rate=0.005, activation_date="2026-01-01"):
        mock_settings = MagicMock()
        def get_val(key, default=None):
            return {
                "lindung_24_7_pending_gazette": pending,
                "lindung_24_7_employee_rate": ee_rate,
                "lindung_24_7_employer_rate": er_rate,
                "lindung_24_7_activation_date": activation_date,
            }.get(key, default)
        mock_settings.get = get_val
        return mock_settings

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_dict_with_required_keys(self, mock_frappe):
        mock_frappe.get_single.return_value = self._make_settings(pending=1)
        result = self.compute(3000.0, "2026-07-01")
        for key in ("amount", "rate", "active", "label"):
            self.assertIn(key, result, f"Missing key: {key}")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_zero_when_gazette_pending(self, mock_frappe):
        """Acceptance criterion: employer cost is zero before gazette."""
        mock_frappe.get_single.return_value = self._make_settings(pending=1)
        result = self.compute(3000.0, "2026-07-01")
        self.assertAlmostEqual(result["amount"], 0.00, places=2)
        self.assertFalse(result["active"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_computes_employer_amount_when_active(self, mock_frappe):
        """Acceptance criterion: employer LINDUNG 24/7 added to employer cost calculation."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, er_rate=0.005, activation_date="2026-01-01"
        )
        result = self.compute(3000.0, "2026-07-01")
        self.assertAlmostEqual(result["amount"], 15.00, places=2)
        self.assertTrue(result["active"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_employer_label_contains_lindung(self, mock_frappe):
        """Employer cost label must reference LINDUNG 24/7."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, er_rate=0.005, activation_date="2026-01-01"
        )
        result = self.compute(3000.0, "2026-07-01")
        self.assertIn("LINDUNG", result["label"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_different_employer_rate_applied(self, mock_frappe):
        """RM5,000 × 1% = RM50.00 employer LINDUNG contribution."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, er_rate=0.01, activation_date="2026-01-01"
        )
        result = self.compute(5000.0, "2026-07-01")
        self.assertAlmostEqual(result["amount"], 50.00, places=2)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_rate_returned_matches_employer_config(self, mock_frappe):
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, er_rate=0.007, activation_date="2026-01-01"
        )
        result = self.compute(3000.0, "2026-07-01")
        self.assertAlmostEqual(result["rate"], 0.007, places=4)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_zero_gross_pay_gives_zero_employer_amount(self, mock_frappe):
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, er_rate=0.005, activation_date="2026-01-01"
        )
        result = self.compute(0.0, "2026-07-01")
        self.assertAlmostEqual(result["amount"], 0.00, places=2)


class TestGazetteAlertMessage(FrappeTestCase):
    """get_gazette_alert_message() HR Manager alert content."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service import (
            get_gazette_alert_message,
        )
        self.get_message = get_gazette_alert_message

    def test_returns_string(self):
        msg = self.get_message(0.005, "2026-07-01")
        self.assertIsInstance(msg, str)

    def test_message_is_non_trivially_long(self):
        """Alert should contain enough actionable information."""
        msg = self.get_message(0.005, "2026-07-01")
        self.assertGreater(len(msg), 50)

    def test_message_mentions_lindung(self):
        """Acceptance criterion: alert must mention LINDUNG 24/7."""
        msg = self.get_message(0.005, "2026-07-01")
        self.assertIn("LINDUNG 24/7", msg)

    def test_message_mentions_activation_date(self):
        """Alert must include the gazette effective date."""
        msg = self.get_message(0.005, "2026-07-01")
        self.assertIn("2026-07-01", msg)

    def test_message_prompts_recalculation(self):
        """Acceptance criterion: alert prompts payroll recalculation from gazette date."""
        msg = self.get_message(0.005, "2026-07-01")
        self.assertIn("recalculate", msg.lower())

    def test_different_rate_in_message(self):
        """Message should reflect the actual gazette rate."""
        msg = self.get_message(0.01, "2026-07-01")
        self.assertIn("LINDUNG 24/7", msg)
        self.assertIn("2026-07-01", msg)


class TestPerkesoAssistIntegration(FrappeTestCase):
    """get_perkeso_assist_lindung_amounts() PERKESO ASSIST e-Caruman integration."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service import (
            get_perkeso_assist_lindung_amounts,
        )
        self.get_amounts = get_perkeso_assist_lindung_amounts

    def _make_settings(self, pending=0, ee_rate=0.005, er_rate=0.005, activation_date="2026-01-01"):
        mock_settings = MagicMock()
        def get_val(key, default=None):
            return {
                "lindung_24_7_pending_gazette": pending,
                "lindung_24_7_employee_rate": ee_rate,
                "lindung_24_7_employer_rate": er_rate,
                "lindung_24_7_activation_date": activation_date,
            }.get(key, default)
        mock_settings.get = get_val
        return mock_settings

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_returns_dict_with_required_keys(self, mock_frappe):
        mock_frappe.get_single.return_value = self._make_settings(pending=1)
        result = self.get_amounts(3000.0, "2026-07-01")
        for key in ("employee_amount", "employer_amount", "active", "column_label_ee", "column_label_er"):
            self.assertIn(key, result, f"Missing key: {key}")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_both_amounts_zero_when_pending(self, mock_frappe):
        """Acceptance criterion: PERKESO ASSIST shows zeros before gazette."""
        mock_frappe.get_single.return_value = self._make_settings(pending=1)
        result = self.get_amounts(3000.0, "2026-07-01")
        self.assertAlmostEqual(result["employee_amount"], 0.00, places=2)
        self.assertAlmostEqual(result["employer_amount"], 0.00, places=2)
        self.assertFalse(result["active"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_correct_amounts_when_gazette_active(self, mock_frappe):
        """Acceptance criterion: PERKESO ASSIST includes both LINDUNG 24/7 amounts post-gazette."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, ee_rate=0.005, er_rate=0.005, activation_date="2026-01-01"
        )
        result = self.get_amounts(4000.0, "2026-07-01")
        # RM4,000 × 0.5% = RM20.00 for both
        self.assertAlmostEqual(result["employee_amount"], 20.00, places=2)
        self.assertAlmostEqual(result["employer_amount"], 20.00, places=2)
        self.assertTrue(result["active"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_column_labels_contain_lindung(self, mock_frappe):
        """Column labels in PERKESO ASSIST CSV must identify LINDUNG 24/7."""
        mock_frappe.get_single.return_value = self._make_settings(pending=1)
        result = self.get_amounts(3000.0, "2026-07-01")
        self.assertIn("LINDUNG", result["column_label_ee"])
        self.assertIn("LINDUNG", result["column_label_er"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_different_ee_and_er_rates(self, mock_frappe):
        """Employee and employer rates can differ independently."""
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, ee_rate=0.003, er_rate=0.007, activation_date="2026-01-01"
        )
        result = self.get_amounts(5000.0, "2026-07-01")
        # RM5,000 × 0.3% = RM15.00 employee; RM5,000 × 0.7% = RM35.00 employer
        self.assertAlmostEqual(result["employee_amount"], 15.00, places=2)
        self.assertAlmostEqual(result["employer_amount"], 35.00, places=2)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung_24_7_service.frappe")
    def test_active_flag_true_when_gazette_published(self, mock_frappe):
        mock_frappe.get_single.return_value = self._make_settings(
            pending=0, ee_rate=0.005, er_rate=0.005, activation_date="2026-01-01"
        )
        result = self.get_amounts(3000.0, "2026-07-01")
        self.assertTrue(result["active"])
