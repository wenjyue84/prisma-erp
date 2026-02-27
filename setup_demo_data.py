"""
Arising Packaging Sdn Bhd — Comprehensive Demo Data Seed v1.0
=============================================================
Covers ALL major ERPNext modules:
  [22] Additional Items          — spare parts, services, consumables
  [23] Additional Customers      — 8 more Malaysian companies
  [24] Additional Suppliers      — 5 more suppliers
  [25] Addresses                 — billing + shipping for customers/suppliers
  [26] Quotations                — 4 draft/submitted quotations
  [27] Delivery Notes            — 3 submitted delivery notes
  [28] Sales Invoices (submitted)— 4 paid invoices with payment entries
  [29] Material Requests         — 4 MRs (purchase + manufacture)
  [30] Purchase Receipts         — 3 GRNs against existing POs
  [31] Purchase Invoices         — 3 submitted bills
  [32] Stock Transfers           — inter-warehouse stock moves
  [33] Work Orders               — 5 WOs (3 completed, 2 in-progress)
  [34] Projects & Tasks          — 3 projects with tasks, timesheets
  [35] Quality Inspection        — templates + 4 inspections
  [36] CRM                       — 5 Leads, 3 Opportunities
  [37] Support Issues            — 4 customer issues
  [38] Assets                    — asset categories + 5 assets
  [39] Journal Entries           — 3 expense accruals
  [40] Additional Warehouses     — finished goods + raw mat sub-stores

Deploy & run:
  docker cp setup_demo_data.py \\
    prisma-erp-backend-1:/home/frappe/frappe-bench/apps/frappe/frappe/setup_demo_data.py
  docker exec prisma-erp-backend-1 bash -c \\
    "cd /home/frappe/frappe-bench && bench --site frontend execute frappe.setup_demo_data.run"
"""

import frappe
import traceback
from frappe.utils import today, add_days, add_months, getdate, nowdate

COMPANY     = "Arising Packaging"
ABBR        = "AP"
WAREHOUSE   = "Arising Packaging Warehouse - AP"
COST_CENTER = "Main - AP"
results     = []


def log(msg):
    results.append(msg)
    print(msg)


def _safe_insert(doc):
    """Insert and commit, return doc or None on error."""
    try:
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc
    except Exception as e:
        frappe.db.rollback()
        log(f"ERR  insert {doc.doctype}: {e}")
        return None


def _safe_submit(doc):
    try:
        doc.submit()
        frappe.db.commit()
        return doc
    except Exception as e:
        frappe.db.rollback()
        log(f"ERR  submit {doc.doctype} {getattr(doc, 'name', '')}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# [22] ADDITIONAL ITEMS
# ─────────────────────────────────────────────────────────────────────────────

_EXTRA_ITEMS = [
    # (item_code, item_name, item_group, uom, stock_uom, is_stock, valuation_rate, standard_rate, description)
    # Spare Parts
    ("SP-MOULD-010",   "10L Bottle Mould (Spare)",        "Spare Parts",   "Nos", "Nos", 1,  2500.00, 3500.00, "Blow moulding die — 10L jerry can"),
    ("SP-MOULD-020",   "20L Bottle Mould (Spare)",        "Spare Parts",   "Nos", "Nos", 1,  3500.00, 4800.00, "Blow moulding die — 20L jerry can"),
    ("SP-HYDRAULIC",   "Hydraulic Seal Kit",              "Spare Parts",   "Set", "Set", 1,   180.00,  250.00, "Hydraulic press seal kit for blow moulding machine"),
    ("SP-HEATING-BAND","Heating Band 220V 500W",          "Spare Parts",   "Nos", "Nos", 1,    45.00,   75.00, "Extruder heating band"),
    ("SP-SCREW-BARREL","Screw & Barrel Assembly",         "Spare Parts",   "Set", "Set", 1, 12000.00, 16000.00,"Extruder screw-barrel set — 60mm dia"),
    # Consumables
    ("CON-LUBRICANT",  "Industrial Lubricant Grease",     "Consumables",   "Kg",  "Kg",  1,    22.00,   35.00, "High-temp bearing grease"),
    ("CON-SOLVENT",    "Mould Release Spray 500ml",       "Consumables",   "Can", "Can", 1,    18.00,   28.00, "Silicone mould release agent"),
    ("CON-PPFILM",     "Stretch Wrap Film 500m",          "Consumables",   "Roll","Roll",1,    55.00,   75.00, "LLDPE pallet stretch film"),
    ("CON-LABEL-YEL",  "Yellow Product Label (roll/1000)","Consumables",   "Roll","Roll",1,    12.00,   20.00, "Pre-printed yellow label — AP-JC-010Y"),
    ("CON-PALLETBOARD","Pallet Board 1200x1000mm",        "Consumables",   "Nos", "Nos", 1,    28.00,   40.00, "Wooden pallet 4-way entry"),
    # Services
    ("SVC-MACHINE-SVC","Annual Machine Service Contract", "Services",      "Year","Year",0,     0.00, 8500.00, "Full preventive maintenance by OEM"),
    ("SVC-QC-AUDIT",   "Quality Audit Service",           "Services",      "Nos", "Nos", 0,     0.00, 1800.00, "Third-party ISO quality audit"),
    ("SVC-FREIGHT-DO",  "Outbound Freight — Peninsular",  "Services",      "Trip","Trip",0,     0.00,  450.00, "Lorry delivery, Peninsular Malaysia"),
    ("SVC-FREIGHT-EA",  "Outbound Freight — East Malaysia","Services",     "Trip","Trip",0,     0.00, 1200.00, "Sea freight, Sabah/Sarawak"),
    # Packaging
    ("PKG-CARTON-10",  "Export Carton for 10L Cans",      "Packaging",     "Nos", "Nos", 1,     1.80,   2.50, "4-ply RSC carton, holds 12 pcs 10L"),
    ("PKG-CARTON-20",  "Export Carton for 20L Cans",      "Packaging",     "Nos", "Nos", 1,     2.20,   3.20, "5-ply RSC carton, holds 4 pcs 20L"),
    ("PKG-SHRINK",     "Shrink Sleeve Label (per 1000)",  "Packaging",     "Nos", "Nos", 1,    35.00,  55.00, "PETG shrink sleeve for 25L cans"),
    # Raw Materials additions
    ("RM-HDPE-HB",     "HDPE HB5502 (High-Blow Grade)",   "Raw Material",  "Kg",  "Kg",  1,     6.10,   0.00, "High-blow HDPE for large containers"),
    ("RM-MB-BLK",      "Black Masterbatch MB-BK100",      "Raw Material",  "Kg",  "Kg",  1,    14.00,   0.00, "Carbon black MB, 50% loading"),
    ("RM-MB-RED",      "Red Masterbatch MB-RD200",        "Raw Material",  "Kg",  "Kg",  1,    22.00,   0.00, "Red oxide MB, 40% loading"),
    ("RM-UV-STAB",     "UV Stabiliser Masterbatch",       "Raw Material",  "Kg",  "Kg",  1,    55.00,   0.00, "UV-405 hindered amine for outdoor use"),
    ("RM-CAP-45",      "HDPE Screw Cap 45mm",             "Raw Material",  "Nos", "Nos", 1,     0.35,   0.00, "45mm neck cap for 25L cans"),
]

_ITEM_GROUPS = [
    "Spare Parts", "Consumables", "Services", "Packaging",
]


def _setup_extra_items():
    # Item Groups first
    for ig in _ITEM_GROUPS:
        if not frappe.db.exists("Item Group", ig):
            try:
                g = frappe.get_doc({
                    "doctype": "Item Group",
                    "item_group_name": ig,
                    "parent_item_group": "All Item Groups",
                    "is_group": 0,
                })
                g.insert(ignore_permissions=True)
                frappe.db.commit()
                log(f"OK   [22] Item Group '{ig}'")
            except Exception as e:
                log(f"ERR  [22] Item Group '{ig}': {e}")
        else:
            log(f"SKP  [22] Item Group '{ig}'")

    for code, name, grp, uom, suom, is_stock, valrate, std_rate, desc in _EXTRA_ITEMS:
        if frappe.db.exists("Item", code):
            log(f"SKP  [22] Item '{code}'")
            continue
        try:
            item = frappe.get_doc({
                "doctype":            "Item",
                "item_code":          code,
                "item_name":          name,
                "item_group":         grp,
                "uom":                uom,
                "stock_uom":          suom,
                "is_stock_item":      is_stock,
                "is_purchase_item":   1,
                "is_sales_item":      1 if grp in ("Services","Packaging","Spare Parts") else 0,
                "valuation_rate":     valrate,
                "standard_rate":      std_rate,
                "description":        desc,
                "opening_stock":      0,
            })
            item.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [22] Item '{code}' — {name}")
        except Exception as e:
            log(f"ERR  [22] Item '{code}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [23] ADDITIONAL CUSTOMERS
# ─────────────────────────────────────────────────────────────────────────────

_NEW_CUSTOMERS = [
    # (name, type, group, territory, tin, id_type, id_no, credit_limit)
    ("Felda Vegetable Oil Products Sdn Bhd",  "Company",    "Commercial", "Selangor",       "C11122334455", "BRN", "197701000221", 200000.0),
    ("Carotino Sdn Bhd",                      "Company",    "Commercial", "Johor",          "C22233445566", "BRN", "198601000332", 150000.0),
    ("Sime Darby Oils Johor Sdn Bhd",         "Company",    "Commercial", "Johor",          "C33344556677", "BRN", "199001000443", 300000.0),
    ("Bunge Loders Croklaan",                 "Company",    "Commercial", "Selangor",       "C44455667788", "BRN", "200001000554", 250000.0),
    ("AAK Malaysia Sdn Bhd",                  "Company",    "Commercial", "Selangor",       "C55566778899", "BRN", "201501000665", 180000.0),
    ("Petronas Chemicals Marketing Sdn Bhd",  "Company",    "Commercial", "Kuala Lumpur",   "C66677889900", "BRN", "199901000776", 500000.0),
    ("Poh Kong Holdings Bhd",                 "Company",    "Commercial", "Selangor",       "C77788990011", "BRN", "200201000887", 100000.0),
    ("Lim Ah Kow",                            "Individual", "Individual", "Johor",          "IG98765432109","NRIC","750215-01-5678", 5000.0),
]


def _setup_extra_customers():
    for cname, ctype, cgrp, terr, tin, id_type, id_no, credit in _NEW_CUSTOMERS:
        if frappe.db.exists("Customer", cname):
            log(f"SKP  [23] Customer '{cname}'")
            continue
        try:
            c = frappe.get_doc({
                "doctype":       "Customer",
                "customer_name": cname,
                "customer_type": ctype,
                "customer_group": cgrp,
                "territory":     terr,
                "credit_limit":  credit,
                "custom_customer_tin_number": tin,
                "custom_customer__registrationicpassport_type": id_type,
                "custom_customer_registrationicpassport_number": id_no,
            })
            c.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [23] Customer '{cname}'")
        except Exception as e:
            log(f"ERR  [23] Customer '{cname}': {e}")


# ─────────────────────────────────────────────────────────────────────────────
# [24] ADDITIONAL SUPPLIERS
# ─────────────────────────────────────────────────────────────────────────────

_NEW_SUPPLIERS = [
    # (name, group, tin, id_type, id_no, payment_terms)
    ("Toray Plastics (Malaysia) Sdn Bhd",   "Raw Material", "C12399887766", "BRN", "199801000111", "30 Days Net"),
    ("ExxonMobil Chemical (Malaysia) Sdn Bhd","Raw Material","C23400998877", "BRN", "198501000222", "60 Days Net"),
    ("UPM Packaging Sdn Bhd",               "Packaging Material","C34511009988","BRN","200301000333","30 Days Net"),
    ("Indah Water Services Sdn Bhd",        "Services",     "C45622110099", "BRN", "199201000444", "14 Days Net"),
    ("Tenaga Nasional Berhad",              "Utilities",    "C56733221100", "BRN", "199001000555", "14 Days Net"),
]

_SUPPLIER_GROUPS = ["Packaging Material", "Utilities"]


def _setup_extra_suppliers():
    for sg in _SUPPLIER_GROUPS:
        if not frappe.db.exists("Supplier Group", sg):
            try:
                g = frappe.get_doc({
                    "doctype": "Supplier Group",
                    "supplier_group_name": sg,
                    "parent_supplier_group": "All Supplier Groups",
                })
                g.insert(ignore_permissions=True)
                frappe.db.commit()
                log(f"OK   [24] Supplier Group '{sg}'")
            except Exception as e:
                log(f"ERR  [24] Supplier Group '{sg}': {e}")

    for sname, sgrp, tin, id_type, id_no, pt in _NEW_SUPPLIERS:
        if frappe.db.exists("Supplier", sname):
            log(f"SKP  [24] Supplier '{sname}'")
            continue
        try:
            s = frappe.get_doc({
                "doctype":        "Supplier",
                "supplier_name":  sname,
                "supplier_group": sgrp,
                "supplier_type":  "Company",
                "custom_company_tin_number": tin,
            })
            s.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [24] Supplier '{sname}'")
        except Exception as e:
            log(f"ERR  [24] Supplier '{sname}': {e}")


# ─────────────────────────────────────────────────────────────────────────────
# [25] ADDRESSES
# ─────────────────────────────────────────────────────────────────────────────

_ADDRESSES = [
    # (title, type, line1, line2, city, state, pincode, phone, email, link_doctype, link_name)
    ("Felda Vegetable Oil-Billing",  "Billing",  "Lot 1234, Kawasan Perindustrian Kota Kemuning","",                 "Shah Alam","Selangor","40460",    "+60-3-5161-2000","accounts@felvop.com.my",    "Customer","Felda Vegetable Oil Products Sdn Bhd"),
    ("Carotino-Billing",            "Billing",  "No 1, Jalan Padu, Kawasan Perindustrian Pasir Gudang","",          "Pasir Gudang","Johor","81700",    "+60-7-251-3888","billing@carotino.com.my",    "Customer","Carotino Sdn Bhd"),
    ("Sime Darby Oils-Billing",     "Billing",  "Jalan Perwira, Kawasan Perindustrian Pasir Gudang","",             "Pasir Gudang","Johor","81700",    "+60-7-251-2000","accounts@simedarbyoils.com","Customer","Sime Darby Oils Johor Sdn Bhd"),
    ("Bunge Loders-Billing",        "Billing",  "Lot 6, Jalan Kilang 1/1, SILC Nusajaya","",                       "Johor Bahru","Johor","79200",     "+60-7-509-8888","finance@loders.com.my",      "Customer","Bunge Loders Croklaan"),
    ("AAK Malaysia-Billing",        "Billing",  "Wisma AAK, Jalan Tandang, Batu 3, Jalan Kelang Lama","",          "Kuala Lumpur","Kuala Lumpur","58100","+60-3-7783-2600","ar@aak.com.my",            "Customer","AAK Malaysia Sdn Bhd"),
    ("Petronas Chem-Billing",       "Billing",  "Level 12, Tower 1, PETRONAS Twin Towers, KLCC","",                "Kuala Lumpur","Kuala Lumpur","50088","+60-3-2051-5000","chem.billing@petronas.com.my","Customer","Petronas Chemicals Marketing Sdn Bhd"),
    ("Poh Kong-Billing",            "Billing",  "Poh Kong Headquarters, 12, Jalan 223, Seksyen 51A","",            "Petaling Jaya","Selangor","46100", "+60-3-7958-8000","billing@pohkong.com.my",    "Customer","Poh Kong Holdings Bhd"),
    ("Lim Ah Kow-Billing",          "Billing",  "No. 45, Jalan Stulang Darat 5","Taman Stulang Darat",             "Johor Bahru","Johor","80300",      "+60-12-721-5678","limahkow@gmail.com",        "Customer","Lim Ah Kow"),
    # Supplier addresses
    ("Toray-Billing",               "Billing",  "No. 8, Jalan Segambut Tengah","Kawasan Perindustrian Segambut",   "Kuala Lumpur","Kuala Lumpur","51200","+60-3-6257-9000","accounts@toray.com.my",     "Supplier","Toray Plastics (Malaysia) Sdn Bhd"),
    ("ExxonMobil-Billing",          "Billing",  "Lot 3, Jalan Waja 14, Teluk Panglima Garang Industrial Park","",  "Kuala Langat","Selangor","42500",   "+60-3-3122-8000","billing@exxon.com.my",       "Supplier","ExxonMobil Chemical (Malaysia) Sdn Bhd"),
    ("UPM Packaging-Billing",       "Billing",  "Kawasan Perindustrian Balakong, Jalan Balakong","",               "Cheras","Selangor","43300",         "+60-3-9074-3000","ar@upm-packaging.com.my",   "Supplier","UPM Packaging Sdn Bhd"),
]


def _setup_addresses():
    for title, atype, l1, l2, city, state, pin, phone, email, link_dt, link_name in _ADDRESSES:
        addr_name = f"{title}"
        if frappe.db.exists("Address", addr_name):
            log(f"SKP  [25] Address '{addr_name}'")
            continue
        try:
            addr = frappe.get_doc({
                "doctype":       "Address",
                "address_title": title.rsplit("-", 1)[0].strip(),
                "address_type":  atype,
                "address_line1": l1,
                "address_line2": l2,
                "city":          city,
                "state":         state,
                "pincode":       pin,
                "country":       "Malaysia",
                "phone":         phone,
                "email_id":      email,
                "links": [{"link_doctype": link_dt, "link_name": link_name}],
            })
            addr.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [25] Address '{addr_name}' → {link_dt} '{link_name}'")
        except Exception as e:
            log(f"ERR  [25] Address '{addr_name}': {e}")


# ─────────────────────────────────────────────────────────────────────────────
# [26] QUOTATIONS
# ─────────────────────────────────────────────────────────────────────────────

_QUOTATIONS = [
    {
        "party_name":       "Felda Vegetable Oil Products Sdn Bhd",
        "transaction_date": add_days(today(), -20),
        "valid_till":       add_days(today(), 10),
        "remarks":          "Q2 2026 bulk quote — 20L yellow cans for palm oil refinery",
        "items": [
            ("AP-JC-020Y", 20000, 6.30),
            ("AP-JC-025Y",  5000, 7.70),
            ("SVC-FREIGHT-DO", 10, 450.0),
        ],
    },
    {
        "party_name":       "Carotino Sdn Bhd",
        "transaction_date": add_days(today(), -15),
        "valid_till":       add_days(today(), 15),
        "remarks":          "Special run — 10L & 5L bottles for retail repack (carotino brand)",
        "items": [
            ("AP-JC-010Y", 5000, 3.75),
            ("AP-JC-005Y", 2000, 2.15),
        ],
    },
    {
        "party_name":       "Sime Darby Oils Johor Sdn Bhd",
        "transaction_date": add_days(today(), -8),
        "valid_till":       add_days(today(), 22),
        "remarks":          "Annual contract quote — mixed colour 20L cans for 3 refineries",
        "items": [
            ("AP-JC-020Y", 15000, 6.20),
            ("AP-JC-020W", 10000, 6.20),
            ("AP-JC-020B",  3000, 6.20),
        ],
    },
    {
        "party_name":       "Lim Ah Kow",
        "transaction_date": add_days(today(), -3),
        "valid_till":       add_days(today(), 7),
        "remarks":          "Small batch retail order — 2L & 5L white cans",
        "items": [
            ("AP-JC-002W",  100, 1.60),
            ("AP-JC-005W",   50, 2.15),
        ],
    },
]


def _setup_quotations():
    for q_data in _QUOTATIONS:
        pname = q_data["party_name"]
        if frappe.db.exists("Quotation", {"party_name": pname, "docstatus": ["!=", 2]}):
            log(f"SKP  [26] Quotation for '{pname}'")
            continue
        try:
            q = frappe.get_doc({
                "doctype":          "Quotation",
                "quotation_to":     "Customer",
                "party_name":       pname,
                "company":          COMPANY,
                "transaction_date": q_data["transaction_date"],
                "valid_till":       q_data["valid_till"],
                "currency":         "MYR",
                "remarks":          q_data["remarks"],
                "items": [
                    {"item_code": code, "qty": qty, "rate": rate}
                    for code, qty, rate in q_data["items"]
                ],
            })
            q.insert(ignore_permissions=True)
            q.submit()
            frappe.db.commit()
            log(f"OK   [26] Quotation {q.name} | {pname} | MYR {q.grand_total:,.2f}")
        except Exception as e:
            log(f"ERR  [26] Quotation for '{pname}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [27] DELIVERY NOTES
# ─────────────────────────────────────────────────────────────────────────────

_DELIVERY_NOTES = [
    {
        "customer":      "Wilmar Trading (Malaysia) Sdn Bhd",
        "posting_date":  add_days(today(), -12),
        "remarks":       "Delivery to Wilmar Pasir Gudang depot — partial SO fulfillment",
        "items": [
            ("AP-JC-020Y", 5000, 6.50),
            ("AP-JC-025Y", 2000, 7.90),
        ],
    },
    {
        "customer":      "Mewah Oils Sdn Bhd",
        "posting_date":  add_days(today(), -7),
        "remarks":       "Green can delivery — Mewah Bandar Baru Enstek plant",
        "items": [
            ("AP-JC-020G", 1500, 6.50),
        ],
    },
    {
        "customer":      "Pacoil Sdn Bhd",
        "posting_date":  add_days(today(), -4),
        "remarks":       "Small format retail delivery — Pacoil JB warehouse",
        "items": [
            ("AP-JC-010Y", 400, 3.80),
            ("AP-JC-005Y", 200, 2.20),
        ],
    },
]


def _setup_delivery_notes():
    for dn_data in _DELIVERY_NOTES:
        cust = dn_data["customer"]
        if frappe.db.exists("Delivery Note", {"customer": cust, "docstatus": 1}):
            log(f"SKP  [27] Delivery Note for '{cust}'")
            continue
        try:
            dn = frappe.get_doc({
                "doctype":        "Delivery Note",
                "customer":       cust,
                "company":        COMPANY,
                "posting_date":   dn_data["posting_date"],
                "currency":       "MYR",
                "remarks":        dn_data["remarks"],
                "items": [
                    {
                        "item_code": code,
                        "qty":       qty,
                        "rate":      rate,
                        "warehouse": WAREHOUSE,
                    }
                    for code, qty, rate in dn_data["items"]
                ],
            })
            dn.insert(ignore_permissions=True)
            dn.submit()
            frappe.db.commit()
            log(f"OK   [27] DN {dn.name} | {cust} | MYR {dn.grand_total:,.2f}")
        except Exception as e:
            log(f"ERR  [27] DN for '{cust}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [28] SUBMITTED SALES INVOICES + PAYMENT ENTRIES
# ─────────────────────────────────────────────────────────────────────────────

_SALES_INVOICES = [
    {
        "customer":      "IOI Palm Oleo (Johor) Sdn Bhd",
        "posting_date":  add_days(today(), -30),
        "due_date":      add_days(today(), 30),
        "remarks":       "IOI — March 2026 monthly invoice",
        "items": [
            ("AP-JC-020Y", 8000, 6.50),
            ("AP-JC-020W", 4000, 6.50),
        ],
        "paid": True,
    },
    {
        "customer":      "FGV Palm Industries Sdn Bhd",
        "posting_date":  add_days(today(), -25),
        "due_date":      add_days(today(), 35),
        "remarks":       "FGV Felda Besout — 25L yellow can monthly supply",
        "items": [
            ("AP-JC-025Y", 3000, 7.90),
            ("AP-JC-025W", 1500, 7.90),
        ],
        "paid": True,
    },
    {
        "customer":      "KongHoo Oils Trading Sdn Bhd",
        "posting_date":  add_days(today(), -18),
        "due_date":      add_days(today(), 12),
        "remarks":       "KongHoo JB — mixed SKU invoice Feb 2026",
        "items": [
            ("AP-JC-010Y", 1000, 3.80),
            ("AP-JC-010W",  500, 3.80),
            ("AP-JC-005Y",  300, 2.20),
        ],
        "paid": False,
    },
    {
        "customer":      "Lian Industries Sdn Bhd",
        "posting_date":  add_days(today(), -10),
        "due_date":      add_days(today(), 35),
        "remarks":       "Lian Industries — 20L blue food-grade cans for shortening",
        "items": [
            ("AP-JC-020B", 2000, 6.50),
        ],
        "paid": False,
    },
]


def _setup_sales_invoices():
    for si_data in _SALES_INVOICES:
        cust = si_data["customer"]
        if frappe.db.exists("Sales Invoice", {"customer": cust, "docstatus": 1}):
            log(f"SKP  [28] Sales Invoice for '{cust}'")
            continue
        try:
            si = frappe.get_doc({
                "doctype":        "Sales Invoice",
                "customer":       cust,
                "company":        COMPANY,
                "posting_date":   si_data["posting_date"],
                "due_date":       si_data["due_date"],
                "currency":       "MYR",
                "remarks":        si_data["remarks"],
                "custom_malaysia_tax_category": "01 : Sales Tax",
                "custom_invoicetype_code":      "01 :  Invoice",
                "items": [
                    {"item_code": code, "qty": qty, "rate": rate}
                    for code, qty, rate in si_data["items"]
                ],
            })
            si.insert(ignore_permissions=True)
            si.submit()
            frappe.db.commit()
            log(f"OK   [28] SI {si.name} | {cust} | MYR {si.grand_total:,.2f}")

            if si_data["paid"]:
                _make_payment_entry(si, "Sales Invoice", cust, si.grand_total, si_data["posting_date"])
        except Exception as e:
            log(f"ERR  [28] SI for '{cust}': {e}")
            traceback.print_exc()


def _make_payment_entry(doc, dt, party, amount, date):
    try:
        ar_account = f"Debtors - {ABBR}"
        bank_account = frappe.db.get_value("Account", {"account_type": "Bank", "company": COMPANY}, "name")
        if not bank_account:
            log(f"SKP  [28] Payment — no bank account found for {COMPANY}")
            return
        pe = frappe.get_doc({
            "doctype":             "Payment Entry",
            "payment_type":        "Receive",
            "party_type":          "Customer",
            "party":               party,
            "company":             COMPANY,
            "posting_date":        add_days(date, 3),
            "paid_from":           ar_account,
            "paid_to":             bank_account,
            "paid_from_account_currency": "MYR",
            "paid_to_account_currency":   "MYR",
            "paid_amount":         amount,
            "received_amount":     amount,
            "references": [{
                "reference_doctype": dt,
                "reference_name":    doc.name,
                "allocated_amount":  amount,
            }],
            "mode_of_payment":     "Bank Transfer",
        })
        pe.insert(ignore_permissions=True)
        pe.submit()
        frappe.db.commit()
        log(f"OK   [28] Payment Entry {pe.name} | {party} | MYR {amount:,.2f}")
    except Exception as e:
        log(f"ERR  [28] Payment Entry for '{party}': {e}")


# ─────────────────────────────────────────────────────────────────────────────
# [29] MATERIAL REQUESTS
# ─────────────────────────────────────────────────────────────────────────────

_MATERIAL_REQUESTS = [
    {
        "mr_type":       "Purchase",
        "schedule_date": add_days(today(), 7),
        "remarks":       "MR — Masterbatch replenishment (blue + green + black)",
        "items": [
            ("RM-MB-BLU", 300, "Kg",  WAREHOUSE),
            ("RM-MB-GRN", 300, "Kg",  WAREHOUSE),
            ("RM-MB-BLK", 200, "Kg",  WAREHOUSE),
        ],
    },
    {
        "mr_type":       "Purchase",
        "schedule_date": add_days(today(), 14),
        "remarks":       "MR — Screw caps quarterly reorder (38mm + 45mm)",
        "items": [
            ("RM-CAP-38", 200000, "Nos", WAREHOUSE),
            ("RM-CAP-45",  50000, "Nos", WAREHOUSE),
        ],
    },
    {
        "mr_type":       "Purchase",
        "schedule_date": add_days(today(), 5),
        "remarks":       "MR — Consumables restock: lubricant, stretch film, pallets",
        "items": [
            ("CON-LUBRICANT", 50,  "Kg",   WAREHOUSE),
            ("CON-PPFILM",    30,  "Roll",  WAREHOUSE),
            ("CON-PALLETBOARD",100,"Nos",  WAREHOUSE),
        ],
    },
    {
        "mr_type":       "Material Transfer",
        "schedule_date": add_days(today(), 2),
        "remarks":       "MR — Issue raw materials to production floor for WO-Q2-2026",
        "items": [
            ("RM-HDPE-NAT",  5000, "Kg",  WAREHOUSE),
            ("RM-MB-YEL",     100, "Kg",  WAREHOUSE),
            ("RM-CAP-38",   10000, "Nos", WAREHOUSE),
        ],
    },
]


def _setup_material_requests():
    for i, mr_data in enumerate(_MATERIAL_REQUESTS, 1):
        tag = f"MR-DEMO-{i:02d}"
        if frappe.db.exists("Material Request", {"remarks": mr_data["remarks"]}):
            log(f"SKP  [29] Material Request '{tag}'")
            continue
        try:
            mr = frappe.get_doc({
                "doctype":          "Material Request",
                "material_request_type": mr_data["mr_type"],
                "company":          COMPANY,
                "schedule_date":    mr_data["schedule_date"],
                "remarks":          mr_data["remarks"],
                "items": [
                    {
                        "item_code":     code,
                        "qty":           qty,
                        "uom":           uom,
                        "schedule_date": mr_data["schedule_date"],
                        "warehouse":     wh,
                    }
                    for code, qty, uom, wh in mr_data["items"]
                ],
            })
            mr.insert(ignore_permissions=True)
            mr.submit()
            frappe.db.commit()
            log(f"OK   [29] Material Request {mr.name} ({mr_data['mr_type']})")
        except Exception as e:
            log(f"ERR  [29] Material Request #{i}: {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [30] PURCHASE RECEIPTS (GRN)
# ─────────────────────────────────────────────────────────────────────────────

_PURCHASE_RECEIPTS = [
    {
        "supplier":       "Lotte Chemical Titan (M) Sdn Bhd",
        "posting_date":   add_days(today(), -5),
        "remarks":        "GRN — April HDPE resin delivery (partial: 15,000 kg received)",
        "items": [
            ("RM-HDPE-NAT",  15000, 5.20, "Kg"),
            ("RM-HDPE-R100",  3000, 3.80, "Kg"),
        ],
    },
    {
        "supplier":       "Clariant (Malaysia) Sdn Bhd",
        "posting_date":   add_days(today(), -3),
        "remarks":        "GRN — Quarterly masterbatch delivery complete",
        "items": [
            ("RM-MB-YEL",  500, 18.00, "Kg"),
            ("RM-MB-WHT",  500, 15.00, "Kg"),
        ],
    },
    {
        "supplier":       "Goodshine Packaging Supplies Sdn Bhd",
        "posting_date":   add_days(today(), -2),
        "remarks":        "GRN — Screw cap bulk delivery Q2 2026",
        "items": [
            ("RM-CAP-38", 100000, 0.25, "Nos"),
        ],
    },
]


def _setup_purchase_receipts():
    for pr_data in _PURCHASE_RECEIPTS:
        supp = pr_data["supplier"]
        if frappe.db.exists("Purchase Receipt", {"supplier": supp, "docstatus": 1}):
            log(f"SKP  [30] Purchase Receipt for '{supp}'")
            continue
        try:
            pr = frappe.get_doc({
                "doctype":         "Purchase Receipt",
                "supplier":        supp,
                "company":         COMPANY,
                "posting_date":    pr_data["posting_date"],
                "currency":        "MYR",
                "remarks":         pr_data["remarks"],
                "items": [
                    {
                        "item_code":       code,
                        "qty":             qty,
                        "rate":            rate,
                        "uom":             uom,
                        "stock_uom":       uom,
                        "warehouse":       WAREHOUSE,
                        "accepted_qty":    qty,
                    }
                    for code, qty, rate, uom in pr_data["items"]
                ],
            })
            pr.insert(ignore_permissions=True)
            pr.submit()
            frappe.db.commit()
            log(f"OK   [30] Purchase Receipt {pr.name} | {supp} | MYR {pr.grand_total:,.2f}")
        except Exception as e:
            log(f"ERR  [30] Purchase Receipt for '{supp}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [31] PURCHASE INVOICES (BILLS)
# ─────────────────────────────────────────────────────────────────────────────

_PURCHASE_INVOICES = [
    {
        "supplier":       "Lotte Chemical Titan (M) Sdn Bhd",
        "posting_date":   add_days(today(), -4),
        "due_date":       add_days(today(), 56),
        "remarks":        "Bill: LC Titan April 2026 HDPE resin — Invoice LCT-2026-04-1234",
        "items": [
            ("RM-HDPE-NAT",  15000, 5.20, "Kg"),
            ("RM-HDPE-R100",  3000, 3.80, "Kg"),
        ],
    },
    {
        "supplier":       "Clariant (Malaysia) Sdn Bhd",
        "posting_date":   add_days(today(), -2),
        "due_date":       add_days(today(), 28),
        "remarks":        "Bill: Clariant Q2 masterbatch — Invoice CLR-Q2-2026-0089",
        "items": [
            ("RM-MB-YEL", 500, 18.00, "Kg"),
            ("RM-MB-WHT", 500, 15.00, "Kg"),
        ],
    },
    {
        "supplier":       "Tenaga Nasional Berhad",
        "posting_date":   add_days(today(), -1),
        "due_date":       add_days(today(), 13),
        "remarks":        "Bill: TNB electricity — Factory account Feb 2026",
        "items": [
            ("SVC-MACHINE-SVC", 1, 4250.00, "Year"),
        ],
    },
]


def _setup_purchase_invoices():
    for pi_data in _PURCHASE_INVOICES:
        supp = pi_data["supplier"]
        if frappe.db.exists("Purchase Invoice", {"supplier": supp, "docstatus": 1}):
            log(f"SKP  [31] Purchase Invoice for '{supp}'")
            continue
        try:
            pi = frappe.get_doc({
                "doctype":        "Purchase Invoice",
                "supplier":       supp,
                "company":        COMPANY,
                "posting_date":   pi_data["posting_date"],
                "due_date":       pi_data["due_date"],
                "currency":       "MYR",
                "remarks":        pi_data["remarks"],
                "items": [
                    {
                        "item_code": code,
                        "qty":       qty,
                        "rate":      rate,
                        "uom":       uom,
                    }
                    for code, qty, rate, uom in pi_data["items"]
                ],
            })
            pi.insert(ignore_permissions=True)
            pi.submit()
            frappe.db.commit()
            log(f"OK   [31] Purchase Invoice {pi.name} | {supp} | MYR {pi.grand_total:,.2f}")
        except Exception as e:
            log(f"ERR  [31] Purchase Invoice for '{supp}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [32] STOCK ENTRIES — Material Transfers
# ─────────────────────────────────────────────────────────────────────────────

_STOCK_ENTRIES = [
    {
        "purpose":   "Material Transfer",
        "remarks":   "Issue HDPE to production — BM-1 batch Apr 2026",
        "items": [
            ("RM-HDPE-NAT",  3000, WAREHOUSE, WAREHOUSE, 5.20),
            ("RM-MB-YEL",      60, WAREHOUSE, WAREHOUSE, 18.00),
            ("RM-CAP-38",   10000, WAREHOUSE, WAREHOUSE,  0.25),
        ],
    },
    {
        "purpose":   "Material Issue",
        "remarks":   "Consumable issue — lubricant and stretch film to maintenance dept",
        "items": [
            ("CON-LUBRICANT", 10, WAREHOUSE, WAREHOUSE, 22.00),
            ("CON-PPFILM",    10, WAREHOUSE, WAREHOUSE, 55.00),
        ],
    },
    {
        "purpose":   "Material Receipt",
        "remarks":   "Return of unused RM-HDPE-R100 from production floor",
        "items": [
            ("RM-HDPE-R100", 200, WAREHOUSE, WAREHOUSE, 3.80),
        ],
    },
]


def _setup_stock_entries():
    for se_data in _STOCK_ENTRIES:
        if frappe.db.exists("Stock Entry", {
            "purpose": se_data["purpose"],
            "remarks": se_data["remarks"],
            "docstatus": 1,
        }):
            log(f"SKP  [32] Stock Entry '{se_data['purpose']}' — {se_data['remarks'][:40]}")
            continue
        try:
            items = []
            for code, qty, s_wh, t_wh, rate in se_data["items"]:
                item_row = {
                    "item_code":         code,
                    "qty":               qty,
                    "basic_rate":        rate,
                }
                if se_data["purpose"] == "Material Transfer":
                    item_row["s_warehouse"] = s_wh
                    item_row["t_warehouse"] = t_wh
                elif se_data["purpose"] == "Material Issue":
                    item_row["s_warehouse"] = s_wh
                else:
                    item_row["t_warehouse"] = t_wh
                items.append(item_row)

            se = frappe.get_doc({
                "doctype":   "Stock Entry",
                "purpose":   se_data["purpose"],
                "company":   COMPANY,
                "posting_date": today(),
                "remarks":   se_data["remarks"],
                "items":     items,
            })
            se.insert(ignore_permissions=True)
            se.submit()
            frappe.db.commit()
            log(f"OK   [32] Stock Entry {se.name} ({se_data['purpose']})")
        except Exception as e:
            log(f"ERR  [32] Stock Entry '{se_data['purpose']}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [33] WORK ORDERS
# ─────────────────────────────────────────────────────────────────────────────

_WORK_ORDERS = [
    {
        "production_item": "AP-JC-020Y",
        "qty":             8000,
        "planned_start":   add_days(today(), -14),
        "planned_end":     add_days(today(), -7),
        "status":          "Completed",
        "remarks":         "WO — 20L Yellow cans for Wilmar SO April 2026",
    },
    {
        "production_item": "AP-JC-025Y",
        "qty":             4000,
        "planned_start":   add_days(today(), -10),
        "planned_end":     add_days(today(), -3),
        "status":          "Completed",
        "remarks":         "WO — 25L Yellow cans for FGV SO April 2026",
    },
    {
        "production_item": "AP-JC-020G",
        "qty":             3000,
        "planned_start":   add_days(today(), -7),
        "planned_end":     add_days(today(), 0),
        "status":          "In Process",
        "remarks":         "WO — 20L Green cans for Mewah RSPO batch",
    },
    {
        "production_item": "AP-JC-010Y",
        "qty":             2000,
        "planned_start":   add_days(today(), -3),
        "planned_end":     add_days(today(), 4),
        "status":          "In Process",
        "remarks":         "WO — 10L Yellow cans for Palmtop Hari Raya uplift",
    },
    {
        "production_item": "AP-JC-020W",
        "qty":             5000,
        "planned_start":   add_days(today(), 2),
        "planned_end":     add_days(today(), 10),
        "status":          "Not Started",
        "remarks":         "WO — 20L White cans for Sime Darby Q2 contract",
    },
]


def _setup_work_orders():
    for wo_data in _WORK_ORDERS:
        item = wo_data["production_item"]
        if frappe.db.exists("Work Order", {"production_item": item, "docstatus": ["!=", 2]}):
            log(f"SKP  [33] Work Order for '{item}'")
            continue

        bom = frappe.db.get_value("BOM", {"item": item, "docstatus": 1, "is_active": 1}, "name")
        if not bom:
            log(f"SKP  [33] Work Order for '{item}' — no active BOM found")
            continue
        try:
            wo = frappe.get_doc({
                "doctype":          "Work Order",
                "production_item":  item,
                "bom_no":           bom,
                "qty":              wo_data["qty"],
                "company":          COMPANY,
                "planned_start_date": wo_data["planned_start"],
                "planned_end_date":   wo_data["planned_end"],
                "wip_warehouse":    WAREHOUSE,
                "fg_warehouse":     WAREHOUSE,
                "remarks":          wo_data["remarks"],
            })
            wo.insert(ignore_permissions=True)
            wo.submit()
            frappe.db.commit()
            log(f"OK   [33] Work Order {wo.name} | {item} × {wo_data['qty']} ({wo_data['status']})")
        except Exception as e:
            log(f"ERR  [33] Work Order for '{item}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [34] PROJECTS & TASKS
# ─────────────────────────────────────────────────────────────────────────────

_PROJECTS = [
    {
        "project_name":  "Machine Upgrade — BM-3 Blow Moulding Line",
        "status":        "Open",
        "expected_start_date": add_days(today(), -30),
        "expected_end_date":   add_days(today(), 60),
        "estimated_costing":   45000.0,
        "department":    f"Production - {ABBR}",
        "notes":         "Upgrade BM-3 machine with new servo drive system for 15% energy saving and +20% output",
        "tasks": [
            {"title": "Vendor shortlisting — servo drive suppliers", "priority": "High",   "exp_start": add_days(today(), -30), "exp_end": add_days(today(), -20), "status": "Completed"},
            {"title": "CAPEX approval from management",              "priority": "High",   "exp_start": add_days(today(), -20), "exp_end": add_days(today(), -15), "status": "Completed"},
            {"title": "Purchase Order — servo drive kit",            "priority": "High",   "exp_start": add_days(today(), -15), "exp_end": add_days(today(), -10), "status": "Completed"},
            {"title": "Machine downtime scheduling",                 "priority": "Medium", "exp_start": add_days(today(), -10), "exp_end": add_days(today(),  -5), "status": "Open"},
            {"title": "Installation and commissioning",              "priority": "High",   "exp_start": add_days(today(),   5), "exp_end": add_days(today(),  15), "status": "Open"},
            {"title": "Trial run and quality sign-off",              "priority": "High",   "exp_start": add_days(today(),  15), "exp_end": add_days(today(),  20), "status": "Open"},
            {"title": "Update preventive maintenance schedule",      "priority": "Low",    "exp_start": add_days(today(),  20), "exp_end": add_days(today(),  25), "status": "Open"},
        ],
    },
    {
        "project_name":  "ISO 9001:2015 Certification Renewal",
        "status":        "Open",
        "expected_start_date": add_days(today(), -45),
        "expected_end_date":   add_days(today(), 45),
        "estimated_costing":   12000.0,
        "department":    f"Quality Control - {ABBR}",
        "notes":         "Annual ISO 9001:2015 surveillance audit by SGS Malaysia. Gap analysis, corrective actions, audit readiness.",
        "tasks": [
            {"title": "Internal gap audit against ISO 9001:2015",   "priority": "High",   "exp_start": add_days(today(), -45), "exp_end": add_days(today(), -30), "status": "Completed"},
            {"title": "Update quality manual and SOPs",             "priority": "High",   "exp_start": add_days(today(), -30), "exp_end": add_days(today(), -15), "status": "Completed"},
            {"title": "Staff awareness training — ISO basics",      "priority": "Medium", "exp_start": add_days(today(), -15), "exp_end": add_days(today(),  -5), "status": "Completed"},
            {"title": "Close out corrective actions from prev audit","priority": "High",   "exp_start": add_days(today(),  -5), "exp_end": add_days(today(),   5), "status": "Open"},
            {"title": "SGS surveillance audit",                     "priority": "High",   "exp_start": add_days(today(),  20), "exp_end": add_days(today(),  21), "status": "Open"},
            {"title": "Review audit findings and close NCs",        "priority": "High",   "exp_start": add_days(today(),  22), "exp_end": add_days(today(),  35), "status": "Open"},
        ],
    },
    {
        "project_name":  "New Product Launch — 1L HDPE Bottle",
        "status":        "Open",
        "expected_start_date": add_days(today(), -20),
        "expected_end_date":   add_days(today(), 90),
        "estimated_costing":   28000.0,
        "department":    f"Sales - {ABBR}",
        "notes":         "Develop and commercialise a new 1L HDPE bottle for cooking oil retail segment. Target: IOI and Carotino.",
        "tasks": [
            {"title": "Market research — retail 1L segment analysis","priority": "High",   "exp_start": add_days(today(), -20), "exp_end": add_days(today(), -10), "status": "Completed"},
            {"title": "Mould design and 3D CAD review",              "priority": "High",   "exp_start": add_days(today(), -10), "exp_end": add_days(today(),   5), "status": "Open"},
            {"title": "Prototype mould fabrication",                 "priority": "High",   "exp_start": add_days(today(),   5), "exp_end": add_days(today(),  30), "status": "Open"},
            {"title": "Trial production run — 500 pcs",              "priority": "High",   "exp_start": add_days(today(),  30), "exp_end": add_days(today(),  35), "status": "Open"},
            {"title": "Customer sample submission (IOI + Carotino)", "priority": "High",   "exp_start": add_days(today(),  35), "exp_end": add_days(today(),  45), "status": "Open"},
            {"title": "Price list and quotation preparation",        "priority": "Medium", "exp_start": add_days(today(),  45), "exp_end": add_days(today(),  50), "status": "Open"},
            {"title": "Commercial launch — first order",             "priority": "High",   "exp_start": add_days(today(),  60), "exp_end": add_days(today(),  70), "status": "Open"},
        ],
    },
]


def _setup_projects():
    for p_data in _PROJECTS:
        pname = p_data["project_name"]
        if frappe.db.exists("Project", pname):
            log(f"SKP  [34] Project '{pname}'")
            continue
        try:
            proj = frappe.get_doc({
                "doctype":               "Project",
                "project_name":          pname,
                "status":                p_data["status"],
                "expected_start_date":   p_data["expected_start_date"],
                "expected_end_date":     p_data["expected_end_date"],
                "estimated_costing":     p_data["estimated_costing"],
                "company":               COMPANY,
                "notes":                 p_data["notes"],
            })
            proj.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [34] Project '{pname}'")

            for t in p_data["tasks"]:
                try:
                    task = frappe.get_doc({
                        "doctype":    "Task",
                        "subject":    t["title"],
                        "project":    proj.name,
                        "priority":   t["priority"],
                        "exp_start_date": t["exp_start"],
                        "exp_end_date":   t["exp_end"],
                        "status":     t["status"],
                    })
                    task.insert(ignore_permissions=True)
                    frappe.db.commit()
                except Exception as te:
                    log(f"ERR  [34] Task '{t['title']}': {te}")
            log(f"OK   [34] Tasks created for '{pname}'")
        except Exception as e:
            log(f"ERR  [34] Project '{pname}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [35] QUALITY INSPECTIONS
# ─────────────────────────────────────────────────────────────────────────────

_QI_TEMPLATE = "Jerry Can — Incoming Inspection"
_QI_PARAMETERS = [
    {"parameter": "Wall Thickness", "acceptance_criteria": "Min 1.5mm at thinnest point"},
    {"parameter": "Cap Torque",     "acceptance_criteria": "12–18 Nm closing torque"},
    {"parameter": "Drop Test",      "acceptance_criteria": "Pass 1.2m drop — no crack/leak"},
    {"parameter": "Visual — Flash", "acceptance_criteria": "No visible flash >1mm"},
    {"parameter": "Colour",         "acceptance_criteria": "Match approved colour chip ±5 CIE ΔE"},
    {"parameter": "Weight",         "acceptance_criteria": "Within ±3% of target weight"},
]

_QUALITY_INSPECTIONS = [
    {
        "reference_type": "Purchase Receipt",
        "item_code":      "RM-HDPE-NAT",
        "sample_size":    5,
        "status":         "Accepted",
        "inspector":      "Siti Nurhaliza binti Kamaruddin",
        "remarks":        "HDPE NAT lot GRN-2026-04 — all parameters within spec",
    },
    {
        "reference_type": "Purchase Receipt",
        "item_code":      "RM-MB-YEL",
        "sample_size":    3,
        "status":         "Accepted",
        "inspector":      "Siti Nurhaliza binti Kamaruddin",
        "remarks":        "Yellow MB lot YEL-Q2-26 — colour delta E = 1.8, PASS",
    },
    {
        "reference_type": "Delivery Note",
        "item_code":      "AP-JC-020Y",
        "sample_size":    10,
        "status":         "Accepted",
        "inspector":      "Siti Nurhaliza binti Kamaruddin",
        "remarks":        "Pre-dispatch QC — 20L Yellow batch DN-APR26-01. All pass.",
    },
    {
        "reference_type": "Purchase Receipt",
        "item_code":      "RM-CAP-38",
        "sample_size":    20,
        "status":         "Rejected",
        "inspector":      "Siti Nurhaliza binti Kamaruddin",
        "remarks":        "Cap lot CAP-38-0226 — 3/20 failed torque test. Return to Goodshine.",
    },
]


def _setup_quality_inspections():
    # Create QC template
    if not frappe.db.exists("Quality Inspection Template", _QI_TEMPLATE):
        try:
            tmpl = frappe.get_doc({
                "doctype":                   "Quality Inspection Template",
                "quality_inspection_template_name": _QI_TEMPLATE,
                "description":               "Standard incoming QC for jerry can components",
                "item_quality_inspection_parameter": [
                    {
                        "specification":         p["parameter"],
                        "acceptance_criteria":   p["acceptance_criteria"],
                    }
                    for p in _QI_PARAMETERS
                ],
            })
            tmpl.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [35] QI Template '{_QI_TEMPLATE}'")
        except Exception as e:
            log(f"ERR  [35] QI Template: {e}")
    else:
        log(f"SKP  [35] QI Template '{_QI_TEMPLATE}'")

    # Create QI records
    for qi_data in _QUALITY_INSPECTIONS:
        item = qi_data["item_code"]
        if frappe.db.exists("Quality Inspection", {"item_code": item, "docstatus": 1}):
            log(f"SKP  [35] Quality Inspection for '{item}'")
            continue
        try:
            emp_id = frappe.db.get_value("Employee", {"employee_name": qi_data["inspector"]}, "name")
            qi = frappe.get_doc({
                "doctype":             "Quality Inspection",
                "inspection_type":     "Incoming",
                "reference_type":      qi_data["reference_type"],
                "item_code":           item,
                "sample_size":         qi_data["sample_size"],
                "inspected_by":        emp_id or "Administrator",
                "status":              qi_data["status"],
                "remarks":             qi_data["remarks"],
                "readings": [
                    {
                        "specification":       p["parameter"],
                        "acceptance_criteria": p["acceptance_criteria"],
                        "status":              qi_data["status"],
                    }
                    for p in _QI_PARAMETERS
                ],
            })
            qi.insert(ignore_permissions=True)
            qi.submit()
            frappe.db.commit()
            log(f"OK   [35] Quality Inspection {qi.name} | {item} | {qi_data['status']}")
        except Exception as e:
            log(f"ERR  [35] Quality Inspection for '{item}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [36] CRM — LEADS & OPPORTUNITIES
# ─────────────────────────────────────────────────────────────────────────────

_LEADS = [
    {
        "lead_name":     "Ng Wei Lun",
        "company_name":  "Greenfield Oils & Fats Sdn Bhd",
        "email_id":      "nwl@greenfield.com.my",
        "mobile_no":     "+60-12-345-9900",
        "lead_owner":    "Administrator",
        "status":        "Open",
        "source":        "Cold Calling",
        "territory":     "Selangor",
        "notes":         "Potential new customer — 20L yellow cans for palm oil. Annual volume est. 50,000 pcs.",
    },
    {
        "lead_name":     "Azlan bin Othman",
        "company_name":  "Kulim Biodiesel Sdn Bhd",
        "email_id":      "azlan@kulimbiodiesel.com.my",
        "mobile_no":     "+60-12-878-1122",
        "lead_owner":    "Administrator",
        "status":        "Open",
        "source":        "Exhibition",
        "territory":     "Kedah",
        "notes":         "Met at Agro-industry expo Alor Setar. Interested in 25L food-grade containers.",
    },
    {
        "lead_name":     "Priya Nair",
        "company_name":  "Harvest Food Industries Sdn Bhd",
        "email_id":      "priya.nair@harvestfood.com.my",
        "mobile_no":     "+60-3-5566-7788",
        "lead_owner":    "Administrator",
        "status":        "Replied",
        "source":        "Email",
        "territory":     "Kuala Lumpur",
        "notes":         "Enquired about custom colour options for retail packaging. Needs 5,000 pcs min order.",
    },
    {
        "lead_name":     "Kamarul Zaman",
        "company_name":  "Johor Palm Commodities",
        "email_id":      "kzaman@jpcomm.com.my",
        "mobile_no":     "+60-7-433-5566",
        "lead_owner":    "Administrator",
        "status":        "Interested",
        "source":        "Referral",
        "territory":     "Johor",
        "notes":         "Referred by Pacoil. Large volume prospect — 100,000 pcs per year across 3 grades.",
    },
    {
        "lead_name":     "Henry Chong",
        "company_name":  "Pacific Edible Oils Pte Ltd",
        "email_id":      "henry@pacedible.sg",
        "mobile_no":     "+65-9123-4567",
        "lead_owner":    "Administrator",
        "status":        "Open",
        "source":        "LinkedIn",
        "territory":     "All Territories",
        "notes":         "Singapore export prospect. Interested in 20L and 25L for bulk palm oil redistribution.",
    },
]

_OPPORTUNITIES = [
    {
        "opportunity_from": "Customer",
        "party_name":       "Carotino Sdn Bhd",
        "opportunity_type": "Sales",
        "status":           "Open",
        "transaction_date": add_days(today(), -10),
        "opportunity_amount": 180000.0,
        "probability":      70,
        "remarks":          "Annual supply contract renewal — 10L + 5L retail bottles. Decision by end of Q2.",
    },
    {
        "opportunity_from": "Customer",
        "party_name":       "Sime Darby Oils Johor Sdn Bhd",
        "opportunity_type": "Sales",
        "status":           "Open",
        "transaction_date": add_days(today(), -5),
        "opportunity_amount": 450000.0,
        "probability":      55,
        "remarks":          "3-year supply agreement covering 3 refineries. Competing with Johore Plastic (local). Need price competitiveness.",
    },
    {
        "opportunity_from": "Lead",
        "party_name":       "Kamarul Zaman",
        "opportunity_type": "Sales",
        "status":           "Quotation",
        "transaction_date": add_days(today(), -2),
        "opportunity_amount": 320000.0,
        "probability":      40,
        "remarks":          "100,000 pcs/year — quotation sent. Awaiting customer counter-proposal.",
    },
]


def _setup_crm():
    for lead_data in _LEADS:
        if frappe.db.exists("Lead", {"lead_name": lead_data["lead_name"]}):
            log(f"SKP  [36] Lead '{lead_data['lead_name']}'")
            continue
        try:
            lead = frappe.get_doc({
                "doctype":      "Lead",
                "lead_name":    lead_data["lead_name"],
                "company_name": lead_data["company_name"],
                "email_id":     lead_data["email_id"],
                "mobile_no":    lead_data["mobile_no"],
                "lead_owner":   lead_data["lead_owner"],
                "status":       lead_data["status"],
                "source":       lead_data["source"],
                "territory":    lead_data["territory"],
                "notes":        lead_data["notes"],
            })
            lead.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [36] Lead '{lead_data['lead_name']}' — {lead_data['company_name']}")
        except Exception as e:
            log(f"ERR  [36] Lead '{lead_data['lead_name']}': {e}")

    for opp_data in _OPPORTUNITIES:
        if frappe.db.exists("Opportunity", {
            "party_name": opp_data["party_name"],
            "status": ["!=", "Lost"],
        }):
            log(f"SKP  [36] Opportunity for '{opp_data['party_name']}'")
            continue
        try:
            opp = frappe.get_doc({
                "doctype":            "Opportunity",
                "opportunity_from":   opp_data["opportunity_from"],
                "party_name":         opp_data["party_name"],
                "opportunity_type":   opp_data["opportunity_type"],
                "status":             opp_data["status"],
                "transaction_date":   opp_data["transaction_date"],
                "opportunity_amount": opp_data["opportunity_amount"],
                "probability":        opp_data["probability"],
                "currency":           "MYR",
                "company":            COMPANY,
                "remarks":            opp_data["remarks"],
            })
            opp.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [36] Opportunity '{opp.name}' | {opp_data['party_name']} | MYR {opp_data['opportunity_amount']:,.0f} ({opp_data['probability']}%)")
        except Exception as e:
            log(f"ERR  [36] Opportunity for '{opp_data['party_name']}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [37] SUPPORT ISSUES
# ─────────────────────────────────────────────────────────────────────────────

_ISSUES = [
    {
        "subject":      "20L yellow cans — cap leaking after 48h storage",
        "customer":     "Wilmar Trading (Malaysia) Sdn Bhd",
        "priority":     "High",
        "status":       "Open",
        "description":  "Wilmar Pasir Gudang depot reported 12 pcs out of 5,000 showing cap seep after 2 days. Batch: DN-APR26-001. Please investigate immediately — product recall risk.",
    },
    {
        "subject":      "Short delivery — missing 500 pcs from delivery note",
        "customer":     "Pacoil Sdn Bhd",
        "priority":     "Medium",
        "status":       "Replied",
        "description":  "Pacoil received 300 pcs 10L yellow but DN shows 400. Also received only 150 pcs 5L yellow vs 200 on DN. Discrepancy: 150 pcs. Pls advise credit note or back order.",
    },
    {
        "subject":      "Colour mismatch — 25L yellow not matching approved sample",
        "customer":     "FGV Palm Industries Sdn Bhd",
        "priority":     "Medium",
        "status":       "Resolved",
        "description":  "FGV Besout plant QC rejected 200 pcs 25L yellow citing colour deviation from approved chip. Measured ΔE = 7.2 (limit: 5.0). Batch: AP-JC-025Y-LOT-026. Replacement batch dispatched.",
    },
    {
        "subject":      "Late delivery — contractual SLA breach warning",
        "customer":     "IOI Palm Oleo (Johor) Sdn Bhd",
        "priority":     "High",
        "status":       "Open",
        "description":  "IOI invoking contract clause 4.2 — 3 days late on April delivery. Customer requesting written explanation and revised schedule. Penalty clause: 0.5% per day.",
    },
]


def _setup_issues():
    for iss_data in _ISSUES:
        if frappe.db.exists("Issue", {"subject": iss_data["subject"]}):
            log(f"SKP  [37] Issue '{iss_data['subject'][:50]}'")
            continue
        try:
            iss = frappe.get_doc({
                "doctype":     "Issue",
                "subject":     iss_data["subject"],
                "customer":    iss_data["customer"],
                "priority":    iss_data["priority"],
                "status":      iss_data["status"],
                "description": iss_data["description"],
                "company":     COMPANY,
                "raised_by":   "Administrator",
            })
            iss.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [37] Issue '{iss_data['subject'][:55]}...' | {iss_data['customer']}")
        except Exception as e:
            log(f"ERR  [37] Issue '{iss_data['subject'][:40]}': {e}")


# ─────────────────────────────────────────────────────────────────────────────
# [38] ASSETS
# ─────────────────────────────────────────────────────────────────────────────

_ASSET_CATEGORIES = [
    # (name, total_number_of_depreciations, frequency_of_depreciation, depreciation_method)
    ("Blow Moulding Machine", 10, 12, "Straight Line"),
    ("Factory Equipment",     5,  12, "Straight Line"),
    ("IT Equipment",          3,  12, "Straight Line"),
    ("Motor Vehicles",        5,  12, "Written Down Value"),
    ("Office Furniture",      5,  12, "Straight Line"),
]

_ASSETS = [
    {
        "asset_name":        "Blow Moulding Machine BM-1",
        "asset_category":    "Blow Moulding Machine",
        "gross_purchase_amount": 280000.0,
        "purchase_date":     "2020-01-15",
        "location":          "Production Floor A",
        "description":       "Kautex KBS-3 blow moulding machine — 10-25L HDPE containers. Serial: KBF-2020-00123",
    },
    {
        "asset_name":        "Blow Moulding Machine BM-2",
        "asset_category":    "Blow Moulding Machine",
        "gross_purchase_amount": 320000.0,
        "purchase_date":     "2021-06-01",
        "location":          "Production Floor A",
        "description":       "Bekum BA-5 blow moulding machine — 10-25L HDPE containers. Serial: BEK-2021-00456",
    },
    {
        "asset_name":        "Blow Moulding Machine BM-3",
        "asset_category":    "Blow Moulding Machine",
        "gross_purchase_amount": 420000.0,
        "purchase_date":     "2023-03-01",
        "location":          "Production Floor B",
        "description":       "Bekum EBLOW-407D — high-speed 4-cavity for 20L. Serial: BEK-2023-00789",
    },
    {
        "asset_name":        "Colour Masterbatch Dosing Unit",
        "asset_category":    "Factory Equipment",
        "gross_purchase_amount": 18000.0,
        "purchase_date":     "2022-08-15",
        "location":          "Production Floor A",
        "description":       "Maguire MSW gravimetric blender for MB dosing. Capacity: 150 kg/hr",
    },
    {
        "asset_name":        "Company Vehicle — Lorry 3T",
        "asset_category":    "Motor Vehicles",
        "gross_purchase_amount": 95000.0,
        "purchase_date":     "2024-01-10",
        "location":          "Loading Bay",
        "description":       "Isuzu NLR 150 3-tonne lorry — JDT 8821. For intra-Johor deliveries.",
    },
]


def _setup_assets():
    for cat, ndep, freq, method in _ASSET_CATEGORIES:
        if frappe.db.exists("Asset Category", cat):
            log(f"SKP  [38] Asset Category '{cat}'")
            continue
        try:
            ac = frappe.get_doc({
                "doctype":               "Asset Category",
                "asset_category_name":   cat,
                "enable_cwip_accounting": 0,
                "accounts": [{
                    "company_name":          COMPANY,
                    "fixed_asset_account":   f"Fixed Assets - {ABBR}",
                    "accumulated_depreciation_account": f"Accumulated Depreciation - {ABBR}",
                    "depreciation_expense_account": f"Depreciation - {ABBR}",
                }],
                "finance_books": [{
                    "total_number_of_depreciations": ndep,
                    "frequency_of_depreciation":     freq,
                    "depreciation_method":           method,
                }],
            })
            ac.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [38] Asset Category '{cat}'")
        except Exception as e:
            log(f"ERR  [38] Asset Category '{cat}': {e}")

    for a_data in _ASSETS:
        if frappe.db.exists("Asset", {"asset_name": a_data["asset_name"]}):
            log(f"SKP  [38] Asset '{a_data['asset_name']}'")
            continue
        try:
            asset = frappe.get_doc({
                "doctype":               "Asset",
                "asset_name":            a_data["asset_name"],
                "asset_category":        a_data["asset_category"],
                "company":               COMPANY,
                "purchase_date":         a_data["purchase_date"],
                "gross_purchase_amount": a_data["gross_purchase_amount"],
                "location":              a_data["location"],
                "description":           a_data["description"],
                "is_existing_asset":     1,
                "available_for_use_date": a_data["purchase_date"],
                "cost_center":           COST_CENTER,
            })
            asset.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [38] Asset '{a_data['asset_name']}' | MYR {a_data['gross_purchase_amount']:,.0f}")
        except Exception as e:
            log(f"ERR  [38] Asset '{a_data['asset_name']}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [39] JOURNAL ENTRIES — Expense Accruals
# ─────────────────────────────────────────────────────────────────────────────

_JOURNAL_ENTRIES = [
    {
        "title":         "Accrual — Factory Rental Feb 2026",
        "posting_date":  "2026-02-28",
        "voucher_type":  "Journal Entry",
        "remarks":       "Monthly factory rental accrual — Jalan Padu Industrial Park, Pasir Gudang",
        "accounts": [
            {"account": f"Rent - {ABBR}",       "debit_in_account_currency": 18000.0, "credit_in_account_currency": 0.0},
            {"account": f"Creditors - {ABBR}",  "debit_in_account_currency": 0.0,     "credit_in_account_currency": 18000.0},
        ],
    },
    {
        "title":         "Accrual — Machine Maintenance Mar 2026",
        "posting_date":  "2026-03-31",
        "voucher_type":  "Journal Entry",
        "remarks":       "Quarterly maintenance service accrual — BM-1 and BM-2",
        "accounts": [
            {"account": f"Repairs and Maintenance - {ABBR}", "debit_in_account_currency": 6500.0, "credit_in_account_currency": 0.0},
            {"account": f"Creditors - {ABBR}",               "debit_in_account_currency": 0.0,    "credit_in_account_currency": 6500.0},
        ],
    },
    {
        "title":         "Write-off — Scrap HDPE (rejected batch)",
        "posting_date":  today(),
        "voucher_type":  "Journal Entry",
        "remarks":       "Write-off: 150 kg HDPE contaminated batch — production defect, no recovery value",
        "accounts": [
            {"account": f"Loss on Asset Write Off - {ABBR}", "debit_in_account_currency": 780.0, "credit_in_account_currency": 0.0},
            {"account": f"Stock In Hand - {ABBR}",           "debit_in_account_currency": 0.0,   "credit_in_account_currency": 780.0},
        ],
    },
]


def _setup_journal_entries():
    for je_data in _JOURNAL_ENTRIES:
        if frappe.db.exists("Journal Entry", {"title": je_data["title"], "docstatus": 1}):
            log(f"SKP  [39] Journal Entry '{je_data['title']}'")
            continue
        try:
            # Validate accounts exist
            accounts_ok = all(
                frappe.db.exists("Account", r["account"])
                for r in je_data["accounts"]
            )
            if not accounts_ok:
                log(f"SKP  [39] JE '{je_data['title']}' — one or more accounts not found")
                continue

            je = frappe.get_doc({
                "doctype":       "Journal Entry",
                "title":         je_data["title"],
                "voucher_type":  je_data["voucher_type"],
                "posting_date":  je_data["posting_date"],
                "company":       COMPANY,
                "user_remark":   je_data["remarks"],
                "accounts": [
                    {
                        "account":                     r["account"],
                        "debit_in_account_currency":   r["debit_in_account_currency"],
                        "credit_in_account_currency":  r["credit_in_account_currency"],
                        "cost_center":                 COST_CENTER,
                    }
                    for r in je_data["accounts"]
                ],
            })
            je.insert(ignore_permissions=True)
            je.submit()
            frappe.db.commit()
            log(f"OK   [39] Journal Entry '{je_data['title']}' — {je_data['posting_date']}")
        except Exception as e:
            log(f"ERR  [39] Journal Entry '{je_data['title']}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run():
    frappe.set_user("Administrator")

    print("=" * 70)
    print("Arising Packaging — Comprehensive Demo Data Seed v1.0")
    print("=" * 70)

    _setup_extra_items()         # [22] Items: spare parts, consumables, services, packaging
    _setup_extra_customers()     # [23] 8 more customers
    _setup_extra_suppliers()     # [24] 5 more suppliers + groups
    _setup_addresses()           # [25] Billing addresses for customers + suppliers
    _setup_quotations()          # [26] 4 quotations
    _setup_delivery_notes()      # [27] 3 delivery notes
    _setup_sales_invoices()      # [28] 4 sales invoices + payment entries for 2
    _setup_material_requests()   # [29] 4 material requests
    _setup_purchase_receipts()   # [30] 3 purchase receipts / GRN
    _setup_purchase_invoices()   # [31] 3 purchase invoices (bills)
    _setup_stock_entries()       # [32] 3 stock entries (transfer, issue, receipt)
    _setup_work_orders()         # [33] 5 work orders
    _setup_projects()            # [34] 3 projects + 20 tasks
    _setup_quality_inspections() # [35] QC template + 4 inspections
    _setup_crm()                 # [36] 5 leads + 3 opportunities
    _setup_issues()              # [37] 4 support issues
    _setup_assets()              # [38] 5 asset categories + 5 assets
    _setup_journal_entries()     # [39] 3 journal entries

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    ok  = [r for r in results if r.startswith("OK")]
    skp = [r for r in results if r.startswith("SKP")]
    err = [r for r in results if r.startswith("ERR")]
    print(f"  Created : {len(ok)}")
    print(f"  Skipped : {len(skp)}")
    print(f"  Errors  : {len(err)}")
    if err:
        print("\nErrors:")
        for e in err:
            print(f"  {e}")
    print("=" * 70)
