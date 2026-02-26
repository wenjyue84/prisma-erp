"""Tests for Salary Slip, Expense Claim, and Consolidated XML payload builders.

Tests build_salary_slip_xml(), build_expense_claim_xml(),
prepare_submission_wrapper(), and build_consolidated_xml() functions.
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
    build_consolidated_xml,
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
        doc.currency = "MYR"
        doc.conversion_rate = 1

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
        emp.custom_state_code = "01"
        emp.custom_bank_account_number = None
        emp.custom_worker_type = "Employee"
        return emp

    def _make_company_doc(self):
        """Create a mock Company doc with LHDN fields."""
        company = MagicMock()
        company.custom_company_tin_number = "C12345678901"
        company.name = "Arising Packaging"
        company.company_name = "Arising Packaging Sdn Bhd"
        company.custom_state_code = "14"
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
        emp.custom_state_code = "01"
        emp.custom_bank_account_number = None
        emp.custom_worker_type = "Employee"
        return emp

    def _make_company_doc(self):
        """Create a mock Company doc with LHDN fields."""
        company = MagicMock()
        company.custom_company_tin_number = "C12345678901"
        company.name = "Arising Packaging"
        company.company_name = "Arising Packaging Sdn Bhd"
        company.custom_state_code = "14"
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


class TestConsolidatedXMLBuilder(FrappeTestCase):
    """Test build_consolidated_xml(docnames, target_month) -- TDD red phase (UT-019).

    Tests verify that build_consolidated_xml():
    - Returns valid UBL 2.1 XML
    - Creates one InvoiceLine per source document
    - Uses classification code '004' on all line items
    - Generates InvoiceCode following CONSOL-{company_abbr}-{YYYY-MM} pattern
    - Sets BillingPeriod to the full target month
    - Sums all individual doc amounts for totals (exact Decimal)
    - Sets buyer contact to 'NA'
    """

    def _make_salary_slip(self, name, net_pay=5000, employee="HR-EMP-00001",
                          company="Arising Packaging", posting_date="2026-01-15",
                          employee_name="Ahmad bin Abdullah"):
        """Create a mock Salary Slip doc for consolidated submission."""
        doc = MagicMock()
        doc.name = name
        doc.doctype = "Salary Slip"
        doc.employee = employee
        doc.employee_name = employee_name
        doc.net_pay = net_pay
        doc.company = company
        doc.posting_date = posting_date
        doc.end_date = "2026-01-31"
        doc.currency = "MYR"
        doc.conversion_rate = 1

        earning = MagicMock()
        earning.salary_component = "Basic Salary"
        earning.amount = net_pay
        earning.custom_lhdn_classification_code = "022 : Others"
        doc.earnings = [earning]
        doc.deductions = []

        return doc

    def _make_company_doc(self, abbr="AP"):
        """Create a mock Company doc."""
        company = MagicMock()
        company.name = "Arising Packaging"
        company.company_name = "Arising Packaging Sdn Bhd"
        company.abbr = abbr
        company.custom_company_tin_number = "C12345678901"
        return company

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_build_consolidated_xml_returns_valid_xml(self, mock_frappe):
        """build_consolidated_xml(docnames, '2026-01') returns a valid UBL XML
        string with Invoice root element."""
        doc1 = self._make_salary_slip("SS-001", net_pay=3000)
        doc2 = self._make_salary_slip("SS-002", net_pay=4000)
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SS-001"): doc1,
            ("Salary Slip", "SS-002"): doc2,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_consolidated_xml(["SS-001", "SS-002"], "2026-01")

        self.assertIsInstance(xml_string, str)
        root = ET.fromstring(xml_string)
        self.assertEqual(root.tag, f"{{{UBL_NS}}}Invoice")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_invoice_lines_count_matches_docnames_count(self, mock_frappe):
        """Each InvoiceLine corresponds to one source document --
        len(InvoiceLines) == len(docnames)."""
        doc1 = self._make_salary_slip("SS-001", net_pay=3000)
        doc2 = self._make_salary_slip("SS-002", net_pay=4000)
        doc3 = self._make_salary_slip("SS-003", net_pay=2000)
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SS-001"): doc1,
            ("Salary Slip", "SS-002"): doc2,
            ("Salary Slip", "SS-003"): doc3,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        docnames = ["SS-001", "SS-002", "SS-003"]
        xml_string = build_consolidated_xml(docnames, "2026-01")
        root = ET.fromstring(xml_string)

        lines = root.findall(f".//{{{CAC_NS}}}InvoiceLine")
        self.assertEqual(len(lines), len(docnames),
                         f"Expected {len(docnames)} InvoiceLines, got {len(lines)}")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_all_line_items_use_classification_004(self, mock_frappe):
        """ItemClassificationCode = '004' on ALL line items in consolidated XML."""
        doc1 = self._make_salary_slip("SS-001", net_pay=3000)
        doc2 = self._make_salary_slip("SS-002", net_pay=4000)
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SS-001"): doc1,
            ("Salary Slip", "SS-002"): doc2,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_consolidated_xml(["SS-001", "SS-002"], "2026-01")
        root = ET.fromstring(xml_string)

        lines = root.findall(f".//{{{CAC_NS}}}InvoiceLine")
        self.assertTrue(len(lines) > 0, "No InvoiceLines found")

        for idx, line in enumerate(lines):
            code_elem = line.find(
                f".//{{{CAC_NS}}}CommodityClassification/{{{CBC_NS}}}ItemClassificationCode"
            )
            self.assertIsNotNone(code_elem,
                                 f"InvoiceLine {idx+1} missing ItemClassificationCode")
            self.assertEqual(code_elem.text, "004",
                             f"InvoiceLine {idx+1} classification code is "
                             f"'{code_elem.text}', expected '004'")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_invoice_code_follows_consol_pattern(self, mock_frappe):
        """InvoiceCode follows pattern CONSOL-{company_abbr}-{YYYY-MM} (max 50 chars)."""
        doc1 = self._make_salary_slip("SS-001", net_pay=3000)
        company = self._make_company_doc(abbr="AP")

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SS-001"): doc1,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_consolidated_xml(["SS-001"], "2026-01")
        root = ET.fromstring(xml_string)

        invoice_id = root.find(f"{{{CBC_NS}}}ID")
        self.assertIsNotNone(invoice_id, "Invoice ID element not found")

        # Pattern: CONSOL-AP-2026-01
        self.assertTrue(invoice_id.text.startswith("CONSOL-"),
                        f"InvoiceCode '{invoice_id.text}' does not start with 'CONSOL-'")
        self.assertIn("AP", invoice_id.text,
                       f"InvoiceCode '{invoice_id.text}' does not contain "
                       f"company abbreviation 'AP'")
        self.assertIn("2026-01", invoice_id.text,
                       f"InvoiceCode '{invoice_id.text}' does not contain "
                       f"target month '2026-01'")
        self.assertLessEqual(len(invoice_id.text), 50,
                             f"InvoiceCode exceeds 50 characters: {len(invoice_id.text)}")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_billing_period_start_and_end_dates(self, mock_frappe):
        """BillingPeriodStartDate = first day of target month,
        EndDate = last day of target month."""
        doc1 = self._make_salary_slip("SS-001", net_pay=3000)
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SS-001"): doc1,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_consolidated_xml(["SS-001"], "2026-01")
        root = ET.fromstring(xml_string)

        billing_period = root.find(f".//{{{CAC_NS}}}InvoicePeriod")
        self.assertIsNotNone(billing_period, "InvoicePeriod (BillingPeriod) not found")

        start_date = billing_period.find(f"{{{CBC_NS}}}StartDate")
        end_date = billing_period.find(f"{{{CBC_NS}}}EndDate")

        self.assertIsNotNone(start_date, "BillingPeriod StartDate not found")
        self.assertIsNotNone(end_date, "BillingPeriod EndDate not found")

        self.assertEqual(start_date.text, "2026-01-01",
                         f"StartDate '{start_date.text}' != expected '2026-01-01'")
        self.assertEqual(end_date.text, "2026-01-31",
                         f"EndDate '{end_date.text}' != expected '2026-01-31'")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_totals_sum_of_all_individual_amounts(self, mock_frappe):
        """TotalIncludingTax = sum of all individual document net amounts (Decimal).
        TotalExcludingTax + TotalTaxAmount == TotalIncludingTax (exact Decimal)."""
        doc1 = self._make_salary_slip("SS-001", net_pay=3000)
        doc2 = self._make_salary_slip("SS-002", net_pay=4500.50)
        doc3 = self._make_salary_slip("SS-003", net_pay=1200.75)
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SS-001"): doc1,
            ("Salary Slip", "SS-002"): doc2,
            ("Salary Slip", "SS-003"): doc3,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_consolidated_xml(
            ["SS-001", "SS-002", "SS-003"], "2026-01"
        )
        root = ET.fromstring(xml_string)

        monetary_total = root.find(f".//{{{CAC_NS}}}LegalMonetaryTotal")
        self.assertIsNotNone(monetary_total, "LegalMonetaryTotal not found")

        tax_excl = monetary_total.find(f"{{{CBC_NS}}}TaxExclusiveAmount")
        tax_incl = monetary_total.find(f"{{{CBC_NS}}}TaxInclusiveAmount")
        self.assertIsNotNone(tax_excl, "TaxExclusiveAmount not found")
        self.assertIsNotNone(tax_incl, "TaxInclusiveAmount not found")

        tax_amount = root.find(f".//{{{CAC_NS}}}TaxTotal/{{{CBC_NS}}}TaxAmount")
        self.assertIsNotNone(tax_amount, "TaxTotal/TaxAmount not found")

        excl = Decimal(tax_excl.text)
        incl = Decimal(tax_incl.text)
        tax = Decimal(tax_amount.text)

        # Verify totals balance
        self.assertEqual(excl + tax, incl,
                         f"Totals don't balance: {excl} + {tax} != {incl}")

        # Verify total equals sum of individual net_pay amounts
        expected_total = Decimal("3000") + Decimal("4500.50") + Decimal("1200.75")
        expected_total = expected_total.quantize(Decimal("0.01"))
        self.assertEqual(excl, expected_total,
                         f"TaxExclusiveAmount {excl} != expected sum {expected_total}")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_buyer_contact_is_na(self, mock_frappe):
        """Buyer contact must be 'NA' (allowed during grace period consolidation)."""
        doc1 = self._make_salary_slip("SS-001", net_pay=3000)
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SS-001"): doc1,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_consolidated_xml(["SS-001"], "2026-01")
        root = ET.fromstring(xml_string)

        # Buyer contact should be 'NA' -- look in AccountingCustomerParty or Contact
        # Check for Contact element or direct text value
        customer_party = root.find(f".//{{{CAC_NS}}}AccountingCustomerParty")
        self.assertIsNotNone(customer_party,
                             "AccountingCustomerParty not found in consolidated XML")

        # 'NA' should appear in buyer contact fields within the customer party
        customer_xml = ET.tostring(customer_party, encoding="unicode")
        self.assertIn("NA", customer_xml,
                       "Buyer contact 'NA' not found in AccountingCustomerParty")


class TestStateCodeInUBL(FrappeTestCase):
    """Test Malaysian state code (CountrySubentityCode) in UBL address elements.

    LHDN v1.1 mandates cbc:CountrySubentityCode in both supplier (employee)
    and buyer (company) PostalAddress blocks. Valid codes: 01-17.
    Foreign employees and consolidated submissions use '17' (Not Applicable).
    """

    VALID_STATE_CODES = [
        "01", "02", "03", "04", "05", "06", "07", "08",
        "09", "10", "11", "12", "13", "14", "15", "16", "17",
    ]

    def _make_salary_slip_doc(self):
        """Create a mock Salary Slip doc."""
        doc = MagicMock()
        doc.name = "SAL-SLP-00001"
        doc.employee = "HR-EMP-00001"
        doc.employee_name = "Ahmad bin Abdullah"
        doc.net_pay = 5000
        doc.company = "Arising Packaging"
        doc.posting_date = "2026-01-31"
        doc.currency = "MYR"
        doc.conversion_rate = 1

        earning = MagicMock()
        earning.salary_component = "Basic Salary"
        earning.amount = 5000
        earning.custom_lhdn_classification_code = "022 : Others"
        doc.earnings = [earning]
        doc.deductions = []

        return doc

    def _make_employee_doc(self, state_code="10", is_foreign=False):
        """Create a mock Employee doc with custom_state_code."""
        emp = MagicMock()
        emp.custom_lhdn_tin = "IG12345678901"
        emp.custom_id_type = "NRIC"
        emp.custom_id_value = "901201145678"
        emp.employee_name = "Ahmad bin Abdullah"
        emp.custom_is_foreign_worker = 1 if is_foreign else 0
        emp.custom_state_code = state_code
        return emp

    def _make_company_doc(self, state_code="14"):
        """Create a mock Company doc with custom_state_code."""
        company = MagicMock()
        company.custom_company_tin_number = "C12345678901"
        company.name = "Arising Packaging"
        company.company_name = "Arising Packaging Sdn Bhd"
        company.abbr = "AP"
        company.custom_state_code = state_code
        return company

    def _make_salary_slip_for_consol(self, name, net_pay=5000):
        """Create a mock Salary Slip doc for consolidated submission."""
        doc = MagicMock()
        doc.name = name
        doc.doctype = "Salary Slip"
        doc.employee = "HR-EMP-00001"
        doc.employee_name = "Ahmad bin Abdullah"
        doc.net_pay = net_pay
        doc.company = "Arising Packaging"
        doc.posting_date = "2026-01-15"
        doc.end_date = "2026-01-31"
        doc.currency = "MYR"
        doc.conversion_rate = 1

        earning = MagicMock()
        earning.salary_component = "Basic Salary"
        earning.amount = net_pay
        earning.custom_lhdn_classification_code = "022 : Others"
        doc.earnings = [earning]
        doc.deductions = []

        return doc

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_supplier_address_has_country_subentity_code(self, mock_frappe):
        """AccountingSupplierParty PostalAddress must include cbc:CountrySubentityCode."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee_doc(state_code="10")  # Selangor
        company = self._make_company_doc(state_code="14")

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-00001")
        root = ET.fromstring(xml_string)

        # Find CountrySubentityCode inside AccountingSupplierParty > Party > PostalAddress
        supplier_state = root.find(
            f".//{{{CAC_NS}}}AccountingSupplierParty"
            f"//{{{CAC_NS}}}PostalAddress"
            f"/{{{CBC_NS}}}CountrySubentityCode"
        )
        self.assertIsNotNone(
            supplier_state,
            "CountrySubentityCode not found in AccountingSupplierParty PostalAddress"
        )
        self.assertEqual(supplier_state.text, "10",
                         f"Supplier state code is '{supplier_state.text}', expected '10'")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_buyer_address_has_country_subentity_code(self, mock_frappe):
        """AccountingCustomerParty PostalAddress must include cbc:CountrySubentityCode."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee_doc(state_code="10")
        company = self._make_company_doc(state_code="14")  # W.P. Kuala Lumpur

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-00001")
        root = ET.fromstring(xml_string)

        # Find CountrySubentityCode inside AccountingCustomerParty > Party > PostalAddress
        buyer_state = root.find(
            f".//{{{CAC_NS}}}AccountingCustomerParty"
            f"//{{{CAC_NS}}}PostalAddress"
            f"/{{{CBC_NS}}}CountrySubentityCode"
        )
        self.assertIsNotNone(
            buyer_state,
            "CountrySubentityCode not found in AccountingCustomerParty PostalAddress"
        )
        self.assertEqual(buyer_state.text, "14",
                         f"Buyer state code is '{buyer_state.text}', expected '14'")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_state_code_01_johor_is_valid(self, mock_frappe):
        """State code '01' (Johor) is a valid CountrySubentityCode value."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee_doc(state_code="01")  # Johor
        company = self._make_company_doc(state_code="01")

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-00001")
        root = ET.fromstring(xml_string)

        # Both supplier and buyer should have state code '01'
        supplier_state = root.find(
            f".//{{{CAC_NS}}}AccountingSupplierParty"
            f"//{{{CAC_NS}}}PostalAddress"
            f"/{{{CBC_NS}}}CountrySubentityCode"
        )
        self.assertIsNotNone(supplier_state,
                             "CountrySubentityCode not found in supplier address")
        self.assertEqual(supplier_state.text, "01",
                         f"Supplier state code '{supplier_state.text}' != '01' (Johor)")
        self.assertIn(supplier_state.text, self.VALID_STATE_CODES,
                      f"State code '{supplier_state.text}' not in valid Malaysian codes")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_state_code_17_not_applicable_for_consolidated(self, mock_frappe):
        """Consolidated XML uses state code '17' (Not Applicable) for buyer address."""
        doc1 = self._make_salary_slip_for_consol("SS-001", net_pay=3000)
        company = self._make_company_doc(state_code="14")

        emp = self._make_employee_doc(state_code="10")

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SS-001"): doc1,
            ("Company", "Arising Packaging"): company,
            ("Employee", "HR-EMP-00001"): emp,
        }.get((dt, name), MagicMock())

        xml_string = build_consolidated_xml(["SS-001"], "2026-01")
        root = ET.fromstring(xml_string)

        # Consolidated buyer address should use '17' (Not Applicable)
        buyer_state = root.find(
            f".//{{{CAC_NS}}}AccountingCustomerParty"
            f"//{{{CAC_NS}}}PostalAddress"
            f"/{{{CBC_NS}}}CountrySubentityCode"
        )
        self.assertIsNotNone(
            buyer_state,
            "CountrySubentityCode not found in consolidated buyer address"
        )
        self.assertEqual(buyer_state.text, "17",
                         f"Consolidated buyer state code is '{buyer_state.text}', "
                         f"expected '17' (Not Applicable)")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_missing_state_code_raises_validation_error(self, mock_frappe):
        """Missing custom_state_code on Employee raises frappe.ValidationError."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee_doc(state_code=None)  # No state code
        company = self._make_company_doc(state_code="14")

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        # Configure mock to raise ValidationError when frappe.throw is called
        mock_frappe.throw.side_effect = frappe.ValidationError

        with self.assertRaises(frappe.ValidationError):
            build_salary_slip_xml("SAL-SLP-00001")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_foreign_employee_uses_state_code_17(self, mock_frappe):
        """Foreign worker (custom_is_foreign_worker=1) uses state code '17'
        regardless of custom_state_code value."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee_doc(state_code="10", is_foreign=True)
        emp.custom_lhdn_tin = "EI00000000010"  # Foreign worker TIN
        company = self._make_company_doc(state_code="14")

        mock_frappe.get_doc.side_effect = lambda dt, name=None: {
            ("Salary Slip", "SAL-SLP-00001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-00001")
        root = ET.fromstring(xml_string)

        # Foreign employee supplier address should use '17'
        supplier_state = root.find(
            f".//{{{CAC_NS}}}AccountingSupplierParty"
            f"//{{{CAC_NS}}}PostalAddress"
            f"/{{{CBC_NS}}}CountrySubentityCode"
        )
        self.assertIsNotNone(
            supplier_state,
            "CountrySubentityCode not found in foreign employee supplier address"
        )
        self.assertEqual(supplier_state.text, "17",
                         f"Foreign employee state code is '{supplier_state.text}', "
                         f"expected '17' (Not Applicable)")


class TestPCBWithholdingTax(FrappeTestCase):
    """Test PCB withholding tax handling in contractor salary slip XML.

    Verifies:
    - TaxableAmount uses gross earnings (not net_pay)
    - PCB deduction appears as WithholdingTaxTotal when > 0
    - Zero PCB omits the WithholdingTaxTotal element
    - Invoice total equals sum of earnings components
    """

    PCB_COMPONENT_NAMES = ("Monthly Tax Deduction", "PCB", "Income Tax")

    def _make_salary_slip_with_pcb(self, pcb_amount=500):
        """Create a mock Salary Slip with earnings and PCB deduction."""
        doc = MagicMock()
        doc.name = "SAL-SLP-PCB-001"
        doc.employee = "HR-EMP-00001"
        doc.employee_name = "Ahmad bin Abdullah"
        doc.company = "Arising Packaging"
        doc.posting_date = "2026-01-31"
        doc.currency = "MYR"
        doc.conversion_rate = 1

        # Earnings: gross = 4000 + 1000 = 5000
        earning1 = MagicMock()
        earning1.salary_component = "Basic Salary"
        earning1.amount = 4000
        earning1.custom_lhdn_classification_code = "022 : Others"

        earning2 = MagicMock()
        earning2.salary_component = "Allowance"
        earning2.amount = 1000
        earning2.custom_lhdn_classification_code = "022 : Others"

        doc.earnings = [earning1, earning2]

        # net_pay = gross - pcb = 5000 - pcb_amount
        doc.net_pay = 5000 - pcb_amount

        # PCB deduction
        deductions = []
        if pcb_amount > 0:
            pcb = MagicMock()
            pcb.salary_component = "Monthly Tax Deduction"
            pcb.amount = pcb_amount
            deductions.append(pcb)
        doc.deductions = deductions

        return doc

    def _make_employee_doc(self):
        emp = MagicMock()
        emp.custom_lhdn_tin = "IG12345678901"
        emp.custom_id_type = "NRIC"
        emp.custom_id_value = "901201145678"
        emp.employee_name = "Ahmad bin Abdullah"
        emp.custom_is_foreign_worker = 0
        emp.custom_state_code = "01"
        emp.custom_bank_account_number = None
        emp.custom_worker_type = "Contractor"
        return emp

    def _make_company_doc(self):
        company = MagicMock()
        company.custom_company_tin_number = "C12345678901"
        company.name = "Arising Packaging"
        company.company_name = "Arising Packaging Sdn Bhd"
        company.custom_state_code = "14"
        return company

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_gross_pay_used_as_invoice_total_not_net_pay(self, mock_frappe):
        """TotalIncludingTax in the XML must use gross earnings (5000),
        not net_pay (4500 after PCB deduction)."""
        doc = self._make_salary_slip_with_pcb(pcb_amount=500)
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-PCB-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-PCB-001")
        root = ET.fromstring(xml_string)

        # Find LegalMonetaryTotal/TaxInclusiveAmount (gross pay)
        tax_inclusive = root.find(
            f".//{{{CAC_NS}}}LegalMonetaryTotal"
            f"/{{{CBC_NS}}}TaxInclusiveAmount"
        )
        self.assertIsNotNone(tax_inclusive,
            "TaxInclusiveAmount element must exist in LegalMonetaryTotal")
        # Must be gross (5000), not net_pay (4500)
        amount = Decimal(tax_inclusive.text)
        self.assertEqual(amount, Decimal("5000.00"),
            f"TaxInclusiveAmount should be gross 5000.00, got {amount}")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_pcb_amount_in_withholding_tax_total(self, mock_frappe):
        """When PCB deduction > 0, XML must include WithholdingTaxTotal
        with the correct PCB amount."""
        doc = self._make_salary_slip_with_pcb(pcb_amount=500)
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-PCB-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-PCB-001")
        root = ET.fromstring(xml_string)

        # WithholdingTaxTotal element should exist
        withholding = root.find(f".//{{{CAC_NS}}}WithholdingTaxTotal")
        self.assertIsNotNone(withholding,
            "WithholdingTaxTotal element must exist when PCB > 0")

        # Amount should be 500
        wh_amount = withholding.find(f"{{{CBC_NS}}}TaxAmount")
        self.assertIsNotNone(wh_amount,
            "WithholdingTaxTotal/TaxAmount must exist")
        self.assertEqual(Decimal(wh_amount.text), Decimal("500.00"),
            f"WithholdingTaxTotal amount should be 500.00, got {wh_amount.text}")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_zero_pcb_omits_withholding_tax_element(self, mock_frappe):
        """When PCB deduction is 0 or absent, WithholdingTaxTotal must
        be omitted from the XML."""
        doc = self._make_salary_slip_with_pcb(pcb_amount=0)
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-PCB-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-PCB-001")
        root = ET.fromstring(xml_string)

        withholding = root.find(f".//{{{CAC_NS}}}WithholdingTaxTotal")
        self.assertIsNone(withholding,
            "WithholdingTaxTotal must NOT exist when PCB is 0 or absent")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_invoice_total_equals_sum_of_earnings_components(self, mock_frappe):
        """TotalIncludingTax must always equal sum of earnings rows
        (gross pay before any deduction)."""
        doc = self._make_salary_slip_with_pcb(pcb_amount=300)
        emp = self._make_employee_doc()
        company = self._make_company_doc()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-PCB-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-PCB-001")
        root = ET.fromstring(xml_string)

        expected_gross = sum(e.amount for e in doc.earnings)

        tax_inclusive = root.find(
            f".//{{{CAC_NS}}}LegalMonetaryTotal"
            f"/{{{CBC_NS}}}TaxInclusiveAmount"
        )
        self.assertIsNotNone(tax_inclusive, "TaxInclusiveAmount must exist")
        actual = Decimal(tax_inclusive.text)
        self.assertEqual(actual, Decimal(str(expected_gross)),
            f"TaxInclusiveAmount ({actual}) must equal sum of earnings ({expected_gross})")


class TestPaymentMeans(FrappeTestCase):
    """Test PaymentMeans element in UBL self-billed invoice.

    Verifies:
    - PaymentMeans present when employee has bank account set
    - PayeeFinancialAccount contains correct bank account number
    - PaymentMeans omitted when bank account is empty/None
    - Bank account truncated to 150 chars
    """

    def _make_salary_slip(self):
        doc = MagicMock()
        doc.name = "SAL-SLP-PM-001"
        doc.employee = "HR-EMP-00001"
        doc.employee_name = "Ahmad bin Abdullah"
        doc.company = "Arising Packaging"
        doc.posting_date = "2026-01-31"
        doc.currency = "MYR"
        doc.conversion_rate = 1

        earning = MagicMock()
        earning.salary_component = "Basic Salary"
        earning.amount = 5000
        earning.custom_lhdn_classification_code = "022 : Others"
        doc.earnings = [earning]
        doc.deductions = []
        doc.net_pay = 5000
        return doc

    def _make_employee(self, bank_account=None):
        emp = MagicMock()
        emp.custom_lhdn_tin = "IG12345678901"
        emp.custom_id_type = "NRIC"
        emp.custom_id_value = "901201145678"
        emp.employee_name = "Ahmad bin Abdullah"
        emp.custom_is_foreign_worker = 0
        emp.custom_state_code = "01"
        emp.custom_bank_account_number = bank_account
        return emp

    def _make_company(self):
        company = MagicMock()
        company.custom_company_tin_number = "C12345678901"
        company.name = "Arising Packaging"
        company.company_name = "Arising Packaging Sdn Bhd"
        company.custom_state_code = "14"
        return company

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_payment_means_present_when_bank_account_set(self, mock_frappe):
        """When employee has custom_bank_account_number, XML must include
        cac:PaymentMeans with PaymentMeansCode '30' (credit transfer)."""
        doc = self._make_salary_slip()
        emp = self._make_employee(bank_account="1234567890")
        company = self._make_company()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-PM-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-PM-001")
        root = ET.fromstring(xml_string)

        payment_means = root.find(f".//{{{CAC_NS}}}PaymentMeans")
        self.assertIsNotNone(payment_means,
            "PaymentMeans element must exist when bank account is set")

        means_code = payment_means.find(f"{{{CBC_NS}}}PaymentMeansCode")
        self.assertIsNotNone(means_code,
            "PaymentMeansCode must exist inside PaymentMeans")
        self.assertEqual(means_code.text, "30",
            "PaymentMeansCode must be '30' (credit transfer)")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_payee_financial_account_contains_bank_number(self, mock_frappe):
        """PayeeFinancialAccount/ID must contain the employee bank account number."""
        doc = self._make_salary_slip()
        emp = self._make_employee(bank_account="1234567890")
        company = self._make_company()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-PM-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-PM-001")
        root = ET.fromstring(xml_string)

        account_id = root.find(
            f".//{{{CAC_NS}}}PaymentMeans"
            f"/{{{CAC_NS}}}PayeeFinancialAccount"
            f"/{{{CBC_NS}}}ID"
        )
        self.assertIsNotNone(account_id,
            "PayeeFinancialAccount/ID must exist")
        self.assertEqual(account_id.text, "1234567890",
            f"Bank account should be '1234567890', got '{account_id.text}'")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_payment_means_omitted_when_no_bank_account(self, mock_frappe):
        """When employee has no bank account, PaymentMeans must be omitted."""
        doc = self._make_salary_slip()
        emp = self._make_employee(bank_account=None)
        company = self._make_company()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-PM-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-PM-001")
        root = ET.fromstring(xml_string)

        payment_means = root.find(f".//{{{CAC_NS}}}PaymentMeans")
        self.assertIsNone(payment_means,
            "PaymentMeans must NOT exist when bank account is empty/None")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_bank_account_truncated_to_150_chars(self, mock_frappe):
        """Bank account numbers longer than 150 chars must be truncated."""
        long_account = "A" * 200
        doc = self._make_salary_slip()
        emp = self._make_employee(bank_account=long_account)
        company = self._make_company()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-PM-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-PM-001")
        root = ET.fromstring(xml_string)

        account_id = root.find(
            f".//{{{CAC_NS}}}PaymentMeans"
            f"/{{{CAC_NS}}}PayeeFinancialAccount"
            f"/{{{CBC_NS}}}ID"
        )
        self.assertIsNotNone(account_id,
            "PayeeFinancialAccount/ID must exist for long account")
        self.assertLessEqual(len(account_id.text), 150,
            f"Bank account must be truncated to 150 chars, got {len(account_id.text)}")


class TestForeignCurrencyHandling(FrappeTestCase):
    """Test foreign currency to MYR conversion in UBL payload.

    Verifies:
    - DocumentCurrencyCode is always 'MYR'
    - MYR salary amounts used directly (no conversion)
    - Foreign currency amounts multiplied by conversion_rate
    - Missing exchange rate raises ValidationError
    - TaxCurrencyCode set for non-MYR currencies
    """

    def _make_salary_slip(self, currency="MYR", conversion_rate=1):
        doc = MagicMock()
        doc.name = "SAL-SLP-FX-001"
        doc.employee = "HR-EMP-00001"
        doc.employee_name = "Ahmad bin Abdullah"
        doc.company = "Arising Packaging"
        doc.posting_date = "2026-01-31"
        doc.currency = currency
        doc.conversion_rate = conversion_rate
        doc.net_pay = 5000

        earning = MagicMock()
        earning.salary_component = "Basic Salary"
        earning.amount = 1000
        earning.custom_lhdn_classification_code = "022 : Others"
        doc.earnings = [earning]
        doc.deductions = []
        return doc

    def _make_employee(self):
        emp = MagicMock()
        emp.custom_lhdn_tin = "IG12345678901"
        emp.custom_id_type = "NRIC"
        emp.custom_id_value = "901201145678"
        emp.employee_name = "Ahmad bin Abdullah"
        emp.custom_is_foreign_worker = 0
        emp.custom_state_code = "01"
        emp.custom_bank_account_number = None
        emp.custom_worker_type = "Contractor"
        return emp

    def _make_company(self):
        company = MagicMock()
        company.custom_company_tin_number = "C12345678901"
        company.name = "Arising Packaging"
        company.custom_state_code = "14"
        return company

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_document_currency_code_is_always_myr(self, mock_frappe):
        """DocumentCurrencyCode must always be 'MYR', even for foreign currency slips."""
        doc = self._make_salary_slip(currency="USD", conversion_rate=4.5)
        emp = self._make_employee()
        company = self._make_company()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-FX-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-FX-001")
        root = ET.fromstring(xml_string)

        currency_code = root.find(f"{{{CBC_NS}}}DocumentCurrencyCode")
        self.assertIsNotNone(currency_code, "DocumentCurrencyCode must exist")
        self.assertEqual(currency_code.text, "MYR",
            f"DocumentCurrencyCode must be 'MYR', got '{currency_code.text}'")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_myr_salary_no_conversion_needed(self, mock_frappe):
        """MYR salary amounts should be used directly without conversion."""
        doc = self._make_salary_slip(currency="MYR", conversion_rate=1)
        emp = self._make_employee()
        company = self._make_company()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-FX-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-FX-001")
        root = ET.fromstring(xml_string)

        # Line amount should be 1000.00 (no conversion)
        line_amount = root.find(
            f".//{{{CAC_NS}}}InvoiceLine/{{{CBC_NS}}}LineExtensionAmount"
        )
        self.assertIsNotNone(line_amount, "LineExtensionAmount must exist")
        self.assertEqual(line_amount.text, "1000.00",
            f"MYR amount should be 1000.00, got '{line_amount.text}'")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_usd_salary_amounts_converted_to_myr(self, mock_frappe):
        """USD salary with conversion_rate=4.5 must multiply amounts by 4.5."""
        doc = self._make_salary_slip(currency="USD", conversion_rate=4.5)
        emp = self._make_employee()
        company = self._make_company()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-FX-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-FX-001")
        root = ET.fromstring(xml_string)

        # Line amount should be 1000 * 4.5 = 4500.00
        line_amount = root.find(
            f".//{{{CAC_NS}}}InvoiceLine/{{{CBC_NS}}}LineExtensionAmount"
        )
        self.assertIsNotNone(line_amount, "LineExtensionAmount must exist")
        self.assertEqual(line_amount.text, "4500.00",
            f"USD 1000 * 4.5 should be 4500.00, got '{line_amount.text}'")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_missing_exchange_rate_raises_validation_error(self, mock_frappe):
        """Foreign currency with conversion_rate=0 must raise ValidationError."""
        doc = self._make_salary_slip(currency="USD", conversion_rate=0)
        emp = self._make_employee()
        company = self._make_company()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-FX-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        mock_frappe.ValidationError = type("ValidationError", (Exception,), {})
        mock_frappe.throw.side_effect = mock_frappe.ValidationError("Exchange rate required")

        with self.assertRaises(mock_frappe.ValidationError):
            build_salary_slip_xml("SAL-SLP-FX-001")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_tax_currency_code_set_for_foreign_currency(self, mock_frappe):
        """When currency != MYR, XML must include TaxCurrencyCode with source currency."""
        doc = self._make_salary_slip(currency="USD", conversion_rate=4.5)
        emp = self._make_employee()
        company = self._make_company()

        mock_frappe.get_doc.side_effect = lambda dt, name: {
            ("Salary Slip", "SAL-SLP-FX-001"): doc,
            ("Employee", "HR-EMP-00001"): emp,
            ("Company", "Arising Packaging"): company,
        }.get((dt, name), MagicMock())

        xml_string = build_salary_slip_xml("SAL-SLP-FX-001")
        root = ET.fromstring(xml_string)

        tax_currency = root.find(f"{{{CBC_NS}}}TaxCurrencyCode")
        self.assertIsNotNone(tax_currency,
            "TaxCurrencyCode must exist for foreign currency slips")
        self.assertEqual(tax_currency.text, "USD",
            f"TaxCurrencyCode should be 'USD', got '{tax_currency.text}'")
