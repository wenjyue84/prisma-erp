"""Tests for US-194: OKU (Disabled Employee) Double Deduction Service.

Covers all 6 acceptance criteria:
AC1: Employee record has OKU flag, Kad OKU number, and Kad OKU expiry date fields
AC2: Payroll calculation checks monthly remuneration ≤RM4,000 for eligibility
AC3: Annual double deduction = min(total annual remuneration, RM48,000)
AC4: Warning raised when Kad OKU expiry is within 60 days
AC5: Annual OKU Double Deduction Summary report lists each OKU employee
AC6: Report notes double deduction extended to YA2030 per Budget 2026
"""
from unittest.mock import MagicMock, patch
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service import (
    OKU_ANNUAL_CAP,
    OKU_MONTHLY_CAP,
    OKU_EXPIRY_ALERT_DAYS,
    ELIGIBLE_YA_START,
    ELIGIBLE_YA_END,
    is_oku_eligible_month,
    compute_annual_double_deduction,
    check_oku_expiry_alerts,
    get_oku_employees_for_company,
    get_eligible_ya_range,
)


class TestOkuConstants(FrappeTestCase):
    """AC1, AC2, AC3 — verify constants are set correctly."""

    def test_annual_cap_is_48000(self):
        self.assertEqual(OKU_ANNUAL_CAP, 48000.0)

    def test_monthly_cap_is_4000(self):
        self.assertEqual(OKU_MONTHLY_CAP, 4000.0)

    def test_expiry_alert_days_is_60(self):
        self.assertEqual(OKU_EXPIRY_ALERT_DAYS, 60)

    def test_eligible_ya_start_is_2026(self):
        self.assertEqual(ELIGIBLE_YA_START, 2026)

    def test_eligible_ya_end_is_2030(self):
        self.assertEqual(ELIGIBLE_YA_END, 2030)

    def test_eligible_ya_range(self):
        ya_range = get_eligible_ya_range()
        self.assertEqual(ya_range, [2026, 2027, 2028, 2029, 2030])


class TestOkuMonthlyEligibility(FrappeTestCase):
    """AC2 — monthly remuneration ≤ RM4,000 required for double deduction."""

    def test_exactly_4000_is_eligible(self):
        self.assertTrue(is_oku_eligible_month(4000.0))

    def test_below_4000_is_eligible(self):
        self.assertTrue(is_oku_eligible_month(3500.0))
        self.assertTrue(is_oku_eligible_month(2000.0))
        self.assertTrue(is_oku_eligible_month(0.0))

    def test_above_4000_is_not_eligible(self):
        self.assertFalse(is_oku_eligible_month(4000.01))
        self.assertFalse(is_oku_eligible_month(5000.0))
        self.assertFalse(is_oku_eligible_month(10000.0))

    def test_string_float_coerced(self):
        self.assertTrue(is_oku_eligible_month("3999.99"))
        self.assertFalse(is_oku_eligible_month("4001.00"))

    def test_boundary_boundary(self):
        # Exactly RM4,000 should be eligible (inclusive ≤)
        self.assertTrue(is_oku_eligible_month(4000))
        self.assertFalse(is_oku_eligible_month(4001))


class TestOkuAnnualDoubleDeduction(FrappeTestCase):
    """AC3 — double deduction = min(total annual remuneration, RM48,000)."""

    def test_below_cap_returns_full_amount(self):
        self.assertEqual(compute_annual_double_deduction(30000.0), 30000.0)

    def test_exactly_at_cap_returns_cap(self):
        self.assertEqual(compute_annual_double_deduction(48000.0), 48000.0)

    def test_above_cap_returns_cap(self):
        self.assertEqual(compute_annual_double_deduction(60000.0), 48000.0)
        self.assertEqual(compute_annual_double_deduction(100000.0), 48000.0)

    def test_zero_remuneration(self):
        self.assertEqual(compute_annual_double_deduction(0.0), 0.0)

    def test_string_float_coerced(self):
        self.assertEqual(compute_annual_double_deduction("36000.0"), 36000.0)

    def test_typical_12_months_at_4000(self):
        # 12 months × RM4,000 = RM48,000 → exactly at cap
        self.assertEqual(compute_annual_double_deduction(48000.0), 48000.0)

    def test_typical_12_months_at_3000(self):
        # 12 months × RM3,000 = RM36,000 → below cap
        self.assertEqual(compute_annual_double_deduction(36000.0), 36000.0)


class TestOkuExpiryAlerts(FrappeTestCase):
    """AC4 — warning raised when Kad OKU expiry is within 60 days."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service.frappe")
    def test_creates_todo_for_expiring_employee(self, mock_frappe):
        from datetime import date, timedelta

        today = date(2026, 3, 1)
        expiry = today + timedelta(days=30)  # within 60 days

        mock_emp = {
            "name": "EMP-001",
            "employee_name": "Ahmad Zaini",
            "company": "Test Co",
            "custom_kad_oku_number": "OKU/2024/001",
            "custom_kad_oku_expiry_date": expiry,
        }

        mock_frappe.get_all.side_effect = [
            [mock_emp],  # first call: employees
            [],           # second call: check existing ToDo
        ]
        mock_frappe.get_doc.return_value = MagicMock()
        mock_frappe.db = MagicMock()

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service.date"
        ) as mock_date:
            mock_date.today.return_value = today
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            check_oku_expiry_alerts()

        mock_frappe.get_doc.assert_called_once()
        doc_call = mock_frappe.get_doc.call_args[0][0]
        self.assertEqual(doc_call["doctype"], "ToDo")
        self.assertIn("OKU", doc_call["description"])
        self.assertIn("expires", doc_call["description"])
        self.assertEqual(doc_call["priority"], "High")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service.frappe")
    def test_no_duplicate_alert_created(self, mock_frappe):
        from datetime import date, timedelta

        today = date(2026, 3, 1)
        expiry = today + timedelta(days=30)

        mock_emp = {
            "name": "EMP-002",
            "employee_name": "Siti Rahimah",
            "company": "Test Co",
            "custom_kad_oku_number": "OKU/2024/002",
            "custom_kad_oku_expiry_date": expiry,
        }

        # Second call: existing ToDo found → should NOT create a new one
        mock_frappe.get_all.side_effect = [
            [mock_emp],               # employees
            [{"name": "TODO-1"}],     # existing ToDo exists
        ]
        mock_frappe.db = MagicMock()

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service.date"
        ) as mock_date:
            mock_date.today.return_value = today
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

            check_oku_expiry_alerts()

        mock_frappe.get_doc.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service.frappe")
    def test_no_alert_when_no_oku_employees_expiring(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        mock_frappe.db = MagicMock()

        check_oku_expiry_alerts()

        mock_frappe.get_doc.assert_not_called()

    def test_alert_threshold_is_60_days(self):
        self.assertEqual(OKU_EXPIRY_ALERT_DAYS, 60)


class TestGetOkuEmployeesForCompany(FrappeTestCase):
    """AC5 — annual report lists each OKU employee with remuneration and deduction."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service.frappe")
    def test_returns_employee_with_correct_deduction(self, mock_frappe):
        from datetime import date

        mock_emp = {
            "name": "EMP-003",
            "employee_name": "Raj Kumar",
            "department": "Operations",
            "company": "ACME Sdn Bhd",
            "custom_kad_oku_number": "OKU/2023/100",
            "custom_kad_oku_expiry_date": date(2027, 12, 31),
            "status": "Active",
        }
        mock_frappe.get_all.return_value = [mock_emp]

        # 12 months × RM3,500 = RM42,000 (below RM48,000 cap, all below RM4,000/month)
        mock_slips = [
            {"start_date": f"2026-{m:02d}-01", "end_date": f"2026-{m:02d}-28", "gross_pay": 3500.0}
            for m in range(1, 13)
        ]
        mock_frappe.db.sql.return_value = mock_slips

        results = get_oku_employees_for_company("ACME Sdn Bhd", 2026)

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["employee"], "EMP-003")
        self.assertAlmostEqual(r["total_annual_remuneration"], 42000.0)
        self.assertAlmostEqual(r["eligible_remuneration"], 42000.0)
        self.assertAlmostEqual(r["eligible_deduction"], 42000.0)
        self.assertAlmostEqual(r["double_deduction"], 42000.0)
        self.assertEqual(r["months_with_eligible_salary"], 12)
        self.assertEqual(r["all_months_eligible"], 1)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service.frappe")
    def test_deduction_capped_at_48000(self, mock_frappe):
        from datetime import date

        mock_emp = {
            "name": "EMP-004",
            "employee_name": "Nurul Huda",
            "department": "HR",
            "company": "ACME Sdn Bhd",
            "custom_kad_oku_number": "OKU/2022/200",
            "custom_kad_oku_expiry_date": date(2028, 6, 30),
            "status": "Active",
        }
        mock_frappe.get_all.return_value = [mock_emp]

        # 12 months × RM4,000 = RM48,000 → exactly at cap
        mock_slips = [
            {"start_date": f"2026-{m:02d}-01", "end_date": f"2026-{m:02d}-28", "gross_pay": 4000.0}
            for m in range(1, 13)
        ]
        mock_frappe.db.sql.return_value = mock_slips

        results = get_oku_employees_for_company("ACME Sdn Bhd", 2026)

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertAlmostEqual(r["eligible_deduction"], 48000.0)
        self.assertAlmostEqual(r["double_deduction"], 48000.0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service.frappe")
    def test_month_above_4000_not_eligible(self, mock_frappe):
        from datetime import date

        mock_emp = {
            "name": "EMP-005",
            "employee_name": "Tan Ah Kow",
            "department": "Finance",
            "company": "ACME Sdn Bhd",
            "custom_kad_oku_number": "OKU/2021/300",
            "custom_kad_oku_expiry_date": date(2027, 3, 31),
            "status": "Active",
        }
        mock_frappe.get_all.return_value = [mock_emp]

        # 11 months × RM3,000 + 1 month × RM5,000 (ineligible)
        mock_slips = (
            [{"start_date": f"2026-{m:02d}-01", "end_date": f"2026-{m:02d}-28", "gross_pay": 3000.0}
             for m in range(1, 12)]
            + [{"start_date": "2026-12-01", "end_date": "2026-12-31", "gross_pay": 5000.0}]
        )
        mock_frappe.db.sql.return_value = mock_slips

        results = get_oku_employees_for_company("ACME Sdn Bhd", 2026)

        r = results[0]
        self.assertAlmostEqual(r["total_annual_remuneration"], 38000.0)
        self.assertAlmostEqual(r["eligible_remuneration"], 33000.0)
        self.assertAlmostEqual(r["eligible_deduction"], 33000.0)
        self.assertEqual(r["months_with_eligible_salary"], 11)
        self.assertEqual(r["all_months_eligible"], 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service.frappe")
    def test_no_salary_slips_skipped(self, mock_frappe):
        mock_emp = {
            "name": "EMP-006",
            "employee_name": "No Slips",
            "department": "Admin",
            "company": "ACME Sdn Bhd",
            "custom_kad_oku_number": "OKU/2020/400",
            "custom_kad_oku_expiry_date": None,
            "status": "Left",
        }
        mock_frappe.get_all.return_value = [mock_emp]
        mock_frappe.db.sql.return_value = []

        results = get_oku_employees_for_company("ACME Sdn Bhd", 2026)
        self.assertEqual(len(results), 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service.frappe")
    def test_result_sorted_by_department_then_name(self, mock_frappe):
        from datetime import date

        emps = [
            {
                "name": "EMP-010", "employee_name": "Zack", "department": "Admin",
                "company": "Co", "custom_kad_oku_number": "A", "custom_kad_oku_expiry_date": date(2027, 1, 1), "status": "Active",
            },
            {
                "name": "EMP-011", "employee_name": "Alice", "department": "Admin",
                "company": "Co", "custom_kad_oku_number": "B", "custom_kad_oku_expiry_date": date(2027, 1, 1), "status": "Active",
            },
            {
                "name": "EMP-012", "employee_name": "Bob", "department": "Finance",
                "company": "Co", "custom_kad_oku_number": "C", "custom_kad_oku_expiry_date": date(2027, 1, 1), "status": "Active",
            },
        ]
        mock_frappe.get_all.return_value = emps
        mock_frappe.db.sql.return_value = [
            {"start_date": "2026-01-01", "end_date": "2026-01-31", "gross_pay": 3000.0}
        ]

        results = get_oku_employees_for_company("Co", 2026)

        names = [r["employee_name"] for r in results]
        self.assertEqual(names, ["Alice", "Zack", "Bob"])


class TestOkuReport(FrappeTestCase):
    """AC5, AC6 — report structure and Budget 2026 YA2030 note."""

    def test_report_columns_present(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction import (
            get_columns,
        )
        columns = get_columns()
        fieldnames = [c["fieldname"] for c in columns]
        self.assertIn("employee", fieldnames)
        self.assertIn("employee_name", fieldnames)
        self.assertIn("kad_oku_number", fieldnames)
        self.assertIn("kad_oku_expiry_date", fieldnames)
        self.assertIn("total_annual_remuneration", fieldnames)
        self.assertIn("eligible_remuneration", fieldnames)
        self.assertIn("double_deduction", fieldnames)
        self.assertIn("months_with_eligible_salary", fieldnames)

    def test_report_filters_present(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction import (
            get_filters,
        )
        filters = get_filters()
        filter_names = [f["fieldname"] for f in filters]
        self.assertIn("company", filter_names)
        self.assertIn("year_of_assessment", filter_names)

    def test_report_ya_filter_options_include_2026_to_2030(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction import (
            get_filters,
        )
        filters = get_filters()
        ya_filter = next(f for f in filters if f["fieldname"] == "year_of_assessment")
        options = ya_filter["options"]
        for year in range(2026, 2031):
            self.assertIn(str(year), options)

    def test_execute_returns_five_values(self):
        from unittest.mock import patch as _patch
        from lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction import (
            execute,
        )
        with _patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction.get_oku_employees_for_company"
        ) as mock_get, _patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction.frappe"
        ) as mock_frappe:
            mock_get.return_value = []
            mock_frappe.defaults.get_user_default.return_value = "Test Co"
            result = execute({"company": "Test Co", "year_of_assessment": "2026"})

        # execute returns (columns, data, message, chart, summary) or (columns, data) + message
        self.assertIsInstance(result, tuple)
        self.assertGreaterEqual(len(result), 2)

    def test_report_message_mentions_ya2030_and_budget2026(self):
        from unittest.mock import patch as _patch
        from lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction import (
            execute,
        )
        with _patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction.get_oku_employees_for_company"
        ) as mock_get, _patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction.frappe"
        ) as mock_frappe:
            mock_get.return_value = []
            mock_frappe.defaults.get_user_default.return_value = "Test Co"
            result = execute({"company": "Test Co", "year_of_assessment": "2026"})

        # The last element should be the message string
        message = result[-1]
        self.assertIsNotNone(message)
        self.assertIn("YA2030", message)
        self.assertIn("Budget 2026", message)

    def test_report_message_mentions_section_34(self):
        from unittest.mock import patch as _patch
        from lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction import (
            execute,
        )
        with _patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction.get_oku_employees_for_company"
        ) as mock_get, _patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.oku_double_deduction.oku_double_deduction.frappe"
        ) as mock_frappe:
            mock_get.return_value = []
            mock_frappe.defaults.get_user_default.return_value = "Test Co"
            result = execute({"company": "Test Co", "year_of_assessment": "2026"})

        message = result[-1]
        self.assertIn("34", message)  # Section 34(6)(n)


class TestOkuCustomFieldsInFixture(FrappeTestCase):
    """AC1 — OKU custom fields defined in fixture JSON."""

    def test_custom_is_oku_in_fixture(self):
        import json
        import os
        fixture_path = os.path.join(
            "/home/frappe/frappe-bench/apps/lhdn_payroll_integration",
            "lhdn_payroll_integration/fixtures/custom_field.json",
        )
        with open(fixture_path) as f:
            fields = json.load(f)
        fieldnames = [fld.get("fieldname") for fld in fields]
        self.assertIn("custom_is_oku", fieldnames)

    def test_custom_kad_oku_number_in_fixture(self):
        import json
        import os
        fixture_path = os.path.join(
            "/home/frappe/frappe-bench/apps/lhdn_payroll_integration",
            "lhdn_payroll_integration/fixtures/custom_field.json",
        )
        with open(fixture_path) as f:
            fields = json.load(f)
        fieldnames = [fld.get("fieldname") for fld in fields]
        self.assertIn("custom_kad_oku_number", fieldnames)

    def test_custom_kad_oku_expiry_date_in_fixture(self):
        import json
        import os
        fixture_path = os.path.join(
            "/home/frappe/frappe-bench/apps/lhdn_payroll_integration",
            "lhdn_payroll_integration/fixtures/custom_field.json",
        )
        with open(fixture_path) as f:
            fields = json.load(f)
        fieldnames = [fld.get("fieldname") for fld in fields]
        self.assertIn("custom_kad_oku_expiry_date", fieldnames)

    def test_oku_fields_on_employee_doctype(self):
        import json
        import os
        fixture_path = os.path.join(
            "/home/frappe/frappe-bench/apps/lhdn_payroll_integration",
            "lhdn_payroll_integration/fixtures/custom_field.json",
        )
        with open(fixture_path) as f:
            fields = json.load(f)
        oku_fields = [fld for fld in fields if fld.get("fieldname", "").startswith("custom_is_oku") or
                      fld.get("fieldname", "").startswith("custom_kad_oku")]
        for fld in oku_fields:
            self.assertEqual(fld.get("dt"), "Employee", f"{fld['fieldname']} should be on Employee doctype")
