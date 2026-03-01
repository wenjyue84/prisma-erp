"""LHDN Payroll Settings DocType controller (US-231).

Single DocType for storing app-wide LHDN payroll configuration,
including the active PCB Specification Version.
"""
import datetime

import frappe
from frappe.model.document import Document

from lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_spec_service import (
    get_spec_changelog,
    get_spec_url_for_version,
)

# Known LHDN spec PDF URLs per year
_SPEC_URLS = {
    "2024": "",
    "2025": "https://www.hasil.gov.my/media/mdahzjwi/spesifikasi-kaedah-pengiraan-berkomputer-pcb-2025.pdf",
    "2026": "https://www.hasil.gov.my/media/arvlrzh5/spesifikasi-kaedah-pengiraan-berkomputer-pcb-2026.pdf",
}


class LHDNPayrollSettings(Document):
    def before_save(self):
        """Auto-populate URL and show checklist warning when version changes."""
        # Auto-fill URL for known versions
        if self.pcb_specification_version in _SPEC_URLS:
            url = _SPEC_URLS[self.pcb_specification_version]
            if url and not self.pcb_specification_url:
                self.pcb_specification_url = url

        # Detect version change and show checklist
        try:
            old_doc = frappe.get_doc("LHDN Payroll Settings", "LHDN Payroll Settings")
            old_version = old_doc.pcb_specification_version
        except Exception:
            old_version = None

        new_version = self.pcb_specification_version

        if old_version and new_version and old_version != new_version:
            try:
                from_year = int(old_version)
                to_year = int(new_version)
                if from_year < to_year:
                    changes = get_spec_changelog(from_year, to_year)
                elif from_year > to_year:
                    changes = get_spec_changelog(to_year, from_year)
                else:
                    changes = []
            except (ValueError, TypeError):
                changes = []

            if changes:
                checklist = "\n".join(f"• {c}" for c in changes)
                frappe.msgprint(
                    f"<b>PCB Specification Version Change: {old_version} → {new_version}</b><br><br>"
                    f"Please review the following changed parameters before confirming:<br><pre>{checklist}</pre>"
                    f"<br>HR Administrator must verify all items against the LHDN published specification.",
                    title="PCB Specification Checklist — Review Required",
                    indicator="orange",
                )
