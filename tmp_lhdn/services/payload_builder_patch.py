# This is the updated build_salary_slip_xml function with PCB withholding tax support

# PCB component names to detect withholding tax deductions
PCB_COMPONENT_NAMES = frozenset({'Monthly Tax Deduction', 'PCB', 'Income Tax', 'Tax Deduction'})
