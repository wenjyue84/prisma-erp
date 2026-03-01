"""Worker Classification Flag: Contract-of-Service vs Contract-for-Service.

LHDN Public Ruling 3/2019 distinguishes:
  - **Contract of Service** (employment): Worker is an employee, subject to PCB
    deduction under Section 107A ITA 1967.
  - **Contract for Service** (independent contractor): Worker is a freelancer,
    agent, dealer, or distributor. Payments are subject to Withholding Tax (WHT)
    under Section 107D ITA 1967 and CP58 annual reporting — NOT PCB.

Misclassification leads to incorrect statutory deductions, potential penalties,
and LHDN audit findings.

US-220: Worker Classification Flag — Contract-of-Service vs Contract-for-Service
         for PCB/WHT Routing.
"""

from datetime import datetime

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The two classification values
CONTRACT_OF_SERVICE = "Contract of Service"
CONTRACT_FOR_SERVICE = "Contract for Service"

# Valid classification values
VALID_CONTRACT_TYPES = {CONTRACT_OF_SERVICE, CONTRACT_FOR_SERVICE}

# Default classification for new employees
DEFAULT_CONTRACT_TYPE = CONTRACT_OF_SERVICE

# Custom field name on Employee DocType
EMPLOYEE_CONTRACT_TYPE_FIELD = "custom_contract_type"

# Statutory scheme routing
PCB_APPLICABLE_TYPES = {CONTRACT_OF_SERVICE}
WHT_APPLICABLE_TYPES = {CONTRACT_FOR_SERVICE}

# Audit trail change reasons (common presets)
CLASSIFICATION_CHANGE_REASONS = [
    "Initial classification on hire",
    "Reclassified following LHDN audit",
    "Reclassified per legal review",
    "Corrected misclassification",
    "Worker engagement terms changed",
]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def is_valid_contract_type(contract_type):
    """Check if a contract type string is a valid classification.

    Args:
        contract_type: The contract type string to validate.

    Returns:
        True if the value is in VALID_CONTRACT_TYPES, False otherwise.
    """
    return contract_type in VALID_CONTRACT_TYPES


def get_contract_type_or_default(contract_type):
    """Return the contract type if valid, otherwise return the default.

    Args:
        contract_type: The contract type to check.

    Returns:
        The contract type if valid, or DEFAULT_CONTRACT_TYPE.
    """
    if contract_type in VALID_CONTRACT_TYPES:
        return contract_type
    return DEFAULT_CONTRACT_TYPE


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------


def is_pcb_applicable(contract_type):
    """Return True if the worker's contract type subjects them to PCB.

    Contract of Service workers are subject to PCB under Section 107A ITA 1967.

    Args:
        contract_type: The worker's contract classification.

    Returns:
        True if PCB applies, False otherwise.
    """
    return contract_type in PCB_APPLICABLE_TYPES


def is_wht_applicable(contract_type):
    """Return True if the worker's contract type subjects them to WHT.

    Contract for Service workers are subject to WHT under Section 107D ITA 1967.

    Args:
        contract_type: The worker's contract classification.

    Returns:
        True if WHT applies, False otherwise.
    """
    return contract_type in WHT_APPLICABLE_TYPES


def get_statutory_scheme(contract_type):
    """Determine the statutory deduction scheme for a worker.

    Args:
        contract_type: The worker's contract classification.

    Returns:
        dict with keys:
            scheme (str): 'PCB' or 'WHT'
            section (str): ITA section reference
            description (str): Human-readable description
            deduction_type (str): 'monthly_pcb' or 'withholding_tax'

    Raises:
        ValueError: If contract_type is not valid.
    """
    if contract_type not in VALID_CONTRACT_TYPES:
        raise ValueError(
            f"Invalid contract type '{contract_type}'. "
            f"Must be one of: {sorted(VALID_CONTRACT_TYPES)}"
        )

    if contract_type == CONTRACT_OF_SERVICE:
        return {
            "scheme": "PCB",
            "section": "Section 107A ITA 1967",
            "description": "Monthly Tax Deduction (PCB/MTD) — employer withholding for employees",
            "deduction_type": "monthly_pcb",
        }
    else:
        return {
            "scheme": "WHT",
            "section": "Section 107D ITA 1967",
            "description": "Withholding Tax 2% — payer deduction for contractors/agents",
            "deduction_type": "withholding_tax",
        }


# ---------------------------------------------------------------------------
# Salary Slip payroll run validation
# ---------------------------------------------------------------------------


def validate_salary_slip_worker(contract_type, employee_name=None):
    """Validate that a worker should be in a Salary Slip payroll run.

    Contract for Service workers should NOT be in Salary Slip payroll
    runs — contractor payments use Supplier/Purchase Invoice instead.

    Args:
        contract_type: The worker's contract classification.
        employee_name: Optional employee name for the warning message.

    Returns:
        dict with keys:
            valid (bool): True if worker can be in payroll run.
            warning (str|None): Warning message if invalid, None if OK.
    """
    effective_type = get_contract_type_or_default(contract_type)

    if effective_type == CONTRACT_FOR_SERVICE:
        name_part = f" ({employee_name})" if employee_name else ""
        return {
            "valid": False,
            "warning": (
                f"Worker{name_part} is classified as '{CONTRACT_FOR_SERVICE}'. "
                f"Contractor payments should use Supplier/Purchase Invoice, "
                f"not Salary Slip payroll. WHT under Section 107D applies."
            ),
        }

    return {"valid": True, "warning": None}


def validate_payroll_batch(employees):
    """Validate a batch of employees for payroll run eligibility.

    Args:
        employees: List of dicts, each with 'employee_name' and 'contract_type'.

    Returns:
        dict with keys:
            valid_count (int): Number of valid (Contract of Service) workers.
            invalid_count (int): Number of invalid (Contract for Service) workers.
            warnings (list): List of warning strings for invalid workers.
            all_valid (bool): True if all workers are valid for payroll.
    """
    warnings = []
    valid_count = 0
    invalid_count = 0

    for emp in employees:
        ct = emp.get("contract_type", DEFAULT_CONTRACT_TYPE)
        name = emp.get("employee_name", "Unknown")
        result = validate_salary_slip_worker(ct, name)
        if result["valid"]:
            valid_count += 1
        else:
            invalid_count += 1
            warnings.append(result["warning"])

    return {
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "warnings": warnings,
        "all_valid": invalid_count == 0,
    }


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def create_audit_entry(
    employee_id,
    old_classification,
    new_classification,
    changed_by,
    reason,
    timestamp=None,
):
    """Create an audit trail entry for a classification change.

    Args:
        employee_id: Employee ID (e.g. 'HR-EMP-00001').
        old_classification: Previous contract type value (or None for initial).
        new_classification: New contract type value.
        changed_by: User who made the change.
        reason: Reason for the change.
        timestamp: Optional datetime; defaults to now.

    Returns:
        dict representing the audit entry.

    Raises:
        ValueError: If new_classification is not valid.
    """
    if new_classification not in VALID_CONTRACT_TYPES:
        raise ValueError(
            f"Invalid new classification '{new_classification}'. "
            f"Must be one of: {sorted(VALID_CONTRACT_TYPES)}"
        )

    if timestamp is None:
        timestamp = datetime.now()

    return {
        "employee_id": employee_id,
        "old_classification": old_classification,
        "new_classification": new_classification,
        "changed_by": changed_by,
        "reason": reason,
        "timestamp": timestamp,
        "is_initial": old_classification is None,
        "statutory_impact": _describe_statutory_impact(old_classification, new_classification),
    }


def _describe_statutory_impact(old_type, new_type):
    """Describe the statutory impact of a classification change.

    Args:
        old_type: Previous classification (or None).
        new_type: New classification.

    Returns:
        str describing the impact.
    """
    if old_type is None:
        if new_type == CONTRACT_OF_SERVICE:
            return "Initial classification: PCB/MTD deductions will apply"
        else:
            return "Initial classification: WHT under Section 107D will apply"

    if old_type == new_type:
        return "No change in statutory scheme"

    if old_type == CONTRACT_OF_SERVICE and new_type == CONTRACT_FOR_SERVICE:
        return (
            "Reclassified from employee to contractor: "
            "PCB deductions will stop; WHT under Section 107D will apply"
        )

    return (
        "Reclassified from contractor to employee: "
        "WHT will stop; PCB/MTD deductions will apply"
    )


def validate_audit_entry(entry):
    """Validate that an audit entry has all required fields.

    Args:
        entry: dict to validate.

    Returns:
        dict with keys:
            valid (bool): True if entry is complete and correct.
            errors (list): List of error strings.
    """
    errors = []
    required = ["employee_id", "new_classification", "changed_by", "reason", "timestamp"]

    for field in required:
        if not entry.get(field):
            errors.append(f"Missing required field: {field}")

    if entry.get("new_classification") and entry["new_classification"] not in VALID_CONTRACT_TYPES:
        errors.append(
            f"Invalid new_classification: {entry['new_classification']}"
        )

    if (
        entry.get("old_classification")
        and entry["old_classification"] not in VALID_CONTRACT_TYPES
    ):
        errors.append(
            f"Invalid old_classification: {entry['old_classification']}"
        )

    return {"valid": len(errors) == 0, "errors": errors}


# ---------------------------------------------------------------------------
# Classification summary / reporting
# ---------------------------------------------------------------------------


def classify_workforce(employees):
    """Classify a list of employees by contract type.

    Args:
        employees: List of dicts, each with at least 'employee_name' and
                   optionally 'contract_type'.

    Returns:
        dict with keys:
            contract_of_service (list): Employees classified as CoS.
            contract_for_service (list): Employees classified as CfS.
            total (int): Total employees.
            cos_count (int): Count of Contract of Service.
            cfs_count (int): Count of Contract for Service.
            cos_percentage (float): Percentage of CoS workers.
            cfs_percentage (float): Percentage of CfS workers.
    """
    cos_list = []
    cfs_list = []

    for emp in employees:
        ct = get_contract_type_or_default(emp.get("contract_type"))
        if ct == CONTRACT_OF_SERVICE:
            cos_list.append(emp)
        else:
            cfs_list.append(emp)

    total = len(employees)
    cos_count = len(cos_list)
    cfs_count = len(cfs_list)

    return {
        "contract_of_service": cos_list,
        "contract_for_service": cfs_list,
        "total": total,
        "cos_count": cos_count,
        "cfs_count": cfs_count,
        "cos_percentage": round((cos_count / total * 100), 2) if total > 0 else 0.0,
        "cfs_percentage": round((cfs_count / total * 100), 2) if total > 0 else 0.0,
    }


def generate_classification_report(employees, company=None):
    """Generate a worker classification compliance report.

    Args:
        employees: List of employee dicts with 'employee_name', 'employee_id',
                   and optionally 'contract_type'.
        company: Optional company name for the report header.

    Returns:
        dict with summary and per-employee details including statutory scheme.
    """
    summary = classify_workforce(employees)

    details = []
    for emp in employees:
        ct = get_contract_type_or_default(emp.get("contract_type"))
        scheme = get_statutory_scheme(ct)
        details.append({
            "employee_id": emp.get("employee_id", ""),
            "employee_name": emp.get("employee_name", ""),
            "contract_type": ct,
            "scheme": scheme["scheme"],
            "section": scheme["section"],
            "deduction_type": scheme["deduction_type"],
        })

    return {
        "company": company,
        "total_workers": summary["total"],
        "cos_count": summary["cos_count"],
        "cfs_count": summary["cfs_count"],
        "cos_percentage": summary["cos_percentage"],
        "cfs_percentage": summary["cfs_percentage"],
        "details": details,
    }
