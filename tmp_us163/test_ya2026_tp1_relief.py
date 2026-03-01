"""Tests for US-163: TP1(1/2026) Relief Categories and PCB Engine for YA2026.

Covers TP1(1/2026) Budget 2026 changes effective from Assessment Year 2026:
  1. Children Life/Medical Insurance — new sub-field under insurance relief,
     shares combined RM 3,000 cap with life_insurance (YA2026)
  2. Childcare Fees Extended — ages 6-12 Ministry of Education after-school
     care programmes, RM 3,000 cap (YA2026)
  3. Autism/Learning Disability Child Relief — ceiling raised from RM 6,000
     to RM 10,000 (new field child_relief_autism_oku, YA2026)
  4. Domestic Tourism & Cultural Attraction — RM 1,000 relief,
     time-bounded YA2026-2027, expiry guard rejects claims after 2027
  5. Vaccine Relief — any NPRA-approved vaccine, no hardcoded list, no cap
  6. PCB calculation uses updated YA2026 relief totals from January 2026
  7. Old YA2025 TP1 records are unaffected by YA2026 caps
  8. Pre-YA2026 fields are cleared when tax_year < 2026
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb
from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief import (
    EmployeeTP1Relief,
    _CAPS_DEFAULT,
    _CAPS_YA2025,
    _CAPS_YA2026,
    _get_caps_for_year,
    _RELIEF_FIELDS,
    _DOMESTIC_TOURISM_EXPIRY_YEAR,
    _YA2026_EFFECTIVE_YEAR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_doc(**kwargs):
    """Build a mock TP1 doc with default zero-valued YA2026 fields."""
    defaults = {
        "employee": "TEST-EMP-YA2026",
        "tax_year": 2026,
        "name": "TP1-TEST-EMP-YA2026-2026",
        "self_relief": 9000,
        "spouse_relief": 0,
        "child_relief_normal": 0,
        "child_relief_disabled": 0,
        "child_relief_autism_oku": 0,
        "life_insurance": 0,
        "children_life_medical_insurance": 0,
        "medical_insurance": 0,
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
        "spa_date": None,
        "disability_self": 0,
        "disability_spouse": 0,
        "socso_employee": 0,
        "epf_employee": 0,
        "voluntary_epf_itopup": 0,
        "annual_zakat": 0,
        "domestic_tourism": 0,
        "vaccine_relief": 0,
        "total_reliefs": 0,
    }
    defaults.update(kwargs)

    doc = MagicMock(spec=EmployeeTP1Relief)
    for k, v in defaults.items():
        setattr(doc, k, v)
    doc.get = lambda f, default=None: getattr(doc, f, default)
    doc.set = lambda f, v: setattr(doc, f, v)
    doc.meta = MagicMock()
    doc.meta.get_label = lambda f: f.replace("_", " ").title()
    return doc


# ---------------------------------------------------------------------------
# 1. YA2026 cap table structure tests
# ---------------------------------------------------------------------------

class TestYA2026CapTable(FrappeTestCase):
    """Verify _CAPS_YA2026 contains all new YA2026 relief fields."""

    def test_ya2026_caps_include_ya2025_caps(self):
        """YA2026 caps inherit all YA2025 caps."""
        for field, cap in _CAPS_YA2025.items():
            self.assertIn(field, _CAPS_YA2026,
                          f"YA2026 caps should include YA2025 field: {field}")

    def test_ya2026_caps_children_life_insurance(self):
        """children_life_medical_insurance cap is RM 3,000 in YA2026."""
        self.assertEqual(_CAPS_YA2026["children_life_medical_insurance"], 3_000)

    def test_ya2026_caps_childcare_extended(self):
        """childcare_fees_extended cap is RM 3,000 in YA2026."""
        self.assertEqual(_CAPS_YA2026["childcare_fees_extended"], 3_000)

    def test_ya2026_caps_domestic_tourism(self):
        """domestic_tourism cap is RM 1,000 in YA2026."""
        self.assertEqual(_CAPS_YA2026["domestic_tourism"], 1_000)

    def test_ya2026_caps_autism_child_relief(self):
        """child_relief_autism_oku cap is RM 10,000 in YA2026 (raised from RM 6,000)."""
        self.assertEqual(_CAPS_YA2026["child_relief_autism_oku"], 10_000)

    def test_ya2026_caps_vaccine_relief_not_capped(self):
        """vaccine_relief has NO entry in YA2026 caps (uncapped by LHDN)."""
        self.assertNotIn("vaccine_relief", _CAPS_YA2026,
                         "vaccine_relief should not be in caps table — it is uncapped")

    def test_get_caps_for_2026_returns_ya2026(self):
        """_get_caps_for_year(2026) returns YA2026 caps."""
        caps = _get_caps_for_year(2026)
        self.assertIn("children_life_medical_insurance", caps)
        self.assertIn("child_relief_autism_oku", caps)
        self.assertIn("domestic_tourism", caps)

    def test_get_caps_for_2025_returns_ya2025_not_ya2026(self):
        """_get_caps_for_year(2025) returns YA2025 caps, NOT YA2026 fields."""
        caps = _get_caps_for_year(2025)
        self.assertNotIn("children_life_medical_insurance", caps)
        self.assertNotIn("child_relief_autism_oku", caps)
        self.assertNotIn("domestic_tourism", caps)

    def test_get_caps_for_2024_returns_default(self):
        """_get_caps_for_year(2024) returns default caps without YA2025/YA2026 fields."""
        caps = _get_caps_for_year(2024)
        self.assertNotIn("housing_loan_interest_500k", caps)
        self.assertNotIn("children_life_medical_insurance", caps)
        self.assertEqual(caps["disability_self"], 6_000)

    def test_get_caps_for_future_year_returns_ya2026(self):
        """_get_caps_for_year(2030) falls back to YA2026 caps."""
        caps = _get_caps_for_year(2030)
        self.assertIn("child_relief_autism_oku", caps)

    def test_domestic_tourism_expiry_year_constant(self):
        """_DOMESTIC_TOURISM_EXPIRY_YEAR is 2027."""
        self.assertEqual(_DOMESTIC_TOURISM_EXPIRY_YEAR, 2027)

    def test_ya2026_effective_year_constant(self):
        """_YA2026_EFFECTIVE_YEAR is 2026."""
        self.assertEqual(_YA2026_EFFECTIVE_YEAR, 2026)


# ---------------------------------------------------------------------------
# 2. New field presence in _RELIEF_FIELDS
# ---------------------------------------------------------------------------

class TestYA2026ReliefFields(FrappeTestCase):
    """Verify new YA2026 fields are in _RELIEF_FIELDS."""

    def test_children_life_insurance_in_relief_fields(self):
        """children_life_medical_insurance is in _RELIEF_FIELDS for total calculation."""
        self.assertIn("children_life_medical_insurance", _RELIEF_FIELDS)

    def test_childcare_fees_extended_in_relief_fields(self):
        """childcare_fees_extended is in _RELIEF_FIELDS."""
        self.assertIn("childcare_fees_extended", _RELIEF_FIELDS)

    def test_domestic_tourism_in_relief_fields(self):
        """domestic_tourism is in _RELIEF_FIELDS."""
        self.assertIn("domestic_tourism", _RELIEF_FIELDS)

    def test_vaccine_relief_in_relief_fields(self):
        """vaccine_relief is in _RELIEF_FIELDS (included in total, no LHDN cap)."""
        self.assertIn("vaccine_relief", _RELIEF_FIELDS)

    def test_child_relief_autism_oku_in_relief_fields(self):
        """child_relief_autism_oku is in _RELIEF_FIELDS."""
        self.assertIn("child_relief_autism_oku", _RELIEF_FIELDS)

    def test_annual_zakat_not_in_relief_fields(self):
        """annual_zakat remains excluded from _RELIEF_FIELDS (it's a tax rebate)."""
        self.assertNotIn("annual_zakat", _RELIEF_FIELDS)


# ---------------------------------------------------------------------------
# 3. Autism/learning disability child relief (RM 10,000 cap, YA2026)
# ---------------------------------------------------------------------------

class TestAutismChildRelief(FrappeTestCase):
    """child_relief_autism_oku field caps and PCB impact."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_autism_relief_capped_at_10000_ya2026(self, mock_frappe):
        """child_relief_autism_oku is capped at RM 10,000 for YA2026."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=15_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.child_relief_autism_oku, 10_000)
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_autism_relief_within_cap_unchanged(self, mock_frappe):
        """child_relief_autism_oku within RM 10,000 is not modified."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, child_relief_autism_oku=8_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.child_relief_autism_oku, 8_000)

    def test_autism_relief_reduces_pcb(self):
        """Autism child relief (as part of tp1_total_reliefs) reduces PCB for YA2026."""
        annual_income = 80_000
        pcb_no_autism = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        pcb_with_autism = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=10_000)
        self.assertGreater(pcb_no_autism, pcb_with_autism,
                           "PCB should decrease when autism child relief is declared")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_autism_relief_not_in_ya2025_caps(self, mock_frappe):
        """child_relief_autism_oku has NO cap for YA2025 (field not available pre-YA2026)."""
        mock_frappe.db.get_value.return_value = None
        # For YA2025, the field should be cleared by _zero_ya2026_fields_for_pre_2026
        doc = _make_mock_doc(tax_year=2025, child_relief_autism_oku=8_000)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.child_relief_autism_oku, 0,
                         "child_relief_autism_oku should be cleared for YA2025")


# ---------------------------------------------------------------------------
# 4. Domestic tourism expiry guard
# ---------------------------------------------------------------------------

class TestDomesticTourismExpiry(FrappeTestCase):
    """domestic_tourism field is time-bounded (YA2026-2027 only)."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_domestic_tourism_allowed_ya2026(self, mock_frappe):
        """domestic_tourism relief is allowed for YA2026."""
        doc = _make_mock_doc(tax_year=2026, domestic_tourism=800)
        # Should not raise
        EmployeeTP1Relief._validate_domestic_tourism_expiry(doc)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_domestic_tourism_allowed_ya2027(self, mock_frappe):
        """domestic_tourism relief is allowed for YA2027 (last valid year)."""
        doc = _make_mock_doc(tax_year=2027, domestic_tourism=1_000)
        # Should not raise
        EmployeeTP1Relief._validate_domestic_tourism_expiry(doc)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_domestic_tourism_rejected_ya2028(self, mock_frappe):
        """domestic_tourism relief is rejected for YA2028 (expired)."""
        mock_frappe.throw = frappe.throw
        doc = _make_mock_doc(tax_year=2028, domestic_tourism=500)
        with self.assertRaises(Exception):
            EmployeeTP1Relief._validate_domestic_tourism_expiry(doc)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_domestic_tourism_zero_skips_expiry_check(self, mock_frappe):
        """Zero domestic_tourism skips expiry guard even for years after 2027."""
        doc = _make_mock_doc(tax_year=2030, domestic_tourism=0)
        # Should not raise — no amount to reject
        EmployeeTP1Relief._validate_domestic_tourism_expiry(doc)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_domestic_tourism_capped_at_1000_ya2026(self, mock_frappe):
        """domestic_tourism is capped at RM 1,000 for YA2026."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, domestic_tourism=2_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.domestic_tourism, 1_000)


# ---------------------------------------------------------------------------
# 5. Vaccine relief (no hardcoded list, no cap)
# ---------------------------------------------------------------------------

class TestVaccineRelief(FrappeTestCase):
    """vaccine_relief field: NPRA-approved vaccines, no cap."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_vaccine_relief_not_capped(self, mock_frappe):
        """vaccine_relief has no cap — large amounts are not truncated."""
        mock_frappe.db.get_value.return_value = None
        # Vaccine relief is not in caps table, so _apply_caps should not touch it
        doc = _make_mock_doc(tax_year=2026, vaccine_relief=5_000)
        EmployeeTP1Relief._apply_caps(doc)
        # Since vaccine_relief is not in caps table, the value should remain unchanged
        self.assertEqual(doc.vaccine_relief, 5_000,
                         "vaccine_relief should not be capped (no LHDN cap)")
        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_vaccine_relief_cleared_for_pre_ya2026(self, mock_frappe):
        """vaccine_relief is cleared for pre-YA2026 tax years."""
        doc = _make_mock_doc(tax_year=2025, vaccine_relief=2_000)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.vaccine_relief, 0)
        mock_frappe.msgprint.assert_called()

    def test_vaccine_relief_reduces_pcb_ya2026(self):
        """Vaccine relief (as part of tp1_total_reliefs) reduces PCB for YA2026 payroll."""
        annual_income = 70_000
        pcb_no_vaccine = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        pcb_with_vaccine = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=3_000)
        self.assertGreater(pcb_no_vaccine, pcb_with_vaccine,
                           "PCB should decrease when vaccine relief is declared")


# ---------------------------------------------------------------------------
# 6. Children life/medical insurance — combined insurance pool
# ---------------------------------------------------------------------------

class TestChildrenLifeInsuranceCombinedCap(FrappeTestCase):
    """children_life_medical_insurance shares RM 3,000 combined cap with life_insurance."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_children_life_capped_at_3000_ya2026(self, mock_frappe):
        """children_life_medical_insurance is capped at RM 3,000 for YA2026."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, children_life_medical_insurance=5_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.children_life_medical_insurance, 3_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_combined_life_children_voluntary_epf_capped_at_3000(self, mock_frappe):
        """life_insurance + children_life_medical_insurance + voluntary_epf combined <= RM 3,000."""
        doc = _make_mock_doc(
            tax_year=2026,
            life_insurance=1_500,
            children_life_medical_insurance=1_000,
            voluntary_epf_itopup=1_000,  # total = 3500, exceeds 3000
        )
        EmployeeTP1Relief._apply_life_voluntary_epf_combined_cap(doc)
        combined = (
            float(doc.life_insurance or 0)
            + float(doc.get("children_life_medical_insurance") or 0)
            + float(doc.voluntary_epf_itopup or 0)
        )
        self.assertLessEqual(combined, 3_000,
                             "Combined life + children_life + voluntary EPF must not exceed RM 3,000")
        mock_frappe.msgprint.assert_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_voluntary_epf_trimmed_first_in_combined_cap(self, mock_frappe):
        """When combined exceeds RM 3,000, voluntary EPF is trimmed first."""
        doc = _make_mock_doc(
            tax_year=2026,
            life_insurance=2_000,
            children_life_medical_insurance=500,
            voluntary_epf_itopup=1_000,  # total = 3500, excess = 500
        )
        EmployeeTP1Relief._apply_life_voluntary_epf_combined_cap(doc)
        # voluntary_epf should be trimmed by 500 (from 1000 to 500)
        self.assertEqual(doc.voluntary_epf_itopup, 500.0)
        # life_insurance and children_life unchanged (excess fully absorbed by voluntary)
        self.assertEqual(doc.life_insurance, 2_000)
        self.assertEqual(doc.get("children_life_medical_insurance"), 500)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_children_life_trimmed_second_when_voluntary_exhausted(self, mock_frappe):
        """children_life_medical_insurance is trimmed after voluntary EPF is exhausted."""
        doc = _make_mock_doc(
            tax_year=2026,
            life_insurance=2_000,
            children_life_medical_insurance=1_500,
            voluntary_epf_itopup=500,  # total = 4000, excess = 1000
        )
        EmployeeTP1Relief._apply_life_voluntary_epf_combined_cap(doc)
        # voluntary_epf trimmed to 0 (absorbs 500 of the 1000 excess)
        self.assertEqual(doc.voluntary_epf_itopup, 0.0)
        # children_life trimmed by remaining 500 (from 1500 to 1000)
        self.assertEqual(doc.get("children_life_medical_insurance"), 1_000.0)
        # life_insurance unchanged
        self.assertEqual(doc.life_insurance, 2_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_children_life_cleared_for_pre_ya2026(self, mock_frappe):
        """children_life_medical_insurance is cleared for pre-YA2026 records."""
        doc = _make_mock_doc(tax_year=2025, children_life_medical_insurance=2_000)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.get("children_life_medical_insurance"), 0)


# ---------------------------------------------------------------------------
# 7. Childcare fees extended (ages 6-12, YA2026)
# ---------------------------------------------------------------------------

class TestChildcareFeesExtended(FrappeTestCase):
    """childcare_fees_extended field for after-school care ages 6-12."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_childcare_extended_capped_at_3000_ya2026(self, mock_frappe):
        """childcare_fees_extended is capped at RM 3,000 for YA2026."""
        mock_frappe.db.get_value.return_value = None
        doc = _make_mock_doc(tax_year=2026, childcare_fees_extended=4_000)
        EmployeeTP1Relief._apply_caps(doc)
        self.assertEqual(doc.childcare_fees_extended, 3_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_childcare_extended_cleared_for_pre_ya2026(self, mock_frappe):
        """childcare_fees_extended is cleared for pre-YA2026 records."""
        doc = _make_mock_doc(tax_year=2025, childcare_fees_extended=2_000)
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.childcare_fees_extended, 0)

    def test_childcare_extended_reduces_pcb(self):
        """Childcare extended (as tp1_total_reliefs) reduces PCB for YA2026 payroll."""
        annual_income = 65_000
        pcb_no_childcare = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        pcb_with_childcare = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=3_000)
        self.assertGreater(pcb_no_childcare, pcb_with_childcare)


# ---------------------------------------------------------------------------
# 8. PCB calculation uses YA2026 total reliefs (January 2026 payroll)
# ---------------------------------------------------------------------------

class TestYA2026PCBCalculation(FrappeTestCase):
    """PCB engine correctly incorporates YA2026 relief totals."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_total_reliefs_includes_ya2026_fields(self, mock_frappe):
        """total_reliefs sums all YA2026 fields including new ones."""
        doc = _make_mock_doc(
            tax_year=2026,
            self_relief=9_000,
            child_relief_autism_oku=8_000,
            children_life_medical_insurance=2_000,
            childcare_fees_extended=1_500,
            domestic_tourism=800,
            vaccine_relief=500,
        )
        EmployeeTP1Relief._calculate_total(doc)
        # 9000 + 8000 + 2000 + 1500 + 800 + 500 = 21800
        self.assertEqual(doc.total_reliefs, 21_800)

    def test_pcb_with_ya2026_reliefs_lower_than_without(self):
        """PCB for January 2026 payroll is lower when YA2026 reliefs are declared."""
        annual_income = 90_000
        # All new YA2026 reliefs combined: 8000 + 2000 + 1500 + 800 + 500 = 12800
        ya2026_total_new_reliefs = 12_800
        pcb_without = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        pcb_with_ya2026 = calculate_pcb(annual_income, resident=True,
                                         tp1_total_reliefs=ya2026_total_new_reliefs)
        self.assertGreater(pcb_without, pcb_with_ya2026,
                           "PCB must be lower when YA2026 TP1 reliefs are applied")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2025_record_unaffected_by_ya2026_fields(self, mock_frappe):
        """YA2025 TP1 record: _zero_ya2026_fields_for_pre_2026 clears all YA2026 fields."""
        doc = _make_mock_doc(
            tax_year=2025,
            # Simulate someone erroneously entering YA2026 fields on a YA2025 record
            child_relief_autism_oku=10_000,
            children_life_medical_insurance=2_500,
            childcare_fees_extended=3_000,
            domestic_tourism=1_000,
            vaccine_relief=2_000,
        )
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.child_relief_autism_oku, 0,
                         "child_relief_autism_oku cleared for YA2025")
        self.assertEqual(doc.get("children_life_medical_insurance"), 0,
                         "children_life_medical_insurance cleared for YA2025")
        self.assertEqual(doc.childcare_fees_extended, 0,
                         "childcare_fees_extended cleared for YA2025")
        self.assertEqual(doc.domestic_tourism, 0,
                         "domestic_tourism cleared for YA2025")
        self.assertEqual(doc.vaccine_relief, 0,
                         "vaccine_relief cleared for YA2025")

    def test_ya2025_pcb_calculation_unchanged_by_ya2026_changes(self):
        """YA2025 PCB is unaffected by YA2026 cap changes (backward compatibility)."""
        # YA2025 employee with disability_self = 7000 (as per YA2025 caps)
        annual_income = 100_000
        tp1_2025 = 7_000  # disability_self at YA2025 cap
        pcb_ya2025 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=tp1_2025)
        # This should still work correctly — the PCB engine is not affected
        # by the cap table changes (caps are only enforced at DocType validation)
        self.assertGreater(pcb_ya2025, 0,
                           "YA2025 PCB should still calculate correctly")
        # Compare with no TP1: should be higher without reliefs
        pcb_no_tp1 = calculate_pcb(annual_income, resident=True, tp1_total_reliefs=0)
        self.assertGreater(pcb_no_tp1, pcb_ya2025)


# ---------------------------------------------------------------------------
# 9. Pre-YA2026 field guard (comprehensive)
# ---------------------------------------------------------------------------

class TestPreYA2026FieldGuard(FrappeTestCase):
    """_zero_ya2026_fields_for_pre_2026 clears YA2026 fields for earlier years."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_fields_not_cleared_for_ya2026(self, mock_frappe):
        """YA2026 fields are retained when tax_year >= 2026."""
        doc = _make_mock_doc(
            tax_year=2026,
            domestic_tourism=500,
            vaccine_relief=1_000,
            child_relief_autism_oku=5_000,
        )
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        # Values should be unchanged
        self.assertEqual(doc.domestic_tourism, 500)
        self.assertEqual(doc.vaccine_relief, 1_000)
        self.assertEqual(doc.child_relief_autism_oku, 5_000)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_tp1_relief.employee_tp1_relief.frappe")
    def test_ya2026_fields_cleared_for_ya2024(self, mock_frappe):
        """YA2026 fields are cleared for YA2024 records."""
        doc = _make_mock_doc(
            tax_year=2024,
            domestic_tourism=500,
            child_relief_autism_oku=5_000,
        )
        EmployeeTP1Relief._zero_ya2026_fields_for_pre_2026(doc)
        self.assertEqual(doc.domestic_tourism, 0)
        self.assertEqual(doc.child_relief_autism_oku, 0)
