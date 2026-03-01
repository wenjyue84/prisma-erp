"""
Tests for US-155: PDPA 2024 Amendment Payroll Data Protection Compliance Module.

TDD GREEN: bench --site frontend run-tests --module lhdn_payroll_integration.tests.test_pdpa_compliance
"""
import json
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, today, add_years, getdate

from lhdn_payroll_integration.lhdn_payroll_integration.services.pdpa_compliance_service import (
    _create_access_log,
    export_employee_payroll_data,
    flag_old_salary_slips,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_company(name="__Test PDPA Compliance Co", abbr="TPCC"):
    if not frappe.db.exists("Company", name):
        frappe.get_doc({
            "doctype": "Company",
            "company_name": name,
            "abbr": abbr,
            "default_currency": "MYR",
            "country": "Malaysia",
        }).insert(ignore_permissions=True)
    return name


def _ensure_employee(name="__PDPA Test Emp", company=None):
    company = company or _ensure_company()
    if frappe.db.exists("Employee", {"employee_name": name}):
        return frappe.db.get_value("Employee", {"employee_name": name}, "name")
    emp = frappe.get_doc({
        "doctype": "Employee",
        "first_name": name,
        "employee_name": name,
        "company": company,
        "gender": "Male",
        "date_of_birth": "1990-01-01",
        # Use today so CP22 30-day deadline check does not block save
        "date_of_joining": today(),
        # Explicitly mark as not pending to bypass CP22 onboarding block
        "custom_cp22_submission_status": "Not Required",
    })
    emp.insert(ignore_permissions=True)
    return emp.name


# ---------------------------------------------------------------------------
# Employee Payroll Consent DocType
# ---------------------------------------------------------------------------

class TestEmployeePayrollConsentDocType(FrappeTestCase):
    """Test that Employee Payroll Consent DocType exists with required fields."""

    def test_doctype_exists(self):
        self.assertTrue(
            frappe.db.exists("DocType", "Employee Payroll Consent"),
            "Employee Payroll Consent DocType must exist",
        )

    def test_has_employee_field(self):
        meta = frappe.get_meta("Employee Payroll Consent")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("employee", field_names)

    def test_has_consent_version_field(self):
        meta = frappe.get_meta("Employee Payroll Consent")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("consent_version", field_names)

    def test_has_consent_date_field(self):
        meta = frappe.get_meta("Employee Payroll Consent")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("consent_date", field_names)

    def test_has_data_categories_field(self):
        meta = frappe.get_meta("Employee Payroll Consent")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("data_categories", field_names)

    def test_has_status_field(self):
        meta = frappe.get_meta("Employee Payroll Consent")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("status", field_names)

    def test_has_consent_given_field(self):
        meta = frappe.get_meta("Employee Payroll Consent")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("consent_given", field_names)

    def test_has_track_changes(self):
        meta = frappe.get_meta("Employee Payroll Consent")
        self.assertEqual(meta.track_changes, 1, "Must have track_changes for audit trail")


class TestEmployeePayrollConsentCreation(FrappeTestCase):
    """Test creating Employee Payroll Consent records."""

    def setUp(self):
        self.company = _ensure_company()
        self.employee = _ensure_employee(company=self.company)

    def test_can_create_consent_record(self):
        doc = frappe.get_doc({
            "doctype": "Employee Payroll Consent",
            "employee": self.employee,
            "company": self.company,
            "consent_version": "2025-v1",
            "consent_given": 1,
            "consent_date": now_datetime(),
            "data_categories": "NRIC, Salary, Bank Account, EPF Number, SOCSO Number",
            "status": "Active",
        })
        doc.insert(ignore_permissions=True)
        self.assertTrue(doc.name.startswith("PDPA-CONSENT-"))

    def test_consent_version_and_timestamp_recorded(self):
        doc = frappe.get_doc({
            "doctype": "Employee Payroll Consent",
            "employee": self.employee,
            "company": self.company,
            "consent_version": "2025-v2",
            "consent_given": 1,
            "consent_date": now_datetime(),
            "status": "Active",
        })
        doc.insert(ignore_permissions=True)
        fetched = frappe.get_doc("Employee Payroll Consent", doc.name)
        self.assertEqual(fetched.consent_version, "2025-v2")
        self.assertIsNotNone(fetched.consent_date)

    def test_data_categories_stored(self):
        cats = "NRIC, Salary, Bank Account, EPF Number"
        doc = frappe.get_doc({
            "doctype": "Employee Payroll Consent",
            "employee": self.employee,
            "company": self.company,
            "consent_version": "2025-v1",
            "consent_given": 1,
            "consent_date": now_datetime(),
            "data_categories": cats,
            "status": "Active",
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Employee Payroll Consent", doc.name, "data_categories"), cats)


# ---------------------------------------------------------------------------
# Payroll Data Access Log DocType
# ---------------------------------------------------------------------------

class TestPayrollDataAccessLogDocType(FrappeTestCase):
    """Test that Payroll Data Access Log DocType exists with required fields."""

    def test_doctype_exists(self):
        self.assertTrue(
            frappe.db.exists("DocType", "Payroll Data Access Log"),
            "Payroll Data Access Log DocType must exist",
        )

    def test_has_event_type_field(self):
        meta = frappe.get_meta("Payroll Data Access Log")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("event_type", field_names)

    def test_has_document_type_field(self):
        meta = frappe.get_meta("Payroll Data Access Log")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("document_type", field_names)

    def test_has_document_name_field(self):
        meta = frappe.get_meta("Payroll Data Access Log")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("document_name", field_names)

    def test_has_user_field(self):
        meta = frappe.get_meta("Payroll Data Access Log")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("user", field_names)

    def test_has_timestamp_field(self):
        meta = frappe.get_meta("Payroll Data Access Log")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("timestamp", field_names)

    def test_has_employee_field(self):
        meta = frappe.get_meta("Payroll Data Access Log")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("employee", field_names)

    def test_has_data_categories_accessed_field(self):
        meta = frappe.get_meta("Payroll Data Access Log")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("data_categories_accessed", field_names)


# ---------------------------------------------------------------------------
# Audit Logging on Salary Slip Access Events
# ---------------------------------------------------------------------------

class TestPayrollDataAccessLogCreation(FrappeTestCase):
    """Confirm that audit log entries are created on Salary Slip view/print/email."""

    def setUp(self):
        self.company = _ensure_company()
        self.employee = _ensure_employee(company=self.company)

    def _count_logs(self, event_type, doc_name):
        return frappe.db.count(
            "Payroll Data Access Log",
            filters={"event_type": event_type, "document_name": doc_name},
        )

    def test_view_access_creates_log_entry(self):
        doc_name = "SAL-SLIP-TEST-VIEW-001"
        before = self._count_logs("View", doc_name)
        _create_access_log("View", "Salary Slip", doc_name, self.employee)
        after = self._count_logs("View", doc_name)
        self.assertEqual(after, before + 1, "A View access log must be created")

    def test_print_access_creates_log_entry(self):
        doc_name = "SAL-SLIP-TEST-PRINT-001"
        before = self._count_logs("Print", doc_name)
        _create_access_log("Print", "Salary Slip", doc_name, self.employee)
        after = self._count_logs("Print", doc_name)
        self.assertEqual(after, before + 1, "A Print access log must be created")

    def test_email_access_creates_log_entry(self):
        doc_name = "SAL-SLIP-TEST-EMAIL-001"
        before = self._count_logs("Email", doc_name)
        _create_access_log("Email", "Salary Slip", doc_name, self.employee)
        after = self._count_logs("Email", doc_name)
        self.assertEqual(after, before + 1, "An Email access log must be created")

    def test_log_entry_records_user(self):
        doc_name = "SAL-SLIP-TEST-USER-001"
        _create_access_log("View", "Salary Slip", doc_name, self.employee)
        log = frappe.db.get_value(
            "Payroll Data Access Log",
            {"document_name": doc_name},
            ["user", "timestamp"],
            as_dict=True,
        )
        self.assertIsNotNone(log)
        self.assertIsNotNone(log.get("user"))
        self.assertIsNotNone(log.get("timestamp"))

    def test_log_entry_records_employee(self):
        doc_name = "SAL-SLIP-TEST-EMP-001"
        _create_access_log("View", "Salary Slip", doc_name, self.employee)
        emp_logged = frappe.db.get_value(
            "Payroll Data Access Log",
            {"document_name": doc_name},
            "employee",
        )
        self.assertEqual(emp_logged, self.employee)


# ---------------------------------------------------------------------------
# Data Subject Request — employee payroll data export
# ---------------------------------------------------------------------------

class TestDataSubjectRequestExport(FrappeTestCase):
    """Test employee payroll data export for data portability right."""

    def setUp(self):
        self.company = _ensure_company()
        self.employee = _ensure_employee(company=self.company)

    def test_export_returns_employee_info(self):
        result = export_employee_payroll_data(self.employee)
        self.assertEqual(result["employee"], self.employee)
        self.assertIn("employee_name", result)
        self.assertIn("export_generated_at", result)

    def test_export_contains_salary_slips_key(self):
        result = export_employee_payroll_data(self.employee)
        self.assertIn("salary_slips", result)
        self.assertIsInstance(result["salary_slips"], list)

    def test_export_contains_consent_records_key(self):
        result = export_employee_payroll_data(self.employee)
        self.assertIn("consent_records", result)
        self.assertIsInstance(result["consent_records"], list)

    def test_export_contains_access_log_key(self):
        result = export_employee_payroll_data(self.employee)
        self.assertIn("access_log_summary", result)
        self.assertIsInstance(result["access_log_summary"], list)

    def test_export_is_json_serializable(self):
        result = export_employee_payroll_data(self.employee)
        try:
            json.dumps(result)
        except (TypeError, ValueError) as e:
            self.fail(f"Export result is not JSON-serializable: {e}")

    def test_export_consent_records_include_logged_consent(self):
        # Create a consent record first
        frappe.get_doc({
            "doctype": "Employee Payroll Consent",
            "employee": self.employee,
            "company": self.company,
            "consent_version": "2025-v1",
            "consent_given": 1,
            "consent_date": now_datetime(),
            "status": "Active",
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = export_employee_payroll_data(self.employee)
        self.assertGreater(len(result["consent_records"]), 0)


# ---------------------------------------------------------------------------
# Retention Enforcement
# ---------------------------------------------------------------------------

class TestRetentionEnforcement(FrappeTestCase):
    """Test payroll data retention flag logic."""

    def test_flag_old_salary_slips_returns_dict(self):
        result = flag_old_salary_slips(retention_years=7)
        self.assertIn("retention_years", result)
        self.assertIn("cutoff_date", result)
        self.assertIn("count", result)
        self.assertIn("salary_slips", result)

    def test_retention_years_configurable(self):
        result_7 = flag_old_salary_slips(retention_years=7)
        result_3 = flag_old_salary_slips(retention_years=3)
        self.assertEqual(result_7["retention_years"], 7)
        self.assertEqual(result_3["retention_years"], 3)

    def test_cutoff_date_is_correct(self):
        result = flag_old_salary_slips(retention_years=7)
        expected = str(add_years(today(), -7))
        self.assertEqual(str(result["cutoff_date"]), expected)

    def test_returns_list_of_salary_slips(self):
        result = flag_old_salary_slips(retention_years=7)
        self.assertIsInstance(result["salary_slips"], list)

    def test_count_matches_list_length(self):
        result = flag_old_salary_slips(retention_years=7)
        self.assertEqual(result["count"], len(result["salary_slips"]))
