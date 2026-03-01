"""Gig Workers Act 2025 — 7-Day Payment Deadline Alert for Informal Gig
Engagements Without Payment Schedule (US-183).

Under the Gig Workers Act 2025 (Act 872), contracting entities must remit
payment to gig workers within 7 days of service completion when no formal
agreement specifies a payment schedule.  This is distinct from Employment
Act S.19 7-day rule (which applies to regular employees under contracts of
service).

Key rules:
  - 7-day clock starts from service_completion_date (delivery confirmation
    by the platform).
  - Failure to pay within 7 days constitutes a criminal offence under
    the Gig Workers Act 2025.
  - Alert is raised 1 day before the deadline lapses.
  - Overdue payments appear in a compliance violation log.
  - Dashboard groups pending payments by days remaining.
  - Compliance report exportable for MOHR inspection.
"""

import frappe
from frappe.utils import getdate, nowdate, add_days, date_diff


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum days allowed for payment after service completion
PAYMENT_DEADLINE_DAYS = 7

#: Days before deadline to raise the pre-deadline alert
ALERT_DAYS_BEFORE_DEADLINE = 1

#: Employment type for gig/platform workers
GIG_WORKER_EMPLOYMENT_TYPE = "Gig / Platform Worker"

#: Transaction statuses eligible for payment tracking
TRACKABLE_STATUSES = frozenset({"Completed"})

#: Violation severity levels
SEVERITY_OVERDUE = "Overdue"
SEVERITY_CRITICAL = "Critical"    # day-of or 1 day before
SEVERITY_WARNING = "Warning"      # 2-3 days remaining
SEVERITY_ON_TRACK = "On Track"    # 4+ days remaining

#: Dashboard grouping bucket boundaries (days remaining)
BUCKET_OVERDUE = "overdue"
BUCKET_DUE_TODAY = "due_today"
BUCKET_DUE_TOMORROW = "due_tomorrow"
BUCKET_DUE_2_3 = "due_2_3_days"
BUCKET_ON_TRACK = "on_track"


# ---------------------------------------------------------------------------
# Core deadline computation
# ---------------------------------------------------------------------------

def compute_payment_deadline(service_completion_date) -> str:
    """Compute the payment deadline from a service completion date.

    Args:
        service_completion_date: Date the gig service was completed.

    Returns:
        ISO date string of the payment deadline (completion + 7 days).
    """
    completion_dt = getdate(service_completion_date)
    deadline = add_days(completion_dt, PAYMENT_DEADLINE_DAYS)
    return str(deadline)


def get_days_remaining(service_completion_date, as_of_date=None) -> int:
    """Calculate days remaining until the 7-day payment deadline.

    Args:
        service_completion_date: Date the gig service was completed.
        as_of_date: Reference date; defaults to today.

    Returns:
        Integer days remaining.  Negative values mean overdue.
    """
    check_date = getdate(as_of_date or nowdate())
    deadline = getdate(compute_payment_deadline(service_completion_date))
    return date_diff(deadline, check_date)


def is_payment_overdue(service_completion_date, as_of_date=None) -> bool:
    """Check if a gig payment has exceeded the 7-day deadline.

    Args:
        service_completion_date: Date the gig service was completed.
        as_of_date: Reference date; defaults to today.

    Returns:
        True if payment is overdue (past deadline).
    """
    return get_days_remaining(service_completion_date, as_of_date) < 0


def classify_urgency(service_completion_date, as_of_date=None) -> str:
    """Classify the urgency/severity of a pending gig payment.

    Args:
        service_completion_date: Date the gig service was completed.
        as_of_date: Reference date; defaults to today.

    Returns:
        One of SEVERITY_OVERDUE, SEVERITY_CRITICAL, SEVERITY_WARNING,
        SEVERITY_ON_TRACK.
    """
    remaining = get_days_remaining(service_completion_date, as_of_date)

    if remaining < 0:
        return SEVERITY_OVERDUE
    if remaining <= ALERT_DAYS_BEFORE_DEADLINE:
        return SEVERITY_CRITICAL
    if remaining <= 3:
        return SEVERITY_WARNING
    return SEVERITY_ON_TRACK


# ---------------------------------------------------------------------------
# Transaction-level tracking
# ---------------------------------------------------------------------------

def has_payment_schedule(transaction: dict) -> bool:
    """Determine whether a gig transaction has a formal payment schedule.

    A transaction is considered to have a payment schedule if its
    ``payment_schedule`` field is truthy (non-empty string, non-None).

    Args:
        transaction: Dict representing the gig transaction record.

    Returns:
        True if a formal payment schedule exists.
    """
    schedule = transaction.get("payment_schedule")
    return bool(schedule and str(schedule).strip())


def needs_deadline_tracking(transaction: dict) -> bool:
    """Check if a gig transaction needs 7-day payment deadline tracking.

    Tracking is required when:
    1. Transaction status is 'Completed'
    2. No formal payment schedule is specified
    3. Payment has not yet been made (no remittance_date)

    Args:
        transaction: Dict with keys status, payment_schedule, remittance_date.

    Returns:
        True if the transaction needs deadline tracking.
    """
    status = transaction.get("status", "")
    if status not in TRACKABLE_STATUSES:
        return False

    if has_payment_schedule(transaction):
        return False

    remittance_date = transaction.get("remittance_date")
    if remittance_date:
        return False

    return True


def evaluate_transaction(transaction: dict, as_of_date=None) -> dict:
    """Evaluate a single gig transaction for payment deadline compliance.

    Args:
        transaction: Dict with keys: name, employee, service_completion_date,
            status, payment_schedule, remittance_date.
        as_of_date: Reference date; defaults to today.

    Returns:
        dict with keys:
            ``needs_tracking`` — whether this transaction requires tracking
            ``deadline``       — payment deadline date string (or None)
            ``days_remaining`` — days until deadline (or None)
            ``urgency``        — severity classification (or None)
            ``is_overdue``     — True if past deadline (or None)
            ``is_paid``        — True if remittance_date is present
    """
    is_paid = bool(transaction.get("remittance_date"))

    if not needs_deadline_tracking(transaction):
        return {
            "needs_tracking": False,
            "deadline": None,
            "days_remaining": None,
            "urgency": None,
            "is_overdue": None,
            "is_paid": is_paid,
        }

    completion_date = transaction.get("service_completion_date")
    if not completion_date:
        return {
            "needs_tracking": True,
            "deadline": None,
            "days_remaining": None,
            "urgency": None,
            "is_overdue": None,
            "is_paid": False,
        }

    deadline = compute_payment_deadline(completion_date)
    remaining = get_days_remaining(completion_date, as_of_date)
    urgency = classify_urgency(completion_date, as_of_date)
    overdue = remaining < 0

    return {
        "needs_tracking": True,
        "deadline": deadline,
        "days_remaining": remaining,
        "urgency": urgency,
        "is_overdue": overdue,
        "is_paid": False,
    }


# ---------------------------------------------------------------------------
# Payment completion
# ---------------------------------------------------------------------------

def record_payment_completion(transaction: dict, remittance_date, as_of_date=None) -> dict:
    """Record a payment completion against a service completion date.

    Args:
        transaction: Dict with service_completion_date.
        remittance_date: Date the payment was actually remitted.
        as_of_date: Not used directly; included for API consistency.

    Returns:
        dict with keys:
            ``service_completion_date`` — original completion date
            ``remittance_date``         — actual payment date
            ``deadline``                — the 7-day deadline
            ``days_to_pay``             — days between completion and payment
            ``within_deadline``         — True if paid on time
            ``days_overdue``            — days past deadline (0 if on time)
    """
    completion_date = transaction.get("service_completion_date")
    if not completion_date:
        return {
            "service_completion_date": None,
            "remittance_date": str(getdate(remittance_date)),
            "deadline": None,
            "days_to_pay": None,
            "within_deadline": False,
            "days_overdue": None,
        }

    completion_dt = getdate(completion_date)
    remittance_dt = getdate(remittance_date)
    deadline = compute_payment_deadline(completion_date)
    deadline_dt = getdate(deadline)

    days_to_pay = date_diff(remittance_dt, completion_dt)
    within_deadline = remittance_dt <= deadline_dt
    days_overdue = max(0, date_diff(remittance_dt, deadline_dt))

    return {
        "service_completion_date": str(completion_dt),
        "remittance_date": str(remittance_dt),
        "deadline": deadline,
        "days_to_pay": days_to_pay,
        "within_deadline": within_deadline,
        "days_overdue": days_overdue,
    }


# ---------------------------------------------------------------------------
# Alert generation
# ---------------------------------------------------------------------------

def should_alert(service_completion_date, as_of_date=None) -> bool:
    """Check if an alert should be raised for a gig payment.

    Alert is raised when days remaining <= ALERT_DAYS_BEFORE_DEADLINE (1 day)
    or when overdue.

    Args:
        service_completion_date: Date the gig service was completed.
        as_of_date: Reference date; defaults to today.

    Returns:
        True if an alert should be raised.
    """
    remaining = get_days_remaining(service_completion_date, as_of_date)
    return remaining <= ALERT_DAYS_BEFORE_DEADLINE


def get_transactions_needing_alerts(transactions: list, as_of_date=None) -> list:
    """Filter transactions that need payment deadline alerts.

    Returns only unpaid transactions without a payment schedule where
    an alert should be raised (1 day before deadline or overdue).

    Args:
        transactions: List of transaction dicts.
        as_of_date: Reference date; defaults to today.

    Returns:
        List of evaluated transaction dicts that need alerts.
    """
    alerts = []
    for txn in transactions:
        if not needs_deadline_tracking(txn):
            continue

        completion_date = txn.get("service_completion_date")
        if not completion_date:
            continue

        if should_alert(completion_date, as_of_date):
            evaluation = evaluate_transaction(txn, as_of_date)
            evaluation["transaction"] = txn.get("name", "")
            evaluation["employee"] = txn.get("employee", "")
            evaluation["employee_name"] = txn.get("employee_name", "")
            alerts.append(evaluation)

    return alerts


# ---------------------------------------------------------------------------
# Compliance violation log
# ---------------------------------------------------------------------------

def get_overdue_transactions(transactions: list, as_of_date=None) -> list:
    """Get all overdue gig payment transactions.

    Args:
        transactions: List of transaction dicts.
        as_of_date: Reference date; defaults to today.

    Returns:
        List of evaluated transaction dicts that are overdue.
    """
    overdue = []
    for txn in transactions:
        if not needs_deadline_tracking(txn):
            continue

        completion_date = txn.get("service_completion_date")
        if not completion_date:
            continue

        if is_payment_overdue(completion_date, as_of_date):
            evaluation = evaluate_transaction(txn, as_of_date)
            evaluation["transaction"] = txn.get("name", "")
            evaluation["employee"] = txn.get("employee", "")
            evaluation["employee_name"] = txn.get("employee_name", "")
            overdue.append(evaluation)

    return overdue


# ---------------------------------------------------------------------------
# Dashboard grouping
# ---------------------------------------------------------------------------

def group_by_days_remaining(transactions: list, as_of_date=None) -> dict:
    """Group pending gig worker payments by days remaining until deadline.

    Args:
        transactions: List of transaction dicts.
        as_of_date: Reference date; defaults to today.

    Returns:
        dict with keys: overdue, due_today, due_tomorrow, due_2_3_days,
        on_track.  Each is a list of evaluated transaction dicts.
    """
    buckets = {
        BUCKET_OVERDUE: [],
        BUCKET_DUE_TODAY: [],
        BUCKET_DUE_TOMORROW: [],
        BUCKET_DUE_2_3: [],
        BUCKET_ON_TRACK: [],
    }

    for txn in transactions:
        if not needs_deadline_tracking(txn):
            continue

        completion_date = txn.get("service_completion_date")
        if not completion_date:
            continue

        remaining = get_days_remaining(completion_date, as_of_date)
        evaluation = evaluate_transaction(txn, as_of_date)
        evaluation["transaction"] = txn.get("name", "")
        evaluation["employee"] = txn.get("employee", "")

        if remaining < 0:
            buckets[BUCKET_OVERDUE].append(evaluation)
        elif remaining == 0:
            buckets[BUCKET_DUE_TODAY].append(evaluation)
        elif remaining == 1:
            buckets[BUCKET_DUE_TOMORROW].append(evaluation)
        elif remaining <= 3:
            buckets[BUCKET_DUE_2_3].append(evaluation)
        else:
            buckets[BUCKET_ON_TRACK].append(evaluation)

    return buckets


def get_dashboard_summary(transactions: list, as_of_date=None) -> dict:
    """Get dashboard summary with counts per bucket.

    Args:
        transactions: List of transaction dicts.
        as_of_date: Reference date; defaults to today.

    Returns:
        dict with count per bucket and total_tracked.
    """
    grouped = group_by_days_remaining(transactions, as_of_date)
    summary = {}
    total = 0
    for bucket, items in grouped.items():
        summary[bucket] = len(items)
        total += len(items)
    summary["total_tracked"] = total
    return summary


# ---------------------------------------------------------------------------
# Compliance report (MOHR export)
# ---------------------------------------------------------------------------

def generate_compliance_report(transactions: list, as_of_date=None) -> dict:
    """Generate a compliance report for MOHR inspection.

    Shows all gig payment timelines including on-time payments,
    overdue records, and currently tracked transactions.

    Args:
        transactions: List of all transaction dicts (paid and unpaid).
        as_of_date: Reference date; defaults to today.

    Returns:
        dict with keys:
            ``total_transactions``   — total number of gig transactions
            ``paid_on_time``         — count paid within 7 days
            ``paid_late``            — count paid after deadline
            ``unpaid_within_deadline``— unpaid but still within 7 days
            ``unpaid_overdue``       — unpaid and past deadline
            ``records``              — list of per-transaction detail dicts
    """
    check_date = getdate(as_of_date or nowdate())

    report = {
        "total_transactions": 0,
        "paid_on_time": 0,
        "paid_late": 0,
        "unpaid_within_deadline": 0,
        "unpaid_overdue": 0,
        "records": [],
    }

    for txn in transactions:
        completion_date = txn.get("service_completion_date")
        if not completion_date:
            continue

        status = txn.get("status", "")
        if status not in TRACKABLE_STATUSES:
            continue

        # Skip transactions with payment schedules — not subject to 7-day rule
        if has_payment_schedule(txn):
            continue

        report["total_transactions"] += 1

        deadline = compute_payment_deadline(completion_date)
        deadline_dt = getdate(deadline)
        remittance_date = txn.get("remittance_date")

        record = {
            "transaction": txn.get("name", ""),
            "employee": txn.get("employee", ""),
            "employee_name": txn.get("employee_name", ""),
            "service_completion_date": str(getdate(completion_date)),
            "deadline": deadline,
            "remittance_date": None,
            "status": "",
            "days_to_pay": None,
            "days_overdue": 0,
        }

        if remittance_date:
            remittance_dt = getdate(remittance_date)
            record["remittance_date"] = str(remittance_dt)
            record["days_to_pay"] = date_diff(remittance_dt, getdate(completion_date))

            if remittance_dt <= deadline_dt:
                record["status"] = "Paid On Time"
                report["paid_on_time"] += 1
            else:
                record["status"] = "Paid Late"
                record["days_overdue"] = date_diff(remittance_dt, deadline_dt)
                report["paid_late"] += 1
        else:
            remaining = date_diff(deadline_dt, check_date)
            if remaining < 0:
                record["status"] = "Unpaid Overdue"
                record["days_overdue"] = abs(remaining)
                report["unpaid_overdue"] += 1
            else:
                record["status"] = "Unpaid Within Deadline"
                report["unpaid_within_deadline"] += 1

        report["records"].append(record)

    return report
