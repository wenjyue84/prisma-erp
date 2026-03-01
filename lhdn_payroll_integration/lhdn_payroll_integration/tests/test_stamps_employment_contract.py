"""Tests for US-150: LHDN STAMPS Employment Contract Digital Stamp Status Tracker.

Covers:
- DocType existence and required fields
- stamp_amount default (RM10)
- stamping_method select options
- status computed field (Pending / Stamped / Legacy Stamped)
- legacy_stamped flag suppresses alerts
- stamps.hasil.gov.my URL present in service
- get_unstamped_contracts helper returns correct structure
- days_since_start calculation
- is_legacy_contract threshold (pre-2021)
"""
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.stamps_employment_contract_service import (
    STAMP_AMOUNT,
    STAMPS_PORTAL_URL,
    PRE_STAMPS_YEAR,
    get_days_since_contract_start,
    get_unstamped_contracts,
    is_legacy_contract,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestSTAMPSConstants(FrappeTestCase):
    """Verify statutory constants."""

    def test_stamp_amount_is_10(self):
        """Fixed stamp duty RM10 per contract (Item 4, First Schedule, Stamp Act 1949)."""
        self.assertEqual(STAMP_AMOUNT, 10.0)

    def test_stamps_portal_url(self):
        """STAMPS portal URL must point to stamps.hasil.gov.my."""
        self.assertIn("stamps.hasil.gov.my", STAMPS_PORTAL_URL)

    def test_pre_stamps_year_is_2021(self):
        """Contracts before 2021 are in the pre-STAMPS era."""
        self.assertEqual(PRE_STAMPS_YEAR, 2021)


# ---------------------------------------------------------------------------
# DocType structure
# ---------------------------------------------------------------------------

class TestSTAMPSDocTypeExists(FrappeTestCase):
    """Test that LHDN STAMPS Employment Contract DocType is registered."""

    def test_doctype_registered(self):
        self.assertTrue(frappe.db.exists("DocType", "LHDN STAMPS Employment Contract"))

    def test_db_table_exists(self):
        tables = frappe.db.sql(
            "SHOW TABLES LIKE 'tabLHDN STAMPS Employment Contract'", as_list=True
        )
        self.assertEqual(len(tables), 1)

    def test_required_fields_present(self):
        meta = frappe.get_meta("LHDN STAMPS Employment Contract")
        field_names = [f.fieldname for f in meta.fields]
        required = [
            "employee",
            "employee_name",
            "company",
            "contract_start_date",
            "stamp_reference_number",
            "stamp_date",
            "stamp_amount",
            "stamping_method",
            "legacy_stamped",
            "status",
            "task_name",
        ]
        for field in required:
            self.assertIn(field, field_names, f"Missing field: {field}")

    def test_stamp_amount_is_currency_field(self):
        meta = frappe.get_meta("LHDN STAMPS Employment Contract")
        field = meta.get_field("stamp_amount")
        self.assertIsNotNone(field)
        self.assertEqual(field.fieldtype, "Currency")

    def test_legacy_stamped_is_check_field(self):
        meta = frappe.get_meta("LHDN STAMPS Employment Contract")
        field = meta.get_field("legacy_stamped")
        self.assertIsNotNone(field)
        self.assertEqual(field.fieldtype, "Check")

    def test_stamping_method_contains_stamps_digital(self):
        meta = frappe.get_meta("LHDN STAMPS Employment Contract")
        field = meta.get_field("stamping_method")
        self.assertIsNotNone(field)
        self.assertIn("STAMPS Digital", field.options or "")

    def test_stamping_method_contains_manual_legacy(self):
        meta = frappe.get_meta("LHDN STAMPS Employment Contract")
        field = meta.get_field("stamping_method")
        self.assertIn("Manual Legacy", field.options or "")

    def test_stamping_method_contains_pre_stamps_legacy(self):
        meta = frappe.get_meta("LHDN STAMPS Employment Contract")
        field = meta.get_field("stamping_method")
        self.assertIn("Pre-STAMPS Legacy", field.options or "")

    def test_status_options_include_pending(self):
        meta = frappe.get_meta("LHDN STAMPS Employment Contract")
        field = meta.get_field("status")
        self.assertIn("Pending", field.options or "")

    def test_status_options_include_stamped(self):
        meta = frappe.get_meta("LHDN STAMPS Employment Contract")
        field = meta.get_field("status")
        self.assertIn("Stamped", field.options or "")

    def test_status_options_include_legacy_stamped(self):
        meta = frappe.get_meta("LHDN STAMPS Employment Contract")
        field = meta.get_field("status")
        self.assertIn("Legacy Stamped", field.options or "")


# ---------------------------------------------------------------------------
# Days since contract start
# ---------------------------------------------------------------------------

class TestDaysSinceContractStart(FrappeTestCase):
    """Test days elapsed calculation."""

    def test_none_returns_zero(self):
        self.assertEqual(get_days_since_contract_start(None), 0)

    def test_today_returns_zero(self):
        from frappe.utils import today
        result = get_days_since_contract_start(today())
        self.assertGreaterEqual(result, 0)
        self.assertLessEqual(result, 1)

    def test_past_date_returns_positive(self):
        from frappe.utils import add_days, today
        past = add_days(today(), -45)
        self.assertEqual(get_days_since_contract_start(past), 45)

    def test_future_date_returns_zero(self):
        from frappe.utils import add_days, today
        future = add_days(today(), 10)
        self.assertEqual(get_days_since_contract_start(future), 0)


# ---------------------------------------------------------------------------
# Legacy contract detection
# ---------------------------------------------------------------------------

class TestIsLegacyContract(FrappeTestCase):
    """Test pre-2021 legacy detection."""

    def test_2020_is_legacy(self):
        self.assertTrue(is_legacy_contract("2020-06-15"))

    def test_2019_is_legacy(self):
        self.assertTrue(is_legacy_contract("2019-01-01"))

    def test_2021_is_not_legacy(self):
        self.assertFalse(is_legacy_contract("2021-01-01"))

    def test_2023_is_not_legacy(self):
        self.assertFalse(is_legacy_contract("2023-07-01"))

    def test_none_is_not_legacy(self):
        self.assertFalse(is_legacy_contract(None))


# ---------------------------------------------------------------------------
# get_unstamped_contracts service
# ---------------------------------------------------------------------------

class TestGetUnstampedContracts(FrappeTestCase):
    """Test the query helper with mocked frappe.get_all."""

    def _make_record(self, name, days_ago, has_reference=False):
        from frappe.utils import add_days, today
        return {
            "name": name,
            "employee": name,
            "employee_name": "Test Employee",
            "company": "Test Co Sdn Bhd",
            "contract_start_date": add_days(today(), -days_ago),
            "stamp_reference_number": "STAMPS-2026-001" if has_reference else "",
            "stamp_date": None,
            "stamp_amount": 10.0,
            "stamping_method": "STAMPS Digital",
            "legacy_stamped": 0,
            "status": "Stamped" if has_reference else "Pending",
        }

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamps_employment_contract_service.frappe.get_all"
    )
    def test_returns_list(self, mock_get_all):
        mock_get_all.return_value = []
        result = get_unstamped_contracts()
        self.assertIsInstance(result, list)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamps_employment_contract_service.frappe.get_all"
    )
    def test_record_has_required_keys(self, mock_get_all):
        mock_get_all.return_value = [self._make_record("EMP-001", 30)]
        result = get_unstamped_contracts()
        self.assertEqual(len(result), 1)
        required_keys = [
            "name",
            "employee",
            "employee_name",
            "company",
            "contract_start_date",
            "stamp_reference_number",
            "stamp_amount",
            "days_since_start",
            "status",
        ]
        for key in required_keys:
            self.assertIn(key, result[0], f"Missing key: {key}")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamps_employment_contract_service.frappe.get_all"
    )
    def test_days_since_start_calculated(self, mock_get_all):
        mock_get_all.return_value = [self._make_record("EMP-001", 60)]
        result = get_unstamped_contracts()
        self.assertEqual(result[0]["days_since_start"], 60)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamps_employment_contract_service.frappe.get_all"
    )
    def test_sorted_by_days_descending(self, mock_get_all):
        mock_get_all.return_value = [
            self._make_record("EMP-001", 20),
            self._make_record("EMP-002", 90),
            self._make_record("EMP-003", 45),
        ]
        result = get_unstamped_contracts()
        days = [r["days_since_start"] for r in result]
        self.assertEqual(days, sorted(days, reverse=True))

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamps_employment_contract_service.frappe.get_all"
    )
    def test_company_filter_forwarded(self, mock_get_all):
        mock_get_all.return_value = []
        get_unstamped_contracts(company="Test Co Sdn Bhd")
        call_filters = mock_get_all.call_args[1]["filters"]
        self.assertIn("company", call_filters)
        self.assertEqual(call_filters["company"], "Test Co Sdn Bhd")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamps_employment_contract_service.frappe.get_all"
    )
    def test_stamp_amount_is_10(self, mock_get_all):
        mock_get_all.return_value = [self._make_record("EMP-001", 10)]
        result = get_unstamped_contracts()
        self.assertEqual(result[0]["stamp_amount"], 10.0)


# ---------------------------------------------------------------------------
# Report existence
# ---------------------------------------------------------------------------

class TestUnstampedContractsReport(FrappeTestCase):
    """Test that Unstamped Employment Contracts report is registered."""

    def test_report_exists(self):
        self.assertTrue(
            frappe.db.exists("Report", "Unstamped Employment Contracts"),
            "Report 'Unstamped Employment Contracts' is not registered",
        )

    def test_report_is_script_type(self):
        report = frappe.get_doc("Report", "Unstamped Employment Contracts")
        self.assertEqual(report.report_type, "Script Report")

    def test_report_module(self):
        report = frappe.get_doc("Report", "Unstamped Employment Contracts")
        self.assertEqual(report.module, "LHDN Payroll Integration")
