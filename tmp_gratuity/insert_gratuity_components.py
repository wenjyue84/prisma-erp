"""Script to insert Gratuity salary components directly into the DB."""
import frappe

components = [
    {
        "doctype": "Salary Component",
        "salary_component": "Gratuity - Approved Fund",
        "salary_component_abbr": "GRAT-AF",
        "type": "Earning",
        "description": "Gratuity from an LHDN-approved fund. ITA 1967 Sch 6 para 25: RM1,000 per year of service is exempt from income tax.",
        "custom_lhdn_exclude_from_invoice": 0,
        "custom_is_pcb_component": 1,
        "custom_lhdn_classification_code": "022",
        "custom_is_gratuity_or_leave_encashment": 1,
        "custom_ea_section": "B5 Gratuity",
    },
    {
        "doctype": "Salary Component",
        "salary_component": "Gratuity - Non-Approved",
        "salary_component_abbr": "GRAT-NA",
        "type": "Earning",
        "description": "Gratuity not from an approved fund. Fully taxable — no Schedule 6 para 25 exemption applies.",
        "custom_lhdn_exclude_from_invoice": 0,
        "custom_is_pcb_component": 1,
        "custom_lhdn_classification_code": "022",
        "custom_is_gratuity_or_leave_encashment": 1,
        "custom_ea_section": "B5 Gratuity",
    },
    {
        "doctype": "Salary Component",
        "salary_component": "Gratuity - Ex-Gratia",
        "salary_component_abbr": "GRAT-EG",
        "type": "Earning",
        "description": "Ex-gratia payment (discretionary). No Schedule 6 para 25 exemption.",
        "custom_lhdn_exclude_from_invoice": 0,
        "custom_is_pcb_component": 1,
        "custom_lhdn_classification_code": "022",
        "custom_is_gratuity_or_leave_encashment": 1,
        "custom_ea_section": "B5 Gratuity",
    },
]

for comp_data in components:
    name = comp_data["salary_component"]
    if frappe.db.exists("Salary Component", name):
        doc = frappe.get_doc("Salary Component", name)
        for k, v in comp_data.items():
            if k not in ("doctype", "salary_component"):
                setattr(doc, k, v)
        doc.save()
        print(f"Updated: {name}")
    else:
        doc = frappe.get_doc(comp_data)
        doc.insert()
        print(f"Inserted: {name}")

frappe.db.commit()
print("Done - all gratuity components committed.")
