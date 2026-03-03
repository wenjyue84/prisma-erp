#!/bin/bash
# spiral.config.sh — prisma-erp project-specific SPIRAL configuration

# Python interpreter (Windows venv)
SPIRAL_PYTHON="$PWD/.venv-tests/Scripts/python.exe"

# Ralph path (default points to bundled ralph in spiral repo — no override needed)
# SPIRAL_RALPH="$SPIRAL_HOME/ralph/ralph.sh"

# Domain-specific research prompt (LHDN/Malaysian payroll)
SPIRAL_RESEARCH_PROMPT="$PWD/scripts/spiral/research_prompt.md"

# Gemini web research (Phase R) — Malaysian payroll compliance
SPIRAL_GEMINI_PROMPT="Research the latest Malaysian LHDN payroll compliance requirements for 2025-2026. Focus on: PCB/MTD calculation rules and formula updates, EPF contribution rates by income bracket, SOCSO/EIS contribution thresholds, EA form (Borang EA) field requirements and updates, TP1/TP3 form rules for employee declarations, employer monthly submission deadlines. Return a structured markdown summary with specific figures, rates, and thresholds."

# Gemini filesTouch annotation (parallel mode)
SPIRAL_GEMINI_ANNOTATE_PROMPT='Which Python files in lhdn_payroll_integration/ would implement this story? Return a JSON array only, no explanation. Example: ["payroll/api.py","payroll/utils.py"]. Story: __STORY_TITLE__'

# Validation command
# Add --suite browser to include browser smoke tests (~25-30s overhead, requires agent-browser CLI).
# Browser tests skip gracefully if agent-browser is not installed.
SPIRAL_VALIDATE_CMD="$SPIRAL_PYTHON tests/run_tests.py --report-dir test-reports"
# SPIRAL_VALIDATE_CMD="$SPIRAL_PYTHON tests/run_tests.py --report-dir test-reports --suite browser"

# Test reports directory
SPIRAL_REPORTS_DIR="test-reports"

# Story ID prefix
SPIRAL_STORY_PREFIX="US"

# Patch directories for parallel mode (only diff these dirs)
SPIRAL_PATCH_DIRS="lhdn_payroll_integration/ prisma_assistant/ tests/"

# Deploy merged code to Docker container after parallel workers complete
SPIRAL_DEPLOY_CMD='docker cp ./lhdn_payroll_integration/. prisma-erp-backend-1:/home/frappe/frappe-bench/apps/lhdn_payroll_integration/ && docker exec prisma-erp-backend-1 bash -c "cd /home/frappe/frappe-bench && bench --site frontend clear-cache"'

# Terminal emulator for --monitor mode
SPIRAL_TERMINAL="/c/Users/Jyue/AppData/Local/Microsoft/WindowsApps/wt.exe"

# Hint directories for populate_hints.py
export SPIRAL_HINT_DIRS="lhdn_payroll_integration/,prisma_assistant/,tests/"

# Model routing: auto-classify per story (haiku/sonnet/opus by complexity)
SPIRAL_MODEL_ROUTING="auto"

# Research model: sonnet for Phase R (good reasoning for compliance research)
SPIRAL_RESEARCH_MODEL="sonnet"

# Specialist agents — pre-context injection before main agents
# Phase R: runs ONLY as Gemini fallback (when Gemini returns empty)
SPIRAL_RESEARCH_SPECIALIST_PROMPT="$PWD/scripts/spiral/specialists/malaysia-payroll-specialist.md"
# Phase I: always runs alongside Gemini (codebase search layer Gemini can't do)
SPIRAL_IMPLEMENT_SPECIALIST_PROMPT="$PWD/scripts/spiral/specialists/frappe-developer-specialist.md"
# Models: haiku for research fallback (static knowledge), sonnet for impl (codebase reasoning)
SPIRAL_RESEARCH_SPECIALIST_MODEL="haiku"
SPIRAL_IMPLEMENT_SPECIALIST_MODEL="sonnet"

# GitNexus knowledge graph — fills filesTouch for stories with no git history
# (US-200+ that were added after the baseline commit range)
SPIRAL_GITNEXUS_REPO="prisma-erp"
