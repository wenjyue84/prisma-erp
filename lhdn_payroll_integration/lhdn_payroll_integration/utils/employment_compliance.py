"""Employment compliance utilities for Malaysian labour law requirements.

Covers:
- Minimum Wages Order (Amendment) 2025 — effective 1 Feb 2025
  RM1,700/month for companies with 5+ employees
  RM8.17/hour for part-time workers
- Ordinary Rate of Pay (ORP) and Overtime Validation — Employment Act S.60A(3)
  OT multipliers: 1.5x Normal, 2.0x Rest Day, 3.0x Public Holiday
  Applies to EA-covered employees earning <= RM4,000/month
- Part-Time Employee ORP Proration — EA Third Schedule (US-102)
  ORP = agreed_monthly_wage / (contracted_hours_per_week * 52 / 12)
  OT cap: 104 hours/month; multipliers: 1.5x Normal, 2.0x Public Holiday
"""

import frappe

# Minimum Wages Order (Amendment) 2025
MINIMUM_WAGE_MONTHLY = 1700.0   # RM per month
MINIMUM_WAGE_HOURLY = 8.17      # RM per hour

# Ordinary Rate of Pay — Employment Act 1955 Section 60A(3)
ORP_SALARY_THRESHOLD = 4000.0   # EA coverage ceiling (RM/month)
OT_MULTIPLIERS = {
    "Normal": 1.5,
    "Rest Day": 2.0,
    "Public Holiday": 3.0,
}

# Part-Time Employee ORP — EA Third Schedule (Regulation 5)
# Employment (Amendment) Act 2022: EA coverage extended to RM4,000/month
PART_TIME_OT_HOURS_CAP = 104  # Maximum OT hours per month for EA-covered part-time employees
PART_TIME_OT_MULTIPLIERS = {
    "Normal": 1.5,
    "Public Holiday": 2.0,
}
PART_TIME_DEFINITION_THRESHOLD = 0.70  # < 70% of normal full-time hours = part-time


def check_minimum_wage(monthly_salary, employment_type=None, worked_days=None, total_days=None, contracted_hours=None):
    """Check if salary meets minimum wage requirements.

    Args:
        monthly_salary: Basic monthly salary in RM.
        employment_type: 'Full-time', 'Part-time', or 'Contract'.
        worked_days: Number of days worked (used for proration, not checked yet).
        total_days: Total working days in period (used for proration, not checked yet).
        contracted_hours: Total contracted hours per month (for part-time hourly check).

    Returns:
        dict with keys:
            'compliant': bool
            'warning': str or None (human-readable warning message)
            'employment_type': str
            'minimum': float (the applicable minimum)
            'actual': float (the actual rate being compared)
    """
    employment_type = employment_type or "Full-time"

    if employment_type == "Part-time" and contracted_hours:
        # Part-time: compare hourly rate
        try:
            contracted_hours_float = float(contracted_hours)
        except (TypeError, ValueError):
            contracted_hours_float = 0.0

        if contracted_hours_float > 0:
            hourly_rate = float(monthly_salary) / contracted_hours_float
            if hourly_rate < MINIMUM_WAGE_HOURLY:
                return {
                    "compliant": False,
                    "warning": (
                        f"Part-time hourly rate RM{hourly_rate:.2f} is below the minimum wage "
                        f"of RM{MINIMUM_WAGE_HOURLY}/hour (Minimum Wages Order 2025)."
                    ),
                    "employment_type": employment_type,
                    "minimum": MINIMUM_WAGE_HOURLY,
                    "actual": hourly_rate,
                }
            return {
                "compliant": True,
                "warning": None,
                "employment_type": employment_type,
                "minimum": MINIMUM_WAGE_HOURLY,
                "actual": hourly_rate,
            }

    # Full-time or Contract: compare monthly salary
    basic_pay = float(monthly_salary)
    if basic_pay < MINIMUM_WAGE_MONTHLY:
        return {
            "compliant": False,
            "warning": (
                f"Monthly salary RM{basic_pay:.2f} is below the national minimum wage "
                f"of RM{MINIMUM_WAGE_MONTHLY:.2f}/month (Minimum Wages Order Amendment 2025, "
                "effective 1 Feb 2025). Non-compliance is an offence under Employment Act "
                "Section 99J (fine up to RM10,000 per contravention)."
            ),
            "employment_type": employment_type,
            "minimum": MINIMUM_WAGE_MONTHLY,
            "actual": basic_pay,
        }

    return {
        "compliant": True,
        "warning": None,
        "employment_type": employment_type,
        "minimum": MINIMUM_WAGE_MONTHLY,
        "actual": basic_pay,
    }


def calculate_orp(monthly_salary, contracted_hours_per_month=None):
    """Calculate Ordinary Rate of Pay (ORP) per Employment Act S.60A(3).

    ORP daily  = monthly_salary / 26
    ORP hourly = monthly_salary / contracted_hours_per_month (if provided)

    Args:
        monthly_salary: Basic monthly salary in RM.
        contracted_hours_per_month: Total contracted hours/month.
            If None or 0, hourly ORP is not computed.

    Returns:
        dict with keys:
            'daily':  float - ORP per day (monthly / 26)
            'hourly': float or None - ORP per hour (monthly / hours, or None)
    """
    try:
        salary = float(monthly_salary)
    except (TypeError, ValueError):
        salary = 0.0

    daily_orp = salary / 26.0

    hourly_orp = None
    if contracted_hours_per_month:
        try:
            hours = float(contracted_hours_per_month)
            if hours > 0:
                hourly_orp = salary / hours
        except (TypeError, ValueError):
            pass

    return {"daily": daily_orp, "hourly": hourly_orp}


def check_overtime_rate(
    monthly_salary,
    component_amount,
    ot_hours_claimed,
    day_type="Normal",
    contracted_hours_per_month=None,
):
    """Check if an OT component meets the statutory minimum rate (EA S.60A(3)).

    Only validates for EA-covered employees earning <= RM4,000/month.

    Args:
        monthly_salary: Basic monthly salary in RM.
        component_amount: The amount paid for the OT component in RM.
        ot_hours_claimed: Number of OT hours claimed.
        day_type: 'Normal', 'Rest Day', or 'Public Holiday'.
        contracted_hours_per_month: Total contracted hours/month (for hourly ORP).
            If None, falls back to daily ORP / 8 (8-hour day assumption).

    Returns:
        dict with keys:
            'compliant':      bool
            'warning':        str or None
            'multiplier':     float or None
            'orp_hourly':     float or None
            'minimum_amount': float or None
    """
    _no_check = {
        "compliant": True,
        "warning": None,
        "multiplier": None,
        "orp_hourly": None,
        "minimum_amount": None,
    }

    try:
        salary = float(monthly_salary)
        amount = float(component_amount)
        hours = float(ot_hours_claimed) if ot_hours_claimed else 0.0
    except (TypeError, ValueError):
        return _no_check

    # Only check EA-covered employees (monthly salary <= RM4,000)
    if salary > ORP_SALARY_THRESHOLD:
        return _no_check

    if hours <= 0:
        return _no_check

    multiplier = OT_MULTIPLIERS.get(day_type, OT_MULTIPLIERS["Normal"])
    orp = calculate_orp(salary, contracted_hours_per_month)
    orp_hourly = orp["hourly"]

    if orp_hourly is None:
        # Fallback: daily ORP / 8 (standard 8-hour working day)
        orp_hourly = orp["daily"] / 8.0

    minimum_amount = orp_hourly * hours * multiplier

    if amount < minimum_amount:
        return {
            "compliant": False,
            "warning": (
                f"OT component (RM{amount:.2f}) for {hours:.1f}h on {day_type} day is below the "
                f"statutory minimum of RM{minimum_amount:.2f} ({multiplier}x ORP of "
                f"RM{orp_hourly:.4f}/h). Employment Act S.60A(3) applies to employees "
                f"earning <=RM{ORP_SALARY_THRESHOLD:.0f}/month."
            ),
            "multiplier": multiplier,
            "orp_hourly": orp_hourly,
            "minimum_amount": minimum_amount,
        }

    return {
        "compliant": True,
        "warning": None,
        "multiplier": multiplier,
        "orp_hourly": orp_hourly,
        "minimum_amount": minimum_amount,
    }


# ---------------------------------------------------------------------------
# Part-Time Employee ORP — EA Third Schedule (US-102)
# ---------------------------------------------------------------------------


def calculate_part_time_orp(agreed_monthly_wage, contracted_hours_per_week):
    """Calculate ORP for part-time employee per EA Third Schedule Regulation 5(3).

    ORP hourly = agreed_monthly_wage / contracted_hours_per_month
    where contracted_hours_per_month = contracted_hours_per_week * 52 / 12

    Args:
        agreed_monthly_wage: Agreed monthly wage in RM.
        contracted_hours_per_week: Contracted hours per week.

    Returns:
        dict with keys:
            'hourly': float or None - ORP per hour
            'contracted_hours_per_month': float or None - calculated monthly hours
    """
    _none = {"hourly": None, "contracted_hours_per_month": None}

    try:
        wage = float(agreed_monthly_wage)
        hours_per_week = float(contracted_hours_per_week)
    except (TypeError, ValueError):
        return _none

    if hours_per_week <= 0:
        return _none

    contracted_hours_per_month = hours_per_week * 52 / 12
    hourly_orp = wage / contracted_hours_per_month

    return {
        "hourly": hourly_orp,
        "contracted_hours_per_month": contracted_hours_per_month,
    }


def check_part_time_ea_coverage(monthly_salary):
    """Check if a part-time employee is covered under Employment Act 1955.

    Employment (Amendment) Act 2022 extended EA coverage to employees earning
    up to RM4,000/month.

    Args:
        monthly_salary: Monthly salary equivalent in RM.

    Returns:
        bool: True if covered under EA (salary <= RM4,000)
    """
    try:
        salary = float(monthly_salary)
    except (TypeError, ValueError):
        return False

    return salary <= ORP_SALARY_THRESHOLD


def check_part_time_ot_hours_cap(claimed_hours_per_month):
    """Check if claimed OT hours exceed the 104-hour monthly cap for EA part-time employees.

    Employment Act Third Schedule limits OT to 104 hours per month for EA-covered
    part-time employees.

    Args:
        claimed_hours_per_month: Total OT hours claimed in the month.

    Returns:
        dict with keys:
            'compliant': bool
            'warning': str or None
            'cap': int - the applicable cap (104)
    """
    _cap = PART_TIME_OT_HOURS_CAP

    try:
        hours = float(claimed_hours_per_month)
    except (TypeError, ValueError):
        return {"compliant": True, "warning": None, "cap": _cap}

    if hours > _cap:
        return {
            "compliant": False,
            "warning": (
                f"OT hours claimed ({hours:.1f}h) exceed the statutory maximum of "
                f"{_cap} hours/month for EA-covered part-time employees "
                "(Employment Act Third Schedule)."
            ),
            "cap": _cap,
        }

    return {"compliant": True, "warning": None, "cap": _cap}


def check_part_time_ot_rate(
    monthly_salary,
    contracted_hours_per_week,
    component_amount,
    ot_hours_claimed,
    day_type="Normal",
):
    """Validate OT pay for a part-time employee under EA Third Schedule.

    Only validates for EA-covered part-time employees earning <= RM4,000/month.

    Args:
        monthly_salary: Agreed monthly wage in RM.
        contracted_hours_per_week: Contracted hours per week.
        component_amount: OT pay amount in RM.
        ot_hours_claimed: OT hours claimed.
        day_type: 'Normal' or 'Public Holiday'.

    Returns:
        dict with keys:
            'compliant':      bool
            'warning':        str or None
            'multiplier':     float or None
            'orp_hourly':     float or None
            'minimum_amount': float or None
    """
    _no_check = {
        "compliant": True,
        "warning": None,
        "multiplier": None,
        "orp_hourly": None,
        "minimum_amount": None,
    }

    try:
        salary = float(monthly_salary)
        amount = float(component_amount)
        hours = float(ot_hours_claimed) if ot_hours_claimed else 0.0
    except (TypeError, ValueError):
        return _no_check

    # Only check EA-covered part-time employees (monthly salary <= RM4,000)
    if not check_part_time_ea_coverage(salary):
        return _no_check

    if hours <= 0:
        return _no_check

    orp = calculate_part_time_orp(salary, contracted_hours_per_week)
    orp_hourly = orp["hourly"]

    if orp_hourly is None:
        # Cannot compute ORP without valid contracted hours — skip check
        return _no_check

    multiplier = PART_TIME_OT_MULTIPLIERS.get(day_type, PART_TIME_OT_MULTIPLIERS["Normal"])
    minimum_amount = orp_hourly * hours * multiplier

    if amount < minimum_amount:
        return {
            "compliant": False,
            "warning": (
                f"Part-time OT component (RM{amount:.2f}) for {hours:.1f}h on {day_type} day "
                f"is below the statutory minimum of RM{minimum_amount:.2f} "
                f"({multiplier}x ORP of RM{orp_hourly:.4f}/h). "
                f"Employment Act Third Schedule applies to part-time employees "
                f"earning <=RM{ORP_SALARY_THRESHOLD:.0f}/month."
            ),
            "multiplier": multiplier,
            "orp_hourly": orp_hourly,
            "minimum_amount": minimum_amount,
        }

    return {
        "compliant": True,
        "warning": None,
        "multiplier": multiplier,
        "orp_hourly": orp_hourly,
        "minimum_amount": minimum_amount,
    }
