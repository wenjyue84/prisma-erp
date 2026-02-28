

class TestCalculatePcbZakatOffset(FrappeTestCase):
    """Test calculate_pcb() with annual_zakat (US-053 — ITA 1967 s.6A(3)).

    Zakat is a ringgit-for-ringgit PCB credit, NOT a reduction in chargeable
    income. The offset is applied AFTER progressive tax computation:
        net_pcb = max(0, gross_monthly_pcb - annual_zakat / 12)
    """

    def test_zakat_reduces_pcb_ringgit_for_ringgit(self):
        """Annual Zakat / 12 is subtracted from monthly PCB.

        annual_income = 60,000; single resident
        gross_monthly_pcb = 1930 / 12 ≈ 160.83
        annual_zakat = 1,200 → monthly_zakat = 100
        net_pcb = 160.83 - 100 = 60.83
        """
        annual = 60_000
        gross_pcb = calculate_pcb(annual, resident=True)
        net_pcb = calculate_pcb(annual, resident=True, annual_zakat=1_200)
        expected_net = round(gross_pcb - 100.0, 2)
        self.assertAlmostEqual(net_pcb, expected_net, places=2)

    def test_zero_zakat_does_not_change_pcb(self):
        """Passing annual_zakat=0 returns same PCB as default."""
        annual = 60_000
        pcb_default = calculate_pcb(annual, resident=True)
        pcb_zero_zakat = calculate_pcb(annual, resident=True, annual_zakat=0)
        self.assertAlmostEqual(pcb_default, pcb_zero_zakat, places=2)

    def test_pcb_never_goes_negative(self):
        """PCB is floored at 0 even when Zakat exceeds gross PCB.

        annual_income = 20,000; single resident; gross_monthly_pcb = 5.00
        annual_zakat = 10,000 → monthly_zakat = 833.33 >> 5.00
        net_pcb = max(0, 5.00 - 833.33) = 0.0
        """
        annual = 20_000
        net_pcb = calculate_pcb(annual, resident=True, annual_zakat=10_000)
        self.assertEqual(net_pcb, 0.0)

    def test_zakat_matching_monthly_pcb_yields_zero(self):
        """When monthly_zakat == gross_monthly_pcb, net PCB is exactly 0."""
        annual = 60_000
        gross_monthly = calculate_pcb(annual, resident=True)  # 1930/12 ≈ 160.83
        annual_zakat = round(gross_monthly * 12, 2)  # exactly cancel out monthly PCB
        net_pcb = calculate_pcb(annual, resident=True, annual_zakat=annual_zakat)
        self.assertEqual(net_pcb, 0.0)

    def test_zakat_is_not_deducted_from_chargeable_income(self):
        """Zakat is a PCB credit, not a relief — chargeable income is unchanged.

        Verify by comparing: if Zakat were a relief, PCB reduction would follow
        the marginal tax rate (e.g. 1% band). But ringgit-for-ringgit means
        RM100/month Zakat => RM100/month PCB reduction exactly.
        """
        annual = 60_000
        annual_zakat = 1_200  # RM100/month
        gross_pcb = calculate_pcb(annual, resident=True)
        net_pcb = calculate_pcb(annual, resident=True, annual_zakat=annual_zakat)
        reduction = round(gross_pcb - net_pcb, 2)
        # Exact ringgit-for-ringgit: reduction should equal 100.00
        self.assertAlmostEqual(reduction, 100.0, places=2)

    def test_zakat_combined_with_married_children_reliefs(self):
        """Zakat offset stacks with standard reliefs correctly."""
        annual = 60_000
        pcb_married = calculate_pcb(annual, resident=True, married=True, children=2)
        pcb_zakat = calculate_pcb(annual, resident=True, married=True, children=2, annual_zakat=600)
        expected_net = round(pcb_married - 50.0, 2)  # 600/12 = 50 offset
        self.assertAlmostEqual(pcb_zakat, max(0.0, expected_net), places=2)

    def test_zakat_combined_with_tp1_reliefs(self):
        """Zakat offset applies after TP1 reliefs (which reduce chargeable income)."""
        annual = 120_000
        pcb_no_extras = calculate_pcb(annual, resident=True)
        pcb_tp1_only = calculate_pcb(annual, resident=True, tp1_total_reliefs=10_000)
        pcb_tp1_zakat = calculate_pcb(annual, resident=True, tp1_total_reliefs=10_000, annual_zakat=1_200)
        # Zakat further reduces PCB below TP1-only level
        self.assertGreater(pcb_no_extras, pcb_tp1_only)
        self.assertGreater(pcb_tp1_only, pcb_tp1_zakat)

    def test_zakat_combined_with_bonus(self):
        """Zakat offset applies to the combined regular + bonus PCB."""
        annual = 60_000
        bonus = 10_000
        gross_pcb_bonus = calculate_pcb(annual, resident=True, bonus_amount=bonus)
        net_pcb_bonus_zakat = calculate_pcb(
            annual, resident=True, bonus_amount=bonus, annual_zakat=1_200
        )
        reduction = round(gross_pcb_bonus - net_pcb_bonus_zakat, 2)
        self.assertAlmostEqual(reduction, 100.0, places=2)

    def test_zakat_non_resident_also_offset(self):
        """Non-resident Zakat offset: applied after flat 30% computation."""
        annual = 60_000
        annual_zakat = 1_200  # 100/month
        gross_nr = calculate_pcb(annual, resident=False)
        net_nr = calculate_pcb(annual, resident=False, annual_zakat=annual_zakat)
        self.assertAlmostEqual(gross_nr - net_nr, 100.0, places=2)

    def test_zakat_high_income_large_offset(self):
        """Large Zakat amount reduces high PCB significantly (not below 0)."""
        annual = 500_000
        annual_zakat = 24_000  # RM2,000/month
        gross_pcb = calculate_pcb(annual, resident=True)
        net_pcb = calculate_pcb(annual, resident=True, annual_zakat=annual_zakat)
        self.assertGreater(gross_pcb, net_pcb)
        reduction = round(gross_pcb - net_pcb, 2)
        self.assertAlmostEqual(reduction, 2_000.0, places=2)
        self.assertGreaterEqual(net_pcb, 0.0)
