#!/usr/bin/env python3
"""
SPIRAL Parallel Phase — Partition PRD
Splits pending stories into N worker prd.json files using round-robin assignment.
Completed stories are included in every worker file (ralph needs them for dep checks).
"""
import argparse
import json
import os
import sys


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

    # Round-robin assignment preserves priority ordering within each bucket
    buckets: list[list] = [[] for _ in range(args.workers)]
    for i, story in enumerate(pending):
        buckets[i % args.workers].append(story)

    os.makedirs(args.outdir, exist_ok=True)

    for i, bucket in enumerate(buckets):
        worker_num = i + 1
        worker_prd = dict(prd)
        # All completed stories (deps) + this worker's pending stories
        worker_prd["userStories"] = completed + bucket
        out_path = os.path.join(args.outdir, f"worker_{worker_num}.json")
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(worker_prd, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, out_path)
        story_ids = [s["id"] for s in bucket]
        id_list = ", ".join(story_ids[:5]) + ("..." if len(story_ids) > 5 else "")
        print(f"[partition] Worker {worker_num}: {len(bucket)} stories [{id_list}] → {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
