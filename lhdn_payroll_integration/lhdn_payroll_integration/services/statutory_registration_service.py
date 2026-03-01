"""
US-156: Employer Statutory Registration Onboarding Checklist with Deadline Alerts

Daily scheduled job that scans all Malaysian companies for missing statutory
registrations and sends escalation emails when deadlines are exceeded.

Statutory deadlines (Malaysia):
- EPF:         7 working days from first hire  (EPF Act 1991)
- SOCSO:       30 calendar days from first hire (SSA 1969 s.7)
- LHDN E-Num:  7 calendar days from first hire (ITA 1967)
- EIS:         Automatic with SOCSO registration (EIS Act 2017)
- HRD Corp:    From date employer has 10+ Malaysian employees (PSMB Act 2001 Reg 4(1))
"""

import frappe
from frappe.utils import today, date_diff, getdate, get_url_to_form
from datetime import timedelta

# Statutory body configuration
STATUTORY_BODIES = {
    "EPF": {
        "deadline_days": 7,
        "deadline_type": "working_days",
        "registration_field": "custom_epf_employer_registration",
        "status_field": "custom_statutory_epf_status",
        "label": "EPF (Employees Provident Fund)",
        "penalty": "RM10,000 fine or 3 years imprisonment",
        "law": "EPF Act 1991",
        "portal_url": "https://i-akaun.kwsp.gov.my/",
    },
    "SOCSO": {
        "deadline_days": 30,
        "deadline_type": "calendar_days",
        "registration_field": "custom_socso_employer_number",
        "status_field": "custom_statutory_socso_status",
        "label": "SOCSO/PERKESO",
        "penalty": "RM5,000 fine or 2 years imprisonment",
        "law": "Employees' Social Security Act 1969 Section 7",
        "portal_url": "https://www.perkeso.gov.my/",
    },
    "LHDN_E_NUMBER": {
        "deadline_days": 7,
        "deadline_type": "calendar_days",
        "registration_field": "custom_epcb_plus_employer_e_number",
        "status_field": "custom_statutory_lhdn_e_number_status",
        "label": "LHDN E-Number (e-Daftar)",
        "penalty": "Application cancelled if documents not received in 14 days",
        "law": "Income Tax Act 1967",
        "portal_url": "https://edaftar.hasil.gov.my/",
    },
    "EIS": {
        "deadline_days": 30,
        "deadline_type": "calendar_days",
        "registration_field": "custom_eis_employer_number",
        "status_field": "custom_statutory_eis_status",
        "label": "EIS (Employment Insurance System)",
        "penalty": "Automatic with SOCSO registration; ensure SOCSO registration is completed",
        "law": "Employment Insurance System Act 2017",
        "portal_url": "https://www.perkeso.gov.my/",
    },
}


def count_working_days(start_date, end_date):
    """Count weekdays (Mon-Fri) between start_date (inclusive) and end_date (exclusive)."""
    start = getdate(start_date)
    end = getdate(end_date)
    count = 0
    current = start
    while current < end:
        if current.weekday() < 5:  # Mon=0, Fri=4
            count += 1
        current = current + timedelta(days=1)
    return count


def check_statutory_registration_deadlines():
    """Daily scheduled job: scan all Malaysian companies for statutory registration compliance."""
    companies = frappe.get_all("Company", filters={"country": "Malaysia"}, fields=["name"])
    for company in companies:
        try:
            _check_company_registrations(company.name)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Statutory Registration Check Failed: {company.name}",
            )


def _check_company_registrations(company_name):
    """Check all statutory registration deadlines for a single company."""
    company = frappe.get_doc("Company", company_name)

    # Get first active employee hire date
    first_hire = frappe.db.get_value(
        "Employee",
        {"company": company_name, "status": "Active"},
        "date_of_joining",
        order_by="date_of_joining asc",
    )

    if not first_hire:
        # No active employees — clear status fields
        for body in STATUTORY_BODIES.values():
            _set_status(company_name, body["status_field"], "")
        _set_status(company_name, "custom_statutory_hrdf_status", "")
        frappe.db.set_value("Company", company_name, "custom_first_employee_hire_date", None)
        return

    # Update the first hire date tracking field
    frappe.db.set_value("Company", company_name, "custom_first_employee_hire_date", first_hire)

    today_date = getdate(today())
    calendar_days_elapsed = date_diff(today_date, first_hire)
    working_days_elapsed = count_working_days(first_hire, today_date)

    # Check each statutory body
    for body_key, body in STATUTORY_BODIES.items():
        reg_number = company.get(body["registration_field"])

        if reg_number:
            _set_status(company_name, body["status_field"], "Registered")
        else:
            elapsed = working_days_elapsed if body["deadline_type"] == "working_days" else calendar_days_elapsed

            if elapsed > body["deadline_days"]:
                _set_status(company_name, body["status_field"], "Overdue")
                _send_overdue_alert(company, body_key, body, first_hire, elapsed)
            else:
                _set_status(company_name, body["status_field"], "Pending")

    # HRD Corp: separate threshold check (10+ Malaysian employees)
    _check_hrdf_status(company_name, company)


def _check_hrdf_status(company_name, company):
    """Check HRD Corp registration requirement based on Malaysian employee count."""
    malaysian_count = frappe.db.count(
        "Employee",
        filters={
            "company": company_name,
            "status": "Active",
            "nationality": "Malaysian",
        },
    )

    hrdf_number = company.get("custom_hrdf_corp_registration_number")

    if malaysian_count >= 10:
        if not hrdf_number:
            _set_status(company_name, "custom_statutory_hrdf_status", "Overdue")
            _send_hrdf_alert(company, malaysian_count)
        else:
            _set_status(company_name, "custom_statutory_hrdf_status", "Registered")
    else:
        _set_status(company_name, "custom_statutory_hrdf_status", "Not Required")


def _set_status(company_name, field, status):
    frappe.db.set_value("Company", company_name, field, status)


def _get_hr_managers(company_name):
    """Return email addresses of enabled HR Manager role users."""
    hr_managers = frappe.get_all(
        "Has Role",
        filters={"role": "HR Manager"},
        fields=["parent"],
        ignore_permissions=True,
    )
    emails = []
    for u in hr_managers:
        user_email = frappe.db.get_value("User", {"name": u.parent, "enabled": 1}, "email")
        if user_email:
            emails.append(user_email)
    return emails


def _send_overdue_alert(company, body_key, body, first_hire, elapsed):
    """Send overdue registration alert email to HR Managers."""
    recipients = _get_hr_managers(company.name)
    if not recipients:
        return

    subject = f"[URGENT] {body['label']} Registration OVERDUE — {company.name}"
    message = f"""
    <p>Dear HR Manager,</p>
    <p>This is an automated compliance alert from the LHDN Payroll Integration system.</p>
    <h3 style="color:red;">&#9888; OVERDUE: {body['label']} Employer Registration</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
        <tr><td><b>Company</b></td><td>{company.name}</td></tr>
        <tr><td><b>Statutory Body</b></td><td>{body['label']}</td></tr>
        <tr><td><b>First Employee Hire Date</b></td><td>{first_hire}</td></tr>
        <tr><td><b>Registration Deadline</b></td><td>{body['deadline_days']} {body['deadline_type'].replace('_', ' ')} from first hire</td></tr>
        <tr><td><b>Days / Working Days Elapsed</b></td><td>{elapsed}</td></tr>
        <tr><td><b>Applicable Law</b></td><td>{body['law']}</td></tr>
        <tr><td><b>Penalty Risk</b></td><td style="color:red;"><b>{body['penalty']}</b></td></tr>
        <tr><td><b>Registration Portal</b></td><td><a href="{body['portal_url']}">{body['portal_url']}</a></td></tr>
    </table>
    <p><b>Immediate action required.</b> Please complete registration and update the
    employer registration number in the Company record:</p>
    <p><a href="{get_url_to_form('Company', company.name)}">&#128279; Open Company Record — {company.name}</a></p>
    <hr/>
    <p style="color:grey;font-size:12px;"><i>This is an automated message from LHDN Payroll Integration (US-156).</i></p>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        delayed=False,
    )


def _send_hrdf_alert(company, malaysian_count):
    """Send HRD Corp registration prompt when Malaysian employee count reaches 10."""
    recipients = _get_hr_managers(company.name)
    if not recipients:
        return

    subject = f"[Action Required] HRD Corp Registration Required — {company.name}"
    message = f"""
    <p>Dear HR Manager,</p>
    <p>This is an automated compliance notification from the LHDN Payroll Integration system.</p>
    <h3 style="color:orange;">&#9888; HRD Corp Registration Required</h3>
    <p>Company <b>{company.name}</b> now has <b>{malaysian_count} Malaysian employees</b>,
       which meets the threshold requiring mandatory HRD Corp registration.</p>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
        <tr><td><b>Malaysian Employee Count</b></td><td>{malaysian_count}</td></tr>
        <tr><td><b>Registration Threshold</b></td><td>10 Malaysian employees in covered sectors</td></tr>
        <tr><td><b>Applicable Law</b></td><td>PSMB Act 2001 Regulation 4(1)</td></tr>
        <tr><td><b>Levy Rate</b></td><td>0.5% of monthly wages (10–49 employees) / 1.0% (50+ employees)</td></tr>
        <tr><td><b>Registration Portal</b></td><td><a href="https://www.hrdcorp.gov.my/">https://www.hrdcorp.gov.my/</a></td></tr>
    </table>
    <p>After registering, update the HRD Corp Registration Number in the Company record:</p>
    <p><a href="{get_url_to_form('Company', company.name)}">&#128279; Open Company Record — {company.name}</a></p>
    <hr/>
    <p style="color:grey;font-size:12px;"><i>This is an automated message from LHDN Payroll Integration (US-156).</i></p>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        delayed=False,
    )
