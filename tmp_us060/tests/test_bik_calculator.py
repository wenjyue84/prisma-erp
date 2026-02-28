"""Tests for US-060: Employee BIK Record DocType and BIK calculator.

Covers:
  - get_annual_car_bik() lookup table by price bracket
  - CAR_BIK_TABLE constants are correct per LHDN Public Ruling 3/2013
  - calculate_monthly_bik_total() returns correct monthly BIK
  - EmployeeBIKRecord._calculate_totals() computes correct totals
  - BIK increases PCB correctly when added to gross income
  - EA Form B7 is populated from BIK records
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.services.bik_calculator import (
    get_annual_car_bik,
    calculate_monthly_bik_total,
    get_annual_bik_for_ea_form,
    CAR_BIK_TABLE,
    FUEL_BIK_MONTHLY,
    DRIVER_BIK_MONTHLY,
)
from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb
from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_bik_record.employee_bik_record import (
    EmployeeBIKRecord,
    get_employee_bik,
)


# ---------------------------------------------------------------------------
# Tests — get_annual_car_bik() lookup
# ---------------------------------------------------------------------------

class TestGetAnnualCarBIK(FrappeTestCase):
    """get_annual_car_bik() returns correct prescribed annual BIK per LHDN table."""

    def test_car_50000_returns_1200(self):
        """Car priced at exactly RM50,000 returns RM1,200/year."""
        self.assertEqual(get_annual_car_bik(50_000), 1_200)

    def test_car_120000_returns_5000(self):
        """Car priced at RM120,000 falls in <=RM150,000 bracket → RM5,000/year.

        This is the acceptance criteria test case.
        """
        self.assertEqual(get_annual_car_bik(120_000), 5_000)

    def test_car_75000_returns_2400(self):
        """Car priced at RM75,000 returns RM2,400/year."""
        self.assertEqual(get_annual_car_bik(75_000), 2_400)

    def test_car_100000_returns_3600(self):
        """Car priced at RM100,000 returns RM3,600/year."""
        self.assertEqual(get_annual_car_bik(100_000), 3_600)

    def test_car_150000_returns_5000(self):
        """Car priced at exactly RM150,000 returns RM5,000/year."""
        self.assertEqual(get_annual_car_bik(150_000), 5_000)

    def test_car_200000_returns_7500(self):
        """Car priced at RM200,000 returns RM7,500/year."""
        self.assertEqual(get_annual_car_bik(200_000), 7_500)

    def test_car_250000_returns_10000(self):
        """Car priced at RM250,000 returns RM10,000/year."""
        self.assertEqual(get_annual_car_bik(250_000), 10_000)

    def test_car_350000_returns_15000(self):
        """Car priced at RM350,000 returns RM15,000/year."""
        self.assertEqual(get_annual_car_bik(350_000), 15_000)

    def test_car_500000_returns_20000(self):
        """Car priced at RM500,000 returns RM20,000/year."""
        self.assertEqual(get_annual_car_bik(500_000), 20_000)

    def test_car_750000_returns_25000(self):
        """Car priced at RM750,000 returns RM25,000/year."""
        self.assertEqual(get_annual_car_bik(750_000), 25_000)

    def test_car_above_750000_returns_50000(self):
        """Car priced above RM750,000 returns maximum RM50,000/year."""
        self.assertEqual(get_annual_car_bik(1_000_000), 50_000)
        self.assertEqual(get_annual_car_bik(2_000_000), 50_000)

    def test_car_zero_price_returns_zero(self):
        """Car price of 0 returns 0 (no car benefit)."""
        self.assertEqual(get_annual_car_bik(0), 0.0)

    def test_car_intermediate_price(self):
        """Car priced between brackets uses upper bracket.

        RM130,000 is between RM100,001 and RM150,000 → RM5,000/year.
        """
        self.assertEqual(get_annual_car_bik(130_000), 5_000)

    def test_returns_float(self):
        """Return type is always float."""
        result = get_annual_car_bik(100_000)
        self.assertIsInstance(result, float)


# ---------------------------------------------------------------------------
# Tests — CAR_BIK_TABLE and constants
# ---------------------------------------------------------------------------

class TestBIKConstants(FrappeTestCase):
    """BIK constants match LHDN prescribed values."""

    def test_fuel_bik_monthly_is_300(self):
        """LHDN prescribed fuel BIK is RM300/month."""
        self.assertEqual(FUEL_BIK_MONTHLY, 300)

    def test_driver_bik_monthly_is_600(self):
        """LHDN prescribed driver BIK is RM600/month."""
        self.assertEqual(DRIVER_BIK_MONTHLY, 600)

    def test_car_bik_table_has_9_brackets(self):
        """CAR_BIK_TABLE has 9 price brackets (up to RM750,000)."""
        self.assertEqual(len(CAR_BIK_TABLE), 9)

    def test_car_bik_table_minimum_bik_is_1200(self):
        """Minimum prescribed car BIK is RM1,200/year."""
        self.assertEqual(min(CAR_BIK_TABLE.values()), 1_200)

    def test_car_bik_table_maximum_bracket_is_750000(self):
        """Maximum price bracket in table is RM750,000."""
        self.assertEqual(max(CAR_BIK_TABLE.keys()), 750_000)


# ---------------------------------------------------------------------------
# Tests — calculate_monthly_bik_total()
# ---------------------------------------------------------------------------

class TestCalculateMonthlyBIKTotal(FrappeTestCase):
    """calculate_monthly_bik_total() returns correct monthly BIK from DB."""

    @patch("lhdn_payroll_integration.services.bik_calculator.frappe")
    def test_returns_zero_when_no_bik_record(self, mock_frappe):
        """Returns 0.0 when no Employee BIK Record exists for the employee/year."""
        mock_frappe.db.get_value.return_value = None

        result = calculate_monthly_bik_total("EMP-001", 2024)

        self.assertEqual(result, 0.0)

    @patch("lhdn_payroll_integration.services.bik_calculator.frappe")
    def test_returns_monthly_bik_from_record(self, mock_frappe):
        """Returns total_monthly_bik from the Employee BIK Record."""
        mock_frappe.db.get_value.return_value = "BIK-EMP-001-2024"
        mock_doc = MagicMock()
        mock_doc.total_monthly_bik = 1_000.0  # RM1,000/month
        mock_frappe.get_doc.return_value = mock_doc

        result = calculate_monthly_bik_total("EMP-001", 2024)

        self.assertEqual(result, 1_000.0)

    @patch("lhdn_payroll_integration.services.bik_calculator.frappe")
    def test_coerces_year_string_to_int(self, mock_frappe):
        """Year passed as string is coerced to int for DB lookup."""
        mock_frappe.db.get_value.return_value = None

        calculate_monthly_bik_total("EMP-001", "2024")

        mock_frappe.db.get_value.assert_called_once_with(
            "Employee BIK Record",
            {"employee": "EMP-001", "payroll_period_year": 2024},
            "name",
        )


# ---------------------------------------------------------------------------
# Tests — EmployeeBIKRecord._calculate_totals()
# ---------------------------------------------------------------------------

class TestEmployeeBIKRecordTotals(FrappeTestCase):
    """EmployeeBIKRecord._calculate_totals() computes correct annual/monthly totals."""

    def _make_mock_doc(self, **kwargs):
        doc = MagicMock(spec=EmployeeBIKRecord)
        defaults = {
            "car_purchase_price": 0,
            "car_bik_annual": 0,
            "fuel_bik_monthly": 0,
            "driver_bik_monthly": 0,
            "accommodation_bik_monthly": 0,
            "club_membership_annual": 0,
            "other_bik_annual": 0,
            "total_annual_bik": 0,
            "total_monthly_bik": 0,
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(doc, k, v)
        return doc

    def test_car_only_bik_annual(self):
        """Car BIK annual is included in total."""
        doc = self._make_mock_doc(car_bik_annual=5_000)
        EmployeeBIKRecord._calculate_totals(doc)
        self.assertAlmostEqual(doc.total_annual_bik, 5_000.0)
        self.assertAlmostEqual(doc.total_monthly_bik, round(5_000 / 12, 2))

    def test_fuel_and_driver_monthly_annualised(self):
        """Fuel and driver monthly BIK are annualised (x12) in total."""
        doc = self._make_mock_doc(fuel_bik_monthly=300, driver_bik_monthly=600)
        EmployeeBIKRecord._calculate_totals(doc)
        # fuel = 300*12 = 3600; driver = 600*12 = 7200; total = 10800
        self.assertAlmostEqual(doc.total_annual_bik, 10_800.0)
        self.assertAlmostEqual(doc.total_monthly_bik, 900.0)  # 10800/12

    def test_combined_all_bik_types(self):
        """All BIK types combined produce correct total."""
        doc = self._make_mock_doc(
            car_bik_annual=5_000,           # annual
            fuel_bik_monthly=300,           # monthly → 3600 annual
            driver_bik_monthly=600,         # monthly → 7200 annual
            accommodation_bik_monthly=500,  # monthly → 6000 annual
            club_membership_annual=2_000,   # annual
            other_bik_annual=1_000,         # annual
        )
        EmployeeBIKRecord._calculate_totals(doc)
        # total annual = 5000 + 3600 + 7200 + 6000 + 2000 + 1000 = 24800
        self.assertAlmostEqual(doc.total_annual_bik, 24_800.0)
        self.assertAlmostEqual(doc.total_monthly_bik, round(24_800 / 12, 2))

    def test_zero_bik_returns_zero_total(self):
        """All-zero BIK fields produce zero totals."""
        doc = self._make_mock_doc()
        EmployeeBIKRecord._calculate_totals(doc)
        self.assertEqual(doc.total_annual_bik, 0.0)
        self.assertEqual(doc.total_monthly_bik, 0.0)


# ---------------------------------------------------------------------------
# Tests — BIK increases PCB correctly
# ---------------------------------------------------------------------------

class TestBIKIncreasesPCB(FrappeTestCase):
    """BIK added to gross income correctly increases PCB computation."""

    def test_bik_increases_annual_income_for_pcb(self):
        """Adding monthly BIK to gross increases the annual income used for PCB."""
        # Annual income RM60,000 (RM5,000/month)
        annual_income_no_bik = 60_000.0
        # With BIK: RM1,000/month additional → annual = 72,000
        monthly_bik = 1_000.0
        annual_income_with_bik = (5_000 + monthly_bik) * 12  # 72,000

        pcb_no_bik = calculate_pcb(annual_income_no_bik, resident=True)
        pcb_with_bik = calculate_pcb(annual_income_with_bik, resident=True)

        self.assertGreater(pcb_with_bik, pcb_no_bik,
                           "PCB should increase when BIK is added to gross income")

    def test_bik_120000_car_correct_pcb_impact(self):
        """Car priced RM120,000 → RM5,000/year BIK → RM416.67/month.

        Acceptance criteria: car price RM120,000 returns correct annual BIK.
        The annual BIK should be RM5,000 per the LHDN table.
        Monthly BIK = 5000/12 ≈ 416.67.
        """
        annual_car_bik = get_annual_car_bik(120_000)
        self.assertEqual(annual_car_bik, 5_000.0)

        monthly_bik = annual_car_bik / 12
        self.assertAlmostEqual(monthly_bik, 416.67, places=1)

        # With BIK, PCB on RM5,000/month employee should be higher
        pcb_base = calculate_pcb(5_000 * 12, resident=True)  # RM5,000/month
        pcb_with_bik = calculate_pcb((5_000 + monthly_bik) * 12, resident=True)

        self.assertGreater(pcb_with_bik, pcb_base)

    def test_bik_total_increases_pcb_acceptance_criteria(self):
        """BIK total increases PCB correctly — acceptance criteria verification.

        Employee with RM8,000/month gross + RM5,000/year car BIK:
        - Monthly BIK = 5000/12 ≈ 416.67
        - Effective annual income = (8000 + 416.67) * 12 = 101,000
        - PCB should be higher than base (annual = 96,000)
        """
        base_monthly = 8_000
        car_bik_annual = get_annual_car_bik(120_000)  # RM5,000
        monthly_bik = car_bik_annual / 12

        pcb_base = calculate_pcb(base_monthly * 12, resident=True)
        pcb_with_bik = calculate_pcb((base_monthly + monthly_bik) * 12, resident=True)

        self.assertGreater(pcb_with_bik, pcb_base,
                           f"PCB with BIK ({pcb_with_bik:.2f}) should exceed base ({pcb_base:.2f})")


# ---------------------------------------------------------------------------
# Tests — get_employee_bik() whitelisted function
# ---------------------------------------------------------------------------

class TestGetEmployeeBIK(FrappeTestCase):
    """get_employee_bik() returns correct monthly/annual BIK data."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_bik_record.employee_bik_record.frappe")
    def test_returns_zeros_when_no_record(self, mock_frappe):
        """Returns zero monthly and annual BIK when no record exists."""
        mock_frappe.db.get_value.return_value = None

        result = get_employee_bik("EMP-001", 2024)

        self.assertEqual(result["monthly_bik"], 0.0)
        self.assertEqual(result["annual_bik"], 0.0)
        self.assertIsNone(result["docname"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_bik_record.employee_bik_record.frappe")
    def test_returns_values_from_record(self, mock_frappe):
        """Returns total_monthly_bik and total_annual_bik from the BIK record."""
        mock_frappe.db.get_value.return_value = "BIK-EMP-001-2024"
        mock_doc = MagicMock()
        mock_doc.total_monthly_bik = 416.67
        mock_doc.total_annual_bik = 5_000.0
        mock_frappe.get_doc.return_value = mock_doc

        result = get_employee_bik("EMP-001", 2024)

        self.assertAlmostEqual(result["monthly_bik"], 416.67, places=2)
        self.assertAlmostEqual(result["annual_bik"], 5_000.0, places=2)
        self.assertEqual(result["docname"], "BIK-EMP-001-2024")


# ---------------------------------------------------------------------------
# Tests — get_annual_bik_for_ea_form()
# ---------------------------------------------------------------------------

class TestGetAnnualBIKForEAForm(FrappeTestCase):
    """get_annual_bik_for_ea_form() returns annual BIK for EA Form B7."""

    @patch("lhdn_payroll_integration.services.bik_calculator.frappe")
    def test_returns_zero_when_no_record(self, mock_frappe):
        """Returns 0.0 when no BIK record exists."""
        mock_frappe.db.get_value.return_value = None

        result = get_annual_bik_for_ea_form("EMP-001", 2024)

        self.assertEqual(result, 0.0)

    @patch("lhdn_payroll_integration.services.bik_calculator.frappe")
    def test_returns_annual_bik_from_record(self, mock_frappe):
        """Returns total_annual_bik from the matching BIK record."""
        mock_frappe.db.get_value.return_value = "BIK-EMP-001-2024"
        mock_doc = MagicMock()
        mock_doc.total_annual_bik = 5_000.0
        mock_frappe.get_doc.return_value = mock_doc

        result = get_annual_bik_for_ea_form("EMP-001", 2024)

        self.assertAlmostEqual(result, 5_000.0, places=2)
