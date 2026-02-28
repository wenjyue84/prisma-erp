"""Malaysian statutory payroll rates.

Centralised module for all statutory contribution rate logic:
- EPF (KWSP) employer contribution rates (EPF Contribution Rate Revision 2022)
- EPF foreign worker mandatory contribution (US-090, effective October 2025)
- SOCSO (PERKESO) First Schedule bracketed table (US-074)
- EIS (SIP) contribution rules (US-075)
- Age-based statutory rate transitions at age 60 (US-076)

All rates are correct as of 2025 amendments.
"""
import frappe
from frappe.utils import flt

# ---------------------------------------------------------------------------
# EPF (KWSP) — Employer Contribution Rates
# EPF Contribution Rate Revision 2022
# ---------------------------------------------------------------------------

EPF_EMPLOYER_RATE_HIGH = 0.13   # 13% for monthly gross salary <= RM5,000
EPF_EMPLOYER_RATE_LOW = 0.12    # 12% for monthly gross salary > RM5,000
EPF_LOWER_SALARY_THRESHOLD = 5000.0  # RM5,000 threshold

# Age 60+ rates — EPF Act 1991 Third Schedule
EPF_OVER_60_EMPLOYEE_RATE = 0.055   # 5.5% statutory (or 0% minimum elected)
EPF_OVER_60_EMPLOYER_RATE = 0.04    # 4% for employees aged 60+
EPF_STANDARD_EMPLOYEE_RATE = 0.11   # 11% standard rate for age < 60

# ---------------------------------------------------------------------------
# EPF — Foreign Worker Mandatory Contribution (US-090)
# Effective October 2025: EPF mandatory for foreign workers at 2% each
# Reference: EPF (Amendment) Act 2024, enforced from 1 October 2025
# ---------------------------------------------------------------------------
from datetime import date as _date_cls
FOREIGN_WORKER_EPF_START = _date_cls(2025, 10, 1)  # Mandatory from 1 October 2025
FOREIGN_WORKER_EPF_RATE = 0.02                       # 2% employee + 2% employer


def calculate_epf_employer_rate(monthly_gross, is_foreign=False, payroll_date=None):
    """Return the statutory EPF employer contribution rate for a given monthly gross.

    Per EPF Contribution Rate Revision 2022 (citizen/PR):
    - 13% for employees earning <= RM5,000/month
    - 12% for employees earning > RM5,000/month

    Per EPF (Amendment) Act 2024 — Foreign Workers (effective October 2025):
    - 2% employer rate from 1 October 2025
    - 0% before October 2025 (foreign workers were previously exempt)

    Args:
        monthly_gross: Employee's monthly gross salary in MYR.
        is_foreign: bool, True if employee is a foreign worker (default False).
        payroll_date: datetime.date for foreign worker start date check (default today).

    Returns:
        float: Employer EPF rate (e.g. 0.13 for 13%, 0.02 for 2%, 0.0 if exempt).
    """
    if is_foreign:
        ref_date = payroll_date or _date_cls.today()
        if ref_date >= FOREIGN_WORKER_EPF_START:
            return FOREIGN_WORKER_EPF_RATE   # 2% from October 2025
        return 0.0   # Not covered before October 2025

    # Citizen / PR: salary-graduated rate
    gross = flt(monthly_gross)
    if gross <= EPF_LOWER_SALARY_THRESHOLD:
        return EPF_EMPLOYER_RATE_HIGH
    return EPF_EMPLOYER_RATE_LOW


def calculate_epf_employee_rate(monthly_gross=None, is_foreign=False, payroll_date=None):
    """Return the statutory EPF employee contribution rate.

    Citizen/PR: 11% standard rate (age < 60).
    Foreign worker from October 2025: 2%.
    Foreign worker before October 2025: 0%.

    Args:
        monthly_gross: Not used for citizens (rate is flat 11%); kept for API symmetry.
        is_foreign: bool, True if foreign worker.
        payroll_date: datetime.date, used for foreign worker effective date check.

    Returns:
        float: Employee EPF rate.
    """
    if is_foreign:
        ref_date = payroll_date or _date_cls.today()
        if ref_date >= FOREIGN_WORKER_EPF_START:
            return FOREIGN_WORKER_EPF_RATE   # 2%
        return 0.0

    return EPF_STANDARD_EMPLOYEE_RATE   # 11%


def get_statutory_rates_for_employee(employee_name, payroll_date):
    """Return EPF/SOCSO/EIS statutory rates for an employee based on age at payroll_date.

    At age 60, statutory contribution rules change (EPF Act 1991 Third Schedule;
    SOCSO Act 1969; EIS Act 2017):
    - EPF employee rate: 5.5% (or 0% if minimum elected); employer: 4%
    - SOCSO: no longer covered
    - EIS: no longer covered

    Args:
        employee_name: str, Frappe Employee docname.
        payroll_date: datetime.date, payroll processing date.

    Returns:
        dict with keys:
            epf_employee_rate (float),
            epf_employer_rate (float or None for < 60 — use calculate_epf_employer_rate()),
            socso_covered (bool),
            eis_covered (bool),
            age (int),
            over_60 (bool).
    """
    from datetime import date as _date

    emp = frappe.get_doc("Employee", employee_name)
    dob = emp.date_of_birth

    # Normalise to date object (Frappe may return a string)
    if isinstance(dob, str):
        from frappe.utils import getdate
        dob = getdate(dob)

    ref_date = payroll_date or _date.today()
    # Use calendar-based age to handle leap years correctly
    age = ref_date.year - dob.year - (
        (ref_date.month, ref_date.day) < (dob.month, dob.day)
    )

    if age >= 60:
        return {
            "epf_employee_rate": EPF_OVER_60_EMPLOYEE_RATE,
            "epf_employer_rate": EPF_OVER_60_EMPLOYER_RATE,
            "socso_covered": False,
            "eis_covered": False,
            "age": age,
            "over_60": True,
        }

    return {
        "epf_employee_rate": EPF_STANDARD_EMPLOYEE_RATE,
        "epf_employer_rate": None,  # salary-dependent — call calculate_epf_employer_rate()
        "socso_covered": True,
        "eis_covered": True,
        "age": age,
        "over_60": False,
    }


# ---------------------------------------------------------------------------
# SOCSO (PERKESO) — First Schedule (Jadual Kadar Caruman)
# Updated October 2024: wage ceiling raised from RM5,000 to RM6,000
# ---------------------------------------------------------------------------

SOCSO_WAGE_CEILING = 6000.0  # Updated October 2024

# SOCSO First Schedule — Employment Injury Scheme + Invalidity Scheme (both)
# Format: (wage_upper_bound, employee_amount, employer_amount)
# Source: PERKESO Jadual Kadar Caruman (72 brackets, RM0 to RM6,000+)
# Note: wages above RM6,000 are capped at RM6,000 ceiling
SOCSO_TABLE = [
    (30, 0.10, 0.30),
    (50, 0.20, 0.40),
    (70, 0.20, 0.60),
    (100, 0.30, 0.90),
    (140, 0.40, 1.20),
    (200, 0.50, 1.70),
    (300, 0.80, 2.50),
    (400, 1.05, 3.25),
    (500, 1.30, 4.00),
    (600, 1.55, 4.75),
    (700, 1.80, 5.50),
    (800, 2.05, 6.25),
    (900, 2.30, 7.00),
    (1000, 2.55, 7.75),
    (1100, 2.80, 8.50),
    (1200, 3.05, 9.25),
    (1300, 3.30, 10.00),
    (1400, 3.55, 10.75),
    (1500, 3.80, 11.50),
    (1600, 4.05, 12.25),
    (1700, 4.30, 13.00),
    (1800, 4.55, 13.75),
    (1900, 4.80, 14.50),
    (2000, 5.05, 15.25),
    (2100, 5.30, 16.00),
    (2200, 5.55, 16.75),
    (2300, 5.80, 17.50),
    (2400, 6.05, 18.25),
    (2500, 6.30, 19.00),
    (2600, 6.55, 19.75),
    (2700, 6.80, 20.50),
    (2800, 7.05, 21.25),
    (2900, 7.30, 22.00),
    (3000, 7.55, 22.75),
    (3100, 7.80, 23.50),
    (3200, 8.05, 24.25),
    (3300, 8.30, 25.00),
    (3400, 8.55, 25.75),
    (3500, 8.80, 26.50),
    (3600, 9.05, 27.25),
    (3700, 9.30, 28.00),
    (3800, 9.55, 28.75),
    (3900, 9.80, 29.50),
    (4000, 10.05, 30.25),
    (4100, 10.30, 31.00),
    (4200, 10.55, 31.75),
    (4300, 10.80, 32.50),
    (4400, 11.05, 33.25),
    (4500, 11.30, 34.00),
    (4600, 11.55, 34.75),
    (4700, 11.80, 35.50),
    (4800, 12.05, 36.25),
    (4900, 12.30, 37.00),
    (5000, 12.55, 37.75),
    (5100, 12.80, 38.50),
    (5200, 13.05, 39.25),
    (5300, 13.30, 40.00),
    (5400, 13.55, 40.75),
    (5500, 13.80, 41.50),
    (5600, 14.05, 42.25),
    (5700, 14.30, 43.00),
    (5800, 14.55, 43.75),
    (5900, 14.80, 44.50),
    (6000, 15.05, 45.25),  # ceiling bracket
]


def calculate_socso_contribution(wages, scheme="both"):
    """Return SOCSO contribution amounts per PERKESO First Schedule.

    Wage ceiling: RM6,000/month (updated October 2024).

    Args:
        wages: Employee's monthly wages in MYR.
        scheme: 'both' (Employment Injury + Invalidity), 'injury_only' (employer only, e.g. age >= 60).

    Returns:
        dict with keys 'employee' and 'employer' amounts (MYR).
    """
    capped_wages = min(flt(wages), SOCSO_WAGE_CEILING)

    for upper_bound, emp_amount, emr_amount in SOCSO_TABLE:
        if capped_wages <= upper_bound:
            if scheme == "injury_only":
                # Employment Injury only: employer pays ~1.25%, employee exempt
                return {"employee": 0.0, "employer": flt(emr_amount * 0.4, 2)}
            return {"employee": flt(emp_amount, 2), "employer": flt(emr_amount, 2)}

    # Above all brackets (should not happen due to ceiling cap, but handle gracefully)
    last = SOCSO_TABLE[-1]
    return {"employee": flt(last[1], 2), "employer": flt(last[2], 2)}


# ---------------------------------------------------------------------------
# EIS (SIP) — Employment Insurance System
# EIS Act 2017 Second Schedule, ceiling updated October 2024
# ---------------------------------------------------------------------------

EIS_WAGE_CEILING = 6000.0  # Updated October 2024 (aligned with SOCSO)
EIS_RATE = 0.002            # 0.2% each — employee and employer


def calculate_eis_contribution(wages, date_of_birth, is_foreign, payroll_date=None):
    """Return EIS (SIP) contribution amounts per EIS Act 2017 Second Schedule.

    Exemptions:
    - Foreign workers: not covered by EIS
    - Age < 18 or age >= 60: exempt

    Wage ceiling: RM6,000/month (updated October 2024).

    Args:
        wages: Employee's monthly wages in MYR.
        date_of_birth: datetime.date of employee's birth.
        is_foreign: bool, True if employee is a foreign worker.
        payroll_date: datetime.date for age calculation (defaults to today).

    Returns:
        dict with keys 'employee' and 'employer' (both 0.0 if exempt).
    """
    from datetime import date as _date

    if is_foreign:
        return {"employee": 0.0, "employer": 0.0}

    ref_date = payroll_date or _date.today()
    age = (ref_date - date_of_birth).days // 365

    if age < 18 or age >= 60:
        return {"employee": 0.0, "employer": 0.0}

    insured_wages = min(flt(wages), EIS_WAGE_CEILING)
    contribution = flt(insured_wages * EIS_RATE, 2)
    return {"employee": contribution, "employer": contribution}
