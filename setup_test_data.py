"""
ERPNext / MyInvois Malaysia E-Invoicing — Test Data Setup (Simulated / Dev mode)
Covers: Company LHDN config, SST tax templates, 2 customers, 2 draft invoices.
Run via: bench --site frontend execute frappe.setup_test_data.run

All credentials are SIMULATED for development/testing only.
Do NOT submit invoices to LHDN with these credentials — they will be rejected.
"""
import frappe
import traceback
import requests

results = []

# ── Simulated LHDN Sandbox Credentials (dev/test only) ──────────────────────
# Format mirrors real LHDN sandbox credentials but values are fake.
# Replace with real credentials from https://myinvois.hasil.gov.my when going live.
SIMULATED_CLIENT_ID     = "d2906b87-4b3e-4a9f-8c12-3f5e7a1d0b94"   # UUID format (fake)
SIMULATED_CLIENT_SECRET = "sndx-K9mP2qRvL7wXjY4tNhBcZeA3uGfD"     # 32-char alphanum (fake)
SIMULATED_BEARER_TOKEN  = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJDMTIzNDU2Nzg5MDEiLCJuYW1lIjoiQXJpc2luZyBQYWNrYWdpbmcgU2RuIEJoZCIsImlhdCI6MTc0MDUyODAwMCwiZXhwIjo5OTk5OTk5OTk5LCJzY29wZSI6Ikludm9pY2luZ0FQSSJ9"
    ".SIMULATED_SIGNATURE_NOT_VALID_FOR_LHDN"
)
# ────────────────────────────────────────────────────────────────────────────


def log(msg):
    results.append(msg)
    print(msg)


def run():
    frappe.set_user("Administrator")

    # ── 1. COMPANY — LHDN Malaysia Setup ──────────────────────────────────
    try:
        company = frappe.get_doc("Company", "Arising Packaging")
        company.reload()
        company.phone_no = "+60-3-1234-5678"
        company.email = "info@arisingpackaging.com.my"
        company.tax_id = "C12345678901"
        # Identity
        company.custom_company_tin_number = "C12345678901"
        company.custom_taxpayer_name = "Arising Packaging Sdn Bhd"
        company.custom_company_registrationicpassport_type = "BRN"
        company.custom_company__registrationicpassport_number = "202001030044"
        company.custom_sst_number = "W10-1234-56789012"
        company.custom_tourism_tax_number = ""
        # API connection
        company.custom_enable_lhdn_invoice = 1
        company.custom_integration_type = "Sandbox"
        company.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
        company.custom_production_url = "https://api.myinvois.hasil.gov.my"
        company.custom_client_id = SIMULATED_CLIENT_ID
        company.custom_client_secret = SIMULATED_CLIENT_SECRET
        company.custom_version = "1.1"
        # Simulated bearer token — makes the form look authenticated in UI
        company.custom_bearer_token = SIMULATED_BEARER_TOKEN
        company.custom_send_customer_code_to_lhdn = 0
        company.save(ignore_permissions=True)
        frappe.db.commit()
        log("OK  [1] Company 'Arising Packaging' — LHDN settings + simulated bearer token set")
    except Exception as e:
        log(f"ERR [1] Company update failed: {e}")
        traceback.print_exc()

    # ── 2. CHART OF ACCOUNTS — Malaysian Tax Templates ────────────────────
    # Sales Tax 10% (goods manufactured / imported)
    try:
        if not frappe.db.exists("Sales Taxes and Charges Template", "SST Sales Tax 10% - AP"):
            t = frappe.get_doc({
                "doctype": "Sales Taxes and Charges Template",
                "title": "SST Sales Tax 10%",
                "company": "Arising Packaging",
                "taxes": [{
                    "charge_type": "On Net Total",
                    "account_head": "GST - AP",
                    "description": "Sales Tax (SST) 10% — Manufactured/Imported Goods",
                    "rate": 10,
                }]
            })
            t.insert(ignore_permissions=True)
            frappe.db.commit()
            log("OK  [2a] Tax template 'SST Sales Tax 10% - AP' created")
        else:
            log("SKP [2a] Tax template 'SST Sales Tax 10% - AP' already exists")
    except Exception as e:
        log(f"ERR [2a] Sales Tax template failed: {e}")
        traceback.print_exc()

    # Service Tax 8% (taxable services)
    try:
        if not frappe.db.exists("Sales Taxes and Charges Template", "SST Service Tax 8% - AP"):
            t2 = frappe.get_doc({
                "doctype": "Sales Taxes and Charges Template",
                "title": "SST Service Tax 8%",
                "company": "Arising Packaging",
                "taxes": [{
                    "charge_type": "On Net Total",
                    "account_head": "GST - AP",
                    "description": "Service Tax (SST) 8% — Taxable Services",
                    "rate": 8,
                }]
            })
            t2.insert(ignore_permissions=True)
            frappe.db.commit()
            log("OK  [2b] Tax template 'SST Service Tax 8% - AP' created")
        else:
            log("SKP [2b] Tax template 'SST Service Tax 8% - AP' already exists")
    except Exception as e:
        log(f"ERR [2b] Service Tax template failed: {e}")
        traceback.print_exc()

    # Tax Exempt (0%)
    try:
        if not frappe.db.exists("Sales Taxes and Charges Template", "SST Exempt - AP"):
            t3 = frappe.get_doc({
                "doctype": "Sales Taxes and Charges Template",
                "title": "SST Exempt",
                "company": "Arising Packaging",
                "taxes": [{
                    "charge_type": "On Net Total",
                    "account_head": "GST - AP",
                    "description": "SST Exempt (0%) — Exempt goods/services",
                    "rate": 0,
                }]
            })
            t3.insert(ignore_permissions=True)
            frappe.db.commit()
            log("OK  [2c] Tax template 'SST Exempt - AP' created")
        else:
            log("SKP [2c] Tax template 'SST Exempt - AP' already exists")
    except Exception as e:
        log(f"ERR [2c] Exempt Tax template failed: {e}")
    except Exception as e:
        log(f"ERR Tax template failed: {e}")
        traceback.print_exc()

    # ── 3. CUSTOMERS (Corporate + Individual) ─────────────────────────────
    try:
        if not frappe.db.exists("Customer", "Tech Solutions Sdn Bhd"):
            cust = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": "Tech Solutions Sdn Bhd",
                "customer_type": "Company",
                "customer_group": "Commercial",
                "territory": "Malaysia",
                "custom_customer_tin_number": "C56789012345",
                "custom_customer_taxpayer_name": "Tech Solutions Sdn Bhd",
                "custom_customer__registrationicpassport_type": "BRN",
                "custom_customer_registrationicpassport_number": "202201000001",
            })
            cust.insert(ignore_permissions=True)
            frappe.db.commit()
            log("OK  [3a] Corporate customer 'Tech Solutions Sdn Bhd' created")
        else:
            log("SKP [3a] Corporate customer already exists")
    except Exception as e:
        log(f"ERR [3a] Corporate customer failed: {e}")
        traceback.print_exc()

    try:
        if not frappe.db.exists("Customer", "Ahmad bin Abdullah"):
            cust2 = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": "Ahmad bin Abdullah",
                "customer_type": "Individual",
                "customer_group": "Individual",
                "territory": "Malaysia",
                "custom_customer_tin_number": "IG12345678901",
                "custom_customer_taxpayer_name": "Ahmad bin Abdullah",
                "custom_customer__registrationicpassport_type": "NRIC",
                "custom_customer_registrationicpassport_number": "800101-14-1234",
            })
            cust2.insert(ignore_permissions=True)
            frappe.db.commit()
            log("OK  [3b] Individual customer 'Ahmad bin Abdullah' created")
        else:
            log("SKP [3b] Individual customer already exists")
    except Exception as e:
        log(f"ERR [3b] Individual customer failed: {e}")
        traceback.print_exc()

    # ── 4. CUSTOMER ADDRESSES ─────────────────────────────────────────────
    try:
        if not frappe.db.exists("Address", "Tech Solutions Sdn Bhd-Billing"):
            addr = frappe.get_doc({
                "doctype": "Address",
                "address_title": "Tech Solutions Sdn Bhd",
                "address_type": "Billing",
                "address_line1": "Unit 15-3, Tower B, Menara KL",
                "address_line2": "Jalan Sultan Ismail",
                "city": "Kuala Lumpur",
                "state": "Wilayah Persekutuan",
                "pincode": "50250",
                "country": "Malaysia",
                "phone": "+60-3-2345-6789",
                "email_id": "billing@techsolutions.com.my",
                "links": [{"link_doctype": "Customer", "link_name": "Tech Solutions Sdn Bhd"}]
            })
            addr.insert(ignore_permissions=True)
            frappe.db.commit()
            log("OK  [4a] Address for 'Tech Solutions Sdn Bhd' created")
        else:
            log("SKP [4a] Address (corporate) already exists")
    except Exception as e:
        log(f"ERR [4a] Address (corporate) failed: {e}")

    try:
        if not frappe.db.exists("Address", "Ahmad bin Abdullah-Billing"):
            addr2 = frappe.get_doc({
                "doctype": "Address",
                "address_title": "Ahmad bin Abdullah",
                "address_type": "Billing",
                "address_line1": "No. 12, Jalan Mawar 3",
                "address_line2": "Taman Bunga Raya",
                "city": "Shah Alam",
                "state": "Selangor",
                "pincode": "40150",
                "country": "Malaysia",
                "phone": "+60-12-345-6789",
                "email_id": "ahmad@example.com.my",
                "links": [{"link_doctype": "Customer", "link_name": "Ahmad bin Abdullah"}]
            })
            addr2.insert(ignore_permissions=True)
            frappe.db.commit()
            log("OK  [4b] Address for 'Ahmad bin Abdullah' created")
        else:
            log("SKP [4b] Address (individual) already exists")
    except Exception as e:
        log(f"ERR [4b] Address (individual) failed: {e}")

    # ── 5. DRAFT SALES INVOICE — CORPORATE ───────────────────────────────
    try:
        existing = frappe.db.exists("Sales Invoice", {"customer": "Tech Solutions Sdn Bhd", "docstatus": 0})
        if not existing:
            tax_tmpl_name = frappe.db.get_value(
                "Sales Taxes and Charges Template",
                {"title": "SST Sales Tax 10%", "company": "Arising Packaging"},
                "name"
            )
            inv = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": "Tech Solutions Sdn Bhd",
                "company": "Arising Packaging",
                "posting_date": frappe.utils.today(),
                "due_date": frappe.utils.add_days(frappe.utils.today(), 30),
                "custom_malaysia_tax_category": "01 : Sales Tax",
                "custom_invoicetype_code": "01 :  Invoice",
                "custom_customer_tin_number": "C56789012345",
                "custom_customer_taxpayer_name": "Tech Solutions Sdn Bhd",
                "custom_customer__registrationicpassport_type": "BRN",
                "custom_customer_registrationicpassport_number": "202201000001",
                "items": [
                    {"item_code": "SKU001", "qty": 10, "rate": 500},
                    {"item_code": "SKU002", "qty": 5,  "rate": 200},
                ],
            })
            if tax_tmpl_name:
                inv.taxes_and_charges = tax_tmpl_name
                inv.set_taxes()
            inv.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [5] Draft SI '{inv.name}' | Customer: Tech Solutions Sdn Bhd | Total: MYR {inv.grand_total}")
        else:
            log(f"SKP [5] Draft SI (corporate) already exists: {existing}")
    except Exception as e:
        log(f"ERR [5] Corporate Sales Invoice failed: {e}")
        traceback.print_exc()

    # ── 6. DRAFT SALES INVOICE — INDIVIDUAL ──────────────────────────────
    try:
        existing2 = frappe.db.exists("Sales Invoice", {"customer": "Ahmad bin Abdullah", "docstatus": 0})
        if not existing2:
            inv2 = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": "Ahmad bin Abdullah",
                "company": "Arising Packaging",
                "posting_date": frappe.utils.today(),
                "due_date": frappe.utils.add_days(frappe.utils.today(), 14),
                "custom_malaysia_tax_category": "01 : Sales Tax",
                "custom_invoicetype_code": "01 :  Invoice",
                "custom_customer_tin_number": "IG12345678901",
                "custom_customer_taxpayer_name": "Ahmad bin Abdullah",
                "custom_customer__registrationicpassport_type": "NRIC",
                "custom_customer_registrationicpassport_number": "800101-14-1234",
                "items": [
                    {"item_code": "SKU003", "qty": 2, "rate": 150},
                ],
            })
            inv2.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [6] Draft SI '{inv2.name}' | Customer: Ahmad bin Abdullah | Total: MYR {inv2.grand_total}")
        else:
            log(f"SKP [6] Draft SI (individual) already exists")
    except Exception as e:
        log(f"ERR [6] Individual Sales Invoice failed: {e}")
        traceback.print_exc()

    setup_prisma_branding()
    setup_assets()
    setup_buying()
    setup_selling()
    setup_manufacturing()
    setup_projects()
    setup_quality()
    setup_subcontracting()
    setup_stock()
    setup_modern_icons()

    print("\n=== SUMMARY ===")
    for r in results:
        print(r)

def setup_prisma_branding():
    try:
        # Read local logo
        logo_file_path = "/tmp/prisma_logo.png"
        import os
        if os.path.exists(logo_file_path):
            with open(logo_file_path, "rb") as f:
                content = f.read()
                
            # Check if file already exists
            existing_file = frappe.db.exists("File", {"file_name": "prisma_logo.png"})
            if existing_file:
                logo_path = frappe.db.get_value("File", existing_file, "file_url")
            else:
                file_doc = frappe.get_doc({
                    "doctype": "File",
                    "file_name": "prisma_logo.png",
                    "content": content,
                    "is_private": 0
                })
                file_doc.insert(ignore_permissions=True)
                logo_path = file_doc.file_url

            # Set System Settings
            system_settings = frappe.get_doc("System Settings", "System Settings")
            system_settings.app_name = "Prisma ERP"
            system_settings.save(ignore_permissions=True)

            # Set Website Settings
            website_settings = frappe.get_doc("Website Settings", "Website Settings")
            website_settings.app_name = "Prisma ERP"
            website_settings.app_logo = logo_path
            website_settings.brand_html = f"<img src='{logo_path}' style='height: 40px;'>"
            website_settings.splash_image = logo_path
            website_settings.save(ignore_permissions=True)
            
            # Set Global Defaults
            global_defaults = frappe.get_doc("Global Defaults", "Global Defaults")
            global_defaults.country = "Malaysia"
            global_defaults.default_currency = "MYR"
            global_defaults.save(ignore_permissions=True)
            
            # Set Navbar Settings (if ERPNext v13+)
            if frappe.db.exists("Navbar Settings", "Navbar Settings"):
                navbar_settings = frappe.get_doc("Navbar Settings", "Navbar Settings")
                navbar_settings.app_logo = logo_path
                navbar_settings.save(ignore_permissions=True)
                
            frappe.db.commit()
            log("OK  [7] Prisma Branding & Localization applied (Logo, App Name, MYR, Malaysia)")
        else:
            log(f"ERR [7] Logo file not found at {logo_file_path}")
    except Exception as e:
        log(f"ERR [7] Prisma branding override failed: {e}")
        traceback.print_exc()


def setup_assets():
    """Create sample Asset Category, Item, and Asset"""
    company_name = "Arising Packaging"
    
    # ── 8. ASSET CATEGORY ────────────────────────────────────────────────
    try:
        category_name = "IT Equipment"
        if not frappe.db.exists("Asset Category", category_name):
            # Try to find suitable accounts
            asset_account = frappe.db.get_value("Account", {"account_type": "Fixed Asset", "company": company_name}, "name")
            dep_account = frappe.db.get_value("Account", {"account_type": "Depreciation", "company": company_name}, "name")
            accum_dep_account = frappe.db.get_value("Account", {"account_type": "Accumulated Depreciation", "company": company_name}, "name")
            
            # Fallbacks if specific types aren't found (basic CoA might not have them typed yet)
            if not asset_account:
                asset_account = "Fixed Assets - AP" if frappe.db.exists("Account", "Fixed Assets - AP") else None
            if not dep_account:
                dep_account = "Depreciation - AP" if frappe.db.exists("Account", "Depreciation - AP") else None
            
            # Create category anyway, user might need to fix accounts if mapping fails
            cat = frappe.get_doc({
                "doctype": "Asset Category",
                "asset_category_name": category_name,
                "depreciation_method": "Straight Line",
                "total_number_of_depreciations": 3,
                "frequency_of_depreciation": 12, # Monthly
                "accounts": [{
                    "company_name": company_name,
                    "fixed_asset_account": asset_account,
                    "depreciation_expense_account": dep_account,
                    "accumulated_depreciation_account": accum_dep_account
                }] if asset_account else []
            })
            cat.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [8] Asset Category '{category_name}' created")
        else:
            log(f"SKP [8] Asset Category '{category_name}' already exists")
    except Exception as e:
        log(f"ERR [8] Asset Category failed: {e}")
        traceback.print_exc()

    # ── 9. ASSET ITEM ───────────────────────────────────────────────────
    try:
        item_code = "LAPTOP-001"
        if not frappe.db.exists("Item", item_code):
            item = frappe.get_doc({
                "doctype": "Item",
                "item_code": item_code,
                "item_name": "MacBook Pro 16-inch",
                "item_group": "Products", # Standard group
                "is_stock_item": 0,
                "is_fixed_asset": 1,
                "asset_category": "IT Equipment",
                "stock_uom": "Nos"
            })
            item.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [9] Asset Item '{item_code}' created")
        else:
            log(f"SKP [9] Asset Item '{item_code}' already exists")
    except Exception as e:
        log(f"ERR [9] Asset Item failed: {e}")
        traceback.print_exc()

    # ── 10. ASSET ────────────────────────────────────────────────────────
    try:
        asset_name = "LAPTOP-AP-001"
        if not frappe.db.exists("Asset", asset_name):
            # Ensure location exists
            if not frappe.db.exists("Location", "Kuala Lumpur"):
                loc = frappe.get_doc({
                    "doctype": "Location",
                    "location_name": "Kuala Lumpur"
                })
                loc.insert(ignore_permissions=True)
                frappe.db.commit()
                log("OK  [10a] Location 'Kuala Lumpur' created")
            
            asset = frappe.get_doc({
                "doctype": "Asset",
                "asset_name": asset_name,
                "item_code": "LAPTOP-001",
                "company": company_name,
                "purchase_date": frappe.utils.today(),
                "gross_purchase_amount": 12000,
                "purchase_amount": 12000,
                "net_purchase_amount": 12000,
                "available_for_use_date": frappe.utils.today(),
                "location": "Kuala Lumpur",
                "status": "Draft"
            })
            asset.flags.ignore_mandatory = True # Double insurance for v16
            asset.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [10] Asset '{asset_name}' created (Draft)")
        else:
            log(f"SKP [10] Asset '{asset_name}' already exists")
    except Exception as e:
        log(f"ERR [10] Asset creation failed: {e}")
        traceback.print_exc()


def setup_buying():
    """Create sample Suppliers, Buying Items, and Purchase docs"""
    company_name = "Arising Packaging"
    
    # ── 11. SUPPLIERS ────────────────────────────────────────────────────
    # Local Supplier
    try:
        if not frappe.db.exists("Supplier", "Global Logistics Sdn Bhd"):
            sup = frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": "Global Logistics Sdn Bhd",
                "supplier_type": "Company",
                "supplier_group": "Local",
                "country": "Malaysia",
                "tax_id": "C99887766554"
            })
            sup.insert(ignore_permissions=True)
            frappe.db.commit()
            log("OK  [11a] Local supplier 'Global Logistics Sdn Bhd' created")
        else:
            log("SKP [11a] Local supplier already exists")
    except Exception as e:
        log(f"ERR [11a] Local supplier failed: {e}")

    # Foreign Supplier
    try:
        if not frappe.db.exists("Supplier", "Shenzhen Manufacturing Ltd"):
            sup2 = frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": "Shenzhen Manufacturing Ltd",
                "supplier_type": "Company",
                "supplier_group": "Distributor",
                "country": "China",
                "tax_id": "CH123456"
            })
            sup2.insert(ignore_permissions=True)
            frappe.db.commit()
            log("OK  [11b] Foreign supplier 'Shenzhen Manufacturing Ltd' created")
        else:
            log("SKP [11b] Foreign supplier already exists")
    except Exception as e:
        log(f"ERR [11b] Foreign supplier failed: {e}")

    # ── 12. PURCHASE ITEMS ───────────────────────────────────────────────
    try:
        # Ensure Item Groups exist
        for ig in ["Raw Materials", "Services"]:
            if not frappe.db.exists("Item Group", ig):
                frappe.get_doc({
                    "doctype": "Item Group",
                    "item_group_name": ig,
                    "parent_item_group": "All Item Groups",
                    "is_group": 0
                }).insert(ignore_permissions=True)
                frappe.db.commit()
                log(f"OK  [12a] Item Group '{ig}' created")

        items = [
            {"item_code": "RAW-MTL-001", "item_name": "Raw Paper Pulp", "item_group": "Raw Materials", "stock_uom": "Kg", "is_purchase_item": 1, "is_stock_item": 1},
            {"item_code": "SRV-TRN-001", "item_name": "Freight & Transport", "item_group": "Services", "stock_uom": "Nos", "is_purchase_item": 1, "is_stock_item": 0}
        ]
        for item_data in items:
            if not frappe.db.exists("Item", item_data["item_code"]):
                item = frappe.get_doc({"doctype": "Item", **item_data})
                item.insert(ignore_permissions=True)
                frappe.db.commit()
                log(f"OK  [12] Purchase Item '{item_data['item_code']}' created")
            else:
                log(f"SKP [12] Purchase Item '{item_data['item_code']}' already exists")
    except Exception as e:
        log(f"ERR [12] Purchase Items failed: {e}")

    # ── 13. PURCHASE ORDER ───────────────────────────────────────────────
    try:
        if not frappe.db.exists("Purchase Order", {"supplier": "Shenzhen Manufacturing Ltd", "docstatus": 0}):
            po = frappe.get_doc({
                "doctype": "Purchase Order",
                "supplier": "Shenzhen Manufacturing Ltd",
                "company": company_name,
                "transaction_date": frappe.utils.today(),
                "schedule_date": frappe.utils.add_days(frappe.utils.today(), 14),
                "items": [
                    {
                        "item_code": "RAW-MTL-001", 
                        "qty": 1000, 
                        "rate": 5.5, 
                        "schedule_date": frappe.utils.add_days(frappe.utils.today(), 14),
                        "warehouse": "Stores - AP" if frappe.db.exists("Warehouse", "Stores - AP") else None
                    }
                ]
            })
            po.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [13] Draft PO '{po.name}' created")
        else:
            log("SKP [13] Draft PO (Shenzhen) already exists")
    except Exception as e:
        log(f"ERR [13] Purchase Order failed: {e}")

    # ── 14. PURCHASE INVOICE ─────────────────────────────────────────────
    try:
        if not frappe.db.exists("Purchase Invoice", {"supplier": "Global Logistics Sdn Bhd", "docstatus": 0}):
            # Find an expense account
            expense_account = frappe.db.get_value("Account", {"account_name": "Direct Expenses", "company": company_name}, "name")
            if not expense_account:
                expense_account = "Direct Expenses - AP" if frappe.db.exists("Account", "Direct Expenses - AP") else None

            pi = frappe.get_doc({
                "doctype": "Purchase Invoice",
                "supplier": "Global Logistics Sdn Bhd",
                "company": company_name,
                "posting_date": frappe.utils.today(),
                "due_date": frappe.utils.add_days(frappe.utils.today(), 30),
                "items": [
                    {
                        "item_code": "SRV-TRN-001", 
                        "qty": 1, 
                        "rate": 1200, 
                        "expense_account": expense_account
                    }
                ]
            })
            
            # Simple tax logic
            tax_tmpl = frappe.db.get_value("Purchase Taxes and Charges Template", {"company": company_name}, "name")
            if tax_tmpl:
                pi.taxes_and_charges = tax_tmpl
                pi.set_taxes()

            pi.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [14] Draft PI '{pi.name}' created")
        else:
            log("SKP [14] Draft PI (Global Logistics) already exists")
    except Exception as e:
        log(f"ERR [14] Purchase Invoice failed: {e}")

def setup_selling():
    """Create sample Selling Items, Quotations, Sales Orders, and Delivery Notes"""
    company_name = "Arising Packaging"
    
    # -- 16. SELLING ITEMS --
    try:
        # Ensure UOMs exist
        for uom in ["Roll", "Nos", "Pkt"]:
            if not frappe.db.exists("UOM", uom):
                frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)
                log(f"OK  [16] UOM '{uom}' created")

        items = [
            {"item_code": "SKU001", "item_name": "Premium Corrugated Box", "item_group": "Products", "stock_uom": "Nos", "is_sales_item": 1, "is_stock_item": 1, "standard_rate": 500},
            {"item_code": "SKU002", "item_name": "Eco-friendly Bubble Wrap", "item_group": "Products", "stock_uom": "Roll", "is_sales_item": 1, "is_stock_item": 1, "standard_rate": 200},
            {"item_code": "SKU003", "item_name": "Packaging Design Service", "item_group": "Services", "stock_uom": "Nos", "is_sales_item": 1, "is_stock_item": 0, "standard_rate": 150},
            {"item_code": "SKU004", "item_name": "Custom Product Label", "item_group": "Products", "stock_uom": "Pkt", "is_sales_item": 1, "is_stock_item": 1, "standard_rate": 50}
        ]
        for item_data in items:
            if not frappe.db.exists("Item", item_data["item_code"]):
                item = frappe.get_doc({"doctype": "Item", **item_data})
                item.insert(ignore_permissions=True)
                frappe.db.commit()
                log(f"OK  [16] Selling Item '{item_data['item_code']}' created")
            else:
                log(f"SKP [16] Selling Item '{item_data['item_code']}' already exists")
    except Exception as e:
        log(f"ERR [16] Selling Items failed: {e}")

    # -- 17. ADDITIONAL CUSTOMER --
    try:
        if not frappe.db.exists("Customer", "Maju Jaya Trading"):
            cust = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": "Maju Jaya Trading",
                "customer_type": "Company",
                "customer_group": "Commercial",
                "territory": "Malaysia",
                "custom_customer_tin_number": "C88776655443",
                "custom_customer_taxpayer_name": "Maju Jaya Trading Sdn Bhd",
                "custom_customer__registrationicpassport_type": "BRN",
                "custom_customer_registrationicpassport_number": "202101000999",
            })
            cust.insert(ignore_permissions=True)
            frappe.db.commit()
            log("OK  [Selling] Customer 'Maju Jaya Trading' created")
    except Exception as e:
        log(f"ERR [Selling] Customer Maju Jaya failed: {e}")

    # -- 18. QUOTATIONS --
    try:
        if not frappe.db.exists("Quotation", {"party_name": "Tech Solutions Sdn Bhd", "docstatus": 0}):
            q = frappe.get_doc({
                "doctype": "Quotation",
                "quotation_to": "Customer",
                "party_name": "Tech Solutions Sdn Bhd",
                "company": company_name,
                "transaction_date": frappe.utils.today(),
                "valid_until": frappe.utils.add_days(frappe.utils.today(), 7),
                "items": [
                    {"item_code": "SKU001", "qty": 100, "rate": 450}
                ]
            })
            q.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [18] Draft Quotation '{q.name}' created")
        
        if not frappe.db.exists("Quotation", {"party_name": "Maju Jaya Trading", "docstatus": 0}):
            q2 = frappe.get_doc({
                "doctype": "Quotation",
                "quotation_to": "Customer",
                "party_name": "Maju Jaya Trading",
                "company": company_name,
                "transaction_date": frappe.utils.today(),
                "items": [
                    {"item_code": "SKU004", "qty": 500, "rate": 45}
                ]
            })
            q2.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [18] Draft Quotation '{q2.name}' (Maju Jaya) created")
    except Exception as e:
        log(f"ERR [18] Quotation failed: {e}")

    # -- 19. SALES ORDER --
    try:
        if not frappe.db.exists("Sales Order", {"customer": "Ahmad bin Abdullah", "docstatus": 0}):
            so = frappe.get_doc({
                "doctype": "Sales Order",
                "customer": "Ahmad bin Abdullah",
                "company": company_name,
                "transaction_date": frappe.utils.today(),
                "delivery_date": frappe.utils.add_days(frappe.utils.today(), 3),
                "items": [
                    {"item_code": "SKU002", "qty": 10, "rate": 190}
                ]
            })
            so.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [19] Draft Sales Order '{so.name}' created")
        else:
            log("SKP [19] Draft Sales Order already exists")
    except Exception as e:
        log(f"ERR [19] Sales Order failed: {e}")

    # -- 20. DELIVERY NOTE --
    try:
        # Create a delivery note for Ahmad’s SO if one exists
        so_name = frappe.db.get_value("Sales Order", {"customer": "Ahmad bin Abdullah", "docstatus": 0}, "name")
        if so_name and not frappe.db.exists("Delivery Note", {"customer": "Ahmad bin Abdullah", "docstatus": 0}):
            dn = frappe.get_doc({
                "doctype": "Delivery Note",
                "customer": "Ahmad bin Abdullah",
                "company": company_name,
                "posting_date": frappe.utils.today(),
                "items": [
                    {
                        "item_code": "SKU002",
                        "qty": 5,
                        "rate": 190,
                        "against_sales_order": so_name,
                        "so_detail": frappe.db.get_value("Sales Order Item", {"parent": so_name, "item_code": "SKU002"}, "name")
                    }
                ]
            })
            dn.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [20] Draft Delivery Note '{dn.name}' created")
    except Exception as e:
        log(f"ERR [20] Delivery Note failed: {e}")

def setup_manufacturing():
    """Create sample data for Manufacturing: Workstations, Operations, Items, BOM, Work Order"""
    company_name = "Arising Packaging"
    log("\n--- Setting up Manufacturing Data ---")

    # ── 11. WORKSTATIONS ────────────────────────────────────────────────
    try:
        workstations = [
            {"workstation_name": "Primary Assembly Line", "hour_rate": 60, "company": company_name},
            {"workstation_name": "Quality Control Station", "hour_rate": 45, "company": company_name},
            {"workstation_name": "Packaging Center", "hour_rate": 35, "company": company_name}
        ]
        for ws_data in workstations:
            if not frappe.db.exists("Workstation", ws_data["workstation_name"]):
                ws = frappe.get_doc({"doctype": "Workstation", **ws_data})
                ws.insert(ignore_permissions=True)
                log(f"OK  [11] Workstation '{ws_data['workstation_name']}' created")
            else:
                log(f"SKP [11] Workstation '{ws_data['workstation_name']}' already exists")
    except Exception as e:
        log(f"ERR [11] Workstation failed: {e}")

    # ── 12. OPERATIONS ──────────────────────────────────────────────────
    try:
        ops_to_create = [
            ("Box Assembly", "Assemble corrugated boxes"),
            ("Final Inspection", "Final quality check"),
            ("Shrink Wrapping", "Wrap for shipping"),
            ("Material Cutting", "Cutting sheets to size")
        ]
        for op_name, op_desc in ops_to_create:
            if not frappe.db.exists("Operation", op_name):
                op = frappe.new_doc("Operation")
                op.name = op_name
                op.operation = op_name
                op.description = op_desc
                op.insert(ignore_permissions=True)
                log(f"OK  [12] Operation '{op_name}' created")
            else:
                log(f"SKP [12] Operation '{op_name}' already exists")
    except Exception as e:
        log(f"ERR [12] Operation failed: {e}")

    # ── 13. ITEMS (Manufacturing) ───────────────────────────────────────
    items = [
        {
            "item_code": "RM-SHEET-01",
            "item_name": "Corrugated Sheet 2x2m",
            "item_group": "Raw Materials",
            "is_stock_item": 1,
            "stock_uom": "Nos",
            "standard_rate": 5.0
        },
        {
            "item_code": "RM-GLUE-01",
            "item_name": "Industrial Glue 1L",
            "item_group": "Raw Materials",
            "is_stock_item": 1,
            "stock_uom": "Nos",
            "standard_rate": 12.5
        },
        {
            "item_code": "FG-BOX-100",
            "item_name": "Large Shipping Box XP",
            "item_group": "Products",
            "is_stock_item": 1,
            "stock_uom": "Nos",
            "is_sales_item": 1,
            "standard_rate": 25.0
        }
    ]

    for item_data in items:
        try:
            if not frappe.db.exists("Item", item_data["item_code"]):
                item = frappe.get_doc({"doctype": "Item", **item_data})
                item.insert(ignore_permissions=True)
                log(f"OK  [13] Item '{item_data['item_code']}' created")
            else:
                log(f"SKP [13] Item '{item_data['item_code']}' already exists")
        except Exception as e:
            log(f"ERR [13] Item {item_data['item_code']} failed: {e}")

    # ── 14. BILL OF MATERIALS (BOM) ──────────────────────────────────────
    try:
        item_fg = "FG-BOX-100"
        if not frappe.db.exists("BOM", {"item": item_fg, "is_active": 1}):
            bom = frappe.new_doc("BOM")
            bom.item = item_fg
            bom.company = company_name
            bom.is_active = 1
            bom.is_default = 1
            bom.quantity = 100
            
            # Add child items
            bom.append("items", {"item_code": "RM-SHEET-01", "qty": 105, "uom": "Nos"})
            bom.append("items", {"item_code": "RM-GLUE-01", "qty": 1, "uom": "Nos"})
            
            # Add operations
            bom.with_operations = 1
            bom.append("operations", {
                "operation": "Box Assembly",
                "workstation": "Primary Assembly Line",
                "time_in_mins": 300,
                "operating_cost": 300
            })
            bom.append("operations", {
                "operation": "Final Inspection",
                "workstation": "Quality Control Station",
                "time_in_mins": 60,
                "operating_cost": 45
            })
            
            bom.insert(ignore_permissions=True)
            bom.submit()
            log(f"OK  [14] BOM for '{item_fg}' created and submitted")
        else:
            log(f"SKP [14] BOM for '{item_fg}' already exists")
    except Exception as e:
        log(f"ERR [14] BOM creation failed: {e}")

    # ── 15. WORK ORDERS ──────────────────────────────────────────────────
    try:
        if bom_name and not frappe.db.exists("Work Order", {"production_item": "FG-BOX-100", "docstatus": 0}):
            wo = frappe.get_doc({
                "doctype": "Work Order",
                "production_item": "FG-BOX-100",
                "bom_no": bom_name,
                "qty": 500,
                "company": company_name,
                "wip_warehouse": "Work In Progress - AP",
                "fg_warehouse": "Finished Goods - AP",
                "planned_start_date": frappe.utils.today()
            })
            
            # Warehouse handling
            for wh_field in ["wip_warehouse", "fg_warehouse"]:
                if not frappe.db.exists("Warehouse", getattr(wo, wh_field)):
                    setattr(wo, wh_field, frappe.db.get_value("Warehouse", {"company": company_name, "warehouse_type": "Work In Progress" if "wip" in wh_field else "Finished Goods"}, "name"))
                if not getattr(wo, wh_field):
                    setattr(wo, wh_field, frappe.db.get_value("Warehouse", {"company": company_name}, "name"))

            wo.insert(ignore_permissions=True)
            log(f"OK  [15] Work Order '{wo.name}' created (Draft) for 500 units")
        else:
            log("SKP [15] Work Order for 'FG-BOX-100' already exists or BOM missing")
    except Exception as e:
        log(f"ERR [15] Work Order creation failed: {e}")

def setup_projects():
    """Create sample Projects, Tasks, and Timesheets"""
    company_name = "Arising Packaging"
    
    # -- 19. PROJECT --
    try:
        project_name = "Warehouse Expansion 2026"
        if not frappe.db.exists("Project", project_name):
            project = frappe.get_doc({
                "doctype": "Project",
                "project_name": project_name,
                "status": "Open",
                "company": company_name,
                "project_type": "External",
                "expected_start_date": frappe.utils.today(),
                "expected_end_date": frappe.utils.add_days(frappe.utils.today(), 90)
            })
            project.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [19] Project '{project_name}' created")
        else:
            log(f"SKP [19] Project '{project_name}' already exists")
    except Exception as e:
        log(f"ERR [19] Project creation failed: {e}")

    # -- 20. TASKS --
    try:
        tasks = [
            {"subject": "Initial Site Survey", "status": "Completed"},
            {"subject": "Purchase of Construction Materials", "status": "Open"},
            {"subject": "Foundation Laying", "status": "Open"},
            {"subject": "Structural Inspection", "status": "Open"}
        ]
        
        project_id = frappe.db.get_value("Project", {"project_name": "Warehouse Expansion 2026"}, "name")
        
        if project_id:
            for task_data in tasks:
                if not frappe.db.exists("Task", {"subject": task_data["subject"], "project": project_id}):
                    task = frappe.get_doc({
                        "doctype": "Task",
                        "subject": task_data["subject"],
                        "project": project_id,
                        "status": task_data["status"],
                        "exp_start_date": frappe.utils.today(),
                        "exp_end_date": frappe.utils.add_days(frappe.utils.today(), 7),
                        "company": company_name
                    })
                    task.insert(ignore_permissions=True)
                    log(f"OK  [20] Task '{task_data['subject']}' created")
                else:
                    log(f"SKP [20] Task '{task_data['subject']}' already exists")
            frappe.db.commit()
    except Exception as e:
        log(f"ERR [20] Tasks creation failed: {e}")

    # -- 21. TIMESHEET --
    try:
        project_id = frappe.db.get_value("Project", {"project_name": "Warehouse Expansion 2026"}, "name")
        if project_id and not frappe.db.exists("Timesheet", {"parent_project": project_id, "docstatus": 0}):
            if not frappe.db.exists("Activity Type", "Execution"):
                frappe.get_doc({"doctype": "Activity Type", "activity_type": "Execution"}).insert()
            
            ts = frappe.get_doc({
                "doctype": "Timesheet",
                "company": company_name,
                "time_logs": [
                    {
                        "project": project_id,
                        "task": frappe.db.get_value("Task", {"subject": "Initial Site Survey", "project": project_id}, "name"),
                        "from_time": frappe.utils.now_datetime(),
                        "hours": 4,
                        "activity_type": "Execution"
                    }
                ]
            })
            ts.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [21] Timesheet created for project")
        else:
            log("SKP [21] Timesheet for project already exists")
    except Exception as e:
        log(f"ERR [21] Timesheet creation failed: {e}")

    # -- 22. SECOND PROJECT --
    try:
        project_name = "Automated Packaging Line"
        if not frappe.db.exists("Project", project_name):
            project = frappe.get_doc({
                "doctype": "Project",
                "project_name": project_name,
                "status": "Open",
                "company": company_name,
                "project_type": "Internal",
                "expected_start_date": frappe.utils.today(),
                "expected_end_date": frappe.utils.add_days(frappe.utils.today(), 120)
            })
            project.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [22] Project '{project_name}' created")
        else:
            log(f"SKP [22] Project '{project_name}' already exists")
    except Exception as e:
        log(f"ERR [22] Second Project failed: {e}")


def setup_quality():
    """Create sample Quality Goals, Procedures, and Inspections"""
    company_name = "Arising Packaging"
    
    # ── 16. QUALITY GOAL ────────────────────────────────────────────────
    try:
        goal_name = "Zero Customer Complaints"
        if not frappe.db.exists("Quality Goal", goal_name):
            goal = frappe.get_doc({
                "doctype": "Quality Goal",
                "quality_goal": goal_name,
                "goal": goal_name,
                "target": 0,
                "frequency": "Monthly",
                "uom": "Nos"
            })
            goal.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [16] Quality Goal '{goal_name}' created")
        else:
            log(f"SKP [16] Quality Goal '{goal_name}' already exists")
    except Exception as e:
        log(f"ERR [16] Quality Goal failed: {e}")

    # ── 17. QUALITY PROCEDURE ───────────────────────────────────────────
    try:
        proc_name = "Standard Packaging Inspection"
        if not frappe.db.exists("Quality Procedure", proc_name):
            # Check meta for field names
            proc = frappe.new_doc("Quality Procedure")
            proc.procedure_name = proc_name
            proc.quality_procedure = proc_name
            
            proc.append("processes", {"process_description": "Check for physical damage"})
            proc.append("processes", {"process_description": "Verify print quality"})
            proc.append("processes", {"process_description": "Measure dimensions"})
            
            proc.insert(ignore_permissions=True)
            log(f"OK  [17] Quality Procedure '{proc_name}' created")
        else:
            log(f"SKP [17] Quality Procedure '{proc_name}' already exists")
    except Exception as e:
        log(f"ERR [17] Quality Procedure failed: {e}")

    # ── 18. QUALITY INSPECTION TEMPLATE ─────────────────────────────────
    try:
        tmpl_name = "Box Quality Check"
        if not frappe.db.exists("Quality Inspection Template", tmpl_name):
            tmpl = frappe.new_doc("Quality Inspection Template")
            tmpl.quality_inspection_template_name = tmpl_name
            tmpl.item_group = "Products"
            tmpl.item_code = "FG-BOX-100"
            
            # Using 'specification' which is common across versions
            for spec in ["Length", "Width"]:
                tmpl.append("item_quality_inspection_parameter", {
                    "specification": spec,
                    "acceptance_criteria": "Standard +/- 0.5",
                    "numeric": 1,
                    "min_value": 0,
                    "max_value": 100
                })
            
            tmpl.insert(ignore_permissions=True)
            log(f"OK  [18] Quality Inspection Template '{tmpl_name}' created")
        else:
            log(f"SKP [18] Quality Inspection Template '{tmpl_name}' already exists")
    except Exception as e:
        log(f"ERR [18] Quality Inspection Template failed: {e}")

    # ── 19. QUALITY INSPECTION ──────────────────────────────────────────
    try:
        # Enable inspection on item first
        if frappe.db.exists("Item", "FG-BOX-100"):
            frappe.db.set_value("Item", "FG-BOX-100", {
                "inspection_required_before_purchase": 0,
                "inspection_required_before_delivery": 1
            })

        # Link to the draft Sales Invoice or just create a standalone
        qi = frappe.new_doc("Quality Inspection")
        qi.inspection_type = "Outgoing"
        qi.item_code = "FG-BOX-100"
        qi.sample_size = 5
        qi.inspection_template = "Box Quality Check"
        qi.status = "Accepted"
        
        # Append readings
        for spec in ["Length", "Width"]:
            qi.append("readings", {
                "specification": spec,
                "status": "Accepted",
                "reading_1": "Standard"
            })
            
        qi.insert(ignore_permissions=True)
        log(f"OK  [19] Quality Inspection '{qi.name}' created")
    except Exception as e:
        log(f"ERR [19] Quality Inspection failed: {e}")

def setup_subcontracting():
    """Create sample Subcontracting Order and related items"""
    company_name = "Arising Packaging"
    
    # -- 19. SUBCONTRACTING ITEMS --
    try:
        items = [
            {
                "item_code": "SUB-RM-001",
                "item_name": "Uncoated Cardboard",
                "item_group": "Raw Materials",
                "stock_uom": "Nos",
                "is_stock_item": 1,
                "is_purchase_item": 1
            },
            {
                "item_code": "SUB-FG-001",
                "item_name": "Coated Premium Box",
                "item_group": "Products",
                "stock_uom": "Nos",
                "is_stock_item": 1,
                "is_sub_contracted_item": 1
            },
            {
                "item_code": "SUB-SRV-001",
                "item_name": "Coating Service",
                "item_group": "Services",
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "is_purchase_item": 1
            }
        ]
        for item_data in items:
            if not frappe.db.exists("Item", item_data["item_code"]):
                item = frappe.get_doc({"doctype": "Item", **item_data})
                item.insert(ignore_permissions=True)
                log(f"OK  [19] Subcontracting Item '{item_data['item_code']}' created")
        frappe.db.commit()
    except Exception as e:
        log(f"ERR [19] Subcontracting Items failed: {e}")

    # -- 20. BOM FOR SUBCONTRACTING --
    bom_name = None
    try:
        if not frappe.db.exists("BOM", {"item": "SUB-FG-001", "is_active": 1}):
            bom = frappe.get_doc({
                "doctype": "BOM",
                "item": "SUB-FG-001",
                "quantity": 1,
                "company": company_name,
                "is_active": 1,
                "is_default": 1,
                "items": [
                    {
                        "item_code": "SUB-RM-001",
                        "qty": 1,
                        "uom": "Nos",
                        "stock_uom": "Nos"
                    }
                ]
            })
            bom.insert(ignore_permissions=True)
            bom_name = bom.name
            
            # Set as default BOM in Item
            item = frappe.get_doc("Item", "SUB-FG-001")
            item.default_bom = bom_name
            item.save(ignore_permissions=True)
            
            log(f"OK  [20] BOM '{bom_name}' created and set as default for Subcontracting")
        else:
            bom_name = frappe.db.get_value("BOM", {"item": "SUB-FG-001", "is_active": 1}, "name")
            log(f"SKP [20] BOM for 'SUB-FG-001' already exists")
        frappe.db.commit()
    except Exception as e:
        log(f"ERR [20] BOM creation failed: {e}")

    # -- 21. PURCHASE ORDER (FOR SUBCONTRACTING) --
    try:
        # Ensure supplier exists
        supplier = "Global Logistics Sdn Bhd"
        if not frappe.db.exists("Supplier", supplier):
             supplier = frappe.db.get_value("Supplier", {}, "name") or "Expert Subcontractor Co."
        
        po_name = None
        if not frappe.db.exists("Purchase Order", {"supplier": supplier, "is_subcontracted": 1, "docstatus": 0}):
            po = frappe.get_doc({
                "doctype": "Purchase Order",
                "supplier": supplier,
                "company": company_name,
                "is_subcontracted": 1,
                "transaction_date": frappe.utils.today(),
                "schedule_date": frappe.utils.add_days(frappe.utils.today(), 14),
                "items": [
                    {
                        "item_code": "SUB-SRV-001", # SERVICE ITEM in v16
                        "qty": 100,
                        "rate": 2.5,
                        "warehouse": "Stores - AP" if frappe.db.exists("Warehouse", "Stores - AP") else None,
                        "fg_item": "SUB-FG-001",
                        "fg_item_qty": 100
                    }
                ]
            })
            po.insert(ignore_permissions=True)
            po_name = po.name
            log(f"OK  [21a] Purchase Order '{po_name}' (Subcontracted/Service) created")
        else:
            po_name = frappe.db.get_value("Purchase Order", {"supplier": supplier, "is_subcontracted": 1, "docstatus": 0}, "name")

        # -- 21b. SUBCONTRACTING ORDER --
        if po_name and not frappe.db.exists("Subcontracting Order", {"supplier": supplier, "docstatus": 0}):
            from subcontracting.subcontracting.doctype.subcontracting_order.subcontracting_order import make_subcontracting_order
            sco = make_subcontracting_order(po_name)
            sco.insert(ignore_permissions=True)
            frappe.db.commit()
            log(f"OK  [21b] Subcontracting Order '{sco.name}' created from PO")
        else:
            log(f"SKP [21b] Subcontracting Order already exists or PO missing")
    except Exception as e:
        log(f"ERR [21] Subcontracting flow failed: {e}")


def setup_stock():
    """Create sample Item Groups, Warehouses, and Stock Entries"""
    company_name = "Arising Packaging"
    log("\n--- Setting up Stock ---")
    
    # ── 22. ITEM GROUPS ──────────────────────────────────────────────────
    try:
        groups = ["Carton Boxes", "Packaging Tape", "Pallets"]
        for g in groups:
            if not frappe.db.exists("Item Group", g):
                frappe.get_doc({
                    "doctype": "Item Group",
                    "item_group_name": g,
                    "parent_item_group": "All Item Groups",
                    "is_group": 0
                }).insert(ignore_permissions=True)
                log(f"OK  [22] Item Group '{g}' created")
    except Exception as e:
        log(f"ERR [22] Item Group: {e}")

    # ── 23. WAREHOUSES ───────────────────────────────────────────────────
    try:
        warehouses = ["Main Warehouse", "Finished Goods", "Raw Materials", "Scrap Warehouse", "Work In Progress"]
        for wh in warehouses:
            wh_name = f"{wh} - AP"
            if not frappe.db.exists("Warehouse", wh_name):
                # Try to find parent
                parent_wh = f"All Warehouses - AP"
                if not frappe.db.exists("Warehouse", parent_wh):
                    parent_wh = None
                    
                frappe.get_doc({
                    "doctype": "Warehouse",
                    "warehouse_name": wh,
                    "company": company_name,
                    "warehouse_type": "Warehouse",
                    "parent_warehouse": parent_wh
                }).insert(ignore_permissions=True)
                log(f"OK  [23] Warehouse '{wh_name}' created")
    except Exception as e:
        log(f"ERR [23] Warehouse: {e}")

    # ── 24. STOCK ITEMS ──────────────────────────────────────────────────
    try:
        items = [
            {"item_code": "BOX-L-001", "item_name": "Large Box Heavy Duty", "item_group": "Carton Boxes", "stock_uom": "Nos"},
            {"item_code": "BOX-M-001", "item_name": "Medium Box Standard", "item_group": "Carton Boxes", "stock_uom": "Nos"},
            {"item_code": "TAPE-BR-001", "item_name": "Brown Packaging Tape", "item_group": "Packaging Tape", "stock_uom": "Roll"}
        ]
        for it in items:
            if not frappe.db.exists("Item", it["item_code"]):
                frappe.get_doc({
                    "doctype": "Item",
                    "item_code": it["item_code"],
                    "item_name": it["item_name"],
                    "item_group": it["item_group"],
                    "stock_uom": it["stock_uom"],
                    "is_stock_item": 1
                }).insert(ignore_permissions=True)
                log(f"OK  [24] Stock Item '{it['item_code']}' created")
    except Exception as e:
        log(f"ERR [24] Item: {e}")

    # ── 25. STOCK ENTRY (Initial Stock Receipt) ─────────────────────────
    try:
        if not frappe.db.exists("Stock Entry", {"stock_entry_type": "Material Receipt", "company": company_name, "docstatus": 1}):
            se = frappe.get_doc({
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Receipt",
                "company": company_name,
                "posting_date": frappe.utils.today(),
                "items": [
                    {"item_code": "BOX-L-001", "qty": 1000, "t_warehouse": "Main Warehouse - AP", "basic_rate": 3.5},
                    {"item_code": "BOX-M-001", "qty": 2000, "t_warehouse": "Main Warehouse - AP", "basic_rate": 2.5}
                ]
            })
            # Ensure warehouse exists
            if not frappe.db.exists("Warehouse", "Main Warehouse - AP"):
                se.items[0].t_warehouse = frappe.db.get_value("Warehouse", {"company": company_name}, "name")
                se.items[1].t_warehouse = se.items[0].t_warehouse
                
            se.insert(ignore_permissions=True)
            se.submit()
            log(f"OK  [25] Stock Receipt '{se.name}' submitted")
    except Exception as e:
        log(f"ERR [25] Stock Entry: {e}")

def setup_modern_icons():
    # 1. Update all Workspace icons to consistent, modern representations
    workspace_icons = {
        "Accounting": "credit-card",
        "Assets": "box",
        "Build": "tool",
        "Buying": "shopping-cart",
        "CRM": "users",
        "HR": "users-check",
        "Loans": "dollar-sign",
        "Manufacturing": "settings",
        "Payroll": "calendar",
        "Projects": "clipboard",
        "Quality": "check-circle",
        "Selling": "tag",
        "Stock": "package",
        "Support": "life-buoy",
        "Website": "layout"
    }

    try:
        workspaces = frappe.get_all("Workspace", fields=["name", "icon"])
        for ws in workspaces:
            if ws.name in workspace_icons:
                doc = frappe.get_doc("Workspace", ws.name)
                doc.icon = workspace_icons[ws.name]
                doc.flags.ignore_permissions = True
                doc.save()
    except Exception as e:
        log(f"ERR Workspace icons update failed: {e}")
        
    # 2. Inject global CSS to make Frappe's native stroke icons elegant (e.g. thinner strokes, softer colors)
    try:
        if not frappe.db.exists("Client Script", "Global Modern Icons"):
            doc = frappe.get_doc({
                "doctype": "Client Script",
                "dt": "Workspace",  # Target globally if applied universally, or using Website Theme
                "name": "Global Modern Icons",
                "module": "Core",
                "script": """
                    // Inject modern global CSS variables for elegant iconography
                    const style = document.createElement('style');
                    style.innerHTML = `
                        /* Enforce consistent modern stroke styles across all SVG usage */
                        svg.icon {
                            stroke-width: 1.5px !important; /* Thinner, more elegant lines */
                            stroke-linejoin: round !important;
                            stroke-linecap: round !important;
                            color: var(--text-color);
                        }
                        /* Modernize the sidebar icons specifically */
                        .sidebar-item-icon svg {
                            width: 18px !important;
                            height: 18px !important;
                            opacity: 0.8;
                            transition: all 0.2s ease-in-out;
                        }
                        .sidebar-item-icon svg:hover {
                            opacity: 1;
                            transform: scale(1.05); /* subtle pop */
                        }
                    `;
                    document.head.appendChild(style);
                """
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()

        log("OK  [*] Standardized workspaces and injected modern elegant icon styles.")
    except Exception as e:
        log(f"ERR Global Modern Icons script failed: {e}")
