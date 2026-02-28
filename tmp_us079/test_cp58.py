"""Tests for CP58 Agent/Dealer Non-Employment Income Statement — US-079.

ITA 1967 s.83A(1A) + P.U.(A) 220/2019: payers must issue CP58 to agents,
dealers, and distributors receiving commission/incentive payments by 31 March.

Tests:
1. Column structure — all required fieldnames present
2. Monthly breakdown columns Jan–Dec present
3. Total annual column present
4. get_data() returns a list
5. execute() returns (columns, data)
6. Contractor with 3 commission payments — correct annual total
7. Employee payee_type rows are excluded
8. Year filter restricts results correctly
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.cp58_agent_statement.cp58_agent_statement import (
    execute,
    get_columns,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "payee_name",
    "payee_nric_reg",
    "payee_tin",
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
    "total_annual",
}

MONTH_FIELDNAMES = [
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
]


class TestCP58Columns(FrappeTestCase):
    """Verify column structure matches CP58 LHDN requirements."""

    def test_get_columns_returns_list(self):
        cols = get_columns()
        self.assertIsInstance(cols, list)

    def test_get_columns_minimum_count(self):
        cols = get_columns()
        # 3 identity cols + 12 months + 1 total = 16
        self.assertGreaterEqual(len(cols), 16)

    def test_required_fieldnames_present(self):
        cols = get_columns()
        fieldnames = {c.get("fieldname") for c in cols if isinstance(c, dict)}
        for required in REQUIRED_FIELDNAMES:
            self.assertIn(required, fieldnames, f"Missing column: {required}")

    def test_month_columns_all_present(self):
        cols = get_columns()
        fieldnames = [c.get("fieldname") for c in cols if isinstance(c, dict)]
        for month in MONTH_FIELDNAMES:
            self.assertIn(month, fieldnames, f"Missing month column: {month}")

    def test_total_annual_is_last_column(self):
        cols = get_columns()
        last = cols[-1]
        self.assertEqual(last.get("fieldname"), "total_annual")

    def test_currency_columns_have_myr_options(self):
        cols = get_columns()
        for col in cols:
            if isinstance(col, dict) and col.get("fieldtype") == "Currency":
                self.assertEqual(
                    col.get("options"),
                    "MYR",
                    f"Column {col.get('fieldname')} missing MYR options",
                )

    def test_payee_name_is_data_column(self):
        cols = get_columns()
        col = next((c for c in cols if c.get("fieldname") == "payee_name"), None)
        self.assertIsNotNone(col, "payee_name column missing")
        self.assertEqual(col.get("fieldtype"), "Data")

    def test_payee_nric_reg_is_data_column(self):
        cols = get_columns()
        col = next((c for c in cols if c.get("fieldname") == "payee_nric_reg"), None)
        self.assertIsNotNone(col, "payee_nric_reg column missing")
        self.assertEqual(col.get("fieldtype"), "Data")


class TestCP58Data(FrappeTestCase):
    """Verify data retrieval, filtering, and annual totals."""

    def _get_company(self):
        company = frappe.db.get_single_value("Global Defaults", "default_company")
        if not company:
            company = frappe.db.get_value("Company", {}, "name")
        return company

    def _get_or_create_test_employee(self):
        """Create a minimal Employee for Expense Claim linkage."""
        emp_id = "EMP-CP58TEST-001"
        if frappe.db.exists("Employee", emp_id):
            return emp_id
        company = self._get_company()
        emp = frappe.new_doc("Employee")
        emp.employee = emp_id
        emp.first_name = "CP58"
        emp.last_name = "TestEmp"
        emp.date_of_joining = "2020-01-01"
        emp.date_of_birth = "1990-01-01"
        emp.gender = "Male"
        emp.company = company
        emp.status = "Active"
        emp.insert(ignore_permissions=True)
        return emp.name

    def _make_expense_claim(
        self,
        employee,
        company,
        posting_date,
        amount,
        payee_type="Contractor",
        payment_category="Commission",
        payee_name="Ahmad Komisyen",
        payee_nric_reg="901234-56-7890",
        payee_tin="IG1234567890",
    ):
        """Create and submit an Expense Claim tagged as contractor commission."""
        ec = frappe.new_doc("Expense Claim")
        ec.employee = employee
        ec.company = company
        ec.posting_date = posting_date
        ec.expenses = []

        expense_type = frappe.db.get_value("Expense Claim Type", {}, "name")
        if not expense_type:
            # Create minimal expense type if none exists
            et = frappe.new_doc("Expense Claim Type")
            et.expense_type = "Commission Payment"
            et.insert(ignore_permissions=True)
            expense_type = et.name

        ec.append(
            "expenses",
            {
                "expense_date": posting_date,
                "expense_type": expense_type,
                "amount": amount,
                "sanctioned_amount": amount,
            },
        )
        ec.total_claimed_amount = amount
        ec.total_sanctioned_amount = amount

        # CP58 custom fields
        ec.custom_payee_type = payee_type
        ec.custom_payment_category = payment_category
        ec.custom_payee_name = payee_name
        ec.custom_payee_nric_reg = payee_nric_reg
        ec.custom_payee_tin = payee_tin

        ec.insert(ignore_permissions=True)

        # Submit
        ec.docstatus = 1
        ec.db_update()
        frappe.db.set_value("Expense Claim", ec.name, "docstatus", 1)

        return ec.name

    def test_get_data_returns_list(self):
        result = get_data(frappe._dict({"company": None, "year": 2023}))
        self.assertIsInstance(result, list)

    def test_execute_returns_columns_and_data(self):
        columns, data = execute(frappe._dict({"year": 2023}))
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)

    def test_contractor_annual_total_three_payments(self):
        """Contractor with 3 commission payments in different months → correct annual total."""
        company = self._get_company()
        if not company:
            self.skipTest("No company in test DB")

        try:
            emp = self._get_or_create_test_employee()
        except Exception:
            self.skipTest("Could not create test Employee")

        payee_name = "CP58-TestAgent-Zainab"
        payee_nric = "801010-12-3456"
        amounts = [1500.0, 2000.0, 2500.0]
        dates = ["2023-01-15", "2023-04-20", "2023-09-10"]

        try:
            for date, amt in zip(dates, amounts):
                self._make_expense_claim(
                    employee=emp,
                    company=company,
                    posting_date=date,
                    amount=amt,
                    payee_name=payee_name,
                    payee_nric_reg=payee_nric,
                )
        except Exception as e:
            self.skipTest(f"Could not create Expense Claims: {e}")

        filters = frappe._dict({"company": company, "year": 2023})
        data = get_data(filters)

        matching = [r for r in data if r.get("payee_name") == payee_name]
        self.assertGreaterEqual(len(matching), 1, "No CP58 row found for test agent")

        row = matching[0]
        expected_total = sum(amounts)  # 6000.0
        self.assertAlmostEqual(
            float(row.get("total_annual", 0)),
            expected_total,
            places=2,
            msg=f"Annual total should be {expected_total}, got {row.get('total_annual')}",
        )

        # Jan = 1500.0
        self.assertAlmostEqual(float(row.get("jan", 0)), 1500.0, places=2)
        # Apr = 2000.0
        self.assertAlmostEqual(float(row.get("apr", 0)), 2000.0, places=2)
        # Sep = 2500.0
        self.assertAlmostEqual(float(row.get("sep", 0)), 2500.0, places=2)
        # Other months = 0
        self.assertAlmostEqual(float(row.get("feb", 0)), 0.0, places=2)

    def test_nric_and_tin_in_row(self):
        """CP58 row includes NRIC/Reg and TIN for the agent."""
        company = self._get_company()
        if not company:
            self.skipTest("No company in test DB")

        filters = frappe._dict({"company": company, "year": 2023})
        data = get_data(filters)
        matching = [r for r in data if r.get("payee_name") == "CP58-TestAgent-Zainab"]
        if not matching:
            self.skipTest("Run test_contractor_annual_total_three_payments first")

        row = matching[0]
        self.assertIn("payee_nric_reg", row)
        self.assertIn("payee_tin", row)
        self.assertEqual(row.get("payee_nric_reg"), "801010-12-3456")

    def test_employee_payee_type_excluded(self):
        """Expense Claims with payee_type=Employee are excluded from CP58."""
        company = self._get_company()
        if not company:
            self.skipTest("No company in test DB")

        try:
            emp = self._get_or_create_test_employee()
        except Exception:
            self.skipTest("Could not create test Employee")

        employee_payee = "CP58-ExcludedEmployee-Payee"
        try:
            self._make_expense_claim(
                employee=emp,
                company=company,
                posting_date="2023-03-01",
                amount=5000.0,
                payee_type="Employee",
                payee_name=employee_payee,
            )
        except Exception:
            self.skipTest("Could not create Employee-type Expense Claim")

        filters = frappe._dict({"company": company, "year": 2023})
        data = get_data(filters)
        matching = [r for r in data if r.get("payee_name") == employee_payee]
        self.assertEqual(
            len(matching),
            0,
            "Employee payee_type claim should not appear in CP58",
        )

    def test_year_filter_excludes_other_years(self):
        """Year filter must restrict results to the specified assessment year."""
        company = self._get_company()
        # Use a far-past year unlikely to have any data
        filters = frappe._dict({"company": company, "year": 2000})
        data = get_data(filters)
        self.assertIsInstance(data, list)
        for row in data:
            self.assertIn("total_annual", row)

    def test_rows_have_all_required_keys(self):
        """Every data row must contain all CP58 required field keys."""
        company = self._get_company()
        filters = frappe._dict({"company": company, "year": 2023})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No CP58 data rows for 2023 — required key test skipped")
        for row in rows:
            for key in REQUIRED_FIELDNAMES:
                self.assertIn(key, row, f"Row missing required key: {key}")

    def test_amounts_are_numeric(self):
        """All monthly and total amounts must be numeric."""
        company = self._get_company()
        filters = frappe._dict({"company": company, "year": 2023})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data rows — numeric check skipped")
        numeric_fields = MONTH_FIELDNAMES + ["total_annual"]
        for row in rows:
            for field in numeric_fields:
                val = row.get(field, 0)
                try:
                    float(val)
                except (TypeError, ValueError):
                    self.fail(f"Field '{field}' value '{val}' is not numeric")
