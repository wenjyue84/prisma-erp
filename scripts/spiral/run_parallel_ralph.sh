#!/bin/bash
# run_parallel_ralph.sh — Orchestrate N parallel Ralph workers via git worktrees
#
# Each worker:
#   - Runs in its own git worktree (isolated source files + git history)
#   - Uses its own prd.json slice (subset of pending stories)
#   - Routes docker cp/bench calls through a mkdir lock wrapper (shared container safety)
#
# After all workers finish:
#   - prd.json pass results are merged back into main
#   - Code diffs are applied via git patch (lhdn_payroll_integration/ only)
#   - Merged code is deployed to the container
#   - Worktrees and branches are cleaned up
#
# Usage: bash run_parallel_ralph.sh WORKERS MAX_ITERS REPO_ROOT PRD_FILE SPIRAL_DIR RALPH_SKILL JQ PYTHON

set -euo pipefail

RALPH_WORKERS="$1"
RALPH_MAX_ITERS="$2"
REPO_ROOT="$3"
PRD_FILE="$4"
SPIRAL_DIR="$5"
RALPH_SKILL="$6"
JQ="$7"
PYTHON="$8"

WORKER_DIR="$SPIRAL_DIR/workers"
WORKTREE_BASE="$REPO_ROOT/.spiral-workers"
# Unique lock dir per invocation (using PID avoids collisions if SPIRAL is re-run)
LOCK_DIR="/tmp/spiral-docker-lock-$$"
TIMESTAMP=$(date +%s)
ITER_PER_WORKER=$(( (RALPH_MAX_ITERS + RALPH_WORKERS - 1) / RALPH_WORKERS ))

REAL_DOCKER="$(command -v docker 2>/dev/null || echo docker)"

echo "  [parallel] ═══════════════════════════════════════════════════"
echo "  [parallel]  PARALLEL RALPH — $RALPH_WORKERS workers"
echo "  [parallel]  Iters/worker:  $ITER_PER_WORKER (total budget: $RALPH_MAX_ITERS)"
echo "  [parallel]  Docker lock:   $LOCK_DIR"
echo "  [parallel] ═══════════════════════════════════════════════════"

# ── Step 1: Partition pending stories into worker prd files ───────────────────
mkdir -p "$WORKER_DIR"
"$PYTHON" "$SPIRAL_DIR/partition_prd.py" \
  --prd "$PRD_FILE" \
  --workers "$RALPH_WORKERS" \
  --outdir "$WORKER_DIR"

# ── Step 2: Create git worktrees + docker lock wrapper per worker ─────────────
declare -a WORKER_DIRS=()
declare -a WORKER_BRANCHES=()

for i in $(seq 1 "$RALPH_WORKERS"); do
  BRANCH="spiral-worker-${i}-${TIMESTAMP}"
  WTREE="$WORKTREE_BASE/worker-${i}"

  # Remove stale worktree if it exists
  git -C "$REPO_ROOT" worktree remove "$WTREE" --force 2>/dev/null || rm -rf "$WTREE" 2>/dev/null || true
  git -C "$REPO_ROOT" worktree add "$WTREE" -b "$BRANCH" HEAD

  # Overlay worker prd.json + override branchName to match the worker's own branch
  # (prevents ralph from trying to git checkout a different branch inside the worktree,
  # which would fail because prd.json/progress.txt/retry-counts.json are already modified)
  cp "$WORKER_DIR/worker_${i}.json" "$WTREE/prd.json"
  "$JQ" --arg b "$BRANCH" '.branchName = $b' "$WTREE/prd.json" > "$WTREE/prd.json.tmp" && mv "$WTREE/prd.json.tmp" "$WTREE/prd.json"

  # Fresh per-worker state files (avoid cross-worker contamination)
  echo "{}" > "$WTREE/retry-counts.json"
  echo "## Worker $i progress" > "$WTREE/progress.txt"

  # ── Docker lock wrapper ─────────────────────────────────────────────────
  # Serializes: docker cp  AND  docker exec ... bench (migrate/run-tests)
  # All other docker commands pass through immediately.
  mkdir -p "$WTREE/.spiral-bin"
  WRAPPER="$WTREE/.spiral-bin/docker"
  cat > "$WRAPPER" << WRAPPER_SCRIPT
#!/bin/bash
# Parallel Ralph docker lock wrapper — serializes container deploy+test ops
REAL="$REAL_DOCKER"
LOCK="$LOCK_DIR"
NEEDS_LOCK=0
[[ "\$1" == "cp" ]] && NEEDS_LOCK=1
# Lock only write-mutating bench operations; read-only calls (run-tests, clear-cache) pass through
[[ "\$*" == *"bench migrate"* ]] && NEEDS_LOCK=1
[[ "\$*" == *"bench sync_fixtures"* ]] && NEEDS_LOCK=1
[[ "\$*" == *"bench install-app"* ]] && NEEDS_LOCK=1
if [[ "\$NEEDS_LOCK" -eq 1 ]]; then
  # Spin-wait using mkdir atomicity (works on all POSIX + MSYS2 / Git Bash)
  while ! mkdir "\$LOCK" 2>/dev/null; do sleep 1; done
  "\$REAL" "\$@"
  RC=\$?
  rmdir "\$LOCK" 2>/dev/null || true
  exit \$RC
else
  exec "\$REAL" "\$@"
fi
WRAPPER_SCRIPT
  chmod +x "$WRAPPER"

  # Patch ralph-config.sh: use per-worker bench output file to avoid cross-worker race.
  # The docker lock serializes docker exec bench calls, but /tmp/ralph-bench-output.txt
  # is read AFTER the lock is released — another worker can overwrite it in the gap.
  WORKER_BENCH_OUT="/tmp/ralph-bench-output-worker-${i}.txt"
  sed -i "s|/tmp/ralph-bench-output\.txt|${WORKER_BENCH_OUT}|g" "$WTREE/ralph-config.sh" 2>/dev/null || true

  STORY_COUNT=$("$JQ" '[.userStories[] | select(.passes != true)] | length' "$WTREE/prd.json" 2>/dev/null || echo "?")
  echo "  [parallel] Worker $i ready — branch: $BRANCH | pending: $STORY_COUNT stories"

  WORKER_DIRS+=("$WTREE")
  WORKER_BRANCHES+=("$BRANCH")
done

# ── Step 3: Launch all workers in background ──────────────────────────────────
declare -a WORKER_PIDS=()

for i in $(seq 1 "$RALPH_WORKERS"); do
  WTREE="${WORKER_DIRS[$((i-1))]}"
  LOG="$WORKER_DIR/worker_${i}.log"

  echo "  [parallel] Launching worker $i → log: $LOG"
  (
    cd "$WTREE"
    # Put lock wrapper first in PATH so docker calls are intercepted
    export PATH="$WTREE/.spiral-bin:$PATH"
    bash "$RALPH_SKILL" "$ITER_PER_WORKER" --prd prd.json \
      > "$LOG" 2>&1
  ) &
  WORKER_PIDS+=($!)
done

echo ""
TAIL_LOGS=$(seq 1 "$RALPH_WORKERS" | while read -r n; do printf "%s " "$WORKER_DIR/worker_${n}.log"; done)
echo "  [parallel] All $RALPH_WORKERS workers running."
echo "  [parallel] Monitor single:  tail -f $WORKER_DIR/worker_1.log"
echo "  [parallel] Monitor all:     tail -f $TAIL_LOGS"
echo "  [parallel] Waiting for completion..."
echo ""

# ── Step 4: Wait for all workers ──────────────────────────────────────────────
for i in "${!WORKER_PIDS[@]}"; do
  PID="${WORKER_PIDS[$i]}"
  WORKER_NUM=$((i + 1))
  wait "$PID" || true  # ralph exits non-zero when no stories remain — expected

  WTREE="${WORKER_DIRS[$i]}"
  DONE_W=$("$JQ" '[.userStories[] | select(.passes == true)] | length' "$WTREE/prd.json" 2>/dev/null || echo "?")
  TOTAL_W=$("$JQ" '[.userStories | length] | .[0]' "$WTREE/prd.json" 2>/dev/null || echo "?")
  echo "  [parallel] Worker $WORKER_NUM finished: $DONE_W/$TOTAL_W stories passed"
done

# ── Step 5: Print last 5 lines of each worker log ─────────────────────────────
echo ""
for i in $(seq 1 "$RALPH_WORKERS"); do
  echo "  ─── Worker $i (last 5 lines) ────────────────────────────────────"
  tail -5 "$WORKER_DIR/worker_${i}.log" 2>/dev/null | sed 's/^/  │ /' || true
done
echo ""

# ── Step 6: Merge prd.json pass results into main prd.json ───────────────────
WORKER_PRDS=()
for wtree in "${WORKER_DIRS[@]}"; do
  WORKER_PRDS+=("$wtree/prd.json")
done

"$PYTHON" "$SPIRAL_DIR/merge_worker_results.py" \
  --main "$PRD_FILE" \
  --workers "${WORKER_PRDS[@]}"

# Commit the merged prd.json as a stable base before code patches
git -C "$REPO_ROOT" add "$PRD_FILE" 2>/dev/null
git -C "$REPO_ROOT" commit -m "chore(spiral): merge prd.json from $RALPH_WORKERS parallel workers" \
  2>/dev/null || true

# ── Step 7: Apply code changes from each worker as a patch ───────────────────
# We diff only lhdn_payroll_integration/ (app code), excluding:
#   - prd.json (already merged above)
#   - progress.txt / retry-counts.json (per-worker transient files)
#   - .spiral-bin/ (lock wrapper, not real code)
PATCHES_APPLIED=0
PATCHES_CONFLICTED=0

for i in $(seq 1 "$RALPH_WORKERS"); do
  BRANCH="${WORKER_BRANCHES[$((i-1))]}"
  PATCH_FILE="$WORKER_DIR/worker_${i}.patch"

  echo "  [parallel] Extracting code diff for worker $i (branch: $BRANCH)..."
  # Scope to app code only
  git -C "$REPO_ROOT" diff "HEAD..$BRANCH" -- \
    "lhdn_payroll_integration/" \
    "prisma_assistant/" \
    "tests/" \
    > "$PATCH_FILE" 2>/dev/null || true

  if [[ ! -s "$PATCH_FILE" ]]; then
    echo "  [parallel] Worker $i: no code changes to apply"
    continue
  fi

  LINES=$(wc -l < "$PATCH_FILE")
  echo "  [parallel] Worker $i: applying $LINES-line patch..."

  if git -C "$REPO_ROOT" apply --3way "$PATCH_FILE" 2>/dev/null; then
    git -C "$REPO_ROOT" add -A 2>/dev/null
    git -C "$REPO_ROOT" commit \
      -m "feat(spiral): worker $i parallel implementation" \
      2>/dev/null || true
    PATCHES_APPLIED=$((PATCHES_APPLIED + 1))
    echo "  [parallel] Worker $i code applied cleanly"
  else
    # 3-way failed — apply with --reject to get partial apply + .rej files
    echo "  [parallel] WARNING: Worker $i patch had conflicts — applying with --reject"
    git -C "$REPO_ROOT" apply --reject "$PATCH_FILE" 2>/dev/null || true
    git -C "$REPO_ROOT" add -A 2>/dev/null
    git -C "$REPO_ROOT" commit \
      -m "feat(spiral): worker $i code (partial — .rej files need review)" \
      2>/dev/null || true
    PATCHES_CONFLICTED=$((PATCHES_CONFLICTED + 1))
    echo "  [parallel] Worker $i: partial apply done; review *.rej files for conflicts"
  fi
done

echo "  [parallel] Code patches: $PATCHES_APPLIED clean, $PATCHES_CONFLICTED with conflicts"

# ── Step 8: Deploy final merged code to container ─────────────────────────────
echo "  [parallel] Deploying merged code to container..."
if "$REAL_DOCKER" cp \
  "$REPO_ROOT/lhdn_payroll_integration/." \
  "prisma-erp-backend-1:/home/frappe/frappe-bench/apps/lhdn_payroll_integration/" \
  2>/dev/null; then
  "$REAL_DOCKER" exec prisma-erp-backend-1 bash -c \
    "cd /home/frappe/frappe-bench && bench --site frontend clear-cache" 2>/dev/null || true
  echo "  [parallel] Container updated with merged code"
else
  echo "  [parallel] WARNING: docker cp failed — container may be down; code in repo is correct"
fi

# ── Step 9: Cleanup worktrees, branches, and lock ────────────────────────────
rm -rf "$LOCK_DIR" 2>/dev/null || true

for i in $(seq 1 "$RALPH_WORKERS"); do
  BRANCH="${WORKER_BRANCHES[$((i-1))]}"
  WTREE="${WORKER_DIRS[$((i-1))]}"
  git -C "$REPO_ROOT" worktree remove "$WTREE" --force 2>/dev/null || true
  git -C "$REPO_ROOT" branch -D "$BRANCH" 2>/dev/null || true
done
rm -rf "$WORKTREE_BASE" 2>/dev/null || true

echo "  [parallel] Cleanup complete."
echo "  [parallel] ═══════════════════════════════════════════════════"
