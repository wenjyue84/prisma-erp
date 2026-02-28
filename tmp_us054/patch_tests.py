"""Patch test_pcb_calculator.py to add CP38 tests (US-054)."""
import sys

with open(sys.argv[1]) as f:
    content = f.read()

# Update import to include get_cp38_amount
old_import = """from lhdn_payroll_integration.services.pcb_calculator import (
    calculate_pcb,
    validate_pcb_amount,
    _compute_tax_on_chargeable_income,
)"""

new_import = """from lhdn_payroll_integration.services.pcb_calculator import (
    calculate_pcb,
    get_cp38_amount,
    validate_pcb_amount,
    _compute_tax_on_chargeable_income,
)"""

if old_import not in content:
    print("ERROR: import block not found!")
    sys.exit(1)

content = content.replace(old_import, new_import, 1)

# Append CP38 test classes
cp38_tests = '''

# ---------------------------------------------------------------------------
# US-054: CP38 Additional Deduction Tests
# ---------------------------------------------------------------------------

class TestGetCp38Amount(FrappeTestCase):
    """Tests for get_cp38_amount() function (US-054 — ITA s.107(1)(b))."""

    def test_cp38_active_notice_returns_amount(self):
        """Returns CP38 amount when expiry is in the future."""
        from datetime import date, timedelta

        future_date = (date.today() + timedelta(days=30)).isoformat()
        mock_employee = MagicMock()
        mock_employee.custom_cp38_amount = 500.0
        mock_employee.custom_cp38_expiry = future_date

        with patch("frappe.get_doc", return_value=mock_employee):
            result = get_cp38_amount("EMP-CP38-001")
        self.assertEqual(result, 500.0)

    def test_cp38_expired_notice_returns_zero(self):
        """Returns 0.0 when expiry date is in the past (notice expired)."""
        from datetime import date, timedelta

        past_date = (date.today() - timedelta(days=1)).isoformat()
        mock_employee = MagicMock()
        mock_employee.custom_cp38_amount = 500.0
        mock_employee.custom_cp38_expiry = past_date

        with patch("frappe.get_doc", return_value=mock_employee):
            result = get_cp38_amount("EMP-CP38-002")
        self.assertEqual(result, 0.0)

    def test_cp38_expiry_today_is_active(self):
        """Returns amount when expiry equals today (boundary — still active)."""
        from datetime import date

        today = date.today().isoformat()
        mock_employee = MagicMock()
        mock_employee.custom_cp38_amount = 200.0
        mock_employee.custom_cp38_expiry = today

        with patch("frappe.get_doc", return_value=mock_employee):
            result = get_cp38_amount("EMP-CP38-003")
        self.assertEqual(result, 200.0)

    def test_cp38_no_expiry_returns_zero(self):
        """Returns 0.0 when expiry field is None/not set."""
        mock_employee = MagicMock()
        mock_employee.custom_cp38_amount = 500.0
        mock_employee.custom_cp38_expiry = None

        with patch("frappe.get_doc", return_value=mock_employee):
            result = get_cp38_amount("EMP-CP38-004")
        self.assertEqual(result, 0.0)

    def test_cp38_zero_amount_returns_zero(self):
        """Returns 0.0 when CP38 amount is 0 even if expiry is in the future."""
        from datetime import date, timedelta

        future_date = (date.today() + timedelta(days=30)).isoformat()
        mock_employee = MagicMock()
        mock_employee.custom_cp38_amount = 0
        mock_employee.custom_cp38_expiry = future_date

        with patch("frappe.get_doc", return_value=mock_employee):
            result = get_cp38_amount("EMP-CP38-005")
        self.assertEqual(result, 0.0)

    def test_cp38_exception_returns_zero(self):
        """Returns 0.0 safely when frappe.get_doc raises (employee not found)."""
        with patch("frappe.get_doc", side_effect=Exception("DoesNotExist")):
            result = get_cp38_amount("EMP-NOTFOUND")
        self.assertEqual(result, 0.0)


class TestCp39ReportColumns(FrappeTestCase):
    """Tests for CP39 report CP38 column (US-054)."""

    def test_cp39_has_cp38_column(self):
        """CP39 report get_columns() must include cp38_amount column."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance.cp39_pcb_remittance import (
            get_columns,
        )
        columns = get_columns()
        fieldnames = [c["fieldname"] for c in columns if isinstance(c, dict)]
        self.assertIn(
            "cp38_amount",
            fieldnames,
            "CP39 report must have cp38_amount column (US-054)",
        )

    def test_cp39_cp38_column_is_currency(self):
        """CP38 column in CP39 report must be Currency type."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance.cp39_pcb_remittance import (
            get_columns,
        )
        columns = get_columns()
        cp38_col = next((c for c in columns if c.get("fieldname") == "cp38_amount"), None)
        self.assertIsNotNone(cp38_col, "cp38_amount column not found")
        self.assertEqual(cp38_col.get("fieldtype"), "Currency")


class TestBorangECp38Column(FrappeTestCase):
    """Tests for Borang E CP38 total column (US-054)."""

    def test_borang_e_has_total_cp38_column(self):
        """Borang E get_columns() must include total_cp38 column."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e import (
            get_columns,
        )
        columns = get_columns()
        fieldnames = [c["fieldname"] for c in columns if isinstance(c, dict)]
        self.assertIn(
            "total_cp38",
            fieldnames,
            "Borang E must have total_cp38 column (US-054)",
        )

    def test_borang_e_total_cp38_is_currency(self):
        """total_cp38 column in Borang E must be Currency type."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e import (
            get_columns,
        )
        columns = get_columns()
        cp38_col = next((c for c in columns if c.get("fieldname") == "total_cp38"), None)
        self.assertIsNotNone(cp38_col, "total_cp38 column not found in Borang E")
        self.assertEqual(cp38_col.get("fieldtype"), "Currency")
'''

content = content + cp38_tests

with open(sys.argv[2], 'w') as f:
    f.write(content)

print("Test file patched successfully")
