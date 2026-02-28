"""
Context for /test web page — requires login.
"""

import frappe

login_required = True


def get_context(context):
    context.title = "Prisma ERP Test Suite"
    context.no_cache = 1

    # Redirect guests to login
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = f"/login?redirect-to=/test"
        raise frappe.Redirect

    context.csrf_token = frappe.session.csrf_token or ""
    context.site_name = getattr(frappe.local, "site", "frontend")
