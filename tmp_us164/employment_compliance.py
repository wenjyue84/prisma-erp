"""Employment compliance utilities for Malaysian labour law requirements.

Covers:
- Minimum Wages Order (Amendment) 2025 — effective 1 Feb 2025
  RM1,700/month for companies with 5+ employees
  RM8.17/hour for part-time workers
- Micro-Employer Minimum Wage Grace Period (US-144)
  Aug 2025 gazette extension: micro-employers (1-4 employees) exempted until 2025-08-01
- Apprenticeship Contract Minimum Wage Extension (US-164)
  NWCC Amendment Act 2025 (effective 1 Aug 2025): apprentices and contract trainees now
  subject to RM1,700 minimum wage. Domestic workers remain the sole exempt category.
- Ordinary Rate of Pay (ORP) and Overtime Validation — Employment Act S.60A(3)
  OT multipliers: 1.5x Normal, 2.0x Rest Day, 3.0x Public Holiday
  Applies to EA-covered employees earning <= RM4,000/month
- Part-Time Employee ORP Proration — EA Third Schedule (US-102)
  ORP = agreed_monthly_wage / (contracted_hours_per_week * 52 / 12)
  OT cap: 104 hours/month; multipliers: 1.5x Normal, 2.0x Public Holiday
- Maternity/Paternity Leave Validation — Employment Act S.37 & S.60FA (US-080)
  Maternity leave: 98 consecutive days; allowance must be >= ORP * days
  Paternity leave: 7 consecutive days; max 5 live births per career
- Working Hours Compliance — Employment Act 1955 Section 60A(1) post-2022 amendment (US-081)
  Maximum 45 hours per week; OT from Salary Detail where custom_day_type is set
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

# Working Hours Compliance — Employment Act 1955 Section 60A(1) post-2022 amendment
MAX_WEEKLY_HOURS = 45  # Maximum hours per week (reduced from 48 by EA Amendment 2022)
WEEKS_PER_MONTH = 4.33  # Average weeks per calendar month

# US-164: Apprenticeship Contract Minimum Wage Extension (NWCC Amendment Act 2025)
# Effective 1 August 2025 — apprentices and contract trainees now subject to RM1,700/month.
# Domestic workers remain the SOLE exempt category per NWCC Act 2011.
APPRENTICE_ENFORCEMENT_DATE = "2025-08-01"
APPRENTICE_TYPES = {"Apprentice", "Contract Trainee"}
DOMESTIC_WORKER_TYPES = {"Domestic Worker", "Domestic", "Domestic Help"}


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


# ---------------------------------------------------------------------------
# Maternity / Paternity Leave — Employment Act 1955 S.37 & S.60FA (US-080)
# ---------------------------------------------------------------------------

# Employment Act 1955 Section 37 (A1651 amendment)
MATERNITY_LEAVE_DAYS = 98       # Maximum consecutive maternity leave days per confinement
# Employment Act 1955 Section 60FA
PATERNITY_LEAVE_DAYS = 7        # Maximum consecutive paternity leave days per birth
MAX_PATERNITY_BIRTHS = 5        # Maximum births for which paternity leave may be claimed


def validate_maternity_pay(salary_slip):
    """Validate maternity allowance on a Salary Slip against Employment Act S.37.

    Checks:
    1. Days taken do not exceed 98 per confinement.
    2. Total maternity component >= ORP_daily * days_taken.

    Args:
        salary_slip: Frappe document or mock with fields:
            - employee       (str) — linked Employee name
            - base           (float) — gross basic salary for ORP calculation
            - earnings       (list of dicts) — salary components
        The linked Employee doc is expected to have:
            - custom_maternity_leave_taken (int) — days taken this confinement

    Returns:
        dict with keys:
            'compliant':    bool
            'warnings':     list[str] — human-readable warnings (empty if compliant)
            'days_taken':   int or None
            'orp_daily':    float or None
            'minimum_pay':  float or None
            'maternity_pay': float or None
    """
    warnings = []

    # --- Retrieve days taken from Employee ---
    try:
        employee_name = salary_slip.employee
        emp = frappe.get_doc("Employee", employee_name)
        days_taken = int(emp.get("custom_maternity_leave_taken") or 0)
    except Exception:
        days_taken = 0

    # --- Calculate ORP ---
    try:
        basic = float(salary_slip.base or 0)
    except (TypeError, ValueError):
        basic = 0.0
    orp_daily = calculate_orp(basic)["daily"]

    # --- Sum maternity components from earnings ---
    maternity_pay = 0.0
    try:
        earnings = salary_slip.earnings or []
        for row in earnings:
            component = (
                row.get("salary_component") if isinstance(row, dict)
                else getattr(row, "salary_component", "")
            ) or ""
            if "maternit" in component.lower():
                try:
                    amount = float(
                        row.get("amount") if isinstance(row, dict)
                        else getattr(row, "amount", 0)
                    )
                    maternity_pay += amount
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass

    # --- Validations ---
    if days_taken > MATERNITY_LEAVE_DAYS:
        warnings.append(
            f"Maternity leave taken ({days_taken} days) exceeds the statutory maximum "
            f"of {MATERNITY_LEAVE_DAYS} consecutive days per confinement "
            f"(Employment Act 1955 Section 37)."
        )

    if days_taken > 0 and orp_daily > 0:
        minimum_pay = orp_daily * days_taken
        if maternity_pay < minimum_pay:
            warnings.append(
                f"Maternity allowance (RM{maternity_pay:.2f}) is below the statutory minimum "
                f"of RM{minimum_pay:.2f} (ORP RM{orp_daily:.2f}/day x {days_taken} days). "
                f"Underpayment of maternity allowance is an offence under Employment Act S.37."
            )
    else:
        minimum_pay = None

    return {
        "compliant": len(warnings) == 0,
        "warnings": warnings,
        "days_taken": days_taken,
        "orp_daily": orp_daily,
        "minimum_pay": minimum_pay if days_taken > 0 and orp_daily > 0 else None,
        "maternity_pay": maternity_pay,
    }


def validate_paternity_claims(employee_doc):
    """Validate paternity leave claims against Employment Act S.60FA.

    Checks:
    1. Paternity births claimed do not exceed 5.
    2. Days taken per claim do not exceed 7.

    Args:
        employee_doc: Frappe Employee document or mock with:
            - custom_paternity_births_claimed (int)
            - custom_paternity_leave_taken    (int) — days taken for current claim

    Returns:
        dict with keys:
            'compliant': bool
            'warnings':  list[str]
            'births_claimed': int
            'days_taken':    int
    """
    warnings = []

    births_claimed = int(employee_doc.get("custom_paternity_births_claimed") or 0)
    days_taken = int(employee_doc.get("custom_paternity_leave_taken") or 0)

    if births_claimed > MAX_PATERNITY_BIRTHS:
        warnings.append(
            f"Paternity leave births claimed ({births_claimed}) exceeds the statutory "
            f"maximum of {MAX_PATERNITY_BIRTHS} live births "
            f"(Employment Act 1955 Section 60FA)."
        )

    if days_taken > PATERNITY_LEAVE_DAYS:
        warnings.append(
            f"Paternity leave days taken ({days_taken}) exceeds the statutory maximum "
            f"of {PATERNITY_LEAVE_DAYS} consecutive days per birth "
            f"(Employment Act 1955 Section 60FA)."
        )

    return {
        "compliant": len(warnings) == 0,
        "warnings": warnings,
        "births_claimed": births_claimed,
        "days_taken": days_taken,
    }

# ---------------------------------------------------------------------------
# Termination and Lay-Off Benefits — Employment (Termination and Lay-Off Benefits)
# Regulations 1980 (US-082)
# ---------------------------------------------------------------------------

# Termination rate lookup: {service_years_ceiling: days_per_year}
# < 2 years  → 10 days/year
# 2-5 years  → 15 days/year
# > 5 years  → 20 days/year
TERMINATION_RATE = {2: 10, 5: 15, 999: 20}


def calculate_termination_benefits(employee, termination_date):
    """Calculate statutory minimum termination pay per Regulations 1980.

    Employment (Termination and Lay-Off Benefits) Regulations 1980:
      - < 2 years of service  → 10 days wages per year
      - 2–5 years of service  → 15 days wages per year
      - > 5 years of service  → 20 days wages per year

    daily_rate = (employee.ctc or employee.salary_currency) / (12 * 26)
    statutory_minimum = daily_rate * rate_days * years_of_service

    Args:
        employee: Frappe Employee document or mock with:
            - date_of_joining (date/str): hire date
            - ctc (float): cost to company / annual salary (used to derive daily rate)
        termination_date (date/str): effective termination date

    Returns:
        dict with keys:
            'years_of_service':          float — fractional years of service
            'rate_days':                 int — days per year (10/15/20)
            'daily_rate':                float — monthly_salary / 26
            'statutory_minimum':         float — minimum termination pay in RM
            'monthly_salary':            float — derived monthly CTC
    """
    from frappe.utils import getdate

    _zero = {
        "years_of_service": 0.0,
        "rate_days": 0,
        "daily_rate": 0.0,
        "statutory_minimum": 0.0,
        "monthly_salary": 0.0,
    }

    # --- Date inputs ---
    try:
        joining_date = getdate(employee.date_of_joining)
        term_date = getdate(termination_date)
    except Exception:
        return _zero

    if not joining_date or not term_date or term_date <= joining_date:
        return _zero

    # --- Years of service ---
    days_of_service = (term_date - joining_date).days
    years_of_service = days_of_service / 365.0

    # --- Determine rate bracket ---
    rate_days = 20  # default > 5 years
    for ceiling in sorted(TERMINATION_RATE.keys()):
        if years_of_service < ceiling:
            rate_days = TERMINATION_RATE[ceiling]
            break

    # --- Monthly salary from CTC ---
    try:
        ctc = float(employee.ctc or 0)
    except (TypeError, ValueError):
        ctc = 0.0
    monthly_salary = ctc / 12.0

    # --- Daily rate: monthly / 26 (Employment Act S.60I) ---
    daily_rate = monthly_salary / 26.0

    # --- Statutory minimum ---
    statutory_minimum = daily_rate * rate_days * years_of_service

    return {
        "years_of_service": years_of_service,
        "rate_days": rate_days,
        "daily_rate": daily_rate,
        "statutory_minimum": statutory_minimum,
        "monthly_salary": monthly_salary,
    }


# ---------------------------------------------------------------------------
# Working Hours Compliance — Employment Act 1955 Section 60A(1) (US-081)
# Post-2022 amendment: maximum 45 hours per week (reduced from 48)
# ---------------------------------------------------------------------------

def validate_weekly_hours(salary_slip):
    """Validate that implied average weekly hours do not exceed the statutory limit.

    Employment Act 1955 Section 60A(1) (as amended 2022): maximum 45 working
    hours per week. Excessive overtime may cause total implied weekly hours to
    breach this limit, which is an Employment Act offence.

    Calculation:
        contracted_monthly_hours = contracted_weekly_hours * WEEKS_PER_MONTH
        ot_hours_monthly         = sum of qty from earnings where custom_day_type is set
        total_monthly_hours      = contracted_monthly_hours + ot_hours_monthly
        implied_weekly_hours     = total_monthly_hours / WEEKS_PER_MONTH
                                 = contracted_weekly_hours + (ot_hours_monthly / WEEKS_PER_MONTH)

    Args:
        salary_slip: Frappe Salary Slip document or mock with:
            - employee (str): Employee ID to fetch custom_contracted_weekly_hours
            - earnings (list): Salary Detail rows with 'custom_day_type' and 'qty' attributes

    Returns:
        dict with keys:
            'compliant':             bool — True if implied_weekly_hours <= MAX_WEEKLY_HOURS
            'warning':               str or None — human-readable warning if non-compliant
            'implied_weekly_hours':  float — calculated average weekly hours
            'max_weekly_hours':      int — statutory maximum (45)
            'contracted_weekly_hours': float — hours from Employee or default 45
            'ot_hours_monthly':      float — total OT hours summed from earnings
    """
    # --- Get contracted weekly hours from Employee (default MAX_WEEKLY_HOURS) ---
    contracted_weekly_hours = MAX_WEEKLY_HOURS  # fallback default
    try:
        employee_name = getattr(salary_slip, "employee", None)
        if employee_name:
            emp_doc = frappe.get_doc("Employee", employee_name)
            raw = getattr(emp_doc, "custom_contracted_weekly_hours", None)
            if raw is not None:
                contracted_weekly_hours = float(raw or MAX_WEEKLY_HOURS)
    except Exception:
        pass  # use default if employee not found or field missing

    # --- Sum OT hours from earnings where custom_day_type is set ---
    ot_hours_monthly = 0.0
    earnings = getattr(salary_slip, "earnings", None) or []
    for row in earnings:
        day_type = getattr(row, "custom_day_type", None)
        if day_type:  # any non-empty value indicates an OT/overtime row
            try:
                ot_hours_monthly += float(getattr(row, "qty", 0) or 0)
            except (TypeError, ValueError):
                pass

    # --- Implied average weekly hours ---
    implied_weekly_hours = contracted_weekly_hours + (ot_hours_monthly / WEEKS_PER_MONTH)

    # --- Compliance check ---
    if implied_weekly_hours > MAX_WEEKLY_HOURS:
        warning = (
            f"Implied average weekly hours ({implied_weekly_hours:.2f}h) exceeds the statutory "
            f"maximum of {MAX_WEEKLY_HOURS} hours per week under Employment Act 1955 "
            f"Section 60A(1) (as amended 2022). Excessive overtime is an Employment Act offence."
        )
        return {
            "compliant": False,
            "warning": warning,
            "implied_weekly_hours": implied_weekly_hours,
            "max_weekly_hours": MAX_WEEKLY_HOURS,
            "contracted_weekly_hours": contracted_weekly_hours,
            "ot_hours_monthly": ot_hours_monthly,
        }

    return {
        "compliant": True,
        "warning": None,
        "implied_weekly_hours": implied_weekly_hours,
        "max_weekly_hours": MAX_WEEKLY_HOURS,
        "contracted_weekly_hours": contracted_weekly_hours,
        "ot_hours_monthly": ot_hours_monthly,
    }


# ---------------------------------------------------------------------------
# Public Holiday Work Pay — Employment Act 1955 Section 60D (US-119)
# ---------------------------------------------------------------------------
# Section 60D: EA-covered employees entitled to 11 paid PH per year.
# Working on PH: employer must pay ordinary daily wage PLUS 2 additional
# days' wages (i.e., the base daily pay is already in regular salary, so the
# additional premium = 2 x ORP daily).
# Section 60A: OT beyond normal working hours on PH = 3x hourly rate.
# Section 60I: ORP daily = monthly_salary / 26 for monthly-rated employees.
# EA coverage: employees earning <= RM4,000/month (post-2022 amendment).
# ---------------------------------------------------------------------------

# Number of gazetted public holidays EA employees are entitled to per year
EA_PUBLIC_HOLIDAYS_PER_YEAR = 11

# PH work additional premium multiplier (base day already covered by salary)
PH_WORK_ADDITIONAL_MULTIPLIER = 2.0   # 2x ORP per day = total 3x including regular day pay

# OT on PH: beyond normal working hours at 3x hourly rate
PH_OT_HOURLY_MULTIPLIER = 3.0


def calculate_ph_work_premium(monthly_salary, normal_daily_hours=8):
    """Calculate the additional pay premium for working on a Public Holiday.

    Employment Act 1955 Section 60D: when an EA-covered employee works on a
    public holiday, the employer must pay the ordinary daily wage plus TWO
    additional days' wages.  Since the base daily pay is already embedded in
    the regular monthly salary, the *additional* premium due is:

        premium = 2 x ORP_daily   (where ORP_daily = monthly_salary / 26)

    Overtime beyond normal working hours is handled separately by
    ``calculate_ph_overtime()``.

    Args:
        monthly_salary: Basic monthly salary in RM.
        normal_daily_hours: Normal daily working hours (default 8). Used only
            for documentation / context; the premium is per-day, not per-hour.

    Returns:
        dict with keys:
            'premium':        float -- additional premium in RM (2 x ORP daily)
            'orp_daily':      float -- ORP per day (monthly_salary / 26)
            'multiplier':     float -- always 2.0 (the additional multiplier)
            'ea_covered':     bool  -- True if salary <= RM4,000 (EA applies)
            'warning':        str or None -- advisory if employee is not EA-covered
    """
    try:
        salary = float(monthly_salary)
    except (TypeError, ValueError):
        salary = 0.0

    orp_daily = salary / 26.0
    premium = PH_WORK_ADDITIONAL_MULTIPLIER * orp_daily
    ea_covered = salary <= ORP_SALARY_THRESHOLD

    warning = None
    if not ea_covered:
        warning = (
            f"Employee monthly salary RM{salary:.2f} exceeds the EA coverage threshold of "
            f"RM{ORP_SALARY_THRESHOLD:.0f}/month. Public holiday work pay for this employee "
            f"is governed by the employment contract, not Section 60D of the Employment Act."
        )

    return {
        "premium": premium,
        "orp_daily": orp_daily,
        "multiplier": PH_WORK_ADDITIONAL_MULTIPLIER,
        "ea_covered": ea_covered,
        "warning": warning,
    }


def calculate_ph_overtime(monthly_salary, ot_hours, normal_daily_hours=8):
    """Calculate overtime pay for hours worked beyond normal hours on a Public Holiday.

    Employment Act 1955 Section 60A: overtime performed on a public holiday
    is compensated at THREE times the hourly ORP:

        OT_pay = 3 x ORP_hourly x ot_hours
        ORP_hourly = ORP_daily / normal_daily_hours = monthly_salary / 26 / normal_daily_hours

    Args:
        monthly_salary: Basic monthly salary in RM.
        ot_hours: Number of overtime hours worked beyond normal daily hours on the PH.
        normal_daily_hours: Normal daily working hours (default 8) for deriving hourly ORP.

    Returns:
        dict with keys:
            'ot_pay':           float -- overtime pay in RM
            'orp_hourly':       float -- hourly ORP (monthly_salary / 26 / normal_daily_hours)
            'multiplier':       float -- always 3.0
            'ot_hours':         float -- OT hours input
            'ea_covered':       bool  -- True if salary <= RM4,000
            'warning':          str or None -- advisory if not EA-covered
    """
    try:
        salary = float(monthly_salary)
        hours = float(ot_hours) if ot_hours is not None else 0.0
        daily_hours = float(normal_daily_hours) if normal_daily_hours else 8.0
    except (TypeError, ValueError):
        return {
            "ot_pay": 0.0,
            "orp_hourly": 0.0,
            "multiplier": PH_OT_HOURLY_MULTIPLIER,
            "ot_hours": 0.0,
            "ea_covered": False,
            "warning": None,
        }

    orp_daily = salary / 26.0
    orp_hourly = orp_daily / daily_hours if daily_hours > 0 else 0.0
    ot_pay = PH_OT_HOURLY_MULTIPLIER * orp_hourly * hours
    ea_covered = salary <= ORP_SALARY_THRESHOLD

    warning = None
    if not ea_covered:
        warning = (
            f"Employee monthly salary RM{salary:.2f} exceeds the EA coverage threshold of "
            f"RM{ORP_SALARY_THRESHOLD:.0f}/month. Public holiday OT pay is governed by the "
            f"employment contract, not Section 60A of the Employment Act."
        )

    return {
        "ot_pay": ot_pay,
        "orp_hourly": orp_hourly,
        "multiplier": PH_OT_HOURLY_MULTIPLIER,
        "ot_hours": hours,
        "ea_covered": ea_covered,
        "warning": warning,
    }


def add_ph_oil_credit(employee_name, days=1.0):
    """Add Off-In-Lieu (OIL) credit to an employee's PH OIL balance.

    When HR chooses to offer an Off-In-Lieu replacement day instead of
    triple pay, call this function to increment the employee's OIL counter.

    Args:
        employee_name: Frappe Employee document name.
        days: Number of OIL days to credit (default 1.0).

    Returns:
        dict with keys:
            'employee':    str -- employee name
            'days_added':  float -- days credited
            'new_balance': float -- updated OIL balance
            'success':     bool
            'error':       str or None
    """
    try:
        emp = frappe.get_doc("Employee", employee_name)
        current = float(getattr(emp, "custom_ph_oil_balance", 0) or 0)
        new_balance = current + float(days)
        emp.custom_ph_oil_balance = new_balance
        emp.save(ignore_permissions=True)
        return {
            "employee": employee_name,
            "days_added": float(days),
            "new_balance": new_balance,
            "success": True,
            "error": None,
        }
    except Exception as e:
        return {
            "employee": employee_name,
            "days_added": float(days),
            "new_balance": None,
            "success": False,
            "error": str(e),
        }


def flag_payroll_public_holiday_dates(payroll_dates, malaysia_public_holidays):
    """Flag which payroll dates fall on Malaysia public holidays.

    Used to alert payroll officers that employees who worked on those dates
    may be entitled to public holiday work pay under Section 60D.

    Args:
        payroll_dates: list of date strings ('YYYY-MM-DD') or date objects.
        malaysia_public_holidays: list of date strings or date objects (gazette PH list).

    Returns:
        dict with keys:
            'flagged_dates': list[str] -- dates in payroll_dates that are public holidays
            'count':         int -- number of flagged dates
    """
    from frappe.utils import getdate

    ph_set = set()
    for d in malaysia_public_holidays:
        try:
            ph_set.add(str(getdate(d)))
        except Exception:
            pass

    flagged = []
    for d in payroll_dates:
        try:
            if str(getdate(d)) in ph_set:
                flagged.append(str(getdate(d)))
        except Exception:
            pass

    return {"flagged_dates": flagged, "count": len(flagged)}


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


# ---------------------------------------------------------------------------
# US-144: Micro-Employer Minimum Wage Schedule (August 2025 Grace Period Extension)
# ---------------------------------------------------------------------------

# Minimum Wage Schedule per Minimum Wages Order 2022 + August 2025 Gazette Extension
# headcount_threshold: minimum active-employee count for this entry to apply.
# None = applies to ALL employers regardless of headcount.
MINIMUM_WAGE_SCHEDULE = [
    {
        "effective_date": "2025-02-01",
        "min_wage": 1700.0,
        "headcount_threshold": 5,   # employers with >= 5 active employees
    },
    {
        "effective_date": "2025-08-01",
        "min_wage": 1700.0,
        "headcount_threshold": None,  # all employers (micro-employers included)
    },
]


def get_applicable_minimum_wage(period_end_date, employer_headcount):
    """Return the minimum monthly wage applicable for a payroll period and employer size.

    Per Minimum Wages Order 2022 and August 2025 gazette extension:
    - 2025-02-01 onwards: RM1,700 for employers with >= 5 active employees.
    - 2025-08-01 onwards: RM1,700 for ALL employers (micro-employers included).

    Args:
        period_end_date: str ('YYYY-MM-DD') or datetime.date — payroll period end.
        employer_headcount: int — number of active employees on the Company.

    Returns:
        float or None:
            float — the applicable minimum monthly wage in RM.
            None  — no minimum wage applies (grace period for this employer size).
    """
    from datetime import date

    if isinstance(period_end_date, str):
        try:
            period_end_date = date.fromisoformat(period_end_date)
        except (ValueError, TypeError):
            return None

    applicable_wage = None
    for entry in sorted(MINIMUM_WAGE_SCHEDULE, key=lambda e: e["effective_date"]):
        eff_date = date.fromisoformat(entry["effective_date"])
        if period_end_date < eff_date:
            continue  # Not yet effective
        threshold = entry["headcount_threshold"]
        if threshold is None or int(employer_headcount) >= threshold:
            applicable_wage = entry["min_wage"]
        # If headcount below threshold, this entry doesn't apply; later entries may override.
    return applicable_wage


def check_minimum_wage_with_headcount(
    monthly_salary,
    period_end_date,
    employer_headcount,
    employment_type=None,
    contracted_hours=None,
    mohr_exemption_ref=None,
):
    """Check minimum wage compliance including micro-employer grace period (US-144).

    Extends check_minimum_wage() with employer-headcount-sensitive schedule logic.
    Micro-employers (1-4 employees) are exempt from RM1,700 until 2025-08-01.

    Args:
        monthly_salary: Basic monthly salary in RM.
        period_end_date: Payroll period end date (str 'YYYY-MM-DD' or datetime.date).
        employer_headcount: Number of active employees on the Company.
        employment_type: 'Full-time', 'Part-time', 'Contract', 'Apprentice',
            'Contract Trainee', or 'Domestic Worker'. Apprentices/Contract Trainees
            are checked from 2025-08-01 only. Domestic Workers are always exempt.
        contracted_hours: Total contracted hours per month (for part-time hourly check).
        mohr_exemption_ref: MOHR exemption reference — if set, validation is skipped.

    Returns:
        dict with keys:
            'compliant':        bool
            'warning':          str or None
            'employment_type':  str
            'minimum':          float or None (applicable minimum; None if grace period)
            'actual':           float
            'grace_period':     bool (True if micro-employer grace period applies)
            'mohr_exempt':      bool (True if MOHR exemption reference bypassed check)
    """
    employment_type = employment_type or "Full-time"

    # MOHR exemption overrides all validation
    if mohr_exemption_ref and str(mohr_exemption_ref).strip():
        return {
            "compliant": True,
            "warning": None,
            "employment_type": employment_type,
            "minimum": None,
            "actual": float(monthly_salary),
            "grace_period": False,
            "mohr_exempt": True,
        }

    # US-164: Domestic workers are the sole exempt category — skip all validation
    if employment_type in DOMESTIC_WORKER_TYPES:
        return {
            "compliant": True,
            "warning": None,
            "employment_type": employment_type,
            "minimum": None,
            "actual": float(monthly_salary),
            "grace_period": False,
            "mohr_exempt": False,
        }

    # US-164: Apprentice / Contract Trainee — enforced from 2025-08-01 only
    # Before Aug 2025 they were not covered; no false positives for historical payrolls.
    if employment_type in APPRENTICE_TYPES:
        from datetime import date as _date
        if isinstance(period_end_date, str):
            try:
                ped = _date.fromisoformat(period_end_date)
            except (ValueError, TypeError):
                ped = None
        else:
            ped = period_end_date

        apprentice_enforcement = _date.fromisoformat(APPRENTICE_ENFORCEMENT_DATE)
        if ped is None or ped < apprentice_enforcement:
            # Before enforcement date — no validation for apprentices
            return {
                "compliant": True,
                "warning": None,
                "employment_type": employment_type,
                "minimum": None,
                "actual": float(monthly_salary),
                "grace_period": True,
                "mohr_exempt": False,
            }

        # From Aug 2025 — RM1,700 applies regardless of employer headcount
        basic_pay = float(monthly_salary)
        if basic_pay < MINIMUM_WAGE_MONTHLY:
            return {
                "compliant": False,
                "warning": (
                    f"Apprentice/Contract Trainee monthly salary RM{basic_pay:.2f} is below "
                    f"the national minimum wage of RM{MINIMUM_WAGE_MONTHLY:.2f}/month. "
                    "The NWCC Amendment Act 2025 (effective 1 August 2025) extended minimum "
                    "wage coverage to apprenticeship contract workers. Non-compliance carries "
                    "a fine of up to RM10,000 per affected worker."
                ),
                "employment_type": employment_type,
                "minimum": MINIMUM_WAGE_MONTHLY,
                "actual": basic_pay,
                "grace_period": False,
                "mohr_exempt": False,
            }
        return {
            "compliant": True,
            "warning": None,
            "employment_type": employment_type,
            "minimum": MINIMUM_WAGE_MONTHLY,
            "actual": basic_pay,
            "grace_period": False,
            "mohr_exempt": False,
        }

    applicable_minimum = get_applicable_minimum_wage(period_end_date, employer_headcount)

    # Grace period: no minimum wage enforcement for this employer size + period
    if applicable_minimum is None:
        return {
            "compliant": True,
            "warning": None,
            "employment_type": employment_type,
            "minimum": None,
            "actual": float(monthly_salary),
            "grace_period": True,
            "mohr_exempt": False,
        }

    # Part-time: compare hourly rate
    if employment_type == "Part-time" and contracted_hours:
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
                        f"Part-time hourly rate RM{hourly_rate:.2f} is below the minimum "
                        f"wage of RM{MINIMUM_WAGE_HOURLY}/hour (Minimum Wages Order 2022)."
                    ),
                    "employment_type": employment_type,
                    "minimum": MINIMUM_WAGE_HOURLY,
                    "actual": hourly_rate,
                    "grace_period": False,
                    "mohr_exempt": False,
                }
            return {
                "compliant": True,
                "warning": None,
                "employment_type": employment_type,
                "minimum": MINIMUM_WAGE_HOURLY,
                "actual": hourly_rate,
                "grace_period": False,
                "mohr_exempt": False,
            }

    # Full-time / Contract: compare monthly salary
    basic_pay = float(monthly_salary)
    if basic_pay < applicable_minimum:
        return {
            "compliant": False,
            "warning": (
                f"Monthly salary RM{basic_pay:.2f} is below the national minimum wage "
                f"of RM{applicable_minimum:.2f}/month (Minimum Wages Order 2024 - universal "
                f"enforcement from 1 August 2025). Non-compliance carries a fine of up to "
                "RM10,000 per employee per offence (National Wages Consultative Council "
                "Act 2011)."
            ),
            "employment_type": employment_type,
            "minimum": applicable_minimum,
            "actual": basic_pay,
            "grace_period": False,
            "mohr_exempt": False,
        }

    return {
        "compliant": True,
        "warning": None,
        "employment_type": employment_type,
        "minimum": applicable_minimum,
        "actual": basic_pay,
        "grace_period": False,
        "mohr_exempt": False,
    }


def get_min_wage_migration_alert_employees(company=None):
    """Return recently submitted salary slips in the RM1,500-RM1,699.99 range.

    These represent employees who will be in violation of the universal RM1,700
    minimum wage effective 1 August 2025 (Minimum Wages Order 2024). Use this
    to generate a one-time migration alert for HR before the August 2025 cutover.

    Args:
        company: Optional company name to filter by.

    Returns:
        list of dict: Salary slip records with 'employee', 'employee_name',
            'gross_pay', 'company' fields.
    """
    filters = {
        "docstatus": 1,
        "gross_pay": ["between", [1500, 1699.99]],
    }
    if company:
        filters["company"] = company

    return frappe.get_all(
        "Salary Slip",
        filters=filters,
        fields=["employee", "employee_name", "gross_pay", "company"],
    )
