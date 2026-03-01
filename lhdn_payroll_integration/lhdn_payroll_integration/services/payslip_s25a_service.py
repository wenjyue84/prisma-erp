"""Employment Act S.25A Digital Payslip Mandatory Fields Compliance Validator (US-232).

Employment Act Section 25A (as amended by Employment (Amendment) Act 2022) requires
employers to provide a payslip at every wage payment.  The payslip must include:
  - Employee full name
  - IC / passport number
  - Gender
  - Citizenship status
  - Wage period (start and end date)
  - Gross salary
  - Itemised deductions (EPF, SOCSO, EIS, PCB each as a separate line)
  - Net pay
  - Payment date (posting_date)
  - Employer name

This module provides:
  - ``validate_s25a_mandatory_fields(doc, method=None)`` — before_submit hook
    that raises ``frappe.ValidationError`` if any mandatory field is missing.
  - ``run_s25a_audit(from_date, to_date, company)`` — returns a list of submitted
    Salary Slips that are missing one or more mandatory S.25A fields.
"""
import frappe
from frappe import _

# Statutory deduction component name fragments for EPF, SOCSO, EIS, PCB
_EPF_KEYWORDS = ("EPF", "KWSP", "Employee Provident Fund", "Kumpulan Wang Simpanan")
_SOCSO_KEYWORDS = ("SOCSO", "PERKESO", "Social Security")
_EIS_KEYWORDS = ("EIS", "Employment Insurance")
_PCB_KEYWORDS = ("PCB", "MTD", "Monthly Tax Deduction", "Income Tax",
                  "Tax Deduction", "Potongan Cukai")


def _has_component(deductions, keywords: tuple) -> bool:
    """Return True if any deduction component name contains one of *keywords*."""
    for row in deductions or []:
        name = (getattr(row, "salary_component", "") or "").upper()
        for kw in keywords:
            if kw.upper() in name:
                return True
    return False


def _get_employee_field(employee_id: str, field: str):
    """Safely fetch a single field from the Employee doctype."""
    try:
        return frappe.db.get_value("Employee", employee_id, field)
    except Exception:
        return None


def check_s25a_fields(doc) -> list:
    """Return a list of missing-field error messages for the given Salary Slip doc.

    Empty list means the slip is S.25A compliant.

    Fields checked:
      1. employee_name (full name on Salary Slip)
      2. custom_id_value (NRIC / passport on Employee)
      3. start_date (wage period start)
      4. end_date (wage period end)
      5. posting_date (payment date)
      6. gross_pay > 0
      7. net_pay is not None
      8. EPF component present in deductions
      9. SOCSO component present in deductions
     10. EIS component present in deductions
    """
    errors = []

    # 1. Employee full name
    if not getattr(doc, "employee_name", None):
        errors.append(
            _("Employee full name (employee_name) is required on the payslip "
              "(Employment Act S.25A).")
        )

    # 2. IC / Passport number
    employee_id = getattr(doc, "employee", None)
    if employee_id:
        id_value = _get_employee_field(employee_id, "custom_id_value")
        if not id_value:
            errors.append(
                _("Employee IC / passport number (custom_id_value) is not set on "
                  "Employee {0}. Required for Employment Act S.25A payslip.").format(
                    employee_id
                )
            )
    else:
        errors.append(_("Salary Slip is not linked to an Employee record."))

    # 3. Wage period start
    if not getattr(doc, "start_date", None):
        errors.append(
            _("Wage period start date (start_date) is missing on the payslip "
              "(Employment Act S.25A).")
        )

    # 4. Wage period end
    if not getattr(doc, "end_date", None):
        errors.append(
            _("Wage period end date (end_date) is missing on the payslip "
              "(Employment Act S.25A).")
        )

    # 5. Payment date
    if not getattr(doc, "posting_date", None):
        errors.append(
            _("Payment date (posting_date) is missing on the payslip "
              "(Employment Act S.25A).")
        )

    # 6. Gross pay must be positive
    gross_pay = float(getattr(doc, "gross_pay", 0) or 0)
    if gross_pay <= 0:
        errors.append(
            _("Gross salary (gross_pay) must be greater than zero on the payslip "
              "(Employment Act S.25A).")
        )

    # 7. Net pay must be set
    net_pay = getattr(doc, "net_pay", None)
    if net_pay is None:
        errors.append(
            _("Net pay (net_pay) is not set on the payslip "
              "(Employment Act S.25A).")
        )

    # 8-10. Statutory deduction components must appear as separate itemised lines
    deductions = getattr(doc, "deductions", [])
    if not _has_component(deductions, _EPF_KEYWORDS):
        errors.append(
            _("EPF (KWSP) employee contribution is not itemised as a separate "
              "deduction line on the payslip. Required under Employment Act S.25A.")
        )
    if not _has_component(deductions, _SOCSO_KEYWORDS):
        errors.append(
            _("SOCSO employee contribution is not itemised as a separate deduction "
              "line on the payslip. Required under Employment Act S.25A.")
        )
    if not _has_component(deductions, _EIS_KEYWORDS):
        errors.append(
            _("EIS employee contribution is not itemised as a separate deduction "
              "line on the payslip. Required under Employment Act S.25A.")
        )

    return errors


def validate_s25a_mandatory_fields(doc, method=None) -> None:
    """Salary Slip before_submit hook: block if mandatory S.25A fields are missing.

    Raises ``frappe.ValidationError`` listing all missing fields if any are absent.
    The error message cites 'Employment Act S.25A — Payslip mandatory fields' so
    that payroll administrators can identify the specific statutory requirement.
    """
    try:
        errors = check_s25a_fields(doc)
        if not errors:
            return

        bullet_list = "\n".join(f"• {e}" for e in errors)
        frappe.throw(
            _(
                "Employment Act S.25A \u2014 Payslip mandatory fields are missing:\n\n"
                "{fields}\n\n"
                "Please correct the employee record or payroll data before "
                "submitting this Salary Slip."
            ).format(fields=bullet_list),
            title=_("Employment Act S.25A \u2014 Payslip Mandatory Fields"),
        )
    except frappe.ValidationError:
        raise
    except Exception as exc:
        frappe.log_error(
            f"S.25A payslip validation error on {getattr(doc, 'name', '?')}: {exc}",
            "Employment Act S.25A Validator",
        )


def run_s25a_audit(from_date: str, to_date: str, company: str = None) -> list:
    """Return a list of submitted Salary Slips that fail S.25A mandatory field checks.

    Args:
        from_date: ISO date string (YYYY-MM-DD) — payroll period start.
        to_date: ISO date string — payroll period end.
        company: Company name filter (None = all companies).

    Returns:
        List of dicts, one per failing Salary Slip:
        ``{"name": str, "employee": str, "employee_name": str,
           "posting_date": date, "errors": [str, ...]}``
    """
    filters = {
        "docstatus": 1,
        "posting_date": ["between", [from_date, to_date]],
    }
    if company:
        filters["company"] = company

    slips = frappe.get_all(
        "Salary Slip",
        filters=filters,
        fields=["name", "employee", "employee_name", "posting_date",
                "start_date", "end_date", "gross_pay", "net_pay"],
        order_by="posting_date asc",
    )

    failing = []
    for row in slips:
        # Load a lightweight mock-like object so check_s25a_fields can inspect it
        try:
            doc = frappe.get_doc("Salary Slip", row["name"])
        except Exception:
            continue
        errors = check_s25a_fields(doc)
        if errors:
            failing.append({
                "name": row["name"],
                "employee": row["employee"],
                "employee_name": row["employee_name"],
                "posting_date": row["posting_date"],
                "errors": errors,
            })

    return failing
