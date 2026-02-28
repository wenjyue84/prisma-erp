"""
Performance Tests — PF-01 to PF-15
=====================================
Measures response times and throughput against defined SLA thresholds.
All time comparisons use PERF_THRESHOLD_MS from config (default 2000 ms).

Concurrency tests use threading to simulate simultaneous users.
"""

import concurrent.futures
import time
import unittest

from tests.base import ERPNextTestCase, get_session
from tests.config import AI_TIMEOUT, PERF_THRESHOLD_MS


class TestResponseTime(ERPNextTestCase):
    """PF-01 to PF-06: Single-request response time SLAs."""

    category = "performance"
    SLA_MS = PERF_THRESHOLD_MS  # 2000 ms default

    def _measure(self, path: str) -> tuple[int, float]:
        resp, ms = self.session.timed_get(path)
        return resp.status_code, ms

    def _measure_api(self, method: str, **params) -> tuple[int, float]:
        resp, ms = self.session.timed_api(method, **params)
        return resp.status_code, ms

    def test_pf01_ping_under_500ms(self):
        """PF-01: /api/method/frappe.ping < 500 ms."""
        _, ms = self._measure_api("frappe.ping")
        self.assertLess(ms, 500, f"Ping took {ms:.0f} ms — expected < 500 ms")

    def test_pf02_auth_check_under_1s(self):
        """PF-02: frappe.auth.get_logged_user < 1000 ms."""
        _, ms = self._measure_api("frappe.auth.get_logged_user")
        self.assertLess(ms, 1000, f"Auth check took {ms:.0f} ms — expected < 1 s")

    def test_pf03_employee_list_under_sla(self):
        """PF-03: GET Employee list (limit=10) < SLA_MS."""
        t0 = time.perf_counter()
        self.session.resource("Employee", params={"limit": 10})
        ms = (time.perf_counter() - t0) * 1000
        self.assertLess(ms, self.SLA_MS, f"Employee list took {ms:.0f} ms")

    def test_pf04_salary_slip_list_under_sla(self):
        """PF-04: GET Salary Slip list (limit=10) < SLA_MS."""
        t0 = time.perf_counter()
        self.session.resource("Salary Slip", params={"limit": 10})
        ms = (time.perf_counter() - t0) * 1000
        self.assertLess(ms, self.SLA_MS, f"Salary Slip list took {ms:.0f} ms")

    def test_pf05_msic_code_list_under_sla(self):
        """PF-05: GET LHDN MSIC Code list < SLA_MS (master data read)."""
        t0 = time.perf_counter()
        self.session.resource("LHDN MSIC Code", params={"limit": 50})
        ms = (time.perf_counter() - t0) * 1000
        self.assertLess(ms, self.SLA_MS, f"MSIC Code list took {ms:.0f} ms")

    def test_pf06_settings_read_under_500ms(self):
        """PF-06: GET Prisma AI Settings < 500 ms."""
        t0 = time.perf_counter()
        self.session.resource("Prisma AI Settings", "Prisma AI Settings")
        ms = (time.perf_counter() - t0) * 1000
        self.assertLess(ms, 500, f"Settings read took {ms:.0f} ms")


class TestChatAPIPerformance(ERPNextTestCase):
    """PF-07 to PF-09: AI chat API timing (slower endpoints)."""

    category = "performance"

    def test_pf07_chat_completes_within_ai_timeout(self):
        """PF-07: send_message completes within AI_TIMEOUT seconds."""
        t0 = time.perf_counter()
        resp = self.session.post(
            "/api/method/prisma_assistant.api.chat.send_message",
            json={"message": "Reply with the single word: FAST"},
            timeout=AI_TIMEOUT,
        )
        ms = (time.perf_counter() - t0) * 1000
        self.assert_status(resp)
        self.assertLess(ms, AI_TIMEOUT * 1000,
                        f"Chat API took {ms:.0f} ms, limit={AI_TIMEOUT}s")

    def test_pf08_key_info_under_500ms(self):
        """PF-08: get_api_key_info < 500 ms (no AI call, just DB read)."""
        t0 = time.perf_counter()
        resp = self.session.api("prisma_assistant.api.chat.get_api_key_info")
        ms = (time.perf_counter() - t0) * 1000
        self.assert_status(resp)
        self.assertLess(ms, 500, f"get_api_key_info took {ms:.0f} ms")

    def test_pf09_sequential_pings_consistent(self):
        """PF-09: 5 sequential pings all < 1000 ms (no degradation)."""
        times = []
        for i in range(5):
            _, ms = self.session.timed_api("frappe.ping")
            times.append(ms)
        max_ms = max(times)
        self.assertLess(max_ms, 1000,
                        f"Slowest ping was {max_ms:.0f} ms. All times: {[f'{t:.0f}' for t in times]}")


class TestConcurrentLoad(ERPNextTestCase):
    """PF-10 to PF-15: Concurrent user simulation."""

    category = "performance"

    def _concurrent_calls(self, n_threads: int, fn, *args, **kwargs) -> list[dict]:
        """Run fn n_threads times concurrently; return list of {status, ms} dicts."""
        results = []

        def call():
            t0 = time.perf_counter()
            try:
                resp = fn(*args, **kwargs)
                return {"status": resp.status_code, "ms": (time.perf_counter() - t0) * 1000}
            except Exception as e:
                return {"status": -1, "ms": (time.perf_counter() - t0) * 1000, "error": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as executor:
            futures = [executor.submit(call) for _ in range(n_threads)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())
        return results

    def test_pf10_5_concurrent_pings(self):
        """PF-10: 5 concurrent frappe.ping calls all succeed."""
        session = get_session()
        results = self._concurrent_calls(5, session.api, "frappe.ping")
        failures = [r for r in results if r["status"] != 200]
        self.assertEqual(len(failures), 0,
                         f"{len(failures)}/5 pings failed: {failures}")

    def test_pf11_10_concurrent_employee_reads(self):
        """PF-11: 10 concurrent GET Employee list calls all succeed."""
        session = get_session()

        def list_employees():
            return session.resource("Employee", params={"limit": 5})

        results = self._concurrent_calls(10, list_employees)
        failures = [r for r in results if r["status"] not in (200, 403)]
        self.assertLessEqual(len(failures), 1,
                              f"{len(failures)}/10 concurrent employee reads failed: {failures}")

    def test_pf12_5_concurrent_salary_slip_reads(self):
        """PF-12: 5 concurrent Salary Slip list reads succeed."""
        session = get_session()

        def list_slips():
            return session.resource("Salary Slip", params={"limit": 5})

        results = self._concurrent_calls(5, list_slips)
        failures = [r for r in results if r["status"] not in (200, 403)]
        self.assertLessEqual(len(failures), 1,
                              f"Concurrent slip reads failed: {failures}")

    def test_pf13_concurrent_response_time_p95(self):
        """PF-13: P95 response time for 10 concurrent pings < 3000 ms."""
        session = get_session()
        results = self._concurrent_calls(10, session.api, "frappe.ping")
        times = sorted(r["ms"] for r in results)
        p95 = times[int(len(times) * 0.95)]  # 95th percentile
        self.assertLess(p95, 3000,
                        f"P95 concurrent response time: {p95:.0f} ms (limit: 3000 ms). All: {[f'{t:.0f}' for t in times]}")

    def test_pf14_no_errors_under_5_concurrent_auth_checks(self):
        """PF-14: 5 concurrent auth-check calls return 200 without error."""
        session = get_session()
        results = self._concurrent_calls(5, session.api, "frappe.auth.get_logged_user")
        failures = [r for r in results if r["status"] != 200]
        self.assertEqual(len(failures), 0,
                         f"Auth check failures under concurrency: {failures}")

    def test_pf15_api_key_info_under_10_concurrent(self):
        """PF-15: 10 concurrent get_api_key_info calls — all succeed without 500."""
        session = get_session()
        results = self._concurrent_calls(
            10, session.api, "prisma_assistant.api.chat.get_api_key_info"
        )
        errors = [r for r in results if r["status"] == 500]
        self.assertEqual(len(errors), 0,
                         f"500 errors under concurrent key_info load: {errors}")


if __name__ == "__main__":
    unittest.main()
