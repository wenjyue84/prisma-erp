# Frappe Developer Agent Memory

## bench execute — module path rules
`bench --site frontend execute <module.function>` resolves the first dotted segment as a **registered Frappe app name**. The file must live inside `apps/<app_name>/<app_name>/`, e.g.:
- Place script at: `apps/prisma_assistant/prisma_assistant/configure_ai_settings.py`
- Call as: `bench --site frontend execute prisma_assistant.configure_ai_settings.run`
- Placing the file at bench root (`apps/frappe/`, `apps/prisma_assistant/` outer level) causes `AppNotInstalledError`.

## prisma_assistant — 3-tier fallback chain (deployed 2026-02-28)
`prisma_assistant.api.chat.send_message` supports a 3-tier fallback. The attempt loop in `_get_settings()` reads `fallback_provider/model/api_key/base_url` and `fallback2_*` fields from the `Prisma AI Settings` Single DocType. No label prefix is added for the primary; `*(Using fallback: <model>)*` is prepended only when a fallback responds.

Active configuration on EC2 `frontend` site:
- Primary: `ollama` / `gemini-3-flash-preview:cloud` via Cloudflare tunnel
- Fallback 1: `gemini` / `gemini-2.0-flash`
- Fallback 2: `openai` (compatible) / `moonshot-v1-8k` at `https://api.moonshot.ai/v1/chat/completions`

## prisma_assistant DocType — fallback2 fields added
`prisma_ai_settings.json` now includes `fallback2_provider`, `fallback2_model`, `fallback2_api_key` (Password), `fallback2_base_url`. After adding new fields to a Single DocType, run `bench migrate` to add the DB columns before saving.

## Hot-deploy pattern (no image rebuild)
1. `git pull` on EC2 to get latest code
2. `docker cp <file> prisma-erp-backend-1:<container_path>` to sync individual files
3. `bench --site frontend migrate` if DocType JSON has new fields
4. `bench --site frontend execute <app>.<module>.run` to run one-off scripts
5. `bench --site frontend clear-cache && docker compose restart backend`

## sites/assets split-volume gotcha
`sites/assets` is a separate anonymous Docker volume per container. JS/CSS assets hot-deployed must go into the **frontend** container (nginx), not backend. See project MEMORY.md.
