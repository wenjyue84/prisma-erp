"""JSON report generator for the Prisma ERP test suite."""

import json
import os
import traceback
import unittest
from datetime import datetime, timezone


class JSONTestResult(unittest.TestResult):
    """Collect test results and render as JSON."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.results: list[dict] = []
        self._timers: dict[str, float] = {}
        self._started_at: datetime | None = None

    def startTestRun(self):
        self._started_at = datetime.now(timezone.utc)

    def startTest(self, test):
        import time
        super().startTest(test)
        self._timers[test.id()] = time.perf_counter()

    def _elapsed(self, test) -> float:
        import time
        start = self._timers.pop(test.id(), time.perf_counter())
        return round((time.perf_counter() - start) * 1000, 2)  # ms

    def addSuccess(self, test):
        self.results.append({
            "id": test.id(),
            "name": test._testMethodName,
            "description": (test._testMethodDoc or "").strip(),
            "category": getattr(test, "category", "uncategorised"),
            "status": "PASS",
            "duration_ms": self._elapsed(test),
            "error": None,
        })

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.results.append({
            "id": test.id(),
            "name": test._testMethodName,
            "description": (test._testMethodDoc or "").strip(),
            "category": getattr(test, "category", "uncategorised"),
            "status": "FAIL",
            "duration_ms": self._elapsed(test),
            "error": {
                "type": err[0].__name__,
                "message": str(err[1]),
                "traceback": traceback.format_tb(err[2]),
            },
        })

    def addError(self, test, err):
        super().addError(test, err)
        self.results.append({
            "id": test.id(),
            "name": test._testMethodName,
            "description": (test._testMethodDoc or "").strip(),
            "category": getattr(test, "category", "uncategorised"),
            "status": "ERROR",
            "duration_ms": self._elapsed(test),
            "error": {
                "type": err[0].__name__,
                "message": str(err[1]),
                "traceback": traceback.format_tb(err[2]),
            },
        })

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.results.append({
            "id": test.id(),
            "name": test._testMethodName,
            "description": (test._testMethodDoc or "").strip(),
            "category": getattr(test, "category", "uncategorised"),
            "status": "SKIP",
            "duration_ms": 0,
            "error": {"type": "Skip", "message": reason, "traceback": []},
        })

    def to_dict(self, suite_label: str = "Prisma ERP Test Suite") -> dict:
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        errored = sum(1 for r in self.results if r["status"] == "ERROR")
        skipped = sum(1 for r in self.results if r["status"] == "SKIP")

        by_category: dict[str, list] = {}
        for r in self.results:
            by_category.setdefault(r["category"], []).append(r)

        return {
            "suite": suite_label,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "errored": errored,
                "skipped": skipped,
                "pass_rate": f"{(passed / total * 100):.1f}%" if total else "N/A",
            },
            "categories": {
                cat: {
                    "total": len(tests),
                    "passed": sum(1 for t in tests if t["status"] == "PASS"),
                    "failed": sum(1 for t in tests if t["status"] in ("FAIL", "ERROR")),
                    "tests": tests,
                }
                for cat, tests in by_category.items()
            },
            "all_results": self.results,
        }

    def save(self, path: str, suite_label: str = "Prisma ERP Test Suite") -> str:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = self.to_dict(suite_label)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return path
