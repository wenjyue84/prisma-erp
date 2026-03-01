"""Tests for Worker Classification Flag: Contract-of-Service vs Contract-for-Service (US-220).

Covers:
- Constants and configuration values
- Contract type validation
- PCB/WHT routing logic
- Statutory scheme determination
- Salary Slip payroll run validation
- Payroll batch validation
- Audit trail creation and validation
- Statutory impact descriptions
- Workforce classification summary
- Classification compliance report generation
"""

import unittest
from datetime import datetime

from lhdn_payroll_integration.services.worker_classification_service import (
    CONTRACT_OF_SERVICE,
    CONTRACT_FOR_SERVICE,
    VALID_CONTRACT_TYPES,
    DEFAULT_CONTRACT_TYPE,
    EMPLOYEE_CONTRACT_TYPE_FIELD,
    PCB_APPLICABLE_TYPES,
    WHT_APPLICABLE_TYPES,
    CLASSIFICATION_CHANGE_REASONS,
    is_valid_contract_type,
    get_contract_type_or_default,
    is_pcb_applicable,
    is_wht_applicable,
    get_statutory_scheme,
    validate_salary_slip_worker,
    validate_payroll_batch,
    create_audit_entry,
    validate_audit_entry,
    classify_workforce,
    generate_classification_report,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestWorkerClassificationConstants(unittest.TestCase):
    """Verify module-level constants."""

    def test_contract_of_service_value(self):
        self.assertEqual(CONTRACT_OF_SERVICE, "Contract of Service")

    def test_contract_for_service_value(self):
        self.assertEqual(CONTRACT_FOR_SERVICE, "Contract for Service")

    def test_valid_contract_types_has_both(self):
        self.assertEqual(VALID_CONTRACT_TYPES, {CONTRACT_OF_SERVICE, CONTRACT_FOR_SERVICE})

    def test_default_is_contract_of_service(self):
        self.assertEqual(DEFAULT_CONTRACT_TYPE, CONTRACT_OF_SERVICE)

    def test_employee_field_name(self):
        self.assertEqual(EMPLOYEE_CONTRACT_TYPE_FIELD, "custom_contract_type")

    def test_pcb_applicable_types(self):
        self.assertIn(CONTRACT_OF_SERVICE, PCB_APPLICABLE_TYPES)
        self.assertNotIn(CONTRACT_FOR_SERVICE, PCB_APPLICABLE_TYPES)

    def test_wht_applicable_types(self):
        self.assertIn(CONTRACT_FOR_SERVICE, WHT_APPLICABLE_TYPES)
        self.assertNotIn(CONTRACT_OF_SERVICE, WHT_APPLICABLE_TYPES)

    def test_classification_change_reasons_not_empty(self):
        self.assertGreater(len(CLASSIFICATION_CHANGE_REASONS), 0)

    def test_classification_change_reasons_are_strings(self):
        for reason in CLASSIFICATION_CHANGE_REASONS:
            self.assertIsInstance(reason, str)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestIsValidContractType(unittest.TestCase):
    """Test is_valid_contract_type()."""

    def test_contract_of_service_valid(self):
        self.assertTrue(is_valid_contract_type(CONTRACT_OF_SERVICE))

    def test_contract_for_service_valid(self):
        self.assertTrue(is_valid_contract_type(CONTRACT_FOR_SERVICE))

    def test_empty_string_invalid(self):
        self.assertFalse(is_valid_contract_type(""))

    def test_none_invalid(self):
        self.assertFalse(is_valid_contract_type(None))

    def test_random_string_invalid(self):
        self.assertFalse(is_valid_contract_type("Freelancer"))

    def test_case_sensitive(self):
        self.assertFalse(is_valid_contract_type("contract of service"))


class TestGetContractTypeOrDefault(unittest.TestCase):
    """Test get_contract_type_or_default()."""

    def test_valid_cos_returns_cos(self):
        self.assertEqual(
            get_contract_type_or_default(CONTRACT_OF_SERVICE),
            CONTRACT_OF_SERVICE,
        )

    def test_valid_cfs_returns_cfs(self):
        self.assertEqual(
            get_contract_type_or_default(CONTRACT_FOR_SERVICE),
            CONTRACT_FOR_SERVICE,
        )

    def test_none_returns_default(self):
        self.assertEqual(
            get_contract_type_or_default(None),
            DEFAULT_CONTRACT_TYPE,
        )

    def test_empty_returns_default(self):
        self.assertEqual(
            get_contract_type_or_default(""),
            DEFAULT_CONTRACT_TYPE,
        )

    def test_invalid_returns_default(self):
        self.assertEqual(
            get_contract_type_or_default("Intern"),
            DEFAULT_CONTRACT_TYPE,
        )


# ---------------------------------------------------------------------------
# PCB / WHT Routing
# ---------------------------------------------------------------------------


class TestIsPcbApplicable(unittest.TestCase):
    """Test is_pcb_applicable()."""

    def test_cos_has_pcb(self):
        self.assertTrue(is_pcb_applicable(CONTRACT_OF_SERVICE))

    def test_cfs_no_pcb(self):
        self.assertFalse(is_pcb_applicable(CONTRACT_FOR_SERVICE))

    def test_invalid_type_no_pcb(self):
        self.assertFalse(is_pcb_applicable("Unknown"))


class TestIsWhtApplicable(unittest.TestCase):
    """Test is_wht_applicable()."""

    def test_cfs_has_wht(self):
        self.assertTrue(is_wht_applicable(CONTRACT_FOR_SERVICE))

    def test_cos_no_wht(self):
        self.assertFalse(is_wht_applicable(CONTRACT_OF_SERVICE))

    def test_invalid_type_no_wht(self):
        self.assertFalse(is_wht_applicable("Unknown"))


class TestPcbWhtMutualExclusion(unittest.TestCase):
    """PCB and WHT must be mutually exclusive for any valid type."""

    def test_cos_pcb_only(self):
        self.assertTrue(is_pcb_applicable(CONTRACT_OF_SERVICE))
        self.assertFalse(is_wht_applicable(CONTRACT_OF_SERVICE))

    def test_cfs_wht_only(self):
        self.assertFalse(is_pcb_applicable(CONTRACT_FOR_SERVICE))
        self.assertTrue(is_wht_applicable(CONTRACT_FOR_SERVICE))


# ---------------------------------------------------------------------------
# Statutory Scheme
# ---------------------------------------------------------------------------


class TestGetStatutoryScheme(unittest.TestCase):
    """Test get_statutory_scheme()."""

    def test_cos_returns_pcb_scheme(self):
        result = get_statutory_scheme(CONTRACT_OF_SERVICE)
        self.assertEqual(result["scheme"], "PCB")
        self.assertEqual(result["section"], "Section 107A ITA 1967")
        self.assertEqual(result["deduction_type"], "monthly_pcb")

    def test_cfs_returns_wht_scheme(self):
        result = get_statutory_scheme(CONTRACT_FOR_SERVICE)
        self.assertEqual(result["scheme"], "WHT")
        self.assertEqual(result["section"], "Section 107D ITA 1967")
        self.assertEqual(result["deduction_type"], "withholding_tax")

    def test_cos_description_mentions_pcb(self):
        result = get_statutory_scheme(CONTRACT_OF_SERVICE)
        self.assertIn("PCB", result["description"])

    def test_cfs_description_mentions_wht(self):
        result = get_statutory_scheme(CONTRACT_FOR_SERVICE)
        self.assertIn("Withholding Tax", result["description"])

    def test_invalid_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_statutory_scheme("Invalid")

    def test_none_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_statutory_scheme(None)


# ---------------------------------------------------------------------------
# Salary Slip Validation
# ---------------------------------------------------------------------------


class TestValidateSalarySlipWorker(unittest.TestCase):
    """Test validate_salary_slip_worker()."""

    def test_cos_worker_valid_for_payroll(self):
        result = validate_salary_slip_worker(CONTRACT_OF_SERVICE)
        self.assertTrue(result["valid"])
        self.assertIsNone(result["warning"])

    def test_cfs_worker_invalid_for_payroll(self):
        result = validate_salary_slip_worker(CONTRACT_FOR_SERVICE)
        self.assertFalse(result["valid"])
        self.assertIsNotNone(result["warning"])

    def test_cfs_warning_mentions_section_107d(self):
        result = validate_salary_slip_worker(CONTRACT_FOR_SERVICE)
        self.assertIn("Section 107D", result["warning"])

    def test_cfs_warning_mentions_purchase_invoice(self):
        result = validate_salary_slip_worker(CONTRACT_FOR_SERVICE)
        self.assertIn("Purchase Invoice", result["warning"])

    def test_cfs_warning_includes_employee_name(self):
        result = validate_salary_slip_worker(CONTRACT_FOR_SERVICE, "Ali bin Ahmad")
        self.assertIn("Ali bin Ahmad", result["warning"])

    def test_cos_with_name_still_valid(self):
        result = validate_salary_slip_worker(CONTRACT_OF_SERVICE, "Some Employee")
        self.assertTrue(result["valid"])

    def test_none_type_defaults_to_cos_valid(self):
        result = validate_salary_slip_worker(None)
        self.assertTrue(result["valid"])


# ---------------------------------------------------------------------------
# Payroll Batch Validation
# ---------------------------------------------------------------------------


class TestValidatePayrollBatch(unittest.TestCase):
    """Test validate_payroll_batch()."""

    def test_all_cos_workers_valid(self):
        employees = [
            {"employee_name": "Alice", "contract_type": CONTRACT_OF_SERVICE},
            {"employee_name": "Bob", "contract_type": CONTRACT_OF_SERVICE},
        ]
        result = validate_payroll_batch(employees)
        self.assertTrue(result["all_valid"])
        self.assertEqual(result["valid_count"], 2)
        self.assertEqual(result["invalid_count"], 0)
        self.assertEqual(len(result["warnings"]), 0)

    def test_mixed_batch_flags_cfs(self):
        employees = [
            {"employee_name": "Alice", "contract_type": CONTRACT_OF_SERVICE},
            {"employee_name": "Contractor Bob", "contract_type": CONTRACT_FOR_SERVICE},
        ]
        result = validate_payroll_batch(employees)
        self.assertFalse(result["all_valid"])
        self.assertEqual(result["valid_count"], 1)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("Contractor Bob", result["warnings"][0])

    def test_all_cfs_workers_all_invalid(self):
        employees = [
            {"employee_name": "Agent A", "contract_type": CONTRACT_FOR_SERVICE},
            {"employee_name": "Agent B", "contract_type": CONTRACT_FOR_SERVICE},
        ]
        result = validate_payroll_batch(employees)
        self.assertFalse(result["all_valid"])
        self.assertEqual(result["valid_count"], 0)
        self.assertEqual(result["invalid_count"], 2)

    def test_empty_batch(self):
        result = validate_payroll_batch([])
        self.assertTrue(result["all_valid"])
        self.assertEqual(result["valid_count"], 0)
        self.assertEqual(result["invalid_count"], 0)

    def test_missing_contract_type_defaults_to_cos(self):
        employees = [{"employee_name": "No Type"}]
        result = validate_payroll_batch(employees)
        self.assertTrue(result["all_valid"])
        self.assertEqual(result["valid_count"], 1)

    def test_multiple_invalid_generates_multiple_warnings(self):
        employees = [
            {"employee_name": "Agent 1", "contract_type": CONTRACT_FOR_SERVICE},
            {"employee_name": "Agent 2", "contract_type": CONTRACT_FOR_SERVICE},
            {"employee_name": "Agent 3", "contract_type": CONTRACT_FOR_SERVICE},
        ]
        result = validate_payroll_batch(employees)
        self.assertEqual(len(result["warnings"]), 3)


# ---------------------------------------------------------------------------
# Audit Trail
# ---------------------------------------------------------------------------


class TestCreateAuditEntry(unittest.TestCase):
    """Test create_audit_entry()."""

    def test_basic_audit_entry(self):
        ts = datetime(2026, 3, 1, 10, 0, 0)
        entry = create_audit_entry(
            employee_id="HR-EMP-00001",
            old_classification=CONTRACT_OF_SERVICE,
            new_classification=CONTRACT_FOR_SERVICE,
            changed_by="admin@test.com",
            reason="Reclassified following LHDN audit",
            timestamp=ts,
        )
        self.assertEqual(entry["employee_id"], "HR-EMP-00001")
        self.assertEqual(entry["old_classification"], CONTRACT_OF_SERVICE)
        self.assertEqual(entry["new_classification"], CONTRACT_FOR_SERVICE)
        self.assertEqual(entry["changed_by"], "admin@test.com")
        self.assertEqual(entry["reason"], "Reclassified following LHDN audit")
        self.assertEqual(entry["timestamp"], ts)
        self.assertFalse(entry["is_initial"])

    def test_initial_classification_flag(self):
        entry = create_audit_entry(
            employee_id="HR-EMP-00002",
            old_classification=None,
            new_classification=CONTRACT_OF_SERVICE,
            changed_by="admin@test.com",
            reason="Initial classification on hire",
        )
        self.assertTrue(entry["is_initial"])
        self.assertIsNone(entry["old_classification"])

    def test_auto_timestamp_when_none(self):
        entry = create_audit_entry(
            employee_id="HR-EMP-00003",
            old_classification=CONTRACT_OF_SERVICE,
            new_classification=CONTRACT_FOR_SERVICE,
            changed_by="admin@test.com",
            reason="Test",
        )
        self.assertIsInstance(entry["timestamp"], datetime)

    def test_invalid_new_classification_raises(self):
        with self.assertRaises(ValueError):
            create_audit_entry(
                employee_id="HR-EMP-00004",
                old_classification=CONTRACT_OF_SERVICE,
                new_classification="Invalid",
                changed_by="admin@test.com",
                reason="Test",
            )

    def test_statutory_impact_cos_to_cfs(self):
        entry = create_audit_entry(
            employee_id="HR-EMP-00005",
            old_classification=CONTRACT_OF_SERVICE,
            new_classification=CONTRACT_FOR_SERVICE,
            changed_by="admin@test.com",
            reason="Worker engagement terms changed",
        )
        self.assertIn("PCB deductions will stop", entry["statutory_impact"])
        self.assertIn("WHT", entry["statutory_impact"])

    def test_statutory_impact_cfs_to_cos(self):
        entry = create_audit_entry(
            employee_id="HR-EMP-00006",
            old_classification=CONTRACT_FOR_SERVICE,
            new_classification=CONTRACT_OF_SERVICE,
            changed_by="admin@test.com",
            reason="Corrected misclassification",
        )
        self.assertIn("WHT will stop", entry["statutory_impact"])
        self.assertIn("PCB", entry["statutory_impact"])

    def test_statutory_impact_initial_cos(self):
        entry = create_audit_entry(
            employee_id="HR-EMP-00007",
            old_classification=None,
            new_classification=CONTRACT_OF_SERVICE,
            changed_by="admin@test.com",
            reason="Initial classification on hire",
        )
        self.assertIn("PCB", entry["statutory_impact"])

    def test_statutory_impact_initial_cfs(self):
        entry = create_audit_entry(
            employee_id="HR-EMP-00008",
            old_classification=None,
            new_classification=CONTRACT_FOR_SERVICE,
            changed_by="admin@test.com",
            reason="Initial classification on hire",
        )
        self.assertIn("WHT", entry["statutory_impact"])

    def test_statutory_impact_no_change(self):
        entry = create_audit_entry(
            employee_id="HR-EMP-00009",
            old_classification=CONTRACT_OF_SERVICE,
            new_classification=CONTRACT_OF_SERVICE,
            changed_by="admin@test.com",
            reason="Re-confirmed classification",
        )
        self.assertIn("No change", entry["statutory_impact"])


class TestValidateAuditEntry(unittest.TestCase):
    """Test validate_audit_entry()."""

    def test_valid_entry(self):
        entry = {
            "employee_id": "HR-EMP-00001",
            "old_classification": CONTRACT_OF_SERVICE,
            "new_classification": CONTRACT_FOR_SERVICE,
            "changed_by": "admin@test.com",
            "reason": "Test reason",
            "timestamp": datetime.now(),
        }
        result = validate_audit_entry(entry)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_missing_employee_id(self):
        entry = {
            "new_classification": CONTRACT_OF_SERVICE,
            "changed_by": "admin@test.com",
            "reason": "Test",
            "timestamp": datetime.now(),
        }
        result = validate_audit_entry(entry)
        self.assertFalse(result["valid"])
        self.assertTrue(any("employee_id" in e for e in result["errors"]))

    def test_missing_changed_by(self):
        entry = {
            "employee_id": "HR-EMP-00001",
            "new_classification": CONTRACT_OF_SERVICE,
            "reason": "Test",
            "timestamp": datetime.now(),
        }
        result = validate_audit_entry(entry)
        self.assertFalse(result["valid"])

    def test_invalid_new_classification(self):
        entry = {
            "employee_id": "HR-EMP-00001",
            "new_classification": "BadValue",
            "changed_by": "admin@test.com",
            "reason": "Test",
            "timestamp": datetime.now(),
        }
        result = validate_audit_entry(entry)
        self.assertFalse(result["valid"])

    def test_invalid_old_classification(self):
        entry = {
            "employee_id": "HR-EMP-00001",
            "old_classification": "BadOldValue",
            "new_classification": CONTRACT_OF_SERVICE,
            "changed_by": "admin@test.com",
            "reason": "Test",
            "timestamp": datetime.now(),
        }
        result = validate_audit_entry(entry)
        self.assertFalse(result["valid"])

    def test_none_old_classification_is_ok(self):
        entry = {
            "employee_id": "HR-EMP-00001",
            "old_classification": None,
            "new_classification": CONTRACT_OF_SERVICE,
            "changed_by": "admin@test.com",
            "reason": "Test",
            "timestamp": datetime.now(),
        }
        result = validate_audit_entry(entry)
        self.assertTrue(result["valid"])


# ---------------------------------------------------------------------------
# Workforce Classification
# ---------------------------------------------------------------------------


class TestClassifyWorkforce(unittest.TestCase):
    """Test classify_workforce()."""

    def test_all_cos(self):
        employees = [
            {"employee_name": "A", "contract_type": CONTRACT_OF_SERVICE},
            {"employee_name": "B", "contract_type": CONTRACT_OF_SERVICE},
        ]
        result = classify_workforce(employees)
        self.assertEqual(result["cos_count"], 2)
        self.assertEqual(result["cfs_count"], 0)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["cos_percentage"], 100.0)
        self.assertEqual(result["cfs_percentage"], 0.0)

    def test_all_cfs(self):
        employees = [
            {"employee_name": "A", "contract_type": CONTRACT_FOR_SERVICE},
            {"employee_name": "B", "contract_type": CONTRACT_FOR_SERVICE},
        ]
        result = classify_workforce(employees)
        self.assertEqual(result["cos_count"], 0)
        self.assertEqual(result["cfs_count"], 2)
        self.assertEqual(result["cfs_percentage"], 100.0)

    def test_mixed(self):
        employees = [
            {"employee_name": "Employee", "contract_type": CONTRACT_OF_SERVICE},
            {"employee_name": "Contractor", "contract_type": CONTRACT_FOR_SERVICE},
            {"employee_name": "Default"},  # no contract_type → defaults to CoS
        ]
        result = classify_workforce(employees)
        self.assertEqual(result["cos_count"], 2)
        self.assertEqual(result["cfs_count"], 1)
        self.assertEqual(result["total"], 3)
        self.assertAlmostEqual(result["cos_percentage"], 66.67)
        self.assertAlmostEqual(result["cfs_percentage"], 33.33)

    def test_empty_list(self):
        result = classify_workforce([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["cos_count"], 0)
        self.assertEqual(result["cfs_count"], 0)
        self.assertEqual(result["cos_percentage"], 0.0)
        self.assertEqual(result["cfs_percentage"], 0.0)

    def test_returned_lists_contain_originals(self):
        emp_cos = {"employee_name": "A", "contract_type": CONTRACT_OF_SERVICE}
        emp_cfs = {"employee_name": "B", "contract_type": CONTRACT_FOR_SERVICE}
        result = classify_workforce([emp_cos, emp_cfs])
        self.assertIn(emp_cos, result["contract_of_service"])
        self.assertIn(emp_cfs, result["contract_for_service"])


# ---------------------------------------------------------------------------
# Classification Report
# ---------------------------------------------------------------------------


class TestGenerateClassificationReport(unittest.TestCase):
    """Test generate_classification_report()."""

    def test_report_structure(self):
        employees = [
            {
                "employee_id": "HR-EMP-00001",
                "employee_name": "Alice",
                "contract_type": CONTRACT_OF_SERVICE,
            },
            {
                "employee_id": "HR-EMP-00002",
                "employee_name": "Bob (Agent)",
                "contract_type": CONTRACT_FOR_SERVICE,
            },
        ]
        report = generate_classification_report(employees, company="Test Corp")
        self.assertEqual(report["company"], "Test Corp")
        self.assertEqual(report["total_workers"], 2)
        self.assertEqual(report["cos_count"], 1)
        self.assertEqual(report["cfs_count"], 1)
        self.assertEqual(len(report["details"]), 2)

    def test_report_detail_has_scheme(self):
        employees = [
            {
                "employee_id": "HR-EMP-00001",
                "employee_name": "Alice",
                "contract_type": CONTRACT_OF_SERVICE,
            },
        ]
        report = generate_classification_report(employees)
        detail = report["details"][0]
        self.assertEqual(detail["scheme"], "PCB")
        self.assertEqual(detail["section"], "Section 107A ITA 1967")
        self.assertEqual(detail["deduction_type"], "monthly_pcb")

    def test_report_cfs_detail_has_wht(self):
        employees = [
            {
                "employee_id": "HR-EMP-00002",
                "employee_name": "Agent",
                "contract_type": CONTRACT_FOR_SERVICE,
            },
        ]
        report = generate_classification_report(employees)
        detail = report["details"][0]
        self.assertEqual(detail["scheme"], "WHT")
        self.assertEqual(detail["deduction_type"], "withholding_tax")

    def test_report_no_company(self):
        report = generate_classification_report([])
        self.assertIsNone(report["company"])
        self.assertEqual(report["total_workers"], 0)

    def test_report_default_contract_type_for_missing(self):
        employees = [{"employee_id": "HR-EMP-00003", "employee_name": "NoType"}]
        report = generate_classification_report(employees)
        detail = report["details"][0]
        self.assertEqual(detail["contract_type"], CONTRACT_OF_SERVICE)
        self.assertEqual(detail["scheme"], "PCB")

    def test_report_percentages(self):
        employees = [
            {"employee_id": "1", "employee_name": "A", "contract_type": CONTRACT_OF_SERVICE},
            {"employee_id": "2", "employee_name": "B", "contract_type": CONTRACT_OF_SERVICE},
            {"employee_id": "3", "employee_name": "C", "contract_type": CONTRACT_FOR_SERVICE},
            {"employee_id": "4", "employee_name": "D", "contract_type": CONTRACT_OF_SERVICE},
        ]
        report = generate_classification_report(employees, company="4 Workers Inc")
        self.assertEqual(report["cos_count"], 3)
        self.assertEqual(report["cfs_count"], 1)
        self.assertEqual(report["cos_percentage"], 75.0)
        self.assertEqual(report["cfs_percentage"], 25.0)
