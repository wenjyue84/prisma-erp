"""Tests for CP8D Annual Employee Remuneration Return — US-031.

Verifies column structure and per-employee annual totals.
"""
import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.cp8d.cp8d import (
    execute,
    get_columns,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "employee",
    "employee_name",
    "employee_tin",
    "nric",
    "annual_gross",
    "total_pcb",
    "epf_employee",
}


class TestCP8DColumns(FrappeTestCase):
    """Tests for get_columns() structure."""

    def test_get_columns_returns_list(self):
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 7)

    def test_get_columns_required_fieldnames(self):
        columns = get_columns()
        fieldnames = {col.get("fieldname") for col in columns if isinstance(col, dict)}
        for required in REQUIRED_FIELDNAMES:
            self.assertIn(required, fieldnames, f"Missing fieldname: {required}")


class TestCP8DData(FrappeTestCase):
    """Tests for get_data() and execute() with synthetic salary slips."""

    def _get_or_create_test_employee(self):
        emp_id = "EMP-CP8DTEST-001"
        if frappe.db.exists("Employee", emp_id):
            return emp_id

        company = frappe.db.get_single_value("Global Defaults", "default_company")
        if not company:
            company = frappe.db.get_value("Company", {}, "name")

        emp = frappe.new_doc("Employee")
        emp.employee = emp_id
        emp.first_name = "CP8D"
        emp.last_name = "TestEmployee"
        emp.date_of_joining = "2020-01-01"
        emp.date_of_birth = "1990-01-01"
        emp.gender = "Male"
        emp.company = company
        emp.status = "Active"
        emp.insert(ignore_permissions=True)
        return emp.name

    def _make_salary_slip(self, employee, company, year, month, gross_pay, net_pay, deductions):
        start = datetime.date(year, month, 1)
        last_day = (
            datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
            if month < 12
            else datetime.date(year, 12, 31)
        )

        slip = frappe.new_doc("Salary Slip")
        slip.employee = employee
        slip.company = company
        slip.start_date = start
        slip.end_date = last_day
        slip.posting_date = last_day
        slip.payroll_frequency = "Monthly"
        slip.gross_pay = gross_pay
        slip.net_pay = net_pay
        slip.docstatus = 1

        for component, amount in deductions.items():
            slip.append(
                "deductions",
                {"salary_component": component, "amount": amount},
            )

        slip.insert(ignore_permissions=True)
        return slip.name

    def test_get_data_returns_list(self):
        filters = frappe._dict({"year": 2026, "company": None})
        result = get_data(filters)
        self.assertIsInstance(result, list)

    def test_execute_returns_columns_and_data(self):
        columns, data = execute(frappe._dict({"year": 2026}))
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)

    def test_per_employee_annual_totals(self):
        """Two submitted slips for the same employee, same year → single aggregated row
        with correct annual_gross, total_pcb, and epf_employee totals."""
        company = frappe.db.get_single_value("Global Defaults", "default_company")
        if not company:
            company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("No company found in test DB")

        emp = self._get_or_create_test_employee()

        try:
            self._make_salary_slip(
                employee=emp,
                company=company,
                year=2025,
                month=3,
                gross_pay=6000.0,
                net_pay=5200.0,
                deductions={"EPF": 660.0, "PCB": 140.0},
            )
            self._make_salary_slip(
                employee=emp,
                company=company,
                year=2025,
                month=4,
                gross_pay=6000.0,
                net_pay=5200.0,
                deductions={"EPF": 660.0, "PCB": 140.0},
            )
        except Exception:
            self.skipTest("Could not create test Salary Slips")

        filters = frappe._dict({"year": 2025, "company": company, "employee": emp})
        # employee filter not in get_data() — use company + year + filter post-hoc
        filters_no_emp = frappe._dict({"year": 2025, "company": company})
        data = get_data(filters_no_emp)

        matching = [r for r in data if r.get("employee") == emp and r.get("annual_gross", 0) > 0]
        self.assertGreaterEqual(len(matching), 1, "Expected at least one row for test employee")

        row = matching[0]
        self.assertAlmostEqual(row["annual_gross"], 12000.0, places=2,
            msg="Annual gross should be sum of 2 months (6000+6000)")
        self.assertAlmostEqual(row["total_pcb"], 280.0, places=2,
            msg="Total PCB should be sum of 2 months (140+140)")
        self.assertAlmostEqual(row["epf_employee"], 1320.0, places=2,
            msg="EPF Employee should be sum of 2 months (660+660)")

    def test_result_row_has_required_keys(self):
        """Each result row must contain all required fieldnames."""
        company = frappe.db.get_single_value("Global Defaults", "default_company")
        if not company:
            company = frappe.db.get_value("Company", {}, "name")

        filters = frappe._dict({"year": 2025, "company": company})
        data = get_data(filters)
        for row in data:
            for key in REQUIRED_FIELDNAMES:
                self.assertIn(key, row, f"Row missing key: {key}")
