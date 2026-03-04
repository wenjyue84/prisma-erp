"""Installation hooks for LHDN Payroll Integration."""

import frappe


def after_install():
	"""Run after the app is installed on a site."""
	_ensure_cloud_workspaces()


def after_migrate():
	"""Run after bench migrate completes.

	Ensures workspaces match the cloud (prismaerp.click).
	bench migrate can delete 'orphaned' workspaces that were not
	created by an app fixture, so we re-create them here.
	"""
	_fix_myinvois_module_name()
	_ensure_cloud_workspaces()


def _fix_myinvois_module_name():
	"""Fix Module Def 'E-Invoice' → 'Myinvois Erpgulf' if needed.

	The myinvois_erpgulf app registers its module as 'Myinvois Erpgulf'
	in modules.txt, but some DB backups have it renamed to 'E-Invoice'.
	get_module_app() uses modules.txt, so the DB must match.
	"""
	if frappe.db.exists("Module Def", "E-Invoice") and not frappe.db.exists(
		"Module Def", "Myinvois Erpgulf"
	):
		tables = [
			"`tabCustom Field`",
			"`tabDocType`",
			"`tabReport`",
			"`tabPage`",
			"`tabProperty Setter`",
			"`tabPrint Format`",
			"`tabWorkspace`",
			"`tabWorkspace Link`",
			"`tabWorkspace Shortcut`",
			"`tabWorkspace Sidebar`",
			"`tabWorkspace Sidebar Item`",
			"`tabDesktop Icon`",
			"`tabNumber Card`",
			"`tabDashboard Chart`",
		]
		for t in tables:
			try:
				frappe.db.sql(
					f"UPDATE {t} SET module = 'Myinvois Erpgulf' WHERE module = 'E-Invoice'"
				)
			except Exception:
				pass

		frappe.db.sql(
			"UPDATE `tabModule Def` SET name = 'Myinvois Erpgulf' WHERE name = 'E-Invoice'"
		)
		frappe.db.sql(
			"UPDATE `tabModule Def` SET app_name = 'myinvois_erpgulf' WHERE name = 'Myinvois Erpgulf'"
		)
		frappe.db.commit()


def _ensure_cloud_workspaces():
	"""Create workspaces that match the cloud but aren't in any app fixture.

	The myinvois_erpgulf app has a duplicate `fixtures =` in hooks.py
	which overwrites the Workspace fixture, so 'Malaysia Compliance' is
	never synced. The hrms app does not define an 'HR' top-level workspace.
	"""
	# Malaysia Compliance (displays as "E-Invoice" on desktop)
	if not frappe.db.exists("Workspace", "Malaysia Compliance"):
		module = "Myinvois Erpgulf" if frappe.db.exists("Module Def", "Myinvois Erpgulf") else None
		if module:
			doc = frappe.get_doc(
				{
					"doctype": "Workspace",
					"label": "Malaysia Compliance",
					"title": "Malaysia Compliance",
					"module": module,
					"type": "Workspace",
					"public": 1,
					"is_hidden": 0,
					"icon": "",
					"content": "[]",
					"shortcuts": [
						{
							"color": "Grey",
							"doc_view": "List",
							"label": "LHDN Detailed Dashboard",
							"link_to": "lhdn-dashboard",
							"type": "Page",
						}
					],
					"links": [
						{"type": "Card Break", "label": "LHDN setup", "link_count": 2},
						{"type": "Link", "label": "LHDN Setup for Company", "link_to": "Company", "link_type": "DocType"},
						{"type": "Link", "label": "Item Tax Templates", "link_to": "Item Tax Template", "link_type": "DocType"},
						{"type": "Card Break", "label": "VAT Report", "link_count": 1},
						{"type": "Link", "label": "LHDN VAT Report on Sales & Purchase", "link_to": "LHDN VAT Report on Sales & Purchase", "link_type": "Report", "is_query_report": 1},
						{"type": "Card Break", "label": "LHDN Status Reports", "link_count": 2},
						{"type": "Link", "label": "LHDN Sales Status Report", "link_to": "LHDN Sales Status Report", "link_type": "Report", "is_query_report": 1},
						{"type": "Link", "label": "LHDN Purchase Status Report", "link_to": "LHDN Purchase Status Report", "link_type": "Report", "is_query_report": 1},
					],
					"quick_lists": [
						{"document_type": "Sales Invoice", "label": "New Sales Invoices", "quick_list_filter": '[[\"Sales Invoice\",\"custom_lhdn_status\",\"like\",\"%Valid%\",false]]'},
						{"document_type": "Purchase Invoice", "label": "New Purchase Invoices", "quick_list_filter": '[[\"Purchase Invoice\",\"custom_lhdn_status\",\"like\",\"%Valid%\",false]]'},
					],
					"charts": [],
					"number_cards": [],
				}
			)
			doc.flags.ignore_permissions = True
			doc.flags.ignore_links = True
			doc.flags.ignore_mandatory = True
			doc.insert(ignore_if_duplicate=True)
			# Label → "E-Invoice" to match cloud (name stays "Malaysia Compliance")
			frappe.db.set_value("Workspace", "Malaysia Compliance", "label", "E-Invoice")

	# HR (top-level workspace for the hrms module)
	if not frappe.db.exists("Workspace", "HR"):
		if frappe.db.exists("Module Def", "HR"):
			doc = frappe.get_doc(
				{
					"doctype": "Workspace",
					"label": "HR",
					"title": "HR",
					"module": "HR",
					"type": "Workspace",
					"public": 1,
					"is_hidden": 0,
					"icon": "employee",
					"content": "[]",
					"shortcuts": [],
					"links": [],
					"charts": [],
					"number_cards": [],
				}
			)
			doc.flags.ignore_permissions = True
			doc.flags.ignore_links = True
			doc.insert(ignore_if_duplicate=True)

	frappe.db.commit()
