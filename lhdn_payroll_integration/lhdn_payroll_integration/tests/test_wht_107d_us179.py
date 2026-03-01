"""Tests for Section 107D ITA WHT 2% Service — US-179.

Section 107D of the Income Tax Act 1967 requires payers to deduct 2% WHT
from monetary and non-monetary incentive payments to agents, dealers, or
distributors whose cumulative annual payments exceed RM5,000.

Test classes:
  1. TestWhtThreshold              — WHT computed only when cumulative > RM5,000
  2. TestRecipientClassification   — only Agent/Dealer/Distributor subject to WHT
  3. TestMonthlyRemittanceSchedule — schedule generation, deadline, breakdown
  4. TestNonMonetaryPaymentTracking — non-monetary incentives at cost
  5. TestCP58Integration           — WHT linked to CP58 annual reporting
  6. TestLatePaymentPenalty        — 10% late penalty calculation
  7. TestAnnualAccumulation        — multiple payments accumulate correctly
"""

from datetime import date
from decimal import Decimal

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.wht_107d_service import (
    APPLICABLE_RECIPIENT_TYPES,
    LATE_PENALTY_RATE,
    WHT_ANNUAL_THRESHOLD,
    WHT_RATE,
    accumulate_annual_payments,
    build_cp58_wht_summary,
    compute_late_penalty,
    compute_payment_type_value,
    compute_wht_amount,
    compute_wht_for_payment,
    generate_monthly_remittance_schedule,
    get_cp58_issuance_deadline,
    get_remittance_deadline,
    is_wht_threshold_exceeded,
)


class TestWhtThreshold(FrappeTestCase):
    """AC2: 2% WHT computed only when cumulative payments exceed RM5,000."""

    def test_no_wht_when_below_threshold(self):
        """No WHT when cumulative total remains below RM5,000."""
        result = compute_wht_for_payment(
            annual_total_before=Decimal("2000.00"),
            payment_amount=Decimal("1000.00"),
            recipient_type="Agent",
        )
        self.assertFalse(result["wht_applicable"])
        self.assertEqual(result["wht_amount"], Decimal("0.00"))

    def test_no_wht_when_cumulative_reaches_exactly_5000(self):
        """No WHT when cumulative total equals exactly RM5,000 (threshold is strict >)."""
        result = compute_wht_for_payment(
            annual_total_before=Decimal("4000.00"),
            payment_amount=Decimal("1000.00"),
            recipient_type="Dealer",
        )
        self.assertFalse(result["wht_applicable"])
        self.assertEqual(result["wht_amount"], Decimal("0.00"))
        self.assertEqual(result["new_annual_total"], Decimal("5000.00"))

    def test_wht_triggered_when_payment_crosses_threshold(self):
        """WHT on the taxable portion when a payment crosses the RM5,000 threshold."""
        # Cumulative was RM4,500; payment RM1,000 → new total RM5,500
        # Taxable portion above threshold = RM5,500 - RM5,000 = RM500
        result = compute_wht_for_payment(
            annual_total_before=Decimal("4500.00"),
            payment_amount=Decimal("1000.00"),
            recipient_type="Agent",
        )
        self.assertTrue(result["wht_applicable"])
        expected_wht = (Decimal("500.00") * WHT_RATE).quantize(Decimal("0.01"))
        self.assertEqual(result["wht_amount"], expected_wht)

    def test_full_wht_when_cumulative_already_exceeded(self):
        """Full 2% WHT on the entire payment when cumulative already exceeds RM5,000."""
        result = compute_wht_for_payment(
            annual_total_before=Decimal("6000.00"),
            payment_amount=Decimal("2000.00"),
            recipient_type="Agent",
        )
        self.assertTrue(result["wht_applicable"])
        self.assertEqual(result["wht_amount"], Decimal("40.00"))  # 2% of RM2,000

    def test_wht_rate_constant_is_2_percent(self):
        """WHT_RATE constant is exactly 0.02 (2%)."""
        self.assertEqual(WHT_RATE, Decimal("0.02"))

    def test_threshold_constant_is_5000(self):
        """WHT_ANNUAL_THRESHOLD constant is RM5,000."""
        self.assertEqual(WHT_ANNUAL_THRESHOLD, Decimal("5000.00"))

    def test_new_annual_total_updated_correctly(self):
        """new_annual_total in result reflects cumulative total after this payment."""
        result = compute_wht_for_payment(
            annual_total_before=Decimal("3000.00"),
            payment_amount=Decimal("1500.00"),
            recipient_type="Distributor",
        )
        self.assertEqual(result["new_annual_total"], Decimal("4500.00"))

    def test_is_wht_threshold_exceeded_returns_true_above_5000(self):
        """is_wht_threshold_exceeded returns True when total > RM5,000."""
        self.assertTrue(is_wht_threshold_exceeded(Decimal("5001.00")))

    def test_is_wht_threshold_exceeded_returns_false_at_5000(self):
        """is_wht_threshold_exceeded returns False when total == RM5,000 (strict >)."""
        self.assertFalse(is_wht_threshold_exceeded(Decimal("5000.00")))

    def test_is_wht_threshold_exceeded_returns_false_below_5000(self):
        """is_wht_threshold_exceeded returns False when total < RM5,000."""
        self.assertFalse(is_wht_threshold_exceeded(Decimal("4999.99")))


class TestRecipientClassification(FrappeTestCase):
    """AC1: Only Agent/Dealer/Distributor recipients are subject to Section 107D WHT."""

    def test_agent_type_attracts_wht(self):
        """Payments classified as Agent are subject to WHT."""
        result = compute_wht_for_payment(
            annual_total_before=Decimal("6000.00"),
            payment_amount=Decimal("1000.00"),
            recipient_type="Agent",
        )
        self.assertTrue(result["wht_applicable"])

    def test_dealer_type_attracts_wht(self):
        """Payments classified as Dealer are subject to WHT."""
        result = compute_wht_for_payment(
            annual_total_before=Decimal("6000.00"),
            payment_amount=Decimal("1000.00"),
            recipient_type="Dealer",
        )
        self.assertTrue(result["wht_applicable"])

    def test_distributor_type_attracts_wht(self):
        """Payments classified as Distributor are subject to WHT."""
        result = compute_wht_for_payment(
            annual_total_before=Decimal("6000.00"),
            payment_amount=Decimal("1000.00"),
            recipient_type="Distributor",
        )
        self.assertTrue(result["wht_applicable"])

    def test_employee_type_not_subject_to_wht(self):
        """Employee payments are NOT subject to Section 107D WHT."""
        result = compute_wht_for_payment(
            annual_total_before=Decimal("10000.00"),
            payment_amount=Decimal("1000.00"),
            recipient_type="Employee",
        )
        self.assertFalse(result["wht_applicable"])
        self.assertEqual(result["wht_amount"], Decimal("0.00"))

    def test_supplier_type_not_subject_to_wht(self):
        """Supplier payments are NOT subject to Section 107D WHT."""
        result = compute_wht_for_payment(
            annual_total_before=Decimal("10000.00"),
            payment_amount=Decimal("1000.00"),
            recipient_type="Supplier",
        )
        self.assertFalse(result["wht_applicable"])

    def test_applicable_recipient_types_constant(self):
        """APPLICABLE_RECIPIENT_TYPES contains exactly Agent, Dealer, Distributor."""
        self.assertEqual(APPLICABLE_RECIPIENT_TYPES, {"Agent", "Dealer", "Distributor"})


class TestMonthlyRemittanceSchedule(FrappeTestCase):
    """AC3: Monthly WHT remittance schedule generated per company with deadline and breakdown."""

    def test_remittance_deadline_is_15th_of_following_month(self):
        """WHT deducted in January must be remitted by 15 February."""
        deadline = get_remittance_deadline(2025, 1)
        self.assertEqual(deadline, date(2025, 2, 15))

    def test_remittance_deadline_december_rolls_to_january_next_year(self):
        """WHT deducted in December must be remitted by 15 January of the following year."""
        deadline = get_remittance_deadline(2025, 12)
        self.assertEqual(deadline, date(2026, 1, 15))

    def test_remittance_deadline_november(self):
        """WHT deducted in November must be remitted by 15 December of the same year."""
        deadline = get_remittance_deadline(2025, 11)
        self.assertEqual(deadline, date(2025, 12, 15))

    def test_schedule_returns_dict(self):
        """generate_monthly_remittance_schedule returns a dictionary."""
        schedule = generate_monthly_remittance_schedule([], "Test Company", 2025, 3)
        self.assertIsInstance(schedule, dict)

    def test_schedule_has_correct_company_field(self):
        """Schedule dict 'company' field matches the input company name."""
        schedule = generate_monthly_remittance_schedule(
            [], "Prisma Technology Sdn Bhd", 2025, 3
        )
        self.assertEqual(schedule["company"], "Prisma Technology Sdn Bhd")

    def test_schedule_total_wht_payable_sums_all_records(self):
        """Schedule 'total_wht_payable' is the sum of all recipient WHT amounts."""
        records = [
            {"recipient_name": "Ali Agent", "recipient_tin": "A111", "wht_amount": Decimal("40.00")},
            {"recipient_name": "Bala Dealer", "recipient_tin": "B222", "wht_amount": Decimal("60.00")},
        ]
        schedule = generate_monthly_remittance_schedule(records, "My Company", 2025, 5)
        self.assertEqual(schedule["total_wht_payable"], Decimal("100.00"))

    def test_schedule_has_recipient_breakdown_list(self):
        """Schedule includes per-recipient breakdown as a list."""
        records = [
            {"recipient_name": "Ali Agent", "recipient_tin": "A111", "wht_amount": Decimal("40.00")},
        ]
        schedule = generate_monthly_remittance_schedule(records, "My Company", 2025, 5)
        self.assertIn("recipient_breakdown", schedule)
        self.assertEqual(len(schedule["recipient_breakdown"]), 1)
        self.assertEqual(schedule["recipient_breakdown"][0]["recipient_name"], "Ali Agent")

    def test_schedule_empty_records_gives_zero_total(self):
        """Empty WHT records produces total_wht_payable of zero."""
        schedule = generate_monthly_remittance_schedule([], "My Company", 2025, 5)
        self.assertEqual(schedule["total_wht_payable"], Decimal("0.00"))

    def test_schedule_includes_remittance_deadline(self):
        """Schedule includes the remittance_deadline as a date object."""
        schedule = generate_monthly_remittance_schedule([], "My Company", 2025, 6)
        self.assertEqual(schedule["remittance_deadline"], date(2025, 7, 15))

    def test_schedule_records_year_and_month(self):
        """Schedule records the year and month of WHT deduction."""
        schedule = generate_monthly_remittance_schedule([], "My Company", 2025, 8)
        self.assertEqual(schedule["year"], 2025)
        self.assertEqual(schedule["month"], 8)


class TestNonMonetaryPaymentTracking(FrappeTestCase):
    """AC6: Non-monetary incentive values (vehicles, property) tracked at cost incurred by payer."""

    def test_monetary_payment_type_accepted(self):
        """'monetary' payment_type is valid and returns correct Decimal value."""
        val = compute_payment_type_value(5000.0, "monetary")
        self.assertEqual(val, Decimal("5000.00"))

    def test_non_monetary_payment_type_accepted(self):
        """'non_monetary' payment_type is valid (cost-at-payer basis)."""
        val = compute_payment_type_value(25000.0, "non_monetary")
        self.assertEqual(val, Decimal("25000.00"))

    def test_invalid_payment_type_raises_value_error(self):
        """Invalid payment_type raises ValueError."""
        with self.assertRaises(ValueError):
            compute_payment_type_value(1000.0, "gift_voucher")

    def test_non_monetary_vehicle_value_subject_to_wht(self):
        """Non-monetary vehicle cost (RM30,000) is included in WHT base calculation."""
        # Payer gives a car worth RM30,000 to an agent whose cumulative already > RM5,000
        result = compute_wht_for_payment(
            annual_total_before=Decimal("8000.00"),
            payment_amount=Decimal("30000.00"),
            recipient_type="Agent",
        )
        self.assertTrue(result["wht_applicable"])
        self.assertEqual(result["wht_amount"], Decimal("600.00"))  # 2% of RM30,000

    def test_wht_calculation_identical_for_monetary_and_non_monetary(self):
        """WHT calculation is the same for monetary and non-monetary at same amount."""
        result_a = compute_wht_for_payment(Decimal("6000.00"), Decimal("1000.00"), "Agent")
        result_b = compute_wht_for_payment(Decimal("6000.00"), Decimal("1000.00"), "Agent")
        self.assertEqual(result_a["wht_amount"], result_b["wht_amount"])


class TestCP58Integration(FrappeTestCase):
    """AC4 & AC5: WHT amounts linked to CP58; LHDN payment reference tracked annually."""

    def test_cp58_issuance_deadline_is_31_march_following_year(self):
        """CP58 must be issued to recipients by 31 March of the year following assessment year."""
        deadline = get_cp58_issuance_deadline(2025)
        self.assertEqual(deadline, date(2026, 3, 31))

    def test_cp58_issuance_deadline_year_2024(self):
        """CP58 for assessment year 2024 is due 31 March 2025."""
        deadline = get_cp58_issuance_deadline(2024)
        self.assertEqual(deadline, date(2025, 3, 31))

    def test_build_cp58_wht_summary_returns_dict(self):
        """build_cp58_wht_summary returns a dictionary."""
        summary = build_cp58_wht_summary("TIN-123", 2025, [])
        self.assertIsInstance(summary, dict)

    def test_build_cp58_wht_summary_sums_total_wht(self):
        """build_cp58_wht_summary correctly sums all WHT amounts for the year."""
        records = [
            {"wht_amount": Decimal("40.00")},
            {"wht_amount": Decimal("60.00")},
            {"wht_amount": Decimal("20.00")},
        ]
        summary = build_cp58_wht_summary("TIN-123", 2025, records)
        self.assertEqual(summary["total_wht"], Decimal("120.00"))

    def test_build_cp58_wht_summary_counts_records(self):
        """build_cp58_wht_summary counts the number of WHT records."""
        records = [{"wht_amount": Decimal("40.00")}] * 3
        summary = build_cp58_wht_summary("TIN-456", 2025, records)
        self.assertEqual(summary["record_count"], 3)

    def test_build_cp58_wht_summary_includes_recipient_id(self):
        """Summary includes recipient_id for CP58 linkage."""
        summary = build_cp58_wht_summary("TIN-789", 2025, [])
        self.assertEqual(summary["recipient_id"], "TIN-789")

    def test_build_cp58_wht_summary_includes_cp58_deadline(self):
        """Summary includes CP58 issuance deadline date."""
        summary = build_cp58_wht_summary("TIN-100", 2025, [])
        self.assertEqual(summary["cp58_issuance_deadline"], date(2026, 3, 31))

    def test_build_cp58_wht_summary_zero_total_for_empty_records(self):
        """Empty WHT records produce total_wht of zero."""
        summary = build_cp58_wht_summary("TIN-200", 2025, [])
        self.assertEqual(summary["total_wht"], Decimal("0.00"))


class TestLatePaymentPenalty(FrappeTestCase):
    """AC3: Late WHT remittance attracts 10% penalty (ITA s.107D(3))."""

    def test_late_penalty_rate_constant_is_10_percent(self):
        """LATE_PENALTY_RATE constant is exactly 0.10 (10%)."""
        self.assertEqual(LATE_PENALTY_RATE, Decimal("0.10"))

    def test_compute_late_penalty_is_10_percent_of_wht(self):
        """Late penalty is 10% of the outstanding WHT amount."""
        penalty = compute_late_penalty(Decimal("200.00"))
        self.assertEqual(penalty, Decimal("20.00"))

    def test_compute_late_penalty_rounds_to_sen(self):
        """Late penalty is rounded to 2 decimal places (nearest sen)."""
        penalty = compute_late_penalty(Decimal("333.33"))
        # 10% of 333.33 = 33.333 → rounds to 33.33
        self.assertEqual(penalty, Decimal("33.33"))

    def test_compute_late_penalty_zero_wht_gives_zero(self):
        """Zero WHT amount gives zero late penalty."""
        penalty = compute_late_penalty(Decimal("0.00"))
        self.assertEqual(penalty, Decimal("0.00"))


class TestAnnualAccumulation(FrappeTestCase):
    """AC1: Annual payment accumulation across multiple payments per recipient."""

    def test_accumulate_single_payment(self):
        """Single payment accumulates to its own amount."""
        payments = [{"amount": Decimal("3000.00")}]
        total = accumulate_annual_payments(payments)
        self.assertEqual(total, Decimal("3000.00"))

    def test_accumulate_multiple_payments(self):
        """Multiple payments are summed correctly."""
        payments = [
            {"amount": Decimal("1500.00")},
            {"amount": Decimal("2000.00")},
            {"amount": Decimal("1000.00")},
        ]
        total = accumulate_annual_payments(payments)
        self.assertEqual(total, Decimal("4500.00"))

    def test_accumulate_empty_list_returns_zero(self):
        """Empty payment list returns Decimal zero."""
        total = accumulate_annual_payments([])
        self.assertEqual(total, Decimal("0.00"))

    def test_wht_progression_across_four_sequential_payments(self):
        """Demonstrate WHT progression: first payments below threshold, then WHT kicks in."""
        # Payment 1: RM2,000 → cumulative RM2,000 (no WHT)
        r1 = compute_wht_for_payment(Decimal("0.00"), Decimal("2000.00"), "Agent")
        self.assertFalse(r1["wht_applicable"])
        self.assertEqual(r1["new_annual_total"], Decimal("2000.00"))

        # Payment 2: RM2,500 → cumulative RM4,500 (no WHT, still below RM5,000)
        r2 = compute_wht_for_payment(r1["new_annual_total"], Decimal("2500.00"), "Agent")
        self.assertFalse(r2["wht_applicable"])
        self.assertEqual(r2["new_annual_total"], Decimal("4500.00"))

        # Payment 3: RM1,500 → cumulative RM6,000 (WHT on RM1,000 portion above RM5,000)
        r3 = compute_wht_for_payment(r2["new_annual_total"], Decimal("1500.00"), "Agent")
        self.assertTrue(r3["wht_applicable"])
        expected_wht = Decimal("1000.00") * WHT_RATE  # only the portion above RM5,000
        self.assertEqual(r3["wht_amount"], expected_wht)

        # Payment 4: RM500 → cumulative RM6,500 (full 2% WHT on RM500)
        r4 = compute_wht_for_payment(r3["new_annual_total"], Decimal("500.00"), "Agent")
        self.assertTrue(r4["wht_applicable"])
        self.assertEqual(r4["wht_amount"], Decimal("10.00"))  # 2% of RM500

    def test_compute_wht_amount_rounds_correctly(self):
        """compute_wht_amount rounds to 2 decimal places using ROUND_HALF_UP."""
        wht = compute_wht_amount(Decimal("333.33"))
        # 2% of 333.33 = 6.6666 → rounds to 6.67
        self.assertEqual(wht, Decimal("6.67"))

    def test_running_cumulative_tracks_correctly(self):
        """Annual cumulative total tracks correctly across sequential payments."""
        cumulative = Decimal("0.00")
        payments = [1000, 2000, 1500, 800, 1200]
        for amount in payments:
            result = compute_wht_for_payment(cumulative, Decimal(str(amount)), "Dealer")
            cumulative = result["new_annual_total"]
        self.assertEqual(cumulative, Decimal("6500.00"))
