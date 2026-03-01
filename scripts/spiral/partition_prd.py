#!/usr/bin/env python3
"""
SPIRAL Parallel Phase — Partition PRD
Splits pending stories into N worker prd.json files using:
  1. Priority-aware ordering: critical → high → medium → low
  2. Dependency-grouped assignment: stories with pending deps go to the same worker

Completed stories are included in every worker file (ralph needs them for dep checks).
"""
import argparse
import json
import os
import sys

# Force UTF-8 stdout — prevents UnicodeEncodeError on Windows cp1252 terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def priority_key(story: dict) -> int:
    return PRIORITY_RANK.get(story.get("priority", "medium"), 2)


def assign_stories(pending: list[dict], n_workers: int) -> list[list[dict]]:
    """
    Assign pending stories to n worker buckets:
    1. Sort all pending stories by priority (critical first).
    2. Co-locate a story with its already-assigned pending dependency's worker.
    3. Otherwise assign to the least-loaded worker.
    """
    if not pending:
        return [[] for _ in range(n_workers)]

    pending_ids = {s["id"] for s in pending}

    # Sort by priority so high-priority stories get bucket assignment before low-priority
    pending_sorted = sorted(pending, key=priority_key)

    buckets: list[list[dict]] = [[] for _ in range(n_workers)]
    assignments: dict[str, int] = {}  # story_id → bucket index

    for story in pending_sorted:
        sid = story["id"]

        # Check if any *pending* dependency is already assigned — co-locate with it
        deps_pending = [d for d in story.get("dependencies", []) if d in pending_ids]
        assigned_worker: int | None = None
        for dep_id in deps_pending:
            if dep_id in assignments:
                assigned_worker = assignments[dep_id]
                break

        # No dep constraint → assign to least-loaded worker
        if assigned_worker is None:
            assigned_worker = min(range(n_workers), key=lambda i: len(buckets[i]))

        buckets[assigned_worker].append(story)
        assignments[sid] = assigned_worker

    return buckets


def main() -> int:
    parser = argparse.ArgumentParser(description="Partition prd.json for parallel ralph workers")
    parser.add_argument("--prd", required=True, help="Path to main prd.json")
    parser.add_argument("--workers", type=int, required=True, help="Number of workers")
    parser.add_argument("--outdir", required=True, help="Output directory for worker prd files")
    args = parser.parse_args()

    if args.workers < 2:
        print("[partition] ERROR: --workers must be >= 2", file=sys.stderr)
        return 1

    if not os.path.isfile(args.prd):
        print(f"[partition] ERROR: {args.prd} not found", file=sys.stderr)
        return 1

    with open(args.prd, encoding="utf-8") as f:
        prd = json.load(f)

    stories = prd.get("userStories", [])
    completed = [s for s in stories if s.get("passes")]
    pending = [s for s in stories if not s.get("passes")]

    print(f"[partition] {len(completed)} completed, {len(pending)} pending → {args.workers} workers")

    if not pending:
        print("[partition] No pending stories — nothing to partition")
        return 0

    buckets = assign_stories(pending, args.workers)

    os.makedirs(args.outdir, exist_ok=True)

    for i, bucket in enumerate(buckets):
        worker_num = i + 1
        worker_prd = dict(prd)
        # All completed stories (for dependency resolution) + this worker's pending stories
        worker_prd["userStories"] = completed + bucket
        out_path = os.path.join(args.outdir, f"worker_{worker_num}.json")
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(worker_prd, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, out_path)
        story_ids = [s["id"] for s in bucket]
        id_list = ", ".join(story_ids[:5]) + ("..." if len(story_ids) > 5 else "")
        priority_counts: dict[str, int] = {}
        for s in bucket:
            p = s.get("priority", "medium")
            priority_counts[p] = priority_counts.get(p, 0) + 1
        pcount_str = " ".join(
            f"{p}:{c}"
            for p, c in sorted(
                priority_counts.items(), key=lambda kv: PRIORITY_RANK.get(kv[0], 2)
            )
        )
        print(
            f"[partition] Worker {worker_num}: {len(bucket)} stories "
            f"[{id_list}] ({pcount_str}) → {out_path}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
