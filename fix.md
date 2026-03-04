# Fix: HR folder thumbnail icons too large on desk

## Date
2026-03-04

## Problem
On https://prismaerp.click/desk, the HR folder icon showed oversized child thumbnails that overflowed outside the icon boundary. The Accounting folder looked correct (small contained thumbnails). Both are `icon_type='Folder'` Desktop Icons that render a 3x3 thumbnail grid of their children.

## Root Cause

Bug in `desktop.js` line 1082 — the `folder-icon` CSS class was never applied to Folder-type icons:

```javascript
render_folder_thumbnail() {
    if (this.icon_type == "Folder") {      // enters this block
        // ... renders folder grid ...
        if (this.icon_type == "App") {     // IMPOSSIBLE — already "Folder" above!
            this.folder_wrapper.addClass("folder-icon");
        }
    }
}
```

Without the `folder-icon` class, child icons rendered at 54px (default icon size) instead of 9px (folder thumbnail size defined in `desktop.css`).

Accounting worked by coincidence — its child icons had no `data-logo` attribute, so the CSS happened to constrain them. HR children had `data-logo` set, which triggered a different rendering path that only respected the `folder-icon` class sizing.

## Fix Applied

**File:** `/home/frappe/frappe-bench/apps/frappe/frappe/desk/page/desktop/desktop.js` (line 1082, EC2 container)

```javascript
// Before:
if (this.icon_type == "App") {

// After:
if (this.icon_type == "Folder" || this.icon_type == "App") {
```

This ensures the `folder-icon` CSS class is applied to both Folder and App type icons, so child thumbnails render at the correct 9px size.

## Deployment Steps Taken

1. SSH to EC2 → `docker exec` sed patch on `desktop.js` line 1082
2. `bench --site frontend clear-cache`
3. `docker restart prisma-erp-frontend-1`

## Verification

- Cleared `localStorage._page:desktop` (client-side cache)
- Hard reload of https://prismaerp.click/desk
- Confirmed HR and Accounting folder thumbnails are identical size (12x12px containers, 9x9px icons)
- All 18 top-level desktop icons display correctly
