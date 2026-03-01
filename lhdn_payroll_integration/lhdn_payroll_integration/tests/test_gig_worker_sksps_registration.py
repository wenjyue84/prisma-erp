"""Tests for US-181: Gig Workers Act 2025 — Auto-Register Gig Workers Under PERKESO SKSPS.

Verifies the PERKESO SKSPS auto-registration service for platform gig workers
under the Gig Workers Act 2025 (Act 872) and SEIA Act 789.

Test coverage:
  - Constants (statuses, URLs, batch size, error codes, required fields, age limits)
  - build_registration_payload() — payload construction from Employee record
  - validate_registration_payload() — required field validation
  - get_registration_status() — status retrieval from Employee custom fields
  - update_registration_status() — status persistence
  - is_sksps_deduction_allowed() — deduction blocking logic
  - submit_sksps_registration() — end-to-end registration with mocked API
  - _create_failed_registration_task() — HR task creation for failures
  - bulk_register_gig_workers() — batch registration
  - check_sksps_age_eligibility() — age range validation (15–65)
"""
from unittest.mock import patch, MagicMock, PropertyMock
from frappe.tests.utils import FrappeTestCase


class TestSkspsConstants(FrappeTestCase):
    """Module-level constants are correct per SKSPS/SEIA Act 789 and Act 872."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_sksps_registration_service import (
            STATUS_NOT_REGISTERED,
            STATUS_PENDING,
            STATUS_ACTIVE,
            STATUS_REJECTED,
            ASSIST_SANDBOX_URL,
            ASSIST_PRODUCTION_URL,
            SKSPS_REGISTRATION_ENDPOINT,
            BULK_BATCH_SIZE,
            PERKESO_ERROR_CODES,
            REQUIRED_REGISTRATION_FIELDS,
            GIG_WORKER_EMPLOYMENT_TYPE,
            SKSPS_MIN_AGE,
            SKSPS_MAX_AGE,
        )
        self.status_not_reg = STATUS_NOT_REGISTERED
        self.status_pending = STATUS_PENDING
        self.status_active = STATUS_ACTIVE
        self.status_rejected = STATUS_REJECTED
        self.sandbox_url = ASSIST_SANDBOX_URL
        self.prod_url = ASSIST_PRODUCTION_URL
        self.endpoint = SKSPS_REGISTRATION_ENDPOINT
        self.batch_size = BULK_BATCH_SIZE
        self.error_codes = PERKESO_ERROR_CODES
        self.required_fields = REQUIRED_REGISTRATION_FIELDS
        self.gig_type = GIG_WORKER_EMPLOYMENT_TYPE
        self.min_age = SKSPS_MIN_AGE
        self.max_age = SKSPS_MAX_AGE

    def test_status_constants(self):
        self.assertEqual(self.status_not_reg, "Not Registered")
        self.assertEqual(self.status_pending, "Pending")
        self.assertEqual(self.status_active, "Active")
        self.assertEqual(self.status_rejected, "Rejected")

    def test_assist_urls_are_https(self):
        self.assertTrue(self.sandbox_url.startswith("https://"))
        self.assertTrue(self.prod_url.startswith("https://"))

    def test_sandbox_url_contains_sandbox(self):
        self.assertIn("sandbox", self.sandbox_url)

    def test_production_url_is_assist_perkeso(self):
        self.assertIn("assist.perkeso.gov.my", self.prod_url)

    def test_registration_endpoint(self):
        self.assertEqual(self.endpoint, "/sksps/registration")

    def test_bulk_batch_size_is_50(self):
        self.assertEqual(self.batch_size, 50)

    def test_error_codes_are_non_empty(self):
        self.assertIsInstance(self.error_codes, dict)
        self.assertGreater(len(self.error_codes), 5)
        for code, msg in self.error_codes.items():
            self.assertTrue(code.startswith("ERR_"), f"Error code {code} should start with ERR_")
            self.assertTrue(len(msg) > 10, f"Error message for {code} too short")

    def test_required_registration_fields(self):
        self.assertEqual(len(self.required_fields), 8)
        self.assertIn("ic_passport_number", self.required_fields)
        self.assertIn("full_name", self.required_fields)
        self.assertIn("date_of_birth", self.required_fields)
        self.assertIn("platform_provider_code", self.required_fields)

    def test_gig_worker_employment_type(self):
        self.assertEqual(self.gig_type, "Gig / Platform Worker")

    def test_age_limits(self):
        self.assertEqual(self.min_age, 15)
        self.assertEqual(self.max_age, 65)


class TestBuildRegistrationPayload(FrappeTestCase):
    """build_registration_payload() constructs correct ASSIST payload."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_sksps_registration_service import (
            build_registration_payload,
        )
        self.build = build_registration_payload

    def _make_employee(self, **overrides):
        base = {
            "name": "EMP-GIG-001",
            "employee_name": "Ahmad bin Ali",
            "custom_icpassport_number": "901234567890",
            "date_of_birth": "1990-05-15",
            "gender": "Male",
            "custom_nationality": "Malaysian",
            "cell_phone": "0123456789",
            "company": "Test Platform Sdn Bhd",
            "current_address": "123 Jalan Gig, KL",
        }
        base.update(overrides)
        return base

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._get_platform_provider_code")
    def test_returns_dict_with_expected_keys(self, mock_code):
        mock_code.return_value = "PLT-001"
        emp = self._make_employee()
        result = self.build(emp)
        self.assertIsInstance(result, dict)
        for key in ["ic_passport_number", "full_name", "date_of_birth",
                     "gender", "nationality", "address", "contact_number",
                     "platform_provider_code", "employee_id", "company"]:
            self.assertIn(key, result, f"Missing key: {key}")

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._get_platform_provider_code")
    def test_ic_number_from_custom_field(self, mock_code):
        mock_code.return_value = "PLT-001"
        emp = self._make_employee(custom_icpassport_number="901234567890")
        result = self.build(emp)
        self.assertEqual(result["ic_passport_number"], "901234567890")

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._get_platform_provider_code")
    def test_full_name_from_employee_name(self, mock_code):
        mock_code.return_value = "PLT-001"
        emp = self._make_employee(employee_name="Siti binti Hassan")
        result = self.build(emp)
        self.assertEqual(result["full_name"], "Siti binti Hassan")

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._get_platform_provider_code")
    def test_platform_provider_code_from_company(self, mock_code):
        mock_code.return_value = "PLT-GRAB-001"
        emp = self._make_employee()
        result = self.build(emp)
        self.assertEqual(result["platform_provider_code"], "PLT-GRAB-001")

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._get_platform_provider_code")
    def test_strips_whitespace(self, mock_code):
        mock_code.return_value = "PLT-001"
        emp = self._make_employee(
            custom_icpassport_number="  901234567890  ",
            employee_name="  Ahmad  ",
        )
        result = self.build(emp)
        self.assertEqual(result["ic_passport_number"], "901234567890")
        self.assertEqual(result["full_name"], "Ahmad")


class TestValidateRegistrationPayload(FrappeTestCase):
    """validate_registration_payload() checks all required fields."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_sksps_registration_service import (
            validate_registration_payload,
        )
        self.validate = validate_registration_payload

    def _make_payload(self, **overrides):
        base = {
            "ic_passport_number": "901234567890",
            "full_name": "Ahmad bin Ali",
            "date_of_birth": "1990-05-15",
            "gender": "Male",
            "nationality": "Malaysian",
            "address": "123 Jalan Test",
            "contact_number": "0123456789",
            "platform_provider_code": "PLT-001",
        }
        base.update(overrides)
        return base

    def test_valid_payload_passes(self):
        result = self.validate(self._make_payload())
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["missing"]), 0)

    def test_missing_ic_number_fails(self):
        result = self.validate(self._make_payload(ic_passport_number=""))
        self.assertFalse(result["valid"])
        self.assertIn("ic_passport_number", result["missing"])

    def test_missing_full_name_fails(self):
        result = self.validate(self._make_payload(full_name=""))
        self.assertFalse(result["valid"])
        self.assertIn("full_name", result["missing"])

    def test_missing_platform_code_fails(self):
        result = self.validate(self._make_payload(platform_provider_code=""))
        self.assertFalse(result["valid"])
        self.assertIn("platform_provider_code", result["missing"])

    def test_multiple_missing_fields(self):
        result = self.validate(self._make_payload(
            ic_passport_number="",
            full_name="",
            date_of_birth="",
        ))
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["missing"]), 3)

    def test_whitespace_only_counts_as_missing(self):
        result = self.validate(self._make_payload(full_name="   "))
        self.assertFalse(result["valid"])
        self.assertIn("full_name", result["missing"])

    def test_none_field_counts_as_missing(self):
        payload = self._make_payload()
        payload["gender"] = None
        result = self.validate(payload)
        self.assertFalse(result["valid"])
        self.assertIn("gender", result["missing"])


class TestGetRegistrationStatus(FrappeTestCase):
    """get_registration_status() reads custom fields from Employee."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_sksps_registration_service import (
            get_registration_status,
            STATUS_NOT_REGISTERED,
            STATUS_ACTIVE,
            STATUS_REJECTED,
            PERKESO_ERROR_CODES,
        )
        self.get_status = get_registration_status
        self.STATUS_NOT_REG = STATUS_NOT_REGISTERED
        self.STATUS_ACTIVE = STATUS_ACTIVE
        self.STATUS_REJECTED = STATUS_REJECTED
        self.ERROR_CODES = PERKESO_ERROR_CODES

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_returns_not_registered_when_no_fields_set(self, mock_frappe):
        mock_frappe.db.get_value.return_value = {
            "custom_sksps_registration_status": None,
            "custom_sksps_reference_number": None,
            "custom_sksps_registration_date": None,
            "custom_sksps_error_code": None,
        }
        result = self.get_status("EMP-001")
        self.assertEqual(result["status"], self.STATUS_NOT_REG)
        self.assertEqual(result["reference_number"], "")

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_returns_active_with_reference(self, mock_frappe):
        mock_frappe.db.get_value.return_value = {
            "custom_sksps_registration_status": "Active",
            "custom_sksps_reference_number": "SKSPS-2026-001234",
            "custom_sksps_registration_date": "2026-01-15",
            "custom_sksps_error_code": None,
        }
        result = self.get_status("EMP-001")
        self.assertEqual(result["status"], self.STATUS_ACTIVE)
        self.assertEqual(result["reference_number"], "SKSPS-2026-001234")

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_returns_rejected_with_error_message(self, mock_frappe):
        mock_frappe.db.get_value.return_value = {
            "custom_sksps_registration_status": "Rejected",
            "custom_sksps_reference_number": None,
            "custom_sksps_registration_date": None,
            "custom_sksps_error_code": "ERR_INVALID_IC",
        }
        result = self.get_status("EMP-001")
        self.assertEqual(result["status"], self.STATUS_REJECTED)
        self.assertEqual(result["error_code"], "ERR_INVALID_IC")
        self.assertEqual(result["error_message"], self.ERROR_CODES["ERR_INVALID_IC"])

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_handles_employee_not_found(self, mock_frappe):
        mock_frappe.db.get_value.return_value = None
        result = self.get_status("NONEXISTENT")
        self.assertEqual(result["status"], self.STATUS_NOT_REG)

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_handles_db_exception(self, mock_frappe):
        mock_frappe.db.get_value.side_effect = Exception("DB connection lost")
        result = self.get_status("EMP-001")
        self.assertEqual(result["status"], self.STATUS_NOT_REG)


class TestUpdateRegistrationStatus(FrappeTestCase):
    """update_registration_status() persists status to Employee custom fields."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_sksps_registration_service import (
            update_registration_status,
            STATUS_ACTIVE,
            STATUS_PENDING,
            STATUS_REJECTED,
        )
        self.update = update_registration_status
        self.STATUS_ACTIVE = STATUS_ACTIVE
        self.STATUS_PENDING = STATUS_PENDING
        self.STATUS_REJECTED = STATUS_REJECTED

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_sets_status_pending(self, mock_frappe):
        self.update("EMP-001", self.STATUS_PENDING)
        mock_frappe.db.set_value.assert_called_once()
        args = mock_frappe.db.set_value.call_args
        self.assertEqual(args[0][0], "Employee")
        self.assertEqual(args[0][1], "EMP-001")
        updates = args[0][2]
        self.assertEqual(updates["custom_sksps_registration_status"], "Pending")

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.nowdate")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_sets_active_with_date_and_ref(self, mock_frappe, mock_nowdate):
        mock_nowdate.return_value = "2026-03-01"
        self.update("EMP-001", self.STATUS_ACTIVE, reference_number="SKSPS-REF-001")
        args = mock_frappe.db.set_value.call_args
        updates = args[0][2]
        self.assertEqual(updates["custom_sksps_registration_status"], "Active")
        self.assertEqual(updates["custom_sksps_reference_number"], "SKSPS-REF-001")
        self.assertEqual(updates["custom_sksps_registration_date"], "2026-03-01")

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_sets_rejected_with_error_code(self, mock_frappe):
        self.update("EMP-001", self.STATUS_REJECTED, error_code="ERR_DUPLICATE")
        args = mock_frappe.db.set_value.call_args
        updates = args[0][2]
        self.assertEqual(updates["custom_sksps_registration_status"], "Rejected")
        self.assertEqual(updates["custom_sksps_error_code"], "ERR_DUPLICATE")


class TestIsSkspsDeductionAllowed(FrappeTestCase):
    """is_sksps_deduction_allowed() blocks deduction unless Active."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_sksps_registration_service import (
            is_sksps_deduction_allowed,
            STATUS_NOT_REGISTERED,
            STATUS_PENDING,
            STATUS_ACTIVE,
            STATUS_REJECTED,
        )
        self.check = is_sksps_deduction_allowed
        self.STATUS_NOT_REG = STATUS_NOT_REGISTERED
        self.STATUS_PENDING = STATUS_PENDING
        self.STATUS_ACTIVE = STATUS_ACTIVE
        self.STATUS_REJECTED = STATUS_REJECTED

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.get_registration_status")
    def test_allowed_when_active(self, mock_status):
        mock_status.return_value = {
            "status": "Active",
            "reference_number": "REF-001",
            "registration_date": "2026-01-15",
            "error_code": "",
            "error_message": "",
        }
        result = self.check("EMP-001")
        self.assertTrue(result["allowed"])
        self.assertEqual(result["status"], "Active")
        self.assertEqual(result["reason"], "")

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.get_registration_status")
    def test_blocked_when_not_registered(self, mock_status):
        mock_status.return_value = {
            "status": "Not Registered",
            "reference_number": "",
            "registration_date": None,
            "error_code": "",
            "error_message": "",
        }
        result = self.check("EMP-001")
        self.assertFalse(result["allowed"])
        self.assertIn("not registered", result["reason"].lower())

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.get_registration_status")
    def test_blocked_when_pending(self, mock_status):
        mock_status.return_value = {
            "status": "Pending",
            "reference_number": "",
            "registration_date": None,
            "error_code": "",
            "error_message": "",
        }
        result = self.check("EMP-001")
        self.assertFalse(result["allowed"])
        self.assertIn("pending", result["reason"].lower())

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.get_registration_status")
    def test_blocked_when_rejected(self, mock_status):
        mock_status.return_value = {
            "status": "Rejected",
            "reference_number": "",
            "registration_date": None,
            "error_code": "ERR_INVALID_IC",
            "error_message": "Invalid IC number",
        }
        result = self.check("EMP-001")
        self.assertFalse(result["allowed"])
        self.assertIn("rejected", result["reason"].lower())


class TestSubmitSkspsRegistration(FrappeTestCase):
    """submit_sksps_registration() end-to-end with mocked API."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_sksps_registration_service import (
            submit_sksps_registration,
            STATUS_ACTIVE,
            STATUS_REJECTED,
            STATUS_NOT_REGISTERED,
        )
        self.submit = submit_sksps_registration
        self.STATUS_ACTIVE = STATUS_ACTIVE
        self.STATUS_REJECTED = STATUS_REJECTED
        self.STATUS_NOT_REG = STATUS_NOT_REGISTERED

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._create_failed_registration_task")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.update_registration_status")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._call_perkeso_assist_api")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.validate_registration_payload")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.build_registration_payload")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_successful_registration(self, mock_frappe, mock_build, mock_validate, mock_api, mock_update, mock_task):
        mock_emp = MagicMock()
        mock_emp.get.side_effect = lambda k, d="": {"employee_name": "Ahmad", "company": "Test Co"}.get(k, d)
        mock_frappe.get_doc.return_value = mock_emp

        mock_build.return_value = {"ic_passport_number": "901234", "full_name": "Ahmad"}
        mock_validate.return_value = {"valid": True, "missing": []}
        mock_api.return_value = {
            "success": True,
            "reference_number": "SKSPS-2026-001",
            "error_code": "",
            "error_message": "",
        }

        result = self.submit("EMP-001", use_sandbox=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], self.STATUS_ACTIVE)
        self.assertEqual(result["reference_number"], "SKSPS-2026-001")

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._create_failed_registration_task")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.update_registration_status")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._call_perkeso_assist_api")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.validate_registration_payload")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.build_registration_payload")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_failed_registration_creates_hr_task(self, mock_frappe, mock_build, mock_validate, mock_api, mock_update, mock_task):
        mock_emp = MagicMock()
        mock_emp.get.side_effect = lambda k, d="": {"employee_name": "Ahmad", "company": "Test Co"}.get(k, d)
        mock_frappe.get_doc.return_value = mock_emp

        mock_build.return_value = {"ic_passport_number": "901234", "full_name": "Ahmad"}
        mock_validate.return_value = {"valid": True, "missing": []}
        mock_api.return_value = {
            "success": False,
            "reference_number": "",
            "error_code": "ERR_INVALID_IC",
            "error_message": "Invalid IC format",
        }

        result = self.submit("EMP-001")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], self.STATUS_REJECTED)
        self.assertEqual(result["error_code"], "ERR_INVALID_IC")
        mock_task.assert_called_once()

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._create_failed_registration_task")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.validate_registration_payload")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.build_registration_payload")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_missing_fields_creates_task_without_api_call(self, mock_frappe, mock_build, mock_validate, mock_task):
        mock_emp = MagicMock()
        mock_emp.get.side_effect = lambda k, d="": {"employee_name": "Ahmad", "company": "Test Co"}.get(k, d)
        mock_frappe.get_doc.return_value = mock_emp

        mock_build.return_value = {"ic_passport_number": "", "full_name": "Ahmad"}
        mock_validate.return_value = {"valid": False, "missing": ["ic_passport_number"]}

        result = self.submit("EMP-001")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "ERR_MISSING_FIELD")
        mock_task.assert_called_once()

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_employee_not_found(self, mock_frappe):
        mock_frappe.get_doc.side_effect = Exception("Not found")
        result = self.submit("NONEXISTENT")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "ERR_MISSING_FIELD")


class TestCreateFailedRegistrationTask(FrappeTestCase):
    """_create_failed_registration_task() creates ToDo with correct details."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_sksps_registration_service import (
            _create_failed_registration_task,
        )
        self.create_task = _create_failed_registration_task

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._get_hr_manager")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_creates_todo_with_error_details(self, mock_frappe, mock_hr):
        mock_hr.return_value = "hr@company.com"
        mock_todo = MagicMock()
        mock_todo.name = "TODO-001"
        mock_frappe.get_doc.return_value = mock_todo

        result = self.create_task(
            "EMP-001", "Ahmad", "ERR_INVALID_IC",
            "Invalid IC", "Test Co",
        )

        mock_frappe.get_doc.assert_called_once()
        call_args = mock_frappe.get_doc.call_args[0][0]
        self.assertEqual(call_args["doctype"], "ToDo")
        self.assertEqual(call_args["reference_type"], "Employee")
        self.assertEqual(call_args["reference_name"], "EMP-001")
        self.assertEqual(call_args["priority"], "High")
        self.assertIn("ERR_INVALID_IC", call_args["description"])
        self.assertIn("Ahmad", call_args["description"])
        mock_todo.insert.assert_called_once()

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._get_hr_manager")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.frappe")
    def test_returns_none_on_exception(self, mock_frappe, mock_hr):
        mock_hr.return_value = "hr@company.com"
        mock_frappe.get_doc.side_effect = Exception("DB error")
        result = self.create_task("EMP-001", "Ahmad", "ERR_SERVER", "Server error", "Test Co")
        self.assertIsNone(result)


class TestBulkRegisterGigWorkers(FrappeTestCase):
    """bulk_register_gig_workers() processes multiple workers."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_sksps_registration_service import (
            bulk_register_gig_workers,
            STATUS_ACTIVE,
            STATUS_REJECTED,
            STATUS_NOT_REGISTERED,
            STATUS_PENDING,
        )
        self.bulk_register = bulk_register_gig_workers
        self.STATUS_ACTIVE = STATUS_ACTIVE
        self.STATUS_REJECTED = STATUS_REJECTED
        self.STATUS_NOT_REG = STATUS_NOT_REGISTERED
        self.STATUS_PENDING = STATUS_PENDING

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.submit_sksps_registration")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.get_registration_status")
    def test_registers_unregistered_workers(self, mock_status, mock_submit):
        mock_status.return_value = {
            "status": "Not Registered",
            "reference_number": "",
            "registration_date": None,
            "error_code": "",
            "error_message": "",
        }
        mock_submit.return_value = {
            "success": True,
            "status": "Active",
            "reference_number": "REF-001",
            "error_code": "",
            "error_message": "",
            "payload": {},
        }

        result = self.bulk_register(
            company="Test Co",
            employee_list=["EMP-001", "EMP-002"],
        )
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["success"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["skipped"], 0)

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.submit_sksps_registration")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.get_registration_status")
    def test_skips_already_active_workers(self, mock_status, mock_submit):
        mock_status.return_value = {
            "status": "Active",
            "reference_number": "REF-EXISTING",
            "registration_date": "2026-01-01",
            "error_code": "",
            "error_message": "",
        }

        result = self.bulk_register(
            company="Test Co",
            employee_list=["EMP-001"],
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["success"], 0)
        mock_submit.assert_not_called()

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.submit_sksps_registration")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.get_registration_status")
    def test_skips_pending_workers(self, mock_status, mock_submit):
        mock_status.return_value = {
            "status": "Pending",
            "reference_number": "",
            "registration_date": None,
            "error_code": "",
            "error_message": "",
        }

        result = self.bulk_register(
            company="Test Co",
            employee_list=["EMP-001"],
        )
        self.assertEqual(result["skipped"], 1)
        mock_submit.assert_not_called()

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.submit_sksps_registration")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.get_registration_status")
    def test_mixed_results(self, mock_status, mock_submit):
        # First worker: not registered, registration succeeds
        # Second worker: already active, skipped
        # Third worker: not registered, registration fails
        status_responses = [
            {"status": "Not Registered", "reference_number": "", "registration_date": None, "error_code": "", "error_message": ""},
            {"status": "Active", "reference_number": "REF-OLD", "registration_date": "2026-01-01", "error_code": "", "error_message": ""},
            {"status": "Not Registered", "reference_number": "", "registration_date": None, "error_code": "", "error_message": ""},
        ]
        mock_status.side_effect = status_responses

        submit_responses = [
            {"success": True, "status": "Active", "reference_number": "REF-NEW", "error_code": "", "error_message": "", "payload": {}},
            {"success": False, "status": "Rejected", "reference_number": "", "error_code": "ERR_INVALID_IC", "error_message": "Bad IC", "payload": {}},
        ]
        mock_submit.side_effect = submit_responses

        result = self.bulk_register(
            company="Test Co",
            employee_list=["EMP-001", "EMP-002", "EMP-003"],
        )
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["success"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["failed"], 1)

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service._get_unregistered_gig_workers")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.submit_sksps_registration")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.get_registration_status")
    def test_auto_discovers_workers_when_no_list(self, mock_status, mock_submit, mock_discover):
        mock_discover.return_value = ["EMP-AUTO-001"]
        mock_status.return_value = {
            "status": "Not Registered", "reference_number": "",
            "registration_date": None, "error_code": "", "error_message": "",
        }
        mock_submit.return_value = {
            "success": True, "status": "Active", "reference_number": "REF-AUTO",
            "error_code": "", "error_message": "", "payload": {},
        }

        result = self.bulk_register(company="Test Co")
        mock_discover.assert_called_once_with("Test Co")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["success"], 1)

    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.submit_sksps_registration")
    @patch("lhdn_payroll_integration.services.gig_worker_sksps_registration_service.get_registration_status")
    def test_empty_list_returns_zero_counts(self, mock_status, mock_submit):
        result = self.bulk_register(company="Test Co", employee_list=[])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["success"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["skipped"], 0)


class TestCheckSkspsAgeEligibility(FrappeTestCase):
    """check_sksps_age_eligibility() validates 15–65 age range."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_sksps_registration_service import (
            check_sksps_age_eligibility,
            SKSPS_MIN_AGE,
            SKSPS_MAX_AGE,
        )
        self.check_age = check_sksps_age_eligibility
        self.MIN_AGE = SKSPS_MIN_AGE
        self.MAX_AGE = SKSPS_MAX_AGE

    def test_eligible_at_25(self):
        result = self.check_age("2001-03-01", as_of_date="2026-03-01")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["age"], 25)

    def test_eligible_at_minimum_age_15(self):
        result = self.check_age("2011-03-01", as_of_date="2026-03-01")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["age"], 15)

    def test_eligible_at_maximum_age_65(self):
        result = self.check_age("1961-03-01", as_of_date="2026-03-01")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["age"], 65)

    def test_ineligible_underage_14(self):
        result = self.check_age("2012-03-02", as_of_date="2026-03-01")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["age"], 13)
        self.assertIn(str(self.MIN_AGE), result["reason"])

    def test_ineligible_overage_66(self):
        result = self.check_age("1960-02-28", as_of_date="2026-03-01")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["age"], 66)
        self.assertIn(str(self.MAX_AGE), result["reason"])

    def test_no_dob_returns_ineligible(self):
        result = self.check_age(None)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["age"], 0)
        self.assertIn("not provided", result["reason"].lower())

    def test_boundary_birthday_not_yet_passed(self):
        """Worker born 1961-06-15, checked 2026-03-01 → age 64 (birthday not passed yet)."""
        result = self.check_age("1961-06-15", as_of_date="2026-03-01")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["age"], 64)

    def test_boundary_birthday_just_passed(self):
        """Worker born 1961-02-28, checked 2026-03-01 → age 65 (birthday passed)."""
        result = self.check_age("1961-02-28", as_of_date="2026-03-01")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["age"], 65)

    def test_exact_day_of_15th_birthday(self):
        """On exact 15th birthday, eligible."""
        result = self.check_age("2011-03-01", as_of_date="2026-03-01")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["age"], 15)

    def test_day_before_15th_birthday(self):
        """Day before 15th birthday, age is still 14, ineligible."""
        result = self.check_age("2011-03-02", as_of_date="2026-03-01")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["age"], 14)
