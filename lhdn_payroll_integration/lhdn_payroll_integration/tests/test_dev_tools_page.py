"""Tests for the LHDN Developer Tools Frappe page.

Three test classes:
- TestDevToolsPageFiles    — all 4 page files exist, JSON is well-formed
- TestDevToolsBackendMethods — permission guard; check_exemption for Employee type
- TestDevToolsWorkspaceShortcut — workspace fixture has lhdn-dev-tools shortcut
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


class TestRetrieveLhdnDocument(FrappeTestCase):
    """retrieve_lhdn_document() calls LHDN raw endpoint using UUID and stores response."""

    _MODULE = "lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools"

    def _import_module(self):
        import importlib
        return importlib.import_module(self._MODULE)

    def test_permission_guard_blocks_non_sm(self):
        """Non-System Manager caller gets PermissionError."""
        mod = self._import_module()
        with patch(f"{self._MODULE}.frappe.get_roles", return_value=["Employee"]):
            with self.assertRaises((frappe.PermissionError, PermissionError)):
                mod.retrieve_lhdn_document("Sal Slip/Test/00001", "Salary Slip")

    def test_returns_error_when_no_uuid(self):
        """Returns {success: False} when document has no custom_lhdn_uuid."""
        mod = self._import_module()

        mock_doc = MagicMock()
        mock_doc.custom_lhdn_uuid = None

        with patch(f"{self._MODULE}.frappe.get_roles", return_value=["System Manager"]):
            with patch(f"{self._MODULE}.frappe.get_doc", return_value=mock_doc):
                result = mod.retrieve_lhdn_document("Sal Slip/Test/00001", "Salary Slip")

        self.assertFalse(result["success"])
        self.assertIn("UUID", result.get("error_detail", ""))

    def test_uuid_used_in_request_url(self):
        """The LHDN UUID from the document appears in the GET request URL."""
        mod = self._import_module()

        test_uuid = "abc-123-def-456"

        mock_doc = MagicMock()
        mock_doc.custom_lhdn_uuid = test_uuid

        mock_company = MagicMock()
        mock_company.custom_sandbox_url = "https://sandbox.myinvois.hasil.gov.my"
        mock_company.custom_client_id = "test_client"
        mock_company.custom_client_secret = "test_secret"

        # Token response
        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {"access_token": "dummy_token"}

        # Document response
        mock_doc_resp = MagicMock()
        mock_doc_resp.ok = True
        mock_doc_resp.text = "<Invoice>test xml</Invoice>"

        with patch(f"{self._MODULE}.frappe.get_roles", return_value=["System Manager"]):
            with patch(f"{self._MODULE}.frappe.get_doc", side_effect=[mock_doc, mock_company]):
                with patch(f"{self._MODULE}.frappe.db") as mock_db:
                    mock_db.get_value.return_value = "Test Company"
                    with patch(f"{self._MODULE}.requests.post", return_value=mock_token_resp):
                        with patch(f"{self._MODULE}.requests.get", return_value=mock_doc_resp) as mock_get:
                            result = mod.retrieve_lhdn_document("Sal Slip/Test/00001", "Salary Slip")

        # UUID must appear in the GET request URL
        call_url = mock_get.call_args[0][0]
        self.assertIn(test_uuid, call_url, f"UUID '{test_uuid}' not found in GET URL: {call_url}")

    def test_response_stored_in_custom_field(self):
        """Raw XML response is saved to custom_lhdn_raw_document via db.set_value."""
        mod = self._import_module()

        test_uuid = "uuid-987"
        expected_xml = "<Invoice>validated xml content</Invoice>"

        mock_doc = MagicMock()
        mock_doc.custom_lhdn_uuid = test_uuid

        mock_company = MagicMock()
        mock_company.custom_sandbox_url = "https://sandbox.myinvois.hasil.gov.my"
        mock_company.custom_client_id = "cid"
        mock_company.custom_client_secret = "csec"

        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {"access_token": "tok"}

        mock_doc_resp = MagicMock()
        mock_doc_resp.ok = True
        mock_doc_resp.text = expected_xml

        with patch(f"{self._MODULE}.frappe.get_roles", return_value=["System Manager"]):
            with patch(f"{self._MODULE}.frappe.get_doc", side_effect=[mock_doc, mock_company]):
                with patch(f"{self._MODULE}.frappe.db") as mock_db:
                    mock_db.get_value.return_value = "Test Company"
                    with patch(f"{self._MODULE}.requests.post", return_value=mock_token_resp):
                        with patch(f"{self._MODULE}.requests.get", return_value=mock_doc_resp):
                            result = mod.retrieve_lhdn_document("Sal Slip/Test/00001", "Salary Slip")

        self.assertTrue(result["success"], f"Expected success but got: {result}")
        self.assertEqual(result["raw_xml"], expected_xml)

        # db.set_value must have been called with the raw XML
        set_value_calls = [str(c) for c in mock_db.set_value.call_args_list]
        xml_stored = any(expected_xml in c for c in set_value_calls)
        self.assertTrue(xml_stored, f"Expected raw XML in db.set_value calls: {set_value_calls}")
