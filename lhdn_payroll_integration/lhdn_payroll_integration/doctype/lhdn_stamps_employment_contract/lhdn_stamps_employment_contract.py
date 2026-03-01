"""LHDN STAMPS Employment Contract DocType controller.

US-150: LHDN STAMPS Employment Contract Digital Stamp Status Tracker
Tracks stamping compliance for employment contracts via stamps.hasil.gov.my.

Fixed stamp duty: RM10 per employment contract.
First Schedule, Stamp Act 1949.
"""
import frappe
from frappe.model.document import Document

STAMPS_PORTAL_URL = "https://stamps.hasil.gov.my"
STAMP_AMOUNT_DEFAULT = 10.0
PRE_STAMPS_YEAR = 2021


class LHDNSTAMPSEmploymentContract(Document):
    def before_save(self):
        """Compute status and stamp amount before saving."""
        self.stamp_amount = STAMP_AMOUNT_DEFAULT
        self._update_status()

    def after_insert(self):
        """Create a pending HR task when contract has no stamp reference."""
        if not self.stamp_reference_number and not self.legacy_stamped:
            self._create_stamp_task()

    def on_update(self):
        """Resolve the pending task when stamp reference is provided."""
        if self.stamp_reference_number and self.task_name:
            self._resolve_stamp_task()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_status(self):
        """Compute Stamping Status based on current field values."""
        if self.legacy_stamped:
            self.status = "Legacy Stamped"
        elif self.stamp_reference_number:
            self.status = "Stamped"
        else:
            self.status = "Pending"

    def _create_stamp_task(self):
        """Create a ToDo task prompting HR to stamp the contract."""
        description = (
            f"Stamp employment contract via LHDN STAMPS ({STAMPS_PORTAL_URL})\n\n"
            f"Employee: {self.employee_name or self.employee}\n"
            f"Contract Start: {self.contract_start_date}\n"
            f"Stamp Amount: RM{STAMP_AMOUNT_DEFAULT:.0f}\n\n"
            f"Steps:\n"
            f"1. Visit {STAMPS_PORTAL_URL}\n"
            f"2. Select instrument type: 'Contract of Employment'\n"
            f"3. Pay RM10 via FPX\n"
            f"4. Enter the stamp reference number in this record"
        )
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "status": "Open",
            "priority": "Medium",
            "description": description,
            "reference_type": self.doctype,
            "reference_name": self.name,
            "assigned_by": "Administrator",
            "owner": frappe.session.user,
        })
        todo.insert(ignore_permissions=True)
        self.db_set("task_name", todo.name, update_modified=False)

    def _resolve_stamp_task(self):
        """Close the pending ToDo task once the stamp reference is entered."""
        try:
            todo = frappe.get_doc("ToDo", self.task_name)
            if todo.status == "Open":
                todo.status = "Closed"
                todo.save(ignore_permissions=True)
        except frappe.DoesNotExistError:
            pass
