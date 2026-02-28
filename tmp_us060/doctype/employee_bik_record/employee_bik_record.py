"""Employee BIK Record — DocType controller.

US-060: Benefits-in-Kind (BIK) Prescribed Value Calculation Module.

LHDN Public Ruling No. 3/2013 (updated 2019) prescribes annual values for
common BIK items. This DocType records per-employee BIK for a payroll period
year. The values are used to:
  - Add monthly BIK to gross income before PCB computation
  - Populate EA Form Section B7 (Benefits-in-Kind)
"""
import frappe
from frappe.model.document import Document

from lhdn_payroll_integration.services.bik_calculator import get_annual_car_bik


class EmployeeBIKRecord(Document):
    def validate(self):
        self._populate_car_bik()
        self._calculate_totals()

    def _populate_car_bik(self):
        """Auto-populate car_bik_annual from car_purchase_price if not manually set."""
        price = float(self.car_purchase_price or 0)
        if price > 0 and not float(self.car_bik_annual or 0):
            self.car_bik_annual = get_annual_car_bik(price)

    def _calculate_totals(self):
        """Calculate total_annual_bik and total_monthly_bik."""
        # Annual BIK items
        car = float(self.car_bik_annual or 0)
        club = float(self.club_membership_annual or 0)
        other = float(self.other_bik_annual or 0)

        # Monthly BIK items × 12
        fuel_annual = float(self.fuel_bik_monthly or 0) * 12
        driver_annual = float(self.driver_bik_monthly or 0) * 12
        accommodation_annual = float(self.accommodation_bik_monthly or 0) * 12

        total_annual = car + club + other + fuel_annual + driver_annual + accommodation_annual
        self.total_annual_bik = round(total_annual, 2)
        self.total_monthly_bik = round(total_annual / 12, 2)


@frappe.whitelist()
def get_employee_bik(employee: str, year: int) -> dict:
    """Return monthly and annual BIK total for an employee for a given year.

    Args:
        employee: Employee document name.
        year: Payroll period year (int or string coerced to int).

    Returns:
        dict with keys:
            - monthly_bik (float): Total monthly BIK to add to gross income.
            - annual_bik (float): Total annual BIK for EA Form B7.
            - docname (str | None): Name of the BIK record, or None if not found.
    """
    year = int(year)
    docname = frappe.db.get_value(
        "Employee BIK Record",
        {"employee": employee, "payroll_period_year": year},
        "name",
    )
    if not docname:
        return {"monthly_bik": 0.0, "annual_bik": 0.0, "docname": None}

    doc = frappe.get_doc("Employee BIK Record", docname)
    return {
        "monthly_bik": float(doc.total_monthly_bik or 0),
        "annual_bik": float(doc.total_annual_bik or 0),
        "docname": docname,
    }
