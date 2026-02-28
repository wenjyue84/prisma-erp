"""
Arising Packaging Sdn Bhd — Comprehensive Demo Data Seed v2.0
=============================================================
Fixed version — all field names verified against live ERPNext v16 instance.

Covers:
  [22] Additional Items          — spare parts, consumables, services, packaging
  [23] Additional Customers      — 8 more Malaysian companies
  [24] Additional Suppliers      — 5 more suppliers
  [25] Addresses                 — billing addresses for customers/suppliers
  [26] Quotations                — 4 submitted quotations
  [27] Delivery Notes            — 3 submitted DNs
  [28] Sales Invoices            — 4 submitted SIs + 2 payment entries
  [29] Material Requests         — 4 MRs
  [30] Purchase Receipts         — 3 GRNs
  [31] Purchase Invoices         — 2 submitted bills
  [32] Stock Entries             — material issue, receipt, transfer
  [33] Work Orders               — 5 WOs
  [34] Projects & Tasks          — 3 projects, 20 tasks
  [35] Quality                   — QI Parameters + Template + 4 Inspections
  [36] CRM                       — 5 Leads + 2 Opportunities
  [37] Support Issues            — 4 issues
  [38] Assets                    — asset categories + 5 assets
  [39] Journal Entries           — expense accruals + write-off

Deploy & run:
  docker cp setup_demo_data.py prisma-erp-backend-1:/home/frappe/frappe-bench/apps/frappe/frappe/setup_demo_data.py
  docker exec prisma-erp-backend-1 bash -c "cd /home/frappe/frappe-bench && bench --site frontend execute frappe.setup_demo_data.run"
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
# [22] ADDITIONAL ITEMS
# ─────────────────────────────────────────────────────────────────────────────

_ITEM_GROUPS_EXTRA = ["Spare Parts", "Consumables", "Services", "Packaging"]

_EXTRA_ITEMS = [
    # (item_code, item_name, item_group, uom, is_stock, valuation_rate, standard_rate, description)
    ("SP-MOULD-010",    "10L Bottle Mould (Spare)",         "Spare Parts",  "Nos",  1,  2500.00, 3500.00, "Blow moulding die for 10L jerry can"),
    ("SP-MOULD-020",    "20L Bottle Mould (Spare)",         "Spare Parts",  "Nos",  1,  3500.00, 4800.00, "Blow moulding die for 20L jerry can"),
    ("SP-HYDRAULIC",    "Hydraulic Seal Kit",               "Spare Parts",  "Set",  1,   180.00,  250.00, "Hydraulic press seal kit for blow moulding machine"),
    ("SP-HEATING-BAND", "Heating Band 220V 500W",           "Spare Parts",  "Nos",  1,    45.00,   75.00, "Extruder heating band"),
    ("SP-SCREW-BARREL", "Screw and Barrel Assembly",        "Spare Parts",  "Set",  1, 12000.00, 16000.00,"Extruder screw-barrel set 60mm dia"),
    ("CON-LUBRICANT",   "Industrial Lubricant Grease",      "Consumables",  "Kg",   1,    22.00,   35.00, "High-temp bearing grease"),
    ("CON-SOLVENT",     "Mould Release Spray 500ml",        "Consumables",  "Can",  1,    18.00,   28.00, "Silicone mould release agent"),
    ("CON-PPFILM",      "Stretch Wrap Film 500m",           "Consumables",  "Nos",  1,    55.00,   75.00, "LLDPE pallet stretch film roll"),
    ("CON-LABEL-YEL",   "Yellow Product Label roll/1000",   "Consumables",  "Nos",  1,    12.00,   20.00, "Pre-printed yellow label AP-JC-010Y"),
    ("CON-PALLETBOARD", "Pallet Board 1200x1000mm",         "Consumables",  "Nos",  1,    28.00,   40.00, "Wooden pallet 4-way entry"),
    ("SVC-MACHINE-SVC", "Annual Machine Service Contract",  "Services",     "Nos",  0,     0.00, 8500.00, "Full preventive maintenance by OEM"),
    ("SVC-QC-AUDIT",    "Quality Audit Service",            "Services",     "Nos",  0,     0.00, 1800.00, "Third-party ISO quality audit"),
    ("SVC-FREIGHT-DO",  "Outbound Freight Peninsular",      "Services",     "Nos",  0,     0.00,  450.00, "Lorry delivery Peninsular Malaysia"),
    ("SVC-FREIGHT-EA",  "Outbound Freight East Malaysia",   "Services",     "Nos",  0,     0.00, 1200.00, "Sea freight Sabah/Sarawak"),
    ("PKG-CARTON-10",   "Export Carton for 10L Cans",       "Packaging",    "Nos",  1,     1.80,   2.50, "4-ply RSC carton holds 12 pcs 10L"),
    ("PKG-CARTON-20",   "Export Carton for 20L Cans",       "Packaging",    "Nos",  1,     2.20,   3.20, "5-ply RSC carton holds 4 pcs 20L"),
    ("PKG-SHRINK",      "Shrink Sleeve Label per 1000",     "Packaging",    "Nos",  1,    35.00,  55.00, "PETG shrink sleeve for 25L cans"),
    ("RM-HDPE-HB",      "HDPE HB5502 High-Blow Grade",      "Raw Material", "Kg",   1,     6.10,   0.00, "High-blow HDPE for large containers"),
    ("RM-MB-BLK",       "Black Masterbatch MB-BK100",       "Raw Material", "Kg",   1,    14.00,   0.00, "Carbon black MB 50% loading"),
    ("RM-MB-RED",       "Red Masterbatch MB-RD200",         "Raw Material", "Kg",   1,    22.00,   0.00, "Red oxide MB 40% loading"),
    ("RM-UV-STAB",      "UV Stabiliser Masterbatch",        "Raw Material", "Kg",   1,    55.00,   0.00, "UV-405 hindered amine for outdoor use"),
    ("RM-CAP-45",       "HDPE Screw Cap 45mm",              "Raw Material", "Nos",  1,     0.35,   0.00, "45mm neck cap for 25L cans"),
]


def _setup_extra_items():
    for ig in _ITEM_GROUPS_EXTRA:
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

    for code, name, grp, uom, is_stock, valrate, std_rate, desc in _EXTRA_ITEMS:
        if frappe.db.exists("Item", code):
            log(f"SKP  [22] Item '{code}'")
            continue
        try:
            item = frappe.get_doc({
                "doctype":        "Item",
                "item_code":      code,
                "item_name":      name,
                "item_group":     grp,
                "uom":            uom,
                "stock_uom":      uom,
                "is_stock_item":  is_stock,
                "is_purchase_item": 1,
                "is_sales_item":  1 if grp in ("Services", "Packaging") else 0,
                "valuation_rate": valrate,
                "standard_rate":  std_rate,
                "description":    desc,
            })
            item.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [22] Item '{code}' — {name}")
        except Exception as e:
            log(f"ERR  [22] Item '{code}': {e}")


# ─────────────────────────────────────────────────────────────────────────────
# [23] ADDITIONAL CUSTOMERS
# ─────────────────────────────────────────────────────────────────────────────

_NEW_CUSTOMERS = [
    ("Felda Vegetable Oil Products Sdn Bhd",  "Company",    "Commercial", "Selangor",     "C11122334455", "BRN",  "197701000221", 200000.0),
    ("Carotino Sdn Bhd",                      "Company",    "Commercial", "Johor",        "C22233445566", "BRN",  "198601000332", 150000.0),
    ("Sime Darby Oils Johor Sdn Bhd",         "Company",    "Commercial", "Johor",        "C33344556677", "BRN",  "199001000443", 300000.0),
    ("Bunge Loders Croklaan",                 "Company",    "Commercial", "Selangor",     "C44455667788", "BRN",  "200001000554", 250000.0),
    ("AAK Malaysia Sdn Bhd",                  "Company",    "Commercial", "Selangor",     "C55566778899", "BRN",  "201501000665", 180000.0),
    ("Petronas Chemicals Marketing Sdn Bhd",  "Company",    "Commercial", "Kuala Lumpur", "C66677889900", "BRN",  "199901000776", 500000.0),
    ("Poh Kong Holdings Bhd",                 "Company",    "Commercial", "Selangor",     "C77788990011", "BRN",  "200201000887", 100000.0),
    ("Lim Ah Kow",                            "Individual", "Individual", "Johor",        "IG98765432109","NRIC", "750215-01-5678", 5000.0),
]


def _setup_extra_customers():
    for cname, ctype, cgrp, terr, tin, id_type, id_no, credit in _NEW_CUSTOMERS:
        if frappe.db.exists("Customer", cname):
            log(f"SKP  [23] Customer '{cname}'")
            continue
        try:
            c = frappe.get_doc({
                "doctype":        "Customer",
                "customer_name":  cname,
                "customer_type":  ctype,
                "customer_group": cgrp,
                "territory":      terr,
                "credit_limit":   credit,
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

_SUPPLIER_GROUPS_EXTRA = ["Packaging Material", "Utilities"]

_NEW_SUPPLIERS = [
    ("Toray Plastics (Malaysia) Sdn Bhd",      "Raw Material",      "C12399887766", "BRN", "199801000111"),
    ("ExxonMobil Chemical (Malaysia) Sdn Bhd", "Raw Material",      "C23400998877", "BRN", "198501000222"),
    ("UPM Packaging Sdn Bhd",                  "Packaging Material","C34511009988", "BRN", "200301000333"),
    ("Indah Water Services Sdn Bhd",           "Services",          "C45622110099", "BRN", "199201000444"),
    ("Tenaga Nasional Berhad",                 "Utilities",         "C56733221100", "BRN", "199001000555"),
]


def _setup_extra_suppliers():
    for sg in _SUPPLIER_GROUPS_EXTRA:
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

    for sname, sgrp, tin, id_type, id_no in _NEW_SUPPLIERS:
        if frappe.db.exists("Supplier", sname):
            log(f"SKP  [24] Supplier '{sname}'")
            continue
        try:
            s = frappe.get_doc({
                "doctype":        "Supplier",
                "supplier_name":  sname,
                "supplier_group": sgrp,
                "supplier_type":  "Company",
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
    ("Felda Vegetable Oil Products Sdn Bhd", "Billing", "Lot 1234, Kawasan Perindustrian Kota Kemuning", "", "Shah Alam",     "Selangor",     "40460", "+60-3-5161-2000", "accounts@felvop.com.my",     "Customer", "Felda Vegetable Oil Products Sdn Bhd"),
    ("Carotino Sdn Bhd",                     "Billing", "No 1, Jalan Padu, Kawasan Perindustrian",        "", "Pasir Gudang",  "Johor",        "81700", "+60-7-251-3888",  "billing@carotino.com.my",    "Customer", "Carotino Sdn Bhd"),
    ("Sime Darby Oils Johor Sdn Bhd",        "Billing", "Jalan Perwira, Kawasan Perindustrian",           "", "Pasir Gudang",  "Johor",        "81700", "+60-7-251-2000",  "accounts@sdoils.com.my",     "Customer", "Sime Darby Oils Johor Sdn Bhd"),
    ("Bunge Loders Croklaan",                "Billing", "Lot 6, Jalan Kilang 1/1, SILC Nusajaya",         "", "Johor Bahru",   "Johor",        "79200", "+60-7-509-8888",  "finance@loders.com.my",      "Customer", "Bunge Loders Croklaan"),
    ("AAK Malaysia Sdn Bhd",                 "Billing", "Wisma AAK, Jalan Tandang, Batu 3",               "", "Kuala Lumpur",  "Kuala Lumpur", "58100", "+60-3-7783-2600", "ar@aak.com.my",              "Customer", "AAK Malaysia Sdn Bhd"),
    ("Petronas Chemicals Marketing Sdn Bhd", "Billing", "Level 12, Tower 1, PETRONAS Twin Towers",        "", "Kuala Lumpur",  "Kuala Lumpur", "50088", "+60-3-2051-5000", "chem.billing@petronas.com.my","Customer","Petronas Chemicals Marketing Sdn Bhd"),
    ("Poh Kong Holdings Bhd",                "Billing", "12, Jalan 223, Seksyen 51A",                     "", "Petaling Jaya", "Selangor",     "46100", "+60-3-7958-8000", "billing@pohkong.com.my",     "Customer", "Poh Kong Holdings Bhd"),
    ("Lim Ah Kow",                           "Billing", "No. 45, Jalan Stulang Darat 5",  "Taman Stulang Darat","Johor Bahru","Johor",       "80300", "+60-12-721-5678", "limahkow@gmail.com",         "Customer", "Lim Ah Kow"),
    ("Toray Plastics (Malaysia) Sdn Bhd",    "Billing", "No. 8, Jalan Segambut Tengah",   "Kawasan Perindustrian Segambut", "Kuala Lumpur","Kuala Lumpur","51200","+60-3-6257-9000","accounts@toray.com.my","Supplier","Toray Plastics (Malaysia) Sdn Bhd"),
    ("ExxonMobil Chemical (Malaysia) Sdn Bhd","Billing","Lot 3, Jalan Waja 14, Teluk Panglima Garang","","Kuala Langat","Selangor","42500","+60-3-3122-8000","billing@exxon.com.my","Supplier","ExxonMobil Chemical (Malaysia) Sdn Bhd"),
    ("UPM Packaging Sdn Bhd",               "Billing", "Kawasan Perindustrian Balakong",                  "", "Cheras",        "Selangor",     "43300", "+60-3-9074-3000", "ar@upm-packaging.com.my",    "Supplier", "UPM Packaging Sdn Bhd"),
]


def _setup_addresses():
    for link_name, atype, l1, l2, city, state, pin, phone, email, link_dt, party in _ADDRESSES:
        # check by dynamic link
        existing = frappe.db.get_value("Dynamic Link",
            {"link_doctype": link_dt, "link_name": party, "parenttype": "Address"},
            "parent")
        if existing:
            log(f"SKP  [25] Address for '{party}'")
            continue
        try:
            addr = frappe.get_doc({
                "doctype":       "Address",
                "address_title": party,
                "address_type":  atype,
                "address_line1": l1,
                "address_line2": l2,
                "city":          city,
                "state":         state,
                "pincode":       pin,
                "country":       "Malaysia",
                "phone":         phone,
                "email_id":      email,
                "links": [{"link_doctype": link_dt, "link_name": party}],
            })
            addr.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [25] Address for '{party}'")
        except Exception as e:
            log(f"ERR  [25] Address for '{party}': {e}")


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
        ],
    },
    {
        "party_name":       "Carotino Sdn Bhd",
        "transaction_date": add_days(today(), -15),
        "valid_till":       add_days(today(), 15),
        "remarks":          "Special run — 10L and 5L bottles for retail repack",
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
        "remarks":          "Small batch retail order — 2L and 5L white cans",
        "items": [
            ("AP-JC-002W", 100, 1.60),
            ("AP-JC-005W",  50, 2.15),
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
        "customer":     "Wilmar Trading (Malaysia) Sdn Bhd",
        "posting_date": add_days(today(), -12),
        "remarks":      "Delivery to Wilmar Pasir Gudang depot — partial SO fulfillment",
        "items": [
            ("AP-JC-020Y", 5000, 6.50),
            ("AP-JC-025Y", 2000, 7.90),
        ],
    },
    {
        "customer":     "Mewah Oils Sdn Bhd",
        "posting_date": add_days(today(), -7),
        "remarks":      "Green can delivery — Mewah Bandar Baru Enstek plant",
        "items": [
            ("AP-JC-020G", 1500, 6.50),
        ],
    },
    {
        "customer":     "Pacoil Sdn Bhd",
        "posting_date": add_days(today(), -4),
        "remarks":      "Small format retail delivery — Pacoil JB warehouse",
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
                "doctype":      "Delivery Note",
                "customer":     cust,
                "company":      COMPANY,
                "posting_date": dn_data["posting_date"],
                "currency":     "MYR",
                "remarks":      dn_data["remarks"],
                "items": [
                    {"item_code": code, "qty": qty, "rate": rate, "warehouse": WAREHOUSE}
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
# [28] SALES INVOICES + PAYMENT ENTRIES
# ─────────────────────────────────────────────────────────────────────────────

_SALES_INVOICES = [
    {
        "customer":     "IOI Palm Oleo (Johor) Sdn Bhd",
        "posting_date": add_days(today(), -30),
        "due_date":     add_days(today(), 30),
        "remarks":      "IOI — March 2026 monthly invoice",
        "items": [("AP-JC-020Y", 8000, 6.50), ("AP-JC-020W", 4000, 6.50)],
        "paid": True,
    },
    {
        "customer":     "FGV Palm Industries Sdn Bhd",
        "posting_date": add_days(today(), -25),
        "due_date":     add_days(today(), 35),
        "remarks":      "FGV Felda Besout — 25L yellow can monthly supply",
        "items": [("AP-JC-025Y", 3000, 7.90), ("AP-JC-025W", 1500, 7.90)],
        "paid": True,
    },
    {
        "customer":     "KongHoo Oils Trading Sdn Bhd",
        "posting_date": add_days(today(), -18),
        "due_date":     add_days(today(), 12),
        "remarks":      "KongHoo JB — mixed SKU invoice Feb 2026",
        "items": [("AP-JC-010Y", 1000, 3.80), ("AP-JC-010W", 500, 3.80), ("AP-JC-005Y", 300, 2.20)],
        "paid": False,
    },
    {
        "customer":     "Lian Industries Sdn Bhd",
        "posting_date": add_days(today(), -10),
        "due_date":     add_days(today(), 35),
        "remarks":      "Lian Industries — 20L blue food-grade cans for shortening",
        "items": [("AP-JC-020B", 2000, 6.50)],
        "paid": False,
    },
]


def _setup_sales_invoices():
    bank_account = frappe.db.get_value(
        "Account", {"account_type": "Bank", "company": COMPANY}, "name"
    )
    ar_account = f"Debtors - {ABBR}"

    for si_data in _SALES_INVOICES:
        cust = si_data["customer"]
        if frappe.db.exists("Sales Invoice", {"customer": cust, "docstatus": 1}):
            log(f"SKP  [28] Sales Invoice for '{cust}'")
            continue
        try:
            si = frappe.get_doc({
                "doctype":      "Sales Invoice",
                "customer":     cust,
                "company":      COMPANY,
                "posting_date": si_data["posting_date"],
                "due_date":     si_data["due_date"],
                "currency":     "MYR",
                "remarks":      si_data["remarks"],
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

            if si_data["paid"] and bank_account:
                try:
                    pe = frappe.get_doc({
                        "doctype":          "Payment Entry",
                        "payment_type":     "Receive",
                        "party_type":       "Customer",
                        "party":            cust,
                        "company":          COMPANY,
                        "posting_date":     add_days(si_data["posting_date"], 5),
                        "paid_from":        ar_account,
                        "paid_to":          bank_account,
                        "paid_from_account_currency": "MYR",
                        "paid_to_account_currency":   "MYR",
                        "paid_amount":      si.grand_total,
                        "received_amount":  si.grand_total,
                        "mode_of_payment":  "Bank Transfer",
                        "references": [{
                            "reference_doctype": "Sales Invoice",
                            "reference_name":    si.name,
                            "allocated_amount":  si.grand_total,
                        }],
                    })
                    pe.insert(ignore_permissions=True)
                    pe.submit()
                    frappe.db.commit()
                    log(f"OK   [28] Payment {pe.name} | {cust} | MYR {si.grand_total:,.2f}")
                except Exception as pe_err:
                    log(f"ERR  [28] Payment for '{cust}': {pe_err}")
        except Exception as e:
            log(f"ERR  [28] SI for '{cust}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [29] MATERIAL REQUESTS
# ─────────────────────────────────────────────────────────────────────────────

_MATERIAL_REQUESTS = [
    {
        "mr_type":       "Purchase",
        "schedule_date": add_days(today(), 7),
        "remarks":       "MR-DEMO-01: Masterbatch replenishment blue green black",
        "items": [
            ("RM-MB-BLU", 300, "Kg"),
            ("RM-MB-GRN", 300, "Kg"),
            ("RM-MB-BLK", 200, "Kg"),
        ],
    },
    {
        "mr_type":       "Purchase",
        "schedule_date": add_days(today(), 14),
        "remarks":       "MR-DEMO-02: Screw caps quarterly reorder",
        "items": [
            ("RM-CAP-38", 200000, "Nos"),
            ("RM-CAP-45",  50000, "Nos"),
        ],
    },
    {
        "mr_type":       "Purchase",
        "schedule_date": add_days(today(), 5),
        "remarks":       "MR-DEMO-03: Consumables restock lubricant and pallets",
        "items": [
            ("CON-LUBRICANT",  50, "Kg"),
            ("CON-PPFILM",     30, "Nos"),
            ("CON-PALLETBOARD",100,"Nos"),
        ],
    },
    {
        "mr_type":       "Material Transfer",
        "schedule_date": add_days(today(), 2),
        "remarks":       "MR-DEMO-04: Issue raw materials to production floor",
        "items": [
            ("RM-HDPE-NAT",  5000, "Kg"),
            ("RM-MB-YEL",     100, "Kg"),
            ("RM-CAP-38",   10000, "Nos"),
        ],
    },
]


def _setup_material_requests():
    for mr_data in _MATERIAL_REQUESTS:
        if frappe.db.exists("Material Request", {"remarks": mr_data["remarks"]}):
            log(f"SKP  [29] {mr_data['remarks'][:40]}")
            continue
        try:
            mr = frappe.get_doc({
                "doctype":               "Material Request",
                "material_request_type": mr_data["mr_type"],
                "company":               COMPANY,
                "schedule_date":         mr_data["schedule_date"],
                "remarks":               mr_data["remarks"],
                "items": [
                    {
                        "item_code":     code,
                        "qty":           qty,
                        "uom":           uom,
                        "stock_uom":     uom,
                        "schedule_date": mr_data["schedule_date"],
                        "warehouse":     WAREHOUSE,
                    }
                    for code, qty, uom in mr_data["items"]
                ],
            })
            mr.insert(ignore_permissions=True)
            mr.submit()
            frappe.db.commit()
            log(f"OK   [29] Material Request {mr.name} ({mr_data['mr_type']})")
        except Exception as e:
            log(f"ERR  [29] {mr_data['remarks'][:40]}: {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [30] PURCHASE RECEIPTS
# ─────────────────────────────────────────────────────────────────────────────

_PURCHASE_RECEIPTS = [
    {
        "supplier":     "Lotte Chemical Titan (M) Sdn Bhd",
        "posting_date": add_days(today(), -5),
        "remarks":      "GRN: April HDPE resin delivery partial 15000 kg",
        "items": [("RM-HDPE-NAT", 15000, 5.20, "Kg"), ("RM-HDPE-R100", 3000, 3.80, "Kg")],
    },
    {
        "supplier":     "Clariant (Malaysia) Sdn Bhd",
        "posting_date": add_days(today(), -3),
        "remarks":      "GRN: Quarterly masterbatch delivery complete",
        "items": [("RM-MB-YEL", 500, 18.00, "Kg"), ("RM-MB-WHT", 500, 15.00, "Kg")],
    },
    {
        "supplier":     "Goodshine Packaging Supplies Sdn Bhd",
        "posting_date": add_days(today(), -2),
        "remarks":      "GRN: Screw cap bulk delivery Q2 2026",
        "items": [("RM-CAP-38", 100000, 0.25, "Nos")],
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
                "doctype":      "Purchase Receipt",
                "supplier":     supp,
                "company":      COMPANY,
                "posting_date": pr_data["posting_date"],
                "currency":     "MYR",
                "remarks":      pr_data["remarks"],
                "items": [
                    {
                        "item_code":    code,
                        "qty":          qty,
                        "rate":         rate,
                        "uom":          uom,
                        "stock_uom":    uom,
                        "warehouse":    WAREHOUSE,
                        "accepted_qty": qty,
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
# [31] PURCHASE INVOICES
# ─────────────────────────────────────────────────────────────────────────────

_PURCHASE_INVOICES = [
    {
        "supplier":     "Lotte Chemical Titan (M) Sdn Bhd",
        "posting_date": add_days(today(), -4),
        "due_date":     add_days(today(), 56),
        "remarks":      "Bill: LCT April 2026 HDPE resin Invoice LCT-2026-04-1234",
        "items": [("RM-HDPE-NAT", 15000, 5.20, "Kg"), ("RM-HDPE-R100", 3000, 3.80, "Kg")],
    },
    {
        "supplier":     "Clariant (Malaysia) Sdn Bhd",
        "posting_date": add_days(today(), -2),
        "due_date":     add_days(today(), 28),
        "remarks":      "Bill: Clariant Q2 masterbatch Invoice CLR-Q2-2026-0089",
        "items": [("RM-MB-YEL", 500, 18.00, "Kg"), ("RM-MB-WHT", 500, 15.00, "Kg")],
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
                "doctype":      "Purchase Invoice",
                "supplier":     supp,
                "company":      COMPANY,
                "posting_date": pi_data["posting_date"],
                "due_date":     pi_data["due_date"],
                "currency":     "MYR",
                "remarks":      pi_data["remarks"],
                "items": [
                    {"item_code": code, "qty": qty, "rate": rate, "uom": uom}
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
# [32] STOCK ENTRIES — use stock_entry_type (ERPNext v16)
# ─────────────────────────────────────────────────────────────────────────────

_STOCK_ENTRIES = [
    {
        "stock_entry_type": "Material Issue",
        "remarks":   "SE-DEMO-01: Issue consumables lubricant and stretch film to maintenance",
        "items": [
            {"item_code": "CON-LUBRICANT", "qty": 10, "s_warehouse": WAREHOUSE, "basic_rate": 22.00},
            {"item_code": "CON-PPFILM",    "qty": 10, "s_warehouse": WAREHOUSE, "basic_rate": 55.00},
        ],
    },
    {
        "stock_entry_type": "Material Receipt",
        "remarks":   "SE-DEMO-02: Return of unused RM-HDPE-R100 from production floor",
        "items": [
            {"item_code": "RM-HDPE-R100", "qty": 200, "t_warehouse": WAREHOUSE, "basic_rate": 3.80},
        ],
    },
    {
        "stock_entry_type": "Material Transfer",
        "remarks":   "SE-DEMO-03: Transfer HDPE and caps from main store to production store",
        "items": [
            {"item_code": "RM-HDPE-NAT", "qty": 2000, "s_warehouse": WAREHOUSE, "t_warehouse": WAREHOUSE, "basic_rate": 5.20},
            {"item_code": "RM-CAP-38",   "qty": 5000, "s_warehouse": WAREHOUSE, "t_warehouse": WAREHOUSE, "basic_rate": 0.25},
        ],
    },
]


def _setup_stock_entries():
    for se_data in _STOCK_ENTRIES:
        if frappe.db.exists("Stock Entry", {"remarks": se_data["remarks"], "docstatus": 1}):
            log(f"SKP  [32] Stock Entry '{se_data['remarks'][:50]}'")
            continue
        try:
            se = frappe.get_doc({
                "doctype":          "Stock Entry",
                "stock_entry_type": se_data["stock_entry_type"],
                "company":          COMPANY,
                "posting_date":     today(),
                "remarks":          se_data["remarks"],
                "items":            se_data["items"],
            })
            se.insert(ignore_permissions=True)
            se.submit()
            frappe.db.commit()
            log(f"OK   [32] Stock Entry {se.name} ({se_data['stock_entry_type']})")
        except Exception as e:
            log(f"ERR  [32] Stock Entry '{se_data['stock_entry_type']}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [33] WORK ORDERS
# ─────────────────────────────────────────────────────────────────────────────

_WORK_ORDERS = [
    ("AP-JC-020Y", 8000, add_days(today(), -14), add_days(today(), -7),  "WO: 20L Yellow — Wilmar SO April 2026"),
    ("AP-JC-025Y", 4000, add_days(today(), -10), add_days(today(), -3),  "WO: 25L Yellow — FGV SO April 2026"),
    ("AP-JC-020G", 3000, add_days(today(), -7),  add_days(today(),  0),  "WO: 20L Green — Mewah RSPO batch"),
    ("AP-JC-010Y", 2000, add_days(today(), -3),  add_days(today(),  4),  "WO: 10L Yellow — Palmtop Hari Raya uplift"),
    ("AP-JC-020W", 5000, add_days(today(),  2),  add_days(today(), 10),  "WO: 20L White — Sime Darby Q2 contract"),
]


def _setup_work_orders():
    for item, qty, start, end, remarks in _WORK_ORDERS:
        if frappe.db.exists("Work Order", {"production_item": item, "docstatus": ["!=", 2]}):
            log(f"SKP  [33] Work Order for '{item}'")
            continue
        bom = frappe.db.get_value("BOM", {"item": item, "docstatus": 1, "is_active": 1}, "name")
        if not bom:
            log(f"SKP  [33] Work Order '{item}' — no active BOM")
            continue
        try:
            wo = frappe.get_doc({
                "doctype":            "Work Order",
                "production_item":    item,
                "bom_no":             bom,
                "qty":                qty,
                "company":            COMPANY,
                "planned_start_date": start,
                "planned_end_date":   end,
                "wip_warehouse":      WAREHOUSE,
                "fg_warehouse":       WAREHOUSE,
                "remarks":            remarks,
            })
            wo.insert(ignore_permissions=True)
            wo.submit()
            frappe.db.commit()
            log(f"OK   [33] Work Order {wo.name} | {item} × {qty}")
        except Exception as e:
            log(f"ERR  [33] Work Order '{item}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [34] PROJECTS & TASKS
# ─────────────────────────────────────────────────────────────────────────────

_PROJECTS = [
    {
        "project_name": "Machine Upgrade — BM-3 Blow Moulding Line",
        "status":       "Open",
        "exp_start":    add_days(today(), -30),
        "exp_end":      add_days(today(), 60),
        "cost":         45000.0,
        "notes":        "Upgrade BM-3 with new servo drive for 15% energy saving and +20% output",
        "tasks": [
            ("Vendor shortlisting — servo drive suppliers", "High",   add_days(today(),-30), add_days(today(),-20), "Completed"),
            ("CAPEX approval from management",              "High",   add_days(today(),-20), add_days(today(),-15), "Completed"),
            ("Purchase Order — servo drive kit",            "High",   add_days(today(),-15), add_days(today(),-10), "Completed"),
            ("Machine downtime scheduling",                 "Medium", add_days(today(),-10), add_days(today(), -5), "Open"),
            ("Installation and commissioning",              "High",   add_days(today(),  5), add_days(today(),  15), "Open"),
            ("Trial run and quality sign-off",              "High",   add_days(today(), 15), add_days(today(),  20), "Open"),
            ("Update preventive maintenance schedule",      "Low",    add_days(today(), 20), add_days(today(),  25), "Open"),
        ],
    },
    {
        "project_name": "ISO 9001:2015 Certification Renewal",
        "status":       "Open",
        "exp_start":    add_days(today(), -45),
        "exp_end":      add_days(today(), 45),
        "cost":         12000.0,
        "notes":        "Annual ISO 9001:2015 surveillance audit by SGS Malaysia",
        "tasks": [
            ("Internal gap audit against ISO 9001:2015",    "High",   add_days(today(),-45), add_days(today(),-30), "Completed"),
            ("Update quality manual and SOPs",              "High",   add_days(today(),-30), add_days(today(),-15), "Completed"),
            ("Staff awareness training — ISO basics",       "Medium", add_days(today(),-15), add_days(today(), -5), "Completed"),
            ("Close corrective actions from previous audit","High",   add_days(today(), -5), add_days(today(),  5), "Open"),
            ("SGS surveillance audit",                      "High",   add_days(today(), 20), add_days(today(), 21), "Open"),
            ("Review audit findings and close NCs",         "High",   add_days(today(), 22), add_days(today(), 35), "Open"),
        ],
    },
    {
        "project_name": "New Product Launch — 1L HDPE Bottle",
        "status":       "Open",
        "exp_start":    add_days(today(), -20),
        "exp_end":      add_days(today(), 90),
        "cost":         28000.0,
        "notes":        "Develop 1L HDPE bottle for cooking oil retail. Target: IOI and Carotino.",
        "tasks": [
            ("Market research — retail 1L segment analysis","High",   add_days(today(),-20), add_days(today(),-10), "Completed"),
            ("Mould design and 3D CAD review",              "High",   add_days(today(),-10), add_days(today(),  5), "Open"),
            ("Prototype mould fabrication",                 "High",   add_days(today(),  5), add_days(today(), 30), "Open"),
            ("Trial production run — 500 pcs",              "High",   add_days(today(), 30), add_days(today(), 35), "Open"),
            ("Customer sample submission IOI and Carotino", "High",   add_days(today(), 35), add_days(today(), 45), "Open"),
            ("Price list and quotation preparation",        "Medium", add_days(today(), 45), add_days(today(), 50), "Open"),
            ("Commercial launch — first order",             "High",   add_days(today(), 60), add_days(today(), 70), "Open"),
        ],
    },
]


def _setup_projects():
    for p_data in _PROJECTS:
        pname = p_data["project_name"]
        if frappe.db.exists("Project", {"project_name": pname}):
            log(f"SKP  [34] Project '{pname}'")
            continue
        try:
            proj = frappe.get_doc({
                "doctype":             "Project",
                "project_name":        pname,
                "status":              p_data["status"],
                "expected_start_date": p_data["exp_start"],
                "expected_end_date":   p_data["exp_end"],
                "estimated_costing":   p_data["cost"],
                "company":             COMPANY,
                "notes":               p_data["notes"],
            })
            proj.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [34] Project '{pname}'")

            for title, priority, exp_start, exp_end, status in p_data["tasks"]:
                try:
                    task = frappe.get_doc({
                        "doctype":        "Task",
                        "subject":        title,
                        "project":        proj.name,
                        "priority":       priority,
                        "exp_start_date": exp_start,
                        "exp_end_date":   exp_end,
                        "status":         status,
                    })
                    task.insert(ignore_permissions=True)
                    frappe.db.commit()
                except Exception as te:
                    log(f"ERR  [34] Task '{title}': {te}")

            log(f"OK   [34] {len(p_data['tasks'])} tasks for '{pname}'")
        except Exception as e:
            log(f"ERR  [34] Project '{pname}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [35] QUALITY — Parameters + Template + Inspections
# specification is a Link to "Quality Inspection Parameter" doctype
# ─────────────────────────────────────────────────────────────────────────────

_QI_PARAMS = [
    "JC-Wall Thickness",
    "JC-Cap Torque",
    "JC-Drop Test",
    "JC-Visual Flash",
    "JC-Colour Match",
    "JC-Weight Check",
]

_QI_TEMPLATE_NAME = "Jerry Can Incoming QC"

_QUALITY_INSPECTIONS = [
    {
        "item_code": "RM-HDPE-NAT",
        "sample_size": 5,
        "status": "Accepted",
        "remarks": "HDPE NAT lot GRN-2026-04 all parameters within spec",
    },
    {
        "item_code": "RM-MB-YEL",
        "sample_size": 3,
        "status": "Accepted",
        "remarks": "Yellow MB lot YEL-Q2-26 colour delta E 1.8 PASS",
    },
    {
        "item_code": "AP-JC-020Y",
        "sample_size": 10,
        "status": "Accepted",
        "remarks": "Pre-dispatch QC 20L Yellow batch all pass",
    },
    {
        "item_code": "RM-CAP-38",
        "sample_size": 20,
        "status": "Rejected",
        "remarks": "Cap lot CAP-38-0226 three of twenty failed torque test return to Goodshine",
    },
]


def _setup_quality():
    # Create QI Parameters
    for pname in _QI_PARAMS:
        if not frappe.db.exists("Quality Inspection Parameter", pname):
            try:
                p = frappe.get_doc({
                    "doctype":   "Quality Inspection Parameter",
                    "parameter": pname,
                })
                p.insert(ignore_permissions=True)
                frappe.db.commit()
                log(f"OK   [35] QI Parameter '{pname}'")
            except Exception as e:
                log(f"ERR  [35] QI Parameter '{pname}': {e}")
        else:
            log(f"SKP  [35] QI Parameter '{pname}'")

    # Create QI Template
    if not frappe.db.exists("Quality Inspection Template", _QI_TEMPLATE_NAME):
        try:
            tmpl = frappe.get_doc({
                "doctype": "Quality Inspection Template",
                "quality_inspection_template_name": _QI_TEMPLATE_NAME,
                "item_quality_inspection_parameter": [
                    {"specification": pname, "value": "Per AP-QC-SOP-001"}
                    for pname in _QI_PARAMS
                ],
            })
            tmpl.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [35] QI Template '{_QI_TEMPLATE_NAME}'")
        except Exception as e:
            log(f"ERR  [35] QI Template: {e}")
            traceback.print_exc()
    else:
        log(f"SKP  [35] QI Template '{_QI_TEMPLATE_NAME}'")

    # Get a purchase receipt to link QI to (reference_type + reference_name are mandatory)
    ref_pr = frappe.db.get_value("Purchase Receipt", {"docstatus": 1}, "name") or ""

    # Create QI records (saved as draft — submitting requires reference doc to exist)
    for qi_data in _QUALITY_INSPECTIONS:
        item = qi_data["item_code"]
        if frappe.db.exists("Quality Inspection", {"item_code": item}):
            log(f"SKP  [35] Quality Inspection for '{item}'")
            continue
        # Enable inspection on the item first (required by ERPNext validation)
        try:
            frappe.db.set_value("Item", item, "inspection_required_before_purchase", 1)
        except Exception:
            pass
        try:
            qi = frappe.get_doc({
                "doctype":         "Quality Inspection",
                "inspection_type": "Incoming",
                "reference_type":  "Purchase Receipt",
                "reference_name":  ref_pr,
                "item_code":       item,
                "sample_size":     qi_data["sample_size"],
                "inspected_by":    "Administrator",
                "status":          qi_data["status"],
                "remarks":         qi_data["remarks"],
                "readings": [
                    {
                        "specification":  pname,
                        "status":         qi_data["status"],
                        "reading_value":  "Pass" if qi_data["status"] == "Accepted" else "Fail",
                    }
                    for pname in _QI_PARAMS
                ],
            })
            qi.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [35] Quality Inspection {qi.name} | {item} | {qi_data['status']} (draft)")
        except Exception as e:
            log(f"ERR  [35] Quality Inspection '{item}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [36] CRM — LEADS & OPPORTUNITIES
# Lead.notes is a Table (CRM Note child table) — skip notes field
# Opportunity party_name for Lead type must be the Lead document ID
# ─────────────────────────────────────────────────────────────────────────────

_LEADS = [
    {
        "lead_name":   "Ng Wei Lun",
        "company_name":"Greenfield Oils and Fats Sdn Bhd",
        "email_id":    "nwl@greenfield.com.my",
        "mobile_no":   "+60-12-345-9900",
        "status":      "Open",
        "source":      "Cold Calling",
        "territory":   "Selangor",
        "city":        "Shah Alam",
    },
    {
        "lead_name":   "Azlan bin Othman",
        "company_name":"Kulim Biodiesel Sdn Bhd",
        "email_id":    "azlan@kulimbiodiesel.com.my",
        "mobile_no":   "+60-12-878-1122",
        "status":      "Open",
        "source":      "Exhibition",
        "territory":   "Kedah",
        "city":        "Alor Setar",
    },
    {
        "lead_name":   "Priya Nair",
        "company_name":"Harvest Food Industries Sdn Bhd",
        "email_id":    "priya.nair@harvestfood.com.my",
        "mobile_no":   "+60-3-5566-7788",
        "status":      "Replied",
        "source":      "Email",
        "territory":   "Kuala Lumpur",
        "city":        "Kuala Lumpur",
    },
    {
        "lead_name":   "Kamarul Zaman",
        "company_name":"Johor Palm Commodities",
        "email_id":    "kzaman@jpcomm.com.my",
        "mobile_no":   "+60-7-433-5566",
        "status":      "Interested",
        "source":      "Referral",
        "territory":   "Johor",
        "city":        "Johor Bahru",
    },
    {
        "lead_name":   "Henry Chong",
        "company_name":"Pacific Edible Oils Pte Ltd",
        "email_id":    "henry@pacedible.sg",
        "mobile_no":   "+65-9123-4567",
        "status":      "Open",
        "source":      "LinkedIn",
        "territory":   "All Territories",
        "city":        "Singapore",
    },
]

_OPPORTUNITIES = [
    {
        "party_type":  "Customer",
        "party_name":  "Carotino Sdn Bhd",
        "status":      "Open",
        "amount":      180000.0,
        "probability": 70,
        "remarks":     "Annual supply contract renewal 10L + 5L retail bottles",
    },
    {
        "party_type":  "Customer",
        "party_name":  "Sime Darby Oils Johor Sdn Bhd",
        "status":      "Open",
        "amount":      450000.0,
        "probability": 55,
        "remarks":     "3-year supply agreement covering 3 refineries",
    },
]


def _setup_crm():
    lead_ids = {}
    for lead_data in _LEADS:
        lname = lead_data["lead_name"]
        existing = frappe.db.get_value("Lead", {"lead_name": lname}, "name")
        if existing:
            log(f"SKP  [36] Lead '{lname}'")
            lead_ids[lname] = existing
            continue
        try:
            lead = frappe.get_doc({
                "doctype":      "Lead",
                "lead_name":    lname,
                "company_name": lead_data["company_name"],
                "email_id":     lead_data["email_id"],
                "mobile_no":    lead_data["mobile_no"],
                "status":       lead_data["status"],
                "source":       lead_data["source"],
                "territory":    lead_data["territory"],
                "city":         lead_data["city"],
                "company":      COMPANY,
            })
            lead.insert(ignore_permissions=True)
            frappe.db.commit()
            lead_ids[lname] = lead.name
            log(f"OK   [36] Lead '{lname}' ({lead.name}) — {lead_data['company_name']}")
        except Exception as e:
            log(f"ERR  [36] Lead '{lname}': {e}")

    for opp_data in _OPPORTUNITIES:
        pname = opp_data["party_name"]
        if frappe.db.exists("Opportunity", {"party_name": pname, "status": ["!=", "Lost"]}):
            log(f"SKP  [36] Opportunity for '{pname}'")
            continue
        try:
            opp = frappe.get_doc({
                "doctype":            "Opportunity",
                "opportunity_from":   opp_data["party_type"],
                "party_name":         pname,
                "opportunity_type":   "Sales",
                "status":             opp_data["status"],
                "transaction_date":   add_days(today(), -5),
                "opportunity_amount": opp_data["amount"],
                "probability":        opp_data["probability"],
                "currency":           "MYR",
                "company":            COMPANY,
                "remarks":            opp_data["remarks"],
            })
            opp.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [36] Opportunity {opp.name} | {pname} | MYR {opp_data['amount']:,.0f} ({opp_data['probability']}%)")
        except Exception as e:
            log(f"ERR  [36] Opportunity for '{pname}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [37] SUPPORT ISSUES
# ─────────────────────────────────────────────────────────────────────────────

_ISSUES = [
    ("20L yellow cans — cap leaking after 48h storage",        "Wilmar Trading (Malaysia) Sdn Bhd", "High",   "Open",     "Wilmar Pasir Gudang depot reported 12 pcs out of 5000 showing cap seep after 2 days. Batch DN-APR26-001. Investigate immediately — product recall risk."),
    ("Short delivery — missing 150 pcs from delivery note",    "Pacoil Sdn Bhd",                   "Medium", "Replied",  "Pacoil received 300 pcs 10L yellow but DN shows 400. Also 150 pcs 5L yellow vs 200 on DN. Discrepancy 150 pcs. Advise credit note or back order."),
    ("Colour mismatch — 25L yellow not matching approved chip", "FGV Palm Industries Sdn Bhd",      "Medium", "Resolved", "FGV Besout QC rejected 200 pcs 25L yellow. Measured delta E 7.2 limit is 5.0. Batch AP-JC-025Y-LOT-026. Replacement batch dispatched."),
    ("Late delivery — contractual SLA breach warning",         "IOI Palm Oleo (Johor) Sdn Bhd",   "High",   "Open",     "IOI invoking contract clause 4.2 — 3 days late on April delivery. Customer requesting written explanation and revised schedule. Penalty clause 0.5 percent per day."),
]


def _setup_issues():
    for subject, customer, priority, status, description in _ISSUES:
        if frappe.db.exists("Issue", {"subject": subject}):
            log(f"SKP  [37] Issue '{subject[:50]}'")
            continue
        try:
            iss = frappe.get_doc({
                "doctype":     "Issue",
                "subject":     subject,
                "customer":    customer,
                "priority":    priority,
                "status":      status,
                "description": description,
                "company":     COMPANY,
                "raised_by":   "Administrator",
            })
            iss.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [37] Issue '{subject[:55]}' | {customer}")
        except Exception as e:
            log(f"ERR  [37] Issue '{subject[:40]}': {e}")


# ─────────────────────────────────────────────────────────────────────────────
# [38] ASSETS — ERPNext v16 uses net_purchase_amount (not gross_purchase_amount)
# location and item_code are mandatory; create them first if missing
# ─────────────────────────────────────────────────────────────────────────────

_ASSET_LOCATION = "Arising Packaging Factory"

_ASSET_CATEGORIES = [
    # (name, fixed_asset_account, total_depreciations, freq_months, method, item_code)
    ("Blow Moulding Machine", "Plants and Machineries - AP", 10, 12, "Straight Line",      "ASSET-BM-MACHINE"),
    ("Factory Equipment",     "Capital Equipment - AP",       5, 12, "Straight Line",      "ASSET-FACTORY-EQP"),
    ("IT Equipment",          "Electronic Equipment - AP",    3, 12, "Straight Line",      "ASSET-IT-EQP"),
    ("Motor Vehicles",        "Capital Equipment - AP",       5, 12, "Written Down Value", "ASSET-MOTOR-VEH"),
    ("Office Furniture",      "Furniture and Fixtures - AP",  5, 12, "Straight Line",      "ASSET-OFFICE-FURN"),
]

_ASSETS = [
    # (asset_name, category, item_code, amount, purchase_date, description)
    ("Blow Moulding Machine BM-1",    "Blow Moulding Machine", "ASSET-BM-MACHINE",   280000.0, "2020-01-15", "Kautex KBS-3 blow moulding machine 10-25L HDPE. Serial KBF-2020-00123"),
    ("Blow Moulding Machine BM-2",    "Blow Moulding Machine", "ASSET-BM-MACHINE",   320000.0, "2021-06-01", "Bekum BA-5 blow moulding machine 10-25L HDPE. Serial BEK-2021-00456"),
    ("Blow Moulding Machine BM-3",    "Blow Moulding Machine", "ASSET-BM-MACHINE",   420000.0, "2023-03-01", "Bekum EBLOW-407D high-speed 4-cavity for 20L. Serial BEK-2023-00789"),
    ("Colour Masterbatch Dosing Unit", "Factory Equipment",    "ASSET-FACTORY-EQP",   18000.0, "2022-08-15", "Maguire MSW gravimetric blender 150 kg/hr"),
    ("Company Vehicle Lorry 3T",      "Motor Vehicles",        "ASSET-MOTOR-VEH",    95000.0, "2024-01-10", "Isuzu NLR 150 3-tonne lorry JDT 8821"),
]


def _setup_assets():
    acc_dep = f"Accumulated Depreciation - {ABBR}"
    dep_exp = f"Depreciation - {ABBR}"

    # Create Location (mandatory field on Asset in ERPNext v16)
    if not frappe.db.exists("Location", _ASSET_LOCATION):
        try:
            loc = frappe.get_doc({
                "doctype":       "Location",
                "location_name": _ASSET_LOCATION,
            })
            loc.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [38] Location '{_ASSET_LOCATION}'")
        except Exception as e:
            log(f"ERR  [38] Location: {e}")
    else:
        log(f"SKP  [38] Location '{_ASSET_LOCATION}'")

    # Create Asset Categories FIRST (items require asset_category)
    for cat, fa_account, ndep, freq, method, _item in _ASSET_CATEGORIES:
        if frappe.db.exists("Asset Category", cat):
            log(f"SKP  [38] Asset Category '{cat}'")
            continue
        try:
            ac = frappe.get_doc({
                "doctype":                "Asset Category",
                "asset_category_name":    cat,
                "enable_cwip_accounting": 0,
                "accounts": [{
                    "company_name":                     COMPANY,
                    "fixed_asset_account":              fa_account,
                    "accumulated_depreciation_account": acc_dep,
                    "depreciation_expense_account":     dep_exp,
                }],
                "finance_books": [{
                    "total_number_of_depreciations": ndep,
                    "frequency_of_depreciation":     freq,
                    "depreciation_method":           method,
                }],
            })
            ac.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [38] Asset Category '{cat}' → {fa_account}")
        except Exception as e:
            log(f"ERR  [38] Asset Category '{cat}': {e}")

    # Create fixed-asset Item records AFTER categories (asset_category is mandatory on fixed asset items)
    for cat, _fa, _nd, _fr, _me, item_code in _ASSET_CATEGORIES:
        if frappe.db.exists("Item", item_code):
            continue
        try:
            itm = frappe.get_doc({
                "doctype":         "Item",
                "item_code":       item_code,
                "item_name":       cat,
                "item_group":      "All Item Groups",
                "stock_uom":       "Nos",
                "is_stock_item":   0,
                "is_fixed_asset":  1,
                "asset_category":  cat,
            })
            itm.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [38] Fixed Asset Item '{item_code}'")
        except Exception as e:
            log(f"ERR  [38] Fixed Asset Item '{item_code}': {e}")

    # Create Assets — ERPNext v16: net_purchase_amount (not gross_purchase_amount)
    for aname, acat, item_code, amount, purchase_date, desc in _ASSETS:
        if frappe.db.exists("Asset", {"asset_name": aname}):
            log(f"SKP  [38] Asset '{aname}'")
            continue
        try:
            asset = frappe.get_doc({
                "doctype":                "Asset",
                "asset_name":             aname,
                "item_code":              item_code,
                "asset_category":         acat,
                "company":                COMPANY,
                "location":               _ASSET_LOCATION,
                "purchase_date":          purchase_date,
                "available_for_use_date": purchase_date,
                "net_purchase_amount":    amount,
                "description":            desc,
                "is_existing_asset":      1,
                "cost_center":            COST_CENTER,
            })
            asset.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [38] Asset '{aname}' | MYR {amount:,.0f}")
        except Exception as e:
            log(f"ERR  [38] Asset '{aname}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# [39] JOURNAL ENTRIES — using real COA account names
# ─────────────────────────────────────────────────────────────────────────────

# Creditors - AP is a Payable account requiring party_type+party on every row that uses it.
# Use a first supplier for the party. Stock In Hand cannot be posted via JE — use Write Off instead.
_JE_SUPPLIER = "Lotte Chemical Titan (M) Sdn Bhd"

_JOURNAL_ENTRIES = [
    {
        "title":        "Accrual — Factory Rental Feb 2026",
        "posting_date": "2026-02-28",
        "remarks":      "Monthly factory rental accrual — Jalan Padu Industrial Park Pasir Gudang",
        "accounts": [
            {"account": f"Office Rent - {ABBR}",    "debit": 18000.0, "credit": 0.0},
            {"account": f"Creditors - {ABBR}",      "debit": 0.0,     "credit": 18000.0,
             "party_type": "Supplier", "party": _JE_SUPPLIER},
        ],
    },
    {
        "title":        "Accrual — Machine Maintenance Q2 2026",
        "posting_date": today(),
        "remarks":      "Quarterly maintenance service accrual BM-1 and BM-2",
        "accounts": [
            {"account": f"Office Maintenance Expenses - {ABBR}", "debit": 6500.0, "credit": 0.0},
            {"account": f"Creditors - {ABBR}",                   "debit": 0.0,    "credit": 6500.0,
             "party_type": "Supplier", "party": _JE_SUPPLIER},
        ],
    },
    {
        "title":        "Write-off — Scrap HDPE contaminated batch",
        "posting_date": today(),
        "remarks":      "Write-off 150 kg HDPE contaminated batch production defect no recovery value",
        "accounts": [
            # Stock In Hand cannot be posted via JE; use Write Off on both sides as an expense entry
            {"account": f"Write Off - {ABBR}",              "debit": 780.0, "credit": 0.0},
            {"account": f"Office Maintenance Expenses - {ABBR}", "debit": 0.0, "credit": 780.0},
        ],
    },
    {
        "title":        "Accrual — Marketing Expenses Trade Show Mar 2026",
        "posting_date": today(),
        "remarks":      "Plastivision Malaysia 2026 booth cost accrual",
        "accounts": [
            {"account": f"Marketing Expenses - {ABBR}", "debit": 12000.0, "credit": 0.0},
            {"account": f"Creditors - {ABBR}",          "debit": 0.0,     "credit": 12000.0,
             "party_type": "Supplier", "party": _JE_SUPPLIER},
        ],
    },
    {
        "title":        "Accrual — Travel Expenses Sales Team Feb 2026",
        "posting_date": today(),
        "remarks":      "Sales team customer visits Klang Valley and Penang Feb 2026",
        "accounts": [
            {"account": f"Travel Expenses - {ABBR}", "debit": 3800.0, "credit": 0.0},
            {"account": f"Creditors - {ABBR}",       "debit": 0.0,    "credit": 3800.0,
             "party_type": "Supplier", "party": _JE_SUPPLIER},
        ],
    },
]


def _setup_journal_entries():
    for je_data in _JOURNAL_ENTRIES:
        if frappe.db.exists("Journal Entry", {"title": je_data["title"], "docstatus": 1}):
            log(f"SKP  [39] Journal Entry '{je_data['title']}'")
            continue
        try:
            # Verify all accounts exist
            missing = [r["account"] for r in je_data["accounts"] if not frappe.db.exists("Account", r["account"])]
            if missing:
                log(f"SKP  [39] JE '{je_data['title']}' — missing accounts: {missing}")
                continue

            je = frappe.get_doc({
                "doctype":      "Journal Entry",
                "title":        je_data["title"],
                "voucher_type": "Journal Entry",
                "posting_date": je_data["posting_date"],
                "company":      COMPANY,
                "user_remark":  je_data["remarks"],
                "accounts": [
                    {
                        "account":                    r["account"],
                        "debit_in_account_currency":  r["debit"],
                        "credit_in_account_currency": r["credit"],
                        "cost_center":                COST_CENTER,
                        **({
                            "party_type": r["party_type"],
                            "party":      r["party"],
                        } if r.get("party_type") else {}),
                    }
                    for r in je_data["accounts"]
                ],
            })
            je.insert(ignore_permissions=True)
            je.submit()
            frappe.db.commit()
            log(f"OK   [39] Journal Entry '{je_data['title']}'")
        except Exception as e:
            log(f"ERR  [39] Journal Entry '{je_data['title']}': {e}")
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run():
    frappe.set_user("Administrator")
    print("=" * 70)
    print("Arising Packaging — Comprehensive Demo Data Seed v2.0")
    print("=" * 70)

    _setup_extra_items()         # [22]
    _setup_extra_customers()     # [23]
    _setup_extra_suppliers()     # [24]
    _setup_addresses()           # [25]
    _setup_quotations()          # [26]
    _setup_delivery_notes()      # [27]
    _setup_sales_invoices()      # [28]
    _setup_material_requests()   # [29]
    _setup_purchase_receipts()   # [30]
    _setup_purchase_invoices()   # [31]
    _setup_stock_entries()       # [32]
    _setup_work_orders()         # [33]
    _setup_projects()            # [34]
    _setup_quality()             # [35]
    _setup_crm()                 # [36]
    _setup_issues()              # [37]
    _setup_assets()              # [38]
    _setup_journal_entries()     # [39]

    print("\n" + "=" * 70)
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
