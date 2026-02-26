"""Tests for RBAC field visibility on LHDN custom fields — TDD red phase (UT-021).

Tests verify that:
- HR User cannot see sensitive LHDN fields (UUID, QR code, error log)
- HR Manager can see all LHDN fields
- custom_requires_self_billed_invoice on Employee is restricted to HR Manager
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestRBAC(FrappeTestCase):
	"""Test suite for role-based access control on LHDN custom fields."""

	def test_hr_user_cannot_see_lhdn_uuid_field(self):
		"""custom_lhdn_uuid on Salary Slip must have permlevel >= 1
		so that HR User (who only has permlevel=0 access) cannot see it."""
		meta = frappe.get_meta("Salary Slip")
		field = meta.get_field("custom_lhdn_uuid")

		self.assertIsNotNone(field,
			"custom_lhdn_uuid field not found on Salary Slip")
		self.assertGreaterEqual(field.permlevel, 1,
			f"custom_lhdn_uuid permlevel is {field.permlevel}, "
			f"expected >= 1 to hide from HR User")

	def test_hr_manager_can_see_all_lhdn_fields(self):
		"""HR Manager role must have Read permission at permlevel=1 on Salary Slip
		to see all LHDN response fields."""
		# Check that there is a DocPerm entry for Salary Slip with role=HR Manager
		# and permlevel=1 and read=1
		perms = frappe.get_all(
			"DocPerm",
			filters={
				"parent": "Salary Slip",
				"role": "HR Manager",
				"permlevel": 1,
				"read": 1,
			},
			fields=["name"],
		)

		self.assertTrue(len(perms) > 0,
			"HR Manager role must have Read permission at permlevel=1 "
			"on Salary Slip to see LHDN fields")

	def test_requires_self_billed_field_restricted_to_hr_manager(self):
		"""custom_requires_self_billed_invoice on Employee must have permlevel >= 1
		so only HR Manager (not HR User) can edit it."""
		meta = frappe.get_meta("Employee")
		field = meta.get_field("custom_requires_self_billed_invoice")

		self.assertIsNotNone(field,
			"custom_requires_self_billed_invoice field not found on Employee")
		self.assertGreaterEqual(field.permlevel, 1,
			f"custom_requires_self_billed_invoice permlevel is {field.permlevel}, "
			f"expected >= 1 to restrict to HR Manager")
