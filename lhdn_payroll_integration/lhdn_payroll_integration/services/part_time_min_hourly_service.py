"""US-184: Enforce Part-Time Employee Minimum Hourly Rate Against RM1,700 Monthly Wage Floor.

Minimum Wages Order 2022 (P.U.(A) 268/2022): RM1,700/month effective 1 February 2023.
Part-time proration: RM1,700 ÷ 26 working days ÷ 8 hours = RM8.17/hour minimum.

Applies to ALL employers from August 2025 (micro-employer extension).

NWCC Act exemptions:
  - Apprentices under the National Apprenticeship Act
  - Disabled workers under specific MOHR disabled worker schemes
  - Contract trainees (where specified under MOHR gazette)
"""

from lhdn_payroll_integration.utils.employment_compliance import (
    MINIMUM_WAGE_MONTHLY,
)

# Part-time hourly rate proration constants
PART_TIME_WORKING_DAYS_PER_MONTH = 26      # LHDN/MOHR standard working days
PART_TIME_HOURS_PER_DAY = 8               # Standard working hours per day
PART_TIME_WORKING_HOURS_PER_MONTH = PART_TIME_WORKING_DAYS_PER_MONTH * PART_TIME_HOURS_PER_DAY  # = 208

# NWCC Act exemption categories that suppress the compliance block
EXEMPT_CATEGORIES = {
    "apprentice",       # National Apprenticeship Act
    "disabled_worker",  # MOHR Disabled Worker Scheme
    "trainee",          # Contract trainee under MOHR gazette
}


def compute_minimum_hourly_rate(monthly_minimum=None):
    """Compute the statutory minimum hourly rate from the monthly minimum wage floor.

    Formula: monthly_minimum / (WORKING_DAYS * HOURS_PER_DAY)
             = RM1,700 / 208 = RM8.17/hour

    Args:
        monthly_minimum (float|None): Override monthly minimum wage.
            If None, uses MINIMUM_WAGE_MONTHLY from employment_compliance.

    Returns:
        dict:
            minimum_hourly (float): Computed minimum hourly rate.
            monthly_minimum (float): Monthly minimum used.
            working_hours_per_month (int): Hours divisor used (208).
    """
    base = monthly_minimum if monthly_minimum is not None else MINIMUM_WAGE_MONTHLY
    minimum_hourly = round(base / PART_TIME_WORKING_HOURS_PER_MONTH, 2)
    return {
        "minimum_hourly": minimum_hourly,
        "monthly_minimum": base,
        "working_hours_per_month": PART_TIME_WORKING_HOURS_PER_MONTH,
    }


def validate_part_time_hourly_rate(hourly_rate, exemption_category=None, monthly_minimum=None):
    """Validate a part-time employee's configured hourly rate against the statutory minimum.

    Args:
        hourly_rate (float): The employee's agreed/configured hourly pay rate.
        exemption_category (str|None): If set to a recognised NWCC Act exemption
            ('apprentice', 'disabled_worker', 'trainee'), compliance block is suppressed.
        monthly_minimum (float|None): Override monthly minimum wage for auto-adjustment
            when minimum wage changes. Defaults to MINIMUM_WAGE_MONTHLY.

    Returns:
        dict:
            compliant (bool): True if rate >= minimum_hourly (or exempt).
            blocked (bool): True if payroll should be blocked (non-compliant and not exempt).
            exempt (bool): True if an exemption is active.
            exemption_category (str|None): The exemption in effect.
            hourly_rate (float): Actual configured rate.
            minimum_hourly (float): Statutory minimum hourly rate.
            shortfall (float|None): Amount below minimum; None if compliant.
            warning (str|None): Human-readable compliance message; None if compliant.
    """
    rate_info = compute_minimum_hourly_rate(monthly_minimum)
    minimum_hourly = rate_info["minimum_hourly"]

    is_exempt = (
        exemption_category is not None
        and exemption_category.lower() in EXEMPT_CATEGORIES
    )
    compliant = hourly_rate >= minimum_hourly

    if compliant or is_exempt:
        return {
            "compliant": compliant,
            "blocked": False,
            "exempt": is_exempt,
            "exemption_category": exemption_category,
            "hourly_rate": hourly_rate,
            "minimum_hourly": minimum_hourly,
            "shortfall": None if compliant else round(minimum_hourly - hourly_rate, 4),
            "warning": None,
        }

    shortfall = round(minimum_hourly - hourly_rate, 4)
    warning = (
        f"Part-time employee hourly rate RM{hourly_rate:.2f}/hour is below the "
        f"statutory minimum of RM{minimum_hourly:.2f}/hour "
        f"(RM{rate_info['monthly_minimum']:.2f}/month ÷ "
        f"{rate_info['working_hours_per_month']} hours, "
        f"Minimum Wages Order 2022). Shortfall: RM{shortfall:.4f}/hour. "
        f"Record an exemption reason on the Employee record to suppress this block."
    )

    return {
        "compliant": False,
        "blocked": True,
        "exempt": False,
        "exemption_category": exemption_category,
        "hourly_rate": hourly_rate,
        "minimum_hourly": minimum_hourly,
        "shortfall": shortfall,
        "warning": warning,
    }


def generate_part_time_compliance_report(employees, monthly_minimum=None):
    """Generate a compliance report for a list of part-time employees.

    Args:
        employees (list[dict]): Each entry must have:
            - name (str): Employee ID / name.
            - hourly_rate (float): Configured hourly rate.
            - exemption_category (str|None): Exemption type, if any.
            Optional:
            - department (str): Department for grouping.
            - company (str): Entity for grouping.
        monthly_minimum (float|None): Override monthly minimum wage.

    Returns:
        dict:
            minimum_hourly (float): Minimum hourly rate used.
            monthly_minimum (float): Monthly minimum used.
            total_employees (int): Total part-time employees checked.
            compliant_count (int): Count passing the check.
            non_compliant_count (int): Count failing (not exempt).
            exempt_count (int): Count with active exemptions.
            rows (list[dict]): Per-employee result with pass/fail status.
    """
    rate_info = compute_minimum_hourly_rate(monthly_minimum)
    minimum_hourly = rate_info["minimum_hourly"]

    rows = []
    compliant_count = 0
    non_compliant_count = 0
    exempt_count = 0

    for emp in employees:
        result = validate_part_time_hourly_rate(
            hourly_rate=emp.get("hourly_rate", 0.0),
            exemption_category=emp.get("exemption_category"),
            monthly_minimum=monthly_minimum,
        )

        status = "PASS" if result["compliant"] else ("EXEMPT" if result["exempt"] else "FAIL")
        if result["compliant"]:
            compliant_count += 1
        elif result["exempt"]:
            exempt_count += 1
        else:
            non_compliant_count += 1

        rows.append({
            "employee": emp.get("name", ""),
            "department": emp.get("department", ""),
            "company": emp.get("company", ""),
            "hourly_rate": emp.get("hourly_rate", 0.0),
            "minimum_hourly": minimum_hourly,
            "status": status,
            "shortfall": result["shortfall"],
            "exemption_category": result["exemption_category"],
            "warning": result["warning"],
        })

    return {
        "minimum_hourly": minimum_hourly,
        "monthly_minimum": rate_info["monthly_minimum"],
        "total_employees": len(employees),
        "compliant_count": compliant_count,
        "non_compliant_count": non_compliant_count,
        "exempt_count": exempt_count,
        "rows": rows,
    }
