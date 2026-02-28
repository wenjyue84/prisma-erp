"""
Prisma AI Chat — whitelisted API endpoint.

Settings are read from the "Prisma AI Settings" Single DocType (UI-configurable).
Falls back to site_config.json keys for backward compatibility:
    ai_chat_provider / ai_chat_api_key / ai_chat_model / ai_chat_base_url

Caller: prisma_assistant.api.chat.send_message
"""

import json
import frappe
from frappe import _


# ── Provider defaults ─────────────────────────────────────────────────────────
_PROVIDER_DEFAULTS = {
    "anthropic": {
        "model": "claude-haiku-4-5-20251001",
        "url": "https://api.anthropic.com/v1/messages",
    },
    "openai": {
        "model": "gpt-4o-mini",
        "url": "https://api.openai.com/v1/chat/completions",
    },
    "gemini": {
        "model": "gemini-2.0-flash-lite",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    },
    # OpenWebUI exposes an OpenAI-compatible API — default port 3000
    "ollama": {
        "model": "qwen2.5",
        "url": "http://host.docker.internal:3000/api/chat/completions",
    },
}

_DEFAULT_SYSTEM_PROMPT = """You are an AI assistant embedded in ERPNext for Prisma Technology (Malaysia).

You can help with anything the user asks, with particular depth in:

ERPNext / Frappe Framework:
- Any module: Accounting, Purchasing, Sales, Inventory, Manufacturing, HR, Projects, CRM
- Frappe doctype structure, reports, print formats, workflows, custom fields, scripts
- Setup, configuration, permissions, roles, and customisation best practices

Malaysian compliance (specialist knowledge):
- Payroll: PCB/MTD, EPF, SOCSO, EIS, HRDF levy calculations and deadlines
- LHDN MyInvois e-invoicing: UBL XML, submission API, error codes, status polling
- Statutory forms: EA Form (CP8A), Borang E, CP8D, CP21, CP22
- SST, transfer pricing, withholding tax, double-taxation agreements
- Employment Act 1955, minimum wage, foreign worker rules

General coding & integrations:
- Python, JavaScript, Frappe/ERPNext custom scripts and API calls
- REST APIs, webhooks, data imports/exports
- SQL queries for Frappe's MariaDB schema

Guidelines:
- Answer any question the user asks — do not refuse because it seems "off topic".
- Be concise and practical. Use numbered steps for procedures.
- When referencing ERPNext fields or doctypes, use their exact label.
- If uncertain about a regulatory detail, say so and point to the official source (LHDN portal, EPF website, etc.).
- Respond in the same language as the user (English or Bahasa Malaysia).
"""


# ── Settings helper ────────────────────────────────────────────────────────────
def _get_settings() -> dict:
    """
    Read AI settings from the Prisma AI Settings doctype.
    Falls back to frappe.conf for any value not set in the DocType.
    """
    doc_settings = {}
    try:
        doc = frappe.get_single("Prisma AI Settings")
        doc_settings = {
            "provider": doc.get("provider") or "",
            "api_key": doc.get_password("api_key") if doc.get("api_key") else "",
            "model": doc.get("model") or "",
            "fallback_model": doc.get("fallback_model") or "",
            "fallback_api_key": doc.get_password("fallback_api_key") if doc.get("fallback_api_key") else "",
            "base_url": doc.get("base_url") or "",
            "fallback_base_url": doc.get("fallback_base_url") or "",
            "system_prompt": doc.get("system_prompt") or "",
        }
    except Exception:  # noqa: BLE001
        pass  # DocType may not exist yet — use frappe.conf only

    return {
        "provider": (doc_settings.get("provider") or frappe.conf.get("ai_chat_provider") or "anthropic").lower(),
        "api_key": doc_settings.get("api_key") or frappe.conf.get("ai_chat_api_key") or "",
        "model": doc_settings.get("model") or frappe.conf.get("ai_chat_model") or "",
        "fallback_model": doc_settings.get("fallback_model") or "",
        "fallback_api_key": doc_settings.get("fallback_api_key") or "",
        "base_url": doc_settings.get("base_url") or frappe.conf.get("ai_chat_base_url") or "",
        "fallback_base_url": doc_settings.get("fallback_base_url") or "",
        "system_prompt": doc_settings.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT,
    }


# ── PDF text extraction (US-PA-06) ────────────────────────────────────────────
def _extract_pdf_content(file_dict: dict) -> dict:
    """
    Extract text from a PDF file. Returns:
      {"type": "text", "content": str, "name": str, "page_count": int}  — digital PDF
      {"type": "image", "data": str, "media_type": "image/jpeg", "name": str} — scanned/empty
    """
    import base64
    import io

    raw = base64.b64decode(file_dict["data"])
    name = file_dict.get("name", "document.pdf")

    try:
        try:
            import pypdf
            PdfReader = pypdf.PdfReader
        except ImportError:
            import PyPDF2 as pypdf  # type: ignore[no-redef]
            PdfReader = pypdf.PdfReader

        reader = PdfReader(io.BytesIO(raw))
        pages = reader.pages
        text = "\n".join((page.extract_text() or "") for page in pages).strip()

        if len(text) >= 100:
            return {
                "type": "text",
                "content": text,
                "name": name,
                "page_count": len(pages),
            }

        # Fewer than 100 chars — likely scanned; fall through to image path
        return {
            "type": "image",
            "data": file_dict["data"],  # raw PDF as "image" for vision model
            "media_type": "image/jpeg",
            "name": name,
        }

    except Exception:  # noqa: BLE001
        # Cannot extract — return a safe error text so the message still goes through
        return {
            "type": "text",
            "content": f"[Could not extract text from {name}]",
            "name": name,
            "page_count": 0,
        }


# ── Main whitelisted function ─────────────────────────────────────────────────
@frappe.whitelist()
def send_message(message: str, history: str = "[]", files: str = "[]") -> dict:
    """Send a user message (with optional file attachments) to the configured LLM."""
    s = _get_settings()
    provider = s["provider"]
    api_key = s["api_key"]
    model = s["model"] or _PROVIDER_DEFAULTS.get(provider, {}).get("model", "")
    fallback_model = s["fallback_model"]
    fallback_api_key = s["fallback_api_key"] or api_key
    base_url = s["base_url"]
    fallback_base_url = s["fallback_base_url"] or base_url  # defaults to same endpoint as primary
    system_prompt = s["system_prompt"]

    if not api_key:
        return {
            "error": _(
                "No AI API key configured. Open Prisma AI Settings to add your API key."
            )
        }

    if provider not in _PROVIDER_DEFAULTS:
        return {"error": _("Unsupported AI provider: {0}. Use anthropic, openai, gemini, or ollama.").format(provider)}

    try:
        parsed_history = json.loads(history) if history else []
    except (ValueError, TypeError):
        parsed_history = []

    parsed_history = parsed_history[-10:]

    # ── Process file attachments (US-PA-05 / US-PA-06) ─────────────────────
    try:
        raw_file_list = json.loads(files) if files else []
    except (ValueError, TypeError):
        raw_file_list = []

    processed_files = []   # image files for vision dispatch
    text_context_parts = []  # extracted text from digital PDFs

    for f in raw_file_list:
        if f.get("type") == "application/pdf":
            result = _extract_pdf_content(f)
            if result["type"] == "text":
                text_context_parts.append(
                    f"[Attached PDF: {result['name']}]\n{result['content']}"
                )
            else:
                # Scanned PDF — send as image to vision model
                processed_files.append({
                    "name": f["name"],
                    "type": "image/jpeg",
                    "data": result["data"],
                })
        else:
            # Images pass through as-is
            processed_files.append(f)

    # Prepend any PDF text to the message so the LLM sees it
    if text_context_parts:
        message = "\n\n".join(text_context_parts) + "\n\n" + message

    file_list = processed_files  # only image files remain for vision dispatch

    # ── Dispatch ────────────────────────────────────────────────────────────
    def _dispatch(mdl, key=None, fl=None, url_override=None):
        k = key or api_key
        fl = fl if fl is not None else file_list
        effective_base_url = url_override if url_override is not None else base_url
        if provider == "anthropic":
            return _call_anthropic(k, mdl, message, parsed_history, effective_base_url, system_prompt, fl)
        elif provider in ("openai", "ollama"):
            url = effective_base_url or _PROVIDER_DEFAULTS[provider]["url"]
            return _call_openai_compatible_with_tools(k, mdl, message, parsed_history, url, system_prompt, fl)
        elif provider == "gemini":
            return _call_gemini(k, mdl, message, parsed_history, effective_base_url, system_prompt, fl)

    try:
        return _dispatch(model)
    except Exception as exc:  # noqa: BLE001
        if fallback_model:
            try:
                result = _dispatch(fallback_model, key=fallback_api_key, url_override=fallback_base_url)
                if result.get("reply"):
                    result["reply"] = f"*(Using fallback model: {fallback_model})*\n\n" + result["reply"]
                return result
            except Exception as fallback_exc:  # noqa: BLE001
                frappe.log_error(str(fallback_exc), "Prisma AI Chat Error (Fallback)")
        frappe.log_error(str(exc), "Prisma AI Chat Error")
        return {"error": _("AI request failed: {0}").format(str(exc)[:200])}


# ── Anthropic ─────────────────────────────────────────────────────────────────
def _call_anthropic(
    api_key: str, model: str, message: str, history: list,
    base_url: str = "", system_prompt: str = "", file_list: list = None
) -> dict:
    import urllib.request

    file_list = file_list or []
    url = base_url or _PROVIDER_DEFAULTS["anthropic"]["url"]

    # Build message history (text-only for prior turns)
    messages = _history_to_messages(history, None)  # no current message yet

    # Build the user content: text + images
    if file_list:
        user_content = [{"type": "text", "text": message}]
        for f in file_list:
            if f.get("type", "").startswith("image/"):
                user_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": f["type"],
                        "data": f["data"],
                    },
                })
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": message})

    payload = json.dumps({
        "model": model,
        "max_tokens": 1024,
        "system": system_prompt or _DEFAULT_SYSTEM_PROMPT,
        "messages": messages,
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )

    # Vision requests need more time
    timeout = 120 if file_list else 60
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())

    reply = data["content"][0]["text"]
    return {"reply": reply}


# ── OpenAI-compatible (OpenAI, Ollama/OpenWebUI, LiteLLM, etc.) ───────────────

def _raw_openai_call(api_key: str, model: str, messages: list, url: str) -> dict:
    """Bare HTTP POST to an OpenAI-compatible endpoint. Raises on error."""
    import urllib.request

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": 1024,
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _get_fac_tools_openai() -> list:
    """
    Fetch available tools from Frappe Assistant Core and convert to OpenAI format.
    Returns [] if FAC is not installed or any error occurs.
    """
    try:
        from frappe_assistant_core.api.handlers import handle_tools_list
    except ImportError:
        return []

    try:
        resp = handle_tools_list(request_id=None)
        tools = resp.get("result", {}).get("tools", [])
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]
    except Exception:  # noqa: BLE001
        return []


def _execute_fac_tool(name: str, arguments: dict) -> str:
    """
    Execute a single FAC tool call and return the text result.
    Never raises — returns an error string so the agentic loop can continue.
    """
    try:
        from frappe_assistant_core.api.handlers import handle_tool_call

        result = handle_tool_call({"name": name, "arguments": arguments}, request_id="chat-1")
        content = result.get("result", {}).get("content", [])
        return "\n".join(c["text"] for c in content if c.get("type") == "text")
    except Exception as exc:  # noqa: BLE001
        return f"Tool execution error ({name}): {exc}"


def _call_openai_compatible_with_tools(
    api_key: str, model: str, message: str, history: list,
    url: str, system_prompt: str = "", file_list: list = None
) -> dict:
    """
    Agentic loop: attach FAC tools to each OpenAI call and handle tool_calls
    until the model returns a final text response (or 5 rounds exhausted).
    Supports multimodal content blocks when file_list contains images.
    """
    import urllib.request

    file_list = file_list or []
    tools = _get_fac_tools_openai()
    messages = [{"role": "system", "content": system_prompt or _DEFAULT_SYSTEM_PROMPT}]
    messages += _history_to_messages(history, None)  # no current message yet

    # Build user content: text + images
    if file_list:
        user_content = [{"type": "text", "text": message}]
        for f in file_list:
            if f.get("type", "").startswith("image/"):
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{f['type']};base64,{f['data']}"},
                })
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": message})

    for _round in range(5):
        extra = {}
        if tools:
            extra["tools"] = tools
            extra["tool_choice"] = "auto"

        raw_payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 1024,
        }
        raw_payload.update(extra)

        payload = json.dumps(raw_payload).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        timeout = 90 if file_list else 20
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())

        choice = data["choices"][0]
        msg = choice["message"]
        finish_reason = choice.get("finish_reason", "stop")

        if finish_reason != "tool_calls":
            reply = msg.get("content") or msg.get("reasoning") or ""
            return {"reply": reply}

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return {"reply": msg.get("content") or ""}

        messages.append({
            "role": "assistant",
            "content": msg.get("content"),
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}") or "{}")
            except (ValueError, TypeError):
                args = {}
            result_text = _execute_fac_tool(fn.get("name", ""), args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": result_text,
            })

    # Loop exhausted — final plain call so the LLM can summarise
    data = _raw_openai_call(api_key, model, messages, url)
    msg = data["choices"][0]["message"]
    return {"reply": msg.get("content") or ""}


def _call_openai_compatible(
    api_key: str, model: str, message: str, history: list,
    url: str, system_prompt: str = ""
) -> dict:
    """Simple (no-tools) path. Kept for reference; dispatch uses _with_tools."""
    messages = [{"role": "system", "content": system_prompt or _DEFAULT_SYSTEM_PROMPT}]
    messages += _history_to_messages(history, message)
    data = _raw_openai_call(api_key, model, messages, url)
    msg = data["choices"][0]["message"]
    return {"reply": msg.get("content") or msg.get("reasoning") or ""}


# ── Gemini ────────────────────────────────────────────────────────────────────
def _call_gemini(
    api_key: str, model: str, message: str, history: list,
    base_url: str = "", system_prompt: str = "", file_list: list = None
) -> dict:
    import urllib.request

    file_list = file_list or []

    contents = []
    for turn in history:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})

    # Build current user parts: text + inline images
    user_parts = [{"text": message}]
    for f in file_list:
        if f.get("type", "").startswith("image/"):
            user_parts.append({
                "inline_data": {
                    "mime_type": f["type"],
                    "data": f["data"],
                }
            })
    contents.append({"role": "user", "parts": user_parts})

    payload = json.dumps({
        "system_instruction": {"parts": [{"text": system_prompt or _DEFAULT_SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 1024},
    }).encode()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    if base_url:
        url = f"{base_url.rstrip('/')}/models/{model}:generateContent?key={api_key}"

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    timeout = 120 if file_list else 60
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())

    reply = data["candidates"][0]["content"]["parts"][0]["text"]
    return {"reply": reply}


# ── Settings form helpers ─────────────────────────────────────────────────────

_ALLOWED_KEY_FIELDS = {"api_key", "fallback_api_key"}


def _mask_key(key: str) -> str:
    """Return first-4 + ****...****  + last-4, or all stars for short keys."""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "****...****" + key[-4:]


@frappe.whitelist()
def get_api_key_info(field_name: str = "api_key") -> dict:
    """
    Return whether a Password field has a value stored and its masked preview.
    Used by the Prisma AI Settings form JS to show partial key without exposing it.
    """
    if field_name not in _ALLOWED_KEY_FIELDS:
        return {"has_key": False}
    try:
        doc = frappe.get_single("Prisma AI Settings")
        key = doc.get_password(field_name) if doc.get(field_name) else ""
    except Exception:  # noqa: BLE001
        key = ""
    if not key:
        return {"has_key": False, "masked": ""}
    return {"has_key": True, "masked": _mask_key(key)}


@frappe.whitelist()
def reveal_api_key(field_name: str = "api_key") -> dict:
    """
    Return the decrypted API key value for display in the settings form.
    Restricted to System Manager role.
    """
    if field_name not in _ALLOWED_KEY_FIELDS:
        frappe.throw(_("Invalid field name"))
    frappe.only_for("System Manager")
    try:
        doc = frappe.get_single("Prisma AI Settings")
        key = doc.get_password(field_name) if doc.get(field_name) else ""
    except Exception:  # noqa: BLE001
        key = ""
    return {"key": key}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _history_to_messages(history: list, current_message: str | None) -> list:
    """
    Convert stored history to OpenAI/Anthropic message format.
    If current_message is None, only the history turns are returned
    (caller appends the current message manually for multimodal support).
    """
    messages = []
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    if current_message is not None:
        messages.append({"role": "user", "content": current_message})
    return messages
