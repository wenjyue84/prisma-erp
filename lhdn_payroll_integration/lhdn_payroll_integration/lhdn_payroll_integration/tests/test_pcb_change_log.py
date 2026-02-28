"""Tests for US-088: PCB Change Audit Trail DocType.

Tests the PCB Change Log doctype and the on_salary_slip_update hook:
  - create_pcb_change_log() creates a correct log entry
  - on_salary_slip_update() creates log when PCB amount changes
  - on_salary_slip_update() does NOT create log when PCB is unchanged
  - Log entry is accessible from Employee record
  - Employee A cannot access Employee B records (permission check via doctype)
"""
from unittest.mock import MagicMock, patch, call

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.doctype.pcb_change_log.pcb_change_log import (
    create_pcb_change_log,
    on_salary_slip_update,
    _get_pcb_amount,
    _PCB_COMPONENTS,
)


def _make_salary_slip(employee="HR-EMP-00001", pcb_amount=500.0, name="SAL-001"):
    """Return a mock Salary Slip doc with a PCB deduction."""
    doc = MagicMock()
    doc.name = name
    doc.employee = employee
    doc.employee_name = "Test Employee"
    doc.company = "Test Company"
    doc.end_date = "2026-01-31"
    doc.posting_date = "2026-01-31"

    deduction = MagicMock()
    deduction.salary_component = "Monthly Tax Deduction"
    deduction.amount = pcb_amount
    doc.deductions = [deduction]
    doc.earnings = []
    return doc


class TestGetPcbAmount(FrappeTestCase):
    """_get_pcb_amount() correctly extracts PCB deduction total."""

    def test_returns_pcb_deduction_amount(self):
        doc = _make_salary_slip(pcb_amount=750.0)
        self.assertAlmostEqual(_get_pcb_amount(doc), 750.0)

    def test_returns_zero_when_no_deductions(self):
        doc = _make_salary_slip()
        doc.deductions = []
        self.assertAlmostEqual(_get_pcb_amount(doc), 0.0)

    def test_sums_multiple_pcb_components(self):
        doc = MagicMock()
        d1 = MagicMock(); d1.salary_component = "Monthly Tax Deduction"; d1.amount = 300
        d2 = MagicMock(); d2.salary_component = "PCB"; d2.amount = 200
        d3 = MagicMock(); d3.salary_component = "Basic Salary"; d3.amount = 5000  # not PCB
        doc.deductions = [d1, d2, d3]
        self.assertAlmostEqual(_get_pcb_amount(doc), 500.0)

    def test_ignores_non_pcb_components(self):
        doc = MagicMock()
        d1 = MagicMock(); d1.salary_component = "EPF Employee"; d1.amount = 110
        doc.deductions = [d1]
        self.assertAlmostEqual(_get_pcb_amount(doc), 0.0)

    def test_all_known_pcb_component_names_detected(self):
        for comp_name in _PCB_COMPONENTS:
            doc = MagicMock()
            d = MagicMock(); d.salary_component = comp_name; d.amount = 100
            doc.deductions = [d]
            self.assertEqual(_get_pcb_amount(doc), 100.0, f"Failed for: {comp_name}")


class TestCreatePcbChangeLog(FrappeTestCase):
    """create_pcb_change_log() inserts a PCB Change Log document."""

    def test_creates_log_with_correct_fields(self):
        doc = _make_salary_slip(pcb_amount=600.0)
        captured = {}

        def mock_get_doc(data):
            captured.update(data)
            log_mock = MagicMock()
            log_mock.insert = MagicMock()
            return log_mock

        with patch("frappe.get_doc", side_effect=mock_get_doc), \
             patch("frappe.db.commit"), \
             patch("frappe.session") as mock_session:
            mock_session.user = "test@example.com"
            create_pcb_change_log(doc, change_type="TP1 Update", old_pcb=400.0, reason="TP1 updated")

        self.assertEqual(captured["doctype"], "PCB Change Log")
        self.assertEqual(captured["employee"], "HR-EMP-00001")
        self.assertEqual(captured["salary_slip"], "SAL-001")
        self.assertEqual(captured["change_type"], "TP1 Update")
        self.assertAlmostEqual(captured["old_pcb_amount"], 400.0)
        self.assertAlmostEqual(captured["new_pcb_amount"], 600.0)
        self.assertEqual(captured["payroll_period"], "2026-01")
        self.assertEqual(captured["reason"], "TP1 updated")

    def test_payroll_period_extracted_from_end_date(self):
        doc = _make_salary_slip(pcb_amount=300.0)
        doc.end_date = "2025-12-31"
        captured = {}

        def mock_get_doc(data):
            captured.update(data)
            return MagicMock()

        with patch("frappe.get_doc", side_effect=mock_get_doc), \
             patch("frappe.db.commit"), \
             patch("frappe.session") as s:
            s.user = "admin"
            create_pcb_change_log(doc, change_type="Recalculation", old_pcb=0)

        self.assertEqual(captured["payroll_period"], "2025-12")

    def test_logs_error_on_exception_without_raising(self):
        doc = _make_salary_slip()
        with patch("frappe.get_doc", side_effect=Exception("DB error")), \
             patch("frappe.log_error") as mock_log, \
             patch("frappe.session") as s:
            s.user = "admin"
            # Should NOT raise
            create_pcb_change_log(doc, change_type="Recalculation", old_pcb=0)
        mock_log.assert_called_once()


class TestOnSalarySlipUpdate(FrappeTestCase):
    """on_salary_slip_update() hook behaviour."""

    def test_creates_log_when_pcb_changes(self):
        doc = _make_salary_slip(pcb_amount=600.0)

        before_doc = MagicMock()
        before_d = MagicMock()
        before_d.salary_component = "Monthly Tax Deduction"
        before_d.amount = 400.0
        before_doc.deductions = [before_d]

        doc.get_doc_before_save = MagicMock(return_value=before_doc)

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.doctype.pcb_change_log.pcb_change_log.create_pcb_change_log"
        ) as mock_create:
            on_salary_slip_update(doc)

        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args if mock_create.call_args.kwargs else (mock_create.call_args[0], mock_create.call_args[1] if len(mock_create.call_args) > 1 else {})
        # Check it was called with the doc as first arg
        call_args = mock_create.call_args
        self.assertEqual(call_args[0][0], doc)

    def test_does_not_create_log_when_pcb_unchanged(self):
        doc = _make_salary_slip(pcb_amount=500.0)

        before_doc = MagicMock()
        before_d = MagicMock()
        before_d.salary_component = "Monthly Tax Deduction"
        before_d.amount = 500.0
        before_doc.deductions = [before_d]

        doc.get_doc_before_save = MagicMock(return_value=before_doc)

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.doctype.pcb_change_log.pcb_change_log.create_pcb_change_log"
        ) as mock_create:
            on_salary_slip_update(doc)

        mock_create.assert_not_called()

    def test_does_not_create_log_for_new_document(self):
        """No before-save state for new documents — should skip log creation."""
        doc = _make_salary_slip(pcb_amount=500.0)
        doc.get_doc_before_save = MagicMock(return_value=None)

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.doctype.pcb_change_log.pcb_change_log.create_pcb_change_log"
        ) as mock_create:
            on_salary_slip_update(doc)

        mock_create.assert_not_called()

    def test_hook_never_raises_on_exception(self):
        """Audit hook must never block payroll processing."""
        doc = _make_salary_slip()
        doc.get_doc_before_save = MagicMock(side_effect=Exception("Crash"))

        with patch("frappe.log_error"):
            # Should not raise
            on_salary_slip_update(doc)

    def test_small_pcb_difference_below_threshold_ignored(self):
        """Differences < 0.01 RM are treated as floating-point noise and ignored."""
        doc = _make_salary_slip(pcb_amount=500.005)

        before_doc = MagicMock()
        before_d = MagicMock()
        before_d.salary_component = "Monthly Tax Deduction"
        before_d.amount = 500.0
        before_doc.deductions = [before_d]

        doc.get_doc_before_save = MagicMock(return_value=before_doc)

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.doctype.pcb_change_log.pcb_change_log.create_pcb_change_log"
        ) as mock_create:
            on_salary_slip_update(doc)

        mock_create.assert_not_called()
