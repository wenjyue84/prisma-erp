"""
Tests for US-121 — Statutory Compliance Submission Tracker

TDD GREEN: all tests must pass after implementation.
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker import (
	_get_monthly_due_date,
	_get_payroll_period_str,
	create_annual_compliance_records,
	create_monthly_compliance_records,
	get_compliance_status_for_dashboard,
	send_overdue_compliance_notifications,
	update_overdue_compliance_records,
)


class TestComplianceTrackerHelpers(FrappeTestCase):
	"""Unit tests for internal helper functions."""

	def test_get_payroll_period_str_standard(self):
		"""YYYY-MM format returned from end_date."""
		result = _get_payroll_period_str("2026-01-31")
		self.assertEqual(result, "2026-01")

	def test_get_payroll_period_str_december(self):
		result = _get_payroll_period_str("2025-12-31")
		self.assertEqual(result, "2025-12")

	def test_get_monthly_due_date_standard(self):
		"""15th of following month returned."""
		due = _get_monthly_due_date("2026-01-31")
		self.assertEqual(str(due), "2026-02-15")

	def test_get_monthly_due_date_december(self):
		"""December payroll → due 15 Jan following year."""
		due = _get_monthly_due_date("2025-12-31")
		self.assertEqual(str(due), "2026-01-15")

	def test_get_monthly_due_date_february(self):
		"""Feb payroll → due 15 Mar."""
		due = _get_monthly_due_date("2026-02-28")
		self.assertEqual(str(due), "2026-03-15")


class TestCreateMonthlyComplianceRecords(FrappeTestCase):
	"""Tests for create_monthly_compliance_records hook."""

	def _make_payroll_entry(self, end_date="2026-01-31", company="Test Company"):
		doc = MagicMock()
		doc.name = "PE-001"
		doc.company = company
		doc.end_date = end_date
		return doc

	def _make_record_factory(self, store):
		"""Return a side_effect factory that accepts doctype argument from frappe.new_doc."""
		def make_record(*args):
			m = MagicMock()
			store.append(m)
			return m
		return make_record

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.db.exists")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.new_doc")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.msgprint")
	def test_creates_five_records_for_new_period(self, mock_msgprint, mock_new_doc, mock_exists):
		"""Should create PCB, EPF, SOCSO, EIS, HRDF records."""
		mock_exists.return_value = False
		records_created = []
		mock_new_doc.side_effect = self._make_record_factory(records_created)

		doc = self._make_payroll_entry()
		create_monthly_compliance_records(doc, "on_submit")

		self.assertEqual(mock_new_doc.call_count, 5)
		compliance_types = [r.compliance_type for r in records_created]
		self.assertIn("PCB", compliance_types)
		self.assertIn("EPF", compliance_types)
		self.assertIn("SOCSO", compliance_types)
		self.assertIn("EIS", compliance_types)
		self.assertIn("HRDF", compliance_types)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.db.exists")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.new_doc")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.msgprint")
	def test_skips_existing_records(self, mock_msgprint, mock_new_doc, mock_exists):
		"""Should skip compliance types that already have records for the period."""
		mock_exists.return_value = True

		doc = self._make_payroll_entry()
		create_monthly_compliance_records(doc, "on_submit")

		mock_new_doc.assert_not_called()

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.db.exists")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.new_doc")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.msgprint")
	def test_due_date_is_15th_of_following_month(self, mock_msgprint, mock_new_doc, mock_exists):
		"""Due date on created records must be 15th of following month."""
		mock_exists.return_value = False
		created_records = []
		mock_new_doc.side_effect = self._make_record_factory(created_records)

		doc = self._make_payroll_entry(end_date="2026-03-31")
		create_monthly_compliance_records(doc, "on_submit")

		for record in created_records:
			self.assertEqual(str(record.due_date), "2026-04-15")

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.db.exists")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.new_doc")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.msgprint")
	def test_payroll_period_set_correctly(self, mock_msgprint, mock_new_doc, mock_exists):
		"""payroll_period field must be YYYY-MM of payroll end_date."""
		mock_exists.return_value = False
		created_records = []
		mock_new_doc.side_effect = self._make_record_factory(created_records)

		doc = self._make_payroll_entry(end_date="2025-11-30")
		create_monthly_compliance_records(doc, "on_submit")

		for record in created_records:
			self.assertEqual(record.payroll_period, "2025-11")

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.db.exists")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.new_doc")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.msgprint")
	def test_penalty_info_populated(self, mock_msgprint, mock_new_doc, mock_exists):
		"""Penalty info must be set on each created record."""
		mock_exists.return_value = False
		created_records = []
		mock_new_doc.side_effect = self._make_record_factory(created_records)

		doc = self._make_payroll_entry()
		create_monthly_compliance_records(doc, "on_submit")

		# At least PCB and EPF should have penalty info
		pcb_record = next(r for r in created_records if r.compliance_type == "PCB")
		self.assertIn("10%", pcb_record.penalty_info)

		epf_record = next(r for r in created_records if r.compliance_type == "EPF")
		self.assertIn("6%", epf_record.penalty_info)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.db.exists")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.new_doc")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.msgprint")
	def test_payroll_entry_linked(self, mock_msgprint, mock_new_doc, mock_exists):
		"""payroll_entry field must link back to the Payroll Entry document."""
		mock_exists.return_value = False
		created_records = []
		mock_new_doc.side_effect = self._make_record_factory(created_records)

		doc = self._make_payroll_entry()
		create_monthly_compliance_records(doc, "on_submit")

		for record in created_records:
			self.assertEqual(record.payroll_entry, "PE-001")


class TestCreateAnnualComplianceRecords(FrappeTestCase):
	"""Tests for annual EA Form and Borang E record creation."""

	def _make_record_factory(self, store):
		def make_record(*args):
			m = MagicMock()
			store.append(m)
			return m
		return make_record

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.db.exists")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.new_doc")
	def test_creates_ea_form_and_borang_e(self, mock_new_doc, mock_exists):
		"""Should create EA Form (28 Feb) and Borang E (31 Mar) records."""
		mock_exists.return_value = False
		created_records = []
		mock_new_doc.side_effect = self._make_record_factory(created_records)

		result = create_annual_compliance_records("Test Co", 2026)

		self.assertEqual(len(result), 2)
		self.assertIn("EA Form", result)
		self.assertIn("Borang E", result)

		ea_record = next(r for r in created_records if r.compliance_type == "EA Form")
		self.assertEqual(str(ea_record.due_date), "2026-02-28")

		borang_e_record = next(r for r in created_records if r.compliance_type == "Borang E")
		self.assertEqual(str(borang_e_record.due_date), "2026-03-31")

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.db.exists")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.new_doc")
	def test_annual_records_idempotent(self, mock_new_doc, mock_exists):
		"""Should skip creation if records already exist."""
		mock_exists.return_value = True

		result = create_annual_compliance_records("Test Co", 2026)

		mock_new_doc.assert_not_called()
		self.assertEqual(result, [])

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.db.exists")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.new_doc")
	def test_annual_payroll_period_is_previous_year_december(self, mock_new_doc, mock_exists):
		"""Annual records payroll_period should be YYYY-1-12."""
		mock_exists.return_value = False
		created_records = []
		mock_new_doc.side_effect = self._make_record_factory(created_records)

		create_annual_compliance_records("Test Co", 2026)

		for r in created_records:
			self.assertEqual(r.payroll_period, "2025-12")


class TestUpdateOverdueRecords(FrappeTestCase):
	"""Tests for the daily overdue update scheduled job."""

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.get_all")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.db.set_value")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.today")
	def test_flips_pending_to_overdue(self, mock_today, mock_set_value, mock_get_all):
		"""Pending records past due date must be flipped to Overdue."""
		mock_today.return_value = "2026-02-20"
		mock_get_all.return_value = [
			{"name": "SCS-001", "compliance_type": "PCB", "company": "Acme", "payroll_period": "2026-01", "due_date": "2026-02-15"},
			{"name": "SCS-002", "compliance_type": "EPF", "company": "Acme", "payroll_period": "2026-01", "due_date": "2026-02-15"},
		]

		update_overdue_compliance_records()

		self.assertEqual(mock_set_value.call_count, 2)
		mock_set_value.assert_any_call(
			"Statutory Compliance Submission", "SCS-001", "submission_status", "Overdue"
		)
		mock_set_value.assert_any_call(
			"Statutory Compliance Submission", "SCS-002", "submission_status", "Overdue"
		)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.get_all")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.db.set_value")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.today")
	def test_no_action_when_no_overdue(self, mock_today, mock_set_value, mock_get_all):
		"""No set_value calls when no overdue records."""
		mock_today.return_value = "2026-02-10"
		mock_get_all.return_value = []

		update_overdue_compliance_records()

		mock_set_value.assert_not_called()


class TestDashboardStatus(FrappeTestCase):
	"""Tests for get_compliance_status_for_dashboard."""

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.get_all")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.today")
	def test_color_coding_green_amber_red(self, mock_today, mock_get_all):
		"""Records are bucketed into green/amber/red based on days remaining."""
		mock_today.return_value = "2026-02-10"
		mock_get_all.return_value = [
			{"name": "SCS-001", "compliance_type": "PCB", "company": "A", "payroll_period": "2026-01", "due_date": "2026-02-20", "submission_status": "Pending", "penalty_info": ""},
			{"name": "SCS-002", "compliance_type": "EPF", "company": "A", "payroll_period": "2026-01", "due_date": "2026-02-13", "submission_status": "Pending", "penalty_info": ""},
			{"name": "SCS-003", "compliance_type": "SOCSO", "company": "A", "payroll_period": "2026-01", "due_date": "2026-02-11", "submission_status": "Pending", "penalty_info": ""},
			{"name": "SCS-004", "compliance_type": "EIS", "company": "A", "payroll_period": "2026-01", "due_date": "2026-02-05", "submission_status": "Overdue", "penalty_info": ""},
		]

		result = get_compliance_status_for_dashboard()

		# SCS-001: 10 days remaining → green
		self.assertEqual(len(result["green"]), 1)
		self.assertEqual(result["green"][0]["name"], "SCS-001")

		# SCS-002: 3 days remaining → amber
		self.assertEqual(len(result["amber"]), 1)
		self.assertEqual(result["amber"][0]["name"], "SCS-002")

		# SCS-003: 1 day remaining → red
		# SCS-004: Overdue → red
		self.assertEqual(len(result["red"]), 2)
		red_names = {r["name"] for r in result["red"]}
		self.assertIn("SCS-003", red_names)
		self.assertIn("SCS-004", red_names)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.frappe.get_all")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.today")
	def test_empty_result_when_no_pending(self, mock_today, mock_get_all):
		"""All-submitted state returns empty buckets."""
		mock_today.return_value = "2026-02-10"
		mock_get_all.return_value = []

		result = get_compliance_status_for_dashboard()

		self.assertEqual(result["green"], [])
		self.assertEqual(result["amber"], [])
		self.assertEqual(result["red"], [])


class TestHooksRegistration(FrappeTestCase):
	"""Verify compliance_tracker is registered in hooks."""

	def test_payroll_entry_on_submit_hook_exists(self):
		"""hooks.py must register create_monthly_compliance_records for Payroll Entry."""
		import lhdn_payroll_integration.hooks as hooks_module

		doc_events = getattr(hooks_module, "doc_events", {})
		payroll_entry_events = doc_events.get("Payroll Entry", {})
		on_submit = payroll_entry_events.get("on_submit", [])

		if isinstance(on_submit, str):
			on_submit = [on_submit]

		self.assertTrue(
			any("compliance_tracker.create_monthly_compliance_records" in h for h in on_submit),
			msg="create_monthly_compliance_records not found in Payroll Entry on_submit hooks",
		)

	def test_daily_scheduler_update_overdue_registered(self):
		"""hooks.py must register update_overdue_compliance_records in daily scheduler."""
		import lhdn_payroll_integration.hooks as hooks_module

		daily = getattr(hooks_module, "scheduler_events", {}).get("daily", [])
		self.assertTrue(
			any("compliance_tracker.update_overdue_compliance_records" in h for h in daily),
			msg="update_overdue_compliance_records not found in daily scheduler_events",
		)

	def test_daily_scheduler_send_notifications_registered(self):
		"""hooks.py must register send_overdue_compliance_notifications in daily scheduler."""
		import lhdn_payroll_integration.hooks as hooks_module

		daily = getattr(hooks_module, "scheduler_events", {}).get("daily", [])
		self.assertTrue(
			any("compliance_tracker.send_overdue_compliance_notifications" in h for h in daily),
			msg="send_overdue_compliance_notifications not found in daily scheduler_events",
		)
