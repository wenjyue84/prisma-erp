"""Tests for PCB Category Code (1/2/3) on Employee — US-051.

Verifies that:
- calculate_pcb() accepts the new ``category`` parameter
- Category 1 (single/working-spouse) produces no extra relief
- Category 2 (non-working spouse) applies RM4,000 spouse relief
- Category 3 (single parent) applies RM4,000 parent relief (ITA s.46A)
- Same annual income produces different PCB across categories
- CP39 report get_columns() includes 'pcb_category' fieldname
- EA Form get_columns() includes 'pcb_category' fieldname
"""
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_calculator import (
    calculate_pcb,
)
from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance.cp39_pcb_remittance import (
    get_columns as cp39_get_columns,
)
from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form.ea_form import (
    get_columns as ea_get_columns,
)

# Test income: RM60,000/year puts us in the 13% band after self-relief RM9,000
_TEST_ANNUAL_INCOME = 60_000.0


class TestPCBCategoryCalculations(FrappeTestCase):
    """Tests for calculate_pcb() with the category parameter."""

    def _chargeable(self, relief):
        """Helper: chargeable income after given relief."""
        return max(0.0, _TEST_ANNUAL_INCOME - relief)

    def test_category_1_no_spouse_relief(self):
        """Category 1: only self-relief RM9,000 applied."""
        pcb = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, category=1)
        # Manually: chargeable = 60000 - 9000 = 51000, in 13% band
        # tax = 1800 + (51000 - 50000) * 0.13 = 1930 / 12 = 160.83
        expected = round((1_800.0 + 1_000.0 * 0.13) / 12, 2)
        self.assertAlmostEqual(pcb, expected, places=2)

    def test_category_2_spouse_relief(self):
        """Category 2: self-relief RM9,000 + spouse relief RM4,000."""
        pcb = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, category=2)
        # chargeable = 60000 - 9000 - 4000 = 47000, in 8% band
        # tax = 600 + (47000 - 35000) * 0.08 = 1560 / 12 = 130.0
        expected = round((600.0 + 12_000.0 * 0.08) / 12, 2)
        self.assertAlmostEqual(pcb, expected, places=2)

    def test_category_3_single_parent_relief(self):
        """Category 3: self-relief RM9,000 + single parent RM4,000 (ITA s.46A)."""
        pcb = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, category=3)
        # Same relief as category 2: RM13,000 total
        pcb_cat2 = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, category=2)
        self.assertAlmostEqual(pcb, pcb_cat2, places=2)

    def test_category_1_higher_than_category_2(self):
        """Category 1 PCB must be higher than Category 2 (less relief = more tax)."""
        pcb1 = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, category=1)
        pcb2 = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, category=2)
        self.assertGreater(pcb1, pcb2)

    def test_category_1_higher_than_category_3(self):
        """Category 1 PCB must be higher than Category 3 (less relief = more tax)."""
        pcb1 = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, category=1)
        pcb3 = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, category=3)
        self.assertGreater(pcb1, pcb3)

    def test_category_none_falls_back_to_married_false(self):
        """No category + married=False behaves like category=1."""
        pcb_default = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, married=False)
        pcb_cat1 = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, category=1)
        self.assertAlmostEqual(pcb_default, pcb_cat1, places=2)

    def test_category_none_falls_back_to_married_true(self):
        """No category + married=True behaves like category=2."""
        pcb_married = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, married=True)
        pcb_cat2 = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, category=2)
        self.assertAlmostEqual(pcb_married, pcb_cat2, places=2)

    def test_category_with_children(self):
        """Category 2 with 2 children applies RM4,000 child reliefs additionally."""
        pcb = calculate_pcb(_TEST_ANNUAL_INCOME, resident=True, category=2, children=2)
        # chargeable = 60000 - 9000 - 4000 - 4000 = 43000, in 8% band
        # tax = 600 + (43000 - 35000) * 0.08 = 1240 / 12 = 103.33
        expected = round((600.0 + 8_000.0 * 0.08) / 12, 2)
        self.assertAlmostEqual(pcb, expected, places=2)

    def test_non_resident_category_ignored(self):
        """Non-residents are taxed at flat 30% regardless of category."""
        pcb1 = calculate_pcb(_TEST_ANNUAL_INCOME, resident=False, category=1)
        pcb2 = calculate_pcb(_TEST_ANNUAL_INCOME, resident=False, category=2)
        pcb3 = calculate_pcb(_TEST_ANNUAL_INCOME, resident=False, category=3)
        expected = round((_TEST_ANNUAL_INCOME * 0.30) / 12, 2)
        self.assertAlmostEqual(pcb1, expected, places=2)
        self.assertAlmostEqual(pcb2, expected, places=2)
        self.assertAlmostEqual(pcb3, expected, places=2)


class TestCP39ReportPCBCategoryColumn(FrappeTestCase):
    """CP39 report must expose pcb_category in its columns."""

    def test_cp39_columns_include_pcb_category(self):
        """get_columns() must include a 'pcb_category' fieldname."""
        columns = cp39_get_columns()
        fieldnames = [c.get("fieldname") for c in columns if isinstance(c, dict)]
        self.assertIn("pcb_category", fieldnames, "CP39 columns missing pcb_category")

    def test_cp39_pcb_category_column_is_data_type(self):
        """pcb_category column must have fieldtype Data."""
        columns = cp39_get_columns()
        cat_col = next(
            (c for c in columns if isinstance(c, dict) and c.get("fieldname") == "pcb_category"),
            None,
        )
        self.assertIsNotNone(cat_col, "pcb_category column not found")
        self.assertEqual(cat_col.get("fieldtype"), "Data")


class TestEAFormPCBCategoryColumn(FrappeTestCase):
    """EA Form report must expose pcb_category in its columns."""

    def test_ea_form_columns_include_pcb_category(self):
        """get_columns() must include a 'pcb_category' fieldname."""
        columns = ea_get_columns()
        fieldnames = [c.get("fieldname") for c in columns if isinstance(c, dict)]
        self.assertIn("pcb_category", fieldnames, "EA Form columns missing pcb_category")

    def test_ea_form_pcb_category_column_is_data_type(self):
        """pcb_category column must have fieldtype Data."""
        columns = ea_get_columns()
        cat_col = next(
            (c for c in columns if isinstance(c, dict) and c.get("fieldname") == "pcb_category"),
            None,
        )
        self.assertIsNotNone(cat_col, "pcb_category column not found")
        self.assertEqual(cat_col.get("fieldtype"), "Data")
