

class TestSSTHandling(FrappeTestCase):
    """Tests that SST registration numbers appear correctly in PartyTaxScheme blocks."""

    def _make_salary_slip_doc(self):
        """Create a mock Salary Slip doc."""
        doc = MagicMock()
        doc.name = "SAL-SLP-SST-001"
        doc.employee = "HR-EMP-00001"
        doc.employee_name = "Ahmad bin Abdullah"
        doc.net_pay = 5000
        doc.company = "Arising Packaging"
        doc.posting_date = "2026-01-31"
        doc.currency = "MYR"
        doc.conversion_rate = 1

        earning = MagicMock()
        earning.salary_component = "Basic Salary"
        earning.amount = 5000
        earning.custom_lhdn_classification_code = "022 : Others"

        doc.earnings = [earning]
        doc.deductions = []

        return doc

    def _make_employee(self, sst_reg=None):
        """Create a mock Employee doc with optional SST registration."""
        emp = MagicMock()
        emp.custom_lhdn_tin = "IG12345678901"
        emp.custom_id_type = "NRIC"
        emp.custom_id_value = "901201145678"
        emp.employee_name = "Ahmad bin Abdullah"
        emp.custom_is_foreign_worker = 0
        emp.custom_state_code = "01"
        emp.custom_bank_account_number = None
        emp.custom_worker_type = "Employee"
        emp.custom_sst_registration_number = sst_reg
        return emp

    def _make_company(self, sst_reg=None):
        """Create a mock Company doc with optional SST registration."""
        company = MagicMock()
        company.custom_company_tin_number = "C12345678901"
        company.name = "Arising Packaging"
        company.company_name = "Arising Packaging Sdn Bhd"
        company.custom_state_code = "14"
        company.custom_sst_registration_number = sst_reg
        return company

    def _get_mock_frappe_side_effect(self, doc, emp, company):
        """Return a side_effect function for mock_frappe.get_doc."""
        def side_effect(dt, name=None):
            return {
                ("Salary Slip", "SAL-SLP-SST-001"): doc,
                ("Employee", "HR-EMP-00001"): emp,
                ("Company", "Arising Packaging"): company,
            }.get((dt, name), MagicMock())
        return side_effect

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_non_sst_supplier_shows_na_registration(self, mock_frappe):
        """Non-SST-registered employee should have RegistrationName='NA' in PartyTaxScheme."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee(sst_reg=None)
        company = self._make_company()
        mock_frappe.get_doc.side_effect = self._get_mock_frappe_side_effect(doc, emp, company)

        xml_string = build_salary_slip_xml("SAL-SLP-SST-001")
        root = ET.fromstring(xml_string)

        ns = {"cac": CAC_NS, "cbc": CBC_NS}
        supplier_tax_scheme = root.find(
            ".//cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:RegistrationName", ns
        )
        self.assertIsNotNone(supplier_tax_scheme,
            "AccountingSupplierParty must have PartyTaxScheme with RegistrationName")
        self.assertEqual(supplier_tax_scheme.text, "NA",
            "Non-SST-registered supplier should have RegistrationName='NA'")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_non_sst_scheme_id_is_na(self, mock_frappe):
        """Non-SST-registered employee should have TaxScheme/ID='NA'."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee(sst_reg=None)
        company = self._make_company()
        mock_frappe.get_doc.side_effect = self._get_mock_frappe_side_effect(doc, emp, company)

        xml_string = build_salary_slip_xml("SAL-SLP-SST-001")
        root = ET.fromstring(xml_string)

        ns = {"cac": CAC_NS, "cbc": CBC_NS}
        scheme_id = root.find(
            ".//cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cac:TaxScheme/cbc:ID", ns
        )
        self.assertIsNotNone(scheme_id,
            "AccountingSupplierParty must have PartyTaxScheme/TaxScheme/ID")
        self.assertEqual(scheme_id.text, "NA",
            "Non-SST-registered supplier TaxScheme/ID should be 'NA'")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_sst_supplier_registration_in_party_tax_scheme(self, mock_frappe):
        """SST-registered employee should have their SST number as RegistrationName."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee(sst_reg="A01-2345-67891012")
        company = self._make_company()
        mock_frappe.get_doc.side_effect = self._get_mock_frappe_side_effect(doc, emp, company)

        xml_string = build_salary_slip_xml("SAL-SLP-SST-001")
        root = ET.fromstring(xml_string)

        ns = {"cac": CAC_NS, "cbc": CBC_NS}
        supplier_tax_scheme = root.find(
            ".//cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:RegistrationName", ns
        )
        self.assertIsNotNone(supplier_tax_scheme,
            "AccountingSupplierParty must have PartyTaxScheme with RegistrationName")
        self.assertEqual(supplier_tax_scheme.text, "A01-2345-67891012",
            "SST-registered supplier should have their SST number as RegistrationName")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_sst_scheme_id_is_sst(self, mock_frappe):
        """SST-registered employee should have TaxScheme/ID='SST'."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee(sst_reg="A01-2345-67891012")
        company = self._make_company()
        mock_frappe.get_doc.side_effect = self._get_mock_frappe_side_effect(doc, emp, company)

        xml_string = build_salary_slip_xml("SAL-SLP-SST-001")
        root = ET.fromstring(xml_string)

        ns = {"cac": CAC_NS, "cbc": CBC_NS}
        scheme_id = root.find(
            ".//cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cac:TaxScheme/cbc:ID", ns
        )
        self.assertIsNotNone(scheme_id,
            "AccountingSupplierParty must have PartyTaxScheme/TaxScheme/ID")
        self.assertEqual(scheme_id.text, "SST",
            "SST-registered supplier TaxScheme/ID should be 'SST'")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_buyer_also_has_party_tax_scheme(self, mock_frappe):
        """AccountingCustomerParty (Company/Buyer) must also include PartyTaxScheme."""
        doc = self._make_salary_slip_doc()
        emp = self._make_employee()
        company = self._make_company(sst_reg="B02-9876-54321098")
        mock_frappe.get_doc.side_effect = self._get_mock_frappe_side_effect(doc, emp, company)

        xml_string = build_salary_slip_xml("SAL-SLP-SST-001")
        root = ET.fromstring(xml_string)

        ns = {"cac": CAC_NS, "cbc": CBC_NS}
        buyer_reg = root.find(
            ".//cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:RegistrationName", ns
        )
        self.assertIsNotNone(buyer_reg,
            "AccountingCustomerParty must have PartyTaxScheme with RegistrationName")
        self.assertEqual(buyer_reg.text, "B02-9876-54321098",
            "SST-registered buyer should have their SST number as RegistrationName")

        buyer_scheme = root.find(
            ".//cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cac:TaxScheme/cbc:ID", ns
        )
        self.assertIsNotNone(buyer_scheme,
            "AccountingCustomerParty must have PartyTaxScheme/TaxScheme/ID")
        self.assertEqual(buyer_scheme.text, "SST",
            "SST-registered buyer TaxScheme/ID should be 'SST'")
