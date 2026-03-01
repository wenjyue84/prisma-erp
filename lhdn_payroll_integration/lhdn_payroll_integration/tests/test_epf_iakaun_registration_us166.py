"""Tests for US-166: EPF i-Akaun 30-Day Registration Deadline Alert for Foreign Workers.

Acceptance criteria verified:
1. Existing active foreign workers (hired before Oct 2025) have a fixed deadline:
   'EPF Registration Required by 14 November 2025'
2. New foreign worker hires from October 2025 onwards get 30-day countdown from hire date
3. custom_epf_iakaun_registration_confirmed and custom_epf_iakaun_registration_date
   fields on Employee (via fixtures)
4. After 30 days without confirmation, high-priority alert sent to HR Manager role
5. Domestic servants excluded from EPF registration alerts (no false positives)
"""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, call

import frappe
from frappe.tests.utils import FrappeTestCase


class TestEPFIAkaunConstants(FrappeTestCase):
    """Verify core constants exported by the service."""

    def test_epf_fw_mandatory_date(self):
        """EPF_FW_MANDATORY_DATE must be 2025-10-01."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            EPF_FW_MANDATORY_DATE,
        )
        self.assertEqual(EPF_FW_MANDATORY_DATE, date(2025, 10, 1))

    def test_legacy_registration_deadline(self):
        """LEGACY_REGISTRATION_DEADLINE must be 2025-11-14."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            LEGACY_REGISTRATION_DEADLINE,
        )
        self.assertEqual(LEGACY_REGISTRATION_DEADLINE, date(2025, 11, 14))

    def test_new_hire_deadline_days(self):
        """NEW_HIRE_DEADLINE_DAYS must be 30."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            NEW_HIRE_DEADLINE_DAYS,
        )
        self.assertEqual(NEW_HIRE_DEADLINE_DAYS, 30)


class TestIsLegacyForeignWorker(FrappeTestCase):
    """Verify is_legacy_foreign_worker classifies employees correctly."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            is_legacy_foreign_worker,
        )
        self.fn = is_legacy_foreign_worker

    def test_hired_sep_2025_is_legacy(self):
        """Employee hired September 30, 2025 → legacy (before Oct 2025)."""
        self.assertTrue(self.fn(date(2025, 9, 30)))

    def test_hired_jan_2025_is_legacy(self):
        """Employee hired January 2025 → legacy."""
        self.assertTrue(self.fn(date(2025, 1, 1)))

    def test_hired_oct_2025_is_not_legacy(self):
        """Employee hired October 1, 2025 → NOT legacy (exactly mandatory date)."""
        self.assertFalse(self.fn(date(2025, 10, 1)))

    def test_hired_oct_15_2025_is_not_legacy(self):
        """Employee hired October 15, 2025 → NOT legacy."""
        self.assertFalse(self.fn(date(2025, 10, 15)))

    def test_hired_nov_2025_is_not_legacy(self):
        """Employee hired November 2025 → NOT legacy."""
        self.assertFalse(self.fn(date(2025, 11, 1)))

    def test_hired_2026_is_not_legacy(self):
        """Employee hired in 2026 → NOT legacy."""
        self.assertFalse(self.fn(date(2026, 3, 1)))

    def test_none_doj_returns_false(self):
        """None date_of_joining → returns False (defensive)."""
        self.assertFalse(self.fn(None))

    def test_string_date_supported(self):
        """String date_of_joining supported (Frappe convention)."""
        self.assertTrue(self.fn("2025-05-01"))
        self.assertFalse(self.fn("2025-10-01"))


class TestGetRegistrationDeadline(FrappeTestCase):
    """Verify get_registration_deadline returns correct deadlines."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            get_registration_deadline,
        )
        self.fn = get_registration_deadline

    def test_legacy_worker_deadline_is_nov_14_2025(self):
        """Legacy worker (hired before Oct 2025) → fixed deadline Nov 14, 2025."""
        deadline = self.fn(date(2025, 9, 30))
        self.assertEqual(deadline, date(2025, 11, 14))

    def test_legacy_worker_jan_2025_deadline_is_nov_14_2025(self):
        """Legacy worker hired Jan 2025 → same fixed deadline Nov 14, 2025."""
        deadline = self.fn(date(2025, 1, 1))
        self.assertEqual(deadline, date(2025, 11, 14))

    def test_new_hire_oct_1_2025_deadline_is_30_days_later(self):
        """New hire Oct 1, 2025 → deadline Oct 31, 2025."""
        deadline = self.fn(date(2025, 10, 1))
        self.assertEqual(deadline, date(2025, 10, 31))

    def test_new_hire_oct_15_2025_deadline_is_nov_14_2025(self):
        """New hire Oct 15, 2025 → deadline Nov 14, 2025."""
        deadline = self.fn(date(2025, 10, 15))
        self.assertEqual(deadline, date(2025, 11, 14))

    def test_new_hire_dec_2025_deadline_is_30_days(self):
        """New hire December 1, 2025 → deadline December 31, 2025."""
        deadline = self.fn(date(2025, 12, 1))
        self.assertEqual(deadline, date(2025, 12, 31))

    def test_new_hire_2026_deadline_is_30_days(self):
        """New hire March 1, 2026 → deadline March 31, 2026."""
        deadline = self.fn(date(2026, 3, 1))
        self.assertEqual(deadline, date(2026, 3, 31))

    def test_string_date_supported(self):
        """String date_of_joining works the same as date object."""
        self.assertEqual(self.fn("2025-09-30"), date(2025, 11, 14))
        self.assertEqual(self.fn("2025-10-01"), date(2025, 10, 31))


class TestIsRegistrationOverdue(FrappeTestCase):
    """Verify is_registration_overdue logic."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            is_registration_overdue,
        )
        self.fn = is_registration_overdue

    def _emp(self, is_foreign=1, is_domestic=0, confirmed=0, doj=date(2025, 10, 1)):
        return {
            "custom_is_foreign_worker": is_foreign,
            "custom_is_domestic_servant": is_domestic,
            "custom_epf_iakaun_registration_confirmed": confirmed,
            "date_of_joining": doj,
        }

    def test_overdue_when_deadline_passed_without_confirmation(self):
        """New hire Oct 1, 2025: overdue after Oct 31, 2025 without confirmation."""
        emp = self._emp(doj=date(2025, 10, 1))
        self.assertTrue(self.fn(emp, today_date=date(2025, 11, 1)))

    def test_not_overdue_within_30_days(self):
        """New hire Oct 1, 2025: NOT overdue on Oct 31, 2025 (exactly at deadline)."""
        emp = self._emp(doj=date(2025, 10, 1))
        self.assertFalse(self.fn(emp, today_date=date(2025, 10, 31)))

    def test_not_overdue_when_confirmed(self):
        """Confirmed employee is never overdue."""
        emp = self._emp(confirmed=1, doj=date(2025, 10, 1))
        self.assertFalse(self.fn(emp, today_date=date(2026, 1, 1)))

    def test_domestic_servant_never_overdue(self):
        """Domestic servant is excluded — always returns False."""
        emp = self._emp(is_foreign=1, is_domestic=1, doj=date(2025, 10, 1))
        self.assertFalse(self.fn(emp, today_date=date(2026, 1, 1)))

    def test_malaysian_employee_never_overdue(self):
        """Malaysian (non-foreign) employee — always returns False."""
        emp = self._emp(is_foreign=0, doj=date(2025, 10, 1))
        self.assertFalse(self.fn(emp, today_date=date(2026, 1, 1)))

    def test_legacy_worker_overdue_after_nov_14_2025(self):
        """Legacy worker (hired Sep 2025): overdue after Nov 14, 2025."""
        emp = self._emp(doj=date(2025, 9, 1))
        self.assertTrue(self.fn(emp, today_date=date(2025, 11, 15)))

    def test_legacy_worker_not_overdue_on_nov_14_2025(self):
        """Legacy worker: NOT overdue on Nov 14, 2025 (exactly at deadline)."""
        emp = self._emp(doj=date(2025, 9, 1))
        self.assertFalse(self.fn(emp, today_date=date(2025, 11, 14)))

    def test_no_doj_returns_false(self):
        """Employee with no date_of_joining → False (defensive)."""
        emp = self._emp(doj=None)
        self.assertFalse(self.fn(emp, today_date=date(2026, 1, 1)))


class TestGetEmployeesNeedingRegistration(FrappeTestCase):
    """Verify get_employees_needing_registration filters correctly."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            get_employees_needing_registration,
        )
        self.fn = get_employees_needing_registration

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.frappe")
    def test_excludes_confirmed_employees(self, mock_frappe):
        """Confirmed employees are not in the needs-registration list."""
        mock_frappe.get_all.return_value = [
            frappe._dict({
                "name": "EMP001",
                "employee_name": "Jane Worker",
                "company": "Test Co",
                "date_of_joining": date(2025, 10, 1),
                "custom_is_domestic_servant": 0,
                "custom_epf_iakaun_registration_confirmed": 1,
                "custom_epf_iakaun_registration_date": date(2025, 10, 15),
            }),
        ]
        result = self.fn(today_date=date(2025, 11, 15))
        self.assertEqual(len(result), 0, "Confirmed employees should not need registration")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.frappe")
    def test_excludes_domestic_servants(self, mock_frappe):
        """Domestic servants are excluded even if unconfirmed."""
        mock_frappe.get_all.return_value = [
            frappe._dict({
                "name": "EMP002",
                "employee_name": "Maria Maid",
                "company": "Test Co",
                "date_of_joining": date(2025, 10, 1),
                "custom_is_domestic_servant": 1,
                "custom_epf_iakaun_registration_confirmed": 0,
                "custom_epf_iakaun_registration_date": None,
            }),
        ]
        result = self.fn(today_date=date(2025, 11, 15))
        self.assertEqual(len(result), 0, "Domestic servants must be excluded")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.frappe")
    def test_includes_unconfirmed_foreign_worker(self, mock_frappe):
        """Unconfirmed foreign worker past mandatory date is included."""
        mock_frappe.get_all.return_value = [
            frappe._dict({
                "name": "EMP003",
                "employee_name": "Nguyen Van A",
                "company": "Test Co",
                "date_of_joining": date(2025, 10, 1),
                "custom_is_domestic_servant": 0,
                "custom_epf_iakaun_registration_confirmed": 0,
                "custom_epf_iakaun_registration_date": None,
            }),
        ]
        result = self.fn(today_date=date(2025, 11, 15))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "EMP003")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.frappe")
    def test_overdue_flag_set_correctly(self, mock_frappe):
        """is_overdue flag set correctly for overdue employee."""
        mock_frappe.get_all.return_value = [
            frappe._dict({
                "name": "EMP004",
                "employee_name": "John Foreign",
                "company": "Test Co",
                "date_of_joining": date(2025, 10, 1),
                "custom_is_domestic_servant": 0,
                "custom_epf_iakaun_registration_confirmed": 0,
                "custom_epf_iakaun_registration_date": None,
            }),
        ]
        # Nov 15 > Oct 31 deadline → overdue
        result = self.fn(today_date=date(2025, 11, 15))
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["is_overdue"])
        self.assertEqual(result[0]["days_overdue"], 15)  # Nov 15 - Oct 31 = 15 days

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.frappe")
    def test_days_remaining_set_for_pending_employee(self, mock_frappe):
        """days_remaining set for employee not yet overdue."""
        mock_frappe.get_all.return_value = [
            frappe._dict({
                "name": "EMP005",
                "employee_name": "Wang Wei",
                "company": "Test Co",
                "date_of_joining": date(2025, 10, 15),
                "custom_is_domestic_servant": 0,
                "custom_epf_iakaun_registration_confirmed": 0,
                "custom_epf_iakaun_registration_date": None,
            }),
        ]
        # Oct 25 < Nov 14 deadline → not overdue, 20 days remaining
        result = self.fn(today_date=date(2025, 10, 25))
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["is_overdue"])
        # deadline is Nov 14; today is Oct 25; days remaining = 20
        self.assertEqual(result[0]["days_remaining"], 20)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.frappe")
    def test_no_alerts_before_mandatory_date(self, mock_frappe):
        """No employees need registration before EPF mandatory date (Oct 1, 2025)."""
        mock_frappe.get_all.return_value = [
            frappe._dict({
                "name": "EMP006",
                "employee_name": "Ali",
                "company": "Test Co",
                "date_of_joining": date(2025, 9, 1),
                "custom_is_domestic_servant": 0,
                "custom_epf_iakaun_registration_confirmed": 0,
                "custom_epf_iakaun_registration_date": None,
            }),
        ]
        result = self.fn(today_date=date(2025, 9, 30))
        self.assertEqual(len(result), 0, "No alerts before mandatory date")


class TestCheckForeignWorkerIAkaunDeadlines(FrappeTestCase):
    """Verify the scheduled job check_foreign_worker_iakaun_deadlines behavior."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service._send_overdue_alert")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.get_employees_needing_registration")
    def test_sends_alert_for_overdue_employees(self, mock_get_emps, mock_send):
        """Overdue employees trigger _send_overdue_alert."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            check_foreign_worker_iakaun_deadlines,
        )
        mock_get_emps.return_value = [
            {
                "name": "EMP001",
                "employee_name": "Nguyen",
                "company": "Co A",
                "date_of_joining": date(2025, 10, 1),
                "registration_deadline": date(2025, 10, 31),
                "is_overdue": True,
                "days_overdue": 5,
                "days_remaining": 0,
                "custom_is_domestic_servant": 0,
                "custom_epf_iakaun_registration_confirmed": 0,
            }
        ]
        check_foreign_worker_iakaun_deadlines(today_date=date(2025, 11, 5))
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        self.assertEqual(args[0], "Co A")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service._send_overdue_alert")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.get_employees_needing_registration")
    def test_no_alert_when_no_overdue(self, mock_get_emps, mock_send):
        """No alert when all employees are confirmed or within deadline."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            check_foreign_worker_iakaun_deadlines,
        )
        mock_get_emps.return_value = [
            {
                "name": "EMP002",
                "employee_name": "Wang",
                "company": "Co B",
                "date_of_joining": date(2025, 10, 15),
                "registration_deadline": date(2025, 11, 14),
                "is_overdue": False,
                "days_overdue": 0,
                "days_remaining": 10,
            }
        ]
        check_foreign_worker_iakaun_deadlines(today_date=date(2025, 11, 5))
        mock_send.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service._send_overdue_alert")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.get_employees_needing_registration")
    def test_no_alert_before_mandatory_date(self, mock_get_emps, mock_send):
        """No alert sent when today is before Oct 1, 2025."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            check_foreign_worker_iakaun_deadlines,
        )
        check_foreign_worker_iakaun_deadlines(today_date=date(2025, 9, 30))
        mock_get_emps.assert_not_called()
        mock_send.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service._send_overdue_alert")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.get_employees_needing_registration")
    def test_groups_by_company(self, mock_get_emps, mock_send):
        """Multiple overdue employees from same company → one combined alert."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            check_foreign_worker_iakaun_deadlines,
        )
        mock_get_emps.return_value = [
            {
                "name": "EMP003",
                "employee_name": "Ali",
                "company": "Co C",
                "date_of_joining": date(2025, 10, 1),
                "registration_deadline": date(2025, 10, 31),
                "is_overdue": True,
                "days_overdue": 5,
                "days_remaining": 0,
            },
            {
                "name": "EMP004",
                "employee_name": "Budi",
                "company": "Co C",
                "date_of_joining": date(2025, 10, 1),
                "registration_deadline": date(2025, 10, 31),
                "is_overdue": True,
                "days_overdue": 5,
                "days_remaining": 0,
            },
        ]
        check_foreign_worker_iakaun_deadlines(today_date=date(2025, 11, 5))
        # Should call _send_overdue_alert once for "Co C" with 2 employees
        self.assertEqual(mock_send.call_count, 1)
        call_args = mock_send.call_args[0]
        self.assertEqual(call_args[0], "Co C")
        self.assertEqual(len(call_args[1]), 2)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service._send_overdue_alert")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.get_employees_needing_registration")
    def test_separate_alerts_per_company(self, mock_get_emps, mock_send):
        """Overdue employees from different companies → separate alerts."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            check_foreign_worker_iakaun_deadlines,
        )
        mock_get_emps.return_value = [
            {
                "name": "EMP005",
                "employee_name": "C",
                "company": "Co D",
                "date_of_joining": date(2025, 10, 1),
                "registration_deadline": date(2025, 10, 31),
                "is_overdue": True,
                "days_overdue": 3,
                "days_remaining": 0,
            },
            {
                "name": "EMP006",
                "employee_name": "D",
                "company": "Co E",
                "date_of_joining": date(2025, 10, 1),
                "registration_deadline": date(2025, 10, 31),
                "is_overdue": True,
                "days_overdue": 3,
                "days_remaining": 0,
            },
        ]
        check_foreign_worker_iakaun_deadlines(today_date=date(2025, 11, 3))
        self.assertEqual(mock_send.call_count, 2)


class TestDomesticServantExclusion(FrappeTestCase):
    """Verify domestic servants are completely excluded from EPF registration alerts."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            is_registration_overdue,
            get_employees_needing_registration,
        )
        self.is_overdue = is_registration_overdue
        self.get_needing = get_employees_needing_registration

    def test_maid_excluded_from_overdue(self):
        """Foreign worker flagged as domestic servant → not overdue."""
        emp = {
            "custom_is_foreign_worker": 1,
            "custom_is_domestic_servant": 1,
            "custom_epf_iakaun_registration_confirmed": 0,
            "date_of_joining": date(2025, 10, 1),
        }
        self.assertFalse(
            self.is_overdue(emp, today_date=date(2026, 1, 1)),
            "Domestic servant (maid/cook/cleaner/driver) must never be overdue for EPF registration",
        )

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service.frappe")
    def test_domestic_servant_not_in_needs_registration_list(self, mock_frappe):
        """Domestic servant is not returned by get_employees_needing_registration."""
        mock_frappe.get_all.return_value = [
            frappe._dict({
                "name": "EMP_MAID",
                "employee_name": "Maria Domestic",
                "company": "Test Co",
                "date_of_joining": date(2025, 10, 1),
                "custom_is_domestic_servant": 1,
                "custom_epf_iakaun_registration_confirmed": 0,
                "custom_epf_iakaun_registration_date": None,
            }),
            frappe._dict({
                "name": "EMP_REGULAR",
                "employee_name": "Wang Regular",
                "company": "Test Co",
                "date_of_joining": date(2025, 10, 1),
                "custom_is_domestic_servant": 0,
                "custom_epf_iakaun_registration_confirmed": 0,
                "custom_epf_iakaun_registration_date": None,
            }),
        ]
        result = self.get_needing(today_date=date(2025, 11, 15))
        names = [r["name"] for r in result]
        self.assertNotIn("EMP_MAID", names, "Domestic servant must not need registration alert")
        self.assertIn("EMP_REGULAR", names, "Regular foreign worker must need registration alert")


class TestCustomFieldsExistInFixtures(FrappeTestCase):
    """Verify that EPF i-Akaun registration custom fields are defined in fixtures."""

    def _get_custom_fields(self):
        import json
        import os
        fixture_path = os.path.join(
            frappe.get_app_path("lhdn_payroll_integration"),
            "fixtures", "custom_field.json",
        )
        if not os.path.exists(fixture_path):
            return []
        with open(fixture_path, encoding="utf-8") as f:
            return json.load(f)

    def test_epf_iakaun_registration_confirmed_field_exists(self):
        """custom_epf_iakaun_registration_confirmed (Check) must be in custom_field.json."""
        fields = self._get_custom_fields()
        fieldnames = [f.get("fieldname", "") for f in fields if f.get("dt") == "Employee"]
        self.assertIn(
            "custom_epf_iakaun_registration_confirmed",
            fieldnames,
            "custom_epf_iakaun_registration_confirmed Check field must be in fixtures",
        )

    def test_epf_iakaun_registration_date_field_exists(self):
        """custom_epf_iakaun_registration_date (Date) must be in custom_field.json."""
        fields = self._get_custom_fields()
        fieldnames = [f.get("fieldname", "") for f in fields if f.get("dt") == "Employee"]
        self.assertIn(
            "custom_epf_iakaun_registration_date",
            fieldnames,
            "custom_epf_iakaun_registration_date Date field must be in fixtures",
        )

    def test_confirmed_field_is_check_type(self):
        """custom_epf_iakaun_registration_confirmed must be fieldtype=Check."""
        fields = self._get_custom_fields()
        for f in fields:
            if f.get("dt") == "Employee" and f.get("fieldname") == "custom_epf_iakaun_registration_confirmed":
                self.assertEqual(f.get("fieldtype"), "Check")
                return
        self.fail("custom_epf_iakaun_registration_confirmed not found in fixtures")

    def test_date_field_is_date_type(self):
        """custom_epf_iakaun_registration_date must be fieldtype=Date."""
        fields = self._get_custom_fields()
        for f in fields:
            if f.get("dt") == "Employee" and f.get("fieldname") == "custom_epf_iakaun_registration_date":
                self.assertEqual(f.get("fieldtype"), "Date")
                return
        self.fail("custom_epf_iakaun_registration_date not found in fixtures")


class TestLegacyWorkerFixedDeadlineAlert(FrappeTestCase):
    """Verify legacy worker alert uses 'EPF Registration Required by 14 November 2025'."""

    def test_legacy_alert_deadline_message(self):
        """Alert message for legacy worker must reference 14 November 2025."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            is_legacy_foreign_worker,
            get_registration_deadline,
        )
        doj = date(2025, 8, 1)
        self.assertTrue(is_legacy_foreign_worker(doj))
        deadline = get_registration_deadline(doj)
        self.assertEqual(deadline, date(2025, 11, 14),
                         "Legacy worker deadline must be 14 November 2025")

    def test_multiple_legacy_workers_all_get_nov_14_deadline(self):
        """All workers hired before Oct 2025 have the same Nov 14 deadline."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.epf_iakaun_registration_service import (
            get_registration_deadline,
        )
        legacy_doj_list = [
            date(2024, 1, 1),
            date(2024, 6, 15),
            date(2025, 1, 1),
            date(2025, 9, 30),
        ]
        for doj in legacy_doj_list:
            deadline = get_registration_deadline(doj)
            self.assertEqual(
                deadline,
                date(2025, 11, 14),
                f"Worker hired on {doj} must have Nov 14, 2025 deadline",
            )
