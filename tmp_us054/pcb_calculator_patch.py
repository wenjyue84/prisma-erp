"""Script to patch pcb_calculator.py for US-054 CP38 support."""
import sys

with open(sys.argv[1]) as f:
    content = f.read()

# 1. Add get_cp38_amount() before @frappe.whitelist() validate_pcb_amount
NEW_FUNC = '''

def get_cp38_amount(employee_name: str) -> float:
    """Return the active CP38 additional deduction for an employee.

    Under ITA 1967 s.107(1)(b), LHDN may issue CP38 notices directing employers
    to deduct additional PCB above normal MTD. Non-compliance makes the employer
    personally liable for the undeducted amount plus 10% surcharge (ITA s.107(3A)).

    Args:
        employee_name: The name/ID of the Employee document.

    Returns:
        float: CP38 amount (RM) if notice is active (expiry >= today), else 0.0.
    """
    try:
        employee = frappe.get_doc("Employee", employee_name)
        expiry = getattr(employee, "custom_cp38_expiry", None)
        amount = float(getattr(employee, "custom_cp38_amount", 0) or 0)
        if expiry and amount > 0:
            today = frappe.utils.getdate()
            expiry_date = frappe.utils.getdate(expiry)
            if expiry_date >= today:
                return amount
    except Exception:
        pass
    return 0.0


'''

target = '@frappe.whitelist()\ndef validate_pcb_amount'
if target not in content:
    print("ERROR: target marker not found in content!")
    sys.exit(1)

content = content.replace(target, NEW_FUNC + target, 1)

# 2. Update validate_pcb_amount to include CP38 in expected_monthly
old_pcb_block = '''    expected_monthly = calculate_pcb(
        annual_income, resident=resident, married=married, children=children,
        worked_days=worked_days_val, total_days=total_days_val,
        category=pcb_category,
    )

    # Find PCB deduction component (look for "Monthly Tax Deduction" or "PCB")'''

new_pcb_block = '''    expected_monthly = calculate_pcb(
        annual_income, resident=resident, married=married, children=children,
        worked_days=worked_days_val, total_days=total_days_val,
        category=pcb_category,
    )

    # CP38 additional deduction (ITA s.107(1)(b)): add to expected total when notice is active
    expected_monthly += get_cp38_amount(doc.employee)

    # Find PCB deduction component (look for "Monthly Tax Deduction" or "PCB")'''

if old_pcb_block not in content:
    print("ERROR: old_pcb_block not found in content!")
    sys.exit(1)

content = content.replace(old_pcb_block, new_pcb_block, 1)

with open(sys.argv[2], 'w') as f:
    f.write(content)

print("Patched successfully")
