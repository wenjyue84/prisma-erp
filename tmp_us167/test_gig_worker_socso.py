"""Tests for US-167: Gig Worker SOCSO (SEIA) Deduction Engine Skeleton.

Verifies the Self-Employment Social Security contribution engine for
platform workers under the Gig Workers Act 2025 (Act 872) and SEIA Act 789.

Test coverage:
  - Constants (rate, ceiling, floor, employer zero)
  - compute_seia_contribution() accuracy and edge cases
  - is_seia_active() commencement date guard
  - is_gig_worker() and is_domestic_gig_exempt() eligibility checks
  - get_eligible_gig_workers() DB query (mocked)
  - generate_seia_remittance_file() CSV output (mocked)
"""
from unittest.mock import patch, MagicMock
from frappe.tests.utils import FrappeTestCase


class TestSeiaConstants(FrappeTestCase):
    """Module-level constants are correct per SEIA Act 789."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service import (
            SEIA_WORKER_RATE,
            SEIA_EMPLOYER_RATE,
            SEIA_EARNINGS_CEILING,
            SEIA_MIN_CONTRIBUTION,
            GIG_WORKER_EMPLOYMENT_TYPE,
        )
        self.rate = SEIA_WORKER_RATE
        self.employer_rate = SEIA_EMPLOYER_RATE
        self.ceiling = SEIA_EARNINGS_CEILING
        self.min_contrib = SEIA_MIN_CONTRIBUTION
        self.gig_type = GIG_WORKER_EMPLOYMENT_TYPE

    def test_worker_rate_is_2_percent(self):
        self.assertAlmostEqual(self.rate, 0.02, places=4)

    def test_employer_rate_is_zero(self):
        """SEIA is worker-funded only — employer share must be zero."""
        self.assertAlmostEqual(self.employer_rate, 0.00, places=4)

    def test_earnings_ceiling_is_5000(self):
        self.assertAlmostEqual(self.ceiling, 5000.00, places=2)

    def test_minimum_contribution_is_5(self):
        self.assertAlmostEqual(self.min_contrib, 5.00, places=2)

    def test_gig_worker_employment_type_string(self):
        self.assertEqual(self.gig_type, "Gig / Platform Worker")


class TestComputeSeiaContribution(FrappeTestCase):
    """compute_seia_contribution() accuracy across wage bands."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service import (
            compute_seia_contribution,
        )
        self.calc = compute_seia_contribution

    def test_returns_dict_with_expected_keys(self):
        result = self.calc(2000)
        self.assertIsInstance(result, dict)
        for key in ("worker", "employer", "insurable_earnings", "rate"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_employer_always_zero(self):
        """Employer share is always 0 for SEIA (worker-funded)."""
        for wages in [500, 1000, 3000, 5000, 8000]:
            result = self.calc(wages)
            self.assertAlmostEqual(result["employer"], 0.00, places=2,
                msg=f"Employer share must be 0 for wages RM{wages}")

    def test_2000_wages_gives_40_ringgit(self):
        """RM2,000 × 2% = RM40.00 worker SEIA."""
        result = self.calc(2000)
        self.assertAlmostEqual(result["worker"], 40.00, places=2)

    def test_5000_wages_at_ceiling(self):
        """RM5,000 × 2% = RM100.00 (at ceiling)."""
        result = self.calc(5000)
        self.assertAlmostEqual(result["worker"], 100.00, places=2)
        self.assertAlmostEqual(result["insurable_earnings"], 5000.00, places=2)

    def test_6000_wages_capped_at_5000_ceiling(self):
        """RM6,000 earnings → insurable capped at RM5,000 → RM100.00 SEIA."""
        result = self.calc(6000)
        self.assertAlmostEqual(result["insurable_earnings"], 5000.00, places=2)
        self.assertAlmostEqual(result["worker"], 100.00, places=2)

    def test_10000_wages_capped_at_ceiling(self):
        """Very high earnings are capped at SEIA ceiling."""
        result_ceiling = self.calc(5000)
        result_high = self.calc(10000)
        self.assertAlmostEqual(result_high["worker"], result_ceiling["worker"], places=2)

    def test_minimum_floor_applied_for_very_low_earnings(self):
        """RM100 × 2% = RM2.00 → floor raises to RM5.00 minimum."""
        result = self.calc(100)
        self.assertAlmostEqual(result["worker"], 5.00, places=2)

    def test_zero_earnings_gives_zero_contribution(self):
        """Zero earnings → zero SEIA (floor does not apply when no earnings)."""
        result = self.calc(0)
        self.assertAlmostEqual(result["worker"], 0.00, places=2)

    def test_250_earnings_minimum_floor(self):
        """RM250 × 2% = RM5.00 → exactly at floor, no change."""
        result = self.calc(250)
        self.assertAlmostEqual(result["worker"], 5.00, places=2)

    def test_rate_returned_is_seia_rate(self):
        result = self.calc(3000)
        self.assertAlmostEqual(result["rate"], 0.02, places=4)

    def test_1000_wages_gives_20_ringgit(self):
        """RM1,000 × 2% = RM20.00."""
        result = self.calc(1000)
        self.assertAlmostEqual(result["worker"], 20.00, places=2)

    def test_3000_wages_gives_60_ringgit(self):
        """RM3,000 × 2% = RM60.00."""
        result = self.calc(3000)
        self.assertAlmostEqual(result["worker"], 60.00, places=2)


class TestSeiaCommencement(FrappeTestCase):
    """is_seia_active() commencement date guard."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service import (
            is_seia_active,
        )
        self.is_active = is_seia_active

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_returns_false_when_commencement_date_blank(self, mock_frappe):
        mock_settings = MagicMock()
        mock_settings.get.return_value = None
        mock_frappe.get_single.return_value = mock_settings
        self.assertFalse(self.is_active("2026-06-01"))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_returns_false_before_commencement_date(self, mock_frappe):
        mock_settings = MagicMock()
        mock_settings.get.return_value = "2026-07-01"
        mock_frappe.get_single.return_value = mock_settings
        # Check date is before commencement
        self.assertFalse(self.is_active("2026-06-30"))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_returns_true_on_commencement_date(self, mock_frappe):
        mock_settings = MagicMock()
        mock_settings.get.return_value = "2026-07-01"
        mock_frappe.get_single.return_value = mock_settings
        self.assertTrue(self.is_active("2026-07-01"))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_returns_true_after_commencement_date(self, mock_frappe):
        mock_settings = MagicMock()
        mock_settings.get.return_value = "2026-07-01"
        mock_frappe.get_single.return_value = mock_settings
        self.assertTrue(self.is_active("2026-08-15"))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_returns_false_when_settings_raises_exception(self, mock_frappe):
        mock_frappe.get_single.side_effect = Exception("Settings not found")
        self.assertFalse(self.is_active("2026-06-01"))


class TestGigWorkerEligibility(FrappeTestCase):
    """is_gig_worker() and is_domestic_gig_exempt() eligibility checks."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service import (
            is_gig_worker,
            is_domestic_gig_exempt,
        )
        self.is_gig = is_gig_worker
        self.is_exempt = is_domestic_gig_exempt

    def _make_employee(self, emp_type=None, seia_flag=0, exempt=0):
        mock_emp = MagicMock()
        mock_emp.get = lambda key, default=None: {
            "custom_employment_type": emp_type or "Permanent",
            "custom_is_seia_worker": seia_flag,
            "custom_is_domestic_gig_exempt": exempt,
        }.get(key, default)
        return mock_emp

    def test_gig_worker_with_seia_flag_is_eligible(self):
        emp = self._make_employee("Gig / Platform Worker", seia_flag=1)
        self.assertTrue(self.is_gig(emp))

    def test_gig_worker_without_seia_flag_not_eligible(self):
        emp = self._make_employee("Gig / Platform Worker", seia_flag=0)
        self.assertFalse(self.is_gig(emp))

    def test_permanent_employee_not_gig_worker(self):
        emp = self._make_employee("Permanent", seia_flag=1)
        self.assertFalse(self.is_gig(emp))

    def test_contract_employee_not_gig_worker(self):
        emp = self._make_employee("Contract", seia_flag=0)
        self.assertFalse(self.is_gig(emp))

    def test_domestic_exempt_flag_true(self):
        emp = self._make_employee("Gig / Platform Worker", seia_flag=1, exempt=1)
        self.assertTrue(self.is_exempt(emp))

    def test_domestic_exempt_flag_false(self):
        emp = self._make_employee("Gig / Platform Worker", seia_flag=1, exempt=0)
        self.assertFalse(self.is_exempt(emp))

    def test_non_exempt_gig_worker_qualifies(self):
        emp = self._make_employee("Gig / Platform Worker", seia_flag=1, exempt=0)
        self.assertTrue(self.is_gig(emp))
        self.assertFalse(self.is_exempt(emp))


class TestGetEligibleGigWorkers(FrappeTestCase):
    """get_eligible_gig_workers() database query returns correct records."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service import (
            get_eligible_gig_workers,
        )
        self.get_workers = get_eligible_gig_workers

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_returns_list(self, mock_frappe):
        mock_frappe.get_all.return_value = ["EMP-001", "EMP-002"]
        result = self.get_workers()
        self.assertIsInstance(result, list)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_filters_by_gig_employment_type(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        self.get_workers()
        call_kwargs = mock_frappe.get_all.call_args
        filters = call_kwargs[1]["filters"] if call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(filters.get("custom_employment_type"), "Gig / Platform Worker")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_filters_by_seia_flag(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        self.get_workers()
        call_kwargs = mock_frappe.get_all.call_args
        filters = call_kwargs[1]["filters"] if call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(filters.get("custom_is_seia_worker"), 1)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_excludes_domestic_exempt_workers(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        self.get_workers()
        call_kwargs = mock_frappe.get_all.call_args
        filters = call_kwargs[1]["filters"] if call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(filters.get("custom_is_domestic_gig_exempt"), 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_company_filter_applied_when_provided(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        self.get_workers(company="Test Sdn Bhd")
        call_kwargs = mock_frappe.get_all.call_args
        filters = call_kwargs[1]["filters"] if call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(filters.get("company"), "Test Sdn Bhd")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_no_company_filter_when_not_provided(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        self.get_workers()
        call_kwargs = mock_frappe.get_all.call_args
        filters = call_kwargs[1]["filters"] if call_kwargs[1] else call_kwargs[0][1]
        self.assertNotIn("company", filters)


class TestGenerateSeiaRemittanceFile(FrappeTestCase):
    """generate_seia_remittance_file() produces correct CSV output."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service import (
            generate_seia_remittance_file,
        )
        self.generate = generate_seia_remittance_file

    def _mock_db_rows(self, rows):
        return rows

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_returns_string(self, mock_frappe):
        mock_frappe.db.sql.return_value = []
        result = self.generate("Test Co", 2026, 3)
        self.assertIsInstance(result, str)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_csv_has_header_row(self, mock_frappe):
        mock_frappe.db.sql.return_value = []
        result = self.generate("Test Co", 2026, 3)
        lines = result.strip().split("\n")
        self.assertGreater(len(lines), 0)
        header = lines[0]
        self.assertIn("NRIC", header)
        self.assertIn("Employee Name", header)
        self.assertIn("SEIA", header)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_csv_includes_contribution_amounts(self, mock_frappe):
        mock_frappe.db.sql.return_value = [
            {
                "slip_name": "SAL-001",
                "employee": "EMP-001",
                "employee_name": "Ahmad bin Ali",
                "gross_pay": 3000.0,
                "custom_icpassport_number": "900101011234",
                "custom_is_domestic_gig_exempt": 0,
            }
        ]
        result = self.generate("Test Co", 2026, 3)
        # RM3,000 × 2% = RM60.00
        self.assertIn("60.00", result)
        self.assertIn("Ahmad bin Ali", result)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_exempt_worker_has_zero_contribution(self, mock_frappe):
        mock_frappe.db.sql.return_value = [
            {
                "slip_name": "SAL-002",
                "employee": "EMP-002",
                "employee_name": "Siti binti Hassan",
                "gross_pay": 2000.0,
                "custom_icpassport_number": "850202021234",
                "custom_is_domestic_gig_exempt": 1,
            }
        ]
        result = self.generate("Test Co", 2026, 3)
        # Exempt worker → 0.00 contribution
        self.assertIn("0.00", result)
        self.assertIn("Yes", result)  # Excluded column = "Yes"

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_employer_share_always_zero_in_csv(self, mock_frappe):
        mock_frappe.db.sql.return_value = [
            {
                "slip_name": "SAL-003",
                "employee": "EMP-003",
                "employee_name": "Lee Wei Ming",
                "gross_pay": 4000.0,
                "custom_icpassport_number": "880303034321",
                "custom_is_domestic_gig_exempt": 0,
            }
        ]
        result = self.generate("Test Co", 2026, 3)
        # RM4,000 × 2% = RM80.00; employer = 0.00
        self.assertIn("80.00", result)
        self.assertIn("0.00", result)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_csv_has_total_footer(self, mock_frappe):
        mock_frappe.db.sql.return_value = [
            {
                "slip_name": "SAL-004",
                "employee": "EMP-004",
                "employee_name": "Kumar a/l Rajan",
                "gross_pay": 2000.0,
                "custom_icpassport_number": "910404044321",
                "custom_is_domestic_gig_exempt": 0,
            }
        ]
        result = self.generate("Test Co", 2026, 3)
        self.assertIn("TOTAL SEIA", result)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.gig_worker_socso_service.frappe")
    def test_empty_result_when_no_slips(self, mock_frappe):
        mock_frappe.db.sql.return_value = []
        result = self.generate("Test Co", 2026, 3)
        # Should still return header + total
        self.assertIn("NRIC", result)
        self.assertIn("TOTAL SEIA", result)
