"""Tests for Borang E US-062 enhancements.

US-062: Add Borang E Mandatory Header Fields (Employer E-Number, Branch Code, Director Section).

Acceptance criteria:
- custom_employer_e_number and custom_lhdn_branch_code fields exist in custom_field.json
- Borang E report header includes employer_e_number and lhdn_branch_code columns
- Summary row contains employer_e_number and lhdn_branch_code
- Summary row contains cat1_employees, cat2_employees, cat3_employees counts
- Summary row contains total_zakat
- Director employees appear with row_type == 'Director CP8D'
- Non-director employees appear with row_type == 'CP8D'
"""
import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch

from lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e import (
    execute,
    get_columns,
    get_data,
    _get_company_header_fields,
    _get_category_counts,
    _get_employee_worker_types,
)

# Required fieldnames for US-062
US062_REQUIRED_FIELDNAMES = {
    "row_type",
    "company",
    "year",
    "employer_e_number",
    "lhdn_branch_code",
    "total_employees",
    "cat1_employees",
    "cat2_employees",
    "cat3_employees",
    "total_gross",
    "total_pcb",
    "total_zakat",
    "worker_type",
}


class TestBorangEUS062Columns(FrappeTestCase):
    """Tests for US-062 column additions."""

    def test_columns_include_employer_e_number(self):
        columns = get_columns()
        fieldnames = {col["fieldname"] for col in columns if isinstance(col, dict)}
        self.assertIn(
            "employer_e_number", fieldnames, "Column employer_e_number missing from Borang E"
        )

    def test_columns_include_lhdn_branch_code(self):
        columns = get_columns()
        fieldnames = {col["fieldname"] for col in columns if isinstance(col, dict)}
        self.assertIn(
            "lhdn_branch_code", fieldnames, "Column lhdn_branch_code missing from Borang E"
        )

    def test_columns_include_category_counts(self):
        columns = get_columns()
        fieldnames = {col["fieldname"] for col in columns if isinstance(col, dict)}
        for cat_field in ("cat1_employees", "cat2_employees", "cat3_employees"):
            self.assertIn(cat_field, fieldnames, f"Column {cat_field} missing from Borang E")

    def test_columns_include_total_zakat(self):
        columns = get_columns()
        fieldnames = {col["fieldname"] for col in columns if isinstance(col, dict)}
        self.assertIn("total_zakat", fieldnames, "Column total_zakat missing from Borang E")

    def test_columns_include_worker_type(self):
        columns = get_columns()
        fieldnames = {col["fieldname"] for col in columns if isinstance(col, dict)}
        self.assertIn("worker_type", fieldnames, "Column worker_type missing from Borang E")

    def test_all_us062_required_columns_present(self):
        columns = get_columns()
        fieldnames = {col["fieldname"] for col in columns if isinstance(col, dict)}
        missing = US062_REQUIRED_FIELDNAMES - fieldnames
        self.assertFalse(missing, f"US-062 required columns missing: {missing}")


class TestBorangEUS062CustomFields(FrappeTestCase):
    """Tests that custom_field.json contains the required Company fields."""

    def _load_custom_fields(self):
        """Load fixture from app directory."""
        app_path = frappe.get_app_path("lhdn_payroll_integration")
        fixture_path = os.path.join(app_path, "fixtures", "custom_field.json")
        self.assertTrue(os.path.exists(fixture_path), f"Fixture not found: {fixture_path}")
        with open(fixture_path, "r") as f:
            return json.load(f)

    def test_custom_employer_e_number_in_fixture(self):
        data = self._load_custom_fields()
        company_fields = {
            f["fieldname"] for f in data if f.get("dt") == "Company"
        }
        self.assertIn(
            "custom_employer_e_number",
            company_fields,
            "custom_employer_e_number missing from Company custom fields fixture",
        )

    def test_custom_lhdn_branch_code_in_fixture(self):
        data = self._load_custom_fields()
        company_fields = {
            f["fieldname"] for f in data if f.get("dt") == "Company"
        }
        self.assertIn(
            "custom_lhdn_branch_code",
            company_fields,
            "custom_lhdn_branch_code missing from Company custom fields fixture",
        )

    def test_custom_employer_e_number_is_data_type(self):
        data = self._load_custom_fields()
        field = next(
            (f for f in data if f.get("fieldname") == "custom_employer_e_number"), None
        )
        self.assertIsNotNone(field, "custom_employer_e_number not found")
        self.assertEqual(field.get("fieldtype"), "Data")

    def test_custom_lhdn_branch_code_is_data_type(self):
        data = self._load_custom_fields()
        field = next(
            (f for f in data if f.get("fieldname") == "custom_lhdn_branch_code"), None
        )
        self.assertIsNotNone(field, "custom_lhdn_branch_code not found")
        self.assertEqual(field.get("fieldtype"), "Data")


class TestBorangEUS062SummaryRow(FrappeTestCase):
    """Tests for US-062 summary row fields."""

    def _get_mock_ea_rows(self, n=3, zakat=100.0, pcb_cat="1"):
        return [
            frappe._dict(
                {
                    "employee": f"EMP-{i:04d}",
                    "employee_name": f"Employee {i}",
                    "year": 2026,
                    "pcb_category": pcb_cat,
                    "total_gross": 5000.0,
                    "pcb_total": 200.0,
                    "annual_zakat": zakat,
                    "epf_employee": 550.0,
                    "socso_employee": 10.0,
                    "eis_employee": 5.0,
                    "net_pay": 4235.0,
                }
            )
            for i in range(n)
        ]

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e.get_ea_data"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_company_header_fields"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_category_counts"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employee_worker_types"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employer_component_total"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_total_cp38_deducted"
    )
    def test_summary_includes_employer_e_number(
        self,
        mock_cp38,
        mock_component,
        mock_worker_types,
        mock_cat_counts,
        mock_header,
        mock_ea,
    ):
        mock_ea.return_value = self._get_mock_ea_rows(2)
        mock_header.return_value = ("E1234567890", "JB01")
        mock_cat_counts.return_value = {"1": 2, "2": 0, "3": 0}
        mock_worker_types.return_value = {}
        mock_component.return_value = 0.0
        mock_cp38.return_value = 0.0

        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)

        self.assertTrue(rows, "get_data returned empty list")
        summary = rows[0]
        self.assertEqual(summary.get("employer_e_number"), "E1234567890")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e.get_ea_data"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_company_header_fields"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_category_counts"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employee_worker_types"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employer_component_total"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_total_cp38_deducted"
    )
    def test_summary_includes_lhdn_branch_code(
        self,
        mock_cp38,
        mock_component,
        mock_worker_types,
        mock_cat_counts,
        mock_header,
        mock_ea,
    ):
        mock_ea.return_value = self._get_mock_ea_rows(2)
        mock_header.return_value = ("E1234567890", "KL02")
        mock_cat_counts.return_value = {"1": 2, "2": 0, "3": 0}
        mock_worker_types.return_value = {}
        mock_component.return_value = 0.0
        mock_cp38.return_value = 0.0

        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)

        self.assertTrue(rows)
        self.assertEqual(rows[0].get("lhdn_branch_code"), "KL02")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e.get_ea_data"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_company_header_fields"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_category_counts"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employee_worker_types"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employer_component_total"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_total_cp38_deducted"
    )
    def test_summary_includes_category_counts(
        self,
        mock_cp38,
        mock_component,
        mock_worker_types,
        mock_cat_counts,
        mock_header,
        mock_ea,
    ):
        mock_ea.return_value = self._get_mock_ea_rows(5)
        mock_header.return_value = ("", "")
        mock_cat_counts.return_value = {"1": 3, "2": 1, "3": 1}
        mock_worker_types.return_value = {}
        mock_component.return_value = 0.0
        mock_cp38.return_value = 0.0

        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)

        self.assertTrue(rows)
        summary = rows[0]
        self.assertEqual(summary.get("cat1_employees"), 3)
        self.assertEqual(summary.get("cat2_employees"), 1)
        self.assertEqual(summary.get("cat3_employees"), 1)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e.get_ea_data"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_company_header_fields"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_category_counts"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employee_worker_types"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employer_component_total"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_total_cp38_deducted"
    )
    def test_summary_includes_total_zakat(
        self,
        mock_cp38,
        mock_component,
        mock_worker_types,
        mock_cat_counts,
        mock_header,
        mock_ea,
    ):
        # 3 employees each with zakat 120.0 → total = 360.0
        mock_ea.return_value = self._get_mock_ea_rows(3, zakat=120.0)
        mock_header.return_value = ("", "")
        mock_cat_counts.return_value = {"1": 3, "2": 0, "3": 0}
        mock_worker_types.return_value = {}
        mock_component.return_value = 0.0
        mock_cp38.return_value = 0.0

        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)

        self.assertTrue(rows)
        self.assertAlmostEqual(float(rows[0].get("total_zakat") or 0), 360.0, places=2)


class TestBorangEUS062DirectorSegregation(FrappeTestCase):
    """Tests for US-062 Section B: director row segregation."""

    def _get_mixed_ea_rows(self):
        """2 regular employees + 1 director."""
        return [
            frappe._dict(
                {
                    "employee": "EMP-0001",
                    "employee_name": "Alice Tan",
                    "year": 2026,
                    "pcb_category": "1",
                    "total_gross": 5000.0,
                    "pcb_total": 200.0,
                    "annual_zakat": 0.0,
                    "epf_employee": 550.0,
                    "socso_employee": 10.0,
                    "eis_employee": 5.0,
                    "net_pay": 4235.0,
                }
            ),
            frappe._dict(
                {
                    "employee": "EMP-0002",
                    "employee_name": "Bob Lim",
                    "year": 2026,
                    "pcb_category": "1",
                    "total_gross": 6000.0,
                    "pcb_total": 300.0,
                    "annual_zakat": 0.0,
                    "epf_employee": 660.0,
                    "socso_employee": 10.0,
                    "eis_employee": 5.0,
                    "net_pay": 5025.0,
                }
            ),
            frappe._dict(
                {
                    "employee": "EMP-0003",
                    "employee_name": "Charlie Wong",
                    "year": 2026,
                    "pcb_category": "1",
                    "total_gross": 20000.0,
                    "pcb_total": 3000.0,
                    "annual_zakat": 0.0,
                    "epf_employee": 0.0,
                    "socso_employee": 0.0,
                    "eis_employee": 0.0,
                    "net_pay": 17000.0,
                }
            ),
        ]

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e.get_ea_data"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_company_header_fields"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_category_counts"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employee_worker_types"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employer_component_total"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_total_cp38_deducted"
    )
    def test_director_rows_have_director_cp8d_type(
        self,
        mock_cp38,
        mock_component,
        mock_worker_types,
        mock_cat_counts,
        mock_header,
        mock_ea,
    ):
        mock_ea.return_value = self._get_mixed_ea_rows()
        mock_header.return_value = ("", "")
        mock_cat_counts.return_value = {"1": 3, "2": 0, "3": 0}
        # EMP-0003 is a director
        mock_worker_types.return_value = {
            "EMP-0001": "Employee",
            "EMP-0002": "Employee",
            "EMP-0003": "Director",
        }
        mock_component.return_value = 0.0
        mock_cp38.return_value = 0.0

        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)

        # row 0 = Summary, rows 1-3 = employees
        detail_rows = rows[1:]
        director_rows = [r for r in detail_rows if r.get("row_type") == "Director CP8D"]
        regular_rows = [r for r in detail_rows if r.get("row_type") == "CP8D"]

        self.assertEqual(len(director_rows), 1, "Expected 1 director row")
        self.assertEqual(director_rows[0].get("employee"), "EMP-0003")
        self.assertEqual(len(regular_rows), 2, "Expected 2 regular CP8D rows")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e.get_ea_data"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_company_header_fields"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_category_counts"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employee_worker_types"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employer_component_total"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_total_cp38_deducted"
    )
    def test_non_director_rows_have_cp8d_type(
        self,
        mock_cp38,
        mock_component,
        mock_worker_types,
        mock_cat_counts,
        mock_header,
        mock_ea,
    ):
        mock_ea.return_value = self._get_mixed_ea_rows()
        mock_header.return_value = ("", "")
        mock_cat_counts.return_value = {"1": 3, "2": 0, "3": 0}
        mock_worker_types.return_value = {
            "EMP-0001": "",
            "EMP-0002": "Employee",
            "EMP-0003": "Director",
        }
        mock_component.return_value = 0.0
        mock_cp38.return_value = 0.0

        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)

        detail_rows = rows[1:]
        for r in detail_rows:
            emp = r.get("employee")
            if emp in ("EMP-0001", "EMP-0002"):
                self.assertEqual(
                    r.get("row_type"),
                    "CP8D",
                    f"Employee {emp} should be CP8D, got {r.get('row_type')}",
                )

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e.get_ea_data"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_company_header_fields"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_category_counts"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employee_worker_types"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_employer_component_total"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e._get_total_cp38_deducted"
    )
    def test_detail_rows_include_worker_type_field(
        self,
        mock_cp38,
        mock_component,
        mock_worker_types,
        mock_cat_counts,
        mock_header,
        mock_ea,
    ):
        mock_ea.return_value = self._get_mixed_ea_rows()
        mock_header.return_value = ("", "")
        mock_cat_counts.return_value = {"1": 3, "2": 0, "3": 0}
        mock_worker_types.return_value = {
            "EMP-0001": "Employee",
            "EMP-0002": "Employee",
            "EMP-0003": "Director",
        }
        mock_component.return_value = 0.0
        mock_cp38.return_value = 0.0

        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)

        for r in rows[1:]:
            self.assertIn("worker_type", r, "worker_type field missing from detail row")


class TestBorangEUS062HelperFunctions(FrappeTestCase):
    """Tests for new US-062 helper functions."""

    def test_get_company_header_fields_empty_company(self):
        e_num, branch = _get_company_header_fields("")
        self.assertEqual(e_num, "")
        self.assertEqual(branch, "")

    def test_get_company_header_fields_none_company(self):
        e_num, branch = _get_company_header_fields(None)
        self.assertEqual(e_num, "")
        self.assertEqual(branch, "")

    def test_get_employee_worker_types_empty_list(self):
        result = _get_employee_worker_types(())
        self.assertEqual(result, {})

    def test_get_category_counts_returns_dict_with_three_keys(self):
        # Use year 1900 to ensure no data — should return zeros
        filters = frappe._dict({"company": "_Test Company", "year": 1900})
        counts = _get_category_counts(filters)
        self.assertIsInstance(counts, dict)
        self.assertIn("1", counts)
        self.assertIn("2", counts)
        self.assertIn("3", counts)

    def test_get_category_counts_values_are_non_negative(self):
        filters = frappe._dict({"company": "_Test Company", "year": 1900})
        counts = _get_category_counts(filters)
        for key in ("1", "2", "3"):
            self.assertGreaterEqual(counts[key], 0)
