"""
Configure Prisma AI 3-tier fallback settings in ERPNext DB.

Run on EC2:
    bench --site frontend execute prisma_assistant.configure_ai_settings.run

Keys are read from site_config.json (persistent on EC2, not in git).
Set them once via:
    bench --site frontend set-config ai_gemini_key   "AIzaSy..."
    bench --site frontend set-config ai_openai_key   "sk-proj-..."
    bench --site frontend set-config ai_tailscale_key "cfee..."

Tier 1 (Primary)  : Gemini API (gemini-2.0-flash)
Tier 2 (Fallback) : OpenAI (gpt-4o-mini)
Tier 3 (Fallback2): Ollama on PC via Tailscale (openai-compatible endpoint)
"""


def run():
    import frappe

    # Reload the DocType from JSON to register any new fields (e.g. fallback2_*)
    # into tabDocField. Needed when bench migrate couldn't complete.
    try:
        frappe.reload_doctype("Prisma AI Settings", force=True)
        print("DocType reloaded")
    except Exception as e:
        print(f"reload_doctype warning (non-fatal): {e}")

    # Read API keys from site_config.json (set once on EC2, not committed to git)
    conf = frappe.get_site_config()
    gemini_key    = conf.get("ai_gemini_key", "")
    openai_key    = conf.get("ai_openai_key", "")
    tailscale_key = conf.get("ai_tailscale_key", "")

    settings = {
        # ── Primary: Gemini ────────────────────────────────────────────────
        "provider": "gemini",
        "model": "gemini-2.0-flash",
        "base_url": "",
        # ── Fallback 1: OpenAI ─────────────────────────────────────────────
        "fallback_model": "gpt-4o-mini",
        "fallback_base_url": "https://api.openai.com/v1/chat/completions",
        # ── Fallback 2: Ollama on PC via Tailscale ─────────────────────────
        "fallback2_provider": "openai",   # openai-compatible endpoint
        "fallback2_model": "gemma3:12b",
        "fallback2_base_url": "http://100.88.116.94:11434/v1/chat/completions",
    }

    # Only overwrite API keys if present in site_config (avoids clearing existing keys)
    if gemini_key:
        settings["api_key"] = gemini_key
    if openai_key:
        settings["fallback_api_key"] = openai_key
    if tailscale_key:
        settings["fallback2_api_key"] = tailscale_key

    # Direct DB writes to tabSingles — bypasses DocType field validation.
    for field, value in settings.items():
        frappe.db.set_value(
            "Prisma AI Settings", "Prisma AI Settings", field, value,
            update_modified=False
        )

    frappe.db.commit()
    print("Done: AI settings saved — Gemini -> OpenAI -> Ollama (Tailscale)")
    if not gemini_key:
        print("  NOTE: run 'bench --site frontend set-config ai_gemini_key <key>' to persist the Gemini key")
