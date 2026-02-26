"""UBL 2.1 XML payload builder for Salary Slip e-Invoices.

Generates self-billed e-Invoice XML for LHDN MyInvois submission.
Self-billed inversion: Employer = Buyer (payer), Contractor = Supplier (payee).
e-Invoice type code = '11' (self-billed).

Financial totals are calculated from doc.earnings child table ONLY —
never from YTD fields or compute_year_to_date() (v16 bug).
"""
import base64
import hashlib
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP

import frappe

# UBL 2.1 Namespaces
UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

TWO_DP = Decimal("0.01")


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


def build_salary_slip_xml(docname):
    """Build UBL 2.1 XML for a self-billed Salary Slip e-Invoice.

    Args:
        docname: The Salary Slip document name.

    Returns:
        str: UBL 2.1 XML string.
    """
    # Register namespaces for clean prefix output
    ET.register_namespace("", UBL_NS)
    ET.register_namespace("cac", CAC_NS)
    ET.register_namespace("cbc", CBC_NS)

    # Fetch documents
    doc = frappe.get_doc("Salary Slip", docname)
    employee = frappe.get_doc("Employee", doc.employee)
    company = frappe.get_doc("Company", doc.company)

    # Root element
    root = ET.Element(f"{{{UBL_NS}}}Invoice")

    # Invoice ID
    _sub(root, CBC_NS, "ID", docname)

    # Issue date
    _sub(root, CBC_NS, "IssueDate", str(doc.posting_date))

    # Invoice type code: 11 = self-billed
    type_code = _sub(root, CBC_NS, "InvoiceTypeCode", "11")
    type_code.set("listVersionID", "1.1")

    # Currency
    _sub(root, CBC_NS, "DocumentCurrencyCode", "MYR")

    # --- AccountingSupplierParty (Employee = Payee = Supplier in self-billed) ---
    supplier_party = _sub(root, CAC_NS, "AccountingSupplierParty")
    supplier_inner = _sub(supplier_party, CAC_NS, "Party")

    supplier_id = _sub(supplier_inner, CAC_NS, "PartyIdentification")
    _sub(supplier_id, CBC_NS, "ID", employee.custom_lhdn_tin)

    supplier_name_elem = _sub(supplier_inner, CAC_NS, "PartyName")
    _sub(supplier_name_elem, CBC_NS, "Name", employee.employee_name)

    # --- AccountingCustomerParty (Company = Payer = Buyer in self-billed) ---
    customer_party = _sub(root, CAC_NS, "AccountingCustomerParty")
    customer_inner = _sub(customer_party, CAC_NS, "Party")

    customer_id = _sub(customer_inner, CAC_NS, "PartyIdentification")
    _sub(customer_id, CBC_NS, "ID", company.custom_company_tin_number)

    customer_name_elem = _sub(customer_inner, CAC_NS, "PartyName")
    _sub(customer_name_elem, CBC_NS, "Name", company.name)

    # --- Calculate totals from earnings ONLY (never use YTD fields) ---
    total_excl = sum(_quantize(e.amount) for e in doc.earnings)
    total_tax = Decimal("0.00")
    total_incl = total_excl + total_tax

    assert_totals_balance(total_excl, total_tax, total_incl)

    # --- TaxTotal ---
    tax_total = _sub(root, CAC_NS, "TaxTotal")
    _sub(tax_total, CBC_NS, "TaxAmount", str(total_tax), currencyID="MYR")

    tax_subtotal_elem = _sub(tax_total, CAC_NS, "TaxSubtotal")
    _sub(tax_subtotal_elem, CBC_NS, "TaxableAmount", str(total_excl), currencyID="MYR")
    _sub(tax_subtotal_elem, CBC_NS, "TaxAmount", str(total_tax), currencyID="MYR")
    tax_cat = _sub(tax_subtotal_elem, CAC_NS, "TaxCategory")
    _sub(tax_cat, CBC_NS, "ID", "E")
    tax_scheme = _sub(tax_cat, CAC_NS, "TaxScheme")
    _sub(tax_scheme, CBC_NS, "ID", "OTH")

    # --- LegalMonetaryTotal ---
    monetary_total = _sub(root, CAC_NS, "LegalMonetaryTotal")
    _sub(monetary_total, CBC_NS, "TaxExclusiveAmount", str(total_excl), currencyID="MYR")
    _sub(monetary_total, CBC_NS, "TaxInclusiveAmount", str(total_incl), currencyID="MYR")
    _sub(monetary_total, CBC_NS, "PayableAmount", str(total_incl), currencyID="MYR")

    # --- InvoiceLines (one per earnings row) ---
    for idx, earning in enumerate(doc.earnings, start=1):
        line = _sub(root, CAC_NS, "InvoiceLine")
        _sub(line, CBC_NS, "ID", str(idx))
        _sub(line, CBC_NS, "InvoicedQuantity", "1", unitCode="C62")

        amount = _quantize(earning.amount)
        _sub(line, CBC_NS, "LineExtensionAmount", str(amount), currencyID="MYR")

        # Item with classification
        item = _sub(line, CAC_NS, "Item")
        _sub(item, CBC_NS, "Description", earning.salary_component)

        classification = getattr(earning, "custom_lhdn_classification_code", None)
        if classification and " : " in str(classification):
            class_code = str(classification).split(" : ")[0].strip()
        else:
            class_code = "022"

        commodity = _sub(item, CAC_NS, "CommodityClassification")
        _sub(commodity, CBC_NS, "ItemClassificationCode", class_code, listID="CLASS")

        # Price
        price = _sub(line, CAC_NS, "Price")
        _sub(price, CBC_NS, "PriceAmount", str(amount), currencyID="MYR")

    # Serialize to XML string
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
