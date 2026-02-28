"""Employment compliance utilities for Malaysian labour law requirements.

Covers:
- Minimum Wages Order (Amendment) 2025 — effective 1 Feb 2025
  RM1,700/month for companies with 5+ employees
  RM8.17/hour for part-time workers
"""

import frappe

# Minimum Wages Order (Amendment) 2025
MINIMUM_WAGE_MONTHLY = 1700.0   # RM per month
MINIMUM_WAGE_HOURLY = 8.17      # RM per hour


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
