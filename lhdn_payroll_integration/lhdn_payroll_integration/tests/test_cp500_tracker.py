"""Tests for CP500 Bi-Monthly Advance Tax Installment Tracker Service (US-233).

Covers:
- Constants and configuration values
- Employee CP500 payer flag helpers
- Installment schedule generation
- Next due date and days-until calculations
- Installment record CRUD helpers
- Overdue detection
- Revision deadline helpers
- Payroll advisory note generation
- Upcoming installment dashboard filtering
- Multi-director dashboard summary
- CP500 config validation
"""

import unittest
from datetime import date, timedelta

from lhdn_payroll_integration.services.cp500_tracker_service import (
    CP500_INSTALLMENT_MONTHS,
    CP500_INSTALLMENT_MONTH_NAMES,
    CP500_INSTALLMENT_COUNT,
    CP500_DUE_DAY,
    FIRST_REVISION_DEADLINE_MONTH,
    FIRST_REVISION_DEADLINE_DAY,
    SECOND_REVISION_DEADLINE_MONTH,
    SECOND_REVISION_DEADLINE_DAY,
    UPCOMING_WINDOW_DAYS,
    ADVISORY_NOTE,
    is_cp500_payer,
    get_annual_installment_amount,
    get_per_installment_amount,
    generate_installment_schedule,
    get_next_due_date,
    get_days_until_next_installment,
    create_installment_record,
    mark_installment_paid,
    is_installment_overdue,
    get_revision_deadlines,
    can_revise_cp500,
    get_next_revision_deadline,
    get_payroll_advisory,
    get_upcoming_installments,
    get_overdue_installments,
    get_directors_with_upcoming_cp500,
    get_dashboard_summary,
    validate_cp500_config,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestCP500Constants(unittest.TestCase):
    """Verify module-level constants."""

    def test_installment_months(self):
        self.assertEqual(CP500_INSTALLMENT_MONTHS, [3, 5, 7, 9, 11, 1])

    def test_installment_month_names(self):
        self.assertEqual(len(CP500_INSTALLMENT_MONTH_NAMES), 6)
        self.assertEqual(CP500_INSTALLMENT_MONTH_NAMES[0], "March")
        self.assertEqual(CP500_INSTALLMENT_MONTH_NAMES[5], "January")

    def test_installment_count(self):
        self.assertEqual(CP500_INSTALLMENT_COUNT, 6)

    def test_due_day(self):
        self.assertEqual(CP500_DUE_DAY, 15)

    def test_first_revision_deadline(self):
        self.assertEqual(FIRST_REVISION_DEADLINE_MONTH, 6)
        self.assertEqual(FIRST_REVISION_DEADLINE_DAY, 30)

    def test_second_revision_deadline(self):
        self.assertEqual(SECOND_REVISION_DEADLINE_MONTH, 10)
        self.assertEqual(SECOND_REVISION_DEADLINE_DAY, 31)

    def test_upcoming_window(self):
        self.assertEqual(UPCOMING_WINDOW_DAYS, 30)

    def test_advisory_note_text(self):
        self.assertIn("CP500 obligations", ADVISORY_NOTE)
        self.assertIn("PCB deduction", ADVISORY_NOTE)


# ---------------------------------------------------------------------------
# Employee flag helpers
# ---------------------------------------------------------------------------

class TestIsCp500Payer(unittest.TestCase):
    """Test is_cp500_payer flag check."""

    def test_true_when_set(self):
        self.assertTrue(is_cp500_payer({"cp500_payer": True}))

    def test_true_when_truthy(self):
        self.assertTrue(is_cp500_payer({"cp500_payer": 1}))

    def test_false_when_not_set(self):
        self.assertFalse(is_cp500_payer({}))

    def test_false_when_none(self):
        self.assertFalse(is_cp500_payer({"cp500_payer": None}))

    def test_false_when_zero(self):
        self.assertFalse(is_cp500_payer({"cp500_payer": 0}))

    def test_false_when_false(self):
        self.assertFalse(is_cp500_payer({"cp500_payer": False}))


class TestGetAnnualInstallmentAmount(unittest.TestCase):
    """Test annual installment amount retrieval."""

    def test_returns_amount(self):
        self.assertEqual(
            get_annual_installment_amount({"cp500_annual_installment_amount": 12000}),
            12000.0,
        )

    def test_returns_zero_when_missing(self):
        self.assertEqual(get_annual_installment_amount({}), 0.0)

    def test_returns_zero_when_none(self):
        self.assertEqual(
            get_annual_installment_amount({"cp500_annual_installment_amount": None}),
            0.0,
        )

    def test_returns_float(self):
        result = get_annual_installment_amount({"cp500_annual_installment_amount": 6000})
        self.assertIsInstance(result, float)


class TestGetPerInstallmentAmount(unittest.TestCase):
    """Test per-installment amount calculation."""

    def test_divides_by_six(self):
        emp = {"cp500_annual_installment_amount": 12000}
        self.assertEqual(get_per_installment_amount(emp), 2000.0)

    def test_rounds_to_two_decimals(self):
        emp = {"cp500_annual_installment_amount": 10000}
        result = get_per_installment_amount(emp)
        self.assertEqual(result, round(10000 / 6, 2))

    def test_zero_when_no_amount(self):
        self.assertEqual(get_per_installment_amount({}), 0.0)

    def test_zero_when_negative(self):
        emp = {"cp500_annual_installment_amount": -1000}
        self.assertEqual(get_per_installment_amount(emp), 0.0)


# ---------------------------------------------------------------------------
# Schedule generation
# ---------------------------------------------------------------------------

class TestGenerateInstallmentSchedule(unittest.TestCase):
    """Test installment schedule generation for an assessment year."""

    def test_returns_six_entries(self):
        schedule = generate_installment_schedule(2026)
        self.assertEqual(len(schedule), 6)

    def test_first_entry_is_march(self):
        schedule = generate_installment_schedule(2026)
        self.assertEqual(schedule[0]["installment_month"], 3)
        self.assertEqual(schedule[0]["installment_month_name"], "March")

    def test_last_entry_is_january_next_year(self):
        schedule = generate_installment_schedule(2026)
        self.assertEqual(schedule[5]["installment_month"], 1)
        self.assertEqual(schedule[5]["due_date"], date(2027, 1, 15))

    def test_due_dates_are_15th(self):
        schedule = generate_installment_schedule(2026)
        for entry in schedule:
            self.assertEqual(entry["due_date"].day, 15)

    def test_all_entries_have_assessment_year(self):
        schedule = generate_installment_schedule(2025)
        for entry in schedule:
            self.assertEqual(entry["assessment_year"], 2025)

    def test_months_in_order(self):
        schedule = generate_installment_schedule(2026)
        months = [e["installment_month"] for e in schedule]
        self.assertEqual(months, [3, 5, 7, 9, 11, 1])

    def test_calendar_years_correct(self):
        schedule = generate_installment_schedule(2026)
        # Mar-Nov in 2026, Jan in 2027
        for entry in schedule[:5]:
            self.assertEqual(entry["due_date"].year, 2026)
        self.assertEqual(schedule[5]["due_date"].year, 2027)


# ---------------------------------------------------------------------------
# Next due date
# ---------------------------------------------------------------------------

class TestGetNextDueDate(unittest.TestCase):
    """Test next upcoming CP500 due date lookup."""

    def test_before_march(self):
        result = get_next_due_date(date(2026, 1, 1), 2026)
        self.assertEqual(result, date(2026, 3, 15))

    def test_on_march_15(self):
        result = get_next_due_date(date(2026, 3, 15), 2026)
        self.assertEqual(result, date(2026, 3, 15))

    def test_after_march_15(self):
        result = get_next_due_date(date(2026, 3, 16), 2026)
        self.assertEqual(result, date(2026, 5, 15))

    def test_after_november(self):
        result = get_next_due_date(date(2026, 11, 16), 2026)
        self.assertEqual(result, date(2027, 1, 15))

    def test_after_january_next_year(self):
        result = get_next_due_date(date(2027, 1, 16), 2026)
        self.assertIsNone(result)


class TestGetDaysUntilNextInstallment(unittest.TestCase):
    """Test days-until calculation."""

    def test_exact_due_date(self):
        result = get_days_until_next_installment(date(2026, 3, 15), 2026)
        self.assertEqual(result, 0)

    def test_one_day_before(self):
        result = get_days_until_next_installment(date(2026, 3, 14), 2026)
        self.assertEqual(result, 1)

    def test_none_when_past_all(self):
        result = get_days_until_next_installment(date(2027, 2, 1), 2026)
        self.assertIsNone(result)

    def test_positive_days(self):
        result = get_days_until_next_installment(date(2026, 1, 1), 2026)
        self.assertGreater(result, 0)


# ---------------------------------------------------------------------------
# Installment records
# ---------------------------------------------------------------------------

class TestCreateInstallmentRecord(unittest.TestCase):
    """Test installment record creation."""

    def test_unpaid_record(self):
        rec = create_installment_record(3, date(2026, 3, 15), 2026)
        self.assertEqual(rec["installment_month"], 3)
        self.assertEqual(rec["due_date"], date(2026, 3, 15))
        self.assertEqual(rec["status"], "Unpaid")
        self.assertEqual(rec["payment_ref"], "")
        self.assertIsNone(rec["paid_date"])

    def test_paid_record(self):
        rec = create_installment_record(
            3, date(2026, 3, 15), 2026,
            payment_ref="PAY-001", paid_date=date(2026, 3, 10), amount=2000,
        )
        self.assertEqual(rec["status"], "Paid")
        self.assertEqual(rec["payment_ref"], "PAY-001")
        self.assertEqual(rec["amount"], 2000.0)

    def test_assessment_year_stored(self):
        rec = create_installment_record(5, date(2026, 5, 15), 2026)
        self.assertEqual(rec["assessment_year"], 2026)


class TestMarkInstallmentPaid(unittest.TestCase):
    """Test marking an installment as paid."""

    def test_marks_paid(self):
        rec = create_installment_record(3, date(2026, 3, 15), 2026)
        mark_installment_paid(rec, "REF-123", date(2026, 3, 12))
        self.assertEqual(rec["status"], "Paid")
        self.assertEqual(rec["payment_ref"], "REF-123")
        self.assertEqual(rec["paid_date"], date(2026, 3, 12))

    def test_updates_amount(self):
        rec = create_installment_record(3, date(2026, 3, 15), 2026, amount=1000)
        mark_installment_paid(rec, "REF-456", date(2026, 3, 14), amount=1500)
        self.assertEqual(rec["amount"], 1500.0)

    def test_preserves_amount_if_not_given(self):
        rec = create_installment_record(3, date(2026, 3, 15), 2026, amount=1000)
        mark_installment_paid(rec, "REF-789", date(2026, 3, 14))
        self.assertEqual(rec["amount"], 1000.0)


class TestIsInstallmentOverdue(unittest.TestCase):
    """Test overdue detection."""

    def test_overdue_when_unpaid_past_due(self):
        rec = create_installment_record(3, date(2026, 3, 15), 2026)
        self.assertTrue(is_installment_overdue(rec, date(2026, 3, 16)))

    def test_not_overdue_on_due_date(self):
        rec = create_installment_record(3, date(2026, 3, 15), 2026)
        self.assertFalse(is_installment_overdue(rec, date(2026, 3, 15)))

    def test_not_overdue_when_paid(self):
        rec = create_installment_record(
            3, date(2026, 3, 15), 2026,
            payment_ref="P1", paid_date=date(2026, 3, 10),
        )
        self.assertFalse(is_installment_overdue(rec, date(2026, 4, 1)))

    def test_not_overdue_before_due(self):
        rec = create_installment_record(5, date(2026, 5, 15), 2026)
        self.assertFalse(is_installment_overdue(rec, date(2026, 3, 1)))

    def test_overdue_with_string_date(self):
        rec = {
            "due_date": "2026-03-15",
            "status": "Unpaid",
        }
        self.assertTrue(is_installment_overdue(rec, date(2026, 3, 16)))


# ---------------------------------------------------------------------------
# Revision deadlines
# ---------------------------------------------------------------------------

class TestRevisionDeadlines(unittest.TestCase):
    """Test revision deadline helpers."""

    def test_get_revision_deadlines(self):
        d = get_revision_deadlines(2026)
        self.assertEqual(d["first_revision"], date(2026, 6, 30))
        self.assertEqual(d["second_revision"], date(2026, 10, 31))

    def test_can_revise_before_october(self):
        self.assertTrue(can_revise_cp500(date(2026, 6, 1), 2026))

    def test_can_revise_on_october_31(self):
        self.assertTrue(can_revise_cp500(date(2026, 10, 31), 2026))

    def test_cannot_revise_after_october(self):
        self.assertFalse(can_revise_cp500(date(2026, 11, 1), 2026))

    def test_next_revision_before_june(self):
        result = get_next_revision_deadline(date(2026, 3, 1), 2026)
        self.assertEqual(result, date(2026, 6, 30))

    def test_next_revision_after_june(self):
        result = get_next_revision_deadline(date(2026, 7, 1), 2026)
        self.assertEqual(result, date(2026, 10, 31))

    def test_next_revision_after_october(self):
        result = get_next_revision_deadline(date(2026, 11, 1), 2026)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Payroll advisory
# ---------------------------------------------------------------------------

class TestGetPayrollAdvisory(unittest.TestCase):
    """Test payroll summary advisory note generation."""

    def test_returns_note_for_cp500_payer(self):
        emp = {"cp500_payer": True}
        result = get_payroll_advisory(emp)
        self.assertEqual(result, ADVISORY_NOTE)

    def test_returns_empty_for_non_payer(self):
        emp = {"cp500_payer": False}
        self.assertEqual(get_payroll_advisory(emp), "")

    def test_returns_empty_when_flag_missing(self):
        self.assertEqual(get_payroll_advisory({}), "")


# ---------------------------------------------------------------------------
# Upcoming installments filter
# ---------------------------------------------------------------------------

class TestGetUpcomingInstallments(unittest.TestCase):
    """Test dashboard upcoming installment filtering."""

    def _make_records(self, ay=2026):
        schedule = generate_installment_schedule(ay)
        return [
            create_installment_record(
                e["installment_month"], e["due_date"], e["assessment_year"]
            )
            for e in schedule
        ]

    def test_filters_within_window(self):
        records = self._make_records()
        # Reference: Feb 20, 2026 -> window ends Mar 22 -> March 15 is within
        result = get_upcoming_installments(records, date(2026, 2, 20))
        due_dates = [r["due_date"] for r in result]
        self.assertIn(date(2026, 3, 15), due_dates)

    def test_excludes_paid(self):
        records = self._make_records()
        mark_installment_paid(records[0], "P1", date(2026, 3, 10))
        result = get_upcoming_installments(records, date(2026, 2, 20))
        months = [r["installment_month"] for r in result]
        self.assertNotIn(3, months)

    def test_excludes_past_due(self):
        records = self._make_records()
        # Reference: April 1 -> March 15 is past, not in upcoming window
        result = get_upcoming_installments(records, date(2026, 4, 1))
        due_dates = [r["due_date"] for r in result]
        self.assertNotIn(date(2026, 3, 15), due_dates)

    def test_custom_window(self):
        records = self._make_records()
        # Reference: Feb 20, window 10 days -> up to Mar 2, March 15 NOT within
        result = get_upcoming_installments(records, date(2026, 2, 20), window_days=10)
        self.assertEqual(len(result), 0)

    def test_empty_records(self):
        result = get_upcoming_installments([], date(2026, 3, 1))
        self.assertEqual(result, [])


class TestGetOverdueInstallments(unittest.TestCase):
    """Test overdue installment filtering."""

    def test_returns_overdue(self):
        records = [
            create_installment_record(3, date(2026, 3, 15), 2026),
            create_installment_record(5, date(2026, 5, 15), 2026),
        ]
        result = get_overdue_installments(records, date(2026, 4, 1))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["installment_month"], 3)

    def test_excludes_paid(self):
        records = [
            create_installment_record(
                3, date(2026, 3, 15), 2026,
                payment_ref="P1", paid_date=date(2026, 3, 10),
            ),
        ]
        result = get_overdue_installments(records, date(2026, 4, 1))
        self.assertEqual(len(result), 0)

    def test_empty_when_none_overdue(self):
        records = [
            create_installment_record(5, date(2026, 5, 15), 2026),
        ]
        result = get_overdue_installments(records, date(2026, 3, 1))
        self.assertEqual(len(result), 0)


# ---------------------------------------------------------------------------
# Multi-director dashboard
# ---------------------------------------------------------------------------

class TestGetDirectorsWithUpcomingCp500(unittest.TestCase):
    """Test multi-director upcoming installment lookup."""

    def _make_director(self, emp_id, name, payer, installments):
        return {
            "employee": emp_id,
            "employee_name": name,
            "cp500_payer": payer,
            "installments": installments,
        }

    def test_includes_payer_with_upcoming(self):
        inst = [create_installment_record(3, date(2026, 3, 15), 2026)]
        directors = [self._make_director("D1", "Ali", True, inst)]
        result = get_directors_with_upcoming_cp500(directors, date(2026, 2, 20))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["employee"], "D1")

    def test_excludes_non_payer(self):
        inst = [create_installment_record(3, date(2026, 3, 15), 2026)]
        directors = [self._make_director("D2", "Siti", False, inst)]
        result = get_directors_with_upcoming_cp500(directors, date(2026, 2, 20))
        self.assertEqual(len(result), 0)

    def test_excludes_payer_without_upcoming(self):
        inst = [create_installment_record(3, date(2026, 3, 15), 2026)]
        directors = [self._make_director("D3", "Raju", True, inst)]
        result = get_directors_with_upcoming_cp500(directors, date(2026, 6, 1))
        # March is past, May 15 is more than 30 days away from June 1
        self.assertEqual(len(result), 0)

    def test_multiple_directors(self):
        d1_inst = [create_installment_record(3, date(2026, 3, 15), 2026)]
        d2_inst = [create_installment_record(3, date(2026, 3, 15), 2026)]
        directors = [
            self._make_director("D1", "Ali", True, d1_inst),
            self._make_director("D2", "Siti", True, d2_inst),
        ]
        result = get_directors_with_upcoming_cp500(directors, date(2026, 2, 20))
        self.assertEqual(len(result), 2)


class TestGetDashboardSummary(unittest.TestCase):
    """Test high-level dashboard summary."""

    def _make_director(self, emp_id, name, payer, installments):
        return {
            "employee": emp_id,
            "employee_name": name,
            "cp500_payer": payer,
            "installments": installments,
        }

    def test_total_cp500_payers(self):
        directors = [
            self._make_director("D1", "Ali", True, []),
            self._make_director("D2", "Siti", False, []),
            self._make_director("D3", "Raju", True, []),
        ]
        summary = get_dashboard_summary(directors, date(2026, 3, 1))
        self.assertEqual(summary["total_cp500_payers"], 2)

    def test_upcoming_count(self):
        inst = [create_installment_record(3, date(2026, 3, 15), 2026)]
        directors = [self._make_director("D1", "Ali", True, inst)]
        summary = get_dashboard_summary(directors, date(2026, 2, 20))
        self.assertEqual(summary["total_upcoming"], 1)

    def test_overdue_count(self):
        inst = [create_installment_record(3, date(2026, 3, 15), 2026)]
        directors = [self._make_director("D1", "Ali", True, inst)]
        summary = get_dashboard_summary(directors, date(2026, 4, 1))
        self.assertEqual(summary["total_overdue"], 1)
        self.assertEqual(len(summary["overdue_directors"]), 1)

    def test_empty_directors(self):
        summary = get_dashboard_summary([], date(2026, 3, 1))
        self.assertEqual(summary["total_cp500_payers"], 0)
        self.assertEqual(summary["total_upcoming"], 0)
        self.assertEqual(summary["total_overdue"], 0)

    def test_summary_keys(self):
        summary = get_dashboard_summary([], date(2026, 3, 1))
        expected_keys = {
            "total_cp500_payers", "directors_with_upcoming",
            "total_upcoming", "total_overdue", "overdue_directors",
        }
        self.assertEqual(set(summary.keys()), expected_keys)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidateCp500Config(unittest.TestCase):
    """Test CP500 configuration validation."""

    def test_valid_config(self):
        emp = {"cp500_payer": True, "cp500_annual_installment_amount": 12000}
        self.assertEqual(validate_cp500_config(emp), [])

    def test_non_payer_always_valid(self):
        emp = {"cp500_payer": False}
        self.assertEqual(validate_cp500_config(emp), [])

    def test_payer_without_amount(self):
        emp = {"cp500_payer": True}
        issues = validate_cp500_config(emp)
        self.assertEqual(len(issues), 1)
        self.assertIn("amount", issues[0].lower())

    def test_payer_with_zero_amount(self):
        emp = {"cp500_payer": True, "cp500_annual_installment_amount": 0}
        issues = validate_cp500_config(emp)
        self.assertEqual(len(issues), 1)

    def test_missing_flag_no_issues(self):
        self.assertEqual(validate_cp500_config({}), [])
