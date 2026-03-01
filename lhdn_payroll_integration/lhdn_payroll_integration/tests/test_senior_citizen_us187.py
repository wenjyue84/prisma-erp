"""Tests for US-187: Budget 2026 — Track Senior Citizen Employee Hiring Tax Deduction.

Acceptance criteria:
  1. Employees aged 60+ are automatically identified (based on DOB, not manual entry)
  2. Annual report generates summary with total wages per YA
  3. Report covers YA2026 to YA2030 as eligible years
  4. Department and entity breakdown available in report columns
  5. Alert when senior citizen employee's contract end date approaches
  6. Historical flag: months/year each senior citizen was employed for the relevant YA
"""
from datetime import date
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service import (
    is_senior_citizen,
    get_age_as_of,
    get_eligible_ya_range,
    get_senior_citizens_for_company,
    check_senior_citizen_contract_expiry_alerts,
    SENIOR_CITIZEN_AGE,
    ELIGIBLE_YA_START,
    ELIGIBLE_YA_END,
    CONTRACT_EXPIRY_ALERT_DAYS,
)


# ---------------------------------------------------------------------------
# 1. Auto-identification of senior citizen employees (AC-1)
# ---------------------------------------------------------------------------

class TestSeniorCitizenIdentification(FrappeTestCase):
    """Employees aged 60+ are automatically identified based on DOB."""

    def test_is_senior_citizen_exact_60(self):
        """Employee who turned 60 on the reference date is a senior citizen."""
        ref_date = date(2026, 6, 15)
        dob = date(1966, 6, 15)  # Turns 60 exactly on ref_date
        self.assertTrue(is_senior_citizen(dob, ref_date))

    def test_is_senior_citizen_over_60(self):
        """Employee aged 65 on reference date is a senior citizen."""
        ref_date = date(2026, 1, 1)
        dob = date(1960, 6, 1)  # 65 at 2026-01-01
        self.assertTrue(is_senior_citizen(dob, ref_date))

    def test_is_not_senior_citizen_under_60(self):
        """Employee aged 59 on reference date is NOT a senior citizen."""
        ref_date = date(2026, 1, 1)
        dob = date(1967, 1, 2)  # 58 on 2026-01-01
        self.assertFalse(is_senior_citizen(dob, ref_date))

    def test_is_not_senior_citizen_exactly_59(self):
        """Employee who turns 60 the next day is not yet a senior citizen."""
        ref_date = date(2026, 3, 14)
        dob = date(1966, 3, 15)  # Turns 60 the next day
        self.assertFalse(is_senior_citizen(dob, ref_date))

    def test_is_senior_citizen_none_dob_returns_false(self):
        """None DOB does not raise; returns False."""
        self.assertFalse(is_senior_citizen(None, date(2026, 1, 1)))

    def test_is_senior_citizen_string_dob(self):
        """String DOB is parsed and evaluated correctly."""
        self.assertTrue(is_senior_citizen("1960-01-01", date(2026, 1, 1)))

    def test_is_senior_citizen_string_as_of_date(self):
        """String as_of_date is parsed correctly."""
        self.assertTrue(is_senior_citizen(date(1960, 1, 1), "2026-01-01"))

    def test_senior_citizen_threshold_is_60(self):
        """SENIOR_CITIZEN_AGE constant is 60."""
        self.assertEqual(SENIOR_CITIZEN_AGE, 60)

    def test_get_age_as_of_calculation(self):
        """get_age_as_of returns correct integer age."""
        dob = date(1966, 6, 15)
        self.assertEqual(get_age_as_of(dob, date(2026, 6, 15)), 60)
        self.assertEqual(get_age_as_of(dob, date(2026, 6, 14)), 59)

    def test_get_age_as_of_none_dob(self):
        """get_age_as_of returns None for None DOB."""
        self.assertIsNone(get_age_as_of(None, date(2026, 1, 1)))


# ---------------------------------------------------------------------------
# 2. Annual report structure (AC-2, AC-4)
# ---------------------------------------------------------------------------

class TestSeniorCitizenReportColumns(FrappeTestCase):
    """Annual report columns cover wages, department, entity."""

    def test_report_columns_include_total_wages(self):
        """Report must include 'total_wages' column (wages paid as senior citizen)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("total_wages", fieldnames)

    def test_report_columns_include_department(self):
        """Report must include 'department' column for entity/department breakdown."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("department", fieldnames)

    def test_report_columns_include_company(self):
        """Report must include 'company' column for entity breakdown."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("company", fieldnames)

    def test_report_columns_include_months_employed_as_sc(self):
        """Report must include 'months_employed_as_sc' for historical monthly tracking."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("months_employed_as_sc", fieldnames)

    def test_report_columns_include_date_of_birth(self):
        """Report must include DOB to show age-based automatic identification."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("date_of_birth", fieldnames)

    def test_report_total_wages_is_currency_type(self):
        """total_wages column must be of type Currency."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            get_columns,
        )
        cols = get_columns()
        wages_col = next((c for c in cols if c["fieldname"] == "total_wages"), None)
        self.assertIsNotNone(wages_col)
        self.assertEqual(wages_col["fieldtype"], "Currency")


# ---------------------------------------------------------------------------
# 3. YA2026-YA2030 coverage (AC-3)
# ---------------------------------------------------------------------------

class TestEligibleYARange(FrappeTestCase):
    """Report covers exactly YA2026 to YA2030."""

    def test_eligible_ya_start_is_2026(self):
        """ELIGIBLE_YA_START constant must be 2026 (Budget 2026 announcement)."""
        self.assertEqual(ELIGIBLE_YA_START, 2026)

    def test_eligible_ya_end_is_2030(self):
        """ELIGIBLE_YA_END constant must be 2030 (extended per Budget 2026)."""
        self.assertEqual(ELIGIBLE_YA_END, 2030)

    def test_get_eligible_ya_range_returns_all_years(self):
        """get_eligible_ya_range() returns [2026, 2027, 2028, 2029, 2030]."""
        expected = [2026, 2027, 2028, 2029, 2030]
        self.assertEqual(get_eligible_ya_range(), expected)

    def test_report_filters_include_ya_select(self):
        """Report filters must include year_of_assessment as Select field."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            get_filters,
        )
        filters = get_filters()
        ya_filter = next((f for f in filters if f["fieldname"] == "year_of_assessment"), None)
        self.assertIsNotNone(ya_filter)
        self.assertEqual(ya_filter["fieldtype"], "Select")

    def test_report_ya_filter_covers_2026_to_2030(self):
        """Year of assessment filter options must include all years 2026–2030."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            get_filters,
        )
        filters = get_filters()
        ya_filter = next((f for f in filters if f["fieldname"] == "year_of_assessment"), None)
        options_str = ya_filter["options"]
        for year in [2026, 2027, 2028, 2029, 2030]:
            self.assertIn(str(year), options_str)

    def test_report_ya_filter_default_is_2026(self):
        """Year of assessment filter defaults to 2026 (first eligible year)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            get_filters,
        )
        filters = get_filters()
        ya_filter = next((f for f in filters if f["fieldname"] == "year_of_assessment"), None)
        self.assertEqual(ya_filter.get("default"), "2026")


# ---------------------------------------------------------------------------
# 4. Department breakdown (AC-4) — via get_senior_citizens_for_company
# ---------------------------------------------------------------------------

class TestSeniorCitizenServiceData(FrappeTestCase):
    """get_senior_citizens_for_company returns department/entity breakdowns."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service._get_total_wages", return_value=120000.0)
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.get_all")
    def test_returns_department_field(self, mock_get_all, _mock_wages):
        """Each returned record includes a 'department' key."""
        mock_get_all.return_value = [
            {
                "name": "EMP-001",
                "employee_name": "Tan Ah Kow",
                "department": "Accounts",
                "company": "Test Co",
                "date_of_birth": date(1960, 1, 1),  # 66 in 2026
                "date_of_joining": date(2020, 1, 1),
                "relieving_date": None,
                "contract_end_date": None,
                "status": "Active",
            }
        ]

        results = get_senior_citizens_for_company("Test Co", 2026)
        self.assertTrue(len(results) >= 1)
        self.assertIn("department", results[0])
        self.assertEqual(results[0]["department"], "Accounts")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service._get_total_wages", return_value=84000.0)
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.get_all")
    def test_returns_total_wages(self, mock_get_all, _mock_wages):
        """Each returned record includes 'total_wages' from salary slips."""
        mock_get_all.return_value = [
            {
                "name": "EMP-001",
                "employee_name": "Ahmad Senior",
                "department": "HR",
                "company": "Test Co",
                "date_of_birth": date(1963, 3, 1),  # 63 in 2026
                "date_of_joining": date(2018, 6, 1),
                "relieving_date": None,
                "contract_end_date": None,
                "status": "Active",
            }
        ]

        results = get_senior_citizens_for_company("Test Co", 2026)
        self.assertTrue(len(results) >= 1)
        self.assertAlmostEqual(results[0]["total_wages"], 84000.0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.get_all")
    def test_excludes_non_senior_citizen_employees(self, mock_get_all):
        """Employees under 60 during the entire YA are excluded from results."""
        mock_get_all.return_value = [
            {
                "name": "EMP-002",
                "employee_name": "Young Worker",
                "department": "IT",
                "company": "Test Co",
                "date_of_birth": date(1990, 1, 1),  # 36 in 2026
                "date_of_joining": date(2020, 1, 1),
                "relieving_date": None,
                "contract_end_date": None,
                "status": "Active",
            }
        ]
        results = get_senior_citizens_for_company("Test Co", 2026)
        # Should be empty — young worker not 60 in 2026
        self.assertEqual(len(results), 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service._get_total_wages", return_value=60000.0)
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.get_all")
    def test_months_employed_as_sc_is_tracked(self, mock_get_all, _mock_wages):
        """months_employed_as_sc correctly counts months as senior citizen in YA."""
        # Employee turns 60 on 2026-07-01 — senior for 6 months in 2026
        mock_get_all.return_value = [
            {
                "name": "EMP-003",
                "employee_name": "Half Year Senior",
                "department": "Finance",
                "company": "Test Co",
                "date_of_birth": date(1966, 7, 1),  # Turns 60 on 2026-07-01
                "date_of_joining": date(2015, 1, 1),
                "relieving_date": None,
                "contract_end_date": None,
                "status": "Active",
            }
        ]

        results = get_senior_citizens_for_company("Test Co", 2026)
        self.assertEqual(len(results), 1)
        # July to December = 6 months
        self.assertEqual(results[0]["months_employed_as_sc"], 6)


# ---------------------------------------------------------------------------
# 5. Contract end date alert (AC-5)
# ---------------------------------------------------------------------------

class TestSeniorCitizenContractAlert(FrappeTestCase):
    """check_senior_citizen_contract_expiry_alerts creates ToDo for approaching contracts."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.db")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.get_all")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.get_doc")
    def test_creates_todo_for_senior_citizen_contract_expiry(self, mock_get_doc, mock_get_all, mock_db):
        """Creates a ToDo when a senior citizen's contract ends within 90 days."""
        from datetime import timedelta
        today = date.today()
        contract_end = today + timedelta(days=45)

        mock_get_all.side_effect = [
            # First call: employees with contract ending soon
            [
                {
                    "name": "EMP-SC-001",
                    "employee_name": "Pak Aziz",
                    "date_of_birth": date(1960, 1, 1),  # 66+ — senior citizen
                    "contract_end_date": contract_end,
                    "company": "Test Co",
                },
            ],
            # Second call: check existing ToDos
            [],
        ]

        mock_todo_doc = MagicMock()
        mock_get_doc.return_value = mock_todo_doc

        check_senior_citizen_contract_expiry_alerts()

        # A ToDo should have been created
        mock_get_doc.assert_called_once()
        call_args = mock_get_doc.call_args[0][0]
        self.assertEqual(call_args["doctype"], "ToDo")
        self.assertIn("EMP-SC-001", call_args["reference_name"])
        self.assertIn("senior citizen", call_args["description"].lower())
        mock_todo_doc.insert.assert_called_once()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.db")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.get_all")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.get_doc")
    def test_no_todo_for_non_senior_citizen(self, mock_get_doc, mock_get_all, mock_db):
        """Does NOT create a ToDo when contract-expiring employee is under 60."""
        from datetime import timedelta
        today = date.today()
        contract_end = today + timedelta(days=30)

        mock_get_all.return_value = [
            {
                "name": "EMP-YOUNG-001",
                "employee_name": "Young Staff",
                "date_of_birth": date(1990, 6, 1),  # 35 — not senior citizen
                "contract_end_date": contract_end,
                "company": "Test Co",
            },
        ]

        check_senior_citizen_contract_expiry_alerts()

        # No ToDo should be created
        mock_get_doc.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.db")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.get_all")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service.frappe.get_doc")
    def test_no_duplicate_todo(self, mock_get_doc, mock_get_all, mock_db):
        """Does NOT create a duplicate ToDo when one already exists."""
        from datetime import timedelta
        today = date.today()
        contract_end = today + timedelta(days=30)

        mock_get_all.side_effect = [
            # First call: employees
            [
                {
                    "name": "EMP-SC-002",
                    "employee_name": "Mak Cik Rosnah",
                    "date_of_birth": date(1958, 1, 1),
                    "contract_end_date": contract_end,
                    "company": "Test Co",
                },
            ],
            # Second call: existing ToDo found
            [{"name": "TODO-001"}],
        ]

        check_senior_citizen_contract_expiry_alerts()

        # No new ToDo should be created
        mock_get_doc.assert_not_called()

    def test_contract_expiry_alert_threshold_is_90_days(self):
        """CONTRACT_EXPIRY_ALERT_DAYS constant must be 90 days."""
        self.assertEqual(CONTRACT_EXPIRY_ALERT_DAYS, 90)


# ---------------------------------------------------------------------------
# 6. Report execute() returns correct structure (AC-1, AC-2, AC-6)
# ---------------------------------------------------------------------------

class TestSeniorCitizenReportExecute(FrappeTestCase):
    """Report execute() returns columns and data correctly."""

    def test_report_execute_returns_tuple(self):
        """execute() with empty filters returns (columns, data) tuple without error."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            execute,
        )
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction.get_senior_citizens_for_company",
            return_value=[],
        ):
            result = execute({"company": "Test Co", "year_of_assessment": "2026"})
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        columns, data = result
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction.get_senior_citizens_for_company")
    def test_report_passes_ya_to_service(self, mock_service):
        """execute() passes year_of_assessment to get_senior_citizens_for_company."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            execute,
        )
        mock_service.return_value = []
        execute({"company": "Prisma Tech", "year_of_assessment": "2028"})
        mock_service.assert_called_once_with("Prisma Tech", 2028)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction.get_senior_citizens_for_company")
    def test_report_department_filter_applied(self, mock_service):
        """Department filter narrows results to matching department only."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.senior_citizen_deduction.senior_citizen_deduction import (
            execute,
        )
        mock_service.return_value = [
            {"employee": "EMP-001", "employee_name": "A", "department": "HR",
             "company": "C", "date_of_birth": date(1960, 1, 1), "age_at_ya_start": 66,
             "turns_60_date": date(2020, 1, 1), "date_of_joining": date(2015, 1, 1),
             "contract_end_date": None, "months_employed_as_sc": 12, "total_wages": 60000.0},
            {"employee": "EMP-002", "employee_name": "B", "department": "Finance",
             "company": "C", "date_of_birth": date(1962, 3, 1), "age_at_ya_start": 64,
             "turns_60_date": date(2022, 3, 1), "date_of_joining": date(2010, 1, 1),
             "contract_end_date": None, "months_employed_as_sc": 12, "total_wages": 72000.0},
        ]
        _cols, data = execute({"company": "C", "year_of_assessment": "2026", "department": "HR"})
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["department"], "HR")
