"""TP3 30-Day Collection Deadline Compliance Alert for Mid-Year New Hires (US-219).

LHDN regulations require employees with prior-year income to submit the TP3
form to their new employer within 30 days of joining, and the employer must
process it before computing the first monthly PCB.  Without TP3, PCB is computed
as if the employee has no prior income, systematically under-deducting tax and
creating employer audit liability under Section 107A ITA 1967.

Key rules:
  - 30-day TP3 collection window from date_of_joining.
  - 14-day alert: notification sent to HR 14 days after join when TP3 missing.
  - Red warning on Salary Slip generation for mid-year hire with no TP3.
  - HR dashboard: list of employees overdue beyond 30 days.
  - January joiners (1 Jan – 31 Jan) are excluded — no prior-employer income
    in the current year.
  - Alert auto-clears when a TP3 record is saved and linked.
"""

from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Regulatory deadline: employee must submit TP3 within this many days
TP3_COLLECTION_DEADLINE_DAYS = 30

#: Days after join date when the first reminder alert fires
FIRST_ALERT_DAYS_AFTER_JOIN = 14

#: January cutoff: joiners in Jan (day 1–31) are excluded
JANUARY_EXCLUSION_MONTH = 1

#: Severity levels for dashboard display
SEVERITY_OVERDUE = "Overdue"
SEVERITY_APPROACHING = "Approaching"
SEVERITY_OK = "OK"
SEVERITY_EXEMPT = "Exempt"

#: Status labels
STATUS_TP3_MISSING = "TP3 Missing"
STATUS_TP3_RECEIVED = "TP3 Received"
STATUS_EXEMPT_JANUARY = "Exempt (January Joiner)"
STATUS_EXEMPT_NOT_MID_YEAR = "Exempt (Not Mid-Year Hire)"

#: Dashboard bucket labels
BUCKET_OVERDUE = "overdue"
BUCKET_ALERT_SENT = "alert_sent"
BUCKET_WITHIN_WINDOW = "within_window"
BUCKET_RECEIVED = "received"
BUCKET_EXEMPT = "exempt"

#: Warning message for Salary Slip
SALARY_SLIP_WARNING = (
    "WARNING: Employee joined mid-year without a TP3 declaration on file. "
    "PCB may be under-deducted. Collect TP3 from employee immediately."
)

#: Notification subject template
NOTIFICATION_SUBJECT = "TP3 Collection Required: {employee_name} ({employee_id})"

#: Notification body template
NOTIFICATION_BODY = (
    "Employee {employee_name} ({employee_id}) joined on {join_date} and has not "
    "submitted a TP3 (Prior Employer YTD Declaration). "
    "{days_since_join} days have elapsed since joining. "
    "The 30-day regulatory deadline {deadline_status}. "
    "Please collect the TP3 form to ensure correct PCB computation."
)


# ---------------------------------------------------------------------------
# Core eligibility checks
# ---------------------------------------------------------------------------

def is_mid_year_hire(join_date, tax_year=None):
    """Return True if the employee joined after January of the given tax year.

    January joiners (1 Jan – 31 Jan) are excluded because they have no
    prior-employer income in the current assessment year.

    Args:
        join_date: The employee's date of joining (date or ISO string).
        tax_year: The assessment year to check against.  Defaults to
                  join_date's year.

    Returns:
        bool: True if mid-year hire requiring TP3 collection.
    """
    if join_date is None:
        return False

    if isinstance(join_date, str):
        join_date = date.fromisoformat(str(join_date)[:10])

    if tax_year is None:
        tax_year = join_date.year

    # Must be in the same tax year
    if join_date.year != int(tax_year):
        return False

    # January joiners are excluded
    if join_date.month == JANUARY_EXCLUSION_MONTH:
        return False

    return True


def has_tp3_on_file(employee_id, tax_year):
    """Check whether a TP3 record exists for the given employee and year.

    Args:
        employee_id: Employee document name.
        tax_year: Assessment year.

    Returns:
        bool: True if a TP3 record is linked.
    """
    if not employee_id or not tax_year:
        return False

    # Check via tp3_records dict (passed externally in batch mode)
    # In production this would query Frappe DB; here we accept a record dict
    # This function is a stub for the service layer — actual DB query is in
    # check_employee_tp3_status() which accepts pre-fetched data.
    return False


# ---------------------------------------------------------------------------
# Deadline computation
# ---------------------------------------------------------------------------

def compute_tp3_deadline(join_date):
    """Compute the TP3 collection deadline (join_date + 30 days).

    Args:
        join_date: Employee's date of joining (date or ISO string).

    Returns:
        date: The deadline date.
    """
    if isinstance(join_date, str):
        join_date = date.fromisoformat(str(join_date)[:10])

    return join_date + timedelta(days=TP3_COLLECTION_DEADLINE_DAYS)


def compute_first_alert_date(join_date):
    """Compute when the first TP3 reminder should fire (join_date + 14 days).

    Args:
        join_date: Employee's date of joining (date or ISO string).

    Returns:
        date: The first alert date.
    """
    if isinstance(join_date, str):
        join_date = date.fromisoformat(str(join_date)[:10])

    return join_date + timedelta(days=FIRST_ALERT_DAYS_AFTER_JOIN)


def get_days_since_join(join_date, as_of_date=None):
    """Calculate days elapsed since the employee's join date.

    Args:
        join_date: Employee's date of joining.
        as_of_date: Reference date; defaults to today.

    Returns:
        int: Number of days since joining.
    """
    if isinstance(join_date, str):
        join_date = date.fromisoformat(str(join_date)[:10])
    if as_of_date is None:
        as_of_date = date.today()
    elif isinstance(as_of_date, str):
        as_of_date = date.fromisoformat(str(as_of_date)[:10])

    return (as_of_date - join_date).days


def get_days_until_deadline(join_date, as_of_date=None):
    """Calculate days remaining until the 30-day TP3 deadline.

    Args:
        join_date: Employee's date of joining.
        as_of_date: Reference date; defaults to today.

    Returns:
        int: Days remaining (negative if overdue).
    """
    deadline = compute_tp3_deadline(join_date)
    if as_of_date is None:
        as_of_date = date.today()
    elif isinstance(as_of_date, str):
        as_of_date = date.fromisoformat(str(as_of_date)[:10])

    return (deadline - as_of_date).days


def is_deadline_overdue(join_date, as_of_date=None):
    """Return True if the 30-day TP3 collection deadline has passed.

    Args:
        join_date: Employee's date of joining.
        as_of_date: Reference date; defaults to today.

    Returns:
        bool: True if overdue.
    """
    return get_days_until_deadline(join_date, as_of_date) < 0


def should_send_first_alert(join_date, as_of_date=None):
    """Return True if today is on or after the 14-day first alert date.

    Args:
        join_date: Employee's date of joining.
        as_of_date: Reference date; defaults to today.

    Returns:
        bool: True if first alert should be triggered.
    """
    days = get_days_since_join(join_date, as_of_date)
    return days >= FIRST_ALERT_DAYS_AFTER_JOIN


# ---------------------------------------------------------------------------
# Employee status assessment
# ---------------------------------------------------------------------------

def check_employee_tp3_status(employee_record, as_of_date=None):
    """Assess TP3 collection status for a single employee.

    Args:
        employee_record: dict with keys:
            - employee_id (str): Employee document name
            - employee_name (str): Employee full name
            - join_date (date|str): Date of joining
            - tax_year (int): Assessment year
            - has_tp3 (bool): Whether a TP3 record exists
        as_of_date: Reference date; defaults to today.

    Returns:
        dict with keys:
            - employee_id, employee_name, join_date, tax_year
            - is_mid_year_hire (bool)
            - has_tp3 (bool)
            - deadline (date): TP3 collection deadline
            - first_alert_date (date): When first reminder fires
            - days_since_join (int)
            - days_until_deadline (int): Negative if overdue
            - is_overdue (bool)
            - should_alert (bool): True if alert should be sent
            - severity (str): SEVERITY_* constant
            - status (str): STATUS_* constant
            - bucket (str): BUCKET_* constant
            - warning_message (str|None): For Salary Slip display
    """
    emp_id = employee_record.get("employee_id", "")
    emp_name = employee_record.get("employee_name", "")
    join_dt = employee_record.get("join_date")
    tax_year = employee_record.get("tax_year")
    has_tp3 = employee_record.get("has_tp3", False)

    if isinstance(join_dt, str):
        join_dt = date.fromisoformat(str(join_dt)[:10])

    result = {
        "employee_id": emp_id,
        "employee_name": emp_name,
        "join_date": join_dt,
        "tax_year": tax_year,
        "is_mid_year_hire": False,
        "has_tp3": has_tp3,
        "deadline": None,
        "first_alert_date": None,
        "days_since_join": 0,
        "days_until_deadline": 0,
        "is_overdue": False,
        "should_alert": False,
        "severity": SEVERITY_OK,
        "status": STATUS_EXEMPT_NOT_MID_YEAR,
        "bucket": BUCKET_EXEMPT,
        "warning_message": None,
    }

    if join_dt is None:
        return result

    mid_year = is_mid_year_hire(join_dt, tax_year)
    result["is_mid_year_hire"] = mid_year

    if not mid_year:
        # January joiner check
        if join_dt.month == JANUARY_EXCLUSION_MONTH and (
            tax_year is None or join_dt.year == int(tax_year)
        ):
            result["status"] = STATUS_EXEMPT_JANUARY
        return result

    # Mid-year hire — compute deadline info
    result["deadline"] = compute_tp3_deadline(join_dt)
    result["first_alert_date"] = compute_first_alert_date(join_dt)
    result["days_since_join"] = get_days_since_join(join_dt, as_of_date)
    result["days_until_deadline"] = get_days_until_deadline(join_dt, as_of_date)
    result["is_overdue"] = result["days_until_deadline"] < 0

    if has_tp3:
        result["severity"] = SEVERITY_OK
        result["status"] = STATUS_TP3_RECEIVED
        result["bucket"] = BUCKET_RECEIVED
        result["should_alert"] = False
        return result

    # TP3 missing
    result["status"] = STATUS_TP3_MISSING
    result["warning_message"] = SALARY_SLIP_WARNING

    if result["is_overdue"]:
        result["severity"] = SEVERITY_OVERDUE
        result["bucket"] = BUCKET_OVERDUE
        result["should_alert"] = True
    elif should_send_first_alert(join_dt, as_of_date):
        result["severity"] = SEVERITY_APPROACHING
        result["bucket"] = BUCKET_ALERT_SENT
        result["should_alert"] = True
    else:
        result["severity"] = SEVERITY_OK
        result["bucket"] = BUCKET_WITHIN_WINDOW
        result["should_alert"] = False

    return result


# ---------------------------------------------------------------------------
# Salary Slip warning
# ---------------------------------------------------------------------------

def get_salary_slip_tp3_warning(employee_record, as_of_date=None):
    """Return a warning message for Salary Slip if TP3 is missing.

    Args:
        employee_record: dict with employee_id, join_date, tax_year, has_tp3.
        as_of_date: Reference date.

    Returns:
        str|None: Warning message or None if no warning needed.
    """
    status = check_employee_tp3_status(employee_record, as_of_date)
    return status.get("warning_message")


# ---------------------------------------------------------------------------
# Batch processing — HR dashboard
# ---------------------------------------------------------------------------

def get_outstanding_tp3_employees(employee_records, as_of_date=None):
    """Return list of employees with outstanding TP3 beyond 30-day deadline.

    Args:
        employee_records: List of employee record dicts.
        as_of_date: Reference date.

    Returns:
        list[dict]: Employee status records where TP3 is overdue.
    """
    results = []
    for rec in employee_records:
        status = check_employee_tp3_status(rec, as_of_date)
        if status["is_overdue"] and not status["has_tp3"]:
            results.append(status)

    # Sort by days overdue (most overdue first)
    results.sort(key=lambda x: x["days_until_deadline"])
    return results


def get_pending_tp3_alerts(employee_records, as_of_date=None):
    """Return list of employees needing TP3 alert (14+ days, no TP3).

    Args:
        employee_records: List of employee record dicts.
        as_of_date: Reference date.

    Returns:
        list[dict]: Employee status records where alert should be sent.
    """
    results = []
    for rec in employee_records:
        status = check_employee_tp3_status(rec, as_of_date)
        if status["should_alert"] and not status["has_tp3"]:
            results.append(status)

    results.sort(key=lambda x: x["days_until_deadline"])
    return results


def generate_tp3_dashboard_summary(employee_records, as_of_date=None):
    """Generate a summary for the HR dashboard grouped by bucket.

    Args:
        employee_records: List of employee record dicts.
        as_of_date: Reference date.

    Returns:
        dict with keys:
            - total_mid_year_hires (int)
            - total_tp3_received (int)
            - total_tp3_missing (int)
            - total_overdue (int)
            - total_alert_sent (int)
            - total_within_window (int)
            - total_exempt (int)
            - buckets (dict): {bucket_name: [employee_status_dicts]}
            - overdue_employees (list): Sorted by days overdue
            - compliance_rate (float): Percentage of mid-year hires with TP3
    """
    buckets = {
        BUCKET_OVERDUE: [],
        BUCKET_ALERT_SENT: [],
        BUCKET_WITHIN_WINDOW: [],
        BUCKET_RECEIVED: [],
        BUCKET_EXEMPT: [],
    }

    total_mid_year = 0
    total_received = 0
    total_missing = 0

    for rec in employee_records:
        status = check_employee_tp3_status(rec, as_of_date)
        bucket = status["bucket"]
        buckets[bucket].append(status)

        if status["is_mid_year_hire"]:
            total_mid_year += 1
            if status["has_tp3"]:
                total_received += 1
            else:
                total_missing += 1

    # Sort overdue by severity (most overdue first)
    buckets[BUCKET_OVERDUE].sort(key=lambda x: x["days_until_deadline"])

    compliance_rate = 0.0
    if total_mid_year > 0:
        compliance_rate = round((total_received / total_mid_year) * 100, 1)

    return {
        "total_mid_year_hires": total_mid_year,
        "total_tp3_received": total_received,
        "total_tp3_missing": total_missing,
        "total_overdue": len(buckets[BUCKET_OVERDUE]),
        "total_alert_sent": len(buckets[BUCKET_ALERT_SENT]),
        "total_within_window": len(buckets[BUCKET_WITHIN_WINDOW]),
        "total_exempt": len(buckets[BUCKET_EXEMPT]),
        "buckets": buckets,
        "overdue_employees": buckets[BUCKET_OVERDUE],
        "compliance_rate": compliance_rate,
    }


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------

def build_notification(employee_record, as_of_date=None):
    """Build a notification dict for an employee needing TP3 collection.

    Args:
        employee_record: dict with employee_id, employee_name, join_date, tax_year, has_tp3.
        as_of_date: Reference date.

    Returns:
        dict|None: Notification dict with subject, body, recipients, severity.
                   None if no notification needed.
    """
    status = check_employee_tp3_status(employee_record, as_of_date)

    if not status["should_alert"]:
        return None

    deadline = status["deadline"]
    deadline_status = "has passed" if status["is_overdue"] else "is approaching"

    subject = NOTIFICATION_SUBJECT.format(
        employee_name=status["employee_name"],
        employee_id=status["employee_id"],
    )
    body = NOTIFICATION_BODY.format(
        employee_name=status["employee_name"],
        employee_id=status["employee_id"],
        join_date=str(status["join_date"]),
        days_since_join=status["days_since_join"],
        deadline_status=deadline_status,
    )

    return {
        "subject": subject,
        "body": body,
        "recipients": ["HR Manager"],
        "severity": status["severity"],
        "employee_id": status["employee_id"],
        "employee_name": status["employee_name"],
        "deadline": str(deadline),
        "days_until_deadline": status["days_until_deadline"],
        "is_overdue": status["is_overdue"],
    }


def build_batch_notifications(employee_records, as_of_date=None):
    """Build notifications for all employees needing TP3 alerts.

    Args:
        employee_records: List of employee record dicts.
        as_of_date: Reference date.

    Returns:
        list[dict]: Notification dicts for employees needing alerts.
    """
    notifications = []
    for rec in employee_records:
        notif = build_notification(rec, as_of_date)
        if notif is not None:
            notifications.append(notif)

    # Sort: overdue first, then by deadline proximity
    notifications.sort(key=lambda x: x["days_until_deadline"])
    return notifications


# ---------------------------------------------------------------------------
# Auto-clear check
# ---------------------------------------------------------------------------

def is_alert_cleared(employee_record, as_of_date=None):
    """Return True if the TP3 alert should be cleared (TP3 received).

    Args:
        employee_record: dict with has_tp3 flag.
        as_of_date: Reference date (unused but kept for API consistency).

    Returns:
        bool: True if TP3 is on file and alert should be dismissed.
    """
    return bool(employee_record.get("has_tp3", False))


# ---------------------------------------------------------------------------
# Compliance report
# ---------------------------------------------------------------------------

def generate_compliance_report(employee_records, as_of_date=None):
    """Generate a compliance report for all mid-year hires.

    Args:
        employee_records: List of employee record dicts.
        as_of_date: Reference date.

    Returns:
        dict with keys:
            - report_date (str): The as_of_date
            - summary (dict): Dashboard summary
            - employees (list): All employee statuses sorted by severity
            - action_required (list): Employees needing immediate action
            - section_107a_risk (list): Overdue employees posing employer liability
    """
    if as_of_date is None:
        as_of_date = date.today()
    elif isinstance(as_of_date, str):
        as_of_date = date.fromisoformat(str(as_of_date)[:10])

    summary = generate_tp3_dashboard_summary(employee_records, as_of_date)

    all_statuses = []
    action_required = []
    section_107a_risk = []

    for rec in employee_records:
        status = check_employee_tp3_status(rec, as_of_date)
        all_statuses.append(status)

        if status["should_alert"] and not status["has_tp3"]:
            action_required.append(status)

        if status["is_overdue"] and not status["has_tp3"]:
            section_107a_risk.append(status)

    # Sort by severity: overdue first, then approaching, then ok
    severity_order = {SEVERITY_OVERDUE: 0, SEVERITY_APPROACHING: 1, SEVERITY_OK: 2, SEVERITY_EXEMPT: 3}
    all_statuses.sort(key=lambda x: severity_order.get(x["severity"], 99))
    action_required.sort(key=lambda x: x["days_until_deadline"])
    section_107a_risk.sort(key=lambda x: x["days_until_deadline"])

    return {
        "report_date": str(as_of_date),
        "summary": summary,
        "employees": all_statuses,
        "action_required": action_required,
        "section_107a_risk": section_107a_risk,
    }
