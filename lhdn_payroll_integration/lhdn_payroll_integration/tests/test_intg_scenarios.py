"""Integration test scenarios T-01 to T-05 for LHDN Payroll Integration.

US-022 mandatory LHDN integration scenarios. Tests the full submission
lifecycle by chaining multiple service calls together, using mocked HTTP
to simulate LHDN sandbox responses.

For T-02 with real LHDN sandbox: update Company "Arising Packaging" with
real client_id + client_secret from https://sdk.myinvois.hasil.gov.my/

Scenarios covered:
- T-01: Standard employee Salary Slip -> custom_lhdn_status='Exempt'
- T-02: Contractor Salary Slip (valid) -> Submitted -> Valid (full chain)
- T-03: Contractor Salary Slip (bad TIN) -> Submitted -> Invalid
- T-04: Network timeout -> custom_retry_count=1, retry enqueued
- T-05: run_monthly_consolidation() -> code-004 payload, slips consolidated

Unit tests:
- quantize(0.1 + 0.2) == Decimal('0.30')
- validate_tin('IG123', 'NRIC') raises frappe.ValidationError
- should_submit_to_lhdn('Salary Slip', exempt_doc) returns False
"""
from decimal import Decimal

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch, call


class TestT01StandardEmployeeExempt(FrappeTestCase):
    """T-01: Submit standard employee Salary Slip -> Exempt, zero API calls."""

    def _make_standard_employee(self):
        emp = MagicMock()
        emp.custom_requires_self_billed_invoice = 0
        emp.custom_worker_type = "Employee"
        return emp

    def _make_salary_slip(self, employee="EMP-T01-001", net_pay=6000):
        doc = MagicMock()
        doc.name = "SAL-T01-001"
        doc.doctype = "Salary Slip"
        doc.employee = employee
        doc.net_pay = net_pay
        return doc

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_t01_standard_slip_exempt_no_api_call(self, mock_exempt_frappe, mock_sub_frappe):
        """T-01: Standard employee slip is Exempt — no LHDN API call made."""
        from lhdn_payroll_integration.services.submission_service import (
            enqueue_salary_slip_submission,
        )

        employee = self._make_standard_employee()
        mock_exempt_frappe.get_doc.return_value = employee

        doc = self._make_salary_slip()
        enqueue_salary_slip_submission(doc, "on_submit")

        # Verify Exempt status was set
        mock_sub_frappe.db.set_value.assert_called_once_with(
            "Salary Slip", "SAL-T01-001", "custom_lhdn_status", "Exempt"
        )
        # Verify zero LHDN API enqueue calls
        mock_sub_frappe.enqueue.assert_not_called()


class TestT02ContractorSlipValidChain(FrappeTestCase):
    """T-02: Contractor Salary Slip (valid data) -> Submitted -> Valid (full chain).

    Tests the full end-to-end chain:
    1. enqueue_salary_slip_submission() sets Pending + enqueues
    2. process_salary_slip() POSTs to LHDN → sets Submitted + UUID
    3. poll_pending_documents() GETs status → sets Valid + validated datetime
    """

    def _make_contractor_employee(self):
        emp = MagicMock()
        emp.custom_requires_self_billed_invoice = 1
        emp.custom_worker_type = "Contractor"
        emp.custom_lhdn_tin = "IG12345678901"
        return emp

    def _make_slip(self):
        doc = MagicMock()
        doc.name = "SAL-T02-001"
        doc.doctype = "Salary Slip"
        doc.employee = "EMP-T02-001"
        doc.net_pay = 8000
        doc.company = "Arising Packaging"
        return doc

    def _mock_202_accepted(self):
        resp = MagicMock()
        resp.status_code = 202
        resp.json.return_value = {
            "acceptedDocuments": [
                {
                    "uuid": "TEST-UUID-T02-VALID-001",
                    "invoiceCodeNumber": "SAL-T02-001",
                }
            ],
            "rejectedDocuments": [],
        }
        return resp

    def _mock_valid_status_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "uuid": "TEST-UUID-T02-VALID-001",
            "status": "valid",
            "dateTimeValidated": "2026-02-26T10:00:00Z",
            "longId": "https://preprod.myinvois.hasil.gov.my/TEST-UUID-T02-VALID-001/share",
        }
        return resp

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_t02_step1_contractor_sets_pending_and_enqueues(
        self, mock_exempt_frappe, mock_sub_frappe
    ):
        """T-02 Step 1: Contractor slip sets Pending status and enqueues background job."""
        from lhdn_payroll_integration.services.submission_service import (
            enqueue_salary_slip_submission,
        )

        emp = self._make_contractor_employee()
        mock_exempt_frappe.get_doc.return_value = emp

        doc = self._make_slip()
        enqueue_salary_slip_submission(doc, "on_submit")

        # Should set Pending
        pending_set = any(
            c == call("Salary Slip", "SAL-T02-001", "custom_lhdn_status", "Pending")
            for c in mock_sub_frappe.db.set_value.call_args_list
        )
        self.assertTrue(pending_set, "Contractor slip must set custom_lhdn_status='Pending'")

        # Should enqueue the background job
        mock_sub_frappe.enqueue.assert_called_once()
        enq_kwargs = mock_sub_frappe.enqueue.call_args[1]
        self.assertEqual(
            enq_kwargs["method"],
            "lhdn_payroll_integration.services.submission_service.process_salary_slip",
        )
        self.assertTrue(enq_kwargs["enqueue_after_commit"])

    @patch("lhdn_payroll_integration.services.submission_service.prepare_submission_wrapper")
    @patch("lhdn_payroll_integration.services.submission_service.build_salary_slip_xml")
    @patch("lhdn_payroll_integration.services.submission_service.requests")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_t02_step2_process_slip_sets_submitted_and_uuid(
        self, mock_frappe, mock_requests, mock_build_xml, mock_wrapper
    ):
        """T-02 Step 2: process_salary_slip() POSTs to LHDN and sets Submitted + UUID."""
        from lhdn_payroll_integration.services.submission_service import process_salary_slip

        mock_build_xml.return_value = "<Invoice>test</Invoice>"
        mock_wrapper.return_value = {
            "documents": [
                {
                    "format": "XML",
                    "document": "base64data",
                    "documentHash": "sha256hash",
                    "codeNumber": "SAL-T02-001",
                }
            ]
        }
        mock_requests.post.return_value = self._mock_202_accepted()

        slip_doc = MagicMock()
        slip_doc.company = "Arising Packaging"
        company_doc = MagicMock()
        company_doc.custom_integration_type = "Sandbox"
        company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        company_doc.custom_bearer_token = "cached-token-t02"

        mock_frappe.get_doc.side_effect = lambda dt, name=None: (
            slip_doc if dt == "Salary Slip" else company_doc
        )

        process_salary_slip("SAL-T02-001")

        # Verify Submitted status + UUID set
        set_calls = {
            (c[0][2], c[0][3])
            for c in mock_frappe.db.set_value.call_args_list
            if len(c[0]) >= 4
        }
        self.assertIn(("custom_lhdn_status", "Submitted"), set_calls,
                      "process_salary_slip must set custom_lhdn_status='Submitted'")
        self.assertIn(("custom_lhdn_uuid", "TEST-UUID-T02-VALID-001"), set_calls,
                      "process_salary_slip must set custom_lhdn_uuid to the returned UUID")

    @patch("lhdn_payroll_integration.services.status_poller.get_access_token")
    @patch("lhdn_payroll_integration.services.status_poller.requests")
    @patch("lhdn_payroll_integration.services.status_poller.frappe")
    def test_t02_step3_poll_sets_valid_and_datetime(
        self, mock_frappe, mock_requests, mock_get_token
    ):
        """T-02 Step 3: poll_pending_documents() fetches status and sets Valid + datetime."""
        from lhdn_payroll_integration.services.status_poller import poll_pending_documents

        mock_get_token.return_value = "poll-token-t02"
        mock_frappe.defaults.get_defaults.return_value = {"company": "Arising Packaging"}

        company_doc = MagicMock()
        company_doc.custom_integration_type = "Sandbox"
        company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        mock_frappe.get_doc.return_value = company_doc

        # Salary Slip with Submitted status waiting for poll
        submitted_slip = frappe._dict({
            "name": "SAL-T02-001",
            "custom_lhdn_uuid": "TEST-UUID-T02-VALID-001",
            "custom_lhdn_status": "Submitted",
        })
        mock_frappe.get_all.side_effect = [
            [submitted_slip],  # Salary Slip query
            [],                # Expense Claim query
        ]
        mock_requests.get.return_value = self._mock_valid_status_response()

        poll_pending_documents()

        # Verify Valid status set
        set_calls = {
            (c[0][2], c[0][3])
            for c in mock_frappe.db.set_value.call_args_list
            if len(c[0]) >= 4
        }
        self.assertIn(("custom_lhdn_status", "Valid"), set_calls,
                      "poll_pending_documents must set custom_lhdn_status='Valid' for valid doc")
        self.assertIn(("custom_lhdn_validated_datetime", "2026-02-26T10:00:00Z"), set_calls,
                      "poll_pending_documents must set custom_lhdn_validated_datetime")


class TestT03ContractorSlipBadTinInvalid(FrappeTestCase):
    """T-03: Contractor Salary Slip with bad TIN -> Invalid, error log populated."""

    def _mock_202_rejected(self):
        resp = MagicMock()
        resp.status_code = 202
        resp.json.return_value = {
            "acceptedDocuments": [],
            "rejectedDocuments": [
                {
                    "invoiceCodeNumber": "SAL-T03-001",
                    "error": {
                        "code": "InvalidTIN",
                        "message": "TIN validation failed",
                        "details": [
                            {
                                "code": "CF0001",
                                "message": "TIN is not valid for this taxpayer type",
                                "target": "TaxpayerTIN",
                            }
                        ],
                    },
                }
            ],
        }
        return resp

    @patch("lhdn_payroll_integration.services.submission_service.prepare_submission_wrapper")
    @patch("lhdn_payroll_integration.services.submission_service.build_salary_slip_xml")
    @patch("lhdn_payroll_integration.services.submission_service.requests")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_t03_rejected_sets_invalid_and_error_log(
        self, mock_frappe, mock_requests, mock_build_xml, mock_wrapper
    ):
        """T-03: Rejected submission sets custom_lhdn_status='Invalid' and populates error log."""
        from lhdn_payroll_integration.services.submission_service import process_salary_slip

        mock_build_xml.return_value = "<Invoice>bad-tin</Invoice>"
        mock_wrapper.return_value = {
            "documents": [
                {
                    "format": "XML",
                    "document": "base64data",
                    "documentHash": "sha256hash",
                    "codeNumber": "SAL-T03-001",
                }
            ]
        }
        mock_requests.post.return_value = self._mock_202_rejected()

        slip_doc = MagicMock()
        slip_doc.company = "Arising Packaging"
        company_doc = MagicMock()
        company_doc.custom_integration_type = "Sandbox"
        company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        company_doc.custom_bearer_token = "cached-token-t03"
        mock_frappe.get_doc.side_effect = lambda dt, name=None: (
            slip_doc if dt == "Salary Slip" else company_doc
        )

        process_salary_slip("SAL-T03-001")

        # Extract all set_value calls
        set_calls = {
            (c[0][2], c[0][3])
            for c in mock_frappe.db.set_value.call_args_list
            if len(c[0]) >= 4
        }
        # Verify Invalid status
        self.assertIn(("custom_lhdn_status", "Invalid"), set_calls,
                      "T-03: Rejected slip must set custom_lhdn_status='Invalid'")

        # Verify error log is populated (contains error text)
        error_log_set = any(
            len(c[0]) >= 4 and c[0][2] == "custom_error_log" and c[0][3]
            for c in mock_frappe.db.set_value.call_args_list
        )
        self.assertTrue(error_log_set,
                        "T-03: custom_error_log must be populated with TIN error details")

        # Verify error log contains relevant error text
        error_log_value = next(
            c[0][3]
            for c in mock_frappe.db.set_value.call_args_list
            if len(c[0]) >= 4 and c[0][2] == "custom_error_log"
        )
        self.assertIn("CF0001", error_log_value,
                      "T-03: Error log must contain LHDN error code CF0001")


class TestT04NetworkTimeoutRetry(FrappeTestCase):
    """T-04: Network timeout -> custom_retry_count=1, status Pending, retry enqueued."""

    @patch("lhdn_payroll_integration.services.submission_service.prepare_submission_wrapper")
    @patch("lhdn_payroll_integration.services.submission_service.build_salary_slip_xml")
    @patch("lhdn_payroll_integration.services.submission_service.requests")
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_t04_timeout_increments_retry_and_enqueues(
        self, mock_frappe, mock_requests, mock_build_xml, mock_wrapper
    ):
        """T-04: On Timeout, retry_count=1 and retry job enqueued; status remains Pending."""
        import requests as real_requests
        from lhdn_payroll_integration.services.submission_service import process_salary_slip

        mock_build_xml.return_value = "<Invoice>test</Invoice>"
        mock_wrapper.return_value = {
            "documents": [
                {
                    "format": "XML",
                    "document": "base64data",
                    "documentHash": "sha256hash",
                    "codeNumber": "SAL-T04-001",
                }
            ]
        }

        # Simulate network timeout on first (and only) POST call
        mock_requests.post.side_effect = real_requests.exceptions.Timeout("Connection timed out")
        mock_requests.exceptions = real_requests.exceptions

        slip_doc = MagicMock()
        slip_doc.company = "Arising Packaging"
        company_doc = MagicMock()
        company_doc.custom_integration_type = "Sandbox"
        company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        company_doc.custom_bearer_token = "cached-token-t04"
        mock_frappe.get_doc.side_effect = lambda dt, name=None: (
            slip_doc if dt == "Salary Slip" else company_doc
        )
        # Current retry count is 0
        mock_frappe.db.get_value.return_value = 0

        process_salary_slip("SAL-T04-001")

        # Verify retry_count was incremented to 1
        retry_set = any(
            len(c[0]) >= 4 and c[0][2] == "custom_retry_count" and c[0][3] == 1
            for c in mock_frappe.db.set_value.call_args_list
        )
        self.assertTrue(retry_set, "T-04: custom_retry_count must be set to 1 after timeout")

        # Verify retry job was enqueued
        mock_frappe.enqueue.assert_called_once()
        enq_method = mock_frappe.enqueue.call_args[1].get(
            "method", mock_frappe.enqueue.call_args[0][0] if mock_frappe.enqueue.call_args[0] else ""
        )
        self.assertIn("process_salary_slip", enq_method,
                      "T-04: Retry job must enqueue process_salary_slip")

        # Verify custom_lhdn_status was NOT changed to Invalid (stays Pending)
        invalid_set = any(
            len(c[0]) >= 4 and c[0][2] == "custom_lhdn_status" and c[0][3] == "Invalid"
            for c in mock_frappe.db.set_value.call_args_list
        )
        self.assertFalse(invalid_set, "T-04: Status must NOT be set to Invalid on timeout")


class TestT05MonthlyConsolidation(FrappeTestCase):
    """T-05: run_monthly_consolidation() -> code-004 payload submitted, slips consolidated."""

    def _make_pending_slip(self, name, net_pay=5000):
        return frappe._dict({
            "name": name,
            "doctype": "Salary Slip",
            "net_pay": net_pay,
            "custom_lhdn_status": "Pending",
            "custom_is_consolidated": 0,
            "posting_date": "2026-01-15",
        })

    @patch("lhdn_payroll_integration.services.submission_service.process_salary_slip")
    @patch("lhdn_payroll_integration.services.submission_service.process_expense_claim")
    @patch("lhdn_payroll_integration.services.consolidation_service.frappe")
    def test_t05_consolidation_marks_slips_consolidated(
        self, mock_frappe, mock_process_claim, mock_process_slip
    ):
        """T-05: run_monthly_consolidation marks eligible slips as custom_is_consolidated=1."""
        from lhdn_payroll_integration.services.consolidation_service import (
            run_monthly_consolidation,
        )
        from datetime import date

        slips = [
            self._make_pending_slip("SAL-T05-001", net_pay=4000),
            self._make_pending_slip("SAL-T05-002", net_pay=3500),
        ]

        mock_frappe.get_all.side_effect = [
            slips,  # Salary Slip query
            [],     # Expense Claim query
        ]
        mock_frappe.utils.get_first_day.return_value = date(2026, 1, 1)
        mock_frappe.utils.get_last_day.return_value = date(2026, 1, 31)
        mock_frappe.utils.add_months.return_value = date(2026, 1, 15)
        mock_frappe.utils.today.return_value = "2026-02-15"
        mock_frappe.ValidationError = frappe.ValidationError

        run_monthly_consolidation()

        # Verify process_salary_slip was called for each eligible slip
        self.assertEqual(
            mock_process_slip.call_count, 2,
            "T-05: process_salary_slip must be called once per eligible slip",
        )

        # Verify custom_is_consolidated=1 was set for each slip
        consolidated_calls = [
            c for c in mock_frappe.db.set_value.call_args_list
            if len(c[0]) >= 4 and c[0][2] == "custom_is_consolidated" and c[0][3] == 1
        ]
        self.assertEqual(
            len(consolidated_calls), 2,
            "T-05: run_monthly_consolidation must set custom_is_consolidated=1 for each eligible slip",
        )

    @patch("lhdn_payroll_integration.services.submission_service.process_salary_slip")
    @patch("lhdn_payroll_integration.services.submission_service.process_expense_claim")
    @patch("lhdn_payroll_integration.services.consolidation_service.frappe")
    def test_t05_high_value_slips_submitted_individually(
        self, mock_frappe, mock_process_claim, mock_process_slip
    ):
        """T-05: Slips with net_pay > RM 10,000 are submitted individually (not skipped)."""
        from lhdn_payroll_integration.services.consolidation_service import (
            run_monthly_consolidation,
        )
        from datetime import date

        slips = [
            self._make_pending_slip("SAL-T05-HV-001", net_pay=15000),  # > RM 10,000
            self._make_pending_slip("SAL-T05-NRM-001", net_pay=5000),  # normal
        ]

        mock_frappe.get_all.side_effect = [slips, []]
        mock_frappe.utils.get_first_day.return_value = date(2026, 1, 1)
        mock_frappe.utils.get_last_day.return_value = date(2026, 1, 31)
        mock_frappe.utils.add_months.return_value = date(2026, 1, 15)
        mock_frappe.utils.today.return_value = "2026-02-15"
        mock_frappe.ValidationError = frappe.ValidationError

        run_monthly_consolidation()

        # Both slips should be processed (high-value individually, normal in batch)
        self.assertEqual(
            mock_process_slip.call_count, 2,
            "T-05: Both high-value and normal slips must be submitted via process_salary_slip",
        )

        # Both should be marked consolidated
        consolidated_slips = [
            c[0][1]
            for c in mock_frappe.db.set_value.call_args_list
            if len(c[0]) >= 4
            and c[0][2] == "custom_is_consolidated"
            and c[0][3] == 1
        ]
        self.assertIn("SAL-T05-HV-001", consolidated_slips,
                      "T-05: High-value slip must be marked custom_is_consolidated=1")
        self.assertIn("SAL-T05-NRM-001", consolidated_slips,
                      "T-05: Normal slip must be marked custom_is_consolidated=1")


class TestUnitQuantize(FrappeTestCase):
    """Unit test: quantize(0.1 + 0.2) == Decimal('0.30')."""

    def test_quantize_floating_point_precision(self):
        """quantize must fix floating point: Decimal(0.1) + Decimal(0.2) = Decimal('0.30')."""
        from lhdn_payroll_integration.utils.decimal_utils import quantize

        result = quantize(Decimal("0.1") + Decimal("0.2"))
        self.assertEqual(result, Decimal("0.30"),
                         "quantize must return Decimal('0.30') for 0.1 + 0.2")


class TestUnitValidateTin(FrappeTestCase):
    """Unit test: validate_tin('IG123', 'NRIC') raises frappe.ValidationError."""

    def test_invalid_short_tin_raises_validation_error(self):
        """validate_tin with too-short NRIC TIN ('IG123') raises frappe.ValidationError."""
        from lhdn_payroll_integration.utils.validation import validate_tin

        with self.assertRaises(frappe.ValidationError):
            validate_tin("IG123", "NRIC")

    def test_valid_nric_tin_passes(self):
        """validate_tin with valid 13-char NRIC TIN passes without error."""
        from lhdn_payroll_integration.utils.validation import validate_tin

        result = validate_tin("IG12345678901", "NRIC")
        self.assertEqual(result, "IG12345678901")


class TestUnitExemptionFilter(FrappeTestCase):
    """Unit test: should_submit_to_lhdn('Salary Slip', exempt_doc) returns False."""

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_exempt_doc_returns_false(self, mock_frappe):
        """should_submit_to_lhdn returns False for standard employee (flag=0)."""
        from lhdn_payroll_integration.services.exemption_filter import should_submit_to_lhdn

        emp = MagicMock()
        emp.custom_requires_self_billed_invoice = 0
        emp.custom_worker_type = "Employee"
        mock_frappe.get_doc.return_value = emp

        exempt_doc = MagicMock()
        exempt_doc.employee = "EMP-STANDARD-001"
        exempt_doc.net_pay = 5000

        result = should_submit_to_lhdn("Salary Slip", exempt_doc)
        self.assertFalse(result, "should_submit_to_lhdn must return False for standard employee")

    @patch("lhdn_payroll_integration.services.exemption_filter.frappe")
    def test_contractor_doc_returns_true(self, mock_frappe):
        """should_submit_to_lhdn returns True for contractor with flag=1 and net_pay > 0."""
        from lhdn_payroll_integration.services.exemption_filter import should_submit_to_lhdn

        emp = MagicMock()
        emp.custom_requires_self_billed_invoice = 1
        emp.custom_worker_type = "Contractor"
        mock_frappe.get_doc.return_value = emp

        contractor_doc = MagicMock()
        contractor_doc.employee = "EMP-CONTRACTOR-001"
        contractor_doc.net_pay = 8000

        result = should_submit_to_lhdn("Salary Slip", contractor_doc)
        self.assertTrue(result, "should_submit_to_lhdn must return True for contractor with flag=1")
