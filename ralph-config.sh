#!/bin/bash
# ralph-config.sh — Frappe/Docker quality gates for lhdn_payroll_integration
# Sourced by ralph.sh before the main loop

# ── 15-minute progress reporter ────────────────────────────────────────────
_ralph_report_progress() {
  local prd="${1:-prd.json}"
  while true; do
    sleep 900  # 15 minutes
    echo ""
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║   📊 15-MIN PROGRESS REPORT — $(date '+%H:%M')  ║"
    echo "  ╠══════════════════════════════════════════╣"
    local done total remaining
    done=$(jq '[.userStories[] | select(.passes == true)] | length' "$prd" 2>/dev/null || echo 0)
    total=$(jq '.userStories | length' "$prd" 2>/dev/null || echo 43)
    remaining=$((total - done))
    echo "  ║  Completed:  $done / $total stories"
    echo "  ║  Remaining:  $remaining stories"
    echo "  ║"
    # Last 3 completed stories
    echo "  ║  Recently done:"
    jq -r '.userStories[] | select(.passes == true) | "  ║    ✓ [\(.id)] \(.title)"' "$prd" 2>/dev/null | tail -3
    echo "  ║"
    # Next 3 pending stories
    echo "  ║  Up next:"
    jq -r '[.userStories[] | select(.passes == false)] | sort_by(.priority) | .[0:3][] | "  ║    → [\(.id)] \(.title)"' "$prd" 2>/dev/null
    echo "  ╚══════════════════════════════════════════╝"
    echo ""
  done
}

# Start reporter in background; clean up on exit
_ralph_report_progress "prd.json" &
_RALPH_REPORTER_PID=$!
trap 'kill $_RALPH_REPORTER_PID 2>/dev/null || true' EXIT

# ── Frappe quality gate (overrides default TypeScript gates) ────────────────
run_project_quality_checks() {
  # $NEXT_STORY is set by ralph.sh main loop — available in this scope
  local pre_ts_errors="${1:-0}"  # unused for Frappe; kept for signature compat
  local checks_passed=true

  echo "  ┌─ Quality Gates (Frappe/Docker) ────────────┐"

  # Gate 1: Docker container running
  echo -n "  │ [1/2] Docker container running... "
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'prisma-erp-backend-1'; then
    echo "✓ RUNNING"
  else
    echo "✗ FAIL — prisma-erp-backend-1 not found"
    echo "  └────────────────────────────────────────────┘"
    return 1
  fi

  # Gate 2: bench run-tests — module extracted from prd.json
  echo -n "  │ [2/2] bench run-tests... "

  # Extract story type from prd.json
  local story_type bench_module
  story_type=$(jq -r ".userStories[] | select(.id == \"$NEXT_STORY\") | .type" prd.json 2>/dev/null | tr -d '\r')

  # Extract first lhdn_payroll_integration.tests.test_XXX module from acceptance criteria
  bench_module=$(jq -r ".userStories[] | select(.id == \"$NEXT_STORY\") | .acceptanceCriteria[]" prd.json 2>/dev/null \
    | grep -oP 'lhdn_payroll_integration\.tests\.test_\w+' | head -1 | tr -d '\r')

  if [[ -z "$bench_module" ]]; then
    echo "SKIP (no bench module in acceptance criteria)"
    echo "  └────────────────────────────────────────────┘"
    echo "  ✓ Quality gates passed (bench check skipped)"
    return 0
  fi

  echo ""
  echo "  │     Module: $bench_module"
  echo "  │     Type:   $story_type"

  # Run bench and capture exit code
  local bench_exit=0
  docker exec prisma-erp-backend-1 bash -c \
    "cd /home/frappe/frappe-bench && bench --site frontend run-tests --module $bench_module" \
    > /tmp/ralph-bench-output.txt 2>&1 || bench_exit=$?

  if [[ "$story_type" == "TEST" ]]; then
    # UT stories: bench must FAIL (red phase)
    if [[ "$bench_exit" -ne 0 ]]; then
      echo "  │     Result: ✓ FAIL (red phase confirmed — expected for UT)"
    else
      echo "  │     Result: ✗ UNEXPECTEDLY PASSED — red phase not confirmed"
      echo "  │     (Implementation may have leaked in — check files)"
      tail -10 /tmp/ralph-bench-output.txt | sed 's/^/  │     /'
      checks_passed=false
    fi
  else
    # US/INTG stories: bench must PASS (green phase)
    if [[ "$bench_exit" -eq 0 ]]; then
      echo "  │     Result: ✓ PASS (green phase confirmed)"
    else
      echo "  │     Result: ✗ FAIL — tests did not pass"
      tail -20 /tmp/ralph-bench-output.txt | sed 's/^/  │     /'
      checks_passed=false
    fi
  fi

  echo "  └────────────────────────────────────────────┘"

  if [[ "$checks_passed" == "true" ]]; then
    echo "  ✓ All quality gates passed!"
    return 0
  else
    echo "  ✗ Quality gate FAILED"
    return 1
  fi
}

# ── Baseline capture (no TypeScript in Frappe project) ─────────────────────
capture_ts_baseline() {
  echo "0"  # No TypeScript — always return 0 baseline
}

echo "  [config] Frappe/Docker quality gates loaded (15-min reporter started, PID=$_RALPH_REPORTER_PID)"
