"""LHDN PCB (Potongan Cukai Berjadual) / MTD monthly tax deduction calculator.

Implements LHDN progressive tax scale for resident and non-resident employees.
Provides calculate_pcb() for raw calculation and validate_pcb_amount() as a
whitelisted Frappe method for Salary Slip validation.

Tax bands (Assessment Year 2024 — Jadual PCB):
    0%      : 0 – 5,000
    1%      : 5,001 – 20,000
    3%      : 20,001 – 35,000
    8%      : 35,001 – 50,000
    13%     : 50,001 – 70,000
    21%     : 70,001 – 100,000
    24%     : 100,001 – 400,000
    24.5%   : 400,001 – 600,000
    25%     : 600,001 – 2,000,000
    26%     : above 2,000,000

Non-resident: flat 30% on gross income (no reliefs applied).

Irregular payments (bonus, commission, gratuity):
    PCB computed using one-twelfth annualisation rule per LHDN Schedule D:
    bonus_pcb = tax_on(annual_income + bonus_amount - reliefs)
                - tax_on(annual_income - reliefs)
    Total PCB for that period = regular_monthly_pcb + bonus_pcb
"""
import datetime

import frappe

# BIK integration (US-060) — lazy import to avoid circular dependency
def _get_bik_for_employee(employee: str, slip_date) -> float:
    """Return monthly BIK for an employee based on the salary slip date.

    Args:
        employee: Employee document name.
        slip_date: Date object or string with the salary slip period date.

    Returns:
        float: Monthly BIK amount to add to gross income (RM). 0.0 if no record.
    """
    try:
        if slip_date:
            if hasattr(slip_date, "year"):
                year = slip_date.year
            else:
                import datetime as _dt
                year = _dt.date.fromisoformat(str(slip_date)[:10]).year
        else:
            year = int(frappe.utils.nowdate()[:4])
        from lhdn_payroll_integration.services.bik_calculator import calculate_monthly_bik_total
        return calculate_monthly_bik_total(employee, year)
    except Exception:
        return 0.0

# LHDN progressive tax bands: (upper_limit, rate_percent, cumulative_tax_at_lower_bound)
# For each band: tax = cumulative_at_lower + (income - lower_bound) * rate
_TAX_BANDS = [
    (5_000,       0.00,  0.0),
    (20_000,      0.01,  0.0),
    (35_000,      0.03,  150.0),
    (50_000,      0.08,  600.0),
    (70_000,      0.13,  1_800.0),
    (100_000,     0.21,  4_400.0),
    (400_000,     0.24,  10_700.0),
    (600_000,     0.245, 82_700.0),
    (2_000_000,   0.25,  131_700.0),
    (float("inf"), 0.26, 481_700.0),
]

# Lower bounds derived from the bands above
_LOWER_BOUNDS = [0, 5_000, 20_000, 35_000, 50_000, 70_000, 100_000, 400_000, 600_000, 2_000_000]

# Standard personal relief amounts (RM)
_SELF_RELIEF = 9_000
_SPOUSE_RELIEF = 4_000
_CHILD_RELIEF_PER_CHILD = 2_000

# ITA 1967 s.6A: Tax rebates (US-058)
# Applies to residents with chargeable income <= RM35,000
_PERSONAL_REBATE = 400
_REBATE_INCOME_LIMIT = 35_000

# Warning threshold: warn if PCB deviates more than 10% from calculated
_WARNING_THRESHOLD = 0.10


def _compute_tax_on_chargeable_income(chargeable_income: float) -> float:
    """Compute annual income tax using LHDN progressive bands.

    Args:
        chargeable_income: Annual chargeable income after reliefs (RM).

    Returns:
        float: Annual tax amount (RM). Zero if chargeable_income <= 0.
    """
    if chargeable_income <= 0:
        return 0.0

    for i, (upper, rate, cumulative) in enumerate(_TAX_BANDS):
        if chargeable_income <= upper:
            excess = chargeable_income - _LOWER_BOUNDS[i]
            return cumulative + excess * rate

    # Should not reach here; last band has upper = inf
    return 0.0


def calculate_pcb(
    annual_income: float,
    resident: bool = True,
    married: bool = False,
    children: int = 0,
    bonus_amount: float = 0.0,
    gratuity_amount: float = 0.0,
    years_of_service: int = 0,
    worked_days: int = None,
    total_days: int = None,
    category: int = None,
    tp1_total_reliefs: float = 0.0,
    annual_zakat: float = 0.0,
    approved_pension_scheme: bool = False,
    employee_age: int = 0,
) -> float:
    """Calculate monthly PCB/MTD deduction amount.

    Applies standard reliefs for residents then uses LHDN progressive bands.
    Non-residents are taxed at flat 30% on gross income.

    PCB Category (LHDN CP39 requirement):
        category=1 : Single or married with working spouse — no spouse relief
        category=2 : Married, non-working spouse — RM4,000 spouse relief (ITA s.45)
        category=3 : Single parent — RM4,000 relief (ITA s.46A)
        category=None: Falls back to the legacy ``married`` bool parameter.

    When worked_days and total_days are both provided and worked_days < total_days,
    monthly income is prorated before annualising:
        prorated_monthly = monthly_income * (worked_days / total_days)
        annual_income = prorated_monthly * 12
    This handles mid-month joins/departures per LHDN PCB proration rules.

    For irregular payments (bonus, commission), pass bonus_amount.
    The function applies the one-twelfth annualisation rule per LHDN Schedule D:
    the returned value is the regular monthly PCB plus the incremental tax on
    the bonus, computed as:
        bonus_pcb = tax_on(annual_income + bonus_amount - reliefs)
                    - tax_on(annual_income - reliefs)

    For gratuity / leave encashment, pass gratuity_amount and years_of_service.
    Schedule 6 paragraph 25 of ITA 1967 provides a tax exemption of RM1,000
    per completed year of service. Only the remainder above the exempt amount
    is taxable (treated as an irregular payment using the annualisation rule).

    Approved Pension Scheme (US-085 — ITA 1967 Schedule 6 paragraph 30):
        When approved_pension_scheme=True and employee_age >= 55, the FULL
        gratuity amount is exempt (100%), overriding the para 25 RM1,000/year
        calculation. This applies to employees retiring from an approved company
        pension scheme at the normal retirement age of 55 (or compulsory
        retirement age 60).

    TP1 Employee Relief Declaration (US-052):
        Pass tp1_total_reliefs to include employee-declared reliefs from Borang TP1.
        These are subtracted from chargeable income AFTER the standard personal/child
        reliefs, reducing PCB proportionally. Non-residents ignore TP1 reliefs.

    Zakat PCB Offset (US-053 — ITA 1967 s.6A(3)):
        Pass annual_zakat to offset PCB payable ringgit-for-ringgit.
        net_pcb = max(0, gross_monthly_pcb - annual_zakat / 12)
        This is a direct tax credit applied AFTER progressive tax computation,
        NOT a reduction in chargeable income. Result is floored at 0.

    Args:
        annual_income: Gross annual employment income (RM).
        resident: True if employee is a tax resident of Malaysia.
        married: (Deprecated) True if employee is married (spouse relief applies).
            Ignored when ``category`` is provided.
        children: Number of qualifying children (RM2,000 each).
        bonus_amount: One-off irregular payment amount (RM) such as bonus
            or commission. When provided, triggers LHDN Schedule D
            annualisation rule and adds incremental bonus PCB to the return value.
        gratuity_amount: Gratuity or leave encashment amount (RM). Subject
            to Schedule 6 para 25 exemption (RM1,000 x years_of_service).
        years_of_service: Completed years of service for Schedule 6 para 25
            exemption calculation.
        worked_days: Number of days actually worked in the pay period.
            When provided with total_days, prorates monthly income.
        total_days: Total calendar days in the pay period month.
            When provided with worked_days, prorates monthly income.
        category: PCB category (1, 2, or 3). When provided, overrides ``married``.
            1 = no spouse relief, 2 = spouse relief RM4,000, 3 = single parent RM4,000.
        tp1_total_reliefs: Additional annual reliefs from employee Borang TP1 declaration
            (e.g. life insurance, medical insurance, education fees, SSPN, EPF, SOCSO).
            These are subtracted from chargeable income to reduce PCB. Default 0.0.
        annual_zakat: Annual Zakat paid by Muslim employee (RM). Under ITA 1967 s.6A(3),
            Zakat is a ringgit-for-ringgit offset applied after tax computation:
            net_pcb = max(0, gross_monthly_pcb - annual_zakat / 12). Default 0.0.
        approved_pension_scheme: True if the employee is a member of an approved company
            pension scheme under ITA 1967 Schedule 6 para 30. When True and employee_age
            >= 55, the full gratuity amount is exempt (overrides para 25). Default False.
        employee_age: Employee's age in years at the time of gratuity payment. Used with
            approved_pension_scheme to determine full exemption eligibility. Default 0.

    Returns:
        float: Monthly PCB amount (RM), rounded to 2 decimal places.
               When bonus_amount or gratuity_amount > 0, includes both the
               regular monthly PCB and the incremental irregular PCB.
               Returns 0.0 for zero or negative income (with no irregular payments).
               Zakat offset is applied last; result is floored at 0.
    """
    # Mid-month proration: if worked_days < total_days, prorate monthly
    # income before annualising (LHDN PCB proration for mid-month join/leave)
    if worked_days is not None and total_days is not None and total_days > 0:
        if worked_days < total_days:
            monthly_income = annual_income / 12
            prorated_monthly = monthly_income * (worked_days / total_days)
            annual_income = prorated_monthly * 12

    if annual_income <= 0 and bonus_amount <= 0 and gratuity_amount <= 0:
        return 0.0

    # Gratuity exemption — Schedule 6 ITA 1967:
    # Para 30 (US-085): Approved pension scheme retirees aged >= 55 → 100% exempt.
    # Para 25          : All others → RM1,000 per completed year of service.
    if gratuity_amount > 0:
        if approved_pension_scheme and int(employee_age or 0) >= 55:
            # Full exemption under Schedule 6 para 30
            exempt_gratuity = gratuity_amount
        else:
            # Partial exemption under Schedule 6 para 25
            exempt_gratuity = min(gratuity_amount, years_of_service * 1_000)
    else:
        exempt_gratuity = 0.0
    taxable_gratuity = max(0.0, gratuity_amount - exempt_gratuity)

    # Total irregular amount = bonus + taxable portion of gratuity
    total_irregular = bonus_amount + taxable_gratuity

    # Compute monthly Zakat offset (ITA 1967 s.6A(3) — ringgit-for-ringgit credit)
    monthly_zakat = float(annual_zakat or 0) / 12 if annual_zakat else 0.0

    if not resident:
        # Non-resident: flat 30%, no reliefs
        regular_monthly = (annual_income * 0.30) / 12 if annual_income > 0 else 0.0
        irregular_pcb = total_irregular * 0.30 if total_irregular > 0 else 0.0
        gross_monthly = regular_monthly + irregular_pcb
        # Apply Zakat offset (ringgit-for-ringgit, floored at 0)
        if monthly_zakat > 0:
            gross_monthly = max(0.0, gross_monthly - monthly_zakat)
        return round(gross_monthly, 2)

    # Resident: apply personal reliefs before tax computation.
    # Resolve spouse/single-parent relief from category or legacy married flag.
    total_relief = _SELF_RELIEF
    if category is not None:
        # category 2 = non-working spouse relief; category 3 = single parent relief (ITA s.46A)
        if int(category) in (2, 3):
            total_relief += _SPOUSE_RELIEF
        # category 1: no additional spouse/parent relief
    elif married:
        total_relief += _SPOUSE_RELIEF
    total_relief += children * _CHILD_RELIEF_PER_CHILD

    # TP1 employee-declared reliefs (US-052): added on top of standard reliefs
    total_relief += max(0.0, float(tp1_total_reliefs or 0))

    chargeable_income = max(0.0, annual_income - total_relief)
    annual_tax = _compute_tax_on_chargeable_income(chargeable_income)

    # ITA 1967 s.6A: Apply RM400 personal rebate and RM400 spouse rebate
    # for residents with chargeable income <= RM35,000 (US-058).
    if chargeable_income <= _REBATE_INCOME_LIMIT:
        annual_tax = max(0.0, annual_tax - _PERSONAL_REBATE)
        # Spouse rebate: Category 2 (non-working spouse) or Category 3 (single parent),
        # also applies via legacy married=True flag.
        _has_spouse = (
            (category is not None and int(category) in (2, 3))
            or (category is None and married)
        )
        if _has_spouse:
            annual_tax = max(0.0, annual_tax - _PERSONAL_REBATE)

    regular_monthly_pcb = annual_tax / 12

    if total_irregular > 0:
        # LHDN Schedule D one-twelfth annualisation rule:
        total_chargeable = max(0.0, annual_income + total_irregular - total_relief)
        tax_with_irregular = _compute_tax_on_chargeable_income(total_chargeable)
        irregular_pcb = tax_with_irregular - annual_tax
        gross_monthly = regular_monthly_pcb + irregular_pcb
    else:
        gross_monthly = regular_monthly_pcb

    # ITA 1967 s.6A(3): Zakat is ringgit-for-ringgit PCB offset (not a relief)
    if monthly_zakat > 0:
        gross_monthly = max(0.0, gross_monthly - monthly_zakat)

    return round(gross_monthly, 2)




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
            today = datetime.date.today()
            if isinstance(expiry, str):
                expiry_date = datetime.date.fromisoformat(expiry)
            else:
                expiry_date = expiry
            if expiry_date >= today:
                return amount
    except Exception:
        pass
    return 0.0


@frappe.whitelist()
def validate_pcb_amount(doc_name: str) -> dict:
    """Validate PCB amount on a Salary Slip against LHDN calculated estimate.

    Fetches the Salary Slip, computes expected PCB using calculate_pcb(),
    and warns (does NOT block) if the actual PCB deviates more than 10%
    from the calculated estimate.

    Args:
        doc_name: Name of the Salary Slip document.

    Returns:
        dict with keys:
            - expected_monthly_pcb (float): Calculated monthly PCB.
            - actual_pcb (float): PCB found in the salary slip deductions.
            - deviation_pct (float): Absolute deviation as a fraction (e.g. 0.15 = 15%).
            - warning (bool): True if deviation exceeds threshold.
            - message (str): Human-readable result.
    """
    doc = frappe.get_doc("Salary Slip", doc_name)

    # Extract annual income from the slip
    monthly_gross = float(doc.gross_pay or 0)

    # BIK (US-060): add monthly BIK to gross income before annualising
    monthly_gross += _get_bik_for_employee(doc.employee, doc.start_date or doc.end_date)

    annual_income = monthly_gross * 12

    # Determine resident status (custom field, defaults to resident)
    resident = True
    married = False
    children = 0

    employee = frappe.get_doc("Employee", doc.employee)
    # custom_is_non_resident (Check, 1/0) is the canonical non-resident flag (US-019).
    # Fall back to legacy custom_tax_resident_status if present.
    if hasattr(employee, "custom_is_non_resident") and employee.custom_is_non_resident:
        resident = False
    elif hasattr(employee, "custom_tax_resident_status"):
        resident = (employee.custom_tax_resident_status or "Resident") == "Resident"
    if hasattr(employee, "custom_marital_status"):
        married = (employee.custom_marital_status or "") == "Married"
    if hasattr(employee, "custom_number_of_children"):
        children = int(employee.custom_number_of_children or 0)

    # PCB category (US-051): prefer custom_pcb_category if set; fall back to married flag.
    pcb_category = None
    raw_cat = getattr(employee, "custom_pcb_category", None)
    if raw_cat:
        try:
            pcb_category = int(raw_cat)
        except (ValueError, TypeError):
            pcb_category = None

    # Extract proration info from Salary Slip (total_working_days, payment_days)
    worked_days_val = None
    total_days_val = None
    if hasattr(doc, "payment_days") and hasattr(doc, "total_working_days"):
        payment_days = int(doc.payment_days or 0)
        total_working_days = int(doc.total_working_days or 0)
        if total_working_days > 0 and payment_days < total_working_days:
            worked_days_val = payment_days
            total_days_val = total_working_days

    expected_monthly = calculate_pcb(
        annual_income, resident=resident, married=married, children=children,
        worked_days=worked_days_val, total_days=total_days_val,
        category=pcb_category,
    )

    # CP38 additional deduction (ITA s.107(1)(b)): add to expected total when notice is active
    expected_monthly += get_cp38_amount(doc.employee)

    # Find PCB deduction component (look for "Monthly Tax Deduction" or "PCB")
    actual_pcb = 0.0
    for deduction in (doc.deductions or []):
        comp = (deduction.salary_component or "").lower()
        if "pcb" in comp or "monthly tax deduction" in comp or "mtd" in comp:
            actual_pcb += float(deduction.amount or 0)

    # Compute deviation
    if expected_monthly > 0:
        deviation = abs(actual_pcb - expected_monthly) / expected_monthly
    else:
        deviation = 0.0 if actual_pcb == 0 else 1.0

    over_threshold = deviation > _WARNING_THRESHOLD

    if over_threshold:
        message = (
            f"PCB Warning: Actual PCB RM {actual_pcb:,.2f} deviates "
            f"{deviation * 100:.1f}% from estimated RM {expected_monthly:,.2f}. "
            "Please verify against LHDN Jadual PCB."
        )
        frappe.msgprint(message, title="PCB Validation Warning", indicator="orange")
    else:
        message = (
            f"PCB OK: Actual RM {actual_pcb:,.2f} is within 10% of "
            f"estimated RM {expected_monthly:,.2f}."
        )

    return {
        "expected_monthly_pcb": expected_monthly,
        "actual_pcb": actual_pcb,
        "deviation_pct": round(deviation * 100, 2),
        "warning": over_threshold,
        "message": message,
    }


def calculate_pcb_method2(
    ytd_gross: float,
    ytd_pcb_deducted: float,
    month_number: int,
    tp1_reliefs: float = 0.0,
    category: int = None,
    annual_zakat: float = 0.0,
    resident: bool = True,
    tp3_prior_gross: float = 0.0,
    tp3_prior_pcb: float = 0.0,
) -> float:
    """Calculate monthly PCB using Method 2 (Year-to-Date Recalculation).

    LHDN PCB Guidelines Appendix D mandates Method 2 for payroll software.
    Formula: MTD_n = (annual_tax_on_annualised_ytd - X) / remaining_months
    where:
        annual_tax_on_annualised_ytd = tax on (ytd_gross * 12 / month_number - reliefs)
        X = total PCB already deducted in months prior to month_number
        remaining_months = 13 - month_number (months left including current)

    For constant-income employees, Method 2 produces the same annual total as Method 1.

    TP3 (Prior Employer YTD) integration:
        When an employee joins mid-year with prior employer income, pass tp3_prior_gross
        and tp3_prior_pcb. These are added to ytd_gross and ytd_pcb_deducted respectively
        before annualisation, ensuring the combined income is correctly annualised and
        PCB already paid to the prior employer is not double-deducted.
        Regulatory basis: LHDN Borang TP3 (prior employment income declaration).

    Args:
        ytd_gross: Year-to-date gross pay INCLUDING current month (RM).
        ytd_pcb_deducted: Total PCB deducted in months BEFORE current month (RM).
        month_number: Current payroll month (1=January, 12=December).
        tp1_reliefs: Employee-declared TP1 additional reliefs (RM, default 0).
        category: PCB category (1=single, 2=non-working spouse, 3=single parent).
        annual_zakat: Annual Zakat paid by employee (RM, ringgit-for-ringgit credit).
        resident: True if employee is a tax resident (default True).
        tp3_prior_gross: Prior employer gross income from Borang TP3 (RM, default 0).
        tp3_prior_pcb: Prior employer PCB deducted from Borang TP3 (RM, default 0).

    Returns:
        float: Monthly PCB deduction for current month (RM), rounded to 2 decimal places.
    """
    month_number = max(1, min(12, int(month_number)))

    # Incorporate TP3 prior employer data into YTD figures
    combined_ytd_gross = float(ytd_gross or 0) + float(tp3_prior_gross or 0)
    combined_ytd_pcb = float(ytd_pcb_deducted or 0) + float(tp3_prior_pcb or 0)

    # Annualise the combined YTD gross income
    annualised_income = combined_ytd_gross * 12.0 / month_number

    if not resident:
        # Non-resident: flat 30%, no reliefs or rebates
        annual_tax = annualised_income * 0.30
        if annual_zakat:
            annual_tax = max(0.0, annual_tax - float(annual_zakat))
        remaining_months = 13 - month_number
        pcb = max(0.0, (annual_tax - combined_ytd_pcb) / remaining_months)
        return round(pcb, 2)

    # Resident: compute total reliefs (same logic as Method 1)
    total_relief = _SELF_RELIEF
    if category is not None:
        if int(category) in (2, 3):
            total_relief += _SPOUSE_RELIEF
    total_relief += max(0.0, float(tp1_reliefs or 0))

    chargeable_income = max(0.0, annualised_income - total_relief)
    annual_tax = _compute_tax_on_chargeable_income(chargeable_income)

    # ITA 1967 s.6A: RM400 personal rebate for chargeable income <= RM35,000
    if chargeable_income <= _REBATE_INCOME_LIMIT:
        annual_tax = max(0.0, annual_tax - _PERSONAL_REBATE)
        _has_spouse = (category is not None and int(category) in (2, 3))
        if _has_spouse:
            annual_tax = max(0.0, annual_tax - _PERSONAL_REBATE)

    # Apply annual Zakat offset (ringgit-for-ringgit credit against full annual tax)
    if annual_zakat:
        annual_tax = max(0.0, annual_tax - float(annual_zakat))

    # Spread remaining tax liability over remaining months (including current month)
    remaining_months = 13 - month_number
    pcb = max(0.0, (annual_tax - combined_ytd_pcb) / remaining_months)
    return round(pcb, 2)


def populate_ytd_pcb_fields(doc, method=None):
    """Before-submit hook: populate YTD gross and PCB fields on Salary Slip.

    Queries prior submitted salary slips for the same employee and calendar year
    to compute cumulative YTD gross pay and PCB deducted. Results are stored in:
        doc.custom_ytd_gross         - YTD gross pay from prior submitted slips
        doc.custom_ytd_pcb_deducted  - YTD PCB deducted from prior submitted slips

    These fields are consumed by calculate_pcb_method2() for accurate Method 2
    calculations. Errors are silently suppressed to avoid blocking submission.

    Args:
        doc: Salary Slip document being submitted.
        method: Frappe event method string (unused, required by hook signature).
    """
    try:
        end_date = doc.end_date
        if isinstance(end_date, str):
            import datetime as _dt
            end_date = _dt.date.fromisoformat(str(end_date))
        year = end_date.year

        # Sum gross_pay from prior submitted slips (same employee, same year, earlier end_date)
        gross_result = frappe.db.sql(
            """
            SELECT COALESCE(SUM(gross_pay), 0)
            FROM `tabSalary Slip`
            WHERE employee = %s
              AND YEAR(end_date) = %s
              AND end_date < %s
              AND docstatus = 1
            """,
            (doc.employee, year, str(doc.end_date)),
        )
        ytd_gross = float((gross_result[0][0] if gross_result else 0) or 0)

        # Sum PCB deduction amounts from prior submitted slips via Salary Detail child table
        pcb_result = frappe.db.sql(
            """
            SELECT COALESCE(SUM(sd.amount), 0)
            FROM `tabSalary Detail` sd
            JOIN `tabSalary Slip` ss ON ss.name = sd.parent
            WHERE ss.employee = %s
              AND YEAR(ss.end_date) = %s
              AND ss.end_date < %s
              AND ss.docstatus = 1
              AND sd.parentfield = 'deductions'
              AND (
                  LOWER(sd.salary_component) LIKE '%pcb%'
                  OR LOWER(sd.salary_component) LIKE '%monthly tax deduction%'
                  OR LOWER(sd.salary_component) LIKE '%mtd%'
              )
            """,
            (doc.employee, year, str(doc.end_date)),
        )
        ytd_pcb = float((pcb_result[0][0] if pcb_result else 0) or 0)

        doc.custom_ytd_gross = ytd_gross
        doc.custom_ytd_pcb_deducted = ytd_pcb
    except Exception:
        pass


def calculate_director_fee_pcb(
    total_fee: float,
    months_covered: int,
    resident: bool = True,
    category: int = None,
    tp1_total_reliefs: float = 0.0,
    annual_zakat: float = 0.0,
) -> float:
    """Calculate PCB/MTD for fee-only directors receiving lump-sum director fees.

    LHDN PCB Specification 2026 Section 5: For directors who receive only
    lump-sum director fees (no monthly salary), MTD is computed as:

        monthly_equivalent = total_fee / months_covered
        annual_equivalent  = monthly_equivalent * 12
        annual_tax         = tax_on(annual_equivalent - reliefs)
        monthly_tax        = annual_tax / 12
        MTD                = monthly_tax * months_covered

    This formula differs from the bonus-month annualisation rule (Schedule D)
    which is used when a director has BOTH monthly salary AND a lump-sum fee.
    For mixed-income directors, use calculate_pcb() with bonus_amount instead.

    For non-resident directors: flat 30% on total_fee (no reliefs applied).

    Annual Zakat (ITA 1967 s.6A(3)) is applied as a ringgit-for-ringgit credit
    against the total MTD for the payment period:
        net_mtd = max(0, gross_mtd - (annual_zakat / 12) * months_covered)

    Args:
        total_fee: Total director fee for the payment period (RM).
        months_covered: Number of months the fee covers
            (1=monthly, 3=quarterly, 6=bi-annual, 12=annually).
        resident: True if director is a Malaysian tax resident.
        category: PCB category (1=single, 2=non-working spouse, 3=single parent).
            Category 2 and 3 receive RM4,000 spouse/parent relief.
        tp1_total_reliefs: Additional annual reliefs from Borang TP1 (RM).
        annual_zakat: Annual Zakat paid by Muslim director (RM). Applied as
            ringgit-for-ringgit credit on the total MTD for the period.

    Returns:
        float: Total MTD for the fee payment period (RM), rounded to 2 decimal places.
               Returns 0.0 for zero or negative fee.
    """
    if total_fee <= 0:
        return 0.0

    months_covered = max(1, int(months_covered))
    monthly_equivalent = total_fee / months_covered

    if not resident:
        # Non-resident: flat 30% on total fee, no reliefs
        gross_mtd = total_fee * 0.30
        if annual_zakat:
            zakat_for_period = (float(annual_zakat) / 12) * months_covered
            gross_mtd = max(0.0, gross_mtd - zakat_for_period)
        return round(gross_mtd, 2)

    # Resident: annualise the monthly equivalent then compute tax
    annual_equivalent = monthly_equivalent * 12

    # Apply standard and TP1 reliefs
    total_relief = _SELF_RELIEF
    if category is not None and int(category) in (2, 3):
        total_relief += _SPOUSE_RELIEF
    total_relief += max(0.0, float(tp1_total_reliefs or 0))

    chargeable_income = max(0.0, annual_equivalent - total_relief)
    annual_tax = _compute_tax_on_chargeable_income(chargeable_income)

    # ITA 1967 s.6A: RM400 personal rebate for chargeable income <= RM35,000
    if chargeable_income <= _REBATE_INCOME_LIMIT:
        annual_tax = max(0.0, annual_tax - _PERSONAL_REBATE)
        _has_spouse = (category is not None and int(category) in (2, 3))
        if _has_spouse:
            annual_tax = max(0.0, annual_tax - _PERSONAL_REBATE)

    monthly_tax = annual_tax / 12
    gross_mtd = monthly_tax * months_covered

    # ITA 1967 s.6A(3): Zakat is ringgit-for-ringgit credit for the payment period
    if annual_zakat:
        zakat_for_period = (float(annual_zakat) / 12) * months_covered
        gross_mtd = max(0.0, gross_mtd - zakat_for_period)

    return round(gross_mtd, 2)
