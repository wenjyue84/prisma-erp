

# ---------------------------------------------------------------------------
# Public Holiday Work Pay — Employment Act 1955 Section 60D (US-119)
# ---------------------------------------------------------------------------
# EA 1955 S.60D: Working on public holiday entitlements:
#   - Employee entitled to 11 gazetted paid public holidays per year
#   - When required to work on PH: ordinary day wage + 2 additional days' wages (triple pay)
#   - The base day pay is already in regular salary; premium = 2x ORP daily
#   - OT beyond normal hours on PH: 3x hourly rate (EA S.60A)
#   - Alternative: employer may grant Off-In-Lieu (OIL) replacement day instead of triple-pay
# EA 1955 S.60I: ORP for monthly-rated employees = monthly_salary / 26

PH_WORK_PREMIUM_MULTIPLIER = 2    # 2x ORP daily (additional premium; base already in salary)
PH_OT_MULTIPLIER = 3              # 3x hourly rate for OT hours on a public holiday
NORMAL_DAILY_HOURS = 8            # Standard working day hours (default)

# Malaysia Fixed-Date Federal Public Holidays (gazetted by MOHR, applied nationwide)
# Format: (month, day) tuples — year-agnostic for recurring fixed-date holidays
# Note: Lunar-calendar holidays (Hari Raya, CNY, Deepavali, Wesak Day, etc.) vary by year
#       and require a year-specific gazette lookup.
MALAYSIA_FIXED_PUBLIC_HOLIDAYS = frozenset([
    (1, 1),    # New Year's Day
    (5, 1),    # Workers' Day / Labour Day
    (8, 31),   # Merdeka Day / National Day
    (9, 16),   # Malaysia Day
    (12, 25),  # Christmas Day
])


def calculate_public_holiday_work_premium(monthly_salary, normal_daily_hours=8):
    """Calculate the additional premium for working on a Malaysian public holiday (EA S.60D).

    Under Employment Act 1955 S.60D, when an EA-covered employee (salary <= RM4,000)
    is required to work on a gazetted public holiday, the employer must pay:
      - The normal day's wage (already included in regular monthly salary)
      - PLUS two additional days' wages as a premium

    This function computes the ADDITIONAL premium only (2x ORP daily).
    The base day pay is already included in the employee's regular monthly salary.

    ORP daily = monthly_salary / 26 (Employment Act S.60I)
    Premium   = ORP daily * 2

    Args:
        monthly_salary: Monthly salary in RM.
        normal_daily_hours: Normal working hours per day (default 8, unused in premium calc
            but kept for API consistency with the OT function).

    Returns:
        dict with keys:
            'premium':    float — additional premium payable (2x ORP daily)
            'orp_daily':  float — ORP per day (monthly / 26)
            'multiplier': int   — premium multiplier (always 2)
            'ea_covered': bool  — True if salary <= RM4,000
    """
    try:
        salary = float(monthly_salary)
    except (TypeError, ValueError):
        salary = 0.0

    orp_daily = salary / 26.0
    premium = orp_daily * PH_WORK_PREMIUM_MULTIPLIER
    ea_covered = salary <= ORP_SALARY_THRESHOLD

    return {
        "premium": premium,
        "orp_daily": orp_daily,
        "multiplier": PH_WORK_PREMIUM_MULTIPLIER,
        "ea_covered": ea_covered,
    }


def calculate_public_holiday_ot_pay(monthly_salary, ot_hours, normal_daily_hours=8):
    """Calculate overtime pay for hours worked beyond normal hours on a public holiday.

    Under Employment Act 1955 S.60A(3), OT on a public holiday is paid at 3x hourly rate.

    ORP daily  = monthly_salary / 26                           (EA S.60I)
    ORP hourly = ORP daily / normal_daily_hours
    OT pay     = ORP hourly * 3 * ot_hours

    Example: RM3,000/month, 8h normal day, 2h OT on PH:
      ORP daily  = 3000 / 26 = RM115.38
      ORP hourly = 115.38 / 8 = RM14.42
      OT pay     = 14.42 * 3 * 2 = RM86.54

    Args:
        monthly_salary: Monthly salary in RM.
        ot_hours: Overtime hours worked beyond normal daily hours.
        normal_daily_hours: Normal working hours per day (default 8).

    Returns:
        dict with keys:
            'ot_pay':     float — OT pay for PH overtime
            'orp_hourly': float — ORP per hour
            'multiplier': int   — OT multiplier (always 3)
            'ot_hours':   float — OT hours claimed
            'ea_covered': bool  — True if salary <= RM4,000
    """
    try:
        salary = float(monthly_salary)
        hours = float(ot_hours) if ot_hours else 0.0
        daily_hours = float(normal_daily_hours) if normal_daily_hours else 8.0
    except (TypeError, ValueError):
        salary, hours, daily_hours = 0.0, 0.0, 8.0

    orp_daily = salary / 26.0
    orp_hourly = orp_daily / daily_hours if daily_hours > 0 else 0.0
    ot_pay = orp_hourly * PH_OT_MULTIPLIER * hours
    ea_covered = salary <= ORP_SALARY_THRESHOLD

    return {
        "ot_pay": ot_pay,
        "orp_hourly": orp_hourly,
        "multiplier": PH_OT_MULTIPLIER,
        "ot_hours": hours,
        "ea_covered": ea_covered,
    }


def check_ea_coverage_for_public_holiday(monthly_salary):
    """Check EA coverage for public holiday pay purposes (Employment Act S.60D).

    EA 1955 covers employees with monthly wages not exceeding RM4,000 for
    public holiday, overtime and rest day purposes (post-2022 amendment).

    Employees above RM4,000/month are not covered by EA public holiday pay provisions;
    their entitlements are governed by their employment contract.

    Args:
        monthly_salary: Monthly salary in RM.

    Returns:
        dict with keys:
            'covered':  bool  — True if EA applies
            'reminder': str or None — message for above-threshold employees
            'salary':   float
    """
    try:
        salary = float(monthly_salary)
    except (TypeError, ValueError):
        salary = 0.0

    if salary <= ORP_SALARY_THRESHOLD:
        return {"covered": True, "reminder": None, "salary": salary}

    return {
        "covered": False,
        "reminder": (
            f"Employee monthly salary RM{salary:.2f} exceeds the EA coverage threshold "
            f"of RM{ORP_SALARY_THRESHOLD:.0f}/month. Public holiday pay terms are governed "
            "by the employment contract, not Employment Act Section 60D."
        ),
        "salary": salary,
    }


def get_public_holiday_oil_balance(employee_name):
    """Retrieve the Off-In-Lieu (OIL) balance for public holiday work.

    The balance is stored in the custom field `custom_ph_oil_balance` on the Employee record.
    HR credits OIL days when an employee elects replacement leave instead of triple-pay.

    Args:
        employee_name: Frappe Employee document name.

    Returns:
        float: Number of OIL days available (0.0 if not set or employee not found).
    """
    try:
        emp = frappe.get_doc("Employee", employee_name)
        return float(emp.get("custom_ph_oil_balance") or 0.0)
    except Exception:
        return 0.0


def add_public_holiday_oil_credit(employee_name, days=1):
    """Add Off-In-Lieu (OIL) credit to an employee for a public holiday worked.

    Increments the `custom_ph_oil_balance` field on the Employee record.
    HR uses this when converting a public holiday worked into an OIL day instead of triple-pay.
    The OIL day must be taken within 30 days of the public holiday per EA S.60D.

    Args:
        employee_name: Frappe Employee document name.
        days: Number of OIL days to credit (default 1).

    Returns:
        dict with keys:
            'success':       bool
            'new_balance':   float — updated OIL balance
            'days_credited': float
    """
    try:
        emp = frappe.get_doc("Employee", employee_name)
        current = float(emp.get("custom_ph_oil_balance") or 0.0)
        new_balance = current + float(days)
        emp.custom_ph_oil_balance = new_balance
        emp.save(ignore_permissions=True)
        return {"success": True, "new_balance": new_balance, "days_credited": float(days)}
    except Exception:
        return {"success": False, "new_balance": 0.0, "days_credited": 0.0}


def is_malaysia_public_holiday(date_value, state=None):
    """Check if a given date is a gazetted Malaysia public holiday.

    Checks against the fixed annual federal public holidays only (New Year's Day,
    Workers' Day, Merdeka Day, Malaysia Day, Christmas Day). Lunar-calendar holidays
    (Hari Raya Aidilfitri, CNY, Deepavali, Wesak Day, etc.) are not included as they
    vary by year and require a year-specific gazette lookup.

    Args:
        date_value: Date string 'YYYY-MM-DD' or Python date object.
        state: Optional state code (reserved for state-specific holiday lookup;
               not implemented in this version).

    Returns:
        dict with keys:
            'is_public_holiday': bool
            'date':              str — date string 'YYYY-MM-DD'
            'note':              str — explains partial coverage
    """
    from frappe.utils import getdate

    try:
        d = getdate(date_value)
        month_day = (d.month, d.day)
        is_ph = month_day in MALAYSIA_FIXED_PUBLIC_HOLIDAYS
        return {
            "is_public_holiday": is_ph,
            "date": str(d),
            "note": (
                "Fixed-date federal holidays only. Lunar holidays (Hari Raya, CNY, etc.) "
                "require a year-specific gazette lookup."
            ),
        }
    except Exception:
        return {
            "is_public_holiday": False,
            "date": str(date_value),
            "note": "Invalid date provided.",
        }
