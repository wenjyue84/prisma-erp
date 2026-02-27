frappe.listview_settings["Salary Slip"] = frappe.listview_settings["Salary Slip"] || {};

const existing_onload = frappe.listview_settings["Salary Slip"].onload;

frappe.listview_settings["Salary Slip"].onload = function (listview) {
	if (existing_onload) {
		existing_onload(listview);
	}

	listview.page.add_action_item(__("Submit to LHDN"), function () {
		const selected = listview.get_checked_items();
		if (!selected.length) {
			frappe.msgprint(__("Please select at least one Salary Slip."));
			return;
		}

		const docnames = selected.map(function (d) {
			return d.name;
		});

		frappe.call({
			method: "lhdn_payroll_integration.services.submission_service.bulk_enqueue_lhdn_submission",
			args: {
				docnames: docnames,
				doctype: "Salary Slip",
			},
			freeze: true,
			freeze_message: __("Submitting {0} document(s) to LHDN...", [docnames.length]),
			callback: function (r) {
				if (r.message) {
					const msg = r.message;
					frappe.msgprint(
						__("LHDN Bulk Submit: {0} enqueued, {1} failed.", [msg.success, msg.failed])
					);
					listview.refresh();
				}
			},
		});
	});
};
