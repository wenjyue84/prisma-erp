"""
US-100: Bulk Payslip Generation API

Employment Act 1955 S.61 compliant bulk payslip generation.
Generates individual payslips for all employees in a Payroll Entry
and returns them as a ZIP archive.
"""

import io
import zipfile
import frappe
from frappe import _
from frappe.utils.pdf import get_pdf


PRINT_FORMAT = "EA S.61 Payslip"


@frappe.whitelist()
def generate_bulk_payslips(payroll_entry=None, salary_slips=None, print_format=None):
    """
    Generate EA S.61 compliant payslips for a payroll run.

    Args:
        payroll_entry (str): Name of the Payroll Entry document.
            If provided, fetches all submitted Salary Slips linked to it.
        salary_slips (list|str): List of Salary Slip names to generate payslips for.
            Takes precedence over payroll_entry if both are provided.
        print_format (str): Print format name. Defaults to "EA S.61 Payslip".

    Returns:
        dict: {
            "file_url": str,   # URL to download the ZIP archive
            "count": int,      # Number of payslips generated
            "errors": list     # List of slips that failed with reasons
        }
    """
    frappe.only_for("HR Manager")

    pf = print_format or PRINT_FORMAT

    # Resolve salary slip list
    slip_names = _resolve_slip_names(payroll_entry, salary_slips)
    if not slip_names:
        frappe.throw(_("No submitted Salary Slips found for the given inputs."))

    zip_buffer = io.BytesIO()
    errors = []
    count = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for slip_name in slip_names:
            try:
                pdf_bytes = get_pdf(
                    frappe.get_doc("Salary Slip", slip_name).as_dict(),
                    print_format=pf,
                    no_letterhead=1,
                )
                filename = f"{slip_name.replace('/', '-')}_payslip.pdf"
                zf.writestr(filename, pdf_bytes)
                count += 1
            except Exception as e:
                errors.append({"slip": slip_name, "error": str(e)})

    zip_buffer.seek(0)
    zip_name = f"payslips_{frappe.utils.nowdate().replace('-', '')}.zip"

    # Save to File doctype
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": zip_name,
        "content": zip_buffer.read(),
        "is_private": 1,
    })
    file_doc.save(ignore_permissions=True)

    return {
        "file_url": file_doc.file_url,
        "count": count,
        "errors": errors,
    }


def _resolve_slip_names(payroll_entry, salary_slips):
    """Return a list of Salary Slip names to process."""
    if salary_slips:
        if isinstance(salary_slips, str):
            import json as _json
            try:
                salary_slips = _json.loads(salary_slips)
            except Exception:
                salary_slips = [salary_slips]
        return salary_slips

    if payroll_entry:
        return frappe.get_all(
            "Salary Slip",
            filters={"payroll_entry": payroll_entry, "docstatus": 1},
            pluck="name",
        )

    return []
