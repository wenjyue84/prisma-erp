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
