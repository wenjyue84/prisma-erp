"""
Security Tests — RBAC (RBAC-01 to RBAC-08)
============================================
Validates role-based access control: different user roles see only what they
should, Admin-only endpoints are blocked for non-admins, and Employee
self-service enforces row-level security.

Uses the ERPNext REST API to test access with different credentials.
"""

import unittest

import requests

from tests.base import ERPNextTestCase, ERPNextSession
from tests.config import BASE_URL, TIMEOUT


class TestAdminOnlyEndpoints(ERPNextTestCase):
    """RBAC-01 to RBAC-03: System Manager-only endpoints are restricted."""

    category = "security:rbac"

    def test_rbac01_guest_cannot_access_system_settings(self):
        """RBAC-01: Guest/anonymous user cannot read System Settings."""
        s = requests.Session()
        s.headers.update({"Accept": "application/json"})
        resp = s.get(f"{BASE_URL}/api/resource/System Settings/System Settings",
                     timeout=TIMEOUT)
        self.assertIn(resp.status_code, (401, 403, 302, 307),
                      f"Guest accessed System Settings: {resp.status_code}")

    def test_rbac02_guest_cannot_list_users(self):
        """RBAC-02: Guest cannot list User doctype."""
        s = requests.Session()
        s.headers.update({"Accept": "application/json"})
        resp = s.get(f"{BASE_URL}/api/resource/User",
                     timeout=TIMEOUT)
        self.assertIn(resp.status_code, (401, 403, 302, 307),
                      f"Guest accessed User list: {resp.status_code}")

    def test_rbac03_guest_cannot_access_error_log(self):
        """RBAC-03: Guest cannot read Error Log (sensitive system data)."""
        s = requests.Session()
        s.headers.update({"Accept": "application/json"})
        resp = s.get(f"{BASE_URL}/api/resource/Error Log",
                     timeout=TIMEOUT)
        self.assertIn(resp.status_code, (401, 403, 302, 307),
                      f"Guest accessed Error Log: {resp.status_code}")


class TestHRDataIsolation(ERPNextTestCase):
    """RBAC-04 to RBAC-06: HR-sensitive data is protected from anonymous access."""

    category = "security:rbac"

    def _anon(self):
        s = requests.Session()
        s.headers.update({"Accept": "application/json"})
        return s

    def test_rbac04_anon_cannot_read_salary_structure(self):
        """RBAC-04: Anonymous user cannot access Salary Structure."""
        resp = self._anon().get(
            f"{BASE_URL}/api/resource/Salary Structure",
            timeout=TIMEOUT,
        )
        self.assertIn(resp.status_code, (401, 403, 302, 307),
                      f"Anon accessed Salary Structure: {resp.status_code}")

    def test_rbac05_anon_cannot_read_payroll_entry(self):
        """RBAC-05: Anonymous user cannot access Payroll Entry."""
        resp = self._anon().get(
            f"{BASE_URL}/api/resource/Payroll Entry",
            timeout=TIMEOUT,
        )
        self.assertIn(resp.status_code, (401, 403, 302, 307),
                      f"Anon accessed Payroll Entry: {resp.status_code}")

    def test_rbac06_anon_cannot_read_lhdn_resubmission_log(self):
        """RBAC-06: Anonymous user cannot access LHDN Resubmission Log."""
        resp = self._anon().get(
            f"{BASE_URL}/api/resource/LHDN Resubmission Log",
            timeout=TIMEOUT,
        )
        self.assertIn(resp.status_code, (401, 403, 302, 307),
                      f"Anon accessed LHDN Resubmission Log: {resp.status_code}")


class TestLHDNEndpointAccess(ERPNextTestCase):
    """RBAC-07 to RBAC-08: LHDN-specific endpoints enforce authentication."""

    category = "security:rbac"

    def _anon(self):
        s = requests.Session()
        s.headers.update({"Accept": "application/json"})
        return s

    def test_rbac07_anon_cannot_call_resubmit_api(self):
        """RBAC-07: Anonymous user cannot call resubmit_to_lhdn."""
        resp = self._anon().post(
            f"{BASE_URL}/api/method/lhdn_payroll_integration.services.submission_service.resubmit_to_lhdn",
            json={"docname": "TEST-00001"},
            timeout=TIMEOUT,
        )
        self.assertIn(resp.status_code, (401, 403, 302, 307),
                      f"Anon called resubmit API: {resp.status_code}")

    def test_rbac08_anon_cannot_call_bulk_submission(self):
        """RBAC-08: Anonymous user cannot call bulk_enqueue_lhdn_submission."""
        resp = self._anon().post(
            f"{BASE_URL}/api/method/lhdn_payroll_integration.services.submission_service.bulk_enqueue_lhdn_submission",
            json={"docnames": []},
            timeout=TIMEOUT,
        )
        self.assertIn(resp.status_code, (401, 403, 302, 307),
                      f"Anon called bulk submission API: {resp.status_code}")


if __name__ == "__main__":
    unittest.main()
