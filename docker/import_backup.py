"""
import_backup.py — AoT backup DB → current Docker DB import script.

Rules:
  - Only shared columns are copied (new geo/AI cols keep their DB defaults)
  - dashboard (backup) → tab (current, page_type='dashboard') with same unique_id
  - widget.dashboard_id → widget.tab_id  via the dashboard unique_id mapping
  - misc: keep Docker InfluxDB host/password; import all other settings
  - Skip: alembic_version, conversion, roles, users, measurements, units
"""
import sqlite3
import uuid
from datetime import datetime, timezone

BACKUP  = '/tmp/backup.db'
CURRENT = '/app/aot/databases/aot.db'

# InfluxDB Docker settings we must NOT overwrite
# Token is read from .env INFLUXDB_ADMIN_TOKEN; falls back to docker-compose default
import os as _os
DOCKER_INFLUX = {
    'measurement_db_host':     'influxdb',
    'measurement_db_port':     8086,
    'measurement_db_password': _os.getenv('INFLUXDB_ADMIN_TOKEN', 'change-me-please'),
    'force_https':             0,
}

def get_cols(conn, tbl):
    return [r[1] for r in conn.execute(f'PRAGMA table_info({tbl})').fetchall()]

def shared_cols(b, c, tbl):
    return [col for col in get_cols(b, tbl) if col in get_cols(c, tbl)]

def import_table(b, c, tbl, extra_skip=None):
    """Import rows from backup into current, using only shared columns."""
    skip = set(extra_skip or [])
    cols = [col for col in shared_cols(b, c, tbl) if col not in skip]
    col_sql = ', '.join(cols)
    placeholders = ', '.join(['?'] * len(cols))
    rows = b.execute(f'SELECT {col_sql} FROM {tbl}').fetchall()
    if not rows:
        print(f'  {tbl}: 0 rows — skipped')
        return 0
    c.executemany(
        f'INSERT OR REPLACE INTO {tbl} ({col_sql}) VALUES ({placeholders})',
        rows
    )
    print(f'  {tbl}: {len(rows)} rows imported')
    return len(rows)

# ─────────────────────────────────────────────────────────────────────────────
b = sqlite3.connect(BACKUP)
c = sqlite3.connect(CURRENT)
b.row_factory = sqlite3.Row

print('=== AoT Backup Import ===')
print()

# ─── 1. Device configurations ────────────────────────────────────────────────
print('--- Device configurations ---')
import_table(b, c, 'input')
import_table(b, c, 'input_channel')
import_table(b, c, 'output')
import_table(b, c, 'output_channel')
import_table(b, c, 'custom_controller')
import_table(b, c, 'device_measurements')
import_table(b, c, 'conditional')
import_table(b, c, 'conditional_data')
import_table(b, c, 'trigger')
import_table(b, c, 'function')
import_table(b, c, 'function_actions')
import_table(b, c, 'function_channel')
import_table(b, c, 'displayorder')

# ─── 2. Dashboard → Tab + Widget ────────────────────────────────────────────
print()
print('--- Dashboards → Tabs + Widgets ---')

dashboards = b.execute('SELECT * FROM dashboard').fetchall()
now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')

# Build tab_id map: old dashboard unique_id → tab unique_id (reuse the same UUID)
dash_map = {}  # dash_unique_id → tab_unique_id (same value)

tab_cols = get_cols(c.cursor().connection, 'tab')
print(f'  Creating {len(dashboards)} tabs from dashboards...')
for d in dashboards:
    dash_uid = d['unique_id']
    tab_uid  = dash_uid  # reuse dashboard's UUID as tab UUID
    dash_map[dash_uid] = tab_uid
    c.execute(
        'INSERT OR REPLACE INTO tab (unique_id, name, page_type, position, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (tab_uid, d['name'], 'dashboard', d['sort_order'] or 0, now_str, now_str)
    )
print(f'  tab: {len(dashboards)} rows imported')

# Import widgets: replace dashboard_id with tab_id
b_wcols = get_cols(b, 'widget')
c_wcols = get_cols(c, 'widget')
# Shared columns excluding the old dashboard_id; we'll inject tab_id
shared_w = [col for col in b_wcols if col in c_wcols and col != 'dashboard_id']
# Add tab_id (not in backup schema) to the target col list
target_cols = shared_w + ['tab_id']
target_sql   = ', '.join(target_cols)
placeholders = ', '.join(['?'] * len(target_cols))

widgets = b.execute(f'SELECT {", ".join(shared_w)}, dashboard_id FROM widget').fetchall()
imported_w = 0
skipped_w  = 0
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
print(f'  widget: {imported_w} rows imported, {skipped_w} skipped (no matching tab)')

# ─── 3. misc: selective import ───────────────────────────────────────────────
print()
print('--- misc settings ---')
b_misc = dict(b.execute('SELECT * FROM misc').fetchone())
b_cols = get_cols(b, 'misc')
c_cols = get_cols(c, 'misc')

# Columns we import from backup
shared_m = [col for col in b_cols if col in c_cols and col not in DOCKER_INFLUX]
for col, val in DOCKER_INFLUX.items():
    b_misc[col] = val  # enforce Docker values

# Build the UPDATE statement for existing misc row
set_clauses = ', '.join(f'{col} = ?' for col in shared_m if col != 'id')
values = [b_misc[col] for col in shared_m if col != 'id']
c.execute(f'UPDATE misc SET {set_clauses} WHERE id = 1', values)
# Apply Docker overrides explicitly
c.execute(
    'UPDATE misc SET measurement_db_host=?, measurement_db_password=?, force_https=? WHERE id=1',
    (DOCKER_INFLUX['measurement_db_host'],
     DOCKER_INFLUX['measurement_db_password'],
     DOCKER_INFLUX['force_https'])
)
print(f'  misc: updated (Docker InfluxDB settings preserved)')

# ─── 4. SMTP ─────────────────────────────────────────────────────────────────
print()
print('--- smtp ---')
import_table(b, c, 'smtp')

# ─── 5. notes / note_tags ────────────────────────────────────────────────────
print()
print('--- notes / note_tags ---')
import_table(b, c, 'notes')
import_table(b, c, 'note_tags')

# ─── 6. MQTT host fix + activate all MQTT inputs ────────────────────────────
print()
print('--- MQTT inputs: fix host + activate ---')
mqtt_host = _os.getenv('MQTT_EXTERNAL_HOST', '192.168.0.205')
mqtt_rows = c.execute("SELECT unique_id, name, custom_options FROM input WHERE device='MQTT_PAHO_JSON'").fetchall()
import json as _json
mqtt_updated = 0
for uid, name, opts_raw in mqtt_rows:
    opts = _json.loads(opts_raw) if opts_raw else {}
    changed = False
    if opts.get('mqtt_hostname') not in (mqtt_host,):
        opts['mqtt_hostname'] = mqtt_host
        changed = True
    if changed:
        c.execute('UPDATE input SET custom_options=?, is_activated=1 WHERE unique_id=?',
                  (_json.dumps(opts), uid))
        mqtt_updated += 1
    else:
        c.execute('UPDATE input SET is_activated=1 WHERE unique_id=?', (uid,))
print(f'  {len(mqtt_rows)} MQTT inputs activated, {mqtt_updated} hosts updated to {mqtt_host}')

# ─── 7. Assign default tabs to imported records ──────────────────────────────
print()
print('--- Tab assignment ---')
def _first_tab(page_type):
    r = c.execute("SELECT unique_id FROM tab WHERE page_type=? ORDER BY position LIMIT 1", (page_type,)).fetchone()
    return r[0] if r else None

input_tab  = _first_tab('input')
output_tab = _first_tab('output')
func_tab   = _first_tab('function')

if input_tab:
    n = c.execute('UPDATE input SET tab_id=? WHERE tab_id IS NULL', (input_tab,)).rowcount
    print(f'  input:             {n} rows → {input_tab[:8]}')
if output_tab:
    n = c.execute('UPDATE output SET tab_id=? WHERE tab_id IS NULL', (output_tab,)).rowcount
    print(f'  output:            {n} rows → {output_tab[:8]}')
if func_tab:
    n = c.execute('UPDATE custom_controller SET tab_id=? WHERE tab_id IS NULL', (func_tab,)).rowcount
    print(f'  custom_controller: {n} rows → {func_tab[:8]}')

# ─── commit ──────────────────────────────────────────────────────────────────
c.commit()
b.close()
c.close()

print()
print('=== Import complete ===')
