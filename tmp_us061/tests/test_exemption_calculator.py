"""Tests for US-061: Perquisite Exemption Thresholds on Salary Components.

Verifies calculate_taxable_component() correctly applies ITA s.13(1)(a) and
Public Ruling No. 5/2019 exemption ceilings for perquisites.

Acceptance criteria tests:
- RM8,000 transport allowance → taxable RM2,000 (RM6,000 ceiling)
- Medical benefit → taxable RM0 (ceiling=0, fully exempt)
"""

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.exemption_calculator import calculate_taxable_component


class TestExemptionCalculator(FrappeTestCase):
    """Unit tests for calculate_taxable_component()."""

    # --- Acceptance criteria tests ---

    def test_transport_allowance_rm8000_taxable_rm2000(self):
        """RM8,000 transport allowance with RM6,000 ceiling → taxable RM2,000."""
        taxable = calculate_taxable_component(
            "Transport Allowance",
            annual_amount=8000,
            exemption_type="Transport",
            ceiling=6000,
        )
        self.assertEqual(taxable, 2000.0)

    def test_medical_benefit_fully_exempt(self):
        """Medical benefit with ceiling=0 (fully exempt) → taxable RM0."""
        taxable = calculate_taxable_component(
            "Medical Benefit",
            annual_amount=5000,
            exemption_type="Medical",
            ceiling=0,
        )
        self.assertEqual(taxable, 0.0)

    # --- Transport exemption ---

    def test_transport_below_ceiling_fully_exempt(self):
        """Transport RM4,000 (below RM6,000 ceiling) → taxable RM0."""
        taxable = calculate_taxable_component(
            "Transport Allowance",
            annual_amount=4000,
            exemption_type="Transport",
            ceiling=6000,
        )
        self.assertEqual(taxable, 0.0)

    def test_transport_exactly_at_ceiling(self):
        """Transport RM6,000 exactly at ceiling → taxable RM0."""
        taxable = calculate_taxable_component(
            "Transport Allowance",
            annual_amount=6000,
            exemption_type="Transport",
            ceiling=6000,
        )
        self.assertEqual(taxable, 0.0)

    # --- Childcare exemption ---

    def test_childcare_below_ceiling_fully_exempt(self):
        """Childcare RM2,000 (below RM2,400 ceiling) → taxable RM0."""
        taxable = calculate_taxable_component(
            "Childcare Allowance",
            annual_amount=2000,
            exemption_type="Childcare",
            ceiling=2400,
        )
        self.assertEqual(taxable, 0.0)

    def test_childcare_above_ceiling_partial_exemption(self):
        """Childcare RM3,000 (above RM2,400 ceiling) → taxable RM600."""
        taxable = calculate_taxable_component(
            "Childcare Allowance",
            annual_amount=3000,
            exemption_type="Childcare",
            ceiling=2400,
        )
        self.assertEqual(taxable, 600.0)

    # --- Fully exempt types (ceiling=0) ---

    def test_mobile_phone_fully_exempt(self):
        """Mobile phone handset ceiling=0 → taxable RM0."""
        taxable = calculate_taxable_component(
            "Mobile Phone Handset",
            annual_amount=2000,
            exemption_type="Mobile Phone",
            ceiling=0,
        )
        self.assertEqual(taxable, 0.0)

    def test_group_insurance_fully_exempt(self):
        """Group insurance ceiling=0 → taxable RM0."""
        taxable = calculate_taxable_component(
            "Group Insurance Premium",
            annual_amount=5000,
            exemption_type="Group Insurance",
            ceiling=0,
        )
        self.assertEqual(taxable, 0.0)

    # --- No exemption type ---

    def test_no_exemption_type_returns_full_amount(self):
        """exemption_type='None' → returns full amount as taxable."""
        taxable = calculate_taxable_component(
            "Basic Salary",
            annual_amount=60000,
            exemption_type="None",
            ceiling=6000,
        )
        self.assertEqual(taxable, 60000.0)

    def test_empty_exemption_type_returns_full_amount(self):
        """Empty exemption_type → returns full amount as taxable."""
        taxable = calculate_taxable_component(
            "Commission",
            annual_amount=24000,
            exemption_type="",
            ceiling=6000,
        )
        self.assertEqual(taxable, 24000.0)

    def test_default_exemption_type_returns_full_amount(self):
        """No exemption_type argument → returns full amount as taxable."""
        taxable = calculate_taxable_component(
            "Bonus",
            annual_amount=10000,
        )
        self.assertEqual(taxable, 10000.0)

    # --- Edge cases ---

    def test_zero_amount_returns_zero(self):
        """Zero annual_amount → taxable RM0 regardless of exemption."""
        taxable = calculate_taxable_component(
            "Transport Allowance",
            annual_amount=0,
            exemption_type="Transport",
            ceiling=6000,
        )
        self.assertEqual(taxable, 0.0)

    def test_negative_amount_returns_zero(self):
        """Negative annual_amount → taxable RM0 (floored)."""
        taxable = calculate_taxable_component(
            "Transport Allowance",
            annual_amount=-1000,
            exemption_type="Transport",
            ceiling=6000,
        )
        # -1000 - 6000 = -7000, floored at 0
        self.assertEqual(taxable, 0.0)


class TestTransportAllowanceFixture(FrappeTestCase):
    """Verify Transport Allowance fixture has correct exemption fields (US-061)."""

    def test_transport_allowance_has_exemption_type(self):
        """Transport Allowance must have custom_exemption_type = 'Transport'."""
        import frappe
        comp = frappe.db.get_value(
            "Salary Component",
            "Transport Allowance",
            ["custom_exemption_type", "custom_annual_exemption_ceiling"],
            as_dict=True,
        )
        self.assertIsNotNone(comp, "Transport Allowance not found in database")
        self.assertEqual(
            comp.custom_exemption_type,
            "Transport",
            "Transport Allowance must have exemption_type = Transport",
        )
        self.assertEqual(
            float(comp.custom_annual_exemption_ceiling or 0),
            6000.0,
            "Transport Allowance must have exemption ceiling = RM6,000",
        )

    def test_custom_exemption_type_field_exists(self):
        """custom_exemption_type custom field must be installed on Salary Component."""
        import frappe
        exists = frappe.db.exists(
            "Custom Field",
            "Salary Component-custom_exemption_type",
        )
        self.assertTrue(exists, "Custom field custom_exemption_type not found on Salary Component")

    def test_custom_annual_exemption_ceiling_field_exists(self):
        """custom_annual_exemption_ceiling custom field must be installed on Salary Component."""
        import frappe
        exists = frappe.db.exists(
            "Custom Field",
            "Salary Component-custom_annual_exemption_ceiling",
        )
        self.assertTrue(
            exists,
            "Custom field custom_annual_exemption_ceiling not found on Salary Component",
        )
