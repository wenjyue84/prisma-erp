"""
Base HTTP test session and TestCase class for Prisma ERP tests.

Every test class should extend ERPNextTestCase which provides:
  - self.session  — authenticated requests.Session
  - self.get()    — convenience GET
  - self.post()   — convenience POST
  - self.api()    — call /api/method/<method>
  - self.resource()— call /api/resource/<doctype>
  - Assertion helpers: assert_status, assert_keys, assert_no_error
"""

import json
import time
import unittest
from typing import Any

import requests

from tests.config import BASE_URL, USERNAME, PASSWORD, TIMEOUT


class ERPNextSession:
    """Authenticated HTTP session wrapper for ERPNext API."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self._csrf_token: str | None = None
        self._login()

    # ── Auth ───────────────────────────────────────────────────────────────────
    def _login(self) -> None:
        resp = self.session.post(
            f"{self.base_url}/api/method/login",
            data={"usr": USERNAME, "pwd": PASSWORD},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("message") not in ("Logged In", "logged_in", None):
            raise RuntimeError(f"Login failed: {data}")
        # Grab CSRF token from response header
        self._csrf_token = resp.headers.get("X-Frappe-CSRF-Token") or data.get("csrf_token")

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"X-Frappe-CSRF-Token": self._csrf_token or ""}
        if extra:
            h.update(extra)
        return h

    # ── HTTP helpers ───────────────────────────────────────────────────────────
    def get(self, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", TIMEOUT)
        return self.session.get(f"{self.base_url}{path}", **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", TIMEOUT)
        kwargs.setdefault("headers", {})
        kwargs["headers"].update(self._headers())
        return self.session.post(f"{self.base_url}{path}", **kwargs)

    def api(self, method: str, **params) -> requests.Response:
        """Call /api/method/<method> with keyword params as JSON body."""
        return self.post(
            f"/api/method/{method}",
            json=params,
        )

    def resource(self, doctype: str, name: str | None = None, **params) -> requests.Response:
        """GET /api/resource/<doctype>[/<name>]."""
        path = f"/api/resource/{doctype}"
        if name:
            path += f"/{name}"
        return self.get(path, params=params)

    # ── Timing ─────────────────────────────────────────────────────────────────
    def timed_get(self, path: str, **kwargs) -> tuple[requests.Response, float]:
        t0 = time.perf_counter()
        resp = self.get(path, **kwargs)
        return resp, (time.perf_counter() - t0) * 1000

    def timed_api(self, method: str, **params) -> tuple[requests.Response, float]:
        t0 = time.perf_counter()
        resp = self.api(method, **params)
        return resp, (time.perf_counter() - t0) * 1000


# Shared session (created once per process)
_shared_session: ERPNextSession | None = None


def get_session() -> ERPNextSession:
    global _shared_session
    if _shared_session is None:
        _shared_session = ERPNextSession()
    return _shared_session


class ERPNextTestCase(unittest.TestCase):
    """Base class for all Prisma ERP HTTP test cases."""

    # Subclasses set this to categorise tests in reports
    category: str = "uncategorised"

    @classmethod
    def setUpClass(cls):
        cls.session = get_session()

    # ── Assertion helpers ──────────────────────────────────────────────────────
    def assert_status(self, resp: requests.Response, expected: int = 200, msg: str = "") -> None:
        self.assertEqual(
            resp.status_code,
            expected,
            msg or f"Expected HTTP {expected}, got {resp.status_code}. Body: {resp.text[:300]}",
        )

    def assert_keys(self, data: dict, *keys: str) -> None:
        for k in keys:
            self.assertIn(k, data, f"Missing key '{k}' in response: {list(data.keys())}")

    def assert_no_error(self, resp: requests.Response) -> dict:
        """Assert HTTP 200 and no exc_type in body; return parsed JSON."""
        self.assert_status(resp)
        body = resp.json()
        self.assertNotIn(
            "exc_type",
            body,
            f"API returned an exception: {body.get('exception') or body.get('exc_type')}",
        )
        return body

    def parse_json(self, resp: requests.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            self.fail(f"Response is not JSON: {resp.text[:200]}")
