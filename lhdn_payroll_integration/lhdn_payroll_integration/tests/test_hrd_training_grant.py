"""Tests for US-205: HRD Corp SBL-KHAS Grant Pre-Approval Compliance and
6-Month Post-Training Claim Deadline Alert.

Covers:
1. check_pre_approval_compliance — no application, status not_submitted
2. check_pre_approval_compliance — application before start, claimable ok
3. check_pre_approval_compliance — application on same day as training start → non-claimable
4. check_pre_approval_compliance — application after training start → non-claimable
5. check_pre_approval_compliance — training started, no application → not_submitted, non-claimable
6. check_claim_deadline_compliance — claim already submitted → claim_submitted
7. check_claim_deadline_compliance — 15 days after end, no claim → ok (no alert)
8. check_claim_deadline_compliance — 20 days after end → claim_due_soon
9. check_claim_deadline_compliance — 28 days after end → claim_urgent
10. check_claim_deadline_compliance — 153+ days (5 months) → claim_critical
11. check_claim_deadline_compliance — 165+ days (5.5 months) → claim_critical_urgent
12. check_claim_deadline_compliance — 183+ days (6 months) → claim_expired
13. check_claim_deadline_compliance — no training end date → ok
14. get_hrd_dashboard_summary — categorises needs_pre_approval correctly
15. get_hrd_dashboard_summary — categorises expiring_claim_windows correctly
16. get_hrd_dashboard_summary — categorises expired_claim_windows correctly
17. get_hrd_dashboard_summary — categorises rejected_grants correctly
"""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase


def _make_training(**kwargs):
    """Build a mock training object with sensible defaults."""
    t = MagicMock()
    t.training_start_date = kwargs.get("training_start_date", None)
    t.training_end_date = kwargs.get("training_end_date", None)
    t.etris_application_date = kwargs.get("etris_application_date", None)
    t.etris_claim_submission_date = kwargs.get("etris_claim_submission_date", None)
    t.etris_approval_status = kwargs.get("etris_approval_status", None)
    t.etris_rejection_reason = kwargs.get("etris_rejection_reason", None)
    return t


def _days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _days_from_now(n):
    return (date.today() + timedelta(days=n)).isoformat()


class TestCheckPreApprovalCompliance(FrappeTestCase):
    """Unit tests for check_pre_approval_compliance()."""

    def test_no_application_training_not_started(self):
        """No eTRiS application, training hasn't started → not_submitted but still claimable."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_pre_approval_compliance,
        )

        training = _make_training(
            training_start_date=_days_from_now(10),
            etris_application_date=None,
        )
        result = check_pre_approval_compliance(training)

        self.assertEqual(result["status"], "not_submitted")
        self.assertTrue(result["claimable"])
        self.assertTrue(len(result["messages"]) > 0)
        self.assertIn("Submit at least 1 working day", result["messages"][0])

    def test_application_before_start_is_claimable(self):
        """eTRiS application submitted before training starts → ok, claimable."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_pre_approval_compliance,
        )

        training = _make_training(
            training_start_date=_days_from_now(5),
            etris_application_date=_days_from_now(1),  # 4 days before training
        )
        result = check_pre_approval_compliance(training)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["claimable"])
        self.assertEqual(result["messages"], [])

    def test_application_same_day_as_training_start_is_non_claimable(self):
        """Application on same day as training start → late_application, non-claimable."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_pre_approval_compliance,
        )

        same_day = _days_from_now(5)
        training = _make_training(
            training_start_date=same_day,
            etris_application_date=same_day,
        )
        result = check_pre_approval_compliance(training)

        self.assertEqual(result["status"], "late_application")
        self.assertFalse(result["claimable"])
        self.assertTrue(len(result["messages"]) > 0)
        self.assertIn("non-claimable", result["messages"][0])

    def test_application_after_training_start_is_non_claimable(self):
        """Application submitted after training started → late_application, non-claimable."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_pre_approval_compliance,
        )

        training = _make_training(
            training_start_date=_days_ago(5),
            etris_application_date=_days_ago(2),  # applied 3 days AFTER start
        )
        result = check_pre_approval_compliance(training)

        self.assertEqual(result["status"], "late_application")
        self.assertFalse(result["claimable"])

    def test_no_application_training_already_started_non_claimable(self):
        """No application and training already started → not_submitted, non-claimable."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_pre_approval_compliance,
        )

        training = _make_training(
            training_start_date=_days_ago(3),
            etris_application_date=None,
        )
        result = check_pre_approval_compliance(training)

        self.assertEqual(result["status"], "not_submitted")
        self.assertFalse(result["claimable"])
        self.assertIn("auto-rejects", result["messages"][0])


class TestCheckClaimDeadlineCompliance(FrappeTestCase):
    """Unit tests for check_claim_deadline_compliance()."""

    def test_claim_already_submitted(self):
        """Claim submitted → status claim_submitted."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_claim_deadline_compliance,
        )

        training = _make_training(
            training_end_date=_days_ago(10),
            etris_claim_submission_date=_days_ago(5),
        )
        result = check_claim_deadline_compliance(training)

        self.assertEqual(result["status"], "claim_submitted")

    def test_15_days_after_end_no_alert(self):
        """15 days since training ended → no alert yet (under 20-day threshold)."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_claim_deadline_compliance,
        )

        training = _make_training(
            training_end_date=_days_ago(15),
            etris_claim_submission_date=None,
        )
        result = check_claim_deadline_compliance(training)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["messages"], [])

    def test_20_days_after_end_claim_due_soon(self):
        """20 days since training ended → claim_due_soon."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_claim_deadline_compliance,
        )

        training = _make_training(
            training_end_date=_days_ago(20),
            etris_claim_submission_date=None,
        )
        result = check_claim_deadline_compliance(training)

        self.assertEqual(result["status"], "claim_due_soon")
        self.assertTrue(len(result["messages"]) > 0)

    def test_28_days_after_end_claim_urgent(self):
        """28 days since training ended → claim_urgent (30-day preferred deadline imminent)."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_claim_deadline_compliance,
        )

        training = _make_training(
            training_end_date=_days_ago(28),
            etris_claim_submission_date=None,
        )
        result = check_claim_deadline_compliance(training)

        self.assertEqual(result["status"], "claim_urgent")
        self.assertIn("30-day", result["messages"][0])

    def test_153_days_after_end_claim_critical(self):
        """153 days (5 months) since training ended → claim_critical, escalate HR Director."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_claim_deadline_compliance,
        )

        training = _make_training(
            training_end_date=_days_ago(153),
            etris_claim_submission_date=None,
        )
        result = check_claim_deadline_compliance(training)

        self.assertEqual(result["status"], "claim_critical")
        self.assertIn("HR Director", result["messages"][0])

    def test_165_days_after_end_claim_critical_urgent(self):
        """165 days (5.5 months) since training ended → claim_critical_urgent."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_claim_deadline_compliance,
        )

        training = _make_training(
            training_end_date=_days_ago(165),
            etris_claim_submission_date=None,
        )
        result = check_claim_deadline_compliance(training)

        self.assertEqual(result["status"], "claim_critical_urgent")
        self.assertIn("IMMEDIATELY", result["messages"][0])

    def test_183_days_after_end_claim_expired(self):
        """183 days (6 months) since training ended → claim_expired, cannot recover."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_claim_deadline_compliance,
        )

        training = _make_training(
            training_end_date=_days_ago(183),
            etris_claim_submission_date=None,
        )
        result = check_claim_deadline_compliance(training)

        self.assertEqual(result["status"], "claim_expired")
        self.assertIn("cannot be recovered", result["messages"][0])

    def test_no_training_end_date_returns_ok(self):
        """No training_end_date → ok, no messages."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            check_claim_deadline_compliance,
        )

        training = _make_training(
            training_end_date=None,
            etris_claim_submission_date=None,
        )
        result = check_claim_deadline_compliance(training)

        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["days_since_training_end"])


class TestGetHrdDashboardSummary(FrappeTestCase):
    """Unit tests for get_hrd_dashboard_summary()."""

    def test_needs_pre_approval_categorised(self):
        """Training with no application and upcoming start → needs_pre_approval."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            get_hrd_dashboard_summary,
        )

        training = _make_training(
            training_start_date=_days_from_now(7),
            training_end_date=_days_from_now(10),
            etris_application_date=None,
        )
        summary = get_hrd_dashboard_summary([training])

        self.assertEqual(len(summary["needs_pre_approval"]), 1)
        self.assertEqual(len(summary["expiring_claim_windows"]), 0)
        self.assertEqual(len(summary["expired_claim_windows"]), 0)
        self.assertEqual(len(summary["rejected_grants"]), 0)

    def test_expiring_claim_window_categorised(self):
        """Training ended 22 days ago, no claim → expiring_claim_windows."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            get_hrd_dashboard_summary,
        )

        training = _make_training(
            training_start_date=_days_ago(25),
            training_end_date=_days_ago(22),
            etris_application_date=_days_ago(27),
            etris_claim_submission_date=None,
        )
        summary = get_hrd_dashboard_summary([training])

        self.assertEqual(len(summary["expiring_claim_windows"]), 1)
        self.assertEqual(len(summary["expired_claim_windows"]), 0)

    def test_expired_claim_window_categorised(self):
        """Training ended 200 days ago, no claim → expired_claim_windows."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            get_hrd_dashboard_summary,
        )

        training = _make_training(
            training_start_date=_days_ago(205),
            training_end_date=_days_ago(200),
            etris_application_date=_days_ago(207),
            etris_claim_submission_date=None,
        )
        summary = get_hrd_dashboard_summary([training])

        self.assertEqual(len(summary["expired_claim_windows"]), 1)
        self.assertEqual(len(summary["expiring_claim_windows"]), 0)

    def test_rejected_grant_categorised(self):
        """Training with etris_approval_status='Rejected' → rejected_grants."""
        from lhdn_payroll_integration.services.hrd_training_grant_service import (
            get_hrd_dashboard_summary,
        )

        training = _make_training(
            training_start_date=_days_ago(30),
            training_end_date=_days_ago(25),
            etris_application_date=_days_ago(32),
            etris_approval_status="Rejected",
            etris_rejection_reason="Training already started",
        )
        summary = get_hrd_dashboard_summary([training])

        self.assertEqual(len(summary["rejected_grants"]), 1)
        self.assertEqual(
            summary["rejected_grants"][0]["rejection_reason"],
            "Training already started",
        )
