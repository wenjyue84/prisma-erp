"""Script to patch ea_form.py for US-060 BIK integration.

Adds Employee BIK Record annual BIK to Section B7 of EA Form.
"""

EA_FILE = "/home/frappe/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/report/ea_form/ea_form.py"

with open(EA_FILE, "r") as f:
    content = f.read()

# Inject BIK Record amount into B7 after section_b is built
OLD_BLOCK = """        # Untagged earnings go into b12 but not into any specific Bn bucket
        untagged = emp_earnings.get("", 0.0)
        b12 = b_tagged_total + untagged"""

NEW_BLOCK = """        # BIK (US-060): add Employee BIK Record annual total to B7
        # This handles BIK values entered via the Employee BIK Record DocType
        # (separate from salary component-tagged BIK earnings)
        try:
            from lhdn_payroll_integration.services.bik_calculator import get_annual_bik_for_ea_form
            bik_record_annual = get_annual_bik_for_ea_form(emp, int(row.year or 0))
            if bik_record_annual > 0:
                section_b["b7_bik"] = section_b.get("b7_bik", 0.0) + bik_record_annual
                b_tagged_total += bik_record_annual
        except Exception:
            pass

        # Untagged earnings go into b12 but not into any specific Bn bucket
        untagged = emp_earnings.get("", 0.0)
        b12 = b_tagged_total + untagged"""

if "BIK (US-060)" not in content:
    if OLD_BLOCK in content:
        content = content.replace(OLD_BLOCK, NEW_BLOCK, 1)
        print("✓ Injected BIK into ea_form B7")
    else:
        print("✗ Could not find untagged block — manual patch needed")
else:
    print("✓ BIK already injected into ea_form, skipping")

with open(EA_FILE, "w") as f:
    f.write(content)

print("Done.")
