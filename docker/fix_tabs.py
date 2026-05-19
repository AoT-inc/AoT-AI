"""
fix_tabs.py — Re-import all 36 dashboards as tabs with sequential positions.

The tab table has UNIQUE(page_type, position), so dashboards with the same
sort_order would silently overwrite each other.  This script:
  1. Clears all 'dashboard' type tabs and their widgets.
  2. Re-inserts all 36 dashboards with deduplicated sequential positions.
  3. Re-imports widgets with the correct tab_id mapping.
"""
import sqlite3
from datetime import datetime, timezone

BACKUP  = '/tmp/backup.db'
CURRENT = '/app/aot/databases/aot.db'

b = sqlite3.connect(BACKUP)
b.row_factory = sqlite3.Row
c = sqlite3.connect(CURRENT)

now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')

# ── 1. Remove existing 'dashboard' tabs (and cascade clear widgets) ──────────
existing_tab_ids = [r[0] for r in c.execute(
    "SELECT unique_id FROM tab WHERE page_type='dashboard'").fetchall()]

if existing_tab_ids:
    placeholders = ','.join('?' * len(existing_tab_ids))
    c.execute(f"DELETE FROM widget WHERE tab_id IN ({placeholders})", existing_tab_ids)
    c.execute("DELETE FROM tab WHERE page_type='dashboard'")
    print(f'Cleared {len(existing_tab_ids)} old dashboard tabs and their widgets')

# ── 2. Load all dashboards, sort by sort_order then unique_id for stability ──
dashboards = b.execute(
    'SELECT * FROM dashboard ORDER BY sort_order, unique_id').fetchall()
print(f'Importing {len(dashboards)} dashboards as tabs...')

dash_map = {}  # old dashboard unique_id → tab unique_id (same value)
for pos, d in enumerate(dashboards):
    dash_uid = d['unique_id']
    tab_uid  = dash_uid      # reuse the same UUID
    dash_map[dash_uid] = tab_uid
    c.execute(
        'INSERT INTO tab (unique_id, name, page_type, position, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (tab_uid, d['name'], 'dashboard', pos, now_str, now_str)
    )
print(f'  tab: {len(dashboards)} rows imported')

# ── 3. Re-import widgets with corrected tab_id mapping ──────────────────────
b_wcols_raw = [r[1] for r in b.execute('PRAGMA table_info(widget)').fetchall()]
c_wcols_raw = [r[1] for r in c.execute('PRAGMA table_info(widget)').fetchall()]
shared_w = [col for col in b_wcols_raw if col in c_wcols_raw and col != 'dashboard_id']

target_cols  = shared_w + ['tab_id']
target_sql   = ', '.join(target_cols)
placeholders = ', '.join(['?'] * len(target_cols))

widgets = b.execute(f'SELECT {", ".join(shared_w)}, dashboard_id FROM widget').fetchall()
imported_w = skipped_w = 0
for w in widgets:
    row = dict(zip(shared_w + ['dashboard_id'], w))
    dash_uid = row.pop('dashboard_id', None)
    tab_uid  = dash_map.get(dash_uid)
    if tab_uid is None:
        skipped_w += 1
        continue
    values = [row[col] for col in shared_w] + [tab_uid]
    c.execute(
        f'INSERT OR REPLACE INTO widget ({target_sql}) VALUES ({placeholders})',
        values
    )
    imported_w += 1

print(f'  widget: {imported_w} rows imported, {skipped_w} skipped')

c.commit()
b.close()
c.close()
print()
print('=== Tab/Widget fix complete ===')
