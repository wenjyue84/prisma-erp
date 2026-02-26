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
            5,
            f"Expected ≥5 shortcuts after adding dev tools, found {len(shortcuts)}",
        )
