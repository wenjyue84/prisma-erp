"""Tests for US-177: Add Life/Medical Insurance Relief Extension to Children on TP1 Form for YA2026.

Budget 2026 expanded two insurance relief categories to include premiums for children:
1. Life insurance / takaful premium (previously self + spouse, RM3,000 combined)
   → already captured as children_life_medical_insurance (YA2026+)
2. Education & medical insurance premium (previously self + spouse, RM3,000 → now RM4,000 combined
   with children's premiums as child_education_medical_insurance, YA2026+)

Acceptance criteria:
  AC1: TP1 has 'children_life_medical_insurance' sub-field with RM3,000 combined cap (life pool)
  AC2: TP1 has 'child_education_medical_insurance' sub-field with RM4,000 combined cap (medical pool)
  AC3: PCB computation reduces chargeable income by declared child insurance premiums up to caps
  AC4: Combined (self + child) insurance cannot exceed the statutory cap
  AC5: Pre-YA2026 records do not show child insurance fields (year-gated)
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
    EmployeeTP1Relief,
    _CAPS_YA2026,
    _CAPS_DEFAULT,
    _MEDICAL_EDUCATION_COMBINED_CAP,
    _LIFE_VOLUNTARY_EPF_COMBINED_CAP,
    _RELIEF_FIELDS,
    _get_caps_for_year,
    get_employee_tp1_reliefs,
)
from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tp1_doc(**kwargs):
    """Build an unsaved EmployeeTP1Relief doc for testing."""
    defaults = {
        "doctype": "Employee TP1 Relief",
        "employee": "TEST-EMP-US177",
        "tax_year": 2026,
        "self_relief": 9000,
        "spouse_relief": 0,
        "child_relief_normal": 0,
        "child_relief_disabled": 0,
        "child_relief_autism_oku": 0,
        "life_insurance": 0,
        "children_life_medical_insurance": 0,
        "medical_insurance": 0,
        "child_education_medical_insurance": 0,
        "education_fees_self": 0,
        "sspn": 0,
        "childcare_fees": 0,
        "childcare_fees_extended": 0,
        "lifestyle_expenses": 0,
        "prs_contribution": 0,
        "serious_illness_expenses": 0,
        "parents_medical": 0,
        "housing_loan_interest_500k": 0,
        "housing_loan_interest_750k": 0,
        "disability_self": 0,
        "disability_spouse": 0,
        "socso_employee": 0,
        "epf_employee": 0,
        "voluntary_epf_itopup": 0,
        "domestic_tourism": 0,
        "vaccine_relief": 0,
        "food_waste_composting_machine": 0,
        "annual_zakat": 0,
    }
    defaults.update(kwargs)
    doc = frappe.get_doc(defaults)
    return doc


# ---------------------------------------------------------------------------
# AC1: children_life_medical_insurance field and RM3,000 combined life pool
# ---------------------------------------------------------------------------

class TestChildLifeInsuranceField(FrappeTestCase):
    """AC1: children_life_medical_insurance sub-field with RM3,000 aggregate in life pool."""

    def test_children_life_medical_insurance_in_ya2026_caps(self):
        """children_life_medical_insurance must be in YA2026 cap table with RM3,000 cap."""
        self.assertIn("children_life_medical_insurance", _CAPS_YA2026)
        self.assertEqual(_CAPS_YA2026["children_life_medical_insurance"], 3_000)

    def test_children_life_medical_insurance_not_in_default_caps(self):
        """children_life_medical_insurance is not in pre-YA2026 default caps."""
        self.assertNotIn("children_life_medical_insurance", _CAPS_DEFAULT)

    def test_children_life_medical_insurance_in_relief_fields(self):
        """children_life_medical_insurance must be counted in total_reliefs."""
        self.assertIn("children_life_medical_insurance", _RELIEF_FIELDS)

    def test_children_life_insurance_contributes_to_total(self):
        """children_life_medical_insurance is included in total_reliefs sum."""
        doc = _make_tp1_doc(
            tax_year=2026,
            children_life_medical_insurance=2000,
        )
        with patch.object(EmployeeTP1Relief, "_enforce_unique_per_year"):
            with patch.object(EmployeeTP1Relief, "_apply_caps"):
                with patch.object(EmployeeTP1Relief, "_apply_medical_education_combined_cap"):
                    EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
                    EmployeeTP1Relief._apply_life_voluntary_epf_combined_cap(doc)
                    EmployeeTP1Relief._calculate_total(doc)
        self.assertIn(2000, [doc.total_reliefs, doc.total_reliefs - 9000])

    def test_children_life_insurance_capped_individually_at_3000(self):
        """children_life_medical_insurance declared > RM3,000 is silently capped."""
        doc = _make_tp1_doc(tax_year=2026, children_life_medical_insurance=5000)
        with patch.object(EmployeeTP1Relief, "_enforce_unique_per_year"):
            with patch.object(EmployeeTP1Relief, "_apply_life_voluntary_epf_combined_cap"):
                with patch.object(EmployeeTP1Relief, "_apply_medical_education_combined_cap"):
                    with patch.object(frappe, "msgprint"):
                        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
                        EmployeeTP1Relief._apply_caps(doc)
                        EmployeeTP1Relief._calculate_total(doc)
        self.assertEqual(doc.children_life_medical_insurance, 3000)


class TestChildLifeInsuranceCombinedPool(FrappeTestCase):
    """AC1+AC4: life_insurance + children_life_medical_insurance combined RM3,000 cap."""

    def test_combined_life_cap_when_both_fields_at_max(self):
        """life_insurance=3,000 + children_life=3,000 combined must not exceed RM3,000."""
        doc = _make_tp1_doc(
            tax_year=2026,
            life_insurance=3000,
            children_life_medical_insurance=3000,
        )
        with patch.object(EmployeeTP1Relief, "_enforce_unique_per_year"):
            with patch.object(EmployeeTP1Relief, "_apply_medical_education_combined_cap"):
                with patch.object(frappe, "msgprint"):
                    EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
                    EmployeeTP1Relief._apply_caps(doc)
                    EmployeeTP1Relief._apply_life_voluntary_epf_combined_cap(doc)
                    EmployeeTP1Relief._calculate_total(doc)
        # Combined life + children_life must be <= 3,000 after trimming
        combined = (doc.life_insurance or 0) + (doc.children_life_medical_insurance or 0)
        self.assertLessEqual(combined, _LIFE_VOLUNTARY_EPF_COMBINED_CAP)

    def test_combined_life_cap_trims_children_before_life(self):
        """Excess trimming prioritises children_life_medical over life_insurance."""
        doc = _make_tp1_doc(
            tax_year=2026,
            life_insurance=2000,
            children_life_medical_insurance=2000,
        )
        with patch.object(EmployeeTP1Relief, "_enforce_unique_per_year"):
            with patch.object(EmployeeTP1Relief, "_apply_medical_education_combined_cap"):
                with patch.object(frappe, "msgprint"):
                    EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
                    EmployeeTP1Relief._apply_caps(doc)
                    EmployeeTP1Relief._apply_life_voluntary_epf_combined_cap(doc)
        # life_insurance should be preserved, children trimmed to fit
        self.assertEqual(float(doc.life_insurance or 0), 2000.0)
        self.assertEqual(float(doc.children_life_medical_insurance or 0), 1000.0)

    def test_children_life_alone_within_cap(self):
        """children_life_medical_insurance <= RM3,000 with no life_insurance is accepted."""
        doc = _make_tp1_doc(tax_year=2026, children_life_medical_insurance=2500)
        with patch.object(EmployeeTP1Relief, "_enforce_unique_per_year"):
            with patch.object(EmployeeTP1Relief, "_apply_medical_education_combined_cap"):
                with patch.object(frappe, "msgprint"):
                    EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
                    EmployeeTP1Relief._apply_caps(doc)
                    EmployeeTP1Relief._apply_life_voluntary_epf_combined_cap(doc)
        self.assertEqual(float(doc.children_life_medical_insurance or 0), 2500.0)


# ---------------------------------------------------------------------------
# AC2: child_education_medical_insurance field with RM4,000 combined medical pool
# ---------------------------------------------------------------------------

class TestChildEducationMedicalInsuranceField(FrappeTestCase):
    """AC2: child_education_medical_insurance sub-field with RM4,000 combined medical pool."""

    def test_child_education_medical_in_ya2026_caps(self):
        """child_education_medical_insurance must be in YA2026 cap table."""
        self.assertIn("child_education_medical_insurance", _CAPS_YA2026)
        self.assertEqual(_CAPS_YA2026["child_education_medical_insurance"], 4_000)

    def test_child_education_medical_not_in_default_caps(self):
        """child_education_medical_insurance is not available before YA2026."""
        self.assertNotIn("child_education_medical_insurance", _CAPS_DEFAULT)

    def test_child_education_medical_in_relief_fields(self):
        """child_education_medical_insurance contributes to total_reliefs."""
        self.assertIn("child_education_medical_insurance", _RELIEF_FIELDS)

    def test_combined_cap_constant_is_4000(self):
        """_MEDICAL_EDUCATION_COMBINED_CAP must be RM4,000."""
        self.assertEqual(_MEDICAL_EDUCATION_COMBINED_CAP, 4_000)

    def test_child_education_medical_alone_accepted_up_to_4000(self):
        """child_education_medical_insurance up to RM4,000 with no medical_insurance is accepted."""
        doc = _make_tp1_doc(tax_year=2026, child_education_medical_insurance=4000)
        with patch.object(EmployeeTP1Relief, "_enforce_unique_per_year"):
            with patch.object(EmployeeTP1Relief, "_apply_life_voluntary_epf_combined_cap"):
                with patch.object(frappe, "msgprint"):
                    EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
                    EmployeeTP1Relief._apply_caps(doc)
                    EmployeeTP1Relief._apply_medical_education_combined_cap(doc)
        self.assertEqual(float(doc.child_education_medical_insurance or 0), 4000.0)

    def test_child_education_medical_contributes_to_total_reliefs(self):
        """child_education_medical_insurance is summed into total_reliefs."""
        doc = _make_tp1_doc(tax_year=2026, child_education_medical_insurance=1500)
        with patch.object(EmployeeTP1Relief, "_enforce_unique_per_year"):
            with patch.object(EmployeeTP1Relief, "_apply_life_voluntary_epf_combined_cap"):
                with patch.object(EmployeeTP1Relief, "_apply_medical_education_combined_cap"):
                    EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
                    EmployeeTP1Relief._apply_caps(doc)
                    EmployeeTP1Relief._calculate_total(doc)
        self.assertAlmostEqual(doc.total_reliefs, 9000 + 1500)


# ---------------------------------------------------------------------------
# AC4: Combined (medical_insurance + child_education_medical_insurance) <= RM4,000
# ---------------------------------------------------------------------------

class TestMedicalInsuranceCombinedCap(FrappeTestCase):
    """AC4: medical_insurance + child_education_medical_insurance <= RM4,000 aggregate."""

    def test_combined_within_cap_no_trimming(self):
        """medical=2000 + child_medical=1500 = 3500 <= RM4,000: no trimming needed."""
        doc = _make_tp1_doc(
            tax_year=2026,
            medical_insurance=2000,
            child_education_medical_insurance=1500,
        )
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._apply_medical_education_combined_cap(doc)
        self.assertEqual(float(doc.medical_insurance or 0), 2000.0)
        self.assertEqual(float(doc.child_education_medical_insurance or 0), 1500.0)

    def test_combined_exceeds_cap_trims_child_first(self):
        """medical=3000 + child_medical=2000 = 5000 > RM4,000: child trimmed to 1000."""
        doc = _make_tp1_doc(
            tax_year=2026,
            medical_insurance=3000,
            child_education_medical_insurance=2000,
        )
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._apply_medical_education_combined_cap(doc)
        self.assertEqual(float(doc.medical_insurance or 0), 3000.0)
        self.assertEqual(float(doc.child_education_medical_insurance or 0), 1000.0)

    def test_combined_both_at_max_trimmed_to_4000(self):
        """medical=3000 + child=4000 = 7000 > RM4,000: child trimmed to 1000."""
        doc = _make_tp1_doc(
            tax_year=2026,
            medical_insurance=3000,
            child_education_medical_insurance=4000,
        )
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._apply_medical_education_combined_cap(doc)
        combined = (doc.medical_insurance or 0) + (doc.child_education_medical_insurance or 0)
        self.assertLessEqual(combined, _MEDICAL_EDUCATION_COMBINED_CAP)
        self.assertEqual(float(doc.medical_insurance or 0), 3000.0)

    def test_combined_exactly_at_cap_no_trimming(self):
        """medical=2500 + child=1500 = 4000 == RM4,000: no trimming."""
        doc = _make_tp1_doc(
            tax_year=2026,
            medical_insurance=2500,
            child_education_medical_insurance=1500,
        )
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._apply_medical_education_combined_cap(doc)
        self.assertEqual(float(doc.medical_insurance or 0), 2500.0)
        self.assertEqual(float(doc.child_education_medical_insurance or 0), 1500.0)

    def test_medical_only_no_trimming(self):
        """medical=3000 alone <= RM4,000: no trimming regardless of child field being 0."""
        doc = _make_tp1_doc(tax_year=2026, medical_insurance=3000, child_education_medical_insurance=0)
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._apply_medical_education_combined_cap(doc)
        self.assertEqual(float(doc.medical_insurance or 0), 3000.0)

    def test_pre_2026_combined_cap_not_applied(self):
        """For tax_year < 2026 the combined cap method is a no-op."""
        doc = _make_tp1_doc(
            tax_year=2025,
            medical_insurance=3000,
            child_education_medical_insurance=0,  # already zeroed by pre-2026 guard
        )
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._apply_medical_education_combined_cap(doc)
        # Method exits early — medical_insurance untouched
        self.assertEqual(float(doc.medical_insurance or 0), 3000.0)


# ---------------------------------------------------------------------------
# AC3: PCB computation uses child insurance premiums to reduce chargeable income
# ---------------------------------------------------------------------------

class TestChildInsurancePcbReduction(FrappeTestCase):
    """AC3: PCB reduces correctly when child insurance premiums are in tp1_total_reliefs."""

    def test_child_education_medical_reduces_pcb(self):
        """Declaring child_education_medical_insurance lowers annual PCB."""
        annual_income = 96_000
        pcb_base = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        pcb_with_child_medical = calculate_pcb(
            annual_income, resident=True, tp1_total_reliefs=2_000
        )
        self.assertGreater(pcb_base, pcb_with_child_medical)

    def test_child_life_insurance_reduces_pcb(self):
        """Declaring children_life_medical_insurance lowers annual PCB."""
        annual_income = 84_000
        pcb_base = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        pcb_with_child_life = calculate_pcb(
            annual_income, resident=True, tp1_total_reliefs=2_000
        )
        self.assertGreater(pcb_base, pcb_with_child_life)

    def test_combined_child_insurances_reduce_pcb_more_than_one(self):
        """Both child insurance premiums together reduce PCB more than either alone."""
        annual_income = 108_000
        pcb_life_only = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=2_000)
        pcb_both = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=4_000)
        self.assertGreater(pcb_life_only, pcb_both)

    def test_total_reliefs_includes_child_insurance_fields(self):
        """total_reliefs sums both child insurance fields correctly."""
        doc = _make_tp1_doc(
            tax_year=2026,
            children_life_medical_insurance=2000,
            child_education_medical_insurance=1500,
        )
        with patch.object(EmployeeTP1Relief, "_enforce_unique_per_year"):
            with patch.object(EmployeeTP1Relief, "_apply_life_voluntary_epf_combined_cap"):
                with patch.object(EmployeeTP1Relief, "_apply_medical_education_combined_cap"):
                    with patch.object(frappe, "msgprint"):
                        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
                        EmployeeTP1Relief._apply_caps(doc)
                        EmployeeTP1Relief._calculate_total(doc)
        expected_total = 9000 + 2000 + 1500  # self_relief + children_life + child_edu_medical
        self.assertAlmostEqual(doc.total_reliefs, expected_total)


# ---------------------------------------------------------------------------
# AC5: Pre-YA2026 records have child insurance fields zeroed (year gating)
# ---------------------------------------------------------------------------

class TestYearGating(FrappeTestCase):
    """AC5: Child insurance fields are year-gated — zeroed for pre-YA2026 records."""

    def test_child_education_medical_zeroed_for_ya2025(self):
        """child_education_medical_insurance is cleared when tax_year=2025."""
        doc = _make_tp1_doc(tax_year=2025, child_education_medical_insurance=2000)
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(float(doc.child_education_medical_insurance or 0), 0.0)

    def test_child_education_medical_zeroed_for_ya2024(self):
        """child_education_medical_insurance is cleared when tax_year=2024."""
        doc = _make_tp1_doc(tax_year=2024, child_education_medical_insurance=1500)
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(float(doc.child_education_medical_insurance or 0), 0.0)

    def test_children_life_medical_zeroed_for_ya2025(self):
        """children_life_medical_insurance is cleared when tax_year=2025."""
        doc = _make_tp1_doc(tax_year=2025, children_life_medical_insurance=1500)
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(float(doc.children_life_medical_insurance or 0), 0.0)

    def test_child_fields_preserved_for_ya2026(self):
        """Child insurance fields are NOT zeroed for tax_year=2026."""
        doc = _make_tp1_doc(
            tax_year=2026,
            children_life_medical_insurance=2000,
            child_education_medical_insurance=1500,
        )
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(float(doc.children_life_medical_insurance or 0), 2000.0)
        self.assertEqual(float(doc.child_education_medical_insurance or 0), 1500.0)

    def test_child_fields_preserved_for_ya2027(self):
        """Child insurance fields are available for tax_year >= 2026."""
        doc = _make_tp1_doc(
            tax_year=2027,
            children_life_medical_insurance=1000,
            child_education_medical_insurance=500,
        )
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(float(doc.children_life_medical_insurance or 0), 1000.0)
        self.assertEqual(float(doc.child_education_medical_insurance or 0), 500.0)

    def test_pre_2026_caps_do_not_include_child_fields(self):
        """_get_caps_for_year(2025) does not include child insurance fields."""
        caps_2025 = _get_caps_for_year(2025)
        self.assertNotIn("children_life_medical_insurance", caps_2025)
        self.assertNotIn("child_education_medical_insurance", caps_2025)

    def test_ya2026_caps_include_child_fields(self):
        """_get_caps_for_year(2026) includes both child insurance fields."""
        caps_2026 = _get_caps_for_year(2026)
        self.assertIn("children_life_medical_insurance", caps_2026)
        self.assertIn("child_education_medical_insurance", caps_2026)


# ---------------------------------------------------------------------------
# Edge cases and cross-field interactions
# ---------------------------------------------------------------------------

class TestChildInsuranceEdgeCases(FrappeTestCase):
    """Edge cases: zero amounts, cap boundaries, cross-field interaction."""

    def test_zero_child_fields_no_trimming(self):
        """Zero child insurance fields — no trimming, no msgprint."""
        doc = _make_tp1_doc(
            tax_year=2026,
            medical_insurance=3000,
            child_education_medical_insurance=0,
        )
        with patch.object(frappe, "msgprint") as mock_mp:
            EmployeeTP1Relief._apply_medical_education_combined_cap(doc)
        mock_mp.assert_not_called()

    def test_child_education_medical_with_zero_medical(self):
        """child_education_medical_insurance=3000 with medical=0 is within RM4,000 cap."""
        doc = _make_tp1_doc(tax_year=2026, medical_insurance=0, child_education_medical_insurance=3000)
        with patch.object(frappe, "msgprint"):
            EmployeeTP1Relief._apply_medical_education_combined_cap(doc)
        self.assertEqual(float(doc.child_education_medical_insurance or 0), 3000.0)

    def test_child_education_medical_trimmed_by_individual_cap(self):
        """child_education_medical_insurance > RM4,000 trimmed by individual _apply_caps."""
        doc = _make_tp1_doc(tax_year=2026, child_education_medical_insurance=5000)
        with patch.object(EmployeeTP1Relief, "_enforce_unique_per_year"):
            with patch.object(EmployeeTP1Relief, "_apply_life_voluntary_epf_combined_cap"):
                with patch.object(EmployeeTP1Relief, "_apply_medical_education_combined_cap"):
                    with patch.object(frappe, "msgprint"):
                        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
                        EmployeeTP1Relief._apply_caps(doc)
        # Individual cap of 4,000 applied first
        self.assertEqual(float(doc.child_education_medical_insurance or 0), 4000.0)

    def test_two_caps_applied_sequentially(self):
        """Life combined cap and medical combined cap are independent — both applied."""
        doc = _make_tp1_doc(
            tax_year=2026,
            life_insurance=2000,
            children_life_medical_insurance=2000,  # excess by 1000 → trimmed
            medical_insurance=3000,
            child_education_medical_insurance=2000,  # excess by 1000 → trimmed
        )
        with patch.object(EmployeeTP1Relief, "_enforce_unique_per_year"):
            with patch.object(frappe, "msgprint"):
                EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
                EmployeeTP1Relief._apply_caps(doc)
                EmployeeTP1Relief._apply_life_voluntary_epf_combined_cap(doc)
                EmployeeTP1Relief._apply_medical_education_combined_cap(doc)

        life_combined = (doc.life_insurance or 0) + (doc.children_life_medical_insurance or 0)
        medical_combined = (doc.medical_insurance or 0) + (doc.child_education_medical_insurance or 0)
        self.assertLessEqual(life_combined, 3_000)
        self.assertLessEqual(medical_combined, 4_000)
