"""Payroll Bank Disbursement File Generator.

US-071: Generate bank disbursement files for Maybank M2E, CIMB BizChannel,
and DuitNow Bulk (PayNet ISO 20022 pain.001.001.03).

Malaysian payroll file formats:
  - Maybank M2E: pipe-delimited with 5-digit org code header
  - CIMB BizChannel: CSV with Header/Detail/Footer structure
  - DuitNow Bulk: PayNet ISO 20022 pain.001.001.03 with SALA purpose code
"""
from datetime import date

import frappe
from frappe.utils import flt, today


# Supported banks
SUPPORTED_BANKS = [
    "Maybank",
    "CIMB",
    "Public Bank",
    "RHB",
    "DuitNow Bulk",
]


def generate_bank_file(payroll_entry_name, bank):
    """Generate a bank disbursement file for the given Payroll Entry.

    Args:
        payroll_entry_name (str): Name of the Payroll Entry document.
        bank (str): Target bank — one of SUPPORTED_BANKS.

    Returns:
        bytes: File content as bytes, ready for download.

    Raises:
        frappe.ValidationError: If the bank is not supported or required
            company fields are missing.
    """
    if bank not in SUPPORTED_BANKS:
        frappe.throw(
            f"Bank '{bank}' is not supported. Supported banks: {', '.join(SUPPORTED_BANKS)}"
        )

    entry = frappe.get_doc("Payroll Entry", payroll_entry_name)
    company = entry.company
    disbursement_date = today()

    slips = _get_salary_slips(payroll_entry_name)
    company_name = frappe.db.get_value("Company", company, "company_name") or company

    if bank == "Maybank":
        org_code = _get_company_field(company, "custom_maybank_org_code", "Maybank Org Code")
        return _generate_maybank_file(slips, org_code, disbursement_date)
    elif bank == "CIMB":
        org_code = _get_company_field(company, "custom_cimb_org_code", "CIMB Org Code")
        return _generate_cimb_file(slips, org_code, disbursement_date)
    elif bank == "DuitNow Bulk":
        return _generate_duitnow_file(slips, company_name, disbursement_date)
    else:
        # Public Bank and RHB: generic pipe-delimited
        return _generate_generic_file(slips, bank, disbursement_date)


def _get_salary_slips(payroll_entry_name):
    """Return list of submitted Salary Slip dicts for the Payroll Entry."""
    slips = frappe.db.sql(
        """
        SELECT
            ss.name,
            ss.employee,
            ss.employee_name,
            ss.net_pay,
            emp.custom_bank_name,
            emp.custom_bank_code,
            emp.custom_account_type,
            emp.custom_nric
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` emp ON emp.name = ss.employee
        WHERE ss.payroll_entry = %(payroll_entry)s
          AND ss.docstatus = 1
        ORDER BY ss.employee
        """,
        {"payroll_entry": payroll_entry_name},
        as_dict=True,
    )
    return slips


def _get_company_field(company, fieldname, label=""):
    """Fetch a custom field from Company, raising ValidationError if blank."""
    value = frappe.db.get_value("Company", company, fieldname)
    if not value:
        display = label or fieldname
        frappe.throw(
            f"Company '{company}' is missing required field: {display}. "
            f"Please fill it in under Company > LHDN Payroll Setup."
        )
    return value


# ---------------------------------------------------------------------------
# Maybank M2E format
# ---------------------------------------------------------------------------

def _generate_maybank_file(slips, org_code, disbursement_date):
    """Maybank M2E pipe-delimited file.

    Args:
        slips: list of salary slip dicts
        org_code (str): 5-digit Maybank organisation code
        disbursement_date (str): date string YYYYMMDD or YYYY-MM-DD

    Returns:
        bytes: pipe-delimited file content

    Format:
        Header:  ORG_CODE|PAY_DATE
        Details: ORG_CODE|PAY_DATE|NAME|NRIC|ACCOUNT|AMOUNT
    """
    pay_date = _format_date_yyyymmdd(disbursement_date)

    lines = []
    # Header row
    lines.append(f"{org_code}|{pay_date}")
    # Detail rows
    for slip in slips:
        name = (slip.get("employee_name") or slip.get("employee_name", "")).replace("|", " ")
        nric = (slip.get("custom_nric") or "").replace("|", "")
        account = (slip.get("custom_bank_code") or "").replace("|", "")
        amount = f"{flt(slip.get('net_pay', 0), 2):.2f}"
        lines.append(f"{org_code}|{pay_date}|{name}|{nric}|{account}|{amount}")

    content = "\r\n".join(lines) + "\r\n"
    return content.encode("utf-8")


# ---------------------------------------------------------------------------
# CIMB BizChannel format
# ---------------------------------------------------------------------------

def _generate_cimb_file(slips, org_code, disbursement_date):
    """CIMB BizChannel CSV with Header/Detail/Footer structure.

    Args:
        slips: list of salary slip dicts
        org_code (str): CIMB organisation code
        disbursement_date (str): date string YYYYMMDD or YYYY-MM-DD

    Returns:
        bytes: pipe-delimited file content

    Format:
        Header:  H|date|org_code
        Details: D|name|account|amount
        Footer:  T|count|total
    """
    pay_date = _format_date_yyyymmdd(disbursement_date)

    lines = []
    # Header
    lines.append(f"H|{pay_date}|{org_code}")

    total_amount = 0.0
    count = 0
    for slip in slips:
        name = (slip.get("employee_name") or "").replace("|", " ")
        account = (slip.get("custom_bank_code") or "").replace("|", "")
        amount = flt(slip.get("net_pay", 0), 2)
        lines.append(f"D|{name}|{account}|{amount:.2f}")
        total_amount += amount
        count += 1

    # Footer
    lines.append(f"T|{count}|{total_amount:.2f}")

    content = "\r\n".join(lines) + "\r\n"
    return content.encode("utf-8")


# ---------------------------------------------------------------------------
# DuitNow Bulk (PayNet ISO 20022 pain.001.001.03) format
# ---------------------------------------------------------------------------

def _generate_duitnow_file(slips, company_name, disbursement_date):
    """DuitNow Bulk ISO 20022 pain.001.001.03 XML with SALA purpose code.

    Args:
        slips: list of salary slip dicts
        company_name (str): company name for debtor identification
        disbursement_date (str): date string YYYY-MM-DD or YYYYMMDD

    Returns:
        bytes: UTF-8 encoded XML
    """
    # Normalise date to YYYY-MM-DD for XML
    raw = _format_date_yyyymmdd(disbursement_date)
    if len(raw) == 8:
        iso_date = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    else:
        iso_date = disbursement_date

    total_amount = sum(flt(s.get("net_pay", 0), 2) for s in slips)
    num_txns = len(slips)
    ctrl_sum = f"{total_amount:.2f}"
    msg_id = f"LHDN-PAYROLL-{raw}"
    creation_dt = f"{iso_date}T00:00:00"

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03">',
        "  <CstmrCdtTrfInitn>",
        "    <GrpHdr>",
        f"      <MsgId>{msg_id}</MsgId>",
        f"      <CreDtTm>{creation_dt}</CreDtTm>",
        f"      <NbOfTxs>{num_txns}</NbOfTxs>",
        f"      <CtrlSum>{ctrl_sum}</CtrlSum>",
        "      <InitgPty>",
        f"        <Nm>{_xml_escape(company_name)}</Nm>",
        "      </InitgPty>",
        "    </GrpHdr>",
        "    <PmtInf>",
        f"      <PmtInfId>{msg_id}-001</PmtInfId>",
        "      <PmtMtd>TRF</PmtMtd>",
        f"      <NbOfTxs>{num_txns}</NbOfTxs>",
        f"      <CtrlSum>{ctrl_sum}</CtrlSum>",
        "      <PmtTpInf>",
        "        <Purp>",
        "          <Cd>SALA</Cd>",
        "        </Purp>",
        "      </PmtTpInf>",
        f"      <ReqdExctnDt>{iso_date}</ReqdExctnDt>",
        "      <Dbtr>",
        f"        <Nm>{_xml_escape(company_name)}</Nm>",
        "      </Dbtr>",
        "      <DbtrAcct>",
        "        <Id><Othr><Id>COMPANY_ACCOUNT</Id></Othr></Id>",
        "      </DbtrAcct>",
        "      <DbtrAgt>",
        "        <FinInstnId><BIC>MBBEMYKL</BIC></FinInstnId>",
        "      </DbtrAgt>",
    ]

    for slip in slips:
        name = _xml_escape(slip.get("employee_name") or slip.get("employee", ""))
        account = slip.get("custom_bank_code") or ""
        amount = f"{flt(slip.get('net_pay', 0), 2):.2f}"
        emp = slip.get("employee", "")
        lines += [
            "      <CdtTrfTxInf>",
            "        <PmtId>",
            f"          <EndToEndId>PAYROLL-{emp}</EndToEndId>",
            "        </PmtId>",
            "        <Amt>",
            f'          <InstdAmt Ccy="MYR">{amount}</InstdAmt>',
            "        </Amt>",
            "        <Cdtr>",
            f"          <Nm>{name}</Nm>",
            "        </Cdtr>",
            "        <CdtrAcct>",
            f"          <Id><Othr><Id>{_xml_escape(account)}</Id></Othr></Id>",
            "        </CdtrAcct>",
            "      </CdtTrfTxInf>",
        ]

    lines += [
        "    </PmtInf>",
        "  </CstmrCdtTrfInitn>",
        "</Document>",
    ]

    content = "\n".join(lines) + "\n"
    return content.encode("utf-8")


# ---------------------------------------------------------------------------
# Generic pipe-delimited format (Public Bank, RHB)
# ---------------------------------------------------------------------------

def _generate_generic_file(slips, bank, disbursement_date):
    """Generic pipe-delimited file for banks without a specific format."""
    pay_date = _format_date_yyyymmdd(disbursement_date)
    lines = []
    lines.append(f"BANK:{bank}|DATE:{pay_date}")
    for slip in slips:
        name = (slip.get("employee_name") or "").replace("|", " ")
        account = (slip.get("custom_bank_code") or "").replace("|", "")
        amount = f"{flt(slip.get('net_pay', 0), 2):.2f}"
        lines.append(f"{name}|{account}|{amount}")

    content = "\r\n".join(lines) + "\r\n"
    return content.encode("utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_date_yyyymmdd(d):
    """Return date as YYYYMMDD string."""
    if isinstance(d, str):
        return d.replace("-", "")
    if isinstance(d, date):
        return d.strftime("%Y%m%d")
    return str(d).replace("-", "")


def _xml_escape(text):
    """Minimal XML character escaping."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


# ---------------------------------------------------------------------------
# Whitelisted API endpoint for desk button
# ---------------------------------------------------------------------------

@frappe.whitelist()
def download_bank_file(payroll_entry_name, bank):
    """Whitelisted endpoint: generate and return bank file as base64 for download.

    Called by the 'Generate Bank File' custom button on Payroll Entry form.

    Returns:
        dict with keys:
            filename (str): suggested download filename
            content_b64 (str): base64-encoded file bytes
            content_type (str): MIME type
    """
    import base64

    file_bytes = generate_bank_file(payroll_entry_name, bank)

    if bank == "DuitNow Bulk":
        ext = "xml"
        content_type = "application/xml"
    elif bank == "CIMB":
        ext = "csv"
        content_type = "text/csv"
    else:
        ext = "txt"
        content_type = "text/plain"

    safe_bank = bank.replace(" ", "_").replace("/", "_")
    filename = f"payroll_bank_{safe_bank}_{payroll_entry_name}.{ext}"

    return {
        "filename": filename,
        "content_b64": base64.b64encode(file_bytes).decode("utf-8"),
        "content_type": content_type,
    }
