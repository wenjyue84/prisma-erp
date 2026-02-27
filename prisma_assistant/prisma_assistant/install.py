"""
Install/migrate hooks for prisma_assistant.

after_migrate: Seeds Prisma AI Settings from site_config.json if the DocType
               record has no API key yet (prevents empty settings after fresh
               migrations or container rebuilds).
"""

import frappe
from prisma_assistant.api.chat import _DEFAULT_SYSTEM_PROMPT


def after_install():
    _seed_ai_settings()


def after_migrate():
    _seed_ai_settings()


def _seed_ai_settings():
    """
    Seed Prisma AI Settings from site_config.json and built-in defaults.
    Idempotent — never overwrites values already present in the DocType.
    """
    try:
        doc = frappe.get_single("Prisma AI Settings")
    except Exception:
        return  # DocType not installed yet

    conf = frappe.conf
    updates = {}

    # Connection fields — only seed from site_config if not set
    if not doc.get("api_key"):
        for conf_key, field in (
            ("ai_chat_provider", "provider"),
            ("ai_chat_api_key", "api_key"),
            ("ai_chat_base_url", "base_url"),
            ("ai_chat_model", "model"),
        ):
            val = conf.get(conf_key)
            if val:
                updates[field] = val

    # Always seed the built-in default prompt if the field is empty
    if not doc.get("system_prompt"):
        updates["system_prompt"] = _DEFAULT_SYSTEM_PROMPT

    if not updates:
        return

    doc.update(updates)
    doc.save(ignore_permissions=True)
    frappe.db.commit()
