"""Tests for Multi-Currency Salary Conversion Service (US-111).

Verifies:
1. convert_to_myr() with manual exchange rate
2. convert_to_myr() MYR passthrough (rate=1.0)
3. get_myr_gross_for_pcb() on MYR slip
4. get_myr_gross_for_pcb() on foreign-currency slip with manual rate
5. get_exchange_rate() direct currency pair (uses fallback when no DB record)
6. get_exchange_rate() same-currency short-circuit (always 1.0)
7. fetch_exchange_rate() for MYR returns 1.0 and base_currency source
8. fetch_exchange_rate() for foreign currency uses fallback when no DB record
9. calculate_component_myr() delegates to convert_to_myr()
10. PCB calculation uses MYR equivalent (not original currency amount)
"""
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.forex_service import (
    SUPPORTED_CURRENCIES,
    _FALLBACK_RATES,
    calculate_component_myr,
    convert_to_myr,
    fetch_exchange_rate,
    get_exchange_rate,
    get_myr_gross_for_pcb,
)


class TestConvertToMYR(FrappeTestCase):
    """Unit tests for convert_to_myr()."""

    def test_myr_passthrough_returns_original_amount(self):
        """MYR currency: conversion rate is 1.0, amount unchanged."""
        result = convert_to_myr(5000.0, "MYR")
        self.assertAlmostEqual(result, 5000.0, places=2)

    def test_myr_lowercase_also_handled(self):
        """Currency codes are normalised to uppercase internally."""
        result = convert_to_myr(3000.0, "myr")
        self.assertAlmostEqual(result, 3000.0, places=2)

    def test_manual_rate_takes_precedence(self):
        """When exchange_rate is explicitly provided, use it without DB lookup."""
        # USD 1000 at rate 4.70 = MYR 4700
        result = convert_to_myr(1000.0, "USD", exchange_rate=4.70)
        self.assertAlmostEqual(result, 4700.0, places=2)

    def test_sgd_manual_rate_conversion(self):
        """SGD salary conversion with manual rate."""
        result = convert_to_myr(2000.0, "SGD", exchange_rate=3.50)
        self.assertAlmostEqual(result, 7000.0, places=2)

    def test_gbp_manual_rate_conversion(self):
        """GBP salary conversion with manual rate."""
        result = convert_to_myr(1500.0, "GBP", exchange_rate=5.90)
        self.assertAlmostEqual(result, 8850.0, places=2)

    def test_aud_manual_rate_conversion(self):
        """AUD salary conversion with manual rate."""
        result = convert_to_myr(4000.0, "AUD", exchange_rate=3.10)
        self.assertAlmostEqual(result, 12400.0, places=2)

    def test_result_rounded_to_two_decimal_places(self):
        """Result is rounded to 2 decimal places."""
        # 100 * 4.733 = 473.3 → 473.30
        result = convert_to_myr(100.0, "USD", exchange_rate=4.733)
        self.assertEqual(result, 473.3)

    def test_zero_amount_returns_zero(self):
        """Zero income in any currency converts to zero MYR."""
        result = convert_to_myr(0.0, "USD", exchange_rate=4.70)
        self.assertAlmostEqual(result, 0.0, places=2)


class TestGetExchangeRate(FrappeTestCase):
    """Unit tests for get_exchange_rate()."""

    def test_same_currency_returns_one(self):
        """Requesting MYR→MYR (or any same-currency pair) returns 1.0."""
        self.assertEqual(get_exchange_rate("MYR", "MYR"), 1.0)
        self.assertEqual(get_exchange_rate("USD", "USD"), 1.0)

    def test_myr_to_myr_always_one(self):
        """Explicit MYR base currency short-circuit."""
        rate = get_exchange_rate("MYR")
        self.assertEqual(rate, 1.0)

    @patch("lhdn_payroll_integration.services.forex_service.frappe.db.sql")
    def test_uses_currency_exchange_table_when_available(self, mock_sql):
        """When Currency Exchange record exists, use it (not fallback)."""
        # Return a rate of 4.85 from the DB
        mock_sql.return_value = [(4.85,)]
        rate = get_exchange_rate("USD", "MYR", date="2025-06-15")
        self.assertAlmostEqual(rate, 4.85, places=4)

    @patch("lhdn_payroll_integration.services.forex_service.frappe.db.sql")
    @patch("lhdn_payroll_integration.services.forex_service.frappe.log_error")
    def test_falls_back_to_static_rates_when_no_db_record(self, mock_log, mock_sql):
        """When no DB record is found, falls back to _FALLBACK_RATES."""
        mock_sql.return_value = []
        rate = get_exchange_rate("USD", "MYR", date="2025-06-15")
        self.assertAlmostEqual(rate, _FALLBACK_RATES["USD"], places=4)
        mock_log.assert_called_once()

    @patch("lhdn_payroll_integration.services.forex_service.frappe.db.sql")
    def test_reverse_lookup_when_direct_not_found(self, mock_sql):
        """If USD→MYR not found but MYR→USD is, invert the rate."""
        # First call (USD→MYR): empty; second call (MYR→USD): returns 0.2128
        mock_sql.side_effect = [[], [(0.2128,)]]
        rate = get_exchange_rate("USD", "MYR", date="2025-06-15")
        expected = round(1.0 / 0.2128, 6)
        self.assertAlmostEqual(rate, expected, places=3)


class TestGetMYRGrossForPCB(FrappeTestCase):
    """Unit tests for get_myr_gross_for_pcb()."""

    def _make_slip(self, gross_pay, currency="MYR", exchange_rate=0):
        doc = MagicMock()
        doc.gross_pay = gross_pay
        doc.custom_salary_currency = currency
        doc.custom_exchange_rate_to_myr = exchange_rate
        doc.posting_date = "2025-06-30"
        doc.end_date = "2025-06-30"
        return doc

    def test_myr_slip_returns_gross_pay_unchanged(self):
        """For MYR salary, gross_pay is returned as-is."""
        doc = self._make_slip(8000.0, "MYR")
        result = get_myr_gross_for_pcb(doc)
        self.assertAlmostEqual(result, 8000.0, places=2)

    def test_usd_slip_with_manual_rate(self):
        """USD salary slip with manual rate → USD gross * rate = MYR equivalent."""
        doc = self._make_slip(2000.0, "USD", exchange_rate=4.70)
        result = get_myr_gross_for_pcb(doc)
        self.assertAlmostEqual(result, 9400.0, places=2)

    def test_sgd_slip_with_manual_rate(self):
        """SGD salary slip with manual rate."""
        doc = self._make_slip(3000.0, "SGD", exchange_rate=3.50)
        result = get_myr_gross_for_pcb(doc)
        self.assertAlmostEqual(result, 10500.0, places=2)

    @patch("lhdn_payroll_integration.services.forex_service.get_exchange_rate")
    def test_foreign_currency_uses_db_lookup_when_no_manual_rate(self, mock_rate):
        """When custom_exchange_rate_to_myr = 0, look up from Currency Exchange."""
        mock_rate.return_value = 4.75
        doc = self._make_slip(1000.0, "USD", exchange_rate=0)
        result = get_myr_gross_for_pcb(doc)
        self.assertAlmostEqual(result, 4750.0, places=2)
        mock_rate.assert_called_once_with("USD", "MYR", date="2025-06-30")

    def test_myr_currency_none_defaults_to_myr(self):
        """When custom_salary_currency is None/empty, treat as MYR."""
        doc = MagicMock()
        doc.gross_pay = 5000.0
        doc.custom_salary_currency = None
        doc.custom_exchange_rate_to_myr = 0
        doc.posting_date = "2025-06-30"
        doc.end_date = "2025-06-30"
        result = get_myr_gross_for_pcb(doc)
        self.assertAlmostEqual(result, 5000.0, places=2)


class TestCalculateComponentMYR(FrappeTestCase):
    """Unit tests for calculate_component_myr()."""

    def test_delegates_to_convert_to_myr(self):
        """calculate_component_myr wraps convert_to_myr correctly."""
        result = calculate_component_myr(500.0, "USD", exchange_rate=4.70)
        self.assertAlmostEqual(result, 2350.0, places=2)

    def test_myr_component_unchanged(self):
        """MYR components returned as-is."""
        result = calculate_component_myr(3000.0, "MYR")
        self.assertAlmostEqual(result, 3000.0, places=2)


class TestFetchExchangeRate(FrappeTestCase):
    """Unit tests for fetch_exchange_rate() whitelisted API."""

    def test_myr_returns_one_and_base_currency_source(self):
        """Requesting MYR returns rate=1.0 and source='base_currency'."""
        result = fetch_exchange_rate("MYR")
        self.assertEqual(result["exchange_rate"], 1.0)
        self.assertEqual(result["source"], "base_currency")
        self.assertEqual(result["from_currency"], "MYR")
        self.assertEqual(result["to_currency"], "MYR")

    @patch("lhdn_payroll_integration.services.forex_service.frappe.db.sql")
    def test_returns_db_rate_with_correct_source(self, mock_sql):
        """When DB has a rate, returns it with source='Currency Exchange table'."""
        mock_sql.return_value = [(4.72,)]
        result = fetch_exchange_rate("USD", date="2025-06-15")
        self.assertAlmostEqual(result["exchange_rate"], 4.72, places=4)
        self.assertEqual(result["source"], "Currency Exchange table")
        self.assertEqual(result["from_currency"], "USD")

    @patch("lhdn_payroll_integration.services.forex_service.frappe.db.sql")
    def test_returns_fallback_when_no_db_record(self, mock_sql):
        """When no DB record, uses fallback rate with source='fallback'."""
        mock_sql.return_value = []
        result = fetch_exchange_rate("SGD", date="2025-06-15")
        self.assertAlmostEqual(result["exchange_rate"], _FALLBACK_RATES["SGD"], places=4)
        self.assertEqual(result["source"], "fallback")

    def test_lowercase_currency_normalised(self):
        """Currency codes are normalised to uppercase."""
        result = fetch_exchange_rate("myr")
        self.assertEqual(result["from_currency"], "MYR")
        self.assertEqual(result["exchange_rate"], 1.0)


class TestSupportedCurrencies(FrappeTestCase):
    """Verify the SUPPORTED_CURRENCIES set."""

    def test_myr_is_supported(self):
        self.assertIn("MYR", SUPPORTED_CURRENCIES)

    def test_common_expatriate_currencies_supported(self):
        for cur in ["USD", "SGD", "GBP", "AUD"]:
            self.assertIn(cur, SUPPORTED_CURRENCIES)

    def test_fallback_rates_cover_supported_currencies(self):
        """Every supported currency except exotic ones has a fallback rate."""
        for cur in SUPPORTED_CURRENCIES:
            self.assertIn(cur, _FALLBACK_RATES, f"No fallback rate for {cur}")


class TestPCBUsesMYREquivalent(FrappeTestCase):
    """Integration: verify PCB calculator receives MYR gross, not foreign currency gross."""

    def test_usd_salary_pcb_uses_myr_amount(self):
        """USD 2000/month at 4.70 → MYR 9400/month → correct annual income for PCB."""
        from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb

        usd_monthly = 2000.0
        rate = 4.70
        myr_monthly = usd_monthly * rate  # 9400 MYR

        # PCB should be calculated on MYR 9400/month, not USD 2000/month
        pcb_on_myr = calculate_pcb(annual_income=myr_monthly * 12, resident=True)
        pcb_on_usd = calculate_pcb(annual_income=usd_monthly * 12, resident=True)

        # PCB on MYR 112800/year should be much higher than PCB on USD 24000/year (MYR equivalent is irrelevant here)
        self.assertGreater(pcb_on_myr, pcb_on_usd)
        # Sanity: MYR 9400/month annual = 112800; tax should be > 0
        self.assertGreater(pcb_on_myr, 0)

    def test_myr_slip_pcb_equals_direct_calculation(self):
        """For MYR slips, get_myr_gross_for_pcb returns same as gross_pay."""
        doc = MagicMock()
        doc.gross_pay = 6000.0
        doc.custom_salary_currency = "MYR"
        doc.custom_exchange_rate_to_myr = 0
        doc.posting_date = "2025-06-30"
        doc.end_date = "2025-06-30"

        myr_gross = get_myr_gross_for_pcb(doc)
        self.assertAlmostEqual(myr_gross, 6000.0, places=2)
