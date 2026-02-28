"""Tests for US-086: XAdES XML Digital Signature for MyInvois Self-Billed Phase 2.

Tests the xml_signer utility module:
  - sign_xml() returns original XML when xmlsec not available
  - sign_xml() returns original XML when xmlsec is available but cert path is invalid
  - maybe_sign_xml() returns original XML when signing is disabled
  - maybe_sign_xml() returns original XML when cert path is empty
  - get_company_signing_config() returns correct defaults
  - payload_builder functions return valid XML (unsigned) when signing flag off
"""
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.xml_signer import (
    sign_xml,
    maybe_sign_xml,
    get_company_signing_config,
)


SAMPLE_XML = '<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<Invoice><ID>TEST-001</ID></Invoice>'


class TestXmlSignerFallback(FrappeTestCase):
    """sign_xml() gracefully degrades when xmlsec is unavailable."""

    def test_returns_original_when_xmlsec_not_available(self):
        """When xmlsec cannot be imported, sign_xml returns original XML unchanged."""
        with patch("lhdn_payroll_integration.utils.xml_signer._xmlsec_available", return_value=False):
            result = sign_xml(SAMPLE_XML, "/fake/path/cert.pem")
        self.assertEqual(result, SAMPLE_XML)

    def test_returns_original_when_cert_path_invalid(self):
        """When xmlsec is available but cert path does not exist, returns original XML."""
        try:
            import xmlsec  # noqa: F401
            xmlsec_available = True
        except ImportError:
            xmlsec_available = False

        if not xmlsec_available:
            # Skip gracefully if xmlsec not installed
            self.skipTest("xmlsec not installed — testing fallback only")

        result = sign_xml(SAMPLE_XML, "/nonexistent/path/cert.pem")
        # Should return original XML on error
        self.assertEqual(result, SAMPLE_XML)

    def test_returns_original_for_invalid_xml(self):
        """sign_xml returns original string when XML is malformed."""
        bad_xml = "not xml at all <<<>>>"
        with patch("lhdn_payroll_integration.utils.xml_signer._xmlsec_available", return_value=False):
            result = sign_xml(bad_xml, "/fake/cert.pem")
        self.assertEqual(result, bad_xml)


class TestMaybeSignXml(FrappeTestCase):
    """maybe_sign_xml() uses company config to decide whether to sign."""

    def test_returns_original_when_signing_disabled(self):
        """When custom_enable_xml_signature=0, maybe_sign_xml returns original XML."""
        mock_company = MagicMock()
        mock_company.custom_enable_xml_signature = 0
        mock_company.custom_digital_cert_path = ""
        mock_company.custom_digital_cert_password = ""

        with patch("frappe.get_doc", return_value=mock_company):
            result = maybe_sign_xml(SAMPLE_XML, "Test Company")

        self.assertEqual(result, SAMPLE_XML)

    def test_returns_original_when_cert_path_empty(self):
        """When signing enabled but cert_path is empty, returns original XML with warning."""
        mock_company = MagicMock()
        mock_company.custom_enable_xml_signature = 1
        mock_company.custom_digital_cert_path = ""
        mock_company.custom_digital_cert_password = ""

        with patch("frappe.get_doc", return_value=mock_company):
            result = maybe_sign_xml(SAMPLE_XML, "Test Company")

        # No cert path → skip signing, return original
        self.assertEqual(result, SAMPLE_XML)

    def test_calls_sign_xml_when_enabled_and_path_set(self):
        """When signing enabled and cert_path set, sign_xml is invoked."""
        mock_company = MagicMock()
        mock_company.custom_enable_xml_signature = 1
        mock_company.custom_digital_cert_path = "/path/to/cert.pem"
        mock_company.custom_digital_cert_password = "secret"

        with patch("frappe.get_doc", return_value=mock_company):
            with patch(
                "lhdn_payroll_integration.utils.xml_signer.sign_xml",
                return_value="<signed/>",
            ) as mock_sign:
                result = maybe_sign_xml(SAMPLE_XML, "Test Company")

        mock_sign.assert_called_once_with(SAMPLE_XML, "/path/to/cert.pem", "secret")
        self.assertEqual(result, "<signed/>")

    def test_returns_original_when_frappe_get_doc_fails(self):
        """When company doc cannot be fetched, maybe_sign_xml returns original XML."""
        with patch("frappe.get_doc", side_effect=Exception("Company not found")):
            result = maybe_sign_xml(SAMPLE_XML, "NonExistentCo")
        self.assertEqual(result, SAMPLE_XML)


class TestGetCompanySigningConfig(FrappeTestCase):
    """get_company_signing_config() reads Company doc fields."""

    def test_returns_enabled_false_when_flag_off(self):
        """When custom_enable_xml_signature=0, config.enabled is False."""
        mock_company = MagicMock()
        mock_company.custom_enable_xml_signature = 0
        mock_company.custom_digital_cert_path = "/path/cert.pem"
        mock_company.custom_digital_cert_password = "pw"

        with patch("frappe.get_doc", return_value=mock_company):
            config = get_company_signing_config("Test Company")

        self.assertFalse(config["enabled"])
        self.assertEqual(config["cert_path"], "/path/cert.pem")

    def test_returns_enabled_true_when_flag_on(self):
        """When custom_enable_xml_signature=1, config.enabled is True."""
        mock_company = MagicMock()
        mock_company.custom_enable_xml_signature = 1
        mock_company.custom_digital_cert_path = "/path/cert.pem"
        mock_company.custom_digital_cert_password = "pw"

        with patch("frappe.get_doc", return_value=mock_company):
            config = get_company_signing_config("Test Company")

        self.assertTrue(config["enabled"])

    def test_returns_safe_defaults_on_error(self):
        """When Company doc fetch fails, returns safe defaults (signing off)."""
        with patch("frappe.get_doc", side_effect=Exception("DB error")):
            config = get_company_signing_config("BadCompany")

        self.assertFalse(config["enabled"])
        self.assertEqual(config["cert_path"], "")

    def test_strips_whitespace_from_cert_path(self):
        """cert_path is stripped of leading/trailing whitespace."""
        mock_company = MagicMock()
        mock_company.custom_enable_xml_signature = 1
        mock_company.custom_digital_cert_path = "  /path/cert.pem  "
        mock_company.custom_digital_cert_password = ""

        with patch("frappe.get_doc", return_value=mock_company):
            config = get_company_signing_config("Test Company")

        self.assertEqual(config["cert_path"], "/path/cert.pem")


class TestPayloadBuilderWithSigningDisabled(FrappeTestCase):
    """payload_builder functions still produce valid XML when signing is off."""

    def _make_salary_slip_mocks(self):
        doc = MagicMock()
        doc.name = "SAL-SLP-TEST-001"
        doc.employee = "HR-EMP-00001"
        doc.employee_name = "Ahmad bin Abdullah"
        doc.net_pay = 5000
        doc.company = "Test Company"
        doc.posting_date = "2026-01-31"
        doc.currency = "MYR"
        doc.conversion_rate = 1

        earning = MagicMock()
        earning.salary_component = "Basic Salary"
        earning.amount = 5000
        earning.custom_lhdn_classification_code = "022 : Others"
        doc.earnings = [earning]
        doc.deductions = []

        employee = MagicMock()
        employee.custom_lhdn_tin = "IG12345678901"
        employee.custom_id_type = "NRIC"
        employee.custom_id_value = "901201145678"
        employee.employee_name = "Ahmad bin Abdullah"
        employee.custom_is_foreign_worker = 0
        employee.custom_state_code = "01"
        employee.custom_bank_account_number = None
        employee.custom_worker_type = "Employee"

        company = MagicMock()
        company.custom_company_tin_number = "C12345678901"
        company.name = "Test Company"
        company.company_name = "Test Company Sdn Bhd"
        company.custom_state_code = "14"
        company.custom_enable_xml_signature = 0
        company.custom_digital_cert_path = ""
        company.custom_digital_cert_password = ""

        return doc, employee, company

    def test_unsigned_xml_is_valid_when_signing_off(self):
        """build_salary_slip_xml returns parseable XML when signing flag is off."""
        from lhdn_payroll_integration.services.payload_builder import build_salary_slip_xml

        doc, employee, company = self._make_salary_slip_mocks()

        with patch("frappe.get_doc") as mock_get_doc, \
             patch("frappe.db.get_value", return_value=0):
            mock_get_doc.side_effect = lambda dt, name: {
                "Salary Slip": doc,
                "Employee": employee,
                "Company": company,
            }.get(dt, MagicMock())

            xml_result = build_salary_slip_xml("SAL-SLP-TEST-001")

        # Should be parseable XML
        root = ET.fromstring(xml_result.split("?>", 1)[-1].strip())
        self.assertIsNotNone(root)

    def test_xml_contains_invoice_id(self):
        """Unsigned XML contains the expected document ID element."""
        from lhdn_payroll_integration.services.payload_builder import build_salary_slip_xml

        doc, employee, company = self._make_salary_slip_mocks()

        with patch("frappe.get_doc") as mock_get_doc, \
             patch("frappe.db.get_value", return_value=0):
            mock_get_doc.side_effect = lambda dt, name: {
                "Salary Slip": doc,
                "Employee": employee,
                "Company": company,
            }.get(dt, MagicMock())

            xml_result = build_salary_slip_xml("SAL-SLP-TEST-001")

        self.assertIn("SAL-SLP-TEST-001", xml_result)
