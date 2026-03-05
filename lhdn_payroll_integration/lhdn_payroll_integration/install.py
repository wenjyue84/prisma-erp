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
	_cleanup_myinvois_legacy()
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


def _cleanup_myinvois_legacy():
	"""Remove stale 'Myinvois Erpgulf' workspace entries from the desk.

	The myinvois_erpgulf app may have created workspace/sidebar records with
	the module name as label. These are superseded by the 'E-Invoice' entries.
	This is idempotent — safe to run if records don't exist.
	"""
	for name in frappe.db.get_all("Workspace Sidebar", filters={"name": "Myinvois Erpgulf"}, pluck="name"):
		frappe.delete_doc("Workspace Sidebar", name, ignore_permissions=True, force=True)

	stale = frappe.db.get_all(
		"Workspace",
		filters=[["label", "=", "Myinvois Erpgulf"]],
		pluck="name",
	)
	for name in stale:
		frappe.delete_doc("Workspace", name, ignore_permissions=True, force=True)

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
			# Set content JSON so the workspace page renders cards/shortcuts
			_MC_CONTENT = (
				'[{"id":"zbqk_ugEBj","type":"header","data":{"text":"<span class=\\"h4\\">Malaysia Compliance</span>","col":12}},'
				'{"id":"MdfVTQpbYN","type":"shortcut","data":{"shortcut_name":"LHDN Detailed Dashboard ","col":4}},'
				'{"id":"_BbQEzQPjh","type":"card","data":{"card_name":"LHDN setup","col":4}},'
				'{"id":"Yud7Xdaykc","type":"card","data":{"card_name":"VAT Report","col":4}},'
				'{"id":"mF0ZRKynXL","type":"card","data":{"card_name":"LHDN Status Reports","col":4}},'
				'{"id":"e-GdBqydJB","type":"header","data":{"text":"<span class=\\"h4\\"><b></b></span>","col":12}},'
				'{"id":"Whuda70tL6","type":"quick_list","data":{"quick_list_name":"New Sales Invoices","col":4}},'
				'{"id":"YspTisQzkE","type":"quick_list","data":{"quick_list_name":"New Purchase Invoices","col":4}}]'
			)
			frappe.db.set_value("Workspace", "Malaysia Compliance", "content", _MC_CONTENT)

	# E-Invoice Workspace Sidebar (required for desktop icon click to work)
	# desktop.js looks up workspace_sidebar_item[icon.label.toLowerCase()]
	# so the Workspace Sidebar name must match the Desktop Icon label exactly.
	if not frappe.db.exists("Workspace Sidebar", "E-Invoice"):
		sidebar = frappe.get_doc(
			{
				"doctype": "Workspace Sidebar",
				"title": "E-Invoice",
				"module": "Myinvois Erpgulf",
				"app": "myinvois_erpgulf",
				"items": [
					{"label": "Home", "link_to": "Malaysia Compliance", "link_type": "Workspace"},
					{"label": "LHDN Detailed Dashboard", "link_to": "lhdn-dashboard", "link_type": "Page"},
				],
			}
		)
		sidebar.flags.ignore_permissions = True
		sidebar.flags.ignore_links = True
		sidebar.flags.ignore_mandatory = True
		sidebar.insert(ignore_if_duplicate=True)

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
