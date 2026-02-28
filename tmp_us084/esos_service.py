"""ESOS / Share Option service — US-084.

ITA 1967 Section 25 and Public Ruling No. 1/2021:
  Gains from ESOS/ESPP exercise are taxable employment income in the year
  of exercise.

  Taxable Gain = (Market Price on exercise date - Exercise Price) x Shares

The gain is treated as an irregular payment (like a bonus) and PCB is
computed using the LHDN one-twelfth annualisation rule for the month in
which the options are exercised.
"""
import frappe


def get_esos_gain_for_month(employee: str, month: int, year: int) -> float:
    """Return total ESOS taxable gain for an employee in a given month/year.

    Sums all Employee Share Option Exercise records where exercise_date falls
    within the specified month and year.

    Args:
        employee: Employee document name.
        month:    Calendar month (1-12).
        year:     Calendar year (e.g. 2025).

    Returns:
        float: Total taxable gain (RM). 0.0 if no exercise records found.
    """
    rows = frappe.db.sql(
        """
        SELECT COALESCE(SUM(taxable_gain), 0) AS total_gain
        FROM `tabEmployee Share Option Exercise`
        WHERE employee = %(employee)s
          AND MONTH(exercise_date) = %(month)s
          AND YEAR(exercise_date)  = %(year)s
        """,
        {"employee": employee, "month": int(month), "year": int(year)},
    )
    return float(rows[0][0]) if rows else 0.0


def get_esos_gain_for_year(employee: str, year: int) -> float:
    """Return total ESOS taxable gain for an employee for a full calendar year.

    Used by the EA Form to populate Section B10.

    Args:
        employee: Employee document name.
        year:     Calendar year (e.g. 2025).

    Returns:
        float: Total taxable gain (RM). 0.0 if no exercise records found.
    """
    rows = frappe.db.sql(
        """
        SELECT COALESCE(SUM(taxable_gain), 0) AS total_gain
        FROM `tabEmployee Share Option Exercise`
        WHERE employee = %(employee)s
          AND YEAR(exercise_date) = %(year)s
        """,
        {"employee": employee, "year": int(year)},
    )
    return float(rows[0][0]) if rows else 0.0
