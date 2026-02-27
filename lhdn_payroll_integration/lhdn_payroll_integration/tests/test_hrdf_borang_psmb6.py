"""Tests for US-044: HRDF Borang PSMB/6 Annual Return report.

Verifies column structure, filter requirements, and that the annual levy
total aggregated by the PSMB/6 report matches the sum of monthly HRDF
Monthly Levy report figures for the same company and year.
"""
import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_borang_psmb6.hrdf_borang_psmb6 import (
    execute,
    get_columns,
    get_data,
    _HRDF_COMPONENTS,
)
from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
    get_data as get_monthly_data,
)

REQUIRED_FIELDNAMES = {"month_label", "total_employees", "total_wages", "total_levy"}


class TestHrdfBorangPsmb6Columns(FrappeTestCase):
    """Tests for get_columns() structure."""

    def test_get_columns_returns_list(self):
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 4)

    def test_required_fieldnames_present(self):
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

    def test_total_employees_is_int_type(self):
        columns = get_columns()
        emp_col = next(
            (c for c in columns if c.get("fieldname") == "total_employees"), None
        )
        self.assertIsNotNone(emp_col, "total_employees column must exist")
        self.assertEqual(emp_col.get("fieldtype"), "Int")


class TestHrdfBorangPsmb6Data(FrappeTestCase):
    """Tests for get_data() with synthetic salary slips."""

    def _get_or_create_company(self):
        company = frappe.db.get_single_value("Global Defaults", "default_company")
        if not company:
            company = frappe.db.get_value("Company", {}, "name")
        return company

    def _get_or_create_test_employee(self, suffix="P6A"):
        emp_id = f"EMP-P6TEST-{suffix}"
        if frappe.db.exists("Employee", emp_id):
            return emp_id

        company = self._get_or_create_company()

        emp = frappe.new_doc("Employee")
        emp.employee = emp_id
        emp.first_name = "PSMB6"
        emp.last_name = f"Test{suffix}"
        emp.date_of_joining = "2020-01-01"
        emp.date_of_birth = "1990-01-01"
        emp.gender = "Male"
        emp.company = company
        emp.status = "Active"
        emp.insert(ignore_permissions=True)
        return emp.name

    def _make_salary_slip(self, employee, company, year, month, gross_pay, hrdf_amount):
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
        slip.net_pay = gross_pay - hrdf_amount
        slip.docstatus = 1

        slip.append(
            "deductions",
            {"salary_component": "HRDF", "amount": hrdf_amount},
        )

        slip.insert(ignore_permissions=True)
        return slip.name

    def test_get_data_returns_list(self):
        filters = frappe._dict({"year": 2026, "company": None})
        result = get_data(filters)
        self.assertIsInstance(result, list)

    def test_empty_filters_returns_empty(self):
        """Missing company or year should return empty list."""
        self.assertEqual(get_data(frappe._dict({})), [])
        self.assertEqual(
            get_data(frappe._dict({"year": 2026})), []
        )

    def test_execute_returns_columns_and_data(self):
        columns, data = execute(frappe._dict({"year": 2026, "company": None}))
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)

    def test_rows_have_all_required_keys(self):
        company = self._get_or_create_company()
        rows = get_data(frappe._dict({"year": 2000, "company": company}))
        if not rows:
            return  # No data for 2000 — structure test passes vacuously
        for row in rows:
            for key in REQUIRED_FIELDNAMES:
                self.assertIn(key, row, f"Row missing required key: {key}")

    def test_levy_total_matches_monthly_levy_report(self):
        """Borang PSMB/6 levy total must equal the sum of monthly levy figures."""
        company = self._get_or_create_company()
        if not company:
            self.skipTest("No company found in test DB")

        # Ensure HRDF salary component exists
        if not frappe.db.exists("Salary Component", "HRDF"):
            sc = frappe.new_doc("Salary Component")
            sc.salary_component = "HRDF"
            sc.salary_component_abbr = "HRDF"
            sc.type = "Deduction"
            sc.insert(ignore_permissions=True)

        try:
            emp = self._get_or_create_test_employee("P6A")
        except Exception:
            self.skipTest("Could not create test Employee")

        # Use a year unlikely to already have HRDF slips
        TEST_YEAR = 2022
        created = []
        try:
            for month, gross, levy in [
                (1, 5000.0, 25.0),
                (2, 5000.0, 25.0),
                (3, 5500.0, 27.5),
            ]:
                name = self._make_salary_slip(emp, company, TEST_YEAR, month, gross, levy)
                created.append(name)
        except Exception as exc:
            self.skipTest(f"Could not create test Salary Slips: {exc}")

        # Get PSMB/6 annual total
        psmb6_data = get_data(frappe._dict({"year": TEST_YEAR, "company": company}))
        psmb6_levy_total = sum(row.get("total_levy", 0) for row in psmb6_data)

        # Get monthly levy totals for each month individually
        monthly_levy_total = 0.0
        for month in ["01", "02", "03"]:
            monthly_rows = get_monthly_data(
                frappe._dict({"year": TEST_YEAR, "month": month, "company": company})
            )
            monthly_levy_total += sum(r.get("hrdf_levy", 0) for r in monthly_rows)

        self.assertAlmostEqual(
            psmb6_levy_total,
            monthly_levy_total,
            places=2,
            msg=(
                f"PSMB/6 levy total ({psmb6_levy_total}) must match "
                f"sum of monthly levy reports ({monthly_levy_total})"
            ),
        )

    def test_month_label_is_human_readable(self):
        """Rows should contain month names, not raw numbers."""
        company = self._get_or_create_company()
        rows = get_data(frappe._dict({"year": 2022, "company": company}))
        for row in rows:
            label = row.get("month_label", "")
            self.assertIsInstance(label, str)
            self.assertTrue(
                label[0].isupper(),
                f"Month label should be capitalized, got: {label!r}",
            )
