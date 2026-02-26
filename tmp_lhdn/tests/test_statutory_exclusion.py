

class TestStatutoryContributionExclusion(FrappeTestCase):
    """Tests that employer statutory contributions (EPF/SOCSO/EIS) are excluded from invoice lines."""

    def _make_salary_slip_with_statutory(self):
        """Create a mock Salary Slip with earnings AND employer statutory rows."""
        doc = MagicMock()
        doc.name = "SAL-SLP-STAT-001"
        doc.employee = "HR-EMP-00001"
        doc.employee_name = "Ahmad bin Abdullah"
        doc.net_pay = 5000
        doc.company = "Arising Packaging"
        doc.posting_date = "2026-01-31"
        doc.currency = "MYR"
        doc.conversion_rate = 1

        # Regular earnings
        basic = MagicMock()
        basic.salary_component = "Basic Salary"
        basic.amount = 4000
        basic.custom_lhdn_classification_code = "022 : Others"

        allowance = MagicMock()
        allowance.salary_component = "Allowance"
        allowance.amount = 1000
        allowance.custom_lhdn_classification_code = "022 : Others"

        # Employer statutory contributions (should be excluded)
        epf_employer = MagicMock()
        epf_employer.salary_component = "EPF - Employer"
        epf_employer.amount = 520
        epf_employer.custom_lhdn_classification_code = "022 : Others"

        socso_employer = MagicMock()
        socso_employer.salary_component = "SOCSO - Employer"
        socso_employer.amount = 69.05
        socso_employer.custom_lhdn_classification_code = "022 : Others"

        eis_employer = MagicMock()
        eis_employer.salary_component = "EIS - Employer"
        eis_employer.amount = 9.90
        eis_employer.custom_lhdn_classification_code = "022 : Others"

        doc.earnings = [basic, allowance, epf_employer, socso_employer, eis_employer]
        doc.deductions = []

        return doc

    def _make_employee(self):
        """Create a mock Employee doc."""
        emp = MagicMock()
        emp.custom_lhdn_tin = "IG12345678901"
        emp.custom_id_type = "NRIC"
        emp.custom_id_value = "901201145678"
        emp.employee_name = "Ahmad bin Abdullah"
        emp.custom_is_foreign_worker = 0
        emp.custom_state_code = "01"
        emp.custom_bank_account_number = None
        emp.custom_worker_type = "Employee"
        return emp

    def _make_company(self):
        """Create a mock Company doc."""
        company = MagicMock()
        company.custom_company_tin_number = "C12345678901"
        company.name = "Arising Packaging"
        company.company_name = "Arising Packaging Sdn Bhd"
        company.custom_state_code = "14"
        return company

    def _get_mock_frappe_side_effect(self, doc, emp, company):
        """Return a side_effect function for mock_frappe.get_doc."""
        def side_effect(dt, name=None):
            return {
                ("Salary Slip", "SAL-SLP-STAT-001"): doc,
                ("Employee", "HR-EMP-00001"): emp,
                ("Company", "Arising Packaging"): company,
            }.get((dt, name), MagicMock())
        return side_effect

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_employer_epf_not_in_invoice_lines(self, mock_frappe):
        """EPF - Employer must NOT appear as an InvoiceLine description."""
        doc = self._make_salary_slip_with_statutory()
        emp = self._make_employee()
        company = self._make_company()
        mock_frappe.get_doc.side_effect = self._get_mock_frappe_side_effect(doc, emp, company)

        xml_string = build_salary_slip_xml("SAL-SLP-STAT-001")
        root = ET.fromstring(xml_string)

        lines = root.findall(f".//{{{CAC_NS}}}InvoiceLine")
        descriptions = [
            line.find(f".//{{{CBC_NS}}}Description").text
            for line in lines
            if line.find(f".//{{{CBC_NS}}}Description") is not None
        ]
        self.assertNotIn("EPF - Employer", descriptions,
            "Employer EPF should not appear as an invoice line")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_employer_socso_not_in_invoice_lines(self, mock_frappe):
        """SOCSO - Employer must NOT appear as an InvoiceLine description."""
        doc = self._make_salary_slip_with_statutory()
        emp = self._make_employee()
        company = self._make_company()
        mock_frappe.get_doc.side_effect = self._get_mock_frappe_side_effect(doc, emp, company)

        xml_string = build_salary_slip_xml("SAL-SLP-STAT-001")
        root = ET.fromstring(xml_string)

        lines = root.findall(f".//{{{CAC_NS}}}InvoiceLine")
        descriptions = [
            line.find(f".//{{{CBC_NS}}}Description").text
            for line in lines
            if line.find(f".//{{{CBC_NS}}}Description") is not None
        ]
        self.assertNotIn("SOCSO - Employer", descriptions,
            "Employer SOCSO should not appear as an invoice line")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_employer_eis_not_in_invoice_lines(self, mock_frappe):
        """EIS - Employer must NOT appear as an InvoiceLine description."""
        doc = self._make_salary_slip_with_statutory()
        emp = self._make_employee()
        company = self._make_company()
        mock_frappe.get_doc.side_effect = self._get_mock_frappe_side_effect(doc, emp, company)

        xml_string = build_salary_slip_xml("SAL-SLP-STAT-001")
        root = ET.fromstring(xml_string)

        lines = root.findall(f".//{{{CAC_NS}}}InvoiceLine")
        descriptions = [
            line.find(f".//{{{CBC_NS}}}Description").text
            for line in lines
            if line.find(f".//{{{CBC_NS}}}Description") is not None
        ]
        self.assertNotIn("EIS - Employer", descriptions,
            "Employer EIS should not appear as an invoice line")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_only_earnings_components_appear_in_invoice_lines(self, mock_frappe):
        """Invoice line count must equal only non-statutory earnings rows (2 of 5)."""
        doc = self._make_salary_slip_with_statutory()
        emp = self._make_employee()
        company = self._make_company()
        mock_frappe.get_doc.side_effect = self._get_mock_frappe_side_effect(doc, emp, company)

        xml_string = build_salary_slip_xml("SAL-SLP-STAT-001")
        root = ET.fromstring(xml_string)

        lines = root.findall(f".//{{{CAC_NS}}}InvoiceLine")
        # 5 earnings rows total, but 3 are employer statutory -> expect 2 lines
        self.assertEqual(len(lines), 2,
            f"Expected 2 invoice lines (non-statutory only), got {len(lines)}")

    @patch("lhdn_payroll_integration.services.payload_builder.frappe")
    def test_custom_exclude_flag_removes_component(self, mock_frappe):
        """When custom_lhdn_exclude_from_invoice=1 on a component, that row is excluded."""
        doc = self._make_salary_slip_with_statutory()
        emp = self._make_employee()
        company = self._make_company()
        mock_frappe.get_doc.side_effect = self._get_mock_frappe_side_effect(doc, emp, company)

        # Simulate custom_lhdn_exclude_from_invoice flag on "Allowance"
        mock_frappe.db.get_value.side_effect = lambda dt, name, field: (
            1 if dt == "Salary Component" and name == "Allowance"
                and field == "custom_lhdn_exclude_from_invoice"
            else 0
        )

        xml_string = build_salary_slip_xml("SAL-SLP-STAT-001")
        root = ET.fromstring(xml_string)

        lines = root.findall(f".//{{{CAC_NS}}}InvoiceLine")
        descriptions = [
            line.find(f".//{{{CBC_NS}}}Description").text
            for line in lines
            if line.find(f".//{{{CBC_NS}}}Description") is not None
        ]
        # Allowance should be excluded by custom flag, statutory already excluded
        # Only Basic Salary should remain
        self.assertNotIn("Allowance", descriptions,
            "Component with custom_lhdn_exclude_from_invoice=1 should be excluded")
        self.assertEqual(len(lines), 1,
            f"Expected 1 invoice line (only Basic Salary), got {len(lines)}")
