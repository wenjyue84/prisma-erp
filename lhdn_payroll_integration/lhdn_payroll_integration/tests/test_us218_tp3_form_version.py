"""Tests for US-218: Process TP3(1/2026) Updated Form Format with Budget 2026 Relief Line Items.

Verifies:
- TP3 form version selection based on employee join year
- TP3(1/2026) field structure includes Budget 2026 relief line items
- Version-aware field listing (2024 = base only, 2025 = partial, 2026 = full)
- TP3 data validation (required fields, non-negative, relief limits)
- Relief value capping at statutory limits
- Total prior reliefs computation
- MTD carry-forward structure generation
- Full TP3 declaration processing pipeline
- Form metadata for UI rendering
"""

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.tp3_form_version_service import (
    TP3_FORM_VERSION_2024,
    TP3_FORM_VERSION_2025,
    TP3_FORM_VERSION_2026,
    SUPPORTED_TP3_VERSIONS,
    CURRENT_TP3_VERSION,
    TP3_BASE_FIELDS,
    TP3_2026_RELIEF_FIELDS,
    TP3_2026_RELIEF_LIMITS,
    get_tp3_form_version,
    get_tp3_form_version_for_employee,
    is_version_supported,
    get_tp3_fields_for_version,
    get_relief_fields_for_version,
    validate_tp3_data,
    cap_relief_values,
    compute_total_prior_reliefs,
    build_mtd_carry_forward,
    process_tp3_declaration,
    get_tp3_form_metadata,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_base_tp3_data(**overrides):
    """Create a minimal valid TP3 data dict."""
    data = {
        "prior_gross_income": 30000.0,
        "prior_epf_deducted": 3300.0,
        "prior_pcb_deducted": 1500.0,
        "prior_socso_deducted": 350.0,
        "prior_eis_deducted": 60.0,
        "prior_zakat_paid": 0.0,
    }
    data.update(overrides)
    return data


def _make_full_2026_tp3_data(**overrides):
    """Create a TP3(1/2026) data dict with all relief fields populated."""
    data = _make_base_tp3_data()
    data.update({
        "prior_childcare_centre_relief": 2500.0,
        "prior_learning_disability_relief": 8000.0,
        "prior_vaccination_relief": 500.0,
        "prior_eco_lifestyle_relief": 1500.0,
        "prior_medical_parents_relief": 3000.0,
        "prior_education_fees_relief": 5000.0,
        "prior_lifestyle_relief": 2000.0,
        "prior_prs_annuity_relief": 2000.0,
        "prior_sspn_relief": 4000.0,
        "prior_life_insurance_relief": 5000.0,
        "prior_medical_insurance_relief": 2000.0,
        "prior_disabled_equipment_relief": 0.0,
        "prior_ev_charging_relief": 1200.0,
    })
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Test: Constants
# ---------------------------------------------------------------------------

class TestTP3FormVersionConstants(FrappeTestCase):
    """Verify TP3 form version constants are correctly defined."""

    def test_supported_versions_contain_three_versions(self):
        """Three TP3 versions must be supported: 2024, 2025, 2026."""
        self.assertEqual(len(SUPPORTED_TP3_VERSIONS), 3)
        self.assertIn(TP3_FORM_VERSION_2024, SUPPORTED_TP3_VERSIONS)
        self.assertIn(TP3_FORM_VERSION_2025, SUPPORTED_TP3_VERSIONS)
        self.assertIn(TP3_FORM_VERSION_2026, SUPPORTED_TP3_VERSIONS)

    def test_current_version_is_2026(self):
        """Current TP3 form version must be 1/2026."""
        self.assertEqual(CURRENT_TP3_VERSION, "1/2026")

    def test_version_strings_format(self):
        """Version strings follow 'N/YYYY' format."""
        self.assertEqual(TP3_FORM_VERSION_2024, "1/2024")
        self.assertEqual(TP3_FORM_VERSION_2025, "1/2025")
        self.assertEqual(TP3_FORM_VERSION_2026, "1/2026")

    def test_base_fields_include_required_income_deduction_fields(self):
        """Base fields must include gross income, EPF, PCB, SOCSO, EIS, Zakat."""
        self.assertIn("prior_gross_income", TP3_BASE_FIELDS)
        self.assertIn("prior_epf_deducted", TP3_BASE_FIELDS)
        self.assertIn("prior_pcb_deducted", TP3_BASE_FIELDS)
        self.assertIn("prior_socso_deducted", TP3_BASE_FIELDS)
        self.assertIn("prior_eis_deducted", TP3_BASE_FIELDS)
        self.assertIn("prior_zakat_paid", TP3_BASE_FIELDS)

    def test_2026_relief_fields_include_budget_2026_items(self):
        """TP3(1/2026) relief fields include new Budget 2026 items."""
        self.assertIn("prior_childcare_centre_relief", TP3_2026_RELIEF_FIELDS)
        self.assertIn("prior_learning_disability_relief", TP3_2026_RELIEF_FIELDS)
        self.assertIn("prior_vaccination_relief", TP3_2026_RELIEF_FIELDS)
        self.assertIn("prior_eco_lifestyle_relief", TP3_2026_RELIEF_FIELDS)
        self.assertIn("prior_ev_charging_relief", TP3_2026_RELIEF_FIELDS)

    def test_2026_relief_limits_childcare_3000(self):
        """Budget 2026: childcare relief limit is RM3,000."""
        self.assertEqual(TP3_2026_RELIEF_LIMITS["prior_childcare_centre_relief"], 3000.0)

    def test_2026_relief_limits_learning_disability_10000(self):
        """Budget 2026: learning disability relief limit is RM10,000."""
        self.assertEqual(TP3_2026_RELIEF_LIMITS["prior_learning_disability_relief"], 10000.0)

    def test_all_relief_fields_have_limits(self):
        """Every TP3(1/2026) relief field must have a corresponding limit."""
        for field in TP3_2026_RELIEF_FIELDS:
            self.assertIn(field, TP3_2026_RELIEF_LIMITS,
                          f"Relief field '{field}' missing from limits dict")


# ---------------------------------------------------------------------------
# Test: Form Version Selection
# ---------------------------------------------------------------------------

class TestGetTP3FormVersion(FrappeTestCase):
    """Tests for get_tp3_form_version() — year-based version selection."""

    def test_join_year_2024_returns_version_2024(self):
        """Joiner in 2024 uses TP3(1/2024) form."""
        self.assertEqual(get_tp3_form_version(2024), "1/2024")

    def test_join_year_2025_returns_version_2025(self):
        """Joiner in 2025 uses TP3(1/2025) form."""
        self.assertEqual(get_tp3_form_version(2025), "1/2025")

    def test_join_year_2026_returns_version_2026(self):
        """Joiner in 2026 uses TP3(1/2026) form."""
        self.assertEqual(get_tp3_form_version(2026), "1/2026")

    def test_future_year_defaults_to_current(self):
        """Joiner in a future year (2027+) defaults to current version."""
        self.assertEqual(get_tp3_form_version(2027), CURRENT_TP3_VERSION)
        self.assertEqual(get_tp3_form_version(2030), CURRENT_TP3_VERSION)

    def test_accepts_string_year(self):
        """Function handles year passed as string."""
        self.assertEqual(get_tp3_form_version("2026"), "1/2026")


class TestGetTP3FormVersionForEmployee(FrappeTestCase):
    """Tests for get_tp3_form_version_for_employee() — date-based version selection."""

    def test_date_2026_march_returns_2026(self):
        """Employee joining 2026-03-15 gets TP3(1/2026)."""
        self.assertEqual(get_tp3_form_version_for_employee("2026-03-15"), "1/2026")

    def test_date_2025_july_returns_2025(self):
        """Employee joining 2025-07-01 gets TP3(1/2025)."""
        self.assertEqual(get_tp3_form_version_for_employee("2025-07-01"), "1/2025")

    def test_date_2024_jan_returns_2024(self):
        """Employee joining 2024-01-15 gets TP3(1/2024)."""
        self.assertEqual(get_tp3_form_version_for_employee("2024-01-15"), "1/2024")

    def test_none_date_returns_current(self):
        """None date of joining defaults to current version."""
        self.assertEqual(get_tp3_form_version_for_employee(None), CURRENT_TP3_VERSION)

    def test_empty_string_returns_current(self):
        """Empty string date defaults to current version."""
        self.assertEqual(get_tp3_form_version_for_employee(""), CURRENT_TP3_VERSION)

    def test_end_of_year_2026(self):
        """December 2026 joiner gets TP3(1/2026)."""
        self.assertEqual(get_tp3_form_version_for_employee("2026-12-31"), "1/2026")


class TestIsVersionSupported(FrappeTestCase):
    """Tests for is_version_supported()."""

    def test_2024_supported(self):
        self.assertTrue(is_version_supported("1/2024"))

    def test_2025_supported(self):
        self.assertTrue(is_version_supported("1/2025"))

    def test_2026_supported(self):
        self.assertTrue(is_version_supported("1/2026"))

    def test_unknown_version_not_supported(self):
        self.assertFalse(is_version_supported("1/2023"))

    def test_empty_string_not_supported(self):
        self.assertFalse(is_version_supported(""))

    def test_none_like_not_supported(self):
        self.assertFalse(is_version_supported("None"))


# ---------------------------------------------------------------------------
# Test: Field Definitions per Version
# ---------------------------------------------------------------------------

class TestGetTP3FieldsForVersion(FrappeTestCase):
    """Tests for get_tp3_fields_for_version() — version-aware field listing."""

    def test_2024_returns_base_fields_only(self):
        """TP3(1/2024) has only base income/deduction fields."""
        fields = get_tp3_fields_for_version(TP3_FORM_VERSION_2024)
        self.assertEqual(len(fields), len(TP3_BASE_FIELDS))
        for f in TP3_BASE_FIELDS:
            self.assertIn(f, fields)

    def test_2025_returns_base_plus_partial_reliefs(self):
        """TP3(1/2025) has base fields plus a subset of relief fields."""
        fields = get_tp3_fields_for_version(TP3_FORM_VERSION_2025)
        self.assertGreater(len(fields), len(TP3_BASE_FIELDS))
        # Should include lifestyle, PRS, SSPN, life insurance
        self.assertIn("prior_lifestyle_relief", fields)
        self.assertIn("prior_prs_annuity_relief", fields)
        # Should NOT include Budget 2026 new items
        self.assertNotIn("prior_childcare_centre_relief", fields)
        self.assertNotIn("prior_ev_charging_relief", fields)

    def test_2026_returns_base_plus_all_reliefs(self):
        """TP3(1/2026) has base fields plus all Budget 2026 relief fields."""
        fields = get_tp3_fields_for_version(TP3_FORM_VERSION_2026)
        expected_count = len(TP3_BASE_FIELDS) + len(TP3_2026_RELIEF_FIELDS)
        self.assertEqual(len(fields), expected_count)
        # All relief fields present
        for f in TP3_2026_RELIEF_FIELDS:
            self.assertIn(f, fields)

    def test_2026_includes_childcare_and_learning_disability(self):
        """TP3(1/2026) specifically includes Budget 2026 childcare and learning disability."""
        fields = get_tp3_fields_for_version(TP3_FORM_VERSION_2026)
        self.assertIn("prior_childcare_centre_relief", fields)
        self.assertIn("prior_learning_disability_relief", fields)


class TestGetReliefFieldsForVersion(FrappeTestCase):
    """Tests for get_relief_fields_for_version() — relief-only fields."""

    def test_2024_has_no_relief_fields(self):
        """TP3(1/2024) has zero relief fields."""
        relief = get_relief_fields_for_version(TP3_FORM_VERSION_2024)
        self.assertEqual(len(relief), 0)

    def test_2025_has_some_relief_fields(self):
        """TP3(1/2025) has 7 relief fields."""
        relief = get_relief_fields_for_version(TP3_FORM_VERSION_2025)
        self.assertEqual(len(relief), 7)

    def test_2026_has_all_relief_fields(self):
        """TP3(1/2026) has all 13 relief fields."""
        relief = get_relief_fields_for_version(TP3_FORM_VERSION_2026)
        self.assertEqual(len(relief), len(TP3_2026_RELIEF_FIELDS))

    def test_relief_fields_exclude_base_fields(self):
        """Relief field list must not contain any base fields."""
        for version in SUPPORTED_TP3_VERSIONS:
            relief = get_relief_fields_for_version(version)
            for f in relief:
                self.assertNotIn(f, TP3_BASE_FIELDS,
                                 f"Base field '{f}' leaked into relief list for {version}")


# ---------------------------------------------------------------------------
# Test: Validation
# ---------------------------------------------------------------------------

class TestValidateTP3Data(FrappeTestCase):
    """Tests for validate_tp3_data() — TP3 data validation."""

    def test_valid_base_data_passes(self):
        """Valid base TP3 data passes validation for all versions."""
        data = _make_base_tp3_data()
        result = validate_tp3_data(data, TP3_FORM_VERSION_2026)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_missing_gross_income_fails(self):
        """Missing prior_gross_income is a validation error."""
        data = _make_base_tp3_data()
        del data["prior_gross_income"]
        result = validate_tp3_data(data, TP3_FORM_VERSION_2026)
        self.assertFalse(result["valid"])
        self.assertTrue(any("prior_gross_income" in e for e in result["errors"]))

    def test_missing_pcb_deducted_fails(self):
        """Missing prior_pcb_deducted is a validation error."""
        data = _make_base_tp3_data()
        del data["prior_pcb_deducted"]
        result = validate_tp3_data(data, TP3_FORM_VERSION_2026)
        self.assertFalse(result["valid"])
        self.assertTrue(any("prior_pcb_deducted" in e for e in result["errors"]))

    def test_negative_gross_income_fails(self):
        """Negative gross income is a validation error."""
        data = _make_base_tp3_data(prior_gross_income=-1000.0)
        result = validate_tp3_data(data, TP3_FORM_VERSION_2026)
        self.assertFalse(result["valid"])

    def test_negative_relief_fails(self):
        """Negative relief value is a validation error."""
        data = _make_full_2026_tp3_data(prior_childcare_centre_relief=-500.0)
        result = validate_tp3_data(data, TP3_FORM_VERSION_2026)
        self.assertFalse(result["valid"])

    def test_relief_over_limit_produces_warning(self):
        """Relief exceeding statutory limit produces a warning, not an error."""
        data = _make_full_2026_tp3_data(prior_childcare_centre_relief=5000.0)  # Limit is 3000
        result = validate_tp3_data(data, TP3_FORM_VERSION_2026)
        self.assertTrue(result["valid"])  # Still valid, just warned
        self.assertGreater(len(result["warnings"]), 0)
        self.assertTrue(any("childcare" in w for w in result["warnings"]))

    def test_unsupported_version_fails(self):
        """Unsupported TP3 version fails validation."""
        data = _make_base_tp3_data()
        result = validate_tp3_data(data, "1/2023")
        self.assertFalse(result["valid"])
        self.assertTrue(any("Unsupported" in e for e in result["errors"]))

    def test_zero_values_are_valid(self):
        """All-zero TP3 data is valid."""
        data = {f: 0.0 for f in TP3_BASE_FIELDS}
        result = validate_tp3_data(data, TP3_FORM_VERSION_2024)
        self.assertTrue(result["valid"])

    def test_optional_base_field_missing_is_ok(self):
        """Optional base fields (EPF, SOCSO, EIS, Zakat) can be missing."""
        data = {
            "prior_gross_income": 30000.0,
            "prior_pcb_deducted": 1500.0,
        }
        result = validate_tp3_data(data, TP3_FORM_VERSION_2024)
        self.assertTrue(result["valid"])

    def test_2024_version_ignores_relief_limits(self):
        """TP3(1/2024) validation does not check relief limits (no relief fields)."""
        data = _make_base_tp3_data()
        data["prior_childcare_centre_relief"] = 99999.0  # Not a 2024 field
        result = validate_tp3_data(data, TP3_FORM_VERSION_2024)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["warnings"]), 0)


# ---------------------------------------------------------------------------
# Test: Relief Capping
# ---------------------------------------------------------------------------

class TestCapReliefValues(FrappeTestCase):
    """Tests for cap_relief_values() — statutory limit capping."""

    def test_values_within_limits_unchanged(self):
        """Values within limits are not modified."""
        data = _make_full_2026_tp3_data()
        capped = cap_relief_values(data, TP3_FORM_VERSION_2026)
        self.assertEqual(capped["prior_childcare_centre_relief"], 2500.0)
        self.assertEqual(capped["prior_learning_disability_relief"], 8000.0)

    def test_childcare_capped_at_3000(self):
        """Childcare relief capped at RM3,000."""
        data = _make_full_2026_tp3_data(prior_childcare_centre_relief=5000.0)
        capped = cap_relief_values(data, TP3_FORM_VERSION_2026)
        self.assertEqual(capped["prior_childcare_centre_relief"], 3000.0)

    def test_learning_disability_capped_at_10000(self):
        """Learning disability relief capped at RM10,000."""
        data = _make_full_2026_tp3_data(prior_learning_disability_relief=15000.0)
        capped = cap_relief_values(data, TP3_FORM_VERSION_2026)
        self.assertEqual(capped["prior_learning_disability_relief"], 10000.0)

    def test_ev_charging_capped_at_2500(self):
        """EV charging relief capped at RM2,500."""
        data = _make_full_2026_tp3_data(prior_ev_charging_relief=3500.0)
        capped = cap_relief_values(data, TP3_FORM_VERSION_2026)
        self.assertEqual(capped["prior_ev_charging_relief"], 2500.0)

    def test_base_fields_not_capped(self):
        """Base income/deduction fields are never capped."""
        data = _make_full_2026_tp3_data(prior_gross_income=999999.0)
        capped = cap_relief_values(data, TP3_FORM_VERSION_2026)
        self.assertEqual(capped["prior_gross_income"], 999999.0)

    def test_2024_version_does_not_cap(self):
        """TP3(1/2024) has no relief limits to apply."""
        data = _make_base_tp3_data()
        data["prior_childcare_centre_relief"] = 99999.0
        capped = cap_relief_values(data, TP3_FORM_VERSION_2024)
        self.assertEqual(capped["prior_childcare_centre_relief"], 99999.0)

    def test_none_values_preserved(self):
        """None relief values are left as None, not capped."""
        data = _make_base_tp3_data()
        data["prior_childcare_centre_relief"] = None
        capped = cap_relief_values(data, TP3_FORM_VERSION_2026)
        self.assertIsNone(capped["prior_childcare_centre_relief"])


# ---------------------------------------------------------------------------
# Test: Total Prior Reliefs Computation
# ---------------------------------------------------------------------------

class TestComputeTotalPriorReliefs(FrappeTestCase):
    """Tests for compute_total_prior_reliefs() — sum of capped relief values."""

    def test_2026_full_data_sums_correctly(self):
        """Full TP3(1/2026) data sums all 13 relief fields."""
        data = _make_full_2026_tp3_data()
        total = compute_total_prior_reliefs(data, TP3_FORM_VERSION_2026)
        # 2500 + 8000 + 500 + 1500 + 3000 + 5000 + 2000 + 2000 + 4000 + 5000 + 2000 + 0 + 1200
        expected = 36700.0
        self.assertEqual(total, expected)

    def test_2024_returns_zero(self):
        """TP3(1/2024) has no relief fields — total is 0."""
        data = _make_base_tp3_data()
        total = compute_total_prior_reliefs(data, TP3_FORM_VERSION_2024)
        self.assertEqual(total, 0.0)

    def test_over_limit_values_capped_before_summing(self):
        """Reliefs exceeding limits are capped before being summed."""
        data = _make_full_2026_tp3_data(
            prior_childcare_centre_relief=5000.0,  # cap to 3000
            prior_learning_disability_relief=20000.0,  # cap to 10000
        )
        total = compute_total_prior_reliefs(data, TP3_FORM_VERSION_2026)
        # Adjusted: 3000 + 10000 + 500 + 1500 + 3000 + 5000 + 2000 + 2000 + 4000 + 5000 + 2000 + 0 + 1200
        expected = 39200.0
        self.assertEqual(total, expected)

    def test_missing_relief_fields_treated_as_zero(self):
        """Missing relief fields are treated as zero in the sum."""
        data = _make_base_tp3_data()  # No relief fields at all
        total = compute_total_prior_reliefs(data, TP3_FORM_VERSION_2026)
        self.assertEqual(total, 0.0)

    def test_negative_relief_ignored(self):
        """Negative relief values are treated as zero (max(0, value))."""
        data = _make_full_2026_tp3_data(prior_childcare_centre_relief=-500.0)
        # -500 → max(0, -500) = 0 → rest stays the same
        total = compute_total_prior_reliefs(data, TP3_FORM_VERSION_2026)
        # Full sum minus the 2500 childcare = 36700 - 2500 = 34200
        self.assertEqual(total, 34200.0)


# ---------------------------------------------------------------------------
# Test: MTD Carry-Forward Builder
# ---------------------------------------------------------------------------

class TestBuildMTDCarryForward(FrappeTestCase):
    """Tests for build_mtd_carry_forward() — MTD-ready structure."""

    def test_carries_base_fields(self):
        """Carry-forward includes prior gross, PCB, EPF, SOCSO, EIS, Zakat."""
        data = _make_base_tp3_data()
        cf = build_mtd_carry_forward(data, TP3_FORM_VERSION_2024)
        self.assertEqual(cf["tp3_prior_gross"], 30000.0)
        self.assertEqual(cf["tp3_prior_pcb"], 1500.0)
        self.assertEqual(cf["tp3_prior_epf"], 3300.0)
        self.assertEqual(cf["tp3_prior_socso"], 350.0)
        self.assertEqual(cf["tp3_prior_eis"], 60.0)
        self.assertEqual(cf["tp3_prior_zakat"], 0.0)

    def test_carries_form_version(self):
        """Carry-forward includes the form version string."""
        data = _make_base_tp3_data()
        cf = build_mtd_carry_forward(data, TP3_FORM_VERSION_2026)
        self.assertEqual(cf["tp3_form_version"], "1/2026")

    def test_carries_total_prior_reliefs(self):
        """Carry-forward includes summed prior reliefs."""
        data = _make_full_2026_tp3_data()
        cf = build_mtd_carry_forward(data, TP3_FORM_VERSION_2026)
        self.assertEqual(cf["tp3_prior_reliefs"], 36700.0)

    def test_2024_carry_forward_zero_reliefs(self):
        """TP3(1/2024) carry-forward has zero reliefs."""
        data = _make_base_tp3_data()
        cf = build_mtd_carry_forward(data, TP3_FORM_VERSION_2024)
        self.assertEqual(cf["tp3_prior_reliefs"], 0.0)

    def test_missing_fields_default_to_zero(self):
        """Missing fields in data default to 0.0 in carry-forward."""
        cf = build_mtd_carry_forward({}, TP3_FORM_VERSION_2024)
        self.assertEqual(cf["tp3_prior_gross"], 0.0)
        self.assertEqual(cf["tp3_prior_pcb"], 0.0)
        self.assertEqual(cf["tp3_prior_epf"], 0.0)


# ---------------------------------------------------------------------------
# Test: Full Processing Pipeline
# ---------------------------------------------------------------------------

class TestProcessTP3Declaration(FrappeTestCase):
    """Tests for process_tp3_declaration() — end-to-end TP3 processing."""

    def test_2026_joiner_valid_data_succeeds(self):
        """New hire joining 2026 with valid TP3 data: success."""
        data = _make_full_2026_tp3_data()
        result = process_tp3_declaration("2026-03-15", data)
        self.assertTrue(result["success"])
        self.assertEqual(result["form_version"], "1/2026")
        self.assertIsNotNone(result["carry_forward"])
        self.assertEqual(result["carry_forward"]["tp3_prior_gross"], 30000.0)

    def test_2024_joiner_uses_2024_version(self):
        """Joiner in 2024: system selects TP3(1/2024) automatically."""
        data = _make_base_tp3_data()
        result = process_tp3_declaration("2024-07-01", data)
        self.assertTrue(result["success"])
        self.assertEqual(result["form_version"], "1/2024")

    def test_2025_joiner_uses_2025_version(self):
        """Joiner in 2025: system selects TP3(1/2025) automatically."""
        data = _make_base_tp3_data()
        result = process_tp3_declaration("2025-04-01", data)
        self.assertTrue(result["success"])
        self.assertEqual(result["form_version"], "1/2025")

    def test_explicit_version_override(self):
        """Explicit version override takes precedence over join date."""
        data = _make_base_tp3_data()
        result = process_tp3_declaration("2024-07-01", data, tp3_form_version="1/2026")
        self.assertEqual(result["form_version"], "1/2026")

    def test_invalid_data_returns_failure(self):
        """Missing required fields cause processing failure."""
        data = {"prior_epf_deducted": 1000.0}  # Missing gross + PCB
        result = process_tp3_declaration("2026-03-15", data)
        self.assertFalse(result["success"])
        self.assertIsNone(result["carry_forward"])
        self.assertGreater(len(result["validation"]["errors"]), 0)

    def test_validation_result_included_on_success(self):
        """Successful processing includes validation with warnings if any."""
        data = _make_full_2026_tp3_data(prior_childcare_centre_relief=5000.0)  # Over limit
        result = process_tp3_declaration("2026-03-15", data)
        self.assertTrue(result["success"])
        self.assertGreater(len(result["validation"]["warnings"]), 0)

    def test_carry_forward_prior_reliefs_flow_correctly(self):
        """Prior reliefs from TP3(1/2026) flow into carry-forward for MTD."""
        data = _make_full_2026_tp3_data()
        result = process_tp3_declaration("2026-06-01", data)
        cf = result["carry_forward"]
        self.assertEqual(cf["tp3_prior_reliefs"], 36700.0)
        self.assertEqual(cf["tp3_form_version"], "1/2026")

    def test_pcb_computation_gets_prior_gross_and_pcb(self):
        """Carry-forward contains tp3_prior_gross and tp3_prior_pcb for PCB calculator."""
        data = _make_full_2026_tp3_data()
        result = process_tp3_declaration("2026-03-15", data)
        cf = result["carry_forward"]
        self.assertIn("tp3_prior_gross", cf)
        self.assertIn("tp3_prior_pcb", cf)
        self.assertEqual(cf["tp3_prior_gross"], 30000.0)
        self.assertEqual(cf["tp3_prior_pcb"], 1500.0)


# ---------------------------------------------------------------------------
# Test: Form Metadata
# ---------------------------------------------------------------------------

class TestGetTP3FormMetadata(FrappeTestCase):
    """Tests for get_tp3_form_metadata() — UI rendering metadata."""

    def test_2026_metadata_title(self):
        """TP3(1/2026) metadata has Budget 2026 in title."""
        meta = get_tp3_form_metadata(TP3_FORM_VERSION_2026)
        self.assertIn("Budget 2026", meta["title"])

    def test_2026_is_current(self):
        """TP3(1/2026) is marked as current version."""
        meta = get_tp3_form_metadata(TP3_FORM_VERSION_2026)
        self.assertTrue(meta["is_current"])

    def test_2024_is_not_current(self):
        """TP3(1/2024) is NOT marked as current version."""
        meta = get_tp3_form_metadata(TP3_FORM_VERSION_2024)
        self.assertFalse(meta["is_current"])

    def test_2026_relief_count(self):
        """TP3(1/2026) metadata reports 13 relief fields."""
        meta = get_tp3_form_metadata(TP3_FORM_VERSION_2026)
        self.assertEqual(meta["relief_count"], len(TP3_2026_RELIEF_FIELDS))

    def test_2024_relief_count_zero(self):
        """TP3(1/2024) metadata reports 0 relief fields."""
        meta = get_tp3_form_metadata(TP3_FORM_VERSION_2024)
        self.assertEqual(meta["relief_count"], 0)

    def test_unknown_version_metadata(self):
        """Unknown version returns empty metadata."""
        meta = get_tp3_form_metadata("1/2023")
        self.assertEqual(meta["title"], "Unknown")
        self.assertEqual(len(meta["fields"]), 0)
        self.assertFalse(meta["is_current"])

    def test_metadata_fields_match_version(self):
        """Metadata fields list matches get_tp3_fields_for_version()."""
        for version in SUPPORTED_TP3_VERSIONS:
            meta = get_tp3_form_metadata(version)
            expected = get_tp3_fields_for_version(version)
            self.assertEqual(meta["fields"], expected,
                             f"Fields mismatch for {version}")

    def test_metadata_version_field(self):
        """Metadata includes the version string."""
        meta = get_tp3_form_metadata(TP3_FORM_VERSION_2025)
        self.assertEqual(meta["version"], "1/2025")
