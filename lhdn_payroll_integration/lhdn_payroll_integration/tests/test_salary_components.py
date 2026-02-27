# Copyright (c) 2026, Prisma Technology and contributors
# For license information, please see license.txt

"""Tests for US-046: EIS, HRDF, and common allowance salary components fixture.

Verifies that EIS Employee, EIS - Employer, HRDF Levy, Transport Allowance,
and Housing Allowance are installed via the salary_component.json fixture.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

REQUIRED_COMPONENTS = [
    {
        "name": "EIS Employee",
        "type": "Deduction",
        "custom_is_pcb_component": 0,
        "custom_lhdn_exclude_from_invoice": 0,
        "custom_lhdn_classification_code": "",
    },
    {
        "name": "EIS - Employer",
        "type": "Deduction",
        "custom_is_pcb_component": 0,
        "custom_lhdn_exclude_from_invoice": 1,
        "custom_lhdn_classification_code": "",
    },
    {
        "name": "HRDF Levy",
        "type": "Deduction",
        "custom_is_pcb_component": 0,
        "custom_lhdn_exclude_from_invoice": 1,
        "custom_lhdn_classification_code": "",
    },
    {
        "name": "Transport Allowance",
        "type": "Earning",
        "custom_is_pcb_component": 0,
        "custom_lhdn_exclude_from_invoice": 0,
        "custom_lhdn_classification_code": "022",
    },
    {
        "name": "Housing Allowance",
        "type": "Earning",
        "custom_is_pcb_component": 0,
        "custom_lhdn_exclude_from_invoice": 0,
        "custom_lhdn_classification_code": "022",
    },
]


class TestSalaryComponentsFixture(FrappeTestCase):
    """Verify that all required salary components from US-046 are installed."""

    def _get_component(self, name):
        return frappe.db.get_value(
            "Salary Component",
            name,
            [
                "name",
                "type",
                "custom_is_pcb_component",
                "custom_lhdn_exclude_from_invoice",
                "custom_lhdn_classification_code",
            ],
            as_dict=True,
        )

    def test_eis_employee_exists(self):
        """EIS Employee deduction component must be installed."""
        comp = self._get_component("EIS Employee")
        self.assertIsNotNone(comp, "EIS Employee salary component not found in database")
        self.assertEqual(comp.type, "Deduction", "EIS Employee must be type Deduction")
        self.assertEqual(
            int(comp.custom_is_pcb_component or 0),
            0,
            "EIS Employee must not be a PCB component",
        )

    def test_eis_employer_exists(self):
        """EIS - Employer deduction component must be installed and excluded from invoice."""
        comp = self._get_component("EIS - Employer")
        self.assertIsNotNone(comp, "EIS - Employer salary component not found in database")
        self.assertEqual(comp.type, "Deduction", "EIS - Employer must be type Deduction")
        self.assertEqual(
            int(comp.custom_lhdn_exclude_from_invoice or 0),
            1,
            "EIS - Employer must be excluded from LHDN invoice",
        )

    def test_hrdf_levy_exists(self):
        """HRDF Levy deduction component must be installed and excluded from invoice."""
        comp = self._get_component("HRDF Levy")
        self.assertIsNotNone(comp, "HRDF Levy salary component not found in database")
        self.assertEqual(comp.type, "Deduction", "HRDF Levy must be type Deduction")
        self.assertEqual(
            int(comp.custom_lhdn_exclude_from_invoice or 0),
            1,
            "HRDF Levy must be excluded from LHDN invoice",
        )

    def test_transport_allowance_exists(self):
        """Transport Allowance earning component must be installed with classification 022."""
        comp = self._get_component("Transport Allowance")
        self.assertIsNotNone(comp, "Transport Allowance salary component not found in database")
        self.assertEqual(comp.type, "Earning", "Transport Allowance must be type Earning")
        self.assertEqual(
            comp.custom_lhdn_classification_code or "",
            "022",
            "Transport Allowance must have LHDN classification code 022 (Others)",
        )

    def test_housing_allowance_exists(self):
        """Housing Allowance earning component must be installed with classification 022."""
        comp = self._get_component("Housing Allowance")
        self.assertIsNotNone(comp, "Housing Allowance salary component not found in database")
        self.assertEqual(comp.type, "Earning", "Housing Allowance must be type Earning")
        self.assertEqual(
            comp.custom_lhdn_classification_code or "",
            "022",
            "Housing Allowance must have LHDN classification code 022 (Others)",
        )

    def test_all_required_components_present(self):
        """All 5 new salary components must be installed after fixture sync."""
        missing = []
        for expected in REQUIRED_COMPONENTS:
            if not frappe.db.exists("Salary Component", expected["name"]):
                missing.append(expected["name"])
        self.assertEqual(
            missing,
            [],
            f"Missing salary components after fixture sync: {missing}",
        )
