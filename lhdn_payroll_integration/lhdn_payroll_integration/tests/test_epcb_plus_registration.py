"""Tests for US-116: e-PCB Plus Registration Status enforcement on CP39 generation.

Acceptance criteria:
  - Company has 'LHDN e-PCB Plus Settings' section custom fields
  - CP39 submission raises ValidationError when company is NOT registered on e-PCB Plus
  - CP39 submission proceeds normally when company IS registered
"""
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service import (
    _validate_epcb_plus_registration,
    submit_cp39_to_lhdn,
)


class TestEpcbPlusCustomFields(FrappeTestCase):
    """Verify that e-PCB Plus custom fields exist on the Company DocType."""

    def _field_exists(self, fieldname):
        return frappe.db.exists(
            "Custom Field", {"dt": "Company", "fieldname": fieldname}
        )

    def test_epcb_registration_status_field_exists(self):
        """custom_epcb_plus_registration_status must exist as Custom Field on Company."""
        self.assertTrue(
            self._field_exists("custom_epcb_plus_registration_status"),
            "custom_epcb_plus_registration_status Custom Field missing on Company",
        )

    def test_epcb_employer_e_number_field_exists(self):
        """custom_epcb_plus_employer_e_number must exist as Custom Field on Company."""
        self.assertTrue(
            self._field_exists("custom_epcb_plus_employer_e_number"),
            "custom_epcb_plus_employer_e_number Custom Field missing on Company",
        )

    def test_epcb_pcb_admin_nric_field_exists(self):
        """custom_epcb_plus_pcb_admin_nric must exist as Custom Field on Company."""
        self.assertTrue(
            self._field_exists("custom_epcb_plus_pcb_admin_nric"),
            "custom_epcb_plus_pcb_admin_nric Custom Field missing on Company",
        )

    def test_epcb_pcb_admin_name_field_exists(self):
        """custom_epcb_plus_pcb_admin_name must exist as Custom Field on Company."""
        self.assertTrue(
            self._field_exists("custom_epcb_plus_pcb_admin_name"),
            "custom_epcb_plus_pcb_admin_name Custom Field missing on Company",
        )

    def test_epcb_employer_rep_nric_field_exists(self):
        """custom_epcb_plus_employer_rep_nric must exist as Custom Field on Company."""
        self.assertTrue(
            self._field_exists("custom_epcb_plus_employer_rep_nric"),
            "custom_epcb_plus_employer_rep_nric Custom Field missing on Company",
        )

    def test_epcb_section_field_exists(self):
        """custom_epcb_plus_section Section Break must exist on Company."""
        self.assertTrue(
            self._field_exists("custom_epcb_plus_section"),
            "custom_epcb_plus_section Section Break Custom Field missing on Company",
        )


class TestEpcbPlusValidation(FrappeTestCase):
    """Test _validate_epcb_plus_registration raises on unregistered company."""

    def test_unregistered_company_raises_validation_error(self):
        """Raises ValidationError when registration status is 'Not Registered'."""
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("No Company found")

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service.frappe.db.get_value",
            return_value="Not Registered",
        ):
            with self.assertRaises(frappe.ValidationError) as ctx:
                _validate_epcb_plus_registration(company)
        self.assertIn("e-PCB Plus", str(ctx.exception))
        self.assertIn("Not Registered", str(ctx.exception))

    def test_none_status_raises_validation_error(self):
        """Raises ValidationError when registration status is None (never set)."""
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("No Company found")

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service.frappe.db.get_value",
            return_value=None,
        ):
            with self.assertRaises(frappe.ValidationError):
                _validate_epcb_plus_registration(company)

    def test_registered_company_does_not_raise(self):
        """Does NOT raise when registration status is 'Registered'."""
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("No Company found")

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service.frappe.db.get_value",
            return_value="Registered",
        ):
            # Should not raise
            _validate_epcb_plus_registration(company)


class TestEpcbPlusCP39Gate(FrappeTestCase):
    """Integration: submit_cp39_to_lhdn is blocked on unregistered company."""

    def _get_company(self):
        return frappe.db.get_value("Company", {}, "name")

    def test_cp39_blocked_when_not_registered(self):
        """submit_cp39_to_lhdn raises ValidationError on unregistered company."""
        company = self._get_company()
        if not company:
            self.skipTest("No Company found")

        _svc = "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service"
        with patch(
            f"{_svc}.frappe.db.get_value",
            return_value="Not Registered",
        ):
            with self.assertRaises(frappe.ValidationError) as ctx:
                submit_cp39_to_lhdn(company, "01", 2025)
        self.assertIn("e-PCB Plus registration is required", str(ctx.exception))

    def test_cp39_proceeds_when_registered(self):
        """submit_cp39_to_lhdn proceeds (calls auth) when company is Registered."""
        company = self._get_company()
        if not company:
            self.skipTest("No Company found")

        _svc = "lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service"

        mock_submit_resp = MagicMock()
        mock_submit_resp.status_code = 200
        mock_submit_resp.text = '{"submissionReference": "CP39-TEST-001"}'
        mock_submit_resp.json.return_value = {"submissionReference": "CP39-TEST-001"}

        mock_rows = [
            {
                "employer_e_number": "E99999",
                "month_year": "01/2025",
                "employee_tin": "IG001",
                "employee_nric": "900101011234",
                "employee_name": "Test Employee",
                "pcb_category": "1",
                "gross_remuneration": 5000.0,
                "epf_employee": 550.0,
                "zakat_amount": 0.0,
                "cp38_amount": 0.0,
                "total_pcb": 200.0,
            }
        ]

        with patch(f"{_svc}._validate_epcb_plus_registration"), \
             patch(f"{_svc}._get_mytax_access_token", return_value="tok-xyz"), \
             patch(f"{_svc}.requests.post", return_value=mock_submit_resp), \
             patch(f"{_svc}.get_data", return_value=mock_rows), \
             patch(f"{_svc}._store_submission_log", return_value="LOG-001"):
            result = submit_cp39_to_lhdn(company, "01", 2025)

        self.assertTrue(result["success"])
        self.assertEqual(result["reference"], "CP39-TEST-001")
