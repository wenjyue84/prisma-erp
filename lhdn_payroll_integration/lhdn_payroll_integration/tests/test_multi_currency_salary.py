"""Tests for US-111: Multi-Currency Salary Conversion for Expatriate PCB Base Calculation.

LHDN PCB Spec: All employment income is reported in RM.
Foreign-currency income is converted at the exchange rate prevailing on the date
of payment (Bank Negara Malaysia middle rate) per ITA 1967 Section 13.

Coverage:
    TestGetExchangeRate          — currency_converter.get_exchange_rate()
    TestGetGrossMyrForSlip       — currency_converter.get_gross_myr_for_slip()
    TestApplyMyrConversion       — currency_converter.apply_myr_conversion() (validate hook)
    TestPcbUsesGrossMyr          — PCB calculation uses MYR-equivalent gross for non-MYR slips
    TestCp39GrossRemuneration    — CP39 uses custom_gross_myr via COALESCE
    TestEaFormExchangeRate       — EA form earnings multiplied by exchange rate
"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.currency_converter import (
    apply_myr_conversion,
    get_exchange_rate,
    get_gross_myr_for_slip,
)


# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------

def _make_slip(gross_pay, currency="MYR", exchange_rate=None, gross_myr=None):
    """Build a minimal Salary Slip mock for testing."""
    slip = MagicMock()
    slip.gross_pay = gross_pay
    slip.custom_salary_currency = currency
    slip.custom_exchange_rate_to_myr = exchange_rate if exchange_rate is not None else (1.0 if currency == "MYR" else 0)
    slip.custom_gross_myr = gross_myr
    slip.posting_date = "2025-01-31"
    slip.start_date = "2025-01-01"
    return slip


# ---------------------------------------------------------------------------
# 1. get_exchange_rate
# ---------------------------------------------------------------------------

class TestGetExchangeRate(FrappeTestCase):
    """get_exchange_rate() fetches from Currency Exchange or returns 1.0."""

    def test_same_currency_returns_one(self):
        """MYR-to-MYR conversion is always 1.0, no DB query needed."""
        result = get_exchange_rate("MYR", "MYR", "2025-01-31")
        self.assertEqual(result, 1.0)

    def test_no_currency_returns_one(self):
        """Empty/None from_currency defaults to 1.0."""
        result = get_exchange_rate(None, "MYR")
        self.assertEqual(result, 1.0)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.currency_converter.frappe.db.sql"
    )
    def test_fetches_from_currency_exchange_table(self, mock_sql):
        """Returns the exchange rate found in tabCurrency Exchange."""
        mock_sql.return_value = [(4.45,)]
        rate = get_exchange_rate("USD", "MYR", "2025-01-31")
        self.assertAlmostEqual(rate, 4.45)
        mock_sql.assert_called_once()

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.currency_converter.frappe.db.sql"
    )
    def test_returns_one_when_no_record_found(self, mock_sql):
        """Falls back to 1.0 when no Currency Exchange record exists."""
        mock_sql.return_value = []
        rate = get_exchange_rate("AUD", "MYR", "2025-01-31")
        self.assertEqual(rate, 1.0)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.currency_converter.frappe.db.sql"
    )
    def test_db_exception_returns_one(self, mock_sql):
        """DB errors are caught gracefully; function returns 1.0."""
        mock_sql.side_effect = Exception("DB error")
        rate = get_exchange_rate("SGD", "MYR", "2025-01-31")
        self.assertEqual(rate, 1.0)


# ---------------------------------------------------------------------------
# 2. get_gross_myr_for_slip
# ---------------------------------------------------------------------------

class TestGetGrossMyrForSlip(FrappeTestCase):
    """get_gross_myr_for_slip() computes MYR gross from slip fields."""

    def test_myr_slip_returns_gross_pay_unchanged(self):
        """MYR salary slips return gross_pay directly (no conversion)."""
        slip = _make_slip(5000.0, currency="MYR", exchange_rate=1.0, gross_myr=5000.0)
        result = get_gross_myr_for_slip(slip)
        self.assertAlmostEqual(result, 5000.0)

    def test_non_myr_applies_exchange_rate(self):
        """USD slip at rate 4.45 converts 1000 USD → 4450 MYR."""
        slip = _make_slip(1000.0, currency="USD", exchange_rate=4.45)
        result = get_gross_myr_for_slip(slip)
        self.assertAlmostEqual(result, 4450.0)

    def test_sgd_conversion(self):
        """SGD slip at rate 3.35 converts 2000 SGD → 6700 MYR."""
        slip = _make_slip(2000.0, currency="SGD", exchange_rate=3.35)
        result = get_gross_myr_for_slip(slip)
        self.assertAlmostEqual(result, 6700.0)

    def test_missing_currency_treated_as_myr(self):
        """A slip with no custom_salary_currency is treated as MYR."""
        slip = MagicMock()
        slip.gross_pay = 8000.0
        # Simulate attribute missing / returns None
        slip.custom_salary_currency = None
        slip.custom_exchange_rate_to_myr = 1.0
        result = get_gross_myr_for_slip(slip)
        self.assertAlmostEqual(result, 8000.0)

    def test_zero_gross_pay(self):
        """Zero gross_pay returns 0.0 regardless of currency."""
        slip = _make_slip(0.0, currency="USD", exchange_rate=4.5)
        result = get_gross_myr_for_slip(slip)
        self.assertAlmostEqual(result, 0.0)


# ---------------------------------------------------------------------------
# 3. apply_myr_conversion (validate hook)
# ---------------------------------------------------------------------------

class TestApplyMyrConversion(FrappeTestCase):
    """apply_myr_conversion() sets custom_gross_myr and custom_exchange_rate_to_myr."""

    def test_myr_slip_sets_gross_myr_equal_to_gross_pay(self):
        """MYR slip: custom_gross_myr = gross_pay, exchange_rate = 1.0."""
        slip = _make_slip(6000.0, currency="MYR")
        apply_myr_conversion(slip)
        self.assertEqual(slip.custom_exchange_rate_to_myr, 1.0)
        self.assertAlmostEqual(slip.custom_gross_myr, 6000.0)

    def test_non_myr_with_manual_rate_uses_provided_rate(self):
        """Non-MYR slip with a manually set exchange_rate uses that rate."""
        slip = _make_slip(1000.0, currency="USD", exchange_rate=4.5)
        apply_myr_conversion(slip)
        self.assertAlmostEqual(slip.custom_gross_myr, 4500.0)
        self.assertAlmostEqual(slip.custom_exchange_rate_to_myr, 4.5)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.currency_converter.get_exchange_rate"
    )
    def test_non_myr_auto_fetches_rate_when_not_set(self, mock_get_rate):
        """Non-MYR slip with no rate auto-fetches from Currency Exchange."""
        mock_get_rate.return_value = 3.28
        slip = _make_slip(2000.0, currency="SGD", exchange_rate=0)
        apply_myr_conversion(slip)
        mock_get_rate.assert_called_once_with("SGD", "MYR", "2025-01-31")
        self.assertAlmostEqual(slip.custom_exchange_rate_to_myr, 3.28)
        self.assertAlmostEqual(slip.custom_gross_myr, 6560.0)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.currency_converter.get_exchange_rate"
    )
    def test_non_myr_defaults_to_one_when_no_rate_available(self, mock_get_rate):
        """No rate in DB and no manual rate → exchange_rate falls back to 1.0."""
        mock_get_rate.return_value = 0.0
        slip = _make_slip(500.0, currency="GBP", exchange_rate=0)
        apply_myr_conversion(slip)
        self.assertEqual(slip.custom_exchange_rate_to_myr, 1.0)
        self.assertAlmostEqual(slip.custom_gross_myr, 500.0)

    def test_myr_slip_without_currency_field(self):
        """Slip with no custom_salary_currency attribute treated as MYR."""
        slip = MagicMock()
        slip.gross_pay = 7000.0
        del slip.custom_salary_currency  # attribute missing
        # apply should not crash
        apply_myr_conversion(slip)
        self.assertEqual(slip.custom_exchange_rate_to_myr, 1.0)
        self.assertAlmostEqual(slip.custom_gross_myr, 7000.0)


# ---------------------------------------------------------------------------
# 4. PCB Calculator uses custom_gross_myr
# ---------------------------------------------------------------------------

class TestPcbUsesGrossMyr(FrappeTestCase):
    """PCB validate_pcb_amount uses MYR-equivalent gross for non-MYR slips."""

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_calculator.frappe.get_doc"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_calculator.frappe.msgprint"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_calculator._get_bik_for_employee"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_calculator.get_cp38_amount"
    )
    def test_non_myr_slip_uses_custom_gross_myr(
        self, mock_cp38, mock_bik, mock_msgprint, mock_get_doc
    ):
        """validate_pcb_amount uses custom_gross_myr instead of gross_pay for non-MYR."""
        mock_bik.return_value = 0.0
        mock_cp38.return_value = 0.0

        # Simulate a USD salary slip: gross_pay=5000 USD, gross_myr=22500 MYR (rate 4.5)
        slip_doc = MagicMock()
        slip_doc.gross_pay = 5000.0          # in USD
        slip_doc.custom_salary_currency = "USD"
        slip_doc.custom_gross_myr = 22500.0  # 5000 * 4.5
        slip_doc.employee = "EMP-001"
        slip_doc.start_date = "2025-01-01"
        slip_doc.end_date = "2025-01-31"
        slip_doc.deductions = []
        slip_doc.payment_days = 26
        slip_doc.total_working_days = 26

        employee_doc = MagicMock()
        employee_doc.custom_is_non_resident = 0
        employee_doc.custom_marital_status = ""
        employee_doc.custom_number_of_children = 0
        employee_doc.custom_pcb_category = None
        employee_doc.custom_cp38_expiry = None
        employee_doc.custom_cp38_amount = 0

        mock_get_doc.side_effect = lambda doctype, name=None, *a, **kw: (
            slip_doc if doctype == "Salary Slip" else employee_doc
        )

        from lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_calculator import (
            validate_pcb_amount,
        )
        result = validate_pcb_amount("SLIP-USD-001")
        # expected PCB is computed on 22500 MYR annual=270,000 MYR
        # (not 5000 USD annual=60,000 MYR)
        # We just check that it used the MYR-equivalent amount
        # Annual = 22500 * 12 = 270,000; tax band 24% → significant PCB
        self.assertGreater(result["expected_monthly_pcb"], 500)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_calculator.frappe.get_doc"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_calculator.frappe.msgprint"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_calculator._get_bik_for_employee"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_calculator.get_cp38_amount"
    )
    def test_myr_slip_uses_gross_pay_as_usual(
        self, mock_cp38, mock_bik, mock_msgprint, mock_get_doc
    ):
        """validate_pcb_amount for MYR slips still uses gross_pay unchanged."""
        mock_bik.return_value = 0.0
        mock_cp38.return_value = 0.0

        slip_doc = MagicMock()
        slip_doc.gross_pay = 10000.0
        slip_doc.custom_salary_currency = "MYR"
        slip_doc.custom_gross_myr = 10000.0
        slip_doc.employee = "EMP-002"
        slip_doc.start_date = "2025-01-01"
        slip_doc.end_date = "2025-01-31"
        slip_doc.deductions = []
        slip_doc.payment_days = 26
        slip_doc.total_working_days = 26

        employee_doc = MagicMock()
        employee_doc.custom_is_non_resident = 0
        employee_doc.custom_marital_status = ""
        employee_doc.custom_number_of_children = 0
        employee_doc.custom_pcb_category = None

        mock_get_doc.side_effect = lambda doctype, name=None, *a, **kw: (
            slip_doc if doctype == "Salary Slip" else employee_doc
        )

        from lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_calculator import (
            validate_pcb_amount,
        )
        result = validate_pcb_amount("SLIP-MYR-001")
        # Annual = 120,000; expected PCB in 24% band (100,001–400,000)
        self.assertGreater(result["expected_monthly_pcb"], 0)


# ---------------------------------------------------------------------------
# 5. CP39 gross_remuneration uses custom_gross_myr
# ---------------------------------------------------------------------------

class TestCp39GrossRemuneration(FrappeTestCase):
    """CP39 report SQL uses COALESCE(custom_gross_myr, gross_pay) for gross."""

    def test_sql_uses_coalesce_for_gross_remuneration(self):
        """The CP39 SQL query contains the COALESCE fallback for custom_gross_myr."""
        import inspect

        from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance import (
            cp39_pcb_remittance,
        )
        source = inspect.getsource(cp39_pcb_remittance)
        self.assertIn("custom_gross_myr", source, "CP39 SQL must reference custom_gross_myr")
        self.assertIn("COALESCE", source, "CP39 SQL must use COALESCE for fallback")


# ---------------------------------------------------------------------------
# 6. EA Form earnings apply exchange rate
# ---------------------------------------------------------------------------

class TestEaFormExchangeRate(FrappeTestCase):
    """EA form earnings SQL multiplies sd.amount by custom_exchange_rate_to_myr."""

    def test_ea_earnings_sql_applies_exchange_rate(self):
        """The earnings SQL in ea_form.py uses custom_exchange_rate_to_myr multiplier."""
        import inspect

        from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form import ea_form
        source = inspect.getsource(ea_form)
        self.assertIn(
            "custom_exchange_rate_to_myr",
            source,
            "EA form SQL must use custom_exchange_rate_to_myr for MYR conversion",
        )

    def test_currency_converter_service_importable(self):
        """The currency_converter module is importable with all expected exports."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.currency_converter import (
            apply_myr_conversion,
            get_exchange_rate,
            get_gross_myr_for_slip,
        )
        self.assertTrue(callable(get_exchange_rate))
        self.assertTrue(callable(get_gross_myr_for_slip))
        self.assertTrue(callable(apply_myr_conversion))

    def test_custom_fields_defined_in_fixture(self):
        """custom_salary_currency, custom_exchange_rate_to_myr, custom_gross_myr are in fixture."""
        import json
        import os

        fixture_path = os.path.join(
            os.path.dirname(__file__),
            "..", "fixtures", "custom_field.json"
        )
        with open(fixture_path) as f:
            fields = json.load(f)

        ss_fieldnames = {
            fld["fieldname"]
            for fld in fields
            if fld.get("dt") == "Salary Slip"
        }
        self.assertIn("custom_salary_currency", ss_fieldnames)
        self.assertIn("custom_exchange_rate_to_myr", ss_fieldnames)
        self.assertIn("custom_gross_myr", ss_fieldnames)
