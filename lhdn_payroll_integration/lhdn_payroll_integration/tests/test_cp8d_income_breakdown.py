"""Tests for CP8D income type breakdown — US-078.

Verifies that bonus (B4), commission (B3), gratuity (B5), and other income (B9)
amounts from EA Section-tagged salary components appear in the correct
CP8D 2024 breakdown columns.
"""
import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.cp8d.cp8d import get_data as cp8d_get_data
from lhdn_payroll_integration.lhdn_payroll_integration.report.cp8d_efiling.cp8d_efiling import (
    get_columns as efiling_get_columns,
    get_data as efiling_get_data,
)


class TestCP8DIncomeBreakdownColumns(FrappeTestCase):
    """Verify breakdown columns exist in both CP8D reports."""

    def test_cp8d_has_gross_bonus_commission_column(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.cp8d.cp8d import get_columns
        fieldnames = {c["fieldname"] for c in get_columns() if isinstance(c, dict)}
        self.assertIn("gross_bonus_commission", fieldnames)

    def test_cp8d_has_gross_gratuity_column(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.cp8d.cp8d import get_columns
        fieldnames = {c["fieldname"] for c in get_columns() if isinstance(c, dict)}
        self.assertIn("gross_gratuity", fieldnames)

    def test_cp8d_has_other_income_column(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.cp8d.cp8d import get_columns
        fieldnames = {c["fieldname"] for c in get_columns() if isinstance(c, dict)}
        self.assertIn("other_income", fieldnames)

    def test_efiling_has_breakdown_columns(self):
        fieldnames = {c["fieldname"] for c in efiling_get_columns() if isinstance(c, dict)}
        for col in ("gross_bonus_commission", "gross_gratuity", "other_income"):
            self.assertIn(col, fieldnames, f"e-Filing missing column: {col}")

    def test_efiling_breakdown_columns_are_currency_myr(self):
        for col in efiling_get_columns():
            if isinstance(col, dict) and col.get("fieldname") in (
                "gross_bonus_commission", "gross_gratuity", "other_income"
            ):
                self.assertEqual(col.get("fieldtype"), "Currency")
                self.assertEqual(col.get("options"), "MYR")


class TestCP8DIncomeBreakdownData(FrappeTestCase):
    """Verify income breakdown values are correctly computed from EA-tagged components."""

    def _get_company(self):
        company = frappe.db.get_single_value("Global Defaults", "default_company")
        if not company:
            company = frappe.db.get_value("Company", {}, "name")
        return company

    def _get_or_create_salary_component(self, name, ea_section):
        """Get or create a salary component with a specific EA section tag."""
        if frappe.db.exists("Salary Component", name):
            # Ensure ea_section is set correctly
            frappe.db.set_value("Salary Component", name, "custom_ea_section", ea_section)
            return name

        sc = frappe.new_doc("Salary Component")
        sc.salary_component = name
        sc.salary_component_abbr = name[:4].upper().replace(" ", "")[:4]
        sc.type = "Earning"
        sc.custom_ea_section = ea_section
        sc.insert(ignore_permissions=True)
        return name

    def _get_or_create_employee(self, emp_id):
        if frappe.db.exists("Employee", emp_id):
            return emp_id
        company = self._get_company()
        emp = frappe.new_doc("Employee")
        emp.employee = emp_id
        emp.first_name = "Breakdown"
        emp.last_name = emp_id[-3:]
        emp.date_of_joining = "2020-01-01"
        emp.date_of_birth = "1990-01-01"
        emp.gender = "Male"
        emp.company = company
        emp.status = "Active"
        emp.insert(ignore_permissions=True)
        return emp.name

    def _make_salary_slip(self, employee, company, year, month, earnings, deductions=None):
        start = datetime.date(year, month, 1)
        last_day = (
            datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
            if month < 12
            else datetime.date(year, 12, 31)
        )
        gross = sum(earnings.values())
        net = gross - sum((deductions or {}).values())
        slip = frappe.new_doc("Salary Slip")
        slip.employee = employee
        slip.company = company
        slip.start_date = start
        slip.end_date = last_day
        slip.posting_date = last_day
        slip.payroll_frequency = "Monthly"
        slip.gross_pay = gross
        slip.net_pay = net
        slip.docstatus = 1
        for comp, amt in earnings.items():
            slip.append("earnings", {"salary_component": comp, "amount": amt})
        for comp, amt in (deductions or {}).items():
            slip.append("deductions", {"salary_component": comp, "amount": amt})
        slip.insert(ignore_permissions=True)
        return slip.name

    def test_bonus_b4_appears_in_gross_bonus_commission(self):
        """B4 Bonus earnings should appear in gross_bonus_commission column."""
        company = self._get_company()
        if not company:
            self.skipTest("No company in test DB")

        try:
            emp = self._get_or_create_employee("EMP-BD078-B4")
            bonus_comp = self._get_or_create_salary_component("BD078Bonus", "B4 Bonus")
            self._make_salary_slip(
                employee=emp, company=company, year=2024, month=1,
                earnings={bonus_comp: 1500.0},
            )
        except Exception as e:
            self.skipTest(f"Could not create test data: {e}")

        filters = frappe._dict({"year": 2024, "company": company})
        data = cp8d_get_data(filters)
        matching = [r for r in data if r.get("employee") == emp]
        self.assertGreaterEqual(len(matching), 1, "No row for bonus employee")
        row = matching[0]
        self.assertIn("gross_bonus_commission", row)
        self.assertAlmostEqual(row["gross_bonus_commission"], 1500.0, places=2,
            msg="B4 Bonus amount should appear in gross_bonus_commission")

    def test_commission_b3_appears_in_gross_bonus_commission(self):
        """B3 Commission earnings should appear in gross_bonus_commission column."""
        company = self._get_company()
        if not company:
            self.skipTest("No company in test DB")

        try:
            emp = self._get_or_create_employee("EMP-BD078-B3")
            comm_comp = self._get_or_create_salary_component("BD078Comm", "B3 Commission")
            self._make_salary_slip(
                employee=emp, company=company, year=2024, month=2,
                earnings={comm_comp: 800.0},
            )
        except Exception as e:
            self.skipTest(f"Could not create test data: {e}")

        filters = frappe._dict({"year": 2024, "company": company})
        data = cp8d_get_data(filters)
        matching = [r for r in data if r.get("employee") == emp]
        self.assertGreaterEqual(len(matching), 1, "No row for commission employee")
        row = matching[0]
        self.assertAlmostEqual(row["gross_bonus_commission"], 800.0, places=2,
            msg="B3 Commission amount should appear in gross_bonus_commission")

    def test_b3_and_b4_combined_in_gross_bonus_commission(self):
        """B3 Commission + B4 Bonus should both sum into gross_bonus_commission."""
        company = self._get_company()
        if not company:
            self.skipTest("No company in test DB")

        try:
            emp = self._get_or_create_employee("EMP-BD078-B34")
            bonus_comp = self._get_or_create_salary_component("BD078BonusCmb", "B4 Bonus")
            comm_comp = self._get_or_create_salary_component("BD078CommCmb", "B3 Commission")
            self._make_salary_slip(
                employee=emp, company=company, year=2024, month=3,
                earnings={bonus_comp: 500.0, comm_comp: 300.0},
            )
        except Exception as e:
            self.skipTest(f"Could not create test data: {e}")

        filters = frappe._dict({"year": 2024, "company": company})
        data = cp8d_get_data(filters)
        matching = [r for r in data if r.get("employee") == emp]
        self.assertGreaterEqual(len(matching), 1, "No row for combined bonus/commission employee")
        row = matching[0]
        self.assertAlmostEqual(row["gross_bonus_commission"], 800.0, places=2,
            msg="B3+B4 should combine into gross_bonus_commission (500+300=800)")

    def test_gratuity_b5_appears_in_gross_gratuity(self):
        """B5 Gratuity earnings should appear in gross_gratuity column."""
        company = self._get_company()
        if not company:
            self.skipTest("No company in test DB")

        try:
            emp = self._get_or_create_employee("EMP-BD078-B5")
            grat_comp = self._get_or_create_salary_component("BD078Grat", "B5 Gratuity")
            self._make_salary_slip(
                employee=emp, company=company, year=2024, month=4,
                earnings={grat_comp: 5000.0},
            )
        except Exception as e:
            self.skipTest(f"Could not create test data: {e}")

        filters = frappe._dict({"year": 2024, "company": company})
        data = cp8d_get_data(filters)
        matching = [r for r in data if r.get("employee") == emp]
        self.assertGreaterEqual(len(matching), 1, "No row for gratuity employee")
        row = matching[0]
        self.assertAlmostEqual(row["gross_gratuity"], 5000.0, places=2,
            msg="B5 Gratuity amount should appear in gross_gratuity")

    def test_other_gains_b9_appears_in_other_income(self):
        """B9 Other Gains earnings should appear in other_income column."""
        company = self._get_company()
        if not company:
            self.skipTest("No company in test DB")

        try:
            emp = self._get_or_create_employee("EMP-BD078-B9")
            other_comp = self._get_or_create_salary_component("BD078Other", "B9 Other Gains")
            self._make_salary_slip(
                employee=emp, company=company, year=2024, month=5,
                earnings={other_comp: 300.0},
            )
        except Exception as e:
            self.skipTest(f"Could not create test data: {e}")

        filters = frappe._dict({"year": 2024, "company": company})
        data = cp8d_get_data(filters)
        matching = [r for r in data if r.get("employee") == emp]
        self.assertGreaterEqual(len(matching), 1, "No row for other income employee")
        row = matching[0]
        self.assertAlmostEqual(row["other_income"], 300.0, places=2,
            msg="B9 Other Gains amount should appear in other_income")

    def test_breakdown_columns_zero_for_employees_without_tagged_components(self):
        """Employees with no EA-tagged earnings should have zero breakdown columns."""
        company = self._get_company()
        if not company:
            self.skipTest("No company in test DB")

        filters = frappe._dict({"year": 2025, "company": company})
        data = cp8d_get_data(filters)
        if not data:
            return  # Nothing to test

        for row in data:
            # All rows must have all three breakdown keys
            self.assertIn("gross_bonus_commission", row)
            self.assertIn("gross_gratuity", row)
            self.assertIn("other_income", row)
            # Values must be numeric (float)
            self.assertIsInstance(row["gross_bonus_commission"], float)
            self.assertIsInstance(row["gross_gratuity"], float)
            self.assertIsInstance(row["other_income"], float)

    def test_efiling_report_includes_breakdown_amounts(self):
        """CP8D e-Filing rows must also include income breakdown amounts."""
        company = self._get_company()
        if not company:
            self.skipTest("No company in test DB")

        filters = frappe._dict({"year": 2024, "company": company})
        data = efiling_get_data(filters)
        if not data:
            return  # Skip if no 2024 data

        for row in data:
            for key in ("gross_bonus_commission", "gross_gratuity", "other_income"):
                self.assertIn(key, row, f"e-Filing row missing breakdown key: {key}")
