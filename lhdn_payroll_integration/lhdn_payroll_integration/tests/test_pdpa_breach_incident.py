"""
Tests for US-200: PDPA 2024 DPO Appointment Registry and
72-Hour Payroll Data Breach Notification Workflow.

TDD GREEN: bench --site frontend run-tests --module lhdn_payroll_integration.tests.test_pdpa_breach_incident
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, add_to_date, today, add_days


class TestPDPADPORegistryDocType(FrappeTestCase):
    """Test that PDPA DPO Registry DocType exists with required fields."""

    def test_doctype_exists(self):
        self.assertTrue(
            frappe.db.exists("DocType", "PDPA DPO Registry"),
            "PDPA DPO Registry DocType must exist"
        )

    def test_doctype_has_dpo_name_field(self):
        meta = frappe.get_meta("PDPA DPO Registry")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("dpo_name", field_names)

    def test_doctype_has_dpo_email_field(self):
        meta = frappe.get_meta("PDPA DPO Registry")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("dpo_email", field_names)

    def test_doctype_has_dpo_phone_field(self):
        meta = frappe.get_meta("PDPA DPO Registry")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("dpo_phone", field_names)

    def test_doctype_has_dpo_appointment_date_field(self):
        meta = frappe.get_meta("PDPA DPO Registry")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("dpo_appointment_date", field_names)

    def test_doctype_has_commissioner_registration_date_field(self):
        meta = frappe.get_meta("PDPA DPO Registry")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("dpo_commissioner_registration_date", field_names)

    def test_doctype_has_company_field(self):
        meta = frappe.get_meta("PDPA DPO Registry")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("company", field_names)

    def test_doctype_has_track_changes(self):
        meta = frappe.get_meta("PDPA DPO Registry")
        self.assertEqual(meta.track_changes, 1, "PDPA DPO Registry must have track_changes for audit log")


class TestPDPADPORegistryCreation(FrappeTestCase):
    """Test creating and validating PDPA DPO Registry records."""

    def _get_or_create_test_company(self):
        company_name = "_Test PDPA DPO Co"
        if not frappe.db.exists("Company", company_name):
            company = frappe.get_doc({
                "doctype": "Company",
                "company_name": company_name,
                "abbr": "TPDC",
                "default_currency": "MYR",
                "country": "Malaysia",
            })
            company.insert(ignore_permissions=True)
        return company_name

    def test_can_create_dpo_registry(self):
        company = self._get_or_create_test_company()
        # Remove any existing registry for this company
        existing = frappe.db.get_value("PDPA DPO Registry", {"company": company}, "name")
        if existing:
            frappe.delete_doc("PDPA DPO Registry", existing, ignore_permissions=True, force=True)

        doc = frappe.get_doc({
            "doctype": "PDPA DPO Registry",
            "company": company,
            "dpo_name": "John DPO",
            "dpo_email": "dpo@test.com",
            "dpo_phone": "+60123456789",
            "dpo_appointment_date": today(),
        })
        doc.insert(ignore_permissions=True)
        self.assertTrue(doc.name)

    def test_21day_deadline_computed_when_not_registered(self):
        company = self._get_or_create_test_company()
        existing = frappe.db.get_value("PDPA DPO Registry", {"company": company}, "name")
        if existing:
            frappe.delete_doc("PDPA DPO Registry", existing, ignore_permissions=True, force=True)

        appointment_date = add_days(today(), -5)  # appointed 5 days ago
        doc = frappe.get_doc({
            "doctype": "PDPA DPO Registry",
            "company": company,
            "dpo_name": "Jane DPO",
            "dpo_email": "jane@test.com",
            "dpo_appointment_date": appointment_date,
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.days_until_21day_deadline, 16, "Should have 16 days remaining (21 - 5)")

    def test_overdue_status_when_21days_exceeded(self):
        company = self._get_or_create_test_company()
        existing = frappe.db.get_value("PDPA DPO Registry", {"company": company}, "name")
        if existing:
            frappe.delete_doc("PDPA DPO Registry", existing, ignore_permissions=True, force=True)

        appointment_date = add_days(today(), -25)  # appointed 25 days ago (overdue)
        doc = frappe.get_doc({
            "doctype": "PDPA DPO Registry",
            "company": company,
            "dpo_name": "Bob DPO",
            "dpo_email": "bob@test.com",
            "dpo_appointment_date": appointment_date,
        })
        doc.insert(ignore_permissions=True)
        self.assertIn("overdue", doc.registration_deadline_status.lower())

    def test_compliant_status_when_registered_in_time(self):
        company = self._get_or_create_test_company()
        existing = frappe.db.get_value("PDPA DPO Registry", {"company": company}, "name")
        if existing:
            frappe.delete_doc("PDPA DPO Registry", existing, ignore_permissions=True, force=True)

        appointment_date = add_days(today(), -10)
        registration_date = add_days(today(), -5)
        doc = frappe.get_doc({
            "doctype": "PDPA DPO Registry",
            "company": company,
            "dpo_name": "Alice DPO",
            "dpo_email": "alice@test.com",
            "dpo_appointment_date": appointment_date,
            "dpo_commissioner_registration_date": registration_date,
        })
        doc.insert(ignore_permissions=True)
        self.assertIn("compliant", doc.registration_deadline_status.lower())


class TestPDPABreachIncidentDocType(FrappeTestCase):
    """Test PDPA Breach Incident DocType exists and has required fields."""

    def test_doctype_exists(self):
        self.assertTrue(
            frappe.db.exists("DocType", "PDPA Breach Incident"),
            "PDPA Breach Incident DocType must exist"
        )

    def test_doctype_has_discovery_datetime_field(self):
        meta = frappe.get_meta("PDPA Breach Incident")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("discovery_datetime", field_names)

    def test_doctype_has_breach_type_field(self):
        meta = frappe.get_meta("PDPA Breach Incident")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("breach_type", field_names)

    def test_doctype_has_affected_records_count_field(self):
        meta = frappe.get_meta("PDPA Breach Incident")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("affected_records_count", field_names)

    def test_doctype_has_data_categories_affected_field(self):
        meta = frappe.get_meta("PDPA Breach Incident")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("data_categories_affected", field_names)

    def test_doctype_has_risk_assessment_field(self):
        meta = frappe.get_meta("PDPA Breach Incident")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("risk_assessment", field_names)

    def test_doctype_has_commissioner_notified_datetime_field(self):
        meta = frappe.get_meta("PDPA Breach Incident")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("commissioner_notified_datetime", field_names)

    def test_doctype_has_employee_notification_datetime_field(self):
        meta = frappe.get_meta("PDPA Breach Incident")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("employee_notification_datetime", field_names)

    def test_doctype_has_status_field(self):
        meta = frappe.get_meta("PDPA Breach Incident")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("status", field_names)

    def test_doctype_has_track_changes_enabled(self):
        meta = frappe.get_meta("PDPA Breach Incident")
        self.assertEqual(meta.track_changes, 1, "PDPA Breach Incident must have track_changes enabled for audit log")


class TestPDPABreachIncidentCreation(FrappeTestCase):
    """Test creating a PDPA Breach Incident document."""

    def _get_or_create_test_company(self):
        company_name = "_Test PDPA Breach Co"
        if not frappe.db.exists("Company", company_name):
            company = frappe.get_doc({
                "doctype": "Company",
                "company_name": company_name,
                "abbr": "TPBC",
                "default_currency": "MYR",
                "country": "Malaysia",
            })
            company.insert(ignore_permissions=True)
        return company_name

    def test_can_create_breach_incident(self):
        company = self._get_or_create_test_company()
        doc = frappe.get_doc({
            "doctype": "PDPA Breach Incident",
            "company": company,
            "discovery_datetime": now_datetime(),
            "breach_type": "Unauthorised Access",
            "affected_records_count": 50,
            "data_categories_affected": "IC Numbers, Bank Account Numbers",
            "risk_assessment": "High risk - sensitive financial data exposed",
            "status": "Draft",
        })
        doc.insert(ignore_permissions=True)
        self.assertTrue(doc.name.startswith("PDPA-BREACH-"))

    def test_hours_since_discovery_computed(self):
        company = self._get_or_create_test_company()
        past_time = add_to_date(now_datetime(), hours=-10)
        doc = frappe.get_doc({
            "doctype": "PDPA Breach Incident",
            "company": company,
            "discovery_datetime": past_time,
            "breach_type": "Data Loss",
            "affected_records_count": 10,
            "data_categories_affected": "Salary Information",
            "risk_assessment": "Medium risk",
            "status": "Draft",
        })
        doc.insert(ignore_permissions=True)
        self.assertGreaterEqual(
            doc.hours_since_discovery, 9.9,
            "hours_since_discovery must be computed on save"
        )

    def test_commissioner_deadline_status_shows_remaining_hours(self):
        company = self._get_or_create_test_company()
        past_time = add_to_date(now_datetime(), hours=-5)
        doc = frappe.get_doc({
            "doctype": "PDPA Breach Incident",
            "company": company,
            "discovery_datetime": past_time,
            "breach_type": "Data Theft",
            "affected_records_count": 25,
            "data_categories_affected": "Salary Information",
            "risk_assessment": "High risk",
            "status": "Draft",
        })
        doc.insert(ignore_permissions=True)
        self.assertIn("remaining", doc.commissioner_deadline_status.lower())

    def test_commissioner_deadline_overdue_after_72h(self):
        company = self._get_or_create_test_company()
        past_time = add_to_date(now_datetime(), hours=-80)
        doc = frappe.get_doc({
            "doctype": "PDPA Breach Incident",
            "company": company,
            "discovery_datetime": past_time,
            "breach_type": "System Compromise",
            "affected_records_count": 100,
            "data_categories_affected": "All payroll data",
            "risk_assessment": "Critical",
            "status": "Draft",
        })
        doc.insert(ignore_permissions=True)
        self.assertIn("overdue", doc.commissioner_deadline_status.lower())

    def test_employee_notification_deadline_set_after_commissioner_notified(self):
        company = self._get_or_create_test_company()
        notified_time = now_datetime()
        doc = frappe.get_doc({
            "doctype": "PDPA Breach Incident",
            "company": company,
            "discovery_datetime": add_to_date(now_datetime(), hours=-10),
            "breach_type": "Insider Threat",
            "affected_records_count": 30,
            "data_categories_affected": "EPF/SOCSO Details",
            "risk_assessment": "Medium risk",
            "commissioner_notified_datetime": notified_time,
            "status": "Commissioner Notified",
        })
        doc.insert(ignore_permissions=True)
        self.assertIsNotNone(
            doc.employee_notification_deadline,
            "Employee notification deadline must be set after Commissioner notified"
        )

    def test_commissioner_notification_letter_generated(self):
        company = self._get_or_create_test_company()
        doc = frappe.get_doc({
            "doctype": "PDPA Breach Incident",
            "company": company,
            "discovery_datetime": now_datetime(),
            "breach_type": "Ransomware",
            "affected_records_count": 200,
            "data_categories_affected": "Full payroll records",
            "risk_assessment": "Critical - full payroll data encrypted",
            "status": "Draft",
        })
        doc.insert(ignore_permissions=True)
        letter = doc.get_commissioner_notification_letter()
        self.assertIn("Personal Data Protection Commissioner", letter)
        self.assertIn(str(doc.affected_records_count), letter)
        self.assertIn(doc.breach_type, letter)
        self.assertIn(doc.risk_assessment, letter)

    def test_employee_notification_email_generated(self):
        company = self._get_or_create_test_company()
        doc = frappe.get_doc({
            "doctype": "PDPA Breach Incident",
            "company": company,
            "discovery_datetime": now_datetime(),
            "breach_type": "Data Loss",
            "affected_records_count": 15,
            "data_categories_affected": "Bank Account Numbers",
            "risk_assessment": "High risk",
            "status": "Draft",
        })
        doc.insert(ignore_permissions=True)
        email = doc.get_employee_breach_notification_email()
        self.assertIn(company, email)
        self.assertIn(doc.data_categories_affected, email)
        self.assertIn("Commissioner", email)
