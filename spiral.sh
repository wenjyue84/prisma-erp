#!/bin/bash
# SPIRAL — Self-iterating Payroll Research and Implementation Autonomous Loop
#
# Usage:
#   bash spiral.sh [max_spiral_iterations] [--gate proceed|skip|quit] [--ralph-iters N]
#
# Phases per iteration:
#   R) RESEARCH    — Claude agent searches LHDN sources → _research_output.json
#   T) TEST SYNTH  — synthesize_tests.py → _test_stories_output.json
#   M) MERGE       — merge_stories.py deduplicates + patches prd.json
#   G) GATE        — human checkpoint: proceed | skip | quit
#   I) IMPLEMENT   — ralph.sh (up to 120 inner iterations)
#   V) VALIDATE    — .venv-tests HTTP suite; fresh report for check_done
#   C) CHECK DONE  — exit 0 if complete, else loop
#
# Non-interactive (Claude Code / CI):
#   bash spiral.sh 1 --gate proceed     # auto-proceed at every gate
#   bash spiral.sh 1 --gate skip        # research+merge only, skip ralph
#   bash spiral.sh 3 --gate proceed --ralph-iters 60

set -euo pipefail

# ── Argument parsing ─────────────────────────────────────────────────────────
MAX_SPIRAL_ITERS=20
GATE_DEFAULT=""        # empty = interactive; "proceed"|"skip"|"quit" = auto
RALPH_MAX_ITERS=120

while [[ $# -gt 0 ]]; do
  case $1 in
    --gate)
      GATE_DEFAULT="$2"; shift 2 ;;
    --ralph-iters)
      RALPH_MAX_ITERS="$2"; shift 2 ;;
    --*)
      echo "[spiral] Unknown flag: $1"; exit 1 ;;
    *)
      MAX_SPIRAL_ITERS="$1"; shift ;;
  esac
done

# ── Configuration ─────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RALPH_SKILL="$HOME/.ai/Skills/ralph/ralph.sh"
STREAM_FMT="$HOME/.ai/Skills/ralph/stream-formatter.mjs"
PYTHON="$REPO_ROOT/.venv-tests/Scripts/python.exe"
SPIRAL_DIR="$REPO_ROOT/scripts/spiral"
PRD_FILE="$REPO_ROOT/prd.json"

# ── jq resolution (reuse ralph.sh pattern) ───────────────────────────────────
RALPH_JQ_DIR="$HOME/.ai/Skills/ralph"
if command -v jq &>/dev/null; then
  JQ="jq"
elif [[ -f "$RALPH_JQ_DIR/jq.exe" ]]; then
  JQ="$RALPH_JQ_DIR/jq.exe"
elif [[ -f "$REPO_ROOT/scripts/ralph/jq.exe" ]]; then
  JQ="$REPO_ROOT/scripts/ralph/jq.exe"
else
  echo "[spiral] ERROR: jq not found. Install with: choco install jq"
  exit 1
fi

# ── Prerequisite checks ───────────────────────────────────────────────────────
if [[ ! -f "$PRD_FILE" ]]; then
  echo "[spiral] ERROR: prd.json not found at $PRD_FILE"
  exit 1
fi
if [[ ! -f "$RALPH_SKILL" ]]; then
  echo "[spiral] ERROR: ralph.sh not found at $RALPH_SKILL"
  exit 1
fi
if [[ ! -f "$PYTHON" ]]; then
  echo "[spiral] WARNING: Python venv not found at $PYTHON — falling back to system python3"
  PYTHON="python3"
fi

# ── Helper: stats from prd.json ───────────────────────────────────────────────
prd_stats() {
  TOTAL=$("$JQ" '[.userStories | length] | .[0]' "$PRD_FILE")
  DONE=$("$JQ" '[.userStories[] | select(.passes == true)] | length' "$PRD_FILE")
  PENDING=$((TOTAL - DONE))
}

# ── Helper: inject placeholders into research prompt ─────────────────────────
build_research_prompt() {
  local iter="$1"
  local output_path="$2"

  local next_id_num
  next_id_num=$("$JQ" '[.userStories[].id | ltrimstr("US-") | tonumber] | max + 1' "$PRD_FILE")

  local existing_titles
  existing_titles=$("$JQ" -r '[.userStories[].title] | join("\n- ")' "$PRD_FILE")

  # Build injected prompt via sed substitutions
  local prompt_content
  prompt_content=$(cat "$SPIRAL_DIR/research_prompt.md")
  prompt_content="${prompt_content//__SPIRAL_ITER__/$iter}"
  prompt_content="${prompt_content//__NEXT_ID_NUM__/$next_id_num}"
  prompt_content="${prompt_content//__OUTPUT_PATH__/$output_path}"
  # Replace __EXISTING_TITLES__ placeholder
  # Use printf to avoid issues with special chars in titles
  printf '%s' "$prompt_content" | \
    awk -v titles="$existing_titles" '{gsub(/__EXISTING_TITLES__/, titles); print}'
}

# ── SPIRAL banner ─────────────────────────────────────────────────────────────
prd_stats
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   SPIRAL — Self-iterating Payroll Loop       ║"
echo "  ╠══════════════════════════════════════════════╣"
echo "  ║  PRD:         $PRD_FILE"
echo "  ║  Stories:     $DONE/$TOTAL complete ($PENDING pending)"
echo "  ║  Max iters:   $MAX_SPIRAL_ITERS"
echo "  ║  Ralph iters: $RALPH_MAX_ITERS per phase"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

# ── Main SPIRAL loop ──────────────────────────────────────────────────────────
SPIRAL_ITER=0

while [[ $SPIRAL_ITER -lt $MAX_SPIRAL_ITERS ]]; do
  SPIRAL_ITER=$((SPIRAL_ITER + 1))

  prd_stats
  echo ""
  echo "  ┌─────────────────────────────────────────────────────┐"
  echo "  │  SPIRAL Iteration $SPIRAL_ITER / $MAX_SPIRAL_ITERS"
  echo "  │  Stories: $DONE/$TOTAL complete ($PENDING pending)"
  echo "  └─────────────────────────────────────────────────────┘"

  # ── Phase R: RESEARCH ────────────────────────────────────────────────────
  echo ""
  echo "  [Phase R] RESEARCH — searching LHDN sources..."
  RESEARCH_OUTPUT="$SPIRAL_DIR/_research_output.json"

  INJECTED_PROMPT=$(build_research_prompt "$SPIRAL_ITER" "$RESEARCH_OUTPUT")
  echo "  [R] Spawning Claude research agent (max 30 turns)..."
  echo "  ─────── Research Agent Start ─────────────────────────"

  if command -v node &>/dev/null && [[ -f "$STREAM_FMT" ]]; then
    (unset CLAUDECODE; claude -p "$INJECTED_PROMPT" \
      --allowedTools "WebSearch,WebFetch,Write,Read" \
      --max-turns 30 \
      --verbose \
      --output-format stream-json \
      --dangerously-skip-permissions \
      </dev/null 2>&1 | node "$STREAM_FMT") || true
  else
    (unset CLAUDECODE; claude -p "$INJECTED_PROMPT" \
      --allowedTools "WebSearch,WebFetch,Write,Read" \
      --max-turns 30 \
      --dangerously-skip-permissions \
      </dev/null 2>&1) || true
  fi

  echo "  ─────── Research Agent End ───────────────────────────"

  if [[ ! -f "$RESEARCH_OUTPUT" ]]; then
    echo "  [R] WARNING: Research agent did not write $RESEARCH_OUTPUT — using empty"
    echo '{"stories":[]}' > "$RESEARCH_OUTPUT"
  else
    RESEARCH_COUNT=$("$JQ" '.stories | length' "$RESEARCH_OUTPUT" 2>/dev/null || echo "?")
    echo "  [R] Research complete — $RESEARCH_COUNT story candidates found"
  fi

  # ── Phase T: TEST SYNTHESIS ───────────────────────────────────────────────
  echo ""
  echo "  [Phase T] TEST SYNTHESIS — scanning test failures..."
  TEST_OUTPUT="$SPIRAL_DIR/_test_stories_output.json"

  "$PYTHON" "$SPIRAL_DIR/synthesize_tests.py" \
    --prd "$PRD_FILE" \
    --reports-dir "$REPO_ROOT/test-reports" \
    --output "$TEST_OUTPUT" || true

  TEST_COUNT=$("$JQ" '.stories | length' "$TEST_OUTPUT" 2>/dev/null || echo "0")
  echo "  [T] Test synthesis complete — $TEST_COUNT story candidates from failures"

  # ── Phase M: MERGE ────────────────────────────────────────────────────────
  echo ""
  echo "  [Phase M] MERGE — deduplicating and patching prd.json..."

  BEFORE_TOTAL=$("$JQ" '[.userStories | length] | .[0]' "$PRD_FILE")
  "$PYTHON" "$SPIRAL_DIR/merge_stories.py" \
    --prd "$PRD_FILE" \
    --research "$RESEARCH_OUTPUT" \
    --test-stories "$TEST_OUTPUT" \
    --max-new 50 || true
  AFTER_TOTAL=$("$JQ" '[.userStories | length] | .[0]' "$PRD_FILE")
  ADDED=$((AFTER_TOTAL - BEFORE_TOTAL))
  echo "  [M] Merge complete — $ADDED new stories added (total: $AFTER_TOTAL)"

  # ── Phase G: HUMAN GATE ───────────────────────────────────────────────────
  prd_stats
  echo ""
  echo "  ╔══════════════════════════════════════════════════════╗"
  echo "  ║  [Phase G] HUMAN GATE — Iteration $SPIRAL_ITER"
  echo "  ╠══════════════════════════════════════════════════════╣"
  echo "  ║  New stories added:  $ADDED"
  echo "  ║  Total pending:      $PENDING"
  echo "  ║  Total stories:      $TOTAL ($DONE complete)"
  echo "  ╠══════════════════════════════════════════════════════╣"
  echo "  ║  Options:"
  echo "  ║    proceed — run ralph to implement pending stories"
  echo "  ║    skip    — skip ralph, advance to check-done"
  echo "  ║    quit    — halt SPIRAL"
  echo "  ╚══════════════════════════════════════════════════════╝"
  echo ""
  if [[ -n "$GATE_DEFAULT" ]]; then
    GATE_INPUT="$GATE_DEFAULT"
    echo "  [G] Auto-gate: $GATE_INPUT"
  else
    printf "  Enter choice: "
    # Read from /dev/tty if available (handles piped stdin), else fall back to normal stdin
    if [[ -t 0 ]]; then
      read -r GATE_INPUT || GATE_INPUT="quit"
    else
      read -r GATE_INPUT </dev/tty 2>/dev/null || read -r GATE_INPUT || GATE_INPUT="quit"
    fi
  fi

  GATE_INPUT=$(echo "$GATE_INPUT" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')

  case "$GATE_INPUT" in
    quit|q|exit)
      echo "  [G] User quit — SPIRAL halted at iteration $SPIRAL_ITER"
      exit 0
      ;;
    skip|s)
      echo "  [G] Skipping ralph — advancing to check-done"
      ;;
    proceed|p|"")
      # ── Phase I: IMPLEMENT (Ralph) ──────────────────────────────────────
      echo ""
      echo "  [Phase I] IMPLEMENT — running ralph ($RALPH_MAX_ITERS inner iterations)..."

      DONE_BEFORE=$("$JQ" '[.userStories[] | select(.passes == true)] | length' "$PRD_FILE")

      bash "$RALPH_SKILL" "$RALPH_MAX_ITERS" || true

      DONE_AFTER=$("$JQ" '[.userStories[] | select(.passes == true)] | length' "$PRD_FILE")
      RALPH_PROGRESS=$((DONE_AFTER - DONE_BEFORE))

      if [[ "$RALPH_PROGRESS" -eq 0 ]]; then
        echo ""
        echo "  [I] WARNING: Ralph made zero progress this iteration."
        echo "  [I] This may indicate all remaining stories are blocked or max-retried."
        echo "  [I] Continuing to check-done phase..."
      else
        echo "  [I] Ralph completed $RALPH_PROGRESS new stories"
      fi
      ;;
    *)
      echo "  [G] Unrecognized input '$GATE_INPUT' — treating as skip"
      ;;
  esac

  # ── Phase V: VALIDATE (HTTP test suite) ──────────────────────────────────
  echo ""
  echo "  [Phase V] VALIDATE — running .venv-tests HTTP suite..."

  if [[ -f "$PYTHON" ]]; then
    (cd "$REPO_ROOT" && "$PYTHON" tests/run_tests.py \
      --report-dir "test-reports" 2>&1) || true

    # Print summary from the freshest report
    "$PYTHON" - <<'PYEOF'
import os, json, sys
d = 'test-reports'
if not os.path.isdir(d):
    print("  [V] No test-reports directory found")
    sys.exit(0)
subdirs = sorted([x for x in os.listdir(d) if os.path.isdir(os.path.join(d,x))], reverse=True)
for s in subdirs:
    p = os.path.join(d, s, 'report.json')
    if os.path.isfile(p):
        r = json.load(open(p, encoding='utf-8'))
        sm = r.get('summary', {})
        print(f"  [V] {s}: {sm.get('passed',0)}/{sm.get('total',0)} pass, {sm.get('failed',0)} failed, {sm.get('errored',0)} errored")
        sys.exit(0)
print("  [V] No report found")
PYEOF
  else
    echo "  [V] WARNING: Python venv not found — skipping HTTP test suite"
  fi

  # ── Phase C: CHECK DONE ───────────────────────────────────────────────────
  echo ""
  echo "  [Phase C] CHECK DONE..."

  if "$PYTHON" "$SPIRAL_DIR/check_done.py" \
    --prd "$PRD_FILE" \
    --reports-dir "$REPO_ROOT/test-reports"; then
    echo ""
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║   *** SPIRAL COMPLETE! ***                           ║"
    echo "  ║   All stories implemented and tests passing.         ║"
    echo "  ║   Iterations: $SPIRAL_ITER / $MAX_SPIRAL_ITERS"
    echo "  ╚══════════════════════════════════════════════════════╝"
    exit 0
  fi

  echo "  [C] Not done yet — looping back to Phase R"
  echo ""
done

# ── Max iterations reached ────────────────────────────────────────────────────
prd_stats
echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║  SPIRAL reached max iterations ($MAX_SPIRAL_ITERS)           ║"
echo "  ║  Stories: $DONE/$TOTAL complete ($PENDING pending)   ║"
echo "  ║  Run again to continue: bash spiral.sh 20            ║"
echo "  ╚══════════════════════════════════════════════════════╝"
exit 0
