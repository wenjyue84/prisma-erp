"""Tests for worker type gate — TDD red phase (UT-031).

Tests verify that should_submit_to_lhdn and get_default_classification_code
correctly distinguish Employee vs Contractor vs Director.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock

from lhdn_payroll_integration.services.exemption_filter import should_submit_to_lhdn, get_default_classification_code


class TestWorkerTypeGate(FrappeTestCase):
	"""Test suite for worker type gate distinguishing Employee vs Contractor vs Director."""

	def _make_employee(self, worker_type="Employee", requires_self_billed=0):
		"""Create a mock Employee with worker type and self-billed flag."""
		emp = MagicMock()
		emp.custom_worker_type = worker_type
		emp.custom_requires_self_billed_einvoice = requires_self_billed
		emp.custom_lhdn_tin = "IG12345678901"
		return emp

	def test_regular_employee_always_exempt_regardless_of_flag(self):
		"""Regular employees (worker_type='Employee') must always be exempt
		from self-billed e-invoice, even if the flag is set."""
		emp = self._make_employee("Employee", requires_self_billed=1)
		doc = MagicMock()
		doc.doctype = "Salary Slip"

		result = should_submit_to_lhdn(doc, emp)
		self.assertFalse(result,
			"Regular employee must be exempt from self-billed e-invoice")

	def test_contractor_with_flag_is_in_scope(self):
		"""Contractors with custom_requires_self_billed_einvoice=1 must be
		in scope for LHDN submission."""
		emp = self._make_employee("Contractor", requires_self_billed=1)
		doc = MagicMock()
		doc.doctype = "Salary Slip"

		result = should_submit_to_lhdn(doc, emp)
		self.assertTrue(result,
			"Contractor with self-billed flag must be in scope")

	def test_director_with_flag_is_in_scope(self):
		"""Directors with custom_requires_self_billed_einvoice=1 must be
		in scope for LHDN submission."""
		emp = self._make_employee("Director", requires_self_billed=1)
		doc = MagicMock()
		doc.doctype = "Salary Slip"

		result = should_submit_to_lhdn(doc, emp)
		self.assertTrue(result,
			"Director with self-billed flag must be in scope")

	def test_director_default_classification_code_is_036(self):
		"""Directors must default to MSIC classification code '036'."""
		result = get_default_classification_code("Director")
		self.assertEqual(result, "036",
			f"Director default classification code must be '036', got '{result}'")

	def test_contractor_default_classification_code_is_037(self):
		"""Contractors must default to MSIC classification code '037'."""
		result = get_default_classification_code("Contractor")
		self.assertEqual(result, "037",
			f"Contractor default classification code must be '037', got '{result}'")

	def test_unknown_worker_type_defaults_to_exempt(self):
		"""Unknown worker types must default to exempt (not in scope)."""
		emp = self._make_employee("Intern", requires_self_billed=0)
		doc = MagicMock()
		doc.doctype = "Salary Slip"

		result = should_submit_to_lhdn(doc, emp)
		self.assertFalse(result,
			"Unknown worker type must default to exempt")
