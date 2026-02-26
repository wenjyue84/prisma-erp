"""
Arising Packaging Sdn Bhd — Comprehensive Sample Data Seed v2.0
Based on arisingpackaging.com  |  Pasir Gudang, Johor  |  Blow-moulded Multilayer Jerry Cans

Creates (idempotent — safe to re-run):
  [1]  Company                 — real website data, LHDN sandbox credentials
  [2]  Item Groups             — Plastic Containers > Jerry Cans | AP Raw Materials
  [3]  Items                   — 17 finished-good SKUs (2L-25L, 4 colours) + 7 raw-material SKUs
  [4]  Item Prices             — Standard Selling (MYR) for all FG | Standard Buying for RM
  [5]  Warehouse               — Arising Packaging Warehouse, Pasir Gudang
  [6]  Customers               — 10 corporate (Wilmar, IOI, Mewah, FGV, Musim Mas, Mapei,
                                  Palmtop, Pacoil, KongHoo, Lian) + 2 individual
  [7]  Customer Addresses      — one billing address per customer
  [8]  Suppliers               — Lotte Chemical Titan, Clariant, Goodshine Packaging
  [9]  Supplier Addresses      — one address per supplier
  [10] Sales Invoices          — 10 draft SIs covering all corporate and individual customers
  [11] Purchase Invoices       — 3 draft PIs for raw material procurement

All LHDN credentials are SIMULATED for dev/test only.

Deploy & run:
  docker cp setup_sample_data.py \\
    prisma-erp-backend-1:/home/frappe/frappe-bench/apps/frappe/frappe/setup_sample_data.py
  docker exec prisma-erp-backend-1 bash -c \\
    "cd /home/frappe/frappe-bench && bench --site frontend execute frappe.setup_sample_data.run"
"""

import frappe
import traceback
from frappe.utils import today, add_days

COMPANY = "Arising Packaging"
results = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    results.append(msg)
    print(msg)


def abbr():
    return frappe.db.get_value("Company", COMPANY, "abbr") or "AP"


def wh():
    return f"Arising Packaging Warehouse - {abbr()}"


def safe_insert(doctype, key, doc_dict, label):
    """Idempotent insert. key = name string or filter dict. Returns (doc, created)."""
    try:
        exists = frappe.db.exists(doctype, key)
        if exists:
            log(f"SKP  {label}")
            return frappe.get_doc(doctype, exists), False
        doc = frappe.get_doc({"doctype": doctype, **doc_dict})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"OK   {label}")
        return doc, True
    except Exception as e:
        log(f"ERR  {label}: {e}")
        traceback.print_exc()
        return None, False


def make_address(title, addr_type, line1, line2, city, state, pin, country, phone, email, link_doctype, link_name, label):
    addr_name = f"{title}-{addr_type}"
    safe_insert(
        "Address",
        addr_name,
        {
            "address_title": title,
            "address_type": addr_type,
            "address_line1": line1,
            "address_line2": line2,
            "city": city,
            "state": state,
            "pincode": pin,
            "country": country,
            "phone": phone,
            "email_id": email,
            "links": [{"link_doctype": link_doctype, "link_name": link_name}],
        },
        label,
    )


# ── Data Definitions ─────────────────────────────────────────────────────────

FINISHED_GOODS = [
    # (item_code,     item_name,               desc_suffix,                 sell_rate)
    ("AP-JC-002W", "Jerry Can 2L White",  "2 litre, White. General-purpose food-grade container.",                       1.50),
    ("AP-JC-005Y", "Jerry Can 5L Yellow", "5 litre, Yellow. Standard cooking-oil container for retail use.",             2.20),
    ("AP-JC-005W", "Jerry Can 5L White",  "5 litre, White. Food-grade, UV-resistant inner layer.",                       2.20),
    ("AP-JC-010Y", "Jerry Can 10L Yellow","10 litre, Yellow. Edible oil industry standard container.",                   3.80),
    ("AP-JC-010W", "Jerry Can 10L White", "10 litre, White. Food-grade, halal-compliant packaging.",                     3.80),
    ("AP-JC-010B", "Jerry Can 10L Blue",  "10 litre, Blue. Industrial chemicals / lubricants grade.",                    3.80),
    ("AP-JC-010G", "Jerry Can 10L Green", "10 litre, Green. Agricultural / pesticide-safe grade.",                       3.80),
    ("AP-JC-020Y", "Jerry Can 20L Yellow","20 litre, Yellow. Bulk edible oil packaging — primary SKU.",                  6.50),
    ("AP-JC-020W", "Jerry Can 20L White", "20 litre, White. Food-grade, SIRIM-specification export container.",          6.50),
    ("AP-JC-020B", "Jerry Can 20L Blue",  "20 litre, Blue. Industrial grade, chemical-resistant multilayer.",            6.50),
    ("AP-JC-020G", "Jerry Can 20L Green", "20 litre, Green. RSPO palm oil / agricultural produce grade.",                6.50),
    ("AP-JC-025Y", "Jerry Can 25L Yellow","25 litre, Yellow. Heavy-duty bulk edible oil container.",                     7.90),
    ("AP-JC-025W", "Jerry Can 25L White", "25 litre, White. Food-grade export specification.",                           7.90),
    ("AP-JC-025B", "Jerry Can 25L Blue",  "25 litre, Blue. Industrial solvent / chemical storage container.",            7.90),
    ("AP-JC-025G", "Jerry Can 25L Green", "25 litre, Green. Agriculture / crop oil storage.",                            7.90),
]

RAW_MATERIALS = [
    # (item_code,       item_name,                   uom,    buy_rate)
    ("RM-HDPE-NAT",  "HDPE Resin Natural",           "Kg",    5.20),
    ("RM-HDPE-R100", "HDPE Resin Recycled R100",     "Kg",    3.80),
    ("RM-MB-YEL",    "Masterbatch Yellow",            "Kg",   18.00),
    ("RM-MB-WHT",    "Masterbatch White",             "Kg",   15.00),
    ("RM-MB-BLU",    "Masterbatch Blue",              "Kg",   20.00),
    ("RM-MB-GRN",    "Masterbatch Green",             "Kg",   19.00),
    ("RM-CAP-38",    "HDPE Screw Cap 38mm",           "Nos",   0.25),
]

CORPORATE_CUSTOMERS = [
    {
        "name": "Wilmar Trading (Malaysia) Sdn Bhd",
        "tin":  "C20202020202", "reg_type": "BRN", "reg_no": "199401008011",
        "addr1": "PLO 286, Jalan Kempas Lama", "addr2": "Kawasan Perindustrian Tanjung Langsat",
        "city": "Pasir Gudang", "state": "Johor", "pin": "81700",
        "phone": "+60-7-252-1133", "email": "procurement@wilmar.com.my", "due_days": 60,
    },
    {
        "name": "IOI Palm Oleo (Johor) Sdn Bhd",
        "tin":  "C60708090010", "reg_type": "BRN", "reg_no": "197901004783",
        "addr1": "IOI Resort, Lebuh IRC", "addr2": "Putrajaya",
        "city": "Putrajaya", "state": "Wilayah Persekutuan", "pin": "62502",
        "phone": "+60-3-8947-9999", "email": "supply@ioicorp.com", "due_days": 60,
    },
    {
        "name": "Mewah Oils Sdn Bhd",
        "tin":  "C11223344556", "reg_type": "BRN", "reg_no": "199401016327",
        "addr1": "Level 10, Menara Mewah, Jalan Kapar", "addr2": "",
        "city": "Klang", "state": "Selangor", "pin": "42100",
        "phone": "+60-3-3377-8800", "email": "orders@mewah.com", "due_days": 45,
    },
    {
        "name": "FGV Palm Industries Sdn Bhd",
        "tin":  "C55443322110", "reg_type": "BRN", "reg_no": "200601035982",
        "addr1": "Level 7, Menara FGV, Jalan Raja Laut", "addr2": "",
        "city": "Kuala Lumpur", "state": "Wilayah Persekutuan", "pin": "50350",
        "phone": "+60-3-2789-2000", "email": "packaging@fgvholdings.com", "due_days": 60,
    },
    {
        "name": "Musim Mas Palm Oil Refinery (Johor) Sdn Bhd",
        "tin":  "C66778899001", "reg_type": "BRN", "reg_no": "201201032188",
        "addr1": "PLO 1A, Jalan Perjiranan 2", "addr2": "Taman Perindustrian Sri Aman",
        "city": "Pasir Gudang", "state": "Johor", "pin": "81700",
        "phone": "+60-7-252-6000", "email": "operations@musimmas.com.my", "due_days": 30,
    },
    {
        "name": "Mapei (Malaysia) Sdn Bhd",
        "tin":  "C44332211009", "reg_type": "BRN", "reg_no": "201401028765",
        "addr1": "No. 12, Jalan P3/5, Seksyen 13, Bandar Baru Bangi", "addr2": "",
        "city": "Kajang", "state": "Selangor", "pin": "43650",
        "phone": "+60-3-8922-7700", "email": "purchasing@mapei.com.my", "due_days": 30,
    },
    {
        "name": "Palmtop Edible Oils Sdn Bhd",
        "tin":  "C33221100887", "reg_type": "BRN", "reg_no": "200501019443",
        "addr1": "No. 8, Jalan Pengkalan 2, Port Klang Industrial Area", "addr2": "",
        "city": "Klang", "state": "Selangor", "pin": "41100",
        "phone": "+60-3-3168-5500", "email": "supply@palmtop.com.my", "due_days": 45,
    },
    {
        "name": "Pacoil Sdn Bhd",
        "tin":  "C22110099776", "reg_type": "BRN", "reg_no": "200801015889",
        "addr1": "No. 25, Lorong Industri 2", "addr2": "Kawasan Perindustrian Nusa Cemerlang",
        "city": "Iskandar Puteri", "state": "Johor", "pin": "79200",
        "phone": "+60-7-509-3300", "email": "orders@pacoil.com.my", "due_days": 30,
    },
    {
        "name": "KongHoo Oils Trading Sdn Bhd",
        "tin":  "C11009988765", "reg_type": "BRN", "reg_no": "200001005432",
        "addr1": "No. 47, Jalan Seroja 3", "addr2": "Taman Johor Jaya",
        "city": "Johor Bahru", "state": "Johor", "pin": "81100",
        "phone": "+60-7-354-2200", "email": "purchase@konghoo.com.my", "due_days": 30,
    },
    {
        "name": "Lian Industries Sdn Bhd",
        "tin":  "C00998877654", "reg_type": "BRN", "reg_no": "199401002156",
        "addr1": "No. 18, Jalan Industri Ringan 7", "addr2": "Taman Industri Ringan Seri Alam",
        "city": "Masai", "state": "Johor", "pin": "81750",
        "phone": "+60-7-387-6600", "email": "admin@lianindustries.com.my", "due_days": 45,
    },
]

INDIVIDUAL_CUSTOMERS = [
    {
        "name": "Ahmad bin Abdullah",
        "tin":  "IG12345678901", "reg_type": "NRIC", "reg_no": "800101-14-1234",
        "addr1": "No. 12, Jalan Mawar 3", "addr2": "Taman Bunga Raya",
        "city": "Shah Alam", "state": "Selangor", "pin": "40150",
        "phone": "+60-12-345-6789", "email": "ahmad@example.com.my", "due_days": 14,
    },
    {
        "name": "Lim Ah Kow",
        "tin":  "IG75061501678", "reg_type": "NRIC", "reg_no": "750615-01-5678",
        "addr1": "No. 33, Jalan Setia 5", "addr2": "Taman Setia",
        "city": "Johor Bahru", "state": "Johor", "pin": "80350",
        "phone": "+60-16-788-9900", "email": "limahkow@gmail.com", "due_days": 14,
    },
]

SUPPLIERS = [
    {
        "name": "Lotte Chemical Titan (M) Sdn Bhd",
        "tin":  "C10010010001", "reg_type": "BRN", "reg_no": "199101003456",
        "addr1": "PLO 11, Jalan Tanjung Langsat", "addr2": "Kawasan Perindustrian Tanjung Langsat",
        "city": "Pasir Gudang", "state": "Johor", "pin": "81700",
        "phone": "+60-7-251-1000", "email": "sales@lctitan.com",
    },
    {
        "name": "Clariant (Malaysia) Sdn Bhd",
        "tin":  "C20020020002", "reg_type": "BRN", "reg_no": "198501025987",
        "addr1": "No. 3, Persiaran Klang Lama", "addr2": "Taman Perindustrian OUG",
        "city": "Kuala Lumpur", "state": "Wilayah Persekutuan", "pin": "58200",
        "phone": "+60-3-7980-3600", "email": "malaysia@clariant.com",
    },
    {
        "name": "Goodshine Packaging Supplies Sdn Bhd",
        "tin":  "C30030030003", "reg_type": "BRN", "reg_no": "201001025679",
        "addr1": "No. 22, Jalan Perindustrian Utilisasi 1", "addr2": "Taman Perindustrian Utilisasi",
        "city": "Batu Caves", "state": "Selangor", "pin": "68100",
        "phone": "+60-3-6188-3300", "email": "sales@goodshinepackaging.com.my",
    },
]

# (customer_name, tin, reg_type, reg_no, items [(code,qty,rate)], date_offset, due_days, tax_template_title, remarks)
SALES_INVOICES = [
    (
        "Wilmar Trading (Malaysia) Sdn Bhd", "C20202020202", "BRN", "199401008011",
        [("AP-JC-020Y", 5000, 6.50), ("AP-JC-025Y", 3000, 7.90)],
        -30, 60, "SST Sales Tax 10%",
        "Monthly container supply for CPO packaging line — Pasir Gudang refinery.",
    ),
    (
        "IOI Palm Oleo (Johor) Sdn Bhd", "C60708090010", "BRN", "197901004783",
        [("AP-JC-010W", 2000, 3.80), ("AP-JC-020W", 2000, 6.50)],
        -20, 60, "SST Sales Tax 10%",
        "Cooking oil packaging — IOI Bunge Loders Croklaan product line.",
    ),
    (
        "Mewah Oils Sdn Bhd", "C11223344556", "BRN", "199401016327",
        [("AP-JC-020G", 1500, 6.50), ("AP-JC-025G", 500, 7.90)],
        -15, 45, "SST Sales Tax 10%",
        "RSPO-certified palm oil — green container per Mewah sustainability programme.",
    ),
    (
        "FGV Palm Industries Sdn Bhd", "C55443322110", "BRN", "200601035982",
        [("AP-JC-025W", 1000, 7.90), ("AP-JC-010W", 500, 3.80)],
        -10, 60, "SST Sales Tax 10%",
        "Felda Cooking Oil brand packaging — export-grade white containers.",
    ),
    (
        "Musim Mas Palm Oil Refinery (Johor) Sdn Bhd", "C66778899001", "BRN", "201201032188",
        [("AP-JC-020Y", 2500, 6.50)],
        -5, 30, "SST Sales Tax 10%",
        "Emergency top-up order — Pasir Gudang refinery, same-day delivery arranged.",
    ),
    (
        "Mapei (Malaysia) Sdn Bhd", "C44332211009", "BRN", "201401028765",
        [("AP-JC-010B", 300, 3.80), ("AP-JC-025B", 200, 7.90)],
        -25, 30, "SST Sales Tax 10%",
        "Industrial blue jerry cans for tile adhesive and grout product line.",
    ),
    (
        "Palmtop Edible Oils Sdn Bhd", "C33221100887", "BRN", "200501019443",
        [("AP-JC-010Y", 800, 3.80), ("AP-JC-020Y", 400, 6.50)],
        -8, 45, "SST Sales Tax 10%",
        "Palmtop cooking oil brand — seasonal uplift for Hari Raya packaging.",
    ),
    (
        "KongHoo Oils Trading Sdn Bhd", "C11009988765", "BRN", "200001005432",
        [("AP-JC-010W", 600, 3.80), ("AP-JC-005W", 300, 2.20)],
        -12, 30, "SST Sales Tax 10%",
        "Retail oil repackaging for JB wet market distribution.",
    ),
    (
        "Lian Industries Sdn Bhd", "C00998877654", "BRN", "199401002156",
        [("AP-JC-010B", 400, 3.80), ("AP-JC-020B", 100, 6.50)],
        -18, 45, "SST Sales Tax 10%",
        "Workshop lubricant and industrial chemical containment.",
    ),
    (
        "Lim Ah Kow", "IG75061501678", "NRIC", "750615-01-5678",
        [("AP-JC-020W", 5, 6.50)],
        -3, 14, None,
        "Walk-in purchase — small F&B business replenishment.",
    ),
]

# (supplier_name, bill_no, items [(code,qty,rate)], date_offset, due_days, remarks)
PURCHASE_INVOICES = [
    (
        "Lotte Chemical Titan (M) Sdn Bhd",
        "LCT-INV-2026-0312",
        [("RM-HDPE-NAT", 15000, 5.20), ("RM-HDPE-R100", 3000, 3.80)],
        -35, 60,
        "Monthly HDPE resin procurement — April 2026 production batch.",
    ),
    (
        "Clariant (Malaysia) Sdn Bhd",
        "CLR-MY-20260328",
        [("RM-MB-YEL", 250, 18.00), ("RM-MB-WHT", 300, 15.00),
         ("RM-MB-BLU", 150, 20.00), ("RM-MB-GRN", 150, 19.00)],
        -28, 30,
        "Quarterly masterbatch replenishment — all colour SKUs.",
    ),
    (
        "Goodshine Packaging Supplies Sdn Bhd",
        "GSP-20260404-001",
        [("RM-CAP-38", 80000, 0.25)],
        -21, 30,
        "Screw cap inventory replenishment — 80,000 pcs for Q2 production.",
    ),
]


# ── Section Functions ─────────────────────────────────────────────────────────

def _setup_company():
    try:
        c = frappe.get_doc("Company", COMPANY)
        c.phone_no  = "+60-7-251-9550"
        c.email     = "thtan@arisingpackaging.com"
        c.website   = "https://arisingpackaging.com"
        c.tax_id    = "C12345678901"
        # LHDN identity
        c.custom_company_tin_number                       = "C12345678901"
        c.custom_taxpayer_name                            = "Arising Packaging Sdn Bhd"
        c.custom_company_registrationicpassport_type      = "BRN"
        c.custom_company__registrationicpassport_number   = "1575073-V"
        c.custom_sst_number                               = "W10-1234-56789012"
        # LHDN API
        c.custom_enable_lhdn_invoice = 1
        c.custom_integration_type    = "Sandbox"
        c.custom_sandbox_url         = "https://preprod-api.myinvois.hasil.gov.my"
        c.custom_production_url      = "https://api.myinvois.hasil.gov.my"
        c.custom_client_id           = "d2906b87-4b3e-4a9f-8c12-3f5e7a1d0b94"
        c.custom_client_secret       = "sndx-K9mP2qRvL7wXjY4tNhBcZeA3uGfD"
        c.custom_version             = "1.1"
        c.custom_bearer_token        = (
            "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiJDMTIzNDU2Nzg5MDEiLCJuYW1lIjoiQXJpc2luZyBQYWNrYWdpbmcgU2RuIEJoZCIsImlhdCI6MTc0MDUyODAwMCwiZXhwIjo5OTk5OTk5OTk5LCJzY29wZSI6Ikludm9pY2luZ0FQSSJ9"
            ".SIMULATED_SIGNATURE_NOT_VALID_FOR_LHDN"
        )
        c.save(ignore_permissions=True)
        frappe.db.commit()
        log("OK   [1] Company 'Arising Packaging' — updated with real website data (BRN 1575073-V)")
    except Exception as e:
        log(f"ERR  [1] Company update: {e}")
        traceback.print_exc()


def _setup_item_groups():
    # "All Item Groups" must already exist (ERPNext default)
    safe_insert("Item Group", "Plastic Containers",
                {"item_group_name": "Plastic Containers", "parent_item_group": "All Item Groups", "is_group": 1},
                "[2] Item Group 'Plastic Containers'")
    safe_insert("Item Group", "Jerry Cans",
                {"item_group_name": "Jerry Cans", "parent_item_group": "Plastic Containers", "is_group": 0},
                "[2] Item Group 'Jerry Cans'")
    safe_insert("Item Group", "AP Raw Materials",
                {"item_group_name": "AP Raw Materials", "parent_item_group": "All Item Groups", "is_group": 0},
                "[2] Item Group 'AP Raw Materials'")


def _setup_items():
    for code, name, desc_suffix, rate in FINISHED_GOODS:
        safe_insert("Item", code, {
            "item_code":       code,
            "item_name":       name,
            "item_group":      "Jerry Cans",
            "stock_uom":       "Nos",
            "is_stock_item":   1,
            "is_sales_item":   1,
            "is_purchase_item":0,
            "description":     f"Multilayer blow-moulded HDPE jerry can — {desc_suffix}",
            "standard_rate":   rate,
        }, f"[3] Item '{code}' {name}")

    rm_descs = {
        "RM-HDPE-NAT":  "High-density polyethylene pellets, natural grade, MFI 0.3 g/10min. Base resin for jerry can body.",
        "RM-HDPE-R100": "Post-consumer recycled HDPE, food-contact approved. Inner layer of multilayer construction.",
        "RM-MB-YEL":    "HDPE-carrier colour masterbatch, Yellow 3G. Let-down ratio 2%.",
        "RM-MB-WHT":    "HDPE-carrier colour masterbatch, Titanium Dioxide White. Let-down ratio 3%.",
        "RM-MB-BLU":    "HDPE-carrier colour masterbatch, Cobalt Blue 2R. Let-down ratio 2%.",
        "RM-MB-GRN":    "HDPE-carrier colour masterbatch, Forest Green 5G. Let-down ratio 2%.",
        "RM-CAP-38":    "Tamper-evident HDPE screw cap, 38mm neck finish, food-grade. Suits all AP jerry can range.",
    }
    for code, name, uom, rate in RAW_MATERIALS:
        safe_insert("Item", code, {
            "item_code":       code,
            "item_name":       name,
            "item_group":      "AP Raw Materials",
            "stock_uom":       uom,
            "is_stock_item":   1,
            "is_sales_item":   0,
            "is_purchase_item":1,
            "description":     rm_descs.get(code, name),
        }, f"[3] Item '{code}' {name}")


def _setup_item_prices():
    # Selling prices for finished goods
    for code, name, _, rate in FINISHED_GOODS:
        key = {"item_code": code, "price_list": "Standard Selling"}
        if not frappe.db.exists("Item Price", key):
            try:
                ip = frappe.get_doc({
                    "doctype": "Item Price",
                    "item_code": code,
                    "price_list": "Standard Selling",
                    "selling": 1,
                    "currency": "MYR",
                    "price_list_rate": rate,
                    "valid_from": today(),
                })
                ip.insert(ignore_permissions=True)
                frappe.db.commit()
                log(f"OK   [4] Selling price {code} = MYR {rate}")
            except Exception as e:
                log(f"ERR  [4] Selling price {code}: {e}")
        else:
            log(f"SKP  [4] Selling price {code}")

    # Buying prices for raw materials
    for code, name, uom, rate in RAW_MATERIALS:
        key = {"item_code": code, "price_list": "Standard Buying"}
        if not frappe.db.exists("Item Price", key):
            try:
                ip = frappe.get_doc({
                    "doctype": "Item Price",
                    "item_code": code,
                    "price_list": "Standard Buying",
                    "buying": 1,
                    "currency": "MYR",
                    "price_list_rate": rate,
                    "valid_from": today(),
                })
                ip.insert(ignore_permissions=True)
                frappe.db.commit()
                log(f"OK   [4] Buying price  {code} = MYR {rate}/{uom}")
            except Exception as e:
                log(f"ERR  [4] Buying price {code}: {e}")
        else:
            log(f"SKP  [4] Buying price {code}")


def _setup_warehouse(warehouse_name):
    safe_insert(
        "Warehouse",
        warehouse_name,
        {
            "warehouse_name": "Arising Packaging Warehouse",
            "company":        COMPANY,
            "address_line_1": "No 10, Jalan Sagai 2, Taman Pasir Putih",
            "city":           "Pasir Gudang",
            "state":          "Johor",
            "pin":            "81700",
            "country":        "Malaysia",
        },
        f"[5] Warehouse '{warehouse_name}'",
    )


def _setup_customers():
    for c in CORPORATE_CUSTOMERS:
        safe_insert("Customer", c["name"], {
            "customer_name":   c["name"],
            "customer_type":   "Company",
            "customer_group":  "Commercial",
            "territory":       "Malaysia",
            "custom_customer_tin_number":                    c["tin"],
            "custom_customer_taxpayer_name":                 c["name"],
            "custom_customer__registrationicpassport_type":  c["reg_type"],
            "custom_customer_registrationicpassport_number": c["reg_no"],
        }, f"[6] Customer '{c['name']}'")

        make_address(
            c["name"], "Billing",
            c["addr1"], c["addr2"], c["city"], c["state"], c["pin"], "Malaysia",
            c["phone"], c["email"],
            "Customer", c["name"],
            f"[7] Address '{c['name']}-Billing'",
        )

    for c in INDIVIDUAL_CUSTOMERS:
        safe_insert("Customer", c["name"], {
            "customer_name":   c["name"],
            "customer_type":   "Individual",
            "customer_group":  "Individual",
            "territory":       "Malaysia",
            "custom_customer_tin_number":                    c["tin"],
            "custom_customer_taxpayer_name":                 c["name"],
            "custom_customer__registrationicpassport_type":  c["reg_type"],
            "custom_customer_registrationicpassport_number": c["reg_no"],
        }, f"[6] Customer '{c['name']}'")

        make_address(
            c["name"], "Billing",
            c["addr1"], c["addr2"], c["city"], c["state"], c["pin"], "Malaysia",
            c["phone"], c["email"],
            "Customer", c["name"],
            f"[7] Address '{c['name']}-Billing'",
        )


def _setup_suppliers():
    for s in SUPPLIERS:
        safe_insert("Supplier", s["name"], {
            "supplier_name":  s["name"],
            "supplier_type":  "Company",
            "supplier_group": "All Supplier Groups",
            "country":        "Malaysia",
        }, f"[8] Supplier '{s['name']}'")

        make_address(
            s["name"], "Billing",
            s["addr1"], s["addr2"], s["city"], s["state"], s["pin"], "Malaysia",
            s["phone"], s["email"],
            "Supplier", s["name"],
            f"[9] Address '{s['name']}-Billing'",
        )


def _setup_sales_invoices(warehouse_name):
    for (cust, tin, reg_type, reg_no, items, date_offset, due_days, tax_title, remarks) in SALES_INVOICES:
        exists = frappe.db.exists("Sales Invoice",
                                  {"customer": cust, "docstatus": 0, "remarks": remarks})
        if exists:
            log(f"SKP  [10] Draft SI for '{cust}' — already exists ({exists})")
            continue
        try:
            posting = add_days(today(), date_offset)
            due     = add_days(posting, due_days)

            inv_doc = {
                "doctype":         "Sales Invoice",
                "customer":        cust,
                "company":         COMPANY,
                "posting_date":    posting,
                "due_date":        due,
                "currency":        "MYR",
                "conversion_rate": 1.0,
                "remarks":         remarks,
                # LHDN fields
                "custom_malaysia_tax_category":                  "01 : Sales Tax",
                "custom_invoicetype_code":                       "01 :  Invoice",
                "custom_customer_tin_number":                    tin,
                "custom_customer_taxpayer_name":                 cust,
                "custom_customer__registrationicpassport_type":  reg_type,
                "custom_customer_registrationicpassport_number": reg_no,
                "items": [
                    {
                        "item_code": code,
                        "qty":       qty,
                        "rate":      rate,
                        "uom":       "Nos",
                    }
                    for code, qty, rate in items
                ],
            }

            if tax_title:
                tmpl = frappe.db.get_value(
                    "Sales Taxes and Charges Template",
                    {"title": tax_title, "company": COMPANY},
                    "name",
                )
                if tmpl:
                    inv_doc["taxes_and_charges"] = tmpl

            inv = frappe.get_doc(inv_doc)
            if tax_title and inv.taxes_and_charges:
                inv.set_taxes()
            inv.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [10] Draft SI {inv.name} | {cust} | MYR {inv.grand_total:,.2f}")
        except Exception as e:
            log(f"ERR  [10] SI for '{cust}': {e}")
            traceback.print_exc()


def _setup_purchase_invoices(warehouse_name):
    for (supplier, bill_no, items, date_offset, due_days, remarks) in PURCHASE_INVOICES:
        exists = frappe.db.exists("Purchase Invoice", {"bill_no": bill_no, "supplier": supplier})
        if exists:
            log(f"SKP  [11] Draft PI {bill_no} — already exists ({exists})")
            continue
        try:
            posting = add_days(today(), date_offset)
            due     = add_days(posting, due_days)

            pi = frappe.get_doc({
                "doctype":         "Purchase Invoice",
                "supplier":        supplier,
                "company":         COMPANY,
                "posting_date":    posting,
                "bill_no":         bill_no,
                "bill_date":       posting,
                "due_date":        due,
                "currency":        "MYR",
                "conversion_rate": 1.0,
                "remarks":         remarks,
                "items": [
                    {
                        "item_code": code,
                        "qty":       qty,
                        "rate":      rate,
                        "uom":       frappe.db.get_value("Item", code, "stock_uom") or "Nos",
                    }
                    for code, qty, rate in items
                ],
            })
            pi.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK   [11] Draft PI {pi.name} ({bill_no}) | {supplier} | MYR {pi.grand_total:,.2f}")
        except Exception as e:
            log(f"ERR  [11] PI for '{supplier}' ({bill_no}): {e}")
            traceback.print_exc()


# ── Entry Point ───────────────────────────────────────────────────────────────

def run():
    frappe.set_user("Administrator")
    _abbr = abbr()
    warehouse_name = f"Arising Packaging Warehouse - {_abbr}"

    _setup_company()
    _setup_item_groups()
    _setup_items()
    _setup_item_prices()
    _setup_warehouse(warehouse_name)
    _setup_customers()
    _setup_suppliers()
    _setup_sales_invoices(warehouse_name)
    _setup_purchase_invoices(warehouse_name)

    print("\n=== SUMMARY ===")
    for r in results:
        print(r)
