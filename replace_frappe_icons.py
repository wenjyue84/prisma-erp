#!/usr/bin/env python3
"""
replace_frappe_icons.py
=======================
Replace Frappe's Lucide SVG icon sprite with Tabler Icons.

Run from the prisma-erp repo root (with Docker containers running):
    uv run python replace_frappe_icons.py           # filled (default, dramatically different)
    uv run python replace_frappe_icons.py outline   # outline, stroke-width 1.5

What this does:
  1. Downloads the Tabler Icons SVG sprite from jsDelivr CDN
  2. Renames IDs: id="tabler[-filled]-NAME" [->] id="icon-NAME"
     (Frappe references icons as <use href="#icon-NAME">)
  3. For FILLED mode: injects fill/stroke inline styles on every path so
     Frappe's "fill: transparent" CSS cannot hide the solid icons.
  4. Saves the patched sprite to frappe_patches/tabler_lucide_icons.svg
  5. Copies it to the FRONTEND container's app directory
     (/apps/frappe/frappe/public/icons/lucide/icons.svg)

Why FRONTEND container?
  sites/assets/frappe is a symlink [->] apps/frappe/frappe/public (per-container
  image overlay). Frappe's include_icons() generates JS that browser-fetches the
  SVG from nginx. nginx resolves the URL through the FRONTEND container's symlink.

Persistence:
  The patched file is saved to frappe_patches/tabler_lucide_icons.svg.
  Committed to git for Dockerfile COPY source.
  deploy-ec2.sh step 4b hot-deploys it on every EC2 push.
"""

import os
import re
import subprocess
import sys
import tempfile
import urllib.request

# ─── Config ───────────────────────────────────────────────────────────────────
# Mode: "filled"  -> Tabler filled/solid icons (dramatically different look)
#       "outline" -> Tabler outline icons, stroke-width 1.5
MODE = "filled" if len(sys.argv) < 2 else sys.argv[1].lower()

OUTLINE_URL = "https://cdn.jsdelivr.net/npm/@tabler/icons-sprite@latest/dist/tabler-sprite.svg"
FILLED_URL  = "https://cdn.jsdelivr.net/npm/@tabler/icons-sprite@latest/dist/tabler-sprite-filled.svg"

FRONTEND_CONTAINER = "prisma-erp-frontend-1"
BACKEND_CONTAINER  = "prisma-erp-backend-1"

APP_ICONS_DIR = "/home/frappe/frappe-bench/apps/frappe/frappe/public/icons"
TARGET_SUBPATHS = [
    "lucide/icons.svg",   # Primary -- what Frappe's app_include_icons fetches
    "lucide.svg",         # Root-level lucide sprite (referenced by some Frappe utils)
]

LOCAL_SAVE = "frappe_patches/tabler_lucide_icons.svg"

# Frappe default icon stroke colour (--icon-stroke CSS variable default)
# Used as fallback fill colour for solid/filled icons.
FRAPPE_ICON_COLOR = "#383838"


# ─── Download ─────────────────────────────────────────────────────────────────
def download_sprite(url: str) -> str:
    print(f"[dl] Downloading Tabler sprite from jsDelivr...")
    print(f"     {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = resp.read().decode("utf-8")
    print(f"   Downloaded {len(content):,} bytes")
    return content


# ─── Patch IDs ────────────────────────────────────────────────────────────────
def patch_ids(content: str, filled: bool) -> str:
    """Rename IDs so Frappe can find them via <use href="#icon-NAME">."""
    if filled:
        # Filled sprite uses id="tabler-filled-NAME"
        prefix_from = 'id="tabler-filled-'
        href_from   = 'href="#tabler-filled-'
    else:
        prefix_from = 'id="tabler-'
        href_from   = 'href="#tabler-'

    print(f'[patch] Patching IDs: {prefix_from} -> id="icon-"')
    before = content.count(prefix_from)
    content = content.replace(prefix_from, 'id="icon-')
    content = content.replace(href_from,   'href="#icon-')
    after = content.count('id="icon-')
    print(f"   Renamed {before} symbol IDs  ({after} total icon- IDs in file)")
    return content


# ─── Filled-mode path fix ─────────────────────────────────────────────────────
def fix_filled_paths(content: str) -> str:
    """
    Frappe's CSS forces fill:transparent on all svg.icon elements, which hides
    filled icons that rely on fill="currentColor".

    Fix: add inline style="fill:COLOR;stroke:none" to every <path> element
    inside the filled sprite. Inline styles always beat external CSS (highest
    specificity), so Frappe's fill:transparent cannot override them.

    We also inject a <style> tag inside the SVG that uses the CSS variable
    --icon-stroke for theme-aware colouring (works in modern browsers).
    """
    print(f"[fill] Fixing filled-icon paths: adding inline fill style to paths...")

    # Replace fill="currentColor" on <symbol> elements with a neutral value
    # (the actual colour is set by the per-path inline styles below)
    content = content.replace('fill="currentColor"', 'fill="none"')

    # Add inline style to every <path> element so Frappe CSS cannot override.
    # We use a CSS variable with a hardcoded fallback: var(--icon-stroke,#383838)
    # The var() notation works inside style="" attributes in all modern browsers.
    before = content.count('<path ')
    content = re.sub(
        r'<path ',
        f'<path style="fill:var(--icon-stroke,{FRAPPE_ICON_COLOR});stroke:none" ',
        content,
    )
    print(f"   Patched {before} path elements with inline fill style")
    return content


# ─── Alias map: Frappe icon names that differ from Tabler names ──────────────
# Frappe's Lucide sprite had icons whose names don't exist in Tabler.
# These aliases add <symbol id="icon-FRAPPE-NAME"> pointing to the closest Tabler icon.
ALIASES = {
    "icon-arrow-left-to-line":   "icon-arrow-bar-left",
    "icon-arrow-right-from-line":"icon-arrow-bar-right",
    "icon-equal-approximately":  "icon-equal",
    "icon-kanban":               "icon-layout-kanban",
    "icon-minimize-2":           "icon-arrows-minimize",
    "icon-monitor":              "icon-device-desktop",
    "icon-panel-right-open":     "icon-layout-sidebar-right",
    "icon-sheet":                "icon-file-spreadsheet",
}


# ─── Docker cp helper ─────────────────────────────────────────────────────────
def docker_cp(src_path: str, container: str, dest_path: str) -> bool:
    cmd = ["docker", "cp", src_path, f"{container}:{dest_path}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[ok]  Copied -> {container}:{dest_path}")
        return True
    else:
        print(f"[err] docker cp failed: {result.stderr.strip()}")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    filled = (MODE == "filled")
    url = FILLED_URL if filled else OUTLINE_URL
    print(f"\n[mode] {'FILLED (solid icons)' if filled else 'OUTLINE (stroke-width 1.5)'}\n")

    # 1. Download
    content = download_sprite(url)

    # 2. Patch IDs
    content = patch_ids(content, filled=filled)

    if filled:
        # 3a. Fix filled paths so Frappe CSS cannot hide them
        content = fix_filled_paths(content)
    else:
        # 3b. Thin outlines: stroke-width 2 -> 1.5
        print("[style] Thinning strokes: stroke-width 2 -> 1.5")
        sw_count = content.count('stroke-width="2"')
        content = content.replace('stroke-width="2"', 'stroke-width="1.5"')
        print(f"   Updated {sw_count} stroke-width attributes")

    # 4. Add Frappe compatibility aliases
    print("[alias] Adding Frappe compatibility aliases...")
    alias_svgs = []
    for alias_id, source_id in ALIASES.items():
        alias_svgs.append(
            f'<symbol id="{alias_id}" viewBox="0 0 24 24">'
            f'<use href="#{source_id}"/></symbol>'
        )

    # 5. Inject inline <style> for theme-aware icon colour (secondary cache-bypass)
    if filled:
        inline_css = (
            '<style>'
            # Ensure any path that missed the regex also gets filled
            f'symbol path{{fill:var(--icon-stroke,{FRAPPE_ICON_COLOR});stroke:none}}'
            '</style>'
        )
    else:
        inline_css = (
            '<style>'
            'symbol path,symbol line,symbol polyline,symbol circle,symbol rect'
            '{stroke-width:1.5 !important}'
            '</style>'
        )
    alias_svgs.append(inline_css)

    content = content.replace("</svg>", "\n".join(alias_svgs) + "\n</svg>")
    print(f"   Added {len(alias_svgs) - 1} aliases + inline CSS")

    symbol_count = content.count("<symbol ")
    print(f"   Total symbols in patched sprite: {symbol_count:,}")

    # 6. Save locally
    os.makedirs(os.path.dirname(LOCAL_SAVE), exist_ok=True)
    with open(LOCAL_SAVE, "w", encoding="utf-8") as f:
        f.write(content)
    size_kb = os.path.getsize(LOCAL_SAVE) // 1024
    print(f"[ok]  Saved locally: {LOCAL_SAVE}  ({size_kb} KB)")

    # 7. Copy to FRONTEND container (what nginx actually serves)
    print("\n[->]  Deploying to FRONTEND container...")
    ok = True
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".svg", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(content)
        tmp = tf.name

    try:
        for subpath in TARGET_SUBPATHS:
            dest = f"{APP_ICONS_DIR}/{subpath}"
            ok = docker_cp(tmp, FRONTEND_CONTAINER, dest) and ok

        print("\n[->]  Deploying to BACKEND container...")
        for subpath in TARGET_SUBPATHS:
            dest = f"{APP_ICONS_DIR}/{subpath}"
            docker_cp(tmp, BACKEND_CONTAINER, dest)
    finally:
        os.unlink(tmp)

    # 8. Bump assets.json mtime on backend to change _version_number (forces browser re-fetch)
    print("\n[bump] Touching assets.json on backend to invalidate browser cache...")
    subprocess.run(
        ["docker", "exec", BACKEND_CONTAINER,
         "touch", "//home/frappe/frappe-bench/sites/assets/assets.json"],
        capture_output=True,
    )
    print("   Browser will fetch fresh sprite on next hard-reload (Ctrl+Shift+R)")

    print()
    if ok:
        mode_label = "FILLED solid icons" if filled else "OUTLINE thin icons"
        print("=" * 60)
        print(f"  Done! [{mode_label}]")
        print("  Open http://localhost:8080 and press Ctrl+Shift+R")
        print("  (hard reload clears browser cache of the old sprite URL)")
        print()
        print("  To make this permanent -- add to Dockerfile.myinvois:")
        print(f"    COPY {LOCAL_SAVE} \\")
        print(f"         apps/frappe/frappe/public/icons/lucide/icons.svg")
        print("=" * 60)
    else:
        print("  Some copies failed -- check Docker container status.")
        sys.exit(1)


if __name__ == "__main__":
    main()
