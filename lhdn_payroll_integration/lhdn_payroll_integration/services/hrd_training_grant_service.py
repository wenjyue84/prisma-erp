"""
HRD Corp SBL-KHAS Grant Pre-Approval Compliance and 6-Month Post-Training
Claim Deadline Alert Service.

Business rules:
  - eTRiS application must be submitted at least 1 working day BEFORE training starts.
    If etris_application_date >= training_start_date → flagged non-claimable.
  - Claim must be submitted within 30 days (preferred) and no later than 6 months
    (absolute hard deadline — late claims cannot be appealed).
  - Alerts:
      day 20 and day 28 after training end → approaching 30-day preferred deadline
      5 months and 5.5 months after training end → critical, escalate to HR Director

Provides:
  check_pre_approval_compliance(training)   → dict with status and warning messages
  check_claim_deadline_compliance(training) → dict with status and alert messages
  get_hrd_dashboard_summary(trainings)      → categorised summary for dashboard
"""
import frappe
from frappe.utils import date_diff, add_months, add_days, today, getdate


# ---------------------------------------------------------------------------
# Pre-Approval Compliance
# ---------------------------------------------------------------------------

def check_pre_approval_compliance(training):
	"""Check HRD Corp eTRiS pre-approval compliance for a Training Event.

	Args:
		training: object with attributes:
			training_start_date (date | str)
			etris_application_date (date | str | None)

	Returns:
		dict:
			status       : "ok" | "not_submitted" | "late_application"
			claimable    : bool   (False if application was late)
			messages     : list[str]
	"""
	training_start = getdate(training.training_start_date) if training.training_start_date else None
	app_date = getdate(training.etris_application_date) if getattr(training, "etris_application_date", None) else None
	today_date = getdate(today())

	messages = []
	claimable = True
	status = "ok"

	if not app_date:
		# No application submitted yet
		if training_start and today_date >= training_start:
			# Training has already started / passed — critical
			status = "not_submitted"
			claimable = False
			messages.append(
				"ALERT: eTRiS application has not been submitted. "
				"Training start date has been reached. "
				"Grant is no longer claimable — HRD Corp auto-rejects post-training applications."
			)
		else:
			# Training hasn't started yet but no application
			status = "not_submitted"
			messages.append(
				"WARNING: eTRiS application not yet submitted. "
				"Submit at least 1 working day before training start to qualify for SBL-KHAS grant."
			)
	else:
		# Application was submitted — check if it was on time (must be BEFORE training_start_date)
		if training_start and app_date >= training_start:
			status = "late_application"
			claimable = False
			messages.append(
				f"ERROR: eTRiS application date ({app_date}) is on or after training start date "
				f"({training_start}). HRD Corp auto-rejects same-day or post-training applications. "
				"This training is non-claimable."
			)

	return {
		"status": status,
		"claimable": claimable,
		"messages": messages,
	}


# ---------------------------------------------------------------------------
# Claim Deadline Compliance
# ---------------------------------------------------------------------------

def check_claim_deadline_compliance(training):
	"""Check HRD Corp post-training claim deadline compliance.

	Alert schedule (days/months after training_end_date):
	  day 20  → approaching preferred 30-day deadline
	  day 28  → urgent — 30-day preferred deadline imminent
	  5 months → critical — escalate to HR Director
	  5.5 months (165 days) → critical urgent — 6-month absolute deadline approaching

	Args:
		training: object with attributes:
			training_end_date (date | str)
			etris_claim_submission_date (date | str | None)

	Returns:
		dict:
			status   : "ok" | "claim_due_soon" | "claim_urgent" | "claim_critical" |
			           "claim_critical_urgent" | "claim_expired" | "claim_submitted"
			messages : list[str]
			days_since_training_end : int | None
	"""
	training_end = getdate(training.training_end_date) if getattr(training, "training_end_date", None) else None
	claim_date = getdate(training.etris_claim_submission_date) if getattr(training, "etris_claim_submission_date", None) else None

	if not training_end:
		return {
			"status": "ok",
			"messages": [],
			"days_since_training_end": None,
		}

	if claim_date:
		# Claim already submitted
		return {
			"status": "claim_submitted",
			"messages": [f"Claim submitted on {claim_date}."],
			"days_since_training_end": date_diff(claim_date, training_end),
		}

	today_date = getdate(today())
	days_elapsed = date_diff(today_date, training_end)

	if days_elapsed < 0:
		# Training not yet ended
		return {
			"status": "ok",
			"messages": [],
			"days_since_training_end": days_elapsed,
		}

	# 6-month absolute deadline = 183 days (approx)
	SIX_MONTHS_DAYS = 183
	FIVE_HALF_MONTHS_DAYS = 165
	FIVE_MONTHS_DAYS = 153

	messages = []
	status = "ok"

	if days_elapsed >= SIX_MONTHS_DAYS:
		status = "claim_expired"
		messages.append(
			f"EXPIRED: {days_elapsed} days since training ended. "
			"6-month absolute HRD Corp claim deadline has passed. "
			"Claim cannot be recovered — contact HRD Corp for guidance."
		)
	elif days_elapsed >= FIVE_HALF_MONTHS_DAYS:
		status = "claim_critical_urgent"
		days_remaining = SIX_MONTHS_DAYS - days_elapsed
		messages.append(
			f"CRITICAL URGENT (HR Director): {days_elapsed} days since training ended. "
			f"Only {days_remaining} days remain before the 6-month absolute deadline. "
			"Submit eTRiS claim IMMEDIATELY."
		)
	elif days_elapsed >= FIVE_MONTHS_DAYS:
		status = "claim_critical"
		days_remaining = SIX_MONTHS_DAYS - days_elapsed
		messages.append(
			f"CRITICAL (Escalate to HR Director): {days_elapsed} days since training ended. "
			f"{days_remaining} days remain before the 6-month absolute HRD Corp deadline. "
			"Escalate claim submission urgently."
		)
	elif days_elapsed >= 28:
		status = "claim_urgent"
		messages.append(
			f"URGENT: {days_elapsed} days since training ended. "
			"30-day preferred claim deadline imminent — submit eTRiS claim now to avoid complications."
		)
	elif days_elapsed >= 20:
		status = "claim_due_soon"
		days_remaining = 30 - days_elapsed
		messages.append(
			f"REMINDER: {days_elapsed} days since training ended. "
			f"{days_remaining} days remain before the preferred 30-day claim window closes. "
			"Submit eTRiS claim soon."
		)

	return {
		"status": status,
		"messages": messages,
		"days_since_training_end": days_elapsed,
	}


# ---------------------------------------------------------------------------
# Dashboard Summary
# ---------------------------------------------------------------------------

DASHBOARD_CATEGORIES = (
	"needs_pre_approval",
	"expiring_claim_windows",
	"expired_claim_windows",
	"rejected_grants",
)


def get_hrd_dashboard_summary(trainings):
	"""Categorise a list of Training Event objects for the HRD dashboard.

	Args:
		trainings: iterable of training objects (see check_* functions for
		           expected attributes).  Each object may optionally have:
		               etris_approval_status (str | None)
		               etris_rejection_reason (str | None)

	Returns:
		dict:
			needs_pre_approval    : list — trainings where pre-approval not yet done
			expiring_claim_windows: list — trainings within the 30-day claim window
			                               (not yet expired, claim not submitted)
			expired_claim_windows : list — trainings past 6-month hard deadline
			rejected_grants       : list — trainings with etris_approval_status == "Rejected"
	"""
	result = {cat: [] for cat in DASHBOARD_CATEGORIES}

	for training in trainings:
		pre = check_pre_approval_compliance(training)
		claim = check_claim_deadline_compliance(training)

		# Rejected grant
		approval_status = getattr(training, "etris_approval_status", None) or ""
		if approval_status.lower() == "rejected":
			result["rejected_grants"].append({
				"training": training,
				"rejection_reason": getattr(training, "etris_rejection_reason", None),
			})
			continue

		# Pre-approval needed (not submitted, training hasn't started yet)
		if pre["status"] == "not_submitted" and pre["claimable"]:
			result["needs_pre_approval"].append({
				"training": training,
				"messages": pre["messages"],
			})

		# Expired claim window
		if claim["status"] == "claim_expired":
			result["expired_claim_windows"].append({
				"training": training,
				"messages": claim["messages"],
			})
		# Expiring claim windows (within 30-day or approaching 6-month deadline)
		elif claim["status"] in ("claim_due_soon", "claim_urgent",
		                         "claim_critical", "claim_critical_urgent"):
			result["expiring_claim_windows"].append({
				"training": training,
				"messages": claim["messages"],
			})

	return result
