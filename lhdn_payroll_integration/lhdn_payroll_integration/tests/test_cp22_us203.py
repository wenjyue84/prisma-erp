"""Tests for US-203: e-CP22 Online-Only Mandatory Submission and Wakil Majikan Authorization.

Acceptance criteria covered:
  AC-1: CP22 generates only digital summary — no paper PDF
  AC-2: Company stores Wakil Majikan: name, MyTax login ID, authorization date
  AC-3: Alert 'e-CP22 must be submitted by company director or registered Wakil Majikan
         via mytax.hasil.gov.my — system cannot auto-submit'
  AC-4: Employee has LHDN acknowledgement reference number field (already exists via US-114)
  AC-5: System blocks onboarding if CP22 Pending and 30+ days elapsed
  AC-6: Penalty notice when 30-day deadline at risk

Tests:
  1. check_employer_rep_setup raises when Wakil Majikan fields missing
  2. check_employer_rep_setup passes when all Wakil Majikan fields present
  3. get_cp22_online_mandate_alert returns correct text
  4. get_cp22_penalty_notice returns correct text
  5. check_onboarding_block raises when Pending + 30+ days elapsed
  6. check_onboarding_block does NOT raise when Pending < 30 days
  7. check_onboarding_block does NOT raise when status is Submitted
  8. check_onboarding_block does NOT raise when no date_of_joining
  9. show_online_mandate_alert calls msgprint with mandate text
  10. show_online_mandate_alert shows penalty notice when deadline <= 7 days
  11. show_online_mandate_alert does NOT show penalty when deadline > 7 days
  12. Company has custom_mytax_employer_rep_login_id field (custom field exists)
  13. Company has custom_mytax_employer_rep_auth_date field (custom field exists)
  14. Company has custom_mytax_employer_rep_name field (custom field exists)
  15. hooks.py registers Employee validate for check_onboarding_block
  16. hooks.py registers LHDN CP22 validate for show_online_mandate_alert
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# 1–4: Service function unit tests
# ---------------------------------------------------------------------------

class TestCheckEmployerRepSetup(FrappeTestCase):
    """Test check_employer_rep_setup validates Wakil Majikan fields on Company."""

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_raises_when_all_fields_missing(self, mock_frappe):
        """Throws ValidationError when all Wakil Majikan fields are missing."""
        from lhdn_payroll_integration.services.cp22_mandate_service import check_employer_rep_setup

        mock_company = MagicMock()
        mock_company.get.return_value = None  # all fields missing
        mock_frappe.get_doc.return_value = mock_company
        mock_frappe.throw.side_effect = frappe.ValidationError("Wakil Majikan Not Configured")

        with self.assertRaises(frappe.ValidationError):
            check_employer_rep_setup("Test Company")

        mock_frappe.throw.assert_called_once()
        call_args = mock_frappe.throw.call_args
        message = call_args[0][0]
        self.assertIn("Wakil Majikan", message)
        self.assertIn("Test Company", message)

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_raises_listing_missing_fields(self, mock_frappe):
        """Throw message lists which specific fields are missing."""
        from lhdn_payroll_integration.services.cp22_mandate_service import check_employer_rep_setup

        mock_company = MagicMock()

        def company_get(field):
            if field == "custom_mytax_employer_rep_name":
                return "Ahmad bin Ali"  # present
            return None  # login_id and auth_date missing

        mock_company.get.side_effect = company_get
        mock_frappe.get_doc.return_value = mock_company
        mock_frappe.throw.side_effect = frappe.ValidationError("missing")

        with self.assertRaises(frappe.ValidationError):
            check_employer_rep_setup("Acme Sdn Bhd")

        message = mock_frappe.throw.call_args[0][0]
        self.assertIn("Login ID", message)
        self.assertIn("Authorization Date", message)
        self.assertNotIn("Name", message)  # name is present — should NOT be listed

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_passes_when_all_fields_present(self, mock_frappe):
        """No exception when all Wakil Majikan fields are present."""
        from lhdn_payroll_integration.services.cp22_mandate_service import check_employer_rep_setup

        mock_company = MagicMock()

        def company_get(field):
            values = {
                "custom_mytax_employer_rep_name": "Ahmad bin Ali",
                "custom_mytax_employer_rep_login_id": "ahmad.ali@mytax.gov.my",
                "custom_mytax_employer_rep_auth_date": "2024-10-01",
            }
            return values.get(field)

        mock_company.get.side_effect = company_get
        mock_frappe.get_doc.return_value = mock_company

        # Should not raise
        check_employer_rep_setup("Good Company Sdn Bhd")
        mock_frappe.throw.assert_not_called()


class TestGetMandateTexts(FrappeTestCase):
    """Test get_cp22_online_mandate_alert and get_cp22_penalty_notice."""

    def test_online_mandate_alert_contains_mytax(self):
        """Mandate alert text references mytax.hasil.gov.my."""
        from lhdn_payroll_integration.services.cp22_mandate_service import get_cp22_online_mandate_alert

        alert = get_cp22_online_mandate_alert()
        self.assertIn("mytax.hasil.gov.my", alert)
        self.assertIn("Wakil Majikan", alert)
        self.assertIn("cannot auto-submit", alert)

    def test_online_mandate_alert_mentions_director(self):
        """Mandate alert text mentions company director."""
        from lhdn_payroll_integration.services.cp22_mandate_service import get_cp22_online_mandate_alert

        alert = get_cp22_online_mandate_alert()
        self.assertIn("company director", alert)

    def test_penalty_notice_cites_ita_section(self):
        """Penalty notice cites ITA 1967 S.83(2)."""
        from lhdn_payroll_integration.services.cp22_mandate_service import get_cp22_penalty_notice

        notice = get_cp22_penalty_notice()
        self.assertIn("ITA 1967", notice)
        self.assertIn("S.83(2)", notice)

    def test_penalty_notice_states_fine_range(self):
        """Penalty notice states RM200 to RM20,000 fine."""
        from lhdn_payroll_integration.services.cp22_mandate_service import get_cp22_penalty_notice

        notice = get_cp22_penalty_notice()
        self.assertIn("RM200", notice)
        self.assertIn("RM20,000", notice)

    def test_penalty_notice_states_imprisonment(self):
        """Penalty notice states imprisonment risk."""
        from lhdn_payroll_integration.services.cp22_mandate_service import get_cp22_penalty_notice

        notice = get_cp22_penalty_notice()
        self.assertIn("imprisonment", notice)


# ---------------------------------------------------------------------------
# 5–8: check_onboarding_block tests
# ---------------------------------------------------------------------------

class TestCheckOnboardingBlock(FrappeTestCase):
    """Test check_onboarding_block blocks Employee save when CP22 overdue."""

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.today", return_value="2026-03-01")
    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_raises_when_pending_and_30_days_elapsed(self, mock_frappe, mock_today):
        """Throws when CP22 is Pending and 30+ days have passed since hire date."""
        from lhdn_payroll_integration.services.cp22_mandate_service import check_onboarding_block

        mock_frappe.utils.date_diff = frappe.utils.date_diff
        mock_frappe.utils.getdate = frappe.utils.getdate
        mock_frappe.throw.side_effect = frappe.ValidationError("CP22 Submission Overdue")

        doc = MagicMock()
        doc.get.return_value = "Pending"  # custom_cp22_submission_status
        doc.date_of_joining = "2026-01-30"  # 30 days before 2026-03-01
        doc.employee_name = "Lim Wei Ming"

        with self.assertRaises(frappe.ValidationError):
            check_onboarding_block(doc)

        mock_frappe.throw.assert_called_once()
        message = mock_frappe.throw.call_args[0][0]
        self.assertIn("Lim Wei Ming", message)
        self.assertIn("mytax.hasil.gov.my", message)
        self.assertIn("ITA 1967", message)

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.today", return_value="2026-03-01")
    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_does_not_raise_when_less_than_30_days(self, mock_frappe, mock_today):
        """No error when CP22 is Pending but < 30 days since hire date."""
        from lhdn_payroll_integration.services.cp22_mandate_service import check_onboarding_block

        mock_frappe.utils.date_diff = frappe.utils.date_diff
        mock_frappe.utils.getdate = frappe.utils.getdate

        doc = MagicMock()
        doc.get.return_value = "Pending"
        doc.date_of_joining = "2026-02-10"  # 19 days before 2026-03-01
        doc.employee_name = "New Hire"

        check_onboarding_block(doc)
        mock_frappe.throw.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_does_not_raise_when_status_submitted(self, mock_frappe):
        """No error when CP22 status is Submitted (regardless of days elapsed)."""
        from lhdn_payroll_integration.services.cp22_mandate_service import check_onboarding_block

        doc = MagicMock()
        doc.get.return_value = "Submitted"
        doc.date_of_joining = "2020-01-01"
        doc.employee_name = "Old Employee"

        check_onboarding_block(doc)
        mock_frappe.throw.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_does_not_raise_when_no_joining_date(self, mock_frappe):
        """No error when date_of_joining is not set."""
        from lhdn_payroll_integration.services.cp22_mandate_service import check_onboarding_block

        doc = MagicMock()
        doc.get.return_value = "Pending"
        doc.date_of_joining = None

        check_onboarding_block(doc)
        mock_frappe.throw.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_does_not_raise_when_status_not_required(self, mock_frappe):
        """No error when CP22 status is Not Required."""
        from lhdn_payroll_integration.services.cp22_mandate_service import check_onboarding_block

        doc = MagicMock()
        doc.get.return_value = "Not Required"
        doc.date_of_joining = "2020-01-01"

        check_onboarding_block(doc)
        mock_frappe.throw.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.today", return_value="2026-03-01")
    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_raises_exactly_at_30_days(self, mock_frappe, mock_today):
        """Block triggers exactly at 30 days (boundary condition)."""
        from lhdn_payroll_integration.services.cp22_mandate_service import check_onboarding_block

        mock_frappe.utils.date_diff = frappe.utils.date_diff
        mock_frappe.utils.getdate = frappe.utils.getdate
        mock_frappe.throw.side_effect = frappe.ValidationError("block")

        doc = MagicMock()
        doc.get.return_value = "Pending"
        doc.date_of_joining = "2026-01-30"  # exactly 30 days before 2026-03-01
        doc.employee_name = "Boundary Test"

        with self.assertRaises(frappe.ValidationError):
            check_onboarding_block(doc)

        mock_frappe.throw.assert_called_once()


# ---------------------------------------------------------------------------
# 9–11: show_online_mandate_alert tests
# ---------------------------------------------------------------------------

class TestShowOnlineMandateAlert(FrappeTestCase):
    """Test show_online_mandate_alert msgprint behavior."""

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_always_shows_mandate_alert(self, mock_frappe):
        """Always displays the online-mandate msgprint regardless of deadline."""
        from lhdn_payroll_integration.services.cp22_mandate_service import (
            show_online_mandate_alert,
            ONLINE_MANDATE_ALERT,
        )

        doc = MagicMock()
        doc.get.return_value = None  # no filing_deadline

        show_online_mandate_alert(doc)

        mock_frappe.msgprint.assert_called()
        first_call = mock_frappe.msgprint.call_args_list[0]
        self.assertEqual(first_call[0][0], ONLINE_MANDATE_ALERT)

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.today", return_value="2026-03-01")
    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_shows_penalty_notice_when_deadline_at_risk(self, mock_frappe, mock_today):
        """Displays penalty notice when filing_deadline is 7 days or fewer away."""
        from lhdn_payroll_integration.services.cp22_mandate_service import (
            show_online_mandate_alert,
            PENALTY_NOTICE,
        )

        mock_frappe.utils.date_diff = frappe.utils.date_diff
        mock_frappe.utils.getdate = frappe.utils.getdate

        doc = MagicMock()

        def doc_get(field):
            if field == "filing_deadline":
                return "2026-03-05"  # 4 days from today (at risk)
            if field == "status":
                return "Pending"
            return None

        doc.get.side_effect = doc_get
        doc.filing_deadline = "2026-03-05"
        doc.status = "Pending"

        show_online_mandate_alert(doc)

        self.assertEqual(mock_frappe.msgprint.call_count, 2)
        second_call = mock_frappe.msgprint.call_args_list[1]
        self.assertEqual(second_call[0][0], PENALTY_NOTICE)
        self.assertIn("orange", str(second_call))

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.today", return_value="2026-03-01")
    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_no_penalty_notice_when_deadline_not_at_risk(self, mock_frappe, mock_today):
        """Does NOT display penalty notice when deadline > 7 days away."""
        from lhdn_payroll_integration.services.cp22_mandate_service import show_online_mandate_alert

        mock_frappe.utils.date_diff = frappe.utils.date_diff
        mock_frappe.utils.getdate = frappe.utils.getdate

        doc = MagicMock()

        def doc_get(field):
            if field == "filing_deadline":
                return "2026-03-20"  # 19 days away — safe
            if field == "status":
                return "Pending"
            return None

        doc.get.side_effect = doc_get
        doc.filing_deadline = "2026-03-20"
        doc.status = "Pending"

        show_online_mandate_alert(doc)

        # Only one msgprint call (mandate alert only — no penalty)
        self.assertEqual(mock_frappe.msgprint.call_count, 1)

    @patch("lhdn_payroll_integration.services.cp22_mandate_service.today", return_value="2026-03-01")
    @patch("lhdn_payroll_integration.services.cp22_mandate_service.frappe")
    def test_no_penalty_when_status_not_pending(self, mock_frappe, mock_today):
        """Does NOT show penalty notice when CP22 status is not Pending."""
        from lhdn_payroll_integration.services.cp22_mandate_service import show_online_mandate_alert

        mock_frappe.utils.date_diff = frappe.utils.date_diff
        mock_frappe.utils.getdate = frappe.utils.getdate

        doc = MagicMock()

        def doc_get(field):
            if field == "filing_deadline":
                return "2026-03-02"  # 1 day away but status is Submitted
            if field == "status":
                return "Submitted"
            return None

        doc.get.side_effect = doc_get

        show_online_mandate_alert(doc)

        # Only one call — mandate alert, no penalty
        self.assertEqual(mock_frappe.msgprint.call_count, 1)


# ---------------------------------------------------------------------------
# 12–14: Custom field existence (integration tests)
# ---------------------------------------------------------------------------

class TestCompanyWakilMajikanFields(FrappeTestCase):
    """Test that required Wakil Majikan custom fields exist on Company doctype."""

    def test_company_has_mytax_employer_rep_name(self):
        """Company has custom_mytax_employer_rep_name (Data) field."""
        self.assertTrue(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Company", "fieldname": "custom_mytax_employer_rep_name"},
            ),
            "custom_mytax_employer_rep_name field missing from Company",
        )

    def test_company_has_mytax_employer_rep_login_id(self):
        """Company has custom_mytax_employer_rep_login_id (Data) field."""
        self.assertTrue(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Company", "fieldname": "custom_mytax_employer_rep_login_id"},
            ),
            "custom_mytax_employer_rep_login_id field missing from Company",
        )

    def test_company_has_mytax_employer_rep_auth_date(self):
        """Company has custom_mytax_employer_rep_auth_date (Date) field."""
        self.assertTrue(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Company", "fieldname": "custom_mytax_employer_rep_auth_date"},
            ),
            "custom_mytax_employer_rep_auth_date field missing from Company",
        )

    def test_mytax_employer_rep_login_id_is_data_type(self):
        """custom_mytax_employer_rep_login_id is Data fieldtype."""
        field = frappe.db.get_value(
            "Custom Field",
            {"dt": "Company", "fieldname": "custom_mytax_employer_rep_login_id"},
            "fieldtype",
        )
        self.assertEqual(field, "Data")

    def test_mytax_employer_rep_auth_date_is_date_type(self):
        """custom_mytax_employer_rep_auth_date is Date fieldtype."""
        field = frappe.db.get_value(
            "Custom Field",
            {"dt": "Company", "fieldname": "custom_mytax_employer_rep_auth_date"},
            "fieldtype",
        )
        self.assertEqual(field, "Date")


# ---------------------------------------------------------------------------
# 15–16: hooks.py registration tests
# ---------------------------------------------------------------------------

class TestUS203HooksRegistration(FrappeTestCase):
    """Test that hooks.py registers the correct doc_events for US-203."""

    def test_employee_validate_includes_onboarding_block(self):
        """hooks.py registers Employee validate with check_onboarding_block."""
        from lhdn_payroll_integration.hooks import doc_events

        employee_events = doc_events.get("Employee", {})
        validate = employee_events.get("validate", [])

        # validate can be a string or list
        if isinstance(validate, str):
            validate = [validate]

        found = any(
            "cp22_mandate_service.check_onboarding_block" in handler
            for handler in validate
        )
        self.assertTrue(
            found,
            "cp22_mandate_service.check_onboarding_block not found in Employee validate hook",
        )

    def test_lhdn_cp22_validate_shows_mandate_alert(self):
        """hooks.py registers LHDN CP22 validate with show_online_mandate_alert."""
        from lhdn_payroll_integration.hooks import doc_events

        cp22_events = doc_events.get("LHDN CP22", {})
        validate = cp22_events.get("validate", [])

        if isinstance(validate, str):
            validate = [validate]

        found = any(
            "cp22_mandate_service.show_online_mandate_alert" in handler
            for handler in validate
        )
        self.assertTrue(
            found,
            "cp22_mandate_service.show_online_mandate_alert not found in LHDN CP22 validate hook",
        )
