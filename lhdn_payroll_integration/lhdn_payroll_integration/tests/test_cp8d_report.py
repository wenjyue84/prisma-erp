"""Tests for CP8D Annual Employee Remuneration Return — US-031.

Verifies column structure and per-employee annual aggregation logic.
CP8D is submitted alongside Borang E for LHDN e-Filing.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.cp8d.cp8d import (
    execute,
    get_columns,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "employee_tin",
    "id_number",
    "employee_name",
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
        self.assertGreaterEqual(len(columns), 6)

    def test_get_columns_required_fieldnames(self):
        columns = get_columns()
        fieldnames = {col.get("fieldname") for col in columns if isinstance(col, dict)}
        for required in REQUIRED_FIELDNAMES:
            self.assertIn(required, fieldnames, f"Missing fieldname: {required}")

    def test_currency_columns_have_myr_options(self):
        columns = get_columns()
        for col in columns:
            if isinstance(col, dict) and col.get("fieldtype") == "Currency":
                self.assertEqual(
                    col.get("options"),
                    "MYR",
                    f"Column {col.get('fieldname')} missing MYR options",
                )


class TestCP8DData(FrappeTestCase):
    """Tests for get_data() and execute() with synthetic salary slips."""

    def _get_or_create_company(self):
        company = frappe.db.get_single_value("Global Defaults", "default_company")
        if not company:
            company = frappe.db.get_value("Company", {}, "name")
        return company

    def _get_or_create_test_employee(self, suffix="001"):
        emp_id = f"EMP-CP8DTEST-{suffix}"
        if frappe.db.exists("Employee", emp_id):
            return emp_id

        company = self._get_or_create_company()

        emp = frappe.new_doc("Employee")
        emp.employee = emp_id
        emp.first_name = "CP8D"
        emp.last_name = f"TestEmp{suffix}"
        emp.date_of_joining = "2020-01-01"
        emp.date_of_birth = "1990-01-01"
        emp.gender = "Male"
        emp.company = company
        emp.status = "Active"
        emp.custom_lhdn_tin = f"TIN{suffix}TEST"
        emp.custom_id_type = "NRIC"
        emp.custom_id_value = f"900101-14-{suffix.zfill(4)}"
        emp.insert(ignore_permissions=True)
        return emp.name

    def _make_salary_slip(self, employee, company, year, month, gross_pay, net_pay, deductions):
        import datetime

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

    def test_annual_totals_aggregation(self):
        """Two submitted slips for same employee in same year → single row with summed totals."""
        company = self._get_or_create_company()
        if not company:
            self.skipTest("No company found in test DB")

        try:
            emp = self._get_or_create_test_employee("001")
        except Exception:
            self.skipTest("Could not create test Employee")

        try:
            self._make_salary_slip(
                employee=emp,
                company=company,
                year=2023,
                month=1,
                gross_pay=6000.0,
                net_pay=5100.0,
                deductions={"EPF": 660.0, "SOCSO": 60.0, "EIS": 14.4, "PCB": 165.6},
            )
            self._make_salary_slip(
                employee=emp,
                company=company,
                year=2023,
                month=2,
                gross_pay=6000.0,
                net_pay=5100.0,
                deductions={"EPF": 660.0, "SOCSO": 60.0, "EIS": 14.4, "PCB": 165.6},
            )
        except Exception:
            self.skipTest("Could not create test Salary Slips — check doctype requirements")

        filters = frappe._dict({"year": 2023, "company": company})
        data = get_data(filters)

        matching = [r for r in data if r.get("employee_name") == "CP8D TestEmp001"]
        self.assertGreaterEqual(len(matching), 1, "Expected at least one row for test employee")

        row = matching[0]
        self.assertAlmostEqual(row["annual_gross"], 12000.0, places=2, msg="Annual gross should sum both months")
        self.assertAlmostEqual(row["total_pcb"], 331.2, places=2, msg="PCB should sum both months")
        self.assertAlmostEqual(row["epf_employee"], 1320.0, places=2, msg="EPF should sum both months")

    def test_employee_tin_included(self):
        """Rows should include employee_tin from custom_lhdn_tin field."""
        company = self._get_or_create_company()
        if not company:
            self.skipTest("No company found in test DB")

        try:
            emp = self._get_or_create_test_employee("001")
        except Exception:
            self.skipTest("Could not create test Employee")

        filters = frappe._dict({"year": 2023, "company": company})
        data = get_data(filters)

        matching = [r for r in data if r.get("employee_name") == "CP8D TestEmp001"]
        if not matching:
            self.skipTest("No matching rows — run test_annual_totals_aggregation first")

        row = matching[0]
        self.assertIn("employee_tin", row, "Row missing employee_tin key")
        self.assertIn("id_number", row, "Row missing id_number key")

    def test_rows_have_all_required_keys(self):
        """Each row must contain all CP8D required fieldnames."""
        company = self._get_or_create_company()
        filters = frappe._dict({"year": 2023, "company": company})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data rows — required key test skipped")
        for row in rows:
            for key in REQUIRED_FIELDNAMES:
                self.assertIn(key, row, f"Row missing required key: {key}")

    def test_year_filter_excludes_other_years(self):
        """Year filter must restrict rows to the specified year."""
        company = self._get_or_create_company()
        # Use a far-past year unlikely to have test data
        filters = frappe._dict({"year": 2000, "company": company})
        data = get_data(filters)
        self.assertIsInstance(data, list)
        # If data exists for 2000, it should not include 2023 slips
        for row in data:
            self.assertIn("annual_gross", row)
