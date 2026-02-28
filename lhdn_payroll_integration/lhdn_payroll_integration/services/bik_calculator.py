"""LHDN Benefits-in-Kind (BIK) Prescribed Value Calculator.

US-060: Implements LHDN Public Ruling No. 3/2013 (updated 2019) prescribed
annual values for common BIK items provided by employers.

BIK provided by employers is taxable employment income under ITA Section
13(1)(b). Omitting BIK understates chargeable income and PCB — LHDN audits
routinely identify this.

Prescribed annual BIK table (car, by purchase price):
    ≤ RM 50,000      → RM  1,200/year
    ≤ RM 75,000      → RM  2,400/year
    ≤ RM 100,000     → RM  3,600/year
    ≤ RM 150,000     → RM  5,000/year
    ≤ RM 200,000     → RM  7,500/year
    ≤ RM 250,000     → RM 10,000/year
    ≤ RM 350,000     → RM 15,000/year
    ≤ RM 500,000     → RM 20,000/year
    ≤ RM 750,000     → RM 25,000/year
    > RM 750,000     → RM 50,000/year

Prescribed monthly BIK:
    Fuel card:  RM 300/month
    Driver:     RM 600/month

Other BIK (accommodation, club, other) are entered as actual amounts.
"""
import frappe

# Car BIK lookup table: {upper_price_limit: annual_bik_amount}
# Key = maximum car purchase price (RM); Value = prescribed annual BIK (RM)
CAR_BIK_TABLE = {
    50_000:  1_200,
    75_000:  2_400,
    100_000: 3_600,
    150_000: 5_000,
    200_000: 7_500,
    250_000: 10_000,
    350_000: 15_000,
    500_000: 20_000,
    750_000: 25_000,
}
_CAR_BIK_MAX = 50_000  # Annual BIK for cars priced above RM750,000

# Prescribed monthly BIK constants
FUEL_BIK_MONTHLY = 300
DRIVER_BIK_MONTHLY = 600


def get_annual_car_bik(car_purchase_price: float) -> float:
    """Return LHDN prescribed annual BIK for a company car.

    Looks up the car purchase price against the CAR_BIK_TABLE brackets
    per LHDN Public Ruling No. 3/2013 (updated 2019).

    Args:
        car_purchase_price: Original purchase price of company car (RM).

    Returns:
        float: Prescribed annual BIK amount (RM).

    Example:
        >>> get_annual_car_bik(120_000)
        5000  # RM120,000 falls in ≤RM150,000 bracket → RM5,000/year
    """
    if car_purchase_price <= 0:
        return 0.0

    for upper_limit in sorted(CAR_BIK_TABLE.keys()):
        if car_purchase_price <= upper_limit:
            return float(CAR_BIK_TABLE[upper_limit])

    # Car price exceeds RM750,000 — maximum prescribed BIK
    return float(_CAR_BIK_MAX)


def calculate_monthly_bik_total(employee_name: str, year: int) -> float:
    """Return total monthly BIK amount for an employee for a given payroll year.

    Fetches the Employee BIK Record for the specified employee and year,
    then computes:
        monthly_bik = (car_bik_annual + club_membership_annual + other_bik_annual
                       + (fuel_bik_monthly + driver_bik_monthly
                          + accommodation_bik_monthly) * 12) / 12

    This value should be added to the employee's monthly gross income before
    computing annual taxable income for PCB purposes.

    Args:
        employee_name: Employee document name.
        year: Payroll period year (int).

    Returns:
        float: Monthly BIK amount to add to gross income (RM).
                Returns 0.0 if no BIK record exists.
    """
    year = int(year)
    docname = frappe.db.get_value(
        "Employee BIK Record",
        {"employee": employee_name, "payroll_period_year": year},
        "name",
    )
    if not docname:
        return 0.0

    doc = frappe.get_doc("Employee BIK Record", docname)
    return float(doc.total_monthly_bik or 0)


def get_annual_bik_for_ea_form(employee_name: str, year: int) -> float:
    """Return total annual BIK for EA Form Section B7.

    Args:
        employee_name: Employee document name.
        year: Payroll period year (int).

    Returns:
        float: Annual BIK amount for EA Form B7 (RM). Returns 0.0 if no record.
    """
    year = int(year)
    docname = frappe.db.get_value(
        "Employee BIK Record",
        {"employee": employee_name, "payroll_period_year": year},
        "name",
    )
    if not docname:
        return 0.0

    doc = frappe.get_doc("Employee BIK Record", docname)
    return float(doc.total_annual_bik or 0)
