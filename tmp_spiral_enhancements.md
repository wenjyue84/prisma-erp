# SPIRAL Efficiency Enhancements — Implementation Plan
Generated: 2026-03-01

## Files Modified
| File | Enhancements |
|------|-------------|
| `scripts/spiral/partition_prd.py` | #1 Priority-aware, #2 Dependency-aware partitioning |
| `scripts/spiral/synthesize_tests.py` | #4 Aggregate last N reports, #8 Enrich with test source |
| `scripts/spiral/merge_stories.py` | #5 Research overflow carry-over, #7 isTestFix flag |
| `scripts/spiral/run_parallel_ralph.sh` | #3 Unlock read-only bench, #10 Live multi-worker tail |
| `spiral.sh` | #5 Overflow args, #6 Adaptive ralph-iters, #9 Configurable capacity |

---

## Enhancement Details

### #1 — Priority-aware partitioning (`partition_prd.py`)
**Problem:** Round-robin interleaves critical/high/low stories randomly across workers.
**Fix:** Sort all pending stories by priority (critical→high→medium→low) before assignment.
**Impact:** Worker 1 always finishes critical stories first even if other workers stall.

### #2 — Dependency-aware partitioning (`partition_prd.py`)
**Problem:** US-050 (depends on US-049) could land on a different worker; US-050 wastes
iterations retrying until its dep is met.
**Fix:** Walk each story's `dependencies` list; if a pending dep is already assigned to
a worker, assign this story to the same worker.
**Impact:** Eliminates cross-worker dep stalls; fewer wasted ralph iterations.

### #3 — Unlock read-only bench from docker lock (`run_parallel_ralph.sh`)
**Problem:** ALL bench calls are serialized — including `bench run-tests` (read-only).
Workers stall waiting for the lock even while just reading test results.
**Fix:** Only lock `docker cp`, `bench migrate`, `bench sync_fixtures`, `bench install-app`.
`bench run-tests`, `bench clear-cache` pass through immediately.
**Impact:** Workers can run tests in parallel → significant wall-clock speedup.

### #4 — Aggregate last N test reports (`synthesize_tests.py`)
**Problem:** Only the single latest report is read. A test that failed 2 iterations ago
but wasn't in the latest report (different suite run) is silently missed.
**Fix:** `find_recent_reports(dir, n=3)` reads last N reports, unions by test ID.
**Impact:** More complete repair-story generation; fewer regressions slip through.

### #5 — Research overflow carry-over (`merge_stories.py` + `spiral.sh`)
**Problem:** When Phase M hits the 50-story cap, leftover research candidates are discarded.
Next iteration R is skipped (OVER_CAPACITY) → those candidates are permanently lost.
**Fix:** `merge_stories.py` accepts `--overflow-in` / `--overflow-out`. Unused non-duplicate
research candidates are written to `_research_overflow.json` and injected next iteration.
Overflow candidates are prioritized before fresh R output (older work first).
**Impact:** No research work is wasted; overflow drains naturally as capacity frees up.

### #6 — Adaptive ralph-iters (`spiral.sh`)
**Problem:** `RALPH_MAX_ITERS` is static regardless of velocity.
High-velocity runs (8 stories/iter) under-utilize budget. Zero-velocity runs waste time.
**Fix:** After Phase I: if velocity ≥ 5 stories → add 20 iters; if velocity = 0 → halve
budget (floor 30).
**Impact:** Budget scales with actual throughput; less wasted iteration on stalls.

### #7 — `isTestFix` flag (`merge_stories.py`)
**Problem:** ralph picks stories from prd.json without knowing which are regressions vs
new features. Both get same treatment.
**Fix:** Stories from Phase T get `"isTestFix": true` in their prd.json entry.
**Impact:** Adds audit trail; future ralph.sh versions or custom prompts can prioritize
these as known regressions.

### #8 — Enrich Phase T stories with test source (`synthesize_tests.py`)
**Problem:** Synthesized stories have metadata (test ID, error type) but not the actual
failing assertion. ralph spends turns hunting for the test file.
**Fix:** `extract_test_source(test_id, repo_root)` locates the `.py` file by progressively
trimming the dotted test_id path, then extracts the method body (up to 20 lines).
Appended to `technicalNotes` as a fenced code block.
**Impact:** ralph has the failing assertion inline → fewer turns to diagnose + fix.

### #9 — Configurable capacity threshold (`spiral.sh`)
**Problem:** `PENDING > 50` is hardcoded — can't tune without editing the script.
**Fix:** `CAPACITY_LIMIT=50` default + `--capacity-limit N` flag.
**Impact:** Allows tuning Phase R suppression without source edits.

### #10 — Live multi-worker tail command (`run_parallel_ralph.sh`)
**Problem:** Only shows how to tail worker 1. No easy way to watch all workers.
**Fix:** Print a `tail -f worker_1.log worker_2.log ...` command covering all N workers.
**Impact:** Faster diagnosis during parallel runs.

---

## Interface Contract (Enhancement #5)

`merge_stories.py` new flags:
```
--overflow-in PATH    Read additional research candidates from this file
--overflow-out PATH   Write unused (cap-blocked, non-duplicate) candidates here
```

`spiral.sh` invocation change (Phase M):
```bash
OVERFLOW_FILE="$SPIRAL_DIR/_research_overflow.json"
"$PYTHON" "$SPIRAL_DIR/merge_stories.py" \
  --prd "$PRD_FILE" \
  --research "$RESEARCH_OUTPUT" \
  --test-stories "$TEST_OUTPUT" \
  --overflow-in  "$OVERFLOW_FILE" \
  --overflow-out "$OVERFLOW_FILE" \
  --max-new 50 || true
```

`spiral.sh` invocation change (Phase T):
```bash
"$PYTHON" "$SPIRAL_DIR/synthesize_tests.py" \
  --prd "$PRD_FILE" \
  --reports-dir "$REPO_ROOT/test-reports" \
  --output "$TEST_OUTPUT" \
  --repo-root "$REPO_ROOT" || true
```
