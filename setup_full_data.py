"""
Arising Packaging Sdn Bhd — Full System Seed v3.0
Run AFTER setup_sample_data.py has already been executed.

Creates (idempotent — safe to re-run):
  [12] Territories          — 16 Malaysian states under the Malaysia territory
  [13] Payment Terms        — Net 14 / 30 / 45 / 60 terms + templates
  [14] Contacts             — One contact person per customer & supplier
  [15] Payment Terms Link   — Attach correct template to each customer/supplier
  [16] Opening Stock        — Stock Reconciliation for all FG + RM items
  [17] BOM                  — 15 submitted BOMs (one per jerry can SKU)
  [18] Sales Orders         — 5 submitted SOs from major customers
  [19] Purchase Orders      — 3 submitted POs to suppliers
  [20] HR                   — Departments, Designations, 6 Employees
  [21] Salary Structure     — Standard structure + assignments for all employees

Deploy & run:
  docker cp setup_full_data.py \\
    prisma-erp-backend-1:/home/frappe/frappe-bench/apps/frappe/frappe/setup_full_data.py
  docker exec prisma-erp-backend-1 bash -c \\
    "cd /home/frappe/frappe-bench && bench --site frontend execute frappe.setup_full_data.run"
"""

import frappe
import traceback
from frappe.utils import today, add_days

COMPANY     = "Arising Packaging"
ABBR        = "AP"
WAREHOUSE   = "Arising Packaging Warehouse - AP"
COST_CENTER = "Main - AP"
results     = []


def log(msg):
    results.append(msg)
    print(msg)


# ─────────────────────────────────────────────────────────────────────────────
# [12] TERRITORIES — Malaysian states
# ─────────────────────────────────────────────────────────────────────────────

MALAYSIAN_STATES = [
    "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan",
    "Pahang", "Perak", "Perlis", "Pulau Pinang", "Sabah",
    "Sarawak", "Selangor", "Terengganu",
    "Kuala Lumpur", "Putrajaya", "Labuan",
]


def _setup_territories():
    for state in MALAYSIAN_STATES:
        try:
            if frappe.db.exists("Territory", state):
                log(f"SKP  [12] Territory '{state}'")
                continue
            t = frappe.get_doc({
                "doctype":          "Territory",
                "territory_name":   state,
                "parent_territory": "Malaysia",
                "is_group":         0,
            })
            t.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [12] Territory '{state}'")
        except Exception as e:
            log(f"ERR  [12] Territory '{state}': {e}")


# ─────────────────────────────────────────────────────────────────────────────
# [13] PAYMENT TERMS
# ─────────────────────────────────────────────────────────────────────────────

_PT = [
    # (payment_term_name, credit_days)
    ("Net 14 Days", 14),
    ("Net 30 Days", 30),
    ("Net 45 Days", 45),
    ("Net 60 Days", 60),
]

_PTT = [
    # (template_name, payment_term_name, credit_days)
    ("14 Days Net", "Net 14 Days", 14),
    ("30 Days Net", "Net 30 Days", 30),
    ("45 Days Net", "Net 45 Days", 45),
    ("60 Days Net", "Net 60 Days", 60),
]


def _setup_payment_terms():
    # Payment Term records
    for pt_name, days in _PT:
        try:
            if frappe.db.exists("Payment Term", pt_name):
                log(f"SKP  [13] Payment Term '{pt_name}'")
                continue
            pt = frappe.get_doc({
                "doctype":             "Payment Term",
                "payment_term_name":   pt_name,
                "due_date_based_on":   "Day(s) after invoice date",
                "invoice_portion":     100.0,
                "credit_days":         days,
            })
            pt.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [13] Payment Term '{pt_name}' ({days} days)")
        except Exception as e:
            log(f"ERR  [13] Payment Term '{pt_name}': {e}")
            traceback.print_exc()

    # Payment Terms Templates
    for tmpl_name, pt_name, days in _PTT:
        try:
            if frappe.db.exists("Payment Terms Template", tmpl_name):
                log(f"SKP  [13] Payment Terms Template '{tmpl_name}'")
                continue
            if not frappe.db.exists("Payment Term", pt_name):
                log(f"ERR  [13] Template '{tmpl_name}' skipped — term '{pt_name}' not found")
                continue
            tmpl = frappe.get_doc({
                "doctype":       "Payment Terms Template",
                "template_name": tmpl_name,
                "terms": [{
                    "payment_term":      pt_name,
                    "invoice_portion":   100.0,
                    "due_date_based_on": "Day(s) after invoice date",
                    "credit_days":       days,
                }],
            })
            tmpl.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [13] Payment Terms Template '{tmpl_name}'")
        except Exception as e:
            log(f"ERR  [13] Template '{tmpl_name}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [14] CONTACTS
# ─────────────────────────────────────────────────────────────────────────────

_CONTACTS = [
    # (first_name, last_name, phone, email, link_doctype, link_name)
    ("Zainal",      "bin Hamid",          "+60-12-300-1100", "zainal.hamid@wilmarmalaysia.com",   "Customer", "Wilmar Trading (Malaysia) Sdn Bhd"),
    ("Jessica",     "Wong Pei Lin",       "+60-12-200-2200", "jessica.wong@ioicorp.com",           "Customer", "IOI Palm Oleo (Johor) Sdn Bhd"),
    ("Ravi",        "Kumar",              "+60-12-400-3300", "ravi.kumar@mewah.com",               "Customer", "Mewah Oils Sdn Bhd"),
    ("Fatimah",     "binti Rahman",       "+60-12-500-4400", "fatimah.rahman@fgvholdings.com",     "Customer", "FGV Palm Industries Sdn Bhd"),
    ("Ahmad Fuad",  "bin Zahari",         "+60-12-600-5500", "ahmadfuad@musimmas.com.my",          "Customer", "Musim Mas Palm Oil Refinery (Johor) Sdn Bhd"),
    ("Roberto",     "Chen",               "+60-12-700-6600", "roberto.chen@mapei.com.my",          "Customer", "Mapei (Malaysia) Sdn Bhd"),
    ("Lim",         "Beng Huat",          "+60-12-800-7700", "benghuat@palmtop.com.my",            "Customer", "Palmtop Edible Oils Sdn Bhd"),
    ("Nur Aisyah",  "binti Aziz",         "+60-12-900-8800", "nuraisyah@pacoil.com.my",            "Customer", "Pacoil Sdn Bhd"),
    ("Kong",        "Ah Huat",            "+60-12-111-9900", "ahuat@konghoo.com.my",               "Customer", "KongHoo Oils Trading Sdn Bhd"),
    ("James",       "Lian",               "+60-12-222-1001", "james@lianindustries.com.my",        "Customer", "Lian Industries Sdn Bhd"),
    # Supplier contacts
    ("Kevin",       "Tan",                "+60-7-251-1001",  "kevintan@lctitan.com",               "Supplier", "Lotte Chemical Titan (M) Sdn Bhd"),
    ("Sarah",       "Abdullah",           "+60-3-7980-3601", "sarah.abdullah@clariant.com",        "Supplier", "Clariant (Malaysia) Sdn Bhd"),
    ("Danny",       "Lim",                "+60-3-6188-3301", "danny@goodshinepackaging.com.my",    "Supplier", "Goodshine Packaging Supplies Sdn Bhd"),
    # Company contact — TH Tan
    ("Tan Teck Hong", "",                 "+60-12-721-9550", "thtan@arisingpackaging.com",         "Company",  COMPANY),
]


def _setup_contacts():
    for first_name, last_name, phone, email, link_doctype, link_name in _CONTACTS:
        try:
            # Idempotency: check if any Contact is already linked to this record
            existing = frappe.db.get_value(
                "Dynamic Link",
                {"link_doctype": link_doctype, "link_name": link_name, "parenttype": "Contact"},
                "parent",
            )
            if existing:
                log(f"SKP  [14] Contact for '{link_name}' ({existing})")
                continue
            contact = frappe.get_doc({
                "doctype":    "Contact",
                "first_name": first_name,
                "last_name":  last_name,
                "email_ids":  [{"email_id": email, "is_primary": 1}],
                "phone_nos":  [{"phone": phone, "is_primary_mobile_no": 1}],
                "links":      [{"link_doctype": link_doctype, "link_name": link_name}],
            })
            contact.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [14] Contact '{first_name} {last_name}'.strip() → {link_doctype} '{link_name}'")
        except Exception as e:
            log(f"ERR  [14] Contact for '{link_name}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [15] ATTACH PAYMENT TERMS TO CUSTOMERS & SUPPLIERS
# ─────────────────────────────────────────────────────────────────────────────

_CUST_PT = {
    "Wilmar Trading (Malaysia) Sdn Bhd":            "60 Days Net",
    "IOI Palm Oleo (Johor) Sdn Bhd":               "60 Days Net",
    "Mewah Oils Sdn Bhd":                          "45 Days Net",
    "FGV Palm Industries Sdn Bhd":                 "60 Days Net",
    "Musim Mas Palm Oil Refinery (Johor) Sdn Bhd": "30 Days Net",
    "Mapei (Malaysia) Sdn Bhd":                    "30 Days Net",
    "Palmtop Edible Oils Sdn Bhd":                 "45 Days Net",
    "Pacoil Sdn Bhd":                              "30 Days Net",
    "KongHoo Oils Trading Sdn Bhd":                "30 Days Net",
    "Lian Industries Sdn Bhd":                     "45 Days Net",
    "Ahmad bin Abdullah":                          "14 Days Net",
    "Lim Ah Kow":                                  "14 Days Net",
}

_SUPP_PT = {
    "Lotte Chemical Titan (M) Sdn Bhd":     "60 Days Net",
    "Clariant (Malaysia) Sdn Bhd":          "30 Days Net",
    "Goodshine Packaging Supplies Sdn Bhd": "30 Days Net",
}


def _attach_payment_terms():
    for cust_name, tmpl in _CUST_PT.items():
        try:
            if not frappe.db.exists("Customer", cust_name):
                log(f"SKP  [15] Customer '{cust_name}' not found")
                continue
            if not frappe.db.exists("Payment Terms Template", tmpl):
                log(f"SKP  [15] Template '{tmpl}' not found — skip '{cust_name}'")
                continue
            cust = frappe.get_doc("Customer", cust_name)
            if cust.payment_terms == tmpl:
                log(f"SKP  [15] Customer '{cust_name}' already → '{tmpl}'")
                continue
            cust.payment_terms = tmpl
            cust.save(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [15] Customer '{cust_name}' → '{tmpl}'")
        except Exception as e:
            log(f"ERR  [15] Customer '{cust_name}': {e}")

    for supp_name, tmpl in _SUPP_PT.items():
        try:
            if not frappe.db.exists("Supplier", supp_name):
                log(f"SKP  [15] Supplier '{supp_name}' not found")
                continue
            if not frappe.db.exists("Payment Terms Template", tmpl):
                log(f"SKP  [15] Template '{tmpl}' not found — skip '{supp_name}'")
                continue
            supp = frappe.get_doc("Supplier", supp_name)
            if supp.payment_terms == tmpl:
                log(f"SKP  [15] Supplier '{supp_name}' already → '{tmpl}'")
                continue
            supp.payment_terms = tmpl
            supp.save(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [15] Supplier '{supp_name}' → '{tmpl}'")
        except Exception as e:
            log(f"ERR  [15] Supplier '{supp_name}': {e}")


# ─────────────────────────────────────────────────────────────────────────────
# [16] OPENING STOCK — Stock Reconciliation
# ─────────────────────────────────────────────────────────────────────────────

_OPENING_STOCK = [
    # (item_code,       qty,    valuation_rate)
    # Finished Goods
    ("AP-JC-002W",     300,    1.05),
    ("AP-JC-005Y",     600,    1.54),
    ("AP-JC-005W",     600,    1.54),
    ("AP-JC-010Y",    1500,    2.66),
    ("AP-JC-010W",    1500,    2.66),
    ("AP-JC-010B",     800,    2.66),
    ("AP-JC-010G",     800,    2.66),
    ("AP-JC-020Y",    5000,    4.55),
    ("AP-JC-020W",    3000,    4.55),
    ("AP-JC-020B",     500,    4.55),
    ("AP-JC-020G",     500,    4.55),
    ("AP-JC-025Y",    2000,    5.53),
    ("AP-JC-025W",    2000,    5.53),
    ("AP-JC-025B",     800,    5.53),
    ("AP-JC-025G",     800,    5.53),
    # Raw Materials
    ("RM-HDPE-NAT",  12000,    5.20),
    ("RM-HDPE-R100",  4000,    3.80),
    ("RM-MB-YEL",      600,   18.00),
    ("RM-MB-WHT",      600,   15.00),
    ("RM-MB-BLU",      350,   20.00),
    ("RM-MB-GRN",      350,   19.00),
    ("RM-CAP-38",    80000,    0.25),
]

_STOCK_REMARKS = "Arising Packaging — Initial Opening Stock Balance"


def _setup_opening_stock():
    try:
        exists = frappe.db.exists("Stock Reconciliation", {
            "purpose":  "Stock Reconciliation",
            "company":  COMPANY,
            "docstatus": 1,
        })
        if exists:
            log(f"SKP  [16] Opening stock reconciliation already exists: {exists}")
            return

        sr = frappe.get_doc({
            "doctype":            "Stock Reconciliation",
            "purpose":            "Stock Reconciliation",
            "company":            COMPANY,
            "posting_date":       today(),
            "difference_account": f"Stock Adjustment - {ABBR}",
            "remarks":            _STOCK_REMARKS,
            "items": [
                {
                    "item_code":       code,
                    "warehouse":       WAREHOUSE,
                    "qty":             qty,
                    "valuation_rate":  rate,
                }
                for code, qty, rate in _OPENING_STOCK
            ],
        })
        sr.insert(ignore_permissions=True)
        sr.submit()
        frappe.db.commit()
        log(f"OK   [16] Opening stock reconciliation {sr.name} — {len(_OPENING_STOCK)} items submitted")
    except Exception as e:
        log(f"ERR  [16] Opening stock: {e}")
        traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [17] BILLS OF MATERIALS — 15 jerry can SKUs
# ─────────────────────────────────────────────────────────────────────────────

_COLOUR_MB = {"Y": "RM-MB-YEL", "W": "RM-MB-WHT", "B": "RM-MB-BLU", "G": "RM-MB-GRN"}

_BOMS = [
    # (item_code,    hdpe_kg,  mb_kg,  colour)
    ("AP-JC-002W",   0.200,   0.004,  "W"),
    ("AP-JC-005Y",   0.400,   0.008,  "Y"),
    ("AP-JC-005W",   0.400,   0.008,  "W"),
    ("AP-JC-010Y",   0.700,   0.015,  "Y"),
    ("AP-JC-010W",   0.700,   0.015,  "W"),
    ("AP-JC-010B",   0.700,   0.015,  "B"),
    ("AP-JC-010G",   0.700,   0.015,  "G"),
    ("AP-JC-020Y",   1.200,   0.025,  "Y"),
    ("AP-JC-020W",   1.200,   0.025,  "W"),
    ("AP-JC-020B",   1.200,   0.025,  "B"),
    ("AP-JC-020G",   1.200,   0.025,  "G"),
    ("AP-JC-025Y",   1.500,   0.030,  "Y"),
    ("AP-JC-025W",   1.500,   0.030,  "W"),
    ("AP-JC-025B",   1.500,   0.030,  "B"),
    ("AP-JC-025G",   1.500,   0.030,  "G"),
]


def _setup_boms():
    created = skipped = 0
    for item_code, hdpe_kg, mb_kg, colour in _BOMS:
        try:
            if frappe.db.exists("BOM", {"item": item_code, "docstatus": 1}):
                log(f"SKP  [17] BOM for '{item_code}'")
                skipped += 1
                continue
            mb_item = _COLOUR_MB[colour]
            bom = frappe.get_doc({
                "doctype":    "BOM",
                "item":       item_code,
                "company":    COMPANY,
                "currency":   "MYR",
                "quantity":   1,
                "is_default": 1,
                "is_active":  1,
                "items": [
                    {"item_code": "RM-HDPE-NAT", "qty": hdpe_kg, "uom": "Kg",  "stock_uom": "Kg"},
                    {"item_code": mb_item,        "qty": mb_kg,   "uom": "Kg",  "stock_uom": "Kg"},
                    {"item_code": "RM-CAP-38",    "qty": 1,       "uom": "Nos", "stock_uom": "Nos"},
                ],
            })
            bom.insert(ignore_permissions=True)
            bom.submit()
            frappe.db.commit()
            log(f"OK   [17] BOM {bom.name} — {item_code} ({hdpe_kg} kg HDPE + {mb_kg} kg {mb_item})")
            created += 1
        except Exception as e:
            log(f"ERR  [17] BOM '{item_code}': {e}")
            traceback.print_exc()
    log(f"OK   [17] BOMs done — {created} created, {skipped} skipped")


# ─────────────────────────────────────────────────────────────────────────────
# [18] SALES ORDERS — 5 submitted
# ─────────────────────────────────────────────────────────────────────────────

_SALES_ORDERS = [
    {
        "customer":         "Wilmar Trading (Malaysia) Sdn Bhd",
        "transaction_date": add_days(today(), -15),
        "delivery_date":    add_days(today(), 14),
        "remarks":          "Wilmar Q2 2026 standing order — monthly container supply contract",
        "items": [
            ("AP-JC-020Y", 10000, 6.50),
            ("AP-JC-025Y",  5000, 7.90),
        ],
    },
    {
        "customer":         "Mewah Oils Sdn Bhd",
        "transaction_date": add_days(today(), -10),
        "delivery_date":    add_days(today(), 7),
        "remarks":          "RSPO-certified palm oil season — green container batch",
        "items": [
            ("AP-JC-020G", 3000, 6.50),
            ("AP-JC-025G", 1000, 7.90),
        ],
    },
    {
        "customer":         "Musim Mas Palm Oil Refinery (Johor) Sdn Bhd",
        "transaction_date": add_days(today(), -5),
        "delivery_date":    add_days(today(), 3),
        "remarks":          "Monthly replenishment order — Pasir Gudang refinery",
        "items": [
            ("AP-JC-020Y", 5000, 6.50),
        ],
    },
    {
        "customer":         "Pacoil Sdn Bhd",
        "transaction_date": add_days(today(), -8),
        "delivery_date":    add_days(today(), 10),
        "remarks":          "Mixed order — retail repackaging for JB distribution",
        "items": [
            ("AP-JC-010Y", 800, 3.80),
            ("AP-JC-005Y", 400, 2.20),
        ],
    },
    {
        "customer":         "Palmtop Edible Oils Sdn Bhd",
        "transaction_date": add_days(today(), -3),
        "delivery_date":    add_days(today(), 14),
        "remarks":          "Hari Raya season uplift — 10L yellow cans",
        "items": [
            ("AP-JC-010Y", 2000, 3.80),
        ],
    },
]


def _setup_sales_orders():
    for i, so_data in enumerate(_SALES_ORDERS, 1):
        cust    = so_data["customer"]
        remarks = so_data["remarks"]
        try:
            if frappe.db.exists("Sales Order", {"customer": cust, "docstatus": 1}):
                log(f"SKP  [18] Sales Order for '{cust}'")
                continue
            so = frappe.get_doc({
                "doctype":          "Sales Order",
                "customer":         cust,
                "company":          COMPANY,
                "transaction_date": so_data["transaction_date"],
                "delivery_date":    so_data["delivery_date"],
                "currency":         "MYR",
                "remarks":          remarks,
                "items": [
                    {
                        "item_code":     code,
                        "qty":           qty,
                        "rate":          rate,
                        "delivery_date": so_data["delivery_date"],
                        "warehouse":     WAREHOUSE,
                    }
                    for code, qty, rate in so_data["items"]
                ],
            })
            so.insert(ignore_permissions=True)
            so.submit()
            frappe.db.commit()
            log(f"OK   [18] SO {so.name} | {cust} | MYR {so.grand_total:,.2f}")
        except Exception as e:
            log(f"ERR  [18] SO for '{cust}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [19] PURCHASE ORDERS — 3 submitted
# ─────────────────────────────────────────────────────────────────────────────

_PURCHASE_ORDERS = [
    {
        "supplier":         "Lotte Chemical Titan (M) Sdn Bhd",
        "transaction_date": add_days(today(), -20),
        "schedule_date":    add_days(today(), 10),
        "remarks":          "April 2026 monthly resin procurement — 2-month production batch",
        "items": [
            ("RM-HDPE-NAT",  20000, 5.20, "Kg"),
            ("RM-HDPE-R100",  5000, 3.80, "Kg"),
        ],
    },
    {
        "supplier":         "Clariant (Malaysia) Sdn Bhd",
        "transaction_date": add_days(today(), -14),
        "schedule_date":    add_days(today(), 7),
        "remarks":          "Quarterly colour masterbatch replenishment — yellow and white",
        "items": [
            ("RM-MB-YEL", 500, 18.00, "Kg"),
            ("RM-MB-WHT", 500, 15.00, "Kg"),
        ],
    },
    {
        "supplier":         "Goodshine Packaging Supplies Sdn Bhd",
        "transaction_date": add_days(today(), -10),
        "schedule_date":    add_days(today(), 5),
        "remarks":          "Q2 2026 screw cap bulk order — 100,000 units",
        "items": [
            ("RM-CAP-38", 100000, 0.25, "Nos"),
        ],
    },
]


def _setup_purchase_orders():
    for i, po_data in enumerate(_PURCHASE_ORDERS, 1):
        supp    = po_data["supplier"]
        remarks = po_data["remarks"]
        try:
            if frappe.db.exists("Purchase Order", {"supplier": supp, "docstatus": 1}):
                log(f"SKP  [19] Purchase Order for '{supp}'")
                continue
            po = frappe.get_doc({
                "doctype":          "Purchase Order",
                "supplier":         supp,
                "company":          COMPANY,
                "transaction_date": po_data["transaction_date"],
                "schedule_date":    po_data["schedule_date"],
                "currency":         "MYR",
                "remarks":          remarks,
                "items": [
                    {
                        "item_code":     code,
                        "qty":           qty,
                        "rate":          rate,
                        "uom":           uom,
                        "schedule_date": po_data["schedule_date"],
                        "warehouse":     WAREHOUSE,
                    }
                    for code, qty, rate, uom in po_data["items"]
                ],
            })
            po.insert(ignore_permissions=True)
            po.submit()
            frappe.db.commit()
            log(f"OK   [19] PO {po.name} | {supp} | MYR {po.grand_total:,.2f}")
        except Exception as e:
            log(f"ERR  [19] PO for '{supp}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [20] HR — Departments, Designations, Employees
# ─────────────────────────────────────────────────────────────────────────────

_DEPARTMENTS = [
    "Production",
    "Quality Control",
    "Sales",
    "Finance & Admin",
]

_DESIGNATIONS = [
    "Director", "Production Manager", "QC Officer",
    "Sales Executive", "Machine Operator", "Admin Officer",
]

_EMPLOYEES = [
    # (first_name, last_name, gender, dob, doj, department, designation)
    ("Tan Teck Hong",            "",                    "Male",   "1970-03-15", "2024-07-19", "Production",    "Director"),
    ("Ahmad Fadzillah",          "bin Nordin",          "Male",   "1985-06-20", "2024-08-01", "Production",    "Production Manager"),
    ("Siti Nurhaliza",           "binti Kamaruddin",    "Female", "1992-04-10", "2024-08-01", "Quality Control","QC Officer"),
    ("Lee Chee Wai",             "",                    "Male",   "1990-09-25", "2024-09-01", "Sales",         "Sales Executive"),
    ("Faizal",                   "bin Ibrahim",         "Male",   "1995-11-08", "2024-08-15", "Production",    "Machine Operator"),
    ("Wong Mei Ling",            "",                    "Female", "1988-07-30", "2024-08-01", "Finance & Admin","Admin Officer"),
]


def _fix_bad_departments():
    """ERPNext auto-appends '- <abbr>' to department_name on save.
    If we passed 'Quality Control - AP' as department_name, the stored name
    became 'Quality Control - AP - AP'.  Rename those back to the correct name."""
    bad_pairs = [
        ("Quality Control - AP - AP", "Quality Control - AP"),
        ("Finance & Admin - AP - AP",  "Finance & Admin - AP"),
    ]
    for wrong, correct in bad_pairs:
        try:
            if not frappe.db.exists("Department", wrong):
                continue
            if frappe.db.exists("Department", correct):
                # correct one already exists — just delete the duplicate
                frappe.delete_doc("Department", wrong, force=True, ignore_permissions=True)
                frappe.db.commit()
                log(f"OK   [20] Removed duplicate department '{wrong}'")
            else:
                frappe.rename_doc("Department", wrong, correct, force=True)
                frappe.db.commit()
                log(f"OK   [20] Renamed '{wrong}' → '{correct}'")
        except Exception as e:
            log(f"ERR  [20] Fix department '{wrong}': {e}")


def _setup_hr():
    _fix_bad_departments()

    # Departments — pass PLAIN name; ERPNext auto-appends '- AP'
    for dept in _DEPARTMENTS:
        full_name = f"{dept} - {ABBR}"   # the name ERPNext will produce
        try:
            if frappe.db.exists("Department", full_name):
                log(f"SKP  [20] Department '{full_name}'")
                continue
            d = frappe.get_doc({
                "doctype":           "Department",
                "department_name":   dept,          # plain name, NO "- AP" suffix
                "parent_department": "All Departments",
                "company":           COMPANY,
            })
            d.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [20] Department '{full_name}'")
        except Exception as e:
            log(f"ERR  [20] Department '{full_name}': {e}")

    # Designations
    for desig in _DESIGNATIONS:
        try:
            if frappe.db.exists("Designation", desig):
                log(f"SKP  [20] Designation '{desig}'")
                continue
            d = frappe.get_doc({"doctype": "Designation", "designation_name": desig})
            d.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [20] Designation '{desig}'")
        except Exception as e:
            log(f"ERR  [20] Designation '{desig}': {e}")

    # Employees
    for first_name, last_name, gender, dob, doj, dept, desig in _EMPLOYEES:
        emp_full = f"{first_name} {last_name}".strip()
        dept_full = f"{dept} - {ABBR}"
        try:
            if frappe.db.exists("Employee", {"employee_name": emp_full}):
                log(f"SKP  [20] Employee '{emp_full}'")
                continue
            emp = frappe.get_doc({
                "doctype":        "Employee",
                "first_name":     first_name,
                "last_name":      last_name,
                "gender":         gender,
                "date_of_birth":  dob,
                "date_of_joining": doj,
                "company":        COMPANY,
                "department":     dept_full,
                "designation":    desig,
                "status":         "Active",
            })
            emp.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [20] Employee '{emp_full}' ({desig}, {dept_full}) → {emp.name}")
        except Exception as e:
            log(f"ERR  [20] Employee '{emp_full}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [21] SALARY STRUCTURE & ASSIGNMENTS
# ─────────────────────────────────────────────────────────────────────────────

_SALARY_STRUCTURE = "Arising Packaging Standard"

# (employee_name, base_salary)  — from_date = start of current fiscal year
_EMP_SALARIES = [
    ("Tan Teck Hong",                    8000.00),
    ("Ahmad Fadzillah bin Nordin",       5500.00),
    ("Siti Nurhaliza binti Kamaruddin",  3800.00),
    ("Lee Chee Wai",                     3500.00),
    ("Faizal bin Ibrahim",               2500.00),
    ("Wong Mei Ling",                    3200.00),
]


def _setup_salary_structure():
    # Create Salary Structure
    try:
        if frappe.db.exists("Salary Structure", _SALARY_STRUCTURE):
            log(f"SKP  [21] Salary Structure '{_SALARY_STRUCTURE}'")
        else:
            ss = frappe.get_doc({
                "doctype":           "Salary Structure",
                "name":              _SALARY_STRUCTURE,
                "company":           COMPANY,
                "currency":          "MYR",
                "payroll_frequency": "Monthly",
                "is_active":         "Yes",
                "earnings": [
                    {
                        "salary_component":         "Basic Salary",
                        "abbr":                     "BS",
                        "amount_based_on_formula":  0,
                        "depends_on_lwp":            1,
                    },
                ],
                "deductions": [
                    {
                        "salary_component":         "EPF Employee",
                        "abbr":                     "EPF_EE",
                        "amount_based_on_formula":  1,
                        "formula":                  "base * 0.11",
                    },
                    {
                        "salary_component":         "SOCSO Employee",
                        "abbr":                     "SOCSO_EE",
                        "amount_based_on_formula":  0,
                        "amount":                   0,
                    },
                    {
                        "salary_component":         "Monthly Tax Deduction",
                        "abbr":                     "MTD",
                        "amount_based_on_formula":  0,
                        "amount":                   0,
                    },
                ],
            })
            ss.insert(ignore_permissions=True)
            ss.submit()
            frappe.db.commit()
            log(f"OK   [21] Salary Structure '{_SALARY_STRUCTURE}' submitted")
    except Exception as e:
        log(f"ERR  [21] Salary Structure: {e}")
        traceback.print_exc()

    # Salary Structure Assignments — one per employee
    FROM_DATE = "2025-07-01"  # start of fiscal year 2025-2026
    for emp_name, base in _EMP_SALARIES:
        try:
            emp_id = frappe.db.get_value("Employee", {"employee_name": emp_name}, "name")
            if not emp_id:
                log(f"SKP  [21] Assignment skipped — employee '{emp_name}' not found")
                continue
            if frappe.db.exists("Salary Structure Assignment", {
                "employee": emp_id,
                "salary_structure": _SALARY_STRUCTURE,
                "docstatus": ("!=", 2),
            }):
                log(f"SKP  [21] Assignment already exists for '{emp_name}'")
                continue
            ssa = frappe.get_doc({
                "doctype":           "Salary Structure Assignment",
                "employee":          emp_id,
                "salary_structure":  _SALARY_STRUCTURE,
                "from_date":         FROM_DATE,
                "company":           COMPANY,
                "currency":          "MYR",
                "base":              base,
            })
            ssa.insert(ignore_permissions=True)
            ssa.submit()
            frappe.db.commit()
            log(f"OK   [21] Assignment '{emp_name}' → MYR {base:,.2f}/month")
        except Exception as e:
            log(f"ERR  [21] Assignment '{emp_name}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run():
    frappe.set_user("Administrator")

    _setup_territories()       # [12]
    _setup_payment_terms()     # [13]
    _setup_contacts()          # [14]
    _attach_payment_terms()    # [15]
    _setup_opening_stock()     # [16]
    _setup_boms()              # [17]
    _setup_sales_orders()      # [18]
    _setup_purchase_orders()   # [19]
    _setup_hr()                # [20]
    _setup_salary_structure()  # [21]

    print("\n=== SUMMARY ===")
    for r in results:
        print(r)
