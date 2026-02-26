"""
TDD Red Phase — Tests for lhdn_payroll_integration app scaffold (UT-001).

All tests assert that the app is correctly scaffolded per US-001 requirements:
  - App installed on site
  - hooks.py with doc_events for Salary Slip and Expense Claim
  - hooks.py with scheduler_events (hourly + monthly)
  - modules.txt exists
  - install.py stubs exist
  - Directory structure (services/, utils/, fixtures/)

These tests are expected to FAIL until US-001 is implemented.
"""
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration import hooks


class TestAppScaffold(FrappeTestCase):
    """Tests for US-001: Create custom app scaffold."""

    # --- AC 1: App is installed ---
    def test_app_is_installed(self):
        """bench --site frontend list-apps shows lhdn_payroll_integration."""
        installed_apps = frappe.get_installed_apps()
        self.assertIn(
            "lhdn_payroll_integration",
            installed_apps,
            "lhdn_payroll_integration must be in the installed apps list",
        )

    # --- AC 2: hooks.py doc_events for Salary Slip ---
    def test_hooks_doc_events_salary_slip(self):
        """hooks.py contains doc_events for Salary Slip (on_submit, on_cancel)."""
        doc_events = getattr(hooks, "doc_events", None)
        self.assertIsNotNone(doc_events, "hooks.py must define doc_events")
        self.assertIn("Salary Slip", doc_events, "doc_events must include 'Salary Slip'")

        ss_events = doc_events["Salary Slip"]
        self.assertIn("on_submit", ss_events, "Salary Slip doc_events must have on_submit")
        self.assertIn("on_cancel", ss_events, "Salary Slip doc_events must have on_cancel")

        # Verify the handler paths match US-001 spec
        self.assertEqual(
            ss_events["on_submit"],
            "lhdn_payroll_integration.services.submission_service.enqueue_salary_slip_submission",
        )
        self.assertEqual(
            ss_events["on_cancel"],
            "lhdn_payroll_integration.services.cancellation_service.handle_salary_slip_cancel",
        )

    # --- AC 2: hooks.py doc_events for Expense Claim ---
    def test_hooks_doc_events_expense_claim(self):
        """hooks.py contains doc_events for Expense Claim (on_submit, on_cancel)."""
        doc_events = getattr(hooks, "doc_events", None)
        self.assertIsNotNone(doc_events, "hooks.py must define doc_events")
        self.assertIn("Expense Claim", doc_events, "doc_events must include 'Expense Claim'")

        ec_events = doc_events["Expense Claim"]
        self.assertIn("on_submit", ec_events, "Expense Claim doc_events must have on_submit")
        self.assertIn("on_cancel", ec_events, "Expense Claim doc_events must have on_cancel")

        # Verify the handler paths match US-001 spec
        self.assertEqual(
            ec_events["on_submit"],
            "lhdn_payroll_integration.services.submission_service.enqueue_expense_claim_submission",
        )
        self.assertEqual(
            ec_events["on_cancel"],
            "lhdn_payroll_integration.services.cancellation_service.handle_expense_claim_cancel",
        )

    # --- AC 3: hooks.py scheduler_events ---
    def test_hooks_scheduler_events(self):
        """hooks.py contains scheduler_events with hourly and monthly entries."""
        scheduler_events = getattr(hooks, "scheduler_events", None)
        self.assertIsNotNone(scheduler_events, "hooks.py must define scheduler_events")

        # Hourly: status poller
        self.assertIn("hourly", scheduler_events, "scheduler_events must have 'hourly' key")
        hourly = scheduler_events["hourly"]
        self.assertIn(
            "lhdn_payroll_integration.services.status_poller.poll_pending_documents",
            hourly,
            "Hourly scheduler must include status_poller.poll_pending_documents",
        )

        # Monthly: consolidation
        self.assertIn("monthly", scheduler_events, "scheduler_events must have 'monthly' key")
        monthly = scheduler_events["monthly"]
        self.assertIn(
            "lhdn_payroll_integration.services.consolidation_service.run_monthly_consolidation",
            monthly,
            "Monthly scheduler must include consolidation_service.run_monthly_consolidation",
        )

    # --- AC 4: modules.txt ---
    def test_modules_txt_exists(self):
        """modules.txt exists with content 'LHDN Payroll Integration'."""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        modules_path = os.path.join(app_dir, "modules.txt")

        self.assertTrue(os.path.isfile(modules_path), f"modules.txt must exist at {modules_path}")

        with open(modules_path) as f:
            content = f.read().strip()
        self.assertIn(
            "LHDN Payroll Integration",
            content,
            "modules.txt must contain 'LHDN Payroll Integration'",
        )

    # --- AC 5: install.py stubs ---
    def test_install_py_stubs_exist(self):
        """install.py exists with after_install() and after_migrate() stubs."""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        install_path = os.path.join(app_dir, "install.py")

        self.assertTrue(os.path.isfile(install_path), f"install.py must exist at {install_path}")

        # Import and check callables exist
        import importlib.util

        spec = importlib.util.spec_from_file_location("install", install_path)
        install_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(install_module)

        self.assertTrue(
            callable(getattr(install_module, "after_install", None)),
            "install.py must define a callable after_install()",
        )
        self.assertTrue(
            callable(getattr(install_module, "after_migrate", None)),
            "install.py must define a callable after_migrate()",
        )

    # --- AC 6: Directory structure ---
    def test_directory_structure(self):
        """App has services/, utils/, fixtures/ directories."""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        for subdir in ("services", "utils", "fixtures"):
            dir_path = os.path.join(app_dir, subdir)
            self.assertTrue(
                os.path.isdir(dir_path),
                f"Directory '{subdir}/' must exist at {dir_path}",
            )
            init_path = os.path.join(dir_path, "__init__.py")
            self.assertTrue(
                os.path.isfile(init_path),
                f"'{subdir}/__init__.py' must exist for proper Python packaging",
            )
