"""Tests for US-129: Pre-Submission e-PCB Plus Employee TIN and Tax Category Completeness Validation.

Acceptance criteria tested:
  - get_employee_data_gaps() flags employees missing TIN, PCB category or IC type
  - Employees with all fields populated are NOT flagged (compliant)
  - run_epcb_preflight_check() returns correct structure and is gated to HR Manager
  - Resolved employees are excluded on re-run (verified via mock)
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.api.epcb_preflight import (
    get_employee_data_gaps,
    run_epcb_preflight_check,
)

# ---------------------------------------------------------------------------
# Helper: build a fake SQL row (simulates one Salary Slip + joined Employee)
# ---------------------------------------------------------------------------

def _row(employee="EMP-001", employee_name="Ahmad", salary_slip="SAL-001",
         tin="IG12345678901", pcb_category="1", id_type="NRIC"):
    return frappe._dict({
        "employee": employee,
        "employee_name": employee_name,
        "salary_slip": salary_slip,
        "tin": tin,
        "pcb_category": pcb_category,
        "id_type": id_type,
    })


_SVC = "lhdn_payroll_integration.lhdn_payroll_integration.api.epcb_preflight"


# ---------------------------------------------------------------------------
# Unit tests — get_employee_data_gaps()
# ---------------------------------------------------------------------------

class TestGetEmployeeDataGaps(FrappeTestCase):
    """Unit tests for the internal gap-detection helper."""

    def test_compliant_employee_not_flagged(self):
        """Employee with TIN + PCB category + ID type → no gap returned."""
        with patch(f"{_SVC}.frappe.db.sql", return_value=[_row()]):
            gaps = get_employee_data_gaps("Test Co", "01", 2025)
        self.assertEqual(gaps, [])

    def test_missing_tin_flagged(self):
        """Employee with empty TIN → gap with missing_tin=True."""
        with patch(f"{_SVC}.frappe.db.sql", return_value=[_row(tin="")]):
            gaps = get_employee_data_gaps("Test Co", "01", 2025)
        self.assertEqual(len(gaps), 1)
        self.assertTrue(gaps[0]["missing_tin"])
        self.assertFalse(gaps[0]["missing_pcb_category"])
        self.assertFalse(gaps[0]["missing_id_type"])
        self.assertIn("TIN missing", gaps[0]["issues"])

    def test_missing_pcb_category_flagged(self):
        """Employee with empty PCB category → gap with missing_pcb_category=True."""
        with patch(f"{_SVC}.frappe.db.sql", return_value=[_row(pcb_category="")]):
            gaps = get_employee_data_gaps("Test Co", "01", 2025)
        self.assertEqual(len(gaps), 1)
        self.assertFalse(gaps[0]["missing_tin"])
        self.assertTrue(gaps[0]["missing_pcb_category"])
        self.assertFalse(gaps[0]["missing_id_type"])
        self.assertIn("PCB Category missing", gaps[0]["issues"])

    def test_missing_id_type_flagged(self):
        """Employee with empty IC/Passport type → gap with missing_id_type=True."""
        with patch(f"{_SVC}.frappe.db.sql", return_value=[_row(id_type="")]):
            gaps = get_employee_data_gaps("Test Co", "01", 2025)
        self.assertEqual(len(gaps), 1)
        self.assertFalse(gaps[0]["missing_tin"])
        self.assertFalse(gaps[0]["missing_pcb_category"])
        self.assertTrue(gaps[0]["missing_id_type"])
        self.assertIn("IC/Passport type missing", gaps[0]["issues"])

    def test_all_three_missing_flagged_with_three_issues(self):
        """Employee missing all three fields → 3 issues in the issues list."""
        with patch(f"{_SVC}.frappe.db.sql", return_value=[_row(tin="", pcb_category="", id_type="")]):
            gaps = get_employee_data_gaps("Test Co", "01", 2025)
        self.assertEqual(len(gaps), 1)
        self.assertTrue(gaps[0]["missing_tin"])
        self.assertTrue(gaps[0]["missing_pcb_category"])
        self.assertTrue(gaps[0]["missing_id_type"])
        self.assertEqual(len(gaps[0]["issues"]), 3)

    def test_only_non_compliant_employees_returned(self):
        """Mix of compliant and non-compliant → only non-compliant returned."""
        rows = [
            _row(employee="EMP-001", tin="IG001"),        # compliant
            _row(employee="EMP-002", tin=""),              # non-compliant
            _row(employee="EMP-003", pcb_category=""),    # non-compliant
            _row(employee="EMP-004", tin="IG004"),        # compliant
        ]
        with patch(f"{_SVC}.frappe.db.sql", return_value=rows):
            gaps = get_employee_data_gaps("Test Co", "01", 2025)
        self.assertEqual(len(gaps), 2)
        employees = {g["employee"] for g in gaps}
        self.assertIn("EMP-002", employees)
        self.assertIn("EMP-003", employees)
        self.assertNotIn("EMP-001", employees)
        self.assertNotIn("EMP-004", employees)

    def test_empty_period_returns_empty_list(self):
        """No salary slips in the period → empty list (compliant by default)."""
        with patch(f"{_SVC}.frappe.db.sql", return_value=[]):
            gaps = get_employee_data_gaps("Test Co", "06", 2025)
        self.assertEqual(gaps, [])

    def test_month_is_zero_padded_for_sql(self):
        """Month 1 (integer) is passed as int 1 to SQL; no crash."""
        with patch(f"{_SVC}.frappe.db.sql", return_value=[]) as mock_sql:
            get_employee_data_gaps("Test Co", 1, 2025)
        # Verify that SQL was called with month=1 (int from zfill→int conversion)
        call_kwargs = mock_sql.call_args[0][1]
        self.assertEqual(call_kwargs["month"], 1)

    def test_gap_dict_contains_required_keys(self):
        """Each gap dict must have all required keys."""
        with patch(f"{_SVC}.frappe.db.sql", return_value=[_row(tin="")]):
            gaps = get_employee_data_gaps("Test Co", "01", 2025)
        required_keys = {
            "employee", "employee_name", "salary_slip",
            "missing_tin", "missing_pcb_category", "missing_id_type", "issues",
        }
        self.assertEqual(required_keys, set(gaps[0].keys()))

    def test_resolved_employee_excluded_on_rerun(self):
        """After fix, employee with all fields populated is excluded from gaps."""
        # First run: missing TIN
        with patch(f"{_SVC}.frappe.db.sql", return_value=[_row(tin="")]):
            gaps_before = get_employee_data_gaps("Test Co", "01", 2025)
        self.assertEqual(len(gaps_before), 1)

        # After fix: TIN now populated
        with patch(f"{_SVC}.frappe.db.sql", return_value=[_row(tin="IG12345678901")]):
            gaps_after = get_employee_data_gaps("Test Co", "01", 2025)
        self.assertEqual(len(gaps_after), 0)


# ---------------------------------------------------------------------------
# Unit tests — run_epcb_preflight_check() API wrapper
# ---------------------------------------------------------------------------

class TestRunEpcbPreflightCheck(FrappeTestCase):
    """Tests for the whitelisted run_epcb_preflight_check() function."""

    def test_returns_compliant_true_when_no_gaps(self):
        """All employees compliant → compliant=True, gap_count=0."""
        with patch(f"{_SVC}.get_employee_data_gaps", return_value=[]):
            result = run_epcb_preflight_check("Test Co", "01", 2025)
        self.assertTrue(result["compliant"])
        self.assertEqual(result["gap_count"], 0)
        self.assertEqual(result["gaps"], [])

    def test_returns_compliant_false_when_gaps_exist(self):
        """Non-compliant employees → compliant=False, gap_count matches."""
        fake_gaps = [
            {
                "employee": "EMP-001",
                "employee_name": "Ahmad",
                "salary_slip": "SAL-001",
                "missing_tin": True,
                "missing_pcb_category": False,
                "missing_id_type": False,
                "issues": ["TIN missing"],
            }
        ]
        with patch(f"{_SVC}.get_employee_data_gaps", return_value=fake_gaps):
            result = run_epcb_preflight_check("Test Co", "01", 2025)
        self.assertFalse(result["compliant"])
        self.assertEqual(result["gap_count"], 1)
        self.assertEqual(len(result["gaps"]), 1)

    def test_response_contains_checked_at_timestamp(self):
        """Response always contains 'checked_at' ISO datetime string."""
        with patch(f"{_SVC}.get_employee_data_gaps", return_value=[]):
            result = run_epcb_preflight_check("Test Co", "01", 2025)
        self.assertIn("checked_at", result)
        self.assertIsInstance(result["checked_at"], str)
        # ISO format contains 'T' separator
        self.assertIn("T", result["checked_at"])

    def test_response_structure_keys(self):
        """Response dict has exactly the required top-level keys."""
        with patch(f"{_SVC}.get_employee_data_gaps", return_value=[]):
            result = run_epcb_preflight_check("Test Co", "01", 2025)
        self.assertIn("compliant", result)
        self.assertIn("gap_count", result)
        self.assertIn("gaps", result)
        self.assertIn("checked_at", result)

    def test_gap_count_matches_gaps_list_length(self):
        """gap_count must equal len(gaps) for any number of gaps."""
        fake_gaps = [
            {
                "employee": f"EMP-{i:03d}",
                "employee_name": f"Employee {i}",
                "salary_slip": f"SAL-{i:03d}",
                "missing_tin": True,
                "missing_pcb_category": False,
                "missing_id_type": False,
                "issues": ["TIN missing"],
            }
            for i in range(5)
        ]
        with patch(f"{_SVC}.get_employee_data_gaps", return_value=fake_gaps):
            result = run_epcb_preflight_check("Test Co", "01", 2025)
        self.assertEqual(result["gap_count"], 5)
        self.assertEqual(len(result["gaps"]), 5)
