"""Tests for US-310: PERKESO LINDUNG 24/7 Employee Contribution Deduction Engine.

Verifies the LINDUNG 24/7 Non-Occupational Accident Scheme contribution engine
introduced by the Employees' Social Security (Amendment) Bill 2025 (passed
2 December 2025).

Test coverage:
  - Module constants (labels, warning message, defaults)
  - is_lindung247_active() — gazette gate logic
  - compute_lindung247_contribution() — rate math, ceiling, rounding
  - get_lindung247_payslip_line() — pre-gazette warning, post-gazette deduction
  - get_lindung247_employer_cost() — employer side
  - get_lindung247_compliance_warning() — warning string
  - generate_eccaruman_lindung247_rows() — PERKESO ASSIST data
  - generate_eccaruman_lindung247_csv() — CSV output
  - alert_hr_gazette_rate_entered() — system alert on rate entry
"""
from unittest.mock import patch, MagicMock
from frappe.tests.utils import FrappeTestCase


# ---------------------------------------------------------------------------
# Helper: build mock LHDN Payroll Settings
# ---------------------------------------------------------------------------

def _mock_settings(gazette_status="Pending Gazette", activation_date=None,
                   employee_rate=0.0, employer_rate=0.0, wage_ceiling=6000.0):
    """Return a MagicMock simulating LHDN Payroll Settings."""
    mock = MagicMock()

    def _get(field, default=None):
        data = {
            "lindung247_gazette_status": gazette_status,
            "lindung247_activation_date": activation_date,
            "lindung247_employee_rate": employee_rate,
            "lindung247_employer_rate": employer_rate,
            "lindung247_wage_ceiling": wage_ceiling,
        }
        return data.get(field, default)

    mock.get = _get
    return mock


# ---------------------------------------------------------------------------
# 1. Module constants
# ---------------------------------------------------------------------------

class TestLindung247Constants(FrappeTestCase):
    """Module-level constants are correctly defined."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
            LINDUNG247_STATUS_PENDING,
            LINDUNG247_STATUS_ACTIVE,
            LINDUNG247_PAYSLIP_LABEL,
            LINDUNG247_EMPLOYER_LABEL,
            LINDUNG247_COMPLIANCE_WARNING,
            LINDUNG247_DEFAULT_WAGE_CEILING,
        )
        self.status_pending = LINDUNG247_STATUS_PENDING
        self.status_active = LINDUNG247_STATUS_ACTIVE
        self.payslip_label = LINDUNG247_PAYSLIP_LABEL
        self.employer_label = LINDUNG247_EMPLOYER_LABEL
        self.warning = LINDUNG247_COMPLIANCE_WARNING
        self.ceiling = LINDUNG247_DEFAULT_WAGE_CEILING

    def test_status_pending_value(self):
        self.assertEqual(self.status_pending, "Pending Gazette")

    def test_status_active_value(self):
        self.assertEqual(self.status_active, "Active")

    def test_payslip_label_includes_employee(self):
        self.assertIn("Employee", self.payslip_label)
        self.assertIn("LINDUNG 24/7", self.payslip_label)

    def test_employer_label_includes_employer(self):
        self.assertIn("Employer", self.employer_label)
        self.assertIn("LINDUNG 24/7", self.employer_label)

    def test_compliance_warning_mentions_gazette(self):
        self.assertIn("gazette", self.warning.lower())

    def test_compliance_warning_mentions_not_applied(self):
        self.assertIn("not applied", self.warning.lower())

    def test_default_wage_ceiling_is_6000(self):
        self.assertAlmostEqual(self.ceiling, 6000.0, places=2)


# ---------------------------------------------------------------------------
# 2. is_lindung247_active()
# ---------------------------------------------------------------------------

class TestIsLindung247Active(FrappeTestCase):
    """is_lindung247_active() returns correct boolean based on settings."""

    def _patch_settings(self, gazette_status="Pending Gazette", activation_date=None,
                        employee_rate=0.0, employer_rate=0.0):
        return patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_single",
            return_value=_mock_settings(gazette_status, activation_date,
                                        employee_rate, employer_rate),
        )

    def test_pending_gazette_returns_false(self):
        """Pre-gazette: status is 'Pending Gazette' → always False."""
        with self._patch_settings("Pending Gazette", "2026-01-01", 0.005, 0.005):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                is_lindung247_active,
            )
            self.assertFalse(is_lindung247_active("2026-06-01"))

    def test_active_status_no_date_returns_false(self):
        """Active status but no activation date → False."""
        with self._patch_settings("Active", None, 0.005, 0.005):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                is_lindung247_active,
            )
            self.assertFalse(is_lindung247_active("2026-06-01"))

    def test_active_status_future_date_returns_false(self):
        """Active status but activation date in the future → False."""
        with self._patch_settings("Active", "2026-07-01", 0.005, 0.005):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                is_lindung247_active,
            )
            self.assertFalse(is_lindung247_active("2026-06-01"))

    def test_active_status_past_date_returns_true(self):
        """Active status and activation date in the past → True."""
        with self._patch_settings("Active", "2026-04-01", 0.005, 0.005):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                is_lindung247_active,
            )
            self.assertTrue(is_lindung247_active("2026-06-01"))

    def test_active_status_on_activation_date_returns_true(self):
        """On the exact activation date → True."""
        with self._patch_settings("Active", "2026-04-01", 0.005, 0.005):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                is_lindung247_active,
            )
            self.assertTrue(is_lindung247_active("2026-04-01"))

    def test_settings_exception_returns_false(self):
        """If settings cannot be read → False (safe default)."""
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_single",
            side_effect=Exception("DocType not found"),
        ):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                is_lindung247_active,
            )
            self.assertFalse(is_lindung247_active("2026-06-01"))


# ---------------------------------------------------------------------------
# 3. compute_lindung247_contribution()
# ---------------------------------------------------------------------------

class TestComputeLindung247Contribution(FrappeTestCase):
    """compute_lindung247_contribution() correctly calculates employer + employee amounts."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
            compute_lindung247_contribution,
        )
        self.compute = compute_lindung247_contribution

    def test_returns_dict_with_required_keys(self):
        result = self.compute(3000, 0.005, 0.005, 6000)
        for key in ("employee", "employer", "insurable_earnings", "employee_rate", "employer_rate"):
            self.assertIn(key, result)

    def test_standard_rate_3000_gross(self):
        """RM3,000 gross at 0.5% each → RM15.00 employee + employer."""
        result = self.compute(3000, 0.005, 0.005, 6000)
        self.assertAlmostEqual(result["employee"], 15.00, places=2)
        self.assertAlmostEqual(result["employer"], 15.00, places=2)
        self.assertAlmostEqual(result["insurable_earnings"], 3000.00, places=2)

    def test_above_ceiling_capped_at_ceiling(self):
        """Gross above ceiling → insurable capped at ceiling."""
        result = self.compute(10000, 0.005, 0.005, 6000)
        self.assertAlmostEqual(result["insurable_earnings"], 6000.00, places=2)
        self.assertAlmostEqual(result["employee"], 30.00, places=2)
        self.assertAlmostEqual(result["employer"], 30.00, places=2)

    def test_at_ceiling_boundary(self):
        """Gross exactly at ceiling → insurable equals ceiling."""
        result = self.compute(6000, 0.005, 0.005, 6000)
        self.assertAlmostEqual(result["insurable_earnings"], 6000.00, places=2)

    def test_zero_gross_pay(self):
        """Zero gross pay → zero contributions."""
        result = self.compute(0, 0.005, 0.005, 6000)
        self.assertAlmostEqual(result["employee"], 0.0, places=2)
        self.assertAlmostEqual(result["employer"], 0.0, places=2)

    def test_different_employee_and_employer_rates(self):
        """Employer and employee rates can differ."""
        result = self.compute(4000, 0.003, 0.007, 6000)
        self.assertAlmostEqual(result["employee"], 12.00, places=2)
        self.assertAlmostEqual(result["employer"], 28.00, places=2)

    def test_rates_stored_in_result(self):
        """Result preserves the rates used for audit trail."""
        result = self.compute(5000, 0.005, 0.006, 6000)
        self.assertAlmostEqual(result["employee_rate"], 0.005, places=4)
        self.assertAlmostEqual(result["employer_rate"], 0.006, places=4)

    def test_rounding_to_two_decimal_places(self):
        """Contribution amounts are rounded to 2 decimal places."""
        # 3333 * 0.005 = 16.665 → 16.67
        result = self.compute(3333, 0.005, 0.005, 6000)
        self.assertAlmostEqual(result["employee"], round(3333 * 0.005, 2), places=2)


# ---------------------------------------------------------------------------
# 4. get_lindung247_payslip_line()
# ---------------------------------------------------------------------------

class TestGetLindung247PayslipLine(FrappeTestCase):
    """get_lindung247_payslip_line() returns correct entry based on gazette status."""

    def _patch_active(self, active: bool, employee_rate=0.005, employer_rate=0.005):
        activation_date = "2026-04-01" if active else None
        gazette_status = "Active" if active else "Pending Gazette"
        return patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_single",
            return_value=_mock_settings(gazette_status, activation_date,
                                        employee_rate, employer_rate),
        )

    def test_pre_gazette_returns_zero_amount(self):
        """Pre-gazette → amount is 0.0."""
        with self._patch_active(False):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                get_lindung247_payslip_line,
            )
            line = get_lindung247_payslip_line(5000, as_of_date="2026-03-01")
        self.assertAlmostEqual(line["amount"], 0.0, places=2)

    def test_pre_gazette_returns_compliance_warning(self):
        """Pre-gazette → warning message is non-empty."""
        with self._patch_active(False):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                get_lindung247_payslip_line,
                LINDUNG247_COMPLIANCE_WARNING,
            )
            line = get_lindung247_payslip_line(5000, as_of_date="2026-03-01")
        self.assertEqual(line["warning"], LINDUNG247_COMPLIANCE_WARNING)
        self.assertFalse(line["is_active"])

    def test_pre_gazette_label_is_correct(self):
        """Pre-gazette → label is LINDUNG 24/7 (Employee)."""
        with self._patch_active(False):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                get_lindung247_payslip_line,
                LINDUNG247_PAYSLIP_LABEL,
            )
            line = get_lindung247_payslip_line(5000, as_of_date="2026-03-01")
        self.assertEqual(line["label"], LINDUNG247_PAYSLIP_LABEL)

    def test_post_gazette_returns_correct_amount(self):
        """Post-gazette → amount equals employee rate * insurable earnings."""
        with self._patch_active(True, employee_rate=0.005, employer_rate=0.005):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                get_lindung247_payslip_line,
            )
            line = get_lindung247_payslip_line(4000, as_of_date="2026-06-01")
        # 4000 * 0.005 = 20.00
        self.assertAlmostEqual(line["amount"], 20.00, places=2)
        self.assertTrue(line["is_active"])
        self.assertEqual(line["warning"], "")

    def test_post_gazette_no_warning(self):
        """Post-gazette → no compliance warning."""
        with self._patch_active(True):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                get_lindung247_payslip_line,
            )
            line = get_lindung247_payslip_line(3000, as_of_date="2026-06-01")
        self.assertEqual(line["warning"], "")

    def test_payslip_line_label_distinct_from_first_category(self):
        """LINDUNG 24/7 payslip label is distinct from SOCSO First Category label."""
        with self._patch_active(True):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                get_lindung247_payslip_line,
            )
            line = get_lindung247_payslip_line(3000, as_of_date="2026-06-01")
        # Must not be the same as any existing SOCSO label
        self.assertNotEqual(line["label"], "SOCSO (Employee)")
        self.assertNotEqual(line["label"], "EIS (Employee)")


# ---------------------------------------------------------------------------
# 5. get_lindung247_employer_cost()
# ---------------------------------------------------------------------------

class TestGetLindung247EmployerCost(FrappeTestCase):
    """get_lindung247_employer_cost() returns employer contribution correctly."""

    def _patch_active(self, active: bool, employer_rate=0.005):
        activation_date = "2026-04-01" if active else None
        gazette_status = "Active" if active else "Pending Gazette"
        return patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_single",
            return_value=_mock_settings(gazette_status, activation_date,
                                        0.005, employer_rate),
        )

    def test_pre_gazette_employer_cost_is_zero(self):
        """Pre-gazette → employer cost is 0.0."""
        with self._patch_active(False):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                get_lindung247_employer_cost,
            )
            cost = get_lindung247_employer_cost(5000, as_of_date="2026-03-01")
        self.assertAlmostEqual(cost["amount"], 0.0, places=2)
        self.assertFalse(cost["is_active"])

    def test_post_gazette_employer_cost_calculated(self):
        """Post-gazette → employer cost equals employer rate * insurable earnings."""
        with self._patch_active(True, employer_rate=0.005):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                get_lindung247_employer_cost,
            )
            cost = get_lindung247_employer_cost(4000, as_of_date="2026-06-01")
        # 4000 * 0.005 = 20.00
        self.assertAlmostEqual(cost["amount"], 20.00, places=2)
        self.assertTrue(cost["is_active"])

    def test_employer_label_is_correct(self):
        """Employer label is LINDUNG 24/7 (Employer)."""
        with self._patch_active(True):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                get_lindung247_employer_cost,
                LINDUNG247_EMPLOYER_LABEL,
            )
            cost = get_lindung247_employer_cost(3000, as_of_date="2026-06-01")
        self.assertEqual(cost["label"], LINDUNG247_EMPLOYER_LABEL)


# ---------------------------------------------------------------------------
# 6. get_lindung247_compliance_warning()
# ---------------------------------------------------------------------------

class TestGetLindung247ComplianceWarning(FrappeTestCase):
    """get_lindung247_compliance_warning() returns correct string."""

    def test_pre_gazette_returns_warning_string(self):
        """Pre-gazette → returns the compliance warning."""
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_single",
            return_value=_mock_settings("Pending Gazette", None),
        ):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                get_lindung247_compliance_warning,
                LINDUNG247_COMPLIANCE_WARNING,
            )
            warning = get_lindung247_compliance_warning()
        self.assertEqual(warning, LINDUNG247_COMPLIANCE_WARNING)

    def test_post_gazette_returns_empty_string(self):
        """Post-gazette → returns empty string (no warning)."""
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_single",
            return_value=_mock_settings("Active", "2026-01-01", 0.005, 0.005),
        ):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                get_lindung247_compliance_warning,
            )
            # Mock nowdate so it's after activation date
            with patch(
                "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.nowdate",
                return_value="2026-06-01",
            ):
                warning = get_lindung247_compliance_warning()
        self.assertEqual(warning, "")


# ---------------------------------------------------------------------------
# 7. generate_eccaruman_lindung247_rows()
# ---------------------------------------------------------------------------

class TestGenerateEccarumanLindung247Rows(FrappeTestCase):
    """generate_eccaruman_lindung247_rows() produces correct PERKESO ASSIST data."""

    def _active_settings_patch(self):
        return patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_single",
            return_value=_mock_settings("Active", "2026-01-01", 0.005, 0.005, 6000),
        )

    def _pending_settings_patch(self):
        return patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_single",
            return_value=_mock_settings("Pending Gazette", None),
        )

    def _db_sql_patch(self, rows):
        return patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.db.sql",
            return_value=rows,
        )

    def test_pre_gazette_returns_empty_list(self):
        """Pre-gazette → no rows generated (deduction not applied)."""
        with self._pending_settings_patch():
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                generate_eccaruman_lindung247_rows,
            )
            # Patch nowdate to ensure pre-gazette state
            with patch(
                "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.nowdate",
                return_value="2026-03-01",
            ):
                rows = generate_eccaruman_lindung247_rows("Test Company", 2026, 3)
        self.assertEqual(rows, [])

    def test_post_gazette_returns_rows_for_each_employee(self):
        """Post-gazette → one row per employee with contribution amounts."""
        mock_slips = [
            {"employee": "EMP-001", "employee_name": "Ahmad", "gross_pay": 4000, "nric": "900101-01-1234"},
            {"employee": "EMP-002", "employee_name": "Siti", "gross_pay": 3000, "nric": "850615-04-5678"},
        ]
        with self._active_settings_patch():
            with self._db_sql_patch(mock_slips):
                from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                    generate_eccaruman_lindung247_rows,
                )
                with patch(
                    "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.nowdate",
                    return_value="2026-06-01",
                ):
                    rows = generate_eccaruman_lindung247_rows("Test Company", 2026, 3)

        self.assertEqual(len(rows), 2)

    def test_post_gazette_correct_contribution_amounts(self):
        """Post-gazette → contribution amounts computed from rate and gross pay."""
        mock_slips = [
            {"employee": "EMP-001", "employee_name": "Ahmad", "gross_pay": 4000, "nric": "900101-01-1234"},
        ]
        with self._active_settings_patch():
            with self._db_sql_patch(mock_slips):
                from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                    generate_eccaruman_lindung247_rows,
                )
                with patch(
                    "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.nowdate",
                    return_value="2026-06-01",
                ):
                    rows = generate_eccaruman_lindung247_rows("Test Company", 2026, 3)

        row = rows[0]
        # 4000 * 0.005 = 20.00 each
        self.assertAlmostEqual(row["lindung247_employee"], 20.00, places=2)
        self.assertAlmostEqual(row["lindung247_employer"], 20.00, places=2)
        self.assertEqual(row["employee"], "EMP-001")
        self.assertEqual(row["nric"], "900101-01-1234")

    def test_gross_above_ceiling_capped(self):
        """Wages above ceiling → insurable earnings capped at ceiling."""
        mock_slips = [
            {"employee": "EMP-001", "employee_name": "Ahmad", "gross_pay": 10000, "nric": "900101-01-1234"},
        ]
        with self._active_settings_patch():
            with self._db_sql_patch(mock_slips):
                from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                    generate_eccaruman_lindung247_rows,
                )
                with patch(
                    "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.nowdate",
                    return_value="2026-06-01",
                ):
                    rows = generate_eccaruman_lindung247_rows("Test Company", 2026, 3)

        row = rows[0]
        # Capped at 6000 * 0.005 = 30.00
        self.assertAlmostEqual(row["insurable_earnings"], 6000.00, places=2)
        self.assertAlmostEqual(row["lindung247_employee"], 30.00, places=2)

    def test_row_contains_required_keys(self):
        """Each row must contain all required PERKESO ASSIST fields."""
        mock_slips = [
            {"employee": "EMP-001", "employee_name": "Ahmad", "gross_pay": 3000, "nric": "900101-01-1234"},
        ]
        with self._active_settings_patch():
            with self._db_sql_patch(mock_slips):
                from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                    generate_eccaruman_lindung247_rows,
                )
                with patch(
                    "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.nowdate",
                    return_value="2026-06-01",
                ):
                    rows = generate_eccaruman_lindung247_rows("Test Company", 2026, 3)

        required_keys = {
            "employee", "employee_name", "nric",
            "gross_pay", "insurable_earnings",
            "lindung247_employee", "lindung247_employer",
        }
        for key in required_keys:
            self.assertIn(key, rows[0], f"Missing key: {key}")


# ---------------------------------------------------------------------------
# 8. generate_eccaruman_lindung247_csv()
# ---------------------------------------------------------------------------

class TestGenerateEccarumanLindung247Csv(FrappeTestCase):
    """generate_eccaruman_lindung247_csv() produces valid CSV."""

    def _active_settings_patch(self):
        return patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_single",
            return_value=_mock_settings("Active", "2026-01-01", 0.005, 0.005, 6000),
        )

    def _db_sql_patch(self, rows):
        return patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.db.sql",
            return_value=rows,
        )

    def test_pre_gazette_csv_is_empty_string(self):
        """Pre-gazette → CSV output is empty string (no submission)."""
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_single",
            return_value=_mock_settings("Pending Gazette", None),
        ):
            from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                generate_eccaruman_lindung247_csv,
            )
            with patch(
                "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.nowdate",
                return_value="2026-03-01",
            ):
                csv_out = generate_eccaruman_lindung247_csv("Test Company", 2026, 3)
        self.assertEqual(csv_out, "")

    def test_post_gazette_csv_has_header_row(self):
        """Post-gazette CSV starts with a header row."""
        mock_slips = [
            {"employee": "EMP-001", "employee_name": "Ahmad", "gross_pay": 3000, "nric": "900101-01-1234"},
        ]
        with self._active_settings_patch():
            with self._db_sql_patch(mock_slips):
                from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                    generate_eccaruman_lindung247_csv,
                )
                with patch(
                    "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.nowdate",
                    return_value="2026-06-01",
                ):
                    csv_out = generate_eccaruman_lindung247_csv("Test Company", 2026, 3)

        lines = csv_out.strip().splitlines()
        self.assertTrue(len(lines) >= 1, "CSV must have at least a header row")
        self.assertIn("NRIC", lines[0])
        self.assertIn("LINDUNG", lines[0])

    def test_post_gazette_csv_includes_employee_data(self):
        """Post-gazette CSV includes employee data rows."""
        mock_slips = [
            {"employee": "EMP-001", "employee_name": "Ahmad", "gross_pay": 3000, "nric": "900101-01-1234"},
        ]
        with self._active_settings_patch():
            with self._db_sql_patch(mock_slips):
                from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                    generate_eccaruman_lindung247_csv,
                )
                with patch(
                    "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.nowdate",
                    return_value="2026-06-01",
                ):
                    csv_out = generate_eccaruman_lindung247_csv("Test Company", 2026, 3)

        self.assertIn("Ahmad", csv_out)
        self.assertIn("900101-01-1234", csv_out)

    def test_post_gazette_csv_has_totals_row(self):
        """Post-gazette CSV includes a TOTAL row."""
        mock_slips = [
            {"employee": "EMP-001", "employee_name": "Ahmad", "gross_pay": 3000, "nric": "900101-01-1234"},
        ]
        with self._active_settings_patch():
            with self._db_sql_patch(mock_slips):
                from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                    generate_eccaruman_lindung247_csv,
                )
                with patch(
                    "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.nowdate",
                    return_value="2026-06-01",
                ):
                    csv_out = generate_eccaruman_lindung247_csv("Test Company", 2026, 3)

        self.assertIn("TOTAL", csv_out)


# ---------------------------------------------------------------------------
# 9. alert_hr_gazette_rate_entered()
# ---------------------------------------------------------------------------

class TestAlertHrGazetteRateEntered(FrappeTestCase):
    """alert_hr_gazette_rate_entered() fires realtime event when rate is set."""

    def _make_doc(self, gazette_status, activation_date, employee_rate, employer_rate=0.005):
        doc = MagicMock()

        def _get(field, *args):
            data = {
                "lindung247_gazette_status": gazette_status,
                "lindung247_activation_date": activation_date,
                "lindung247_employee_rate": employee_rate,
                "lindung247_employer_rate": employer_rate,
            }
            return data.get(field)

        doc.get = _get
        return doc

    def test_pending_gazette_does_not_alert(self):
        """Pre-gazette status → no alert fired."""
        doc = self._make_doc("Pending Gazette", None, 0.0)
        with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.publish_realtime") as mock_pub:
            with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.log_error") as mock_log:
                with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_all", return_value=[]):
                    from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                        alert_hr_gazette_rate_entered,
                    )
                    alert_hr_gazette_rate_entered(doc)
        mock_pub.assert_not_called()

    def test_active_with_rate_fires_alert(self):
        """Active status + rate + date → alert fired and error log written."""
        doc = self._make_doc("Active", "2026-04-01", 0.005)
        mock_users = [{"name": "admin@example.com", "email": "admin@example.com"}]
        with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.publish_realtime") as mock_pub:
            with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.log_error") as mock_log:
                with patch(
                    "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_all",
                    return_value=mock_users,
                ):
                    from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                        alert_hr_gazette_rate_entered,
                    )
                    alert_hr_gazette_rate_entered(doc)

        mock_pub.assert_called_once()
        mock_log.assert_called_once()

    def test_active_no_date_does_not_alert(self):
        """Active status but no activation_date → no alert."""
        doc = self._make_doc("Active", None, 0.005)
        with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.publish_realtime") as mock_pub:
            with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.log_error"):
                with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_all", return_value=[]):
                    from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                        alert_hr_gazette_rate_entered,
                    )
                    alert_hr_gazette_rate_entered(doc)
        mock_pub.assert_not_called()

    def test_active_no_rate_does_not_alert(self):
        """Active status but no employee_rate → no alert."""
        doc = self._make_doc("Active", "2026-04-01", None)
        with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.publish_realtime") as mock_pub:
            with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.log_error"):
                with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_all", return_value=[]):
                    from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                        alert_hr_gazette_rate_entered,
                    )
                    alert_hr_gazette_rate_entered(doc)
        mock_pub.assert_not_called()

    def test_alert_message_contains_rate_info(self):
        """Alert message includes contribution rates and effective date."""
        doc = self._make_doc("Active", "2026-04-01", 0.005, 0.005)
        mock_users = [{"name": "hr@example.com", "email": "hr@example.com"}]
        with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.publish_realtime") as mock_pub:
            with patch("lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.log_error"):
                with patch(
                    "lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service.frappe.get_all",
                    return_value=mock_users,
                ):
                    from lhdn_payroll_integration.lhdn_payroll_integration.services.lindung247_service import (
                        alert_hr_gazette_rate_entered,
                    )
                    alert_hr_gazette_rate_entered(doc)

        call_kwargs = mock_pub.call_args
        payload = call_kwargs[0][1] if call_kwargs[0] else call_kwargs[1].get("message", {})
        msg = payload.get("message", "")
        self.assertIn("2026-04-01", msg)
        self.assertIn("LINDUNG 24/7", msg)
