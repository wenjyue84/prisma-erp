"""Tests for LHDN Payroll workspace fixture.

TDD RED phase: these tests fail because workspace.json does not exist yet.
"""
import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

WORKSPACE_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "fixtures",
    "workspace.json",
)


class TestLHDNPayrollWorkspaceFixture(FrappeTestCase):
    """Tests that the LHDN Payroll workspace fixture is correctly defined."""

    def _load_fixture(self):
        """Load the workspace fixture JSON file."""
        abs_path = os.path.abspath(WORKSPACE_FIXTURE_PATH)
        self.assertTrue(
            os.path.exists(abs_path),
            f"workspace.json not found at {abs_path}",
        )
        with open(abs_path) as f:
            data = json.load(f)
        return data

    def _find_workspace(self, data):
        """Return the LHDN Payroll workspace entry from fixture data."""
        # Fixture may be a list (multiple workspaces) or a single dict
        if isinstance(data, list):
            for item in data:
                if item.get("name") == "LHDN Payroll":
                    return item
            self.fail("No workspace named 'LHDN Payroll' found in fixture")
        elif isinstance(data, dict):
            self.assertEqual(data.get("name"), "LHDN Payroll")
            return data
        self.fail("workspace.json must be a list or dict")

    def test_workspace_fixture_file_exists(self):
        """workspace.json must exist in the fixtures directory."""
        abs_path = os.path.abspath(WORKSPACE_FIXTURE_PATH)
        self.assertTrue(os.path.exists(abs_path), f"Missing: {abs_path}")

    def test_workspace_name(self):
        """Workspace fixture must have name='LHDN Payroll'."""
        data = self._load_fixture()
        ws = self._find_workspace(data)
        self.assertEqual(ws.get("name"), "LHDN Payroll")

    def test_workspace_module(self):
        """Workspace fixture must belong to module 'LHDN Payroll Integration'."""
        data = self._load_fixture()
        ws = self._find_workspace(data)
        self.assertEqual(ws.get("module"), "LHDN Payroll Integration")

    def test_workspace_has_minimum_shortcuts(self):
        """Workspace must contain at least 4 shortcuts."""
        data = self._load_fixture()
        ws = self._find_workspace(data)
        shortcuts = ws.get("shortcuts") or []
        self.assertGreaterEqual(
            len(shortcuts),
            4,
            f"Expected ≥4 shortcuts, found {len(shortcuts)}",
        )

    def test_workspace_required_shortcuts(self):
        """Workspace must include shortcuts for the 4 required links."""
        data = self._load_fixture()
        ws = self._find_workspace(data)
        shortcuts = ws.get("shortcuts") or []
        labels = {s.get("label") or s.get("link_to") or "" for s in shortcuts}
        required = {"Salary Slip", "Expense Claim", "LHDN Payroll Compliance", "Background Jobs"}
        for req in required:
            self.assertIn(req, labels, f"Missing shortcut: {req}")
