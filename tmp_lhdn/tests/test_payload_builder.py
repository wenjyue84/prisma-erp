"""Tests for Salary Slip and Expense Claim XML payload builders.

Tests build_salary_slip_xml(), build_expense_claim_xml(), and
prepare_submission_wrapper() functions.
"""
import base64
import hashlib
import xml.etree.ElementTree as ET

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch
from decimal import Decimal

from lhdn_payroll_integration.services.payload_builder import (
    build_salary_slip_xml,
    build_expense_claim_xml,
    prepare_submission_wrapper,
)

UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"


class TestSalarySlipXMLBuilder(FrappeTestCase):
    """Test build_salary_slip_xml(docname) XML generation logic."""

    def _make_salary_slip_doc(self, employee_name="HR-EMP-00001", net_pay=5000,
                               is_foreign=False):
        """Create a mock Salary Slip doc with earnings rows."""
        doc = MagicMock()
        doc.name = "SAL-SLP-00001"
        doc.employee = employee_name
        doc.employee_name = "Ahmad bin Abdullah"
        doc.net_pay = net_pay
        doc.company = "Arising Packaging"
        doc.posting_date = "2026-01-31"

        # Earnings rows
        earning1 = MagicMock()
        earning1.salary_component = "Basic Salary"
        earning1.amount = 4000
        earning1.custom_lhdn_classification_code = "022 : Others"

        earning2 = MagicMock()
        earning2.salary_component = "Allowance"
        earning2.amount = 1000
        earning2.custom_lhdn_classification_code = "022 : Others"

        doc.earnings = [earning1, earning2]
        doc.deductions = []

        return doc

    def _make_employee_doc(self, is_foreign=False):
        """Create a mock Employee doc with LHDN fields."""
        emp = MagicMock()
        emp.custom_lhdn_tin = "IG12345678901"
        emp.custom_id_type = "NRIC"
        emp.custom_id_value = "901201145678"
        emp.employee_name = "Ahmad bin Abdullah"
        emp.custom_is_foreign_worker = 1 if is_foreign else 0
        return emp

    def _make_company_doc(self):
        """Create a mock Company doc with LHDN fields."""
        company = MagicMock()
        company.custom_company_tin_number = "C12345678901"
        company.name = "Arising Packaging"
        company.company_name = "Arising Packaging Sdn Bhd"
        return company

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_build_salary_slip_xml_returns_string(self, mock_frappe):
        """build_salary_slip_xml returns a valid XML string with correct root element."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-00001")

        self.assertIsInstance(xml_string, str)
        # Parse XML and check root element
        root = ET.fromstring(xml_string)
        self.assertEqual(root.tag, f"{{{UBL_NS}}}Invoice")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_invoice_type_code_is_11(self, mock_frappe):
        """InvoiceTypeCode element contains '11' (self-billed invoice)."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-00001")
        root = ET.fromstring(xml_string)

        type_code = root.find(f".//{{{CBC_NS}}}InvoiceTypeCode")
        self.assertIsNotNone(type_code, "InvoiceTypeCode element not found")
        self.assertEqual(type_code.text, "11")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_supplier_is_employee_payee(self, mock_frappe):
        """AccountingSupplierParty contains employee TIN and name (payee = supplier)."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-00001")
        root = ET.fromstring(xml_string)

        supplier = root.find(f".//{{{CAC_NS}}}AccountingSupplierParty")
        self.assertIsNotNone(supplier, "AccountingSupplierParty not found")

        # Employee TIN should be in supplier party
        supplier_xml = ET.tostring(supplier, encoding="unicode")
        self.assertIn("IG12345678901", supplier_xml)
        self.assertIn("Ahmad bin Abdullah", supplier_xml)

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_buyer_is_employer_payer(self, mock_frappe):
        """AccountingCustomerParty contains company TIN and name (payer = buyer)."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-00001")
        root = ET.fromstring(xml_string)

        customer = root.find(f".//{{{CAC_NS}}}AccountingCustomerParty")
        self.assertIsNotNone(customer, "AccountingCustomerParty not found")

        # Company TIN should be in customer party
        customer_xml = ET.tostring(customer, encoding="unicode")
        self.assertIn("C12345678901", customer_xml)
        self.assertIn("Arising Packaging", customer_xml)

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_foreign_worker_tin_is_ei00000000010(self, mock_frappe):
        """For foreign worker employee, SupplierTIN = 'EI00000000010'."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee_doc(is_foreign=True)
        emp.custom_lhdn_tin = "EI00000000010"  # Foreign worker TIN
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-00001")
        root = ET.fromstring(xml_string)

        supplier = root.find(f".//{{{CAC_NS}}}AccountingSupplierParty")
        supplier_xml = ET.tostring(supplier, encoding="unicode")
        self.assertIn("EI00000000010", supplier_xml)

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_totals_balance_exact(self, mock_frappe):
        """TotalExcludingTax + TotalTaxAmount == TotalIncludingTax (exact Decimal, 2dp)."""
        doc = self._make_salary_slip_doc(net_pay=5000)
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-00001")
        root = ET.fromstring(xml_string)

        # Find LegalMonetaryTotal
        monetary_total = root.find(f".//{{{CAC_NS}}}LegalMonetaryTotal")
        self.assertIsNotNone(monetary_total, "LegalMonetaryTotal not found")

        tax_excl = monetary_total.find(f"{{{CBC_NS}}}TaxExclusiveAmount")
        tax_incl = monetary_total.find(f"{{{CBC_NS}}}TaxInclusiveAmount")
        self.assertIsNotNone(tax_excl, "TaxExclusiveAmount not found")
        self.assertIsNotNone(tax_incl, "TaxInclusiveAmount not found")

        # Find TaxTotal/TaxAmount
        tax_total = root.find(f".//{{{CAC_NS}}}TaxTotal/{{{CBC_NS}}}TaxAmount")
        self.assertIsNotNone(tax_total, "TaxTotal/TaxAmount not found")

        # Exact Decimal comparison
        excl = Decimal(tax_excl.text)
        incl = Decimal(tax_incl.text)
        tax = Decimal(tax_total.text)

        self.assertEqual(excl + tax, incl,
                         f"Totals don't balance: {excl} + {tax} != {incl}")

        # Verify 2 decimal places
        self.assertEqual(excl, excl.quantize(Decimal("0.01")))
        self.assertEqual(incl, incl.quantize(Decimal("0.01")))
        self.assertEqual(tax, tax.quantize(Decimal("0.01")))

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_ytd_fields_not_accessed(self, mock_frappe):
        """YTD fields (doc.ytd_net_pay, doc.year_to_date) are never accessed."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        # Set up PropertyMock to track attribute access
        doc.configure_mock(**{"ytd_net_pay": MagicMock(), "year_to_date": MagicMock()})

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        # Reset access tracking after mock setup
        type(doc).ytd_net_pay = property(lambda self: (_ for _ in ()).throw(
            AssertionError("ytd_net_pay was accessed")))
        type(doc).year_to_date = property(lambda self: (_ for _ in ()).throw(
            AssertionError("year_to_date was accessed")))

        # Build XML — should NOT access ytd_net_pay or year_to_date
        # If the implementation accesses these, PropertyMock will record it
        # and we can check
        try:
            xml_string = build_salary_slip_xml("SAL-SLP-00001")
        except (AssertionError, AttributeError):
            self.fail("build_salary_slip_xml accessed YTD fields which should not be used")


class TestExpenseClaimXMLBuilder(FrappeTestCase):
    """Test build_expense_claim_xml(docname) XML generation logic."""

    def _make_expense_claim_doc(self, employee="HR-EMP-00001"):
        """Create a mock Expense Claim doc with expenses rows."""
        doc = MagicMock()
        doc.name = "HR-EXP-00001"
        doc.employee = employee
        doc.employee_name = "Ahmad bin Abdullah"
        doc.company = "Arising Packaging"
        doc.posting_date = "2026-01-31"
        doc.total_sanctioned_amount = 850
        doc.custom_expense_category = "Self-Billed Required"

        # Expenses rows (Expense Claim child table)
        expense1 = MagicMock()
        expense1.expense_type = "Travel"
        expense1.sanctioned_amount = 500
        expense1.custom_lhdn_classification_code = "036 : Self-billed - Others"

        expense2 = MagicMock()
        expense2.expense_type = "Office Supplies"
        expense2.sanctioned_amount = 350
        expense2.custom_lhdn_classification_code = "036 : Self-billed - Others"

        doc.expenses = [expense1, expense2]

        return doc

    def _make_employee_doc(self, is_foreign=False):
        """Create a mock Employee doc with LHDN fields."""
        emp = MagicMock()
        emp.custom_lhdn_tin = "IG12345678901"
        emp.custom_id_type = "NRIC"
        emp.custom_id_value = "901201145678"
        emp.employee_name = "Ahmad bin Abdullah"
        emp.custom_is_foreign_worker = 1 if is_foreign else 0
        return emp

    def _make_company_doc(self):
        """Create a mock Company doc with LHDN fields."""
        company = MagicMock()
        company.custom_company_tin_number = "C12345678901"
        company.name = "Arising Packaging"
        company.company_name = "Arising Packaging Sdn Bhd"
        return company

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_build_expense_claim_xml_returns_valid_xml(self, mock_frappe):
        """build_expense_claim_xml returns a valid XML string with Invoice root."""
        doc = self._make_expense_claim_doc()
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Expense Claim", "HR-EXP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_expense_claim_xml("HR-EXP-00001")

        self.assertIsInstance(xml_string, str)
        root = ET.fromstring(xml_string)
        self.assertEqual(root.tag, f"{{{UBL_NS}}}Invoice")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_invoice_type_code_is_11(self, mock_frappe):
        """Expense Claim e-Invoice uses InvoiceTypeCode '11' (self-billed)."""
        doc = self._make_expense_claim_doc()
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Expense Claim", "HR-EXP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_expense_claim_xml("HR-EXP-00001")
        root = ET.fromstring(xml_string)

        type_code = root.find(f".//{{{CBC_NS}}}InvoiceTypeCode")
        self.assertIsNotNone(type_code, "InvoiceTypeCode element not found")
        self.assertEqual(type_code.text, "11")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_line_items_from_expenses_table(self, mock_frappe):
        """InvoiceLine count matches number of rows in expenses child table."""
        doc = self._make_expense_claim_doc()
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Expense Claim", "HR-EXP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_expense_claim_xml("HR-EXP-00001")
        root = ET.fromstring(xml_string)

        lines = root.findall(f".//{{{CAC_NS}}}InvoiceLine")
        self.assertEqual(len(lines), len(doc.expenses),
                         f"Expected {len(doc.expenses)} InvoiceLines, got {len(lines)}")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_total_matches_total_sanctioned_amount(self, mock_frappe):
        """LegalMonetaryTotal TaxExclusiveAmount equals sum of sanctioned_amount."""
        doc = self._make_expense_claim_doc()
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Expense Claim", "HR-EXP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_expense_claim_xml("HR-EXP-00001")
        root = ET.fromstring(xml_string)

        monetary_total = root.find(f".//{{{CAC_NS}}}LegalMonetaryTotal")
        self.assertIsNotNone(monetary_total, "LegalMonetaryTotal not found")

        tax_excl = monetary_total.find(f"{{{CBC_NS}}}TaxExclusiveAmount")
        self.assertIsNotNone(tax_excl, "TaxExclusiveAmount not found")

        # Total should match sum of sanctioned amounts from expenses rows
        expected = sum(Decimal(str(e.sanctioned_amount)) for e in doc.expenses)
        expected = expected.quantize(Decimal("0.01"))
        self.assertEqual(Decimal(tax_excl.text), expected,
                         f"TaxExclusiveAmount {tax_excl.text} != expected {expected}")

        # Verify totals balance: excl + tax == incl
        tax_incl = monetary_total.find(f"{{{CBC_NS}}}TaxInclusiveAmount")
        tax_amount = root.find(f".//{{{CAC_NS}}}TaxTotal/{{{CBC_NS}}}TaxAmount")
        self.assertIsNotNone(tax_incl)
        self.assertIsNotNone(tax_amount)

        excl = Decimal(tax_excl.text)
        incl = Decimal(tax_incl.text)
        tax = Decimal(tax_amount.text)
        self.assertEqual(excl + tax, incl,
                         f"Totals don't balance: {excl} + {tax} != {incl}")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_same_buyer_supplier_inversion_as_salary_slip(self, mock_frappe):
        """Employee is Supplier (payee), Company is Customer (payer) -- same as Salary Slip."""
        doc = self._make_expense_claim_doc()
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Expense Claim", "HR-EXP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_expense_claim_xml("HR-EXP-00001")
        root = ET.fromstring(xml_string)

        # Supplier = Employee (payee)
        supplier = root.find(f".//{{{CAC_NS}}}AccountingSupplierParty")
        self.assertIsNotNone(supplier, "AccountingSupplierParty not found")
        supplier_xml = ET.tostring(supplier, encoding="unicode")
        self.assertIn("IG12345678901", supplier_xml,
                       "Employee TIN not found in SupplierParty")
        self.assertIn("Ahmad bin Abdullah", supplier_xml,
                       "Employee name not found in SupplierParty")

        # Customer = Company (payer)
        customer = root.find(f".//{{{CAC_NS}}}AccountingCustomerParty")
        self.assertIsNotNone(customer, "AccountingCustomerParty not found")
        customer_xml = ET.tostring(customer, encoding="unicode")
        self.assertIn("C12345678901", customer_xml,
                       "Company TIN not found in CustomerParty")
        self.assertIn("Arising Packaging", customer_xml,
                       "Company name not found in CustomerParty")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_expense_type_classification_code_used(self, mock_frappe):
        """Each InvoiceLine uses the classification code from the expense row."""
        doc = self._make_expense_claim_doc()
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        # Set distinct classification codes per row to verify mapping
        doc.expenses[0].custom_lhdn_classification_code = "036 : Self-billed - Others"
        doc.expenses[1].custom_lhdn_classification_code = "037 : Self-billed - Monetary payment for employer's own services"

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Expense Claim", "HR-EXP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_expense_claim_xml("HR-EXP-00001")
        root = ET.fromstring(xml_string)

        lines = root.findall(f".//{{{CAC_NS}}}InvoiceLine")
        self.assertEqual(len(lines), 2)

        # First line should have classification code 036
        code1 = lines[0].find(
            f".//{{{CAC_NS}}}CommodityClassification/{{{CBC_NS}}}ItemClassificationCode"
        )
        self.assertIsNotNone(code1, "First line missing classification code")
        self.assertEqual(code1.text, "036")

        # Second line should have classification code 037
        code2 = lines[1].find(
            f".//{{{CAC_NS}}}CommodityClassification/{{{CBC_NS}}}ItemClassificationCode"
        )
        self.assertIsNotNone(code2, "Second line missing classification code")
        self.assertEqual(code2.text, "037")


class TestSubmissionWrapper(FrappeTestCase):
    """Test prepare_submission_wrapper(xml_string, docname) format."""

    SAMPLE_XML = '<?xml version="1.0" encoding="UTF-8"?><Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"><cbc:ID xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">SAL-SLP-00001</cbc:ID></Invoice>'

    def test_prepare_submission_wrapper_format(self):
        """prepare_submission_wrapper returns dict with 'documents' list."""
        result = prepare_submission_wrapper(self.SAMPLE_XML, "SAL-SLP-00001")

        self.assertIsInstance(result, dict)
        self.assertIn("documents", result)
        self.assertIsInstance(result["documents"], list)
        self.assertEqual(len(result["documents"]), 1)

        doc_entry = result["documents"][0]
        self.assertIn("format", doc_entry)
        self.assertIn("document", doc_entry)
        self.assertIn("documentHash", doc_entry)
        self.assertIn("codeNumber", doc_entry)

    def test_wrapper_contains_base64_document(self):
        """Wrapper document field contains base64-encoded XML."""
        result = prepare_submission_wrapper(self.SAMPLE_XML, "SAL-SLP-00001")
        doc_entry = result["documents"][0]

        # Decode base64 and verify it matches original XML
        decoded = base64.b64decode(doc_entry["document"]).decode("utf-8")
        self.assertEqual(decoded, self.SAMPLE_XML)

    def test_wrapper_contains_sha256_hash(self):
        """Wrapper documentHash field contains SHA-256 hex digest of XML bytes."""
        result = prepare_submission_wrapper(self.SAMPLE_XML, "SAL-SLP-00001")
        doc_entry = result["documents"][0]

        # Compute expected hash
        expected_hash = hashlib.sha256(self.SAMPLE_XML.encode("utf-8")).hexdigest()
        self.assertEqual(doc_entry["documentHash"], expected_hash)
