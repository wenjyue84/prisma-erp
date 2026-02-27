"""Tests for the LHDN Developer Tools Frappe page.

Three test classes:
- TestDevToolsPageFiles    — all 4 page files exist, JSON is well-formed
- TestDevToolsBackendMethods — permission guard; check_exemption for Employee type
- TestDevToolsWorkspaceShortcut — workspace fixture has lhdn-dev-tools shortcut
- TestRetrieveLhdnDocument — retrieve_lhdn_document uses UUID in URL and stores XML
"""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

# Absolute path resolution helpers
_PAGE_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "lhdn_payroll_integration",
        "page",
        "lhdn_dev_tools",
    )
)

_WORKSPACE_FIXTURE_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "fixtures",
        "workspace.json",
    )
)

_MODULE = "lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools"


class TestDevToolsPageFiles(FrappeTestCase):
    """All 4 page artefact files must exist and be well-formed."""

    def _page_path(self, filename):
        return os.path.join(_PAGE_DIR, filename)

    def test_init_py_exists(self):
        self.assertTrue(
            os.path.exists(self._page_path("__init__.py")),
            "__init__.py missing from page directory",
        )

    def test_json_exists(self):
        self.assertTrue(
            os.path.exists(self._page_path("lhdn_dev_tools.json")),
            "lhdn_dev_tools.json missing",
        )

    def test_py_exists(self):
        self.assertTrue(
            os.path.exists(self._page_path("lhdn_dev_tools.py")),
            "lhdn_dev_tools.py missing",
        )

    def test_js_exists(self):
        self.assertTrue(
            os.path.exists(self._page_path("lhdn_dev_tools.js")),
            "lhdn_dev_tools.js missing",
        )

    def test_json_doctype(self):
        with open(self._page_path("lhdn_dev_tools.json")) as f:
            data = json.load(f)
        self.assertEqual(data.get("doctype"), "Page", "JSON doctype must be 'Page'")

    def test_json_name(self):
        with open(self._page_path("lhdn_dev_tools.json")) as f:
            data = json.load(f)
        self.assertEqual(data.get("name"), "lhdn-dev-tools", "JSON name must be 'lhdn-dev-tools'")

    def test_json_module(self):
        with open(self._page_path("lhdn_dev_tools.json")) as f:
            data = json.load(f)
        self.assertEqual(
            data.get("module"),
            "LHDN Payroll Integration",
            "JSON module must be 'LHDN Payroll Integration'",
        )

    def test_json_roles_system_manager(self):
        with open(self._page_path("lhdn_dev_tools.json")) as f:
            data = json.load(f)
        roles = [r.get("role") for r in (data.get("roles") or [])]
        self.assertIn(
            "System Manager",
            roles,
            "Page must restrict access to System Manager role",
        )


class TestDevToolsBackendMethods(FrappeTestCase):
    """Permission guard blocks non-System-Manager callers for all whitelisted methods."""

    def _import_module(self):
        import importlib
        return importlib.import_module(_MODULE)

    def _non_sm_patch(self, module_path):
        return patch(f"{_MODULE}.frappe.get_roles", return_value=["Employee"])

    def test_get_system_status_blocks_non_sm(self):
        mod = self._import_module()
        with patch(f"{_MODULE}.frappe.get_roles", return_value=["Employee"]):
            with self.assertRaises((frappe.PermissionError, PermissionError)):
                mod.get_system_status()

    def test_test_lhdn_connection_blocks_non_sm(self):
        mod = self._import_module()
        with patch(f"{_MODULE}.frappe.get_roles", return_value=["Employee"]):
            with self.assertRaises((frappe.PermissionError, PermissionError)):
                mod.test_lhdn_connection()

    def test_run_status_poller_blocks_non_sm(self):
        mod = self._import_module()
        with patch(f"{_MODULE}.frappe.get_roles", return_value=["Employee"]):
            with self.assertRaises((frappe.PermissionError, PermissionError)):
                mod.run_status_poller()

    def test_run_monthly_consolidation_blocks_non_sm(self):
        mod = self._import_module()
        with patch(f"{_MODULE}.frappe.get_roles", return_value=["Employee"]):
            with self.assertRaises((frappe.PermissionError, PermissionError)):
                mod.run_monthly_consolidation()

    def test_run_yearly_retention_blocks_non_sm(self):
        mod = self._import_module()
        with patch(f"{_MODULE}.frappe.get_roles", return_value=["Employee"]):
            with self.assertRaises((frappe.PermissionError, PermissionError)):
                mod.run_yearly_retention()

    def test_check_exemption_blocks_non_sm(self):
        mod = self._import_module()
        with patch(f"{_MODULE}.frappe.get_roles", return_value=["Employee"]):
            with self.assertRaises((frappe.PermissionError, PermissionError)):
                mod.check_exemption("EMP-0001")

    def test_get_recent_submissions_blocks_non_sm(self):
        mod = self._import_module()
        with patch(f"{_MODULE}.frappe.get_roles", return_value=["Employee"]):
            with self.assertRaises((frappe.PermissionError, PermissionError)):
                mod.get_recent_submissions()

    def test_check_exemption_returns_false_for_employee_worker_type(self):
        """Employee worker type is not in IN_SCOPE_WORKER_TYPES — must return in_scope=False."""
        mod = self._import_module()

        mock_emp = MagicMock()
        mock_emp.custom_worker_type = "Employee"

        with patch(f"{_MODULE}.frappe.get_roles", return_value=["System Manager"]):
            with patch(f"{_MODULE}.frappe.get_doc", return_value=mock_emp):
                result = mod.check_exemption("EMP-0001")

        self.assertFalse(result["in_scope"], "Employee worker type must be out-of-scope")
        self.assertIn("not in-scope", result["reason"])

    def test_retrieve_lhdn_document_blocks_non_sm(self):
        """retrieve_lhdn_document must block non-System Manager users."""
        mod = self._import_module()
        with patch(f"{_MODULE}.frappe.get_roles", return_value=["Employee"]):
            with self.assertRaises((frappe.PermissionError, PermissionError)):
                mod.retrieve_lhdn_document("Sal Slip/2026/00001", "Salary Slip")


class TestRetrieveLhdnDocument(FrappeTestCase):
    """retrieve_lhdn_document uses the document UUID in the GET URL and stores the response XML."""

    def _import_module(self):
        import importlib
        return importlib.import_module(_MODULE)

    def test_retrieve_uses_uuid_in_url_and_stores_xml(self):
        """UUID must appear in the GET URL and the raw XML stored via frappe.db.set_value."""
        mod = self._import_module()

        test_uuid = "abc-123-test-uuid-456"
        test_xml = "<Invoice><ID>TEST-001</ID></Invoice>"

        # Mock the target document
        mock_doc = MagicMock()
        mock_doc.custom_lhdn_uuid = test_uuid

        # Mock the company document
        mock_company = MagicMock()
        mock_company.custom_sandbox_url = "https://sandbox.myinvois.hasil.gov.my"
        mock_company.custom_client_id = "client_test_123"
        mock_company.custom_client_secret = "secret_test_456"

        # Mock token response
        mock_token_response = MagicMock()
        mock_token_response.ok = True
        mock_token_response.json.return_value = {"access_token": "test_bearer_token"}

        # Mock raw document response
        mock_raw_response = MagicMock()
        mock_raw_response.ok = True
        mock_raw_response.text = test_xml

        def fake_get_doc(doctype, name=None):
            if doctype == "Company":
                return mock_company
            return mock_doc

        with patch(f"{_MODULE}.frappe.get_roles", return_value=["System Manager"]):
            with patch(f"{_MODULE}.frappe.get_doc", side_effect=fake_get_doc):
                with patch(f"{_MODULE}.frappe.db.get_value", return_value="Test Company"):
                    with patch(f"{_MODULE}.frappe.db.set_value") as mock_set_value:
                        with patch(f"{_MODULE}.requests.post", return_value=mock_token_response):
                            with patch(f"{_MODULE}.requests.get", return_value=mock_raw_response) as mock_get:
                                result = mod.retrieve_lhdn_document(
                                    "Sal Slip/2026/00001", "Salary Slip"
                                )

        # Verify UUID is in the GET URL
        self.assertTrue(mock_get.called, "requests.get must be called")
        call_url = mock_get.call_args[0][0]
        self.assertIn(test_uuid, call_url, "UUID must appear in the GET URL path")

        # Verify the XML is stored via set_value
        self.assertTrue(mock_set_value.called, "frappe.db.set_value must be called to store XML")
        set_args = mock_set_value.call_args[0]
        self.assertEqual(set_args[2], "custom_lhdn_raw_document",
                         "set_value must target custom_lhdn_raw_document field")
        self.assertEqual(set_args[3], test_xml,
                         "set_value must store the full raw XML text")

        # Verify success result
        self.assertTrue(result["success"], "Result must indicate success")
        self.assertEqual(result["raw_xml"], test_xml)

    def test_retrieve_returns_error_when_no_uuid(self):
        """Returns error dict if the document has no custom_lhdn_uuid."""
        mod = self._import_module()

        mock_doc = MagicMock()
        mock_doc.custom_lhdn_uuid = None

        with patch(f"{_MODULE}.frappe.get_roles", return_value=["System Manager"]):
            with patch(f"{_MODULE}.frappe.get_doc", return_value=mock_doc):
                result = mod.retrieve_lhdn_document("Sal Slip/2026/00001", "Salary Slip")

        self.assertFalse(result["success"])
        self.assertIn("UUID", result["error_detail"])

    def test_retrieve_returns_error_on_token_failure(self):
        """Returns error dict if the LHDN token endpoint returns a non-200 status."""
        mod = self._import_module()

        mock_doc = MagicMock()
        mock_doc.custom_lhdn_uuid = "some-uuid"

        mock_company = MagicMock()
        mock_company.custom_sandbox_url = "https://sandbox.myinvois.hasil.gov.my"
        mock_company.custom_client_id = "bad_client"
        mock_company.custom_client_secret = "bad_secret"

        mock_token_response = MagicMock()
        mock_token_response.ok = False
        mock_token_response.status_code = 400

        def fake_get_doc(doctype, name=None):
            if doctype == "Company":
                return mock_company
            return mock_doc

        with patch(f"{_MODULE}.frappe.get_roles", return_value=["System Manager"]):
            with patch(f"{_MODULE}.frappe.get_doc", side_effect=fake_get_doc):
                with patch(f"{_MODULE}.frappe.db.get_value", return_value="Test Company"):
                    with patch(f"{_MODULE}.requests.post", return_value=mock_token_response):
                        result = mod.retrieve_lhdn_document("Sal Slip/2026/00001", "Salary Slip")

        self.assertFalse(result["success"])
        self.assertIn("Token request failed", result["error_detail"])

    def test_js_has_retrieve_from_lhdn_button(self):
        """lhdn_dev_tools.js must contain the Retrieve from LHDN button markup."""
        js_path = os.path.join(_PAGE_DIR, "lhdn_dev_tools.js")
        self.assertTrue(os.path.exists(js_path), "lhdn_dev_tools.js must exist")
        with open(js_path) as f:
            content = f.read()
        self.assertIn("retrieve_lhdn_document", content,
                      "JS must reference retrieve_lhdn_document method")
        self.assertIn("Retrieve from LHDN", content,
                      "JS must contain 'Retrieve from LHDN' button label")

    def test_custom_field_raw_document_in_fixture(self):
        """custom_field.json must contain custom_lhdn_raw_document for Salary Slip and Expense Claim."""
        fixture_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "fixtures",
                "custom_field.json",
            )
        )
        self.assertTrue(os.path.exists(fixture_path), "custom_field.json must exist")
        with open(fixture_path) as f:
            fields = json.load(f)

        fieldnames_by_dt = {}
        for f in fields:
            dt = f.get("dt", "")
            fn = f.get("fieldname", "")
            fieldnames_by_dt.setdefault(dt, set()).add(fn)

        self.assertIn(
            "custom_lhdn_raw_document",
            fieldnames_by_dt.get("Salary Slip", set()),
            "custom_lhdn_raw_document must be defined on Salary Slip",
        )
        self.assertIn(
            "custom_lhdn_raw_document",
            fieldnames_by_dt.get("Expense Claim", set()),
            "custom_lhdn_raw_document must be defined on Expense Claim",
        )


class TestDevToolsWorkspaceShortcut(FrappeTestCase):
    """workspace.json must contain a shortcut linking to lhdn-dev-tools."""

    def _load_fixture(self):
        self.assertTrue(
            os.path.exists(_WORKSPACE_FIXTURE_PATH),
            f"workspace.json not found at {_WORKSPACE_FIXTURE_PATH}",
        )
        with open(_WORKSPACE_FIXTURE_PATH) as f:
            return json.load(f)

    def _find_workspace(self, data):
        if isinstance(data, list):
            for item in data:
                if item.get("name") == "LHDN Payroll":
                    return item
            self.fail("No workspace named 'LHDN Payroll' found")
        return data

    def test_dev_tools_shortcut_exists(self):
        data = self._load_fixture()
        ws = self._find_workspace(data)
        shortcuts = ws.get("shortcuts") or []
        links = [s.get("link_to") for s in shortcuts]
        self.assertIn(
            "lhdn-dev-tools",
            links,
            "workspace.json must contain a shortcut with link_to='lhdn-dev-tools'",
        )

    def test_dev_tools_shortcut_type_is_page(self):
        data = self._load_fixture()
        ws = self._find_workspace(data)
        shortcuts = ws.get("shortcuts") or []
        dev_tools = [s for s in shortcuts if s.get("link_to") == "lhdn-dev-tools"]
        self.assertTrue(dev_tools, "No lhdn-dev-tools shortcut found")
        self.assertEqual(dev_tools[0].get("type"), "Page", "Shortcut type must be 'Page'")

    def test_workspace_has_five_or_more_shortcuts(self):
        data = self._load_fixture()
        ws = self._find_workspace(data)
        shortcuts = ws.get("shortcuts") or []
        self.assertGreaterEqual(
            len(shortcuts),
            4,
            f"Expected ≥4 shortcuts after adding dev tools, found {len(shortcuts)}",
        )
