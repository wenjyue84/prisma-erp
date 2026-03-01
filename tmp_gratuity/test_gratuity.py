"""Tests for US-125: Approved Gratuity Fund Contribution and Tax-Exempt Gratuity Declaration.

Covers:
1. 3 Gratuity salary components exist in fixture (Approved Fund / Non-Approved / Ex-Gratia)
2. Each component is type Earning with custom_is_gratuity_or_leave_encashment=1 and EA section B5
3. Approved Fund Gratuity: exempt = min(gratuity, RM1,000 x years_of_service)
4. Approved Fund Gratuity fully exempt when gratuity <= exemption cap
5. Non-Approved Gratuity: no exemption, fully taxable
6. Ex-Gratia: no para 25 exemption
7. Zero years_of_service triggers warning for Approved Fund type
8. EA Form section is B5 Gratuity
9. PCB calculation excludes exempt gratuity from chargeable income
10. EA Form aggregation of multiple gratuity payments
11. Component-name to gratuity-type mapping
"""

import frappe
from frappe.tests.utils import FrappeTestCase


GRATUITY_COMPONENTS = [
    "Gratuity - Approved Fund",
    "Gratuity - Non-Approved",
    "Gratuity - Ex-Gratia",
]


class TestGratuitySalaryComponentsFixture(FrappeTestCase):
    """Verify the 3 gratuity salary components are installed via fixture."""

    def _get_component(self, name):
        return frappe.db.get_value(
            "Salary Component",
            name,
            ["name", "type", "custom_is_gratuity_or_leave_encashment", "custom_ea_section"],
            as_dict=True,
        )

    def test_approved_fund_component_exists(self):
        """'Gratuity - Approved Fund' earning component must be installed."""
        comp = self._get_component("Gratuity - Approved Fund")
        self.assertIsNotNone(comp, "Gratuity - Approved Fund salary component not found")
        self.assertEqual(comp.type, "Earning")
        self.assertEqual(int(comp.custom_is_gratuity_or_leave_encashment or 0), 1)

    def test_non_approved_component_exists(self):
        """'Gratuity - Non-Approved' earning component must be installed."""
        comp = self._get_component("Gratuity - Non-Approved")
        self.assertIsNotNone(comp, "Gratuity - Non-Approved salary component not found")
        self.assertEqual(comp.type, "Earning")
        self.assertEqual(int(comp.custom_is_gratuity_or_leave_encashment or 0), 1)

    def test_ex_gratia_component_exists(self):
        """'Gratuity - Ex-Gratia' earning component must be installed."""
        comp = self._get_component("Gratuity - Ex-Gratia")
        self.assertIsNotNone(comp, "Gratuity - Ex-Gratia salary component not found")
        self.assertEqual(comp.type, "Earning")
        self.assertEqual(int(comp.custom_is_gratuity_or_leave_encashment or 0), 1)

    def test_all_gratuity_components_have_ea_b5_section(self):
        """All 3 gratuity components must map to EA Form section B5."""
        for name in GRATUITY_COMPONENTS:
            comp = self._get_component(name)
            self.assertIsNotNone(comp, f"{name} not found")
            self.assertIn(
                "B5", str(comp.custom_ea_section or ""),
                f"{name} must map to EA Form B5 Gratuity"
            )

    def test_all_three_gratuity_components_present(self):
        """All 3 gratuity salary components must be present after fixture sync."""
        missing = [name for name in GRATUITY_COMPONENTS
                   if not frappe.db.exists("Salary Component", name)]
        self.assertEqual(missing, [], f"Missing gratuity components: {missing}")


class TestCalculateGratuityExemption(FrappeTestCase):
    """Unit tests for calculate_gratuity_exemption() — Schedule 6 para 25 logic."""

    def _calc(self, amount, gtype, years):
        from lhdn_payroll_integration.services.gratuity_calculator import calculate_gratuity_exemption
        return calculate_gratuity_exemption(amount, gtype, years)

    def test_approved_fund_5yr_rm10000(self):
        """5-year employee with RM10,000 approved fund gratuity: exempt RM5,000, taxable RM5,000."""
        result = self._calc(10_000.0, "Approved Fund Gratuity", 5)
        self.assertAlmostEqual(result["exempt_gratuity"], 5_000.0, places=2)
        self.assertAlmostEqual(result["taxable_gratuity"], 5_000.0, places=2)

    def test_approved_fund_exempt_capped_at_gratuity_amount(self):
        """When exempt cap > gratuity, entire gratuity is exempt (taxable = 0)."""
        # 10 years -> cap = RM10,000; gratuity = RM6,000 -> all exempt
        result = self._calc(6_000.0, "Approved Fund Gratuity", 10)
        self.assertAlmostEqual(result["exempt_gratuity"], 6_000.0, places=2)
        self.assertAlmostEqual(result["taxable_gratuity"], 0.0, places=2)

    def test_approved_fund_1yr_rm1000_exactly(self):
        """1-year employee, RM1,000 gratuity from approved fund: fully exempt."""
        result = self._calc(1_000.0, "Approved Fund Gratuity", 1)
        self.assertAlmostEqual(result["exempt_gratuity"], 1_000.0, places=2)
        self.assertAlmostEqual(result["taxable_gratuity"], 0.0, places=2)

    def test_non_approved_gratuity_fully_taxable(self):
        """Non-Approved Gratuity: no Schedule 6 para 25 exemption, fully taxable."""
        result = self._calc(8_000.0, "Non-Approved Gratuity", 8)
        self.assertAlmostEqual(result["exempt_gratuity"], 0.0, places=2)
        self.assertAlmostEqual(result["taxable_gratuity"], 8_000.0, places=2)

    def test_ex_gratia_no_para25_exemption(self):
        """Ex-Gratia: no paragraph 25 exemption (para 30 may apply separately)."""
        result = self._calc(5_000.0, "Ex-Gratia", 5)
        self.assertAlmostEqual(result["exempt_gratuity"], 0.0, places=2)
        self.assertAlmostEqual(result["taxable_gratuity"], 5_000.0, places=2)

    def test_zero_years_approved_fund_no_exemption_and_warning(self):
        """Approved Fund Gratuity with 0 years: exempt is 0 and warning is set."""
        result = self._calc(5_000.0, "Approved Fund Gratuity", 0)
        self.assertAlmostEqual(result["exempt_gratuity"], 0.0, places=2)
        self.assertAlmostEqual(result["taxable_gratuity"], 5_000.0, places=2)
        self.assertGreater(len(result["warning"]), 0, "Warning must be set when years_of_service=0")

    def test_ea_form_section_is_b5(self):
        """Gratuity exemption result always references EA Form section B5."""
        result = self._calc(5_000.0, "Approved Fund Gratuity", 5)
        self.assertIn("B5", result["ea_form_section"])

    def test_gross_gratuity_in_result(self):
        """Result dict contains gross_gratuity equal to input."""
        result = self._calc(12_345.67, "Approved Fund Gratuity", 10)
        self.assertAlmostEqual(result["gross_gratuity"], 12_345.67, places=2)

    def test_exemption_limit_in_result(self):
        """exemption_limit = RM1,000 x completed years."""
        result = self._calc(20_000.0, "Approved Fund Gratuity", 7)
        self.assertAlmostEqual(result["exemption_limit"], 7_000.0, places=2)

    def test_fractional_years_floored(self):
        """Fractional years are floored to whole completed years (e.g. 4.9 -> 4)."""
        result = self._calc(10_000.0, "Approved Fund Gratuity", 4.9)
        # 4 completed years -> exempt cap = RM4,000
        self.assertAlmostEqual(result["exemption_limit"], 4_000.0, places=2)
        self.assertAlmostEqual(result["exempt_gratuity"], 4_000.0, places=2)
        self.assertAlmostEqual(result["taxable_gratuity"], 6_000.0, places=2)


class TestGratuityComponentTypeMapping(FrappeTestCase):
    """Tests for get_gratuity_type_from_component() name-to-type mapping."""

    def test_approved_fund_component_maps_to_approved_type(self):
        """'Gratuity - Approved Fund' maps to 'Approved Fund Gratuity'."""
        from lhdn_payroll_integration.services.gratuity_calculator import (
            get_gratuity_type_from_component, GRATUITY_TYPE_APPROVED
        )
        result = get_gratuity_type_from_component("Gratuity - Approved Fund")
        self.assertEqual(result, GRATUITY_TYPE_APPROVED)

    def test_non_approved_component_maps_to_non_approved_type(self):
        """'Gratuity - Non-Approved' maps to 'Non-Approved Gratuity'."""
        from lhdn_payroll_integration.services.gratuity_calculator import (
            get_gratuity_type_from_component, GRATUITY_TYPE_NON_APPROVED
        )
        result = get_gratuity_type_from_component("Gratuity - Non-Approved")
        self.assertEqual(result, GRATUITY_TYPE_NON_APPROVED)

    def test_ex_gratia_component_maps_to_ex_gratia_type(self):
        """'Gratuity - Ex-Gratia' maps to 'Ex-Gratia'."""
        from lhdn_payroll_integration.services.gratuity_calculator import (
            get_gratuity_type_from_component, GRATUITY_TYPE_EX_GRATIA
        )
        result = get_gratuity_type_from_component("Gratuity - Ex-Gratia")
        self.assertEqual(result, GRATUITY_TYPE_EX_GRATIA)


class TestPCBExcludesExemptGratuity(FrappeTestCase):
    """Verify PCB calculation excludes exempt gratuity from chargeable income."""

    def test_pcb_with_exempt_gratuity_lower_than_full_amount(self):
        """PCB on RM10,000 approved gratuity (5yr) should only tax RM5,000.

        Monthly income: RM6,000 (annual RM72,000)
        Approved Fund Gratuity: RM10,000; 5 years service
        Exempt: RM5,000; Taxable: RM5,000
        PCB with gratuity_amount=10,000 years=5 must equal
        PCB with gratuity_amount=5,000 years=0 (no further exemption).
        """
        from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb

        # PCB with RM10,000 gratuity, 5 years -> exempt RM5,000, taxable RM5,000
        pcb_with_exempt = calculate_pcb(
            annual_income=72_000.0,
            resident=True,
            gratuity_amount=10_000.0,
            years_of_service=5,
        )
        # PCB with only RM5,000 as taxable irregular (no further exemption)
        pcb_fully_taxable_5k = calculate_pcb(
            annual_income=72_000.0,
            resident=True,
            gratuity_amount=5_000.0,
            years_of_service=0,
        )
        # The two should be equal: exempt portion is excluded from tax base
        self.assertAlmostEqual(
            pcb_with_exempt,
            pcb_fully_taxable_5k,
            places=1,
            msg="PCB with 5yr approved gratuity exemption should match PCB on RM5,000 taxable gratuity"
        )

    def test_pcb_non_approved_gratuity_fully_taxed(self):
        """Non-approved gratuity (years=0) PCB equals bonus PCB on same amount."""
        from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb

        # Non-approved: pass years_of_service=0 so no exemption applies
        pcb_non_approved = calculate_pcb(
            annual_income=72_000.0,
            resident=True,
            gratuity_amount=5_000.0,
            years_of_service=0,
        )
        # Direct taxable: same as bonus_amount (both are fully taxable irregular payments)
        pcb_direct = calculate_pcb(
            annual_income=72_000.0,
            resident=True,
            bonus_amount=5_000.0,
        )
        self.assertAlmostEqual(
            pcb_non_approved,
            pcb_direct,
            places=1,
            msg="Non-approved gratuity PCB should equal PCB on equivalent bonus (no exemption)"
        )


class TestEAFormGratuityAggregation(FrappeTestCase):
    """Tests for EA Form B5 gratuity aggregation across multiple payments."""

    def test_aggregate_single_gratuity(self):
        """Single approved gratuity aggregates correctly for EA Form."""
        from lhdn_payroll_integration.services.gratuity_calculator import (
            calculate_gratuity_exemption,
            get_ea_form_gratuity_amounts,
        )

        result = calculate_gratuity_exemption(10_000.0, "Approved Fund Gratuity", 5)
        ea = get_ea_form_gratuity_amounts([result])

        self.assertAlmostEqual(ea["total_gross"], 10_000.0, places=2)
        self.assertAlmostEqual(ea["total_exempt"], 5_000.0, places=2)
        self.assertAlmostEqual(ea["total_taxable"], 5_000.0, places=2)
        self.assertIn("B5", ea["ea_section"])

    def test_aggregate_mixed_gratuity_types(self):
        """Mixed approved and non-approved gratuity totals correctly for EA Form."""
        from lhdn_payroll_integration.services.gratuity_calculator import (
            calculate_gratuity_exemption,
            get_ea_form_gratuity_amounts,
        )

        approved = calculate_gratuity_exemption(10_000.0, "Approved Fund Gratuity", 5)  # exempt 5,000
        non_approved = calculate_gratuity_exemption(3_000.0, "Non-Approved Gratuity", 5)  # exempt 0

        ea = get_ea_form_gratuity_amounts([approved, non_approved])

        self.assertAlmostEqual(ea["total_gross"], 13_000.0, places=2)
        self.assertAlmostEqual(ea["total_exempt"], 5_000.0, places=2)
        self.assertAlmostEqual(ea["total_taxable"], 8_000.0, places=2)
