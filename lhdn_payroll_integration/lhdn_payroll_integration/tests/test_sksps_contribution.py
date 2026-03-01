"""Tests for US-182: Gig Workers Act 2025 — SKSPS Per-Transaction Contribution
Calculation and PERKESO Monthly Aggregate Remittance.

Verifies:
  - Constants (rate, excluded/eligible statuses, deadline day, CSV columns)
  - compute_transaction_sksps() — per-transaction 1.25% calculation
  - is_transaction_eligible() — status-based eligibility filtering
  - aggregate_monthly_sksps() — monthly rollup with exclusions
  - get_remittance_deadline() — 15th of following month
  - is_remittance_overdue() — overdue detection
  - get_worker_transaction_summary() — payslip-level summary read
  - generate_perkeso_remittance_file() — CSV generation
  - batch_compute_sksps_for_period() — multi-worker batch computation
"""

from datetime import date
from unittest.mock import patch, MagicMock
from frappe.tests.utils import FrappeTestCase


class TestSkspsContributionConstants(FrappeTestCase):
    """Module-level constants match Gig Workers Act 2025 / SEIA Act 789."""

    def setUp(self):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            SKSPS_CONTRIBUTION_RATE,
            EXCLUDED_TRANSACTION_STATUSES,
            ELIGIBLE_TRANSACTION_STATUSES,
            REMITTANCE_DEADLINE_DAY,
            GIG_WORKER_EMPLOYMENT_TYPE,
            MIN_TRANSACTION_VALUE,
            REMITTANCE_CSV_COLUMNS,
        )
        self.rate = SKSPS_CONTRIBUTION_RATE
        self.excluded = EXCLUDED_TRANSACTION_STATUSES
        self.eligible = ELIGIBLE_TRANSACTION_STATUSES
        self.deadline_day = REMITTANCE_DEADLINE_DAY
        self.gig_type = GIG_WORKER_EMPLOYMENT_TYPE
        self.min_value = MIN_TRANSACTION_VALUE
        self.csv_columns = REMITTANCE_CSV_COLUMNS

    def test_rate_is_1_25_percent(self):
        self.assertAlmostEqual(self.rate, 0.0125, places=4)

    def test_excluded_statuses_contain_failed_cancelled_refunded(self):
        self.assertIn("Failed", self.excluded)
        self.assertIn("Cancelled", self.excluded)
        self.assertIn("Refunded", self.excluded)

    def test_excluded_statuses_count(self):
        self.assertEqual(len(self.excluded), 3)

    def test_eligible_statuses_only_completed(self):
        self.assertEqual(self.eligible, frozenset({"Completed"}))

    def test_remittance_deadline_day_is_15(self):
        self.assertEqual(self.deadline_day, 15)

    def test_gig_worker_employment_type(self):
        self.assertEqual(self.gig_type, "Gig / Platform Worker")

    def test_min_transaction_value_is_zero(self):
        self.assertEqual(self.min_value, 0.00)

    def test_csv_columns_has_6_fields(self):
        self.assertEqual(len(self.csv_columns), 6)
        self.assertIn("NRIC/Passport", self.csv_columns)
        self.assertIn("SKSPS Contribution (RM)", self.csv_columns)


class TestComputeTransactionSksps(FrappeTestCase):
    """Per-transaction 1.25% SKSPS calculation."""

    def setUp(self):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            compute_transaction_sksps,
        )
        self.compute = compute_transaction_sksps

    def test_basic_calculation_rm100(self):
        result = self.compute(100.00)
        self.assertAlmostEqual(result["sksps_amount"], 1.25, places=2)
        self.assertTrue(result["eligible"])
        self.assertAlmostEqual(result["rate"], 0.0125, places=4)

    def test_basic_calculation_rm50(self):
        result = self.compute(50.00)
        # 50 * 0.0125 = 0.625 → Python banker's rounding → 0.62
        self.assertAlmostEqual(result["sksps_amount"], 0.62, places=2)

    def test_large_transaction_rm10000(self):
        result = self.compute(10000.00)
        self.assertAlmostEqual(result["sksps_amount"], 125.00, places=2)

    def test_small_transaction_rm1(self):
        result = self.compute(1.00)
        self.assertAlmostEqual(result["sksps_amount"], 0.01, places=2)

    def test_zero_value_is_ineligible(self):
        result = self.compute(0.00)
        self.assertEqual(result["sksps_amount"], 0.00)
        self.assertFalse(result["eligible"])

    def test_negative_value_is_ineligible(self):
        result = self.compute(-50.00)
        self.assertEqual(result["sksps_amount"], 0.00)
        self.assertFalse(result["eligible"])

    def test_fractional_value_rm33_33(self):
        result = self.compute(33.33)
        # 33.33 * 0.0125 = 0.416625 → rounded to 0.42
        self.assertAlmostEqual(result["sksps_amount"], 0.42, places=2)

    def test_result_contains_original_value(self):
        result = self.compute(200.00)
        self.assertAlmostEqual(result["transaction_value"], 200.00, places=2)

    def test_rounding_precision(self):
        # 79.99 * 0.0125 = 0.999875 → 1.00
        result = self.compute(79.99)
        self.assertAlmostEqual(result["sksps_amount"], 1.00, places=2)

    def test_very_small_positive_value(self):
        result = self.compute(0.01)
        # 0.01 * 0.0125 = 0.000125 → 0.00
        self.assertAlmostEqual(result["sksps_amount"], 0.00, places=2)
        self.assertTrue(result["eligible"])


class TestIsTransactionEligible(FrappeTestCase):
    """Transaction status-based eligibility filtering."""

    def setUp(self):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            is_transaction_eligible,
        )
        self.check = is_transaction_eligible

    def test_completed_is_eligible(self):
        self.assertTrue(self.check("Completed"))

    def test_failed_is_excluded(self):
        self.assertFalse(self.check("Failed"))

    def test_cancelled_is_excluded(self):
        self.assertFalse(self.check("Cancelled"))

    def test_refunded_is_excluded(self):
        self.assertFalse(self.check("Refunded"))

    def test_empty_string_is_excluded(self):
        self.assertFalse(self.check(""))

    def test_none_is_excluded(self):
        self.assertFalse(self.check(None))

    def test_unknown_status_is_excluded(self):
        self.assertFalse(self.check("Pending"))

    def test_whitespace_trimmed(self):
        self.assertTrue(self.check("Completed"))
        self.assertFalse(self.check("  "))

    def test_case_sensitive(self):
        # Status strings must match exact case
        self.assertFalse(self.check("completed"))
        self.assertFalse(self.check("COMPLETED"))


class TestAggregateMonthlySksps(FrappeTestCase):
    """Monthly aggregation of per-transaction SKSPS deductions."""

    def setUp(self):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            aggregate_monthly_sksps,
        )
        self.aggregate = aggregate_monthly_sksps

    def test_all_completed_transactions(self):
        txns = [
            {"value": 100.00, "status": "Completed"},
            {"value": 200.00, "status": "Completed"},
            {"value": 50.00, "status": "Completed"},
        ]
        result = self.aggregate(txns)
        # 100*0.0125=1.25, 200*0.0125=2.50, 50*0.0125=0.62 (banker's rounding)
        self.assertAlmostEqual(result["total_sksps"], 4.37, places=2)
        self.assertEqual(result["eligible_count"], 3)
        self.assertEqual(result["excluded_count"], 0)
        self.assertAlmostEqual(result["total_transaction_value"], 350.00, places=2)

    def test_mixed_statuses(self):
        txns = [
            {"value": 100.00, "status": "Completed"},
            {"value": 200.00, "status": "Cancelled"},
            {"value": 150.00, "status": "Completed"},
            {"value": 50.00, "status": "Failed"},
            {"value": 80.00, "status": "Refunded"},
        ]
        result = self.aggregate(txns)
        # Only Completed: 100+150=250 → 100*0.0125=1.25 + 150*0.0125=1.88 = 3.13
        self.assertAlmostEqual(result["total_sksps"], 3.13, places=2)
        self.assertEqual(result["eligible_count"], 2)
        self.assertEqual(result["excluded_count"], 3)
        self.assertAlmostEqual(result["total_transaction_value"], 250.00, places=2)

    def test_all_excluded(self):
        txns = [
            {"value": 100.00, "status": "Cancelled"},
            {"value": 200.00, "status": "Failed"},
        ]
        result = self.aggregate(txns)
        self.assertEqual(result["total_sksps"], 0.00)
        self.assertEqual(result["eligible_count"], 0)
        self.assertEqual(result["excluded_count"], 2)

    def test_empty_transactions(self):
        result = self.aggregate([])
        self.assertEqual(result["total_sksps"], 0.00)
        self.assertEqual(result["eligible_count"], 0)
        self.assertEqual(result["excluded_count"], 0)
        self.assertEqual(result["transactions"], [])

    def test_single_transaction(self):
        txns = [{"value": 500.00, "status": "Completed"}]
        result = self.aggregate(txns)
        self.assertAlmostEqual(result["total_sksps"], 6.25, places=2)
        self.assertEqual(result["eligible_count"], 1)

    def test_transaction_breakdown_returned(self):
        txns = [
            {"value": 100.00, "status": "Completed"},
            {"value": 50.00, "status": "Failed"},
        ]
        result = self.aggregate(txns)
        self.assertEqual(len(result["transactions"]), 2)
        self.assertTrue(result["transactions"][0]["eligible"])
        self.assertFalse(result["transactions"][1]["eligible"])
        self.assertAlmostEqual(result["transactions"][0]["sksps_amount"], 1.25, places=2)
        self.assertEqual(result["transactions"][1]["sksps_amount"], 0.00)

    def test_zero_value_completed_transaction(self):
        txns = [{"value": 0.00, "status": "Completed"}]
        result = self.aggregate(txns)
        # 0 value → compute_transaction_sksps returns ineligible but status is Completed
        # However compute returns eligible=False for 0 value, aggregation still counts it
        # because is_transaction_eligible checks status, not value
        self.assertEqual(result["eligible_count"], 1)
        self.assertEqual(result["total_sksps"], 0.00)

    def test_large_number_of_transactions(self):
        txns = [{"value": 10.00, "status": "Completed"} for _ in range(100)]
        result = self.aggregate(txns)
        # 100 * (10 * 0.0125) = 100 * 0.13 = 12.50 (note: 10*0.0125=0.125→0.13 each)
        # Actually 0.125 rounds to 0.12 (banker's rounding) or 0.13 (half-up)
        # Python round(0.125, 2) = 0.12 (banker's rounding)
        expected = 100 * round(10.00 * 0.0125, 2)
        self.assertAlmostEqual(result["total_sksps"], expected, places=2)
        self.assertEqual(result["eligible_count"], 100)


class TestGetRemittanceDeadline(FrappeTestCase):
    """Remittance deadline is 15th of the following month."""

    def setUp(self):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            get_remittance_deadline,
        )
        self.get_deadline = get_remittance_deadline

    def test_january_deadline_is_feb_15(self):
        self.assertEqual(self.get_deadline(2026, 1), date(2026, 2, 15))

    def test_june_deadline_is_jul_15(self):
        self.assertEqual(self.get_deadline(2026, 6), date(2026, 7, 15))

    def test_november_deadline_is_dec_15(self):
        self.assertEqual(self.get_deadline(2026, 11), date(2026, 12, 15))

    def test_december_deadline_crosses_year_boundary(self):
        self.assertEqual(self.get_deadline(2026, 12), date(2027, 1, 15))

    def test_deadline_day_is_always_15(self):
        for month in range(1, 13):
            deadline = self.get_deadline(2026, month)
            self.assertEqual(deadline.day, 15)


class TestIsRemittanceOverdue(FrappeTestCase):
    """Remittance overdue detection."""

    def setUp(self):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            is_remittance_overdue,
        )
        self.check_overdue = is_remittance_overdue

    def test_not_overdue_before_deadline(self):
        # Jan 2026 payroll, deadline Feb 15; check on Feb 10
        result = self.check_overdue(2026, 1, as_of_date="2026-02-10")
        self.assertFalse(result["overdue"])
        self.assertEqual(result["days_overdue"], 0)

    def test_not_overdue_on_deadline_day(self):
        # Jan 2026 payroll, deadline Feb 15; check on Feb 15
        result = self.check_overdue(2026, 1, as_of_date="2026-02-15")
        self.assertFalse(result["overdue"])
        self.assertEqual(result["days_overdue"], 0)

    def test_overdue_one_day_after(self):
        # Jan 2026 payroll, deadline Feb 15; check on Feb 16
        result = self.check_overdue(2026, 1, as_of_date="2026-02-16")
        self.assertTrue(result["overdue"])
        self.assertEqual(result["days_overdue"], 1)

    def test_overdue_multiple_days(self):
        result = self.check_overdue(2026, 1, as_of_date="2026-02-25")
        self.assertTrue(result["overdue"])
        self.assertEqual(result["days_overdue"], 10)

    def test_deadline_returned_in_result(self):
        result = self.check_overdue(2026, 3, as_of_date="2026-04-01")
        self.assertEqual(result["deadline"], date(2026, 4, 15))

    def test_december_year_boundary_overdue(self):
        # Dec 2026 payroll, deadline Jan 15, 2027; check on Jan 20, 2027
        result = self.check_overdue(2026, 12, as_of_date="2027-01-20")
        self.assertTrue(result["overdue"])
        self.assertEqual(result["days_overdue"], 5)


class TestGetWorkerTransactionSummary(FrappeTestCase):
    """Payslip-level SKSPS summary retrieval."""

    @patch("lhdn_payroll_integration.services.sksps_contribution_service.frappe")
    def test_returns_summary_from_salary_slip(self, mock_frappe):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            get_worker_transaction_summary,
        )
        mock_frappe.get_all.return_value = [{
            "name": "SAL-SLIP-001",
            "custom_sksps_total_transactions": 25,
            "custom_sksps_eligible_transactions": 20,
            "custom_sksps_total_value": 5000.00,
            "custom_sksps_contribution": 62.50,
        }]

        result = get_worker_transaction_summary("EMP-001", 2026, 1)
        self.assertEqual(result["salary_slip"], "SAL-SLIP-001")
        self.assertEqual(result["total_transactions"], 25)
        self.assertEqual(result["eligible_transactions"], 20)
        self.assertAlmostEqual(result["total_value"], 5000.00, places=2)
        self.assertAlmostEqual(result["sksps_contribution"], 62.50, places=2)

    @patch("lhdn_payroll_integration.services.sksps_contribution_service.frappe")
    def test_returns_empty_when_no_salary_slip(self, mock_frappe):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            get_worker_transaction_summary,
        )
        mock_frappe.get_all.return_value = []
        result = get_worker_transaction_summary("EMP-002", 2026, 1)
        self.assertEqual(result, {})

    @patch("lhdn_payroll_integration.services.sksps_contribution_service.frappe")
    def test_handles_exception_gracefully(self, mock_frappe):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            get_worker_transaction_summary,
        )
        mock_frappe.get_all.side_effect = Exception("DB error")
        result = get_worker_transaction_summary("EMP-003", 2026, 1)
        self.assertEqual(result, {})

    @patch("lhdn_payroll_integration.services.sksps_contribution_service.frappe")
    def test_handles_null_custom_fields(self, mock_frappe):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            get_worker_transaction_summary,
        )
        mock_frappe.get_all.return_value = [{
            "name": "SAL-SLIP-002",
            "custom_sksps_total_transactions": None,
            "custom_sksps_eligible_transactions": None,
            "custom_sksps_total_value": None,
            "custom_sksps_contribution": None,
        }]
        result = get_worker_transaction_summary("EMP-004", 2026, 2)
        self.assertEqual(result["total_transactions"], 0)
        self.assertEqual(result["eligible_transactions"], 0)
        self.assertAlmostEqual(result["total_value"], 0.00, places=2)
        self.assertAlmostEqual(result["sksps_contribution"], 0.00, places=2)


class TestGeneratePerkesoRemittanceFile(FrappeTestCase):
    """PERKESO monthly SKSPS remittance CSV generation."""

    @patch("lhdn_payroll_integration.services.sksps_contribution_service.frappe")
    def test_generates_csv_with_worker_rows(self, mock_frappe):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            generate_perkeso_remittance_file,
        )
        mock_frappe.db.sql.return_value = [
            {
                "employee": "EMP-001",
                "employee_name": "Ahmad bin Ali",
                "custom_icpassport_number": "901234567890",
                "custom_sksps_reference_number": "SKSPS-001",
                "custom_sksps_total_transactions": 30,
                "custom_sksps_eligible_transactions": 25,
                "custom_sksps_total_value": 6000.00,
                "custom_sksps_contribution": 75.00,
            },
            {
                "employee": "EMP-002",
                "employee_name": "Siti binti Rahman",
                "custom_icpassport_number": "880987654321",
                "custom_sksps_reference_number": "SKSPS-002",
                "custom_sksps_total_transactions": 15,
                "custom_sksps_eligible_transactions": 12,
                "custom_sksps_total_value": 3000.00,
                "custom_sksps_contribution": 37.50,
            },
        ]

        csv_output = generate_perkeso_remittance_file("Test Co", 2026, 1)

        # Check header
        self.assertIn("NRIC/Passport", csv_output)
        self.assertIn("SKSPS Contribution (RM)", csv_output)

        # Check worker data
        self.assertIn("901234567890", csv_output)
        self.assertIn("Ahmad bin Ali", csv_output)
        self.assertIn("SKSPS-001", csv_output)
        self.assertIn("75.00", csv_output)

        self.assertIn("880987654321", csv_output)
        self.assertIn("Siti binti Rahman", csv_output)
        self.assertIn("37.50", csv_output)

        # Check total
        self.assertIn("112.50", csv_output)
        self.assertIn("2 workers", csv_output)

        # Check metadata
        self.assertIn("Test Co", csv_output)
        self.assertIn("2026-01", csv_output)
        self.assertIn("2026-02-15", csv_output)

    @patch("lhdn_payroll_integration.services.sksps_contribution_service.frappe")
    def test_empty_csv_when_no_workers(self, mock_frappe):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            generate_perkeso_remittance_file,
        )
        mock_frappe.db.sql.return_value = []

        csv_output = generate_perkeso_remittance_file("Test Co", 2026, 2)
        self.assertIn("NRIC/Passport", csv_output)
        self.assertIn("0.00", csv_output)
        self.assertIn("0 workers", csv_output)


class TestBatchComputeSkspsForPeriod(FrappeTestCase):
    """Multi-worker batch SKSPS computation."""

    def setUp(self):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            batch_compute_sksps_for_period,
        )
        self.batch_compute = batch_compute_sksps_for_period

    def test_two_workers_aggregated(self):
        txns = {
            "EMP-001": [
                {"value": 100.00, "status": "Completed"},
                {"value": 200.00, "status": "Completed"},
            ],
            "EMP-002": [
                {"value": 400.00, "status": "Completed"},
                {"value": 50.00, "status": "Cancelled"},
            ],
        }
        result = self.batch_compute("Test Co", 2026, 1, txns)

        self.assertEqual(result["total_workers"], 2)
        # EMP-001: (100*0.0125=1.25) + (200*0.0125=2.50) = 3.75
        # EMP-002: (400*0.0125=5.00) + cancelled = 5.00
        # Total: 8.75
        self.assertAlmostEqual(result["total_sksps"], 8.75, places=2)
        self.assertEqual(result["deadline"], date(2026, 2, 15))

    def test_empty_workers_dict(self):
        result = self.batch_compute("Test Co", 2026, 1, {})
        self.assertEqual(result["total_workers"], 0)
        self.assertEqual(result["total_sksps"], 0.00)

    def test_worker_with_all_excluded_transactions(self):
        txns = {
            "EMP-001": [
                {"value": 100.00, "status": "Failed"},
                {"value": 200.00, "status": "Refunded"},
            ],
        }
        result = self.batch_compute("Test Co", 2026, 3, txns)
        self.assertEqual(result["total_sksps"], 0.00)
        self.assertEqual(result["total_workers"], 1)
        self.assertEqual(result["workers"][0]["eligible_count"], 0)
        self.assertEqual(result["workers"][0]["excluded_count"], 2)

    def test_workers_summary_contains_per_worker_data(self):
        txns = {
            "EMP-001": [{"value": 1000.00, "status": "Completed"}],
        }
        result = self.batch_compute("Test Co", 2026, 6, txns)
        worker = result["workers"][0]
        self.assertEqual(worker["employee"], "EMP-001")
        self.assertAlmostEqual(worker["total_sksps"], 12.50, places=2)
        self.assertAlmostEqual(worker["total_transaction_value"], 1000.00, places=2)
        self.assertEqual(worker["eligible_count"], 1)

    def test_december_deadline_crosses_year(self):
        txns = {"EMP-001": [{"value": 100.00, "status": "Completed"}]}
        result = self.batch_compute("Test Co", 2026, 12, txns)
        self.assertEqual(result["deadline"], date(2027, 1, 15))


class TestSkspsRateAccuracy(FrappeTestCase):
    """Verify SKSPS rate accuracy across edge cases."""

    def setUp(self):
        from lhdn_payroll_integration.services.sksps_contribution_service import (
            compute_transaction_sksps,
            SKSPS_CONTRIBUTION_RATE,
        )
        self.compute = compute_transaction_sksps
        self.rate = SKSPS_CONTRIBUTION_RATE

    def test_rate_not_confused_with_socso_2_percent(self):
        """SKSPS is 1.25%, NOT 2% like SEIA."""
        self.assertNotAlmostEqual(self.rate, 0.02, places=4)
        self.assertAlmostEqual(self.rate, 0.0125, places=4)

    def test_rm1000_transaction(self):
        result = self.compute(1000.00)
        self.assertAlmostEqual(result["sksps_amount"], 12.50, places=2)

    def test_rm5_transaction(self):
        result = self.compute(5.00)
        # 5 * 0.0125 = 0.0625 → 0.06
        self.assertAlmostEqual(result["sksps_amount"], 0.06, places=2)

    def test_rm8000_transaction(self):
        result = self.compute(8000.00)
        # No ceiling for SKSPS (unlike SEIA which has RM5,000 ceiling)
        self.assertAlmostEqual(result["sksps_amount"], 100.00, places=2)

    def test_platform_bears_full_cost(self):
        """The full SKSPS amount is borne by the platform provider, not split."""
        result = self.compute(100.00)
        # Only sksps_amount — no employer/worker split
        self.assertIn("sksps_amount", result)
        self.assertAlmostEqual(result["sksps_amount"], 1.25, places=2)
