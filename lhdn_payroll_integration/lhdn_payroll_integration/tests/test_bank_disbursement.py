"""Tests for US-071 + US-089: Payroll Bank Disbursement File Generator.

Acceptance criteria (US-071):
  - Maybank format: pipe-delimited with ORG_CODE|PAY_DATE header + 6-field detail lines
  - CIMB format: Header (H|), Detail (D|), Footer (T|) structure
  - DuitNow: ISO 20022 pain.001.001.03 XML with SALA purpose code
  - Unsupported bank raises ValidationError

Acceptance criteria (US-089):
  - generate_duitnow_bulk_xml(payroll_entry_name) generates ISO 20022 pain.001.001.03 XML
  - <PmtInf>/<PmtTpInf>/<CtgyPurp>/<Cd>SALA</Cd> mandatory purpose code
  - <CdtTrfTxInf>/<Cdtr>/<Id> uses DuitNow ID (NRIC or registered mobile)
  - <EndToEndId> unique per transaction max 35 chars
"""
from unittest.mock import patch, MagicMock

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service import (
    SUPPORTED_BANKS,
    generate_bank_file,
    generate_duitnow_bulk_xml,
    _generate_maybank_file,
    _generate_cimb_file,
    _generate_duitnow_file,
    _format_date_yyyymmdd,
    _xml_escape,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_slip(employee="EMP-001", name="Ahmad Bin Ali", bank_code="12345678901234567890",
               nric="901231145678", net_pay=3500.00):
    """Return a mock salary slip frappe._dict."""
    return frappe._dict({
        "name": f"SAL-{employee}",
        "employee": employee,
        "employee_name": name,
        "custom_bank_code": bank_code,
        "custom_nric": nric,
        "custom_bank_name": "Maybank",
        "custom_account_type": "Savings",
        "net_pay": net_pay,
    })


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestSupportedBanks(FrappeTestCase):
    """Verify SUPPORTED_BANKS list."""

    def test_supported_banks_contains_maybank(self):
        self.assertIn("Maybank", SUPPORTED_BANKS)

    def test_supported_banks_contains_cimb(self):
        self.assertIn("CIMB", SUPPORTED_BANKS)

    def test_supported_banks_contains_duitnow(self):
        self.assertIn("DuitNow Bulk", SUPPORTED_BANKS)

    def test_supported_banks_contains_public_bank(self):
        self.assertIn("Public Bank", SUPPORTED_BANKS)

    def test_supported_banks_contains_rhb(self):
        self.assertIn("RHB", SUPPORTED_BANKS)


# ---------------------------------------------------------------------------
# Maybank M2E format — _generate_maybank_file(slips, org_code, date)
# ---------------------------------------------------------------------------

class TestMaybankFormat(FrappeTestCase):
    """Verify Maybank M2E pipe-delimited format."""

    ORG_CODE = "12345"
    PAY_DATE = "20250630"

    def _make_slips(self):
        return [
            _make_slip("EMP-001", "Ahmad Bin Ali", "1234567890", "901231145678", 3500.00),
            _make_slip("EMP-002", "Siti Binti Hamid", "0987654321", "850615105432", 4200.50),
        ]

    def test_maybank_output_is_bytes(self):
        """_generate_maybank_file returns bytes."""
        result = _generate_maybank_file(self._make_slips(), self.ORG_CODE, self.PAY_DATE)
        self.assertIsInstance(result, bytes)

    def test_maybank_header_has_two_fields(self):
        """First line must be ORG_CODE|PAY_DATE (exactly 2 pipe-separated fields)."""
        content = _generate_maybank_file(
            self._make_slips(), self.ORG_CODE, self.PAY_DATE
        ).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        header = lines[0]
        parts = header.split("|")
        self.assertEqual(len(parts), 2, f"Header should have 2 parts: {header}")

    def test_maybank_header_contains_org_code(self):
        """Header must include the org code."""
        content = _generate_maybank_file(
            self._make_slips(), self.ORG_CODE, self.PAY_DATE
        ).decode("utf-8")
        header = [ln for ln in content.splitlines() if ln][0]
        self.assertIn(self.ORG_CODE, header)

    def test_maybank_header_contains_date(self):
        """Header must include the pay date."""
        content = _generate_maybank_file(
            self._make_slips(), self.ORG_CODE, self.PAY_DATE
        ).decode("utf-8")
        header = [ln for ln in content.splitlines() if ln][0]
        self.assertIn(self.PAY_DATE, header)

    def test_maybank_detail_lines_have_six_fields(self):
        """Each detail line must have 6 pipe-separated fields: ORG|DATE|NAME|NRIC|ACCOUNT|AMOUNT."""
        content = _generate_maybank_file(
            self._make_slips(), self.ORG_CODE, self.PAY_DATE
        ).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        for detail in lines[1:]:
            parts = detail.split("|")
            self.assertEqual(
                len(parts), 6,
                f"Detail line must have 6 fields: {detail}"
            )

    def test_maybank_detail_amount_is_decimal(self):
        """Amount field in detail line must be formatted as 2dp decimal."""
        slips = [_make_slip(net_pay=3500.00)]
        content = _generate_maybank_file(slips, self.ORG_CODE, self.PAY_DATE).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        detail = lines[1]
        amount_str = detail.split("|")[-1]
        self.assertAlmostEqual(float(amount_str), 3500.00, places=2)

    def test_maybank_detail_count_matches_slip_count(self):
        """Number of detail lines must equal number of salary slips."""
        slips = self._make_slips()
        content = _generate_maybank_file(slips, self.ORG_CODE, self.PAY_DATE).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        self.assertEqual(len(lines) - 1, len(slips))

    def test_maybank_pipe_delimiter_in_all_lines(self):
        """All non-empty lines must contain the pipe delimiter."""
        content = _generate_maybank_file(
            self._make_slips(), self.ORG_CODE, self.PAY_DATE
        ).decode("utf-8")
        for line in content.splitlines():
            if line:
                self.assertIn("|", line, f"Pipe delimiter missing in line: {line}")

    def test_maybank_empty_slips_has_header_only(self):
        """With no slips, output contains only the header line."""
        content = _generate_maybank_file([], self.ORG_CODE, self.PAY_DATE).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        self.assertEqual(len(lines), 1, "Empty slips should produce header only")

    def test_maybank_name_pipe_chars_replaced(self):
        """Pipe chars in employee name must be replaced to preserve 6-field format."""
        slips = [_make_slip(name="Ahmad|Ali")]
        content = _generate_maybank_file(slips, self.ORG_CODE, self.PAY_DATE).decode("utf-8")
        detail = content.splitlines()[1]
        parts = detail.split("|")
        self.assertEqual(len(parts), 6, "Name with | should still produce 6 fields")


# ---------------------------------------------------------------------------
# CIMB BizChannel format — _generate_cimb_file(slips, org_code, date)
# ---------------------------------------------------------------------------

class TestCIMBFormat(FrappeTestCase):
    """Verify CIMB BizChannel Header/Detail/Footer structure."""

    ORG_CODE = "ORG001"
    PAY_DATE = "20250630"

    def _make_slips(self):
        return [
            _make_slip("EMP-001", "Ahmad Bin Ali", "1234567890", net_pay=3500.00),
            _make_slip("EMP-002", "Siti Binti Hamid", "0987654321", net_pay=4200.50),
        ]

    def test_cimb_output_is_bytes(self):
        result = _generate_cimb_file(self._make_slips(), self.ORG_CODE, self.PAY_DATE)
        self.assertIsInstance(result, bytes)

    def test_cimb_first_line_starts_with_H(self):
        """First line must start with 'H|'."""
        content = _generate_cimb_file(
            self._make_slips(), self.ORG_CODE, self.PAY_DATE
        ).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        self.assertTrue(lines[0].startswith("H|"), f"Header should start with 'H|': {lines[0]}")

    def test_cimb_last_line_starts_with_T(self):
        """Last line must start with 'T|'."""
        content = _generate_cimb_file(
            self._make_slips(), self.ORG_CODE, self.PAY_DATE
        ).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        self.assertTrue(lines[-1].startswith("T|"), f"Footer should start with 'T|': {lines[-1]}")

    def test_cimb_detail_lines_start_with_D(self):
        """Detail lines must start with 'D|'."""
        slips = self._make_slips()
        content = _generate_cimb_file(slips, self.ORG_CODE, self.PAY_DATE).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        detail_lines = lines[1:-1]  # exclude header and footer
        self.assertEqual(len(detail_lines), len(slips))
        for line in detail_lines:
            self.assertTrue(line.startswith("D|"), f"Detail should start with 'D|': {line}")

    def test_cimb_header_has_three_fields(self):
        """Header line H|date|org_code must have exactly 3 fields."""
        content = _generate_cimb_file(
            self._make_slips(), self.ORG_CODE, self.PAY_DATE
        ).decode("utf-8")
        header = [ln for ln in content.splitlines() if ln][0]
        parts = header.split("|")
        self.assertEqual(len(parts), 3, f"Header should have 3 fields: {header}")

    def test_cimb_detail_has_four_fields(self):
        """Detail line D|name|account|amount must have exactly 4 fields."""
        content = _generate_cimb_file(
            self._make_slips(), self.ORG_CODE, self.PAY_DATE
        ).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        detail = lines[1]
        parts = detail.split("|")
        self.assertEqual(len(parts), 4, f"Detail should have 4 fields: {detail}")

    def test_cimb_footer_count_correct(self):
        """Footer count field must equal number of detail records."""
        slips = self._make_slips()
        content = _generate_cimb_file(slips, self.ORG_CODE, self.PAY_DATE).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        footer = lines[-1]
        count = int(footer.split("|")[1])
        self.assertEqual(count, len(slips))

    def test_cimb_footer_total_correct(self):
        """Footer total must equal sum of all net_pay amounts."""
        slips = self._make_slips()
        expected_total = sum(s.net_pay for s in slips)
        content = _generate_cimb_file(slips, self.ORG_CODE, self.PAY_DATE).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        footer = lines[-1]
        total = float(footer.split("|")[2])
        self.assertAlmostEqual(total, expected_total, places=2)

    def test_cimb_empty_slips_has_header_and_footer_only(self):
        """With no slips, output has header + footer only (2 lines)."""
        content = _generate_cimb_file([], self.ORG_CODE, self.PAY_DATE).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("H|"))
        self.assertTrue(lines[1].startswith("T|"))

    def test_cimb_empty_footer_has_zero_count_and_total(self):
        """Empty slips footer shows count=0, total=0.00."""
        content = _generate_cimb_file([], self.ORG_CODE, self.PAY_DATE).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln]
        footer = lines[-1]
        parts = footer.split("|")
        self.assertEqual(parts[1], "0")
        self.assertEqual(parts[2], "0.00")


# ---------------------------------------------------------------------------
# DuitNow Bulk — _generate_duitnow_file(slips, company_name, date)
# ---------------------------------------------------------------------------

class TestDuitNowFormat(FrappeTestCase):
    """Verify DuitNow Bulk ISO 20022 pain.001.001.03 format."""

    def _make_slips(self):
        return [_make_slip("EMP-001", "Ahmad Bin Ali", "1234567890", net_pay=3500.00)]

    def test_duitnow_output_is_bytes(self):
        result = _generate_duitnow_file(self._make_slips(), "Test Company", "2025-06-30")
        self.assertIsInstance(result, bytes)

    def test_duitnow_is_valid_xml(self):
        """Output must be parseable XML."""
        import xml.etree.ElementTree as ET
        content = _generate_duitnow_file(self._make_slips(), "Test Company", "2025-06-30")
        # Should not raise ParseError
        root = ET.fromstring(content.decode("utf-8"))
        self.assertIsNotNone(root)

    def test_duitnow_has_pain001_namespace(self):
        """XML must use the ISO 20022 pain.001.001.03 namespace."""
        content = _generate_duitnow_file(
            self._make_slips(), "Test Company", "2025-06-30"
        ).decode("utf-8")
        self.assertIn("pain.001.001.03", content)

    def test_duitnow_has_sala_purpose_code(self):
        """XML must include SALA purpose code for salary payments."""
        content = _generate_duitnow_file(
            self._make_slips(), "Test Company", "2025-06-30"
        ).decode("utf-8")
        self.assertIn("SALA", content)

    def test_duitnow_contains_employee_amount(self):
        """XML must include the employee's net pay amount."""
        slips = [_make_slip(net_pay=3500.00)]
        content = _generate_duitnow_file(slips, "Test Company", "2025-06-30").decode("utf-8")
        self.assertIn("3500.00", content)

    def test_duitnow_contains_instd_amt_myr(self):
        """XML must specify MYR currency."""
        content = _generate_duitnow_file(
            self._make_slips(), "Test Company", "2025-06-30"
        ).decode("utf-8")
        self.assertIn('Ccy="MYR"', content)

    def test_duitnow_nb_of_txs_matches_slip_count(self):
        """NbOfTxs element must match number of salary slips."""
        slips = self._make_slips()
        content = _generate_duitnow_file(slips, "Test Company", "2025-06-30").decode("utf-8")
        self.assertIn(f"<NbOfTxs>{len(slips)}</NbOfTxs>", content)

    def test_duitnow_empty_slips_nb_of_txs_zero(self):
        """With no slips, NbOfTxs must be 0."""
        content = _generate_duitnow_file([], "Test Company", "2025-06-30").decode("utf-8")
        self.assertIn("<NbOfTxs>0</NbOfTxs>", content)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestHelpers(FrappeTestCase):
    """Verify utility helper functions."""

    def test_format_date_string_with_dashes(self):
        self.assertEqual(_format_date_yyyymmdd("2025-06-30"), "20250630")

    def test_format_date_string_already_compact(self):
        self.assertEqual(_format_date_yyyymmdd("20250630"), "20250630")

    def test_format_date_date_object(self):
        from datetime import date as date_type
        self.assertEqual(_format_date_yyyymmdd(date_type(2025, 6, 30)), "20250630")

    def test_xml_escape_ampersand(self):
        self.assertEqual(_xml_escape("A&B"), "A&amp;B")

    def test_xml_escape_lt(self):
        self.assertEqual(_xml_escape("<name>"), "&lt;name&gt;")

    def test_xml_escape_empty(self):
        self.assertEqual(_xml_escape(""), "")

    def test_xml_escape_none(self):
        self.assertEqual(_xml_escape(None), "")


# ---------------------------------------------------------------------------
# generate_bank_file routing and validation
# ---------------------------------------------------------------------------

class TestGenerateBankFileRouting(FrappeTestCase):
    """Verify generate_bank_file dispatches correctly and validates bank."""

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service.frappe"
    )
    def test_unsupported_bank_calls_throw(self, mock_frappe):
        """generate_bank_file with unsupported bank must call frappe.throw."""
        mock_frappe.throw.side_effect = frappe.ValidationError("unsupported bank")
        with self.assertRaises(frappe.ValidationError):
            generate_bank_file("PE-001", "FakeBank")
        mock_frappe.throw.assert_called_once()

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service._get_salary_slips"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service._get_company_field"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service.frappe"
    )
    def test_maybank_routing_returns_bytes(self, mock_frappe, mock_get_field, mock_get_slips):
        """generate_bank_file with Maybank returns bytes."""
        mock_entry = MagicMock()
        mock_entry.company = "Test Company"
        mock_frappe.get_doc.return_value = mock_entry
        mock_frappe.db.get_value.return_value = "Test Company"
        mock_get_field.return_value = "12345"

        mock_get_slips.return_value = [
            frappe._dict({
                "name": "SAL-001",
                "employee": "EMP-001",
                "employee_name": "Ahmad Ali",
                "custom_bank_code": "1234567890",
                "custom_nric": "901231145678",
                "custom_bank_name": "Maybank",
                "custom_account_type": "Savings",
                "net_pay": 3500.00,
            })
        ]

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service.today",
            return_value="2025-06-30",
        ):
            result = generate_bank_file("PE-001", "Maybank")

        self.assertIsInstance(result, bytes)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service._get_salary_slips"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service._get_company_field"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service.frappe"
    )
    def test_cimb_routing_returns_bytes(self, mock_frappe, mock_get_field, mock_get_slips):
        """generate_bank_file with CIMB returns bytes."""
        mock_entry = MagicMock()
        mock_entry.company = "Test Company"
        mock_frappe.get_doc.return_value = mock_entry
        mock_frappe.db.get_value.return_value = "Test Company"
        mock_get_field.return_value = "ORG001"

        mock_get_slips.return_value = [
            frappe._dict({
                "name": "SAL-001",
                "employee": "EMP-001",
                "employee_name": "Ahmad Ali",
                "custom_bank_code": "1234567890",
                "custom_nric": "901231145678",
                "custom_bank_name": "CIMB",
                "custom_account_type": "Current",
                "net_pay": 3500.00,
            })
        ]

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service.today",
            return_value="2025-06-30",
        ):
            result = generate_bank_file("PE-001", "CIMB")

        self.assertIsInstance(result, bytes)


# ---------------------------------------------------------------------------
# US-089: generate_duitnow_bulk_xml — ISO 20022 pain.001.001.03 with SALA
# ---------------------------------------------------------------------------

_MOCK_SLIPS_089 = [
    frappe._dict({
        "name": "SAL-2025-001",
        "employee": "EMP-001",
        "employee_name": "Ahmad Bin Ali",
        "custom_bank_code": "12345678901234567890",
        "custom_nric": "901231145678",
        "custom_bank_name": "Maybank",
        "custom_account_type": "Savings",
        "net_pay": 3500.00,
    }),
    frappe._dict({
        "name": "SAL-2025-002",
        "employee": "EMP-002",
        "employee_name": "Siti Binti Hamid",
        "custom_bank_code": "0987654321",
        "custom_nric": "850615105432",
        "custom_bank_name": "CIMB",
        "custom_account_type": "Current",
        "net_pay": 4200.50,
    }),
]


class TestDuitNowBulkXmlUS089(FrappeTestCase):
    """US-089: DuitNow Bulk ISO 20022 pain.001.001.03 with SALA purpose code.

    Tests for generate_duitnow_bulk_xml(payroll_entry_name).
    """

    def _run_generate(self):
        """Helper: call generate_duitnow_bulk_xml with mocked Frappe."""
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service.frappe"
        ) as mock_frappe, patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service._get_salary_slips",
            return_value=_MOCK_SLIPS_089,
        ), patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.bank_disbursement_service.today",
            return_value="2025-06-30",
        ):
            mock_entry = MagicMock()
            mock_entry.company = "Arising Packaging Sdn Bhd"
            mock_frappe.get_doc.return_value = mock_entry
            mock_frappe.db.get_value.return_value = "Arising Packaging Sdn Bhd"
            result = generate_duitnow_bulk_xml("PE-2025-001")
        return result

    def test_generate_duitnow_bulk_xml_returns_bytes(self):
        """generate_duitnow_bulk_xml must return bytes."""
        result = self._run_generate()
        self.assertIsInstance(result, bytes)

    def test_generated_xml_is_parseable(self):
        """Output must be valid XML parseable by ElementTree."""
        import xml.etree.ElementTree as ET
        content = self._run_generate()
        root = ET.fromstring(content.decode("utf-8"))
        self.assertIsNotNone(root)

    def test_pain001_namespace_present(self):
        """XML must declare the ISO 20022 pain.001.001.03 namespace."""
        content = self._run_generate().decode("utf-8")
        self.assertIn("pain.001.001.03", content)

    def test_ctgy_purp_sala_code_present(self):
        """<PmtInf>/<PmtTpInf>/<CtgyPurp>/<Cd>SALA</Cd> must be in output."""
        content = self._run_generate().decode("utf-8")
        self.assertIn("<CtgyPurp>", content)
        self.assertIn("<Cd>SALA</Cd>", content)

    def test_end_to_end_id_within_35_chars(self):
        """Every <EndToEndId> must be at most 35 characters (ISO 20022 limit)."""
        import xml.etree.ElementTree as ET
        content = self._run_generate()
        # Use string search since namespace makes ET path complex
        xml_text = content.decode("utf-8")
        import re
        end_to_end_ids = re.findall(r"<EndToEndId>(.+?)</EndToEndId>", xml_text)
        self.assertTrue(len(end_to_end_ids) > 0, "No EndToEndId elements found")
        for eid in end_to_end_ids:
            self.assertLessEqual(
                len(eid), 35,
                f"EndToEndId '{eid}' exceeds 35 chars (len={len(eid)})"
            )

    def test_end_to_end_id_contains_payroll_prefix(self):
        """EndToEndId must start with PAYROLL- prefix."""
        import re
        content = self._run_generate().decode("utf-8")
        end_to_end_ids = re.findall(r"<EndToEndId>(.+?)</EndToEndId>", content)
        for eid in end_to_end_ids:
            self.assertTrue(eid.startswith("PAYROLL-"), f"EndToEndId '{eid}' missing PAYROLL- prefix")

    def test_cdtr_id_contains_nric(self):
        """<Cdtr>/<Id> must include employee NRIC as DuitNow identifier."""
        content = self._run_generate().decode("utf-8")
        # First slip NRIC
        self.assertIn("901231145678", content)

    def test_myr_currency_present(self):
        """InstdAmt must specify MYR currency."""
        content = self._run_generate().decode("utf-8")
        self.assertIn('Ccy="MYR"', content)

    def test_nb_of_txs_matches_slip_count(self):
        """NbOfTxs in GrpHdr must match number of salary slips."""
        content = self._run_generate().decode("utf-8")
        self.assertIn(f"<NbOfTxs>{len(_MOCK_SLIPS_089)}</NbOfTxs>", content)

    def test_ctrl_sum_matches_total_pay(self):
        """CtrlSum must equal sum of net_pay across all slips."""
        content = self._run_generate().decode("utf-8")
        total = sum(s.net_pay for s in _MOCK_SLIPS_089)
        self.assertIn(f"<CtrlSum>{total:.2f}</CtrlSum>", content)


class TestDuitNowFileUpdatedForUS089(FrappeTestCase):
    """Verify _generate_duitnow_file internals match US-089 requirements."""

    def _slips(self):
        return [
            frappe._dict({
                "name": "SAL-ABCDEFGHIJ12345",  # 18-char name to test truncation
                "employee": "EMP-001",
                "employee_name": "Ahmad Bin Ali",
                "custom_bank_code": "1234567890",
                "custom_nric": "901231145678",
                "net_pay": 3500.00,
            })
        ]

    def test_ctgy_purp_not_purp(self):
        """DuitNow XML must use <CtgyPurp> tag (not <Purp>) for SALA code."""
        content = _generate_duitnow_file(self._slips(), "Test Corp", "2025-06-30").decode("utf-8")
        self.assertIn("<CtgyPurp>", content)
        self.assertNotIn("<Purp>", content)

    def test_end_to_end_id_uses_slip_name_and_yyyymm(self):
        """EndToEndId must be built from slip name and YYYYMM."""
        import re
        content = _generate_duitnow_file(self._slips(), "Test Corp", "2025-06-30").decode("utf-8")
        eids = re.findall(r"<EndToEndId>(.+?)</EndToEndId>", content)
        self.assertEqual(len(eids), 1)
        # Should contain YYYYMM suffix "202506"
        self.assertIn("202506", eids[0])

    def test_end_to_end_id_max_35_chars(self):
        """EndToEndId must be truncated to max 35 chars."""
        import re
        content = _generate_duitnow_file(self._slips(), "Test Corp", "2025-06-30").decode("utf-8")
        eids = re.findall(r"<EndToEndId>(.+?)</EndToEndId>", content)
        for eid in eids:
            self.assertLessEqual(len(eid), 35, f"EndToEndId '{eid}' exceeds 35 chars")

    def test_cdtr_id_contains_nric(self):
        """Cdtr/Id must embed the employee NRIC."""
        content = _generate_duitnow_file(self._slips(), "Test Corp", "2025-06-30").decode("utf-8")
        self.assertIn("901231145678", content)
