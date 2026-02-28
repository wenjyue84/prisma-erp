#!/usr/bin/env python3
"""
SPIRAL Phase T — Test Synthesis
Reads latest test-reports/*/report.json and turns FAIL/ERROR results into story candidates.
Deduplicates against existing prd.json titles using 60% word-overlap heuristic.
Writes {"stories": [...]} to --output path.
stdlib only — no extra dependencies.
"""
import argparse
import json
import os
import re
import sys
from typing import Any


PRIORITY_MAP = {
    "smoke": "critical",
    "security": "critical",
    "regression": "high",
    "api_contract": "high",
    "integration": "high",
    "unit": "medium",
    "unit:prisma_ai": "medium",
    "unit:lhdn_payroll": "medium",
    "edge_cases": "medium",
    "performance": "low",
}


def find_latest_report(reports_dir: str) -> str | None:
    if not os.path.isdir(reports_dir):
        return None
    subdirs = sorted(
        [d for d in os.listdir(reports_dir) if os.path.isdir(os.path.join(reports_dir, d))],
        reverse=True,
    )
    for d in subdirs:
        candidate = os.path.join(reports_dir, d, "report.json")
        if os.path.isfile(candidate):
            return candidate
    return None


def normalize(text: str) -> str:
    """Lowercase alphanum words only."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def overlap_ratio(a: str, b: str) -> float:
    """Fraction of words in `a` that also appear in `b`."""
    wa = normalize(a)
    wb = normalize(b)
    if not wa:
        return 0.0
    return len(wa & wb) / len(wa)


def is_duplicate(candidate_title: str, existing_titles: list[str], threshold: float = 0.6) -> bool:
    for existing in existing_titles:
        if overlap_ratio(candidate_title, existing) >= threshold:
            return True
        if overlap_ratio(existing, candidate_title) >= threshold:
            return True
    return False


def parse_test_id(test_id: str) -> tuple[str, str, str]:
    """
    Parse 'tests.unit.lhdn_payroll.test_pcb.TestClass.test_method'
    → (category_hint, class_name, method_name)
    """
    parts = test_id.split(".")
    method = parts[-1] if parts else test_id
    class_name = parts[-2] if len(parts) >= 2 else ""
    # category from module path: tests.<category>.<sub>...
    category_hint = ".".join(parts[1:3]) if len(parts) >= 3 else "unit"
    return category_hint, class_name, method


def result_to_story(result: dict[str, Any]) -> dict[str, Any]:
    """Convert a FAIL/ERROR test result to a story candidate."""
    test_id = result.get("id", "")
    name = result.get("name", test_id)
    description = result.get("description", "")
    category = result.get("category", "unit")
    error = result.get("error") or {}

    category_hint, class_name, method_name = parse_test_id(test_id)

    # Determine priority from category
    priority = PRIORITY_MAP.get(category, PRIORITY_MAP.get(category_hint.split(":")[0], "medium"))

    # Build human-readable title from test name
    # test_pcb_method_name → "Fix PCB method name failure"
    readable = method_name.lstrip("test_").replace("_", " ").strip()
    if class_name:
        cls_readable = class_name.replace("Test", "").replace("_", " ").strip()
        title = f"Fix failing test: {cls_readable} — {readable}"
    else:
        title = f"Fix failing test: {readable}"

    # Build acceptance criteria
    ac = [f"Test `{test_id}` passes without error."]
    if error.get("message"):
        # Truncate long error messages
        msg = error["message"][:200].replace("\n", " ")
        ac.append(f"Root cause resolved: {msg}")

    tech_notes = [f"Test category: {category}", f"Test ID: {test_id}"]
    if error.get("type"):
        tech_notes.append(f"Error type: {error['type']}")
    if description:
        tech_notes.append(f"Test description: {description}")

    return {
        "title": title,
        "priority": priority,
        "description": (
            f"Automated test `{name}` is failing with status {result.get('status', 'FAIL')}. "
            f"This indicates a regression or missing implementation in the {category} suite. "
            f"{description}"
        ).strip(),
        "acceptanceCriteria": ac,
        "technicalNotes": tech_notes,
        "dependencies": [],
        "estimatedComplexity": "small",
        "_source": f"test-synthesis:{test_id}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SPIRAL test synthesis")
    parser.add_argument("--prd", default="prd.json", help="Path to prd.json")
    parser.add_argument("--reports-dir", default="test-reports", help="Test reports directory")
    parser.add_argument(
        "--output",
        default="scripts/spiral/_test_stories_output.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    # Load existing titles from prd.json for dedup
    existing_titles: list[str] = []
    if os.path.isfile(args.prd):
        with open(args.prd, encoding="utf-8") as f:
            prd = json.load(f)
        existing_titles = [s.get("title", "") for s in prd.get("userStories", [])]

    # Find latest report
    report_path = find_latest_report(args.reports_dir)
    if not report_path:
        print(f"[synthesize] WARNING: No test report found in {args.reports_dir}/")
        output = {"stories": []}
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        print(f"[synthesize] Wrote 0 stories → {args.output}")
        return 0

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    report_dir = os.path.basename(os.path.dirname(report_path))
    all_results = report.get("all_results", [])
    failures = [r for r in all_results if r.get("status") in ("FAIL", "ERROR")]
    print(f"[synthesize] Report: {report_dir} — {len(failures)} failures/errors out of {len(all_results)}")

    # Convert to story candidates, dedup against prd + each other
    candidates = []
    seen_titles: list[str] = list(existing_titles)

    for result in failures:
        story = result_to_story(result)
        title = story["title"]
        if is_duplicate(title, seen_titles):
            print(f"[synthesize] Skipping duplicate: {title}")
            continue
        candidates.append(story)
        seen_titles.append(title)

    print(f"[synthesize] Generated {len(candidates)} new story candidates from test failures")

    output = {"stories": candidates}
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    tmp = args.output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    os.replace(tmp, args.output)
    print(f"[synthesize] Wrote {len(candidates)} stories -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
