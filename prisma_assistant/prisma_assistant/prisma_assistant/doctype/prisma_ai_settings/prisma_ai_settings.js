// Prisma AI Settings — form client script
// Auto-loaded by Frappe when the form is opened.

frappe.ui.form.on("Prisma AI Settings", {
	refresh(frm) {
		_show_key_preview(frm, "api_key", "Main API Key");
		_show_key_preview(frm, "fallback_api_key", "Fallback API Key");
	},
});

/**
 * Fetch the masked preview of a Password field from the server and inject it
 * as a small "Current: sk-...****...abcd  [Reveal]" line in the field description.
 */
function _show_key_preview(frm, field_name, label) {
	frappe.call({
		method: "prisma_assistant.api.chat.get_api_key_info",
		args: { field_name },
		callback(r) {
			if (!r.message || !r.message.has_key) {
				// No key stored — restore plain description
				frm.set_df_property(field_name, "description", _base_desc(field_name));
				frm.refresh_field(field_name);
				return;
			}

			const masked = r.message.masked;
			const desc =
				`<span style="font-family:monospace;font-size:0.85em">${masked}</span>` +
				`&nbsp;&nbsp;<a href="javascript:void(0)" ` +
				`style="color:var(--primary-color,#5c5ce0)" ` +
				`onclick="prisma_ai_reveal_key('${field_name}','${label}')">Reveal</a>`;

			frm.set_df_property(field_name, "description", desc);
			frm.refresh_field(field_name);
		},
	});
}

function _base_desc(field_name) {
	if (field_name === "api_key") {
		return "Your provider API key. Stored encrypted.";
	}
	return "API key for the fallback model if it uses a different provider or key. Leave blank to reuse the main API Key.";
}

/**
 * Exposed globally so the inline onclick handler can call it.
 * Fetches the full decrypted key and shows it in a dialog the user can copy.
 */
window.prisma_ai_reveal_key = function (field_name, label) {
	frappe.call({
		method: "prisma_assistant.api.chat.reveal_api_key",
		args: { field_name },
		callback(r) {
			if (r.message && r.message.key) {
				frappe.msgprint({
					title: label,
					message:
						`<div style="word-break:break-all;user-select:all;` +
						`font-family:monospace;padding:8px;background:var(--bg-color);` +
						`border:1px solid var(--border-color);border-radius:4px">` +
						frappe.utils.escape_html(r.message.key) +
						`</div><div style="margin-top:6px;font-size:0.8em;color:var(--text-muted)">` +
						`Click the text above to select all, then copy.</div>`,
					indicator: "blue",
				});
			} else {
				frappe.msgprint(__("No key stored for this field."));
			}
		},
	});
};
