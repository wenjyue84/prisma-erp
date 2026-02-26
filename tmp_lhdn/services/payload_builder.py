"""UBL 2.1 XML payload builder for Salary Slip and Expense Claim e-Invoices.

Generates self-billed e-Invoice XML for LHDN MyInvois submission.
Self-billed inversion: Employer = Buyer (payer), Employee = Supplier (payee).
e-Invoice type code = '11' (self-billed).

Financial totals are calculated from child table rows ONLY --
never from YTD fields or compute_year_to_date() (v16 bug).
"""
import base64
import calendar
import hashlib
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP

import frappe

# UBL 2.1 Namespaces
UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

TWO_DP = Decimal("0.01")

# PCB component names to detect withholding tax deductions
PCB_COMPONENT_NAMES = frozenset({
    'Monthly Tax Deduction', 'PCB', 'Income Tax', 'Tax Deduction'
})


def _quantize(value):
    """Quantize a value to 2 decimal places with ROUND_HALF_UP."""
    return Decimal(str(value)).quantize(TWO_DP, rounding=ROUND_HALF_UP)


def _sub(parent, ns, tag, text=None, **attribs):
    """Create a sub-element with namespace prefix."""
    elem = ET.SubElement(parent, f"{{{ns}}}{tag}", **attribs)
    if text is not None:
        elem.text = str(text)
    return elem


def assert_totals_balance(total_excl, total_tax, total_incl):
    """Assert that totals balance: excl + tax == incl."""
    if total_excl + total_tax != total_incl:
        frappe.throw(
            f"Totals don't balance: {total_excl} + {total_tax} != {total_incl}"
        )


def _extract_classification_code(raw_code, default="022"):
    """Extract numeric classification code from 'NNN : Description' format."""
    if raw_code and " : " in str(raw_code):
        return str(raw_code).split(" : ")[0].strip()
    return default


def _resolve_state_code(employee):
    """Resolve Malaysian state code for an employee.

    Foreign workers (custom_is_foreign_worker=1) always return '17' (Not Applicable).
    Local employees must have custom_state_code set or a ValidationError is raised.

    Returns:
        str: Two-digit state code ('01'-'17').
    """
    if getattr(employee, "custom_is_foreign_worker", 0):
        return "17"
    state_code = getattr(employee, "custom_state_code", None)
    if not state_code:
        frappe.throw("Employee state code not set")
    return str(state_code)


def _resolve_company_state_code(company):
    """Resolve Malaysian state code for a company.

    Returns:
        str: Two-digit state code ('01'-'17').
    """
    state_code = getattr(company, "custom_state_code", None)
    if not state_code:
        frappe.throw("Company state code not set")
    return str(state_code)


def _add_postal_address(party_elem, state_code):
    """Add cac:PostalAddress with cbc:CountrySubentityCode to a Party element."""
    postal = _sub(party_elem, CAC_NS, "PostalAddress")
    _sub(postal, CBC_NS, "CountrySubentityCode", state_code)


def _build_invoice_skeleton(docname, issue_date, employee, company):
    """Build common UBL 2.1 Invoice skeleton with supplier/customer parties.

    Returns the root Element with ID, IssueDate, InvoiceTypeCode, Currency,
    AccountingSupplierParty (Employee), and AccountingCustomerParty (Company).
    """
    ET.register_namespace("", UBL_NS)
    ET.register_namespace("cac", CAC_NS)
    ET.register_namespace("cbc", CBC_NS)

    root = ET.Element(f"{{{UBL_NS}}}Invoice")
    _sub(root, CBC_NS, "ID", docname)
    _sub(root, CBC_NS, "IssueDate", str(issue_date))

    type_code = _sub(root, CBC_NS, "InvoiceTypeCode", "11")
    type_code.set("listVersionID", "1.1")

    _sub(root, CBC_NS, "DocumentCurrencyCode", "MYR")

    # Resolve state codes before building XML
    supplier_state = _resolve_state_code(employee)
    buyer_state = _resolve_company_state_code(company)

    # AccountingSupplierParty (Employee = Payee = Supplier in self-billed)
    supplier_party = _sub(root, CAC_NS, "AccountingSupplierParty")
    supplier_inner = _sub(supplier_party, CAC_NS, "Party")
    supplier_id = _sub(supplier_inner, CAC_NS, "PartyIdentification")
    _sub(supplier_id, CBC_NS, "ID", employee.custom_lhdn_tin)
    supplier_name_elem = _sub(supplier_inner, CAC_NS, "PartyName")
    _sub(supplier_name_elem, CBC_NS, "Name", employee.employee_name)
    _add_postal_address(supplier_inner, supplier_state)

    # AccountingCustomerParty (Company = Payer = Buyer in self-billed)
    customer_party = _sub(root, CAC_NS, "AccountingCustomerParty")
    customer_inner = _sub(customer_party, CAC_NS, "Party")
    customer_id = _sub(customer_inner, CAC_NS, "PartyIdentification")
    _sub(customer_id, CBC_NS, "ID", company.custom_company_tin_number)
    customer_name_elem = _sub(customer_inner, CAC_NS, "PartyName")
    _sub(customer_name_elem, CBC_NS, "Name", company.name)
    _add_postal_address(customer_inner, buyer_state)

    return root


def _add_tax_and_totals(root, total_excl, total_tax):
    """Add TaxTotal and LegalMonetaryTotal elements to the invoice root."""
    total_incl = total_excl + total_tax
    assert_totals_balance(total_excl, total_tax, total_incl)

    tax_total = _sub(root, CAC_NS, "TaxTotal")
    _sub(tax_total, CBC_NS, "TaxAmount", str(total_tax), currencyID="MYR")

    tax_subtotal_elem = _sub(tax_total, CAC_NS, "TaxSubtotal")
    _sub(tax_subtotal_elem, CBC_NS, "TaxableAmount", str(total_excl), currencyID="MYR")
    _sub(tax_subtotal_elem, CBC_NS, "TaxAmount", str(total_tax), currencyID="MYR")
    tax_cat = _sub(tax_subtotal_elem, CAC_NS, "TaxCategory")
    _sub(tax_cat, CBC_NS, "ID", "E")
    tax_scheme = _sub(tax_cat, CAC_NS, "TaxScheme")
    _sub(tax_scheme, CBC_NS, "ID", "OTH")

    monetary_total = _sub(root, CAC_NS, "LegalMonetaryTotal")
    _sub(monetary_total, CBC_NS, "TaxExclusiveAmount", str(total_excl), currencyID="MYR")
    _sub(monetary_total, CBC_NS, "TaxInclusiveAmount", str(total_incl), currencyID="MYR")
    _sub(monetary_total, CBC_NS, "PayableAmount", str(total_incl), currencyID="MYR")


def build_salary_slip_xml(docname):
    """Build UBL 2.1 XML for a self-billed Salary Slip e-Invoice.

    Args:
        docname: The Salary Slip document name.

    Returns:
        str: UBL 2.1 XML string.
    """
    doc = frappe.get_doc("Salary Slip", docname)
    employee = frappe.get_doc("Employee", doc.employee)
    company = frappe.get_doc("Company", doc.company)

    root = _build_invoice_skeleton(docname, doc.posting_date, employee, company)

    # Calculate totals from earnings ONLY (never use YTD fields)
    total_excl = sum(_quantize(e.amount) for e in doc.earnings)
    total_tax = Decimal("0.00")

    _add_tax_and_totals(root, total_excl, total_tax)

    # PCB withholding tax: detect from deductions and add WithholdingTaxTotal
    pcb_amount = sum(
        _quantize(d.amount)
        for d in getattr(doc, 'deductions', [])
        if getattr(d, 'salary_component', '') in PCB_COMPONENT_NAMES
    )
    if pcb_amount > Decimal("0.00"):
        withholding = _sub(root, CAC_NS, "WithholdingTaxTotal")
        _sub(withholding, CBC_NS, "TaxAmount", str(pcb_amount), currencyID="MYR")

    # PaymentMeans: include when employee has bank account set
    bank_account = getattr(employee, 'custom_bank_account_number', '') or ''
    if bank_account:
        bank_account = str(bank_account)[:150]
        payment_means = _sub(root, CAC_NS, "PaymentMeans")
        _sub(payment_means, CBC_NS, "PaymentMeansCode", "30")
        payee_account = _sub(payment_means, CAC_NS, "PayeeFinancialAccount")
        _sub(payee_account, CBC_NS, "ID", bank_account)

    # InvoiceLines (one per earnings row)
    for idx, earning in enumerate(doc.earnings, start=1):
        line = _sub(root, CAC_NS, "InvoiceLine")
        _sub(line, CBC_NS, "ID", str(idx))
        _sub(line, CBC_NS, "InvoicedQuantity", "1", unitCode="C62")

        amount = _quantize(earning.amount)
        _sub(line, CBC_NS, "LineExtensionAmount", str(amount), currencyID="MYR")

        item = _sub(line, CAC_NS, "Item")
        _sub(item, CBC_NS, "Description", earning.salary_component)

        classification = getattr(earning, "custom_lhdn_classification_code", None)
        class_code = _extract_classification_code(classification, default="022")

        commodity = _sub(item, CAC_NS, "CommodityClassification")
        _sub(commodity, CBC_NS, "ItemClassificationCode", class_code, listID="CLASS")

        price = _sub(line, CAC_NS, "Price")
        _sub(price, CBC_NS, "PriceAmount", str(amount), currencyID="MYR")

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def build_expense_claim_xml(docname):
    """Build UBL 2.1 XML for a self-billed Expense Claim e-Invoice.

    Args:
        docname: The Expense Claim document name.

    Returns:
        str: UBL 2.1 XML string.
    """
    doc = frappe.get_doc("Expense Claim", docname)
    employee = frappe.get_doc("Employee", doc.employee)
    company = frappe.get_doc("Company", doc.company)

    root = _build_invoice_skeleton(docname, doc.posting_date, employee, company)

    # Calculate totals from expenses rows (sanctioned_amount)
    total_excl = sum(_quantize(row.sanctioned_amount) for row in doc.expenses)
    total_tax = Decimal("0.00")

    _add_tax_and_totals(root, total_excl, total_tax)

    # InvoiceLines (one per expenses row)
    for idx, expense in enumerate(doc.expenses, start=1):
        line = _sub(root, CAC_NS, "InvoiceLine")
        _sub(line, CBC_NS, "ID", str(idx))
        _sub(line, CBC_NS, "InvoicedQuantity", "1", unitCode="C62")

        amount = _quantize(expense.sanctioned_amount)
        _sub(line, CBC_NS, "LineExtensionAmount", str(amount), currencyID="MYR")

        item = _sub(line, CAC_NS, "Item")
        _sub(item, CBC_NS, "Description", expense.expense_type)

        classification = getattr(expense, "custom_lhdn_classification_code", None)
        class_code = _extract_classification_code(classification, default="027")

        commodity = _sub(item, CAC_NS, "CommodityClassification")
        _sub(commodity, CBC_NS, "ItemClassificationCode", class_code, listID="CLASS")

        price = _sub(line, CAC_NS, "Price")
        _sub(price, CBC_NS, "PriceAmount", str(amount), currencyID="MYR")

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def build_consolidated_xml(docnames, target_month):
    """Build UBL 2.1 XML for a consolidated e-Invoice aggregating multiple documents.

    Consolidates multiple Salary Slip documents into a single e-Invoice with
    one InvoiceLine per source document. Uses classification code '004' for
    all line items and 'NA' for buyer contact (grace period consolidation).

    Args:
        docnames: List of Salary Slip document names to consolidate.
        target_month: Target month string in 'YYYY-MM' format.

    Returns:
        str: UBL 2.1 XML string.
    """
    if not docnames:
        frappe.throw("No documents provided for consolidation")

    # Load first document to determine company
    first_doc = frappe.get_doc("Salary Slip", docnames[0])
    company = frappe.get_doc("Company", first_doc.company)

    # Build invoice code: CONSOL-{company_abbr}-{YYYY-MM} (max 50 chars)
    invoice_code = f"CONSOL-{company.abbr}-{target_month}"[:50]

    # Parse target month for billing period
    year, month = target_month.split("-")
    year = int(year)
    month = int(month)
    last_day_num = calendar.monthrange(year, month)[1]
    start_date = f"{target_month}-01"
    end_date = f"{target_month}-{last_day_num:02d}"

    # Register namespaces and build root
    ET.register_namespace("", UBL_NS)
    ET.register_namespace("cac", CAC_NS)
    ET.register_namespace("cbc", CBC_NS)

    root = ET.Element(f"{{{UBL_NS}}}Invoice")
    _sub(root, CBC_NS, "ID", invoice_code)
    _sub(root, CBC_NS, "IssueDate", start_date)

    type_code = _sub(root, CBC_NS, "InvoiceTypeCode", "11")
    type_code.set("listVersionID", "1.1")

    _sub(root, CBC_NS, "DocumentCurrencyCode", "MYR")

    # InvoicePeriod (BillingPeriod)
    invoice_period = _sub(root, CAC_NS, "InvoicePeriod")
    _sub(invoice_period, CBC_NS, "StartDate", start_date)
    _sub(invoice_period, CBC_NS, "EndDate", end_date)

    # AccountingSupplierParty (first employee = Supplier in self-billed)
    employee = frappe.get_doc("Employee", first_doc.employee)
    supplier_state = _resolve_state_code(employee)
    supplier_party = _sub(root, CAC_NS, "AccountingSupplierParty")
    supplier_inner = _sub(supplier_party, CAC_NS, "Party")
    supplier_id = _sub(supplier_inner, CAC_NS, "PartyIdentification")
    _sub(supplier_id, CBC_NS, "ID", employee.custom_lhdn_tin)
    supplier_name_elem = _sub(supplier_inner, CAC_NS, "PartyName")
    _sub(supplier_name_elem, CBC_NS, "Name", employee.employee_name)
    _add_postal_address(supplier_inner, supplier_state)

    # AccountingCustomerParty (Company = Buyer) with contact = 'NA'
    # Consolidated submissions use state code '17' (Not Applicable) for buyer
    customer_party = _sub(root, CAC_NS, "AccountingCustomerParty")
    customer_inner = _sub(customer_party, CAC_NS, "Party")
    customer_id = _sub(customer_inner, CAC_NS, "PartyIdentification")
    _sub(customer_id, CBC_NS, "ID", company.custom_company_tin_number)
    customer_name_elem = _sub(customer_inner, CAC_NS, "PartyName")
    _sub(customer_name_elem, CBC_NS, "Name", company.name)
    _add_postal_address(customer_inner, "17")
    # Buyer contact = 'NA' (allowed during grace period consolidation)
    contact = _sub(customer_inner, CAC_NS, "Contact")
    _sub(contact, CBC_NS, "Name", "NA")

    # Load all docs and calculate totals
    docs = []
    total_excl = Decimal("0.00")
    for docname in docnames:
        doc = frappe.get_doc("Salary Slip", docname)
        amount = _quantize(doc.net_pay)
        total_excl += amount
        docs.append((doc, amount))

    total_tax = Decimal("0.00")

    # Add tax and totals
    _add_tax_and_totals(root, total_excl, total_tax)

    # InvoiceLines (one per source document, classification code '004')
    for idx, (doc, amount) in enumerate(docs, start=1):
        line = _sub(root, CAC_NS, "InvoiceLine")
        _sub(line, CBC_NS, "ID", str(idx))
        _sub(line, CBC_NS, "InvoicedQuantity", "1", unitCode="C62")
        _sub(line, CBC_NS, "LineExtensionAmount", str(amount), currencyID="MYR")

        item = _sub(line, CAC_NS, "Item")
        desc = f"Self-billed payroll - {doc.name} - {doc.employee_name} - {doc.end_date}"
        _sub(item, CBC_NS, "Description", desc)

        commodity = _sub(item, CAC_NS, "CommodityClassification")
        _sub(commodity, CBC_NS, "ItemClassificationCode", "004", listID="CLASS")

        price = _sub(line, CAC_NS, "Price")
        _sub(price, CBC_NS, "PriceAmount", str(amount), currencyID="MYR")

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def prepare_submission_wrapper(xml_string, docname):
    """Wrap XML in LHDN MyInvois HTTP submission format.

    Args:
        xml_string: The UBL 2.1 XML string.
        docname: The document name for codeNumber extraction.

    Returns:
        dict: Submission wrapper with documents list containing
              format, document (base64), documentHash (SHA-256), codeNumber.
    """
    xml_bytes = xml_string.encode("utf-8")
    document_hash = hashlib.sha256(xml_bytes).hexdigest()
    document_b64 = base64.b64encode(xml_bytes).decode("utf-8")
    code_number = "".join(filter(str.isdigit, docname)) or "001"
    code_number = code_number[:50]

    return {
        "documents": [
            {
                "format": "XML",
                "document": document_b64,
                "documentHash": document_hash,
                "codeNumber": code_number,
            }
        ]
    }
