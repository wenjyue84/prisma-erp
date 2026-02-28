"""Employment compliance utilities for Malaysian labour law requirements.

Covers:
- Minimum Wages Order (Amendment) 2025 — effective 1 Feb 2025
  RM1,700/month for companies with 5+ employees
  RM8.17/hour for part-time workers
- Ordinary Rate of Pay (ORP) and Overtime Validation — Employment Act S.60A(3)
  OT multipliers: 1.5x Normal, 2.0x Rest Day, 3.0x Public Holiday
  Applies to EA-covered employees earning <= RM4,000/month
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
