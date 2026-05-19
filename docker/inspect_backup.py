import sqlite3, json

backup = sqlite3.connect('/tmp/backup.db')
backup.row_factory = sqlite3.Row
current = sqlite3.connect('/app/aot/databases/aot.db')
current.row_factory = sqlite3.Row

def schema(conn, tbl):
    return [(r['cid'], r['name'], r['type'], r['dflt_value'], r['notnull'])
            for r in conn.execute(f'PRAGMA table_info({tbl})').fetchall()]

# --- misc (settings) ---
print('=== misc (backup) ===')
for row in backup.execute('SELECT * FROM misc').fetchall():
    d = dict(row)
    # Hide passwords
    for k in list(d):
        if 'password' in k.lower() or 'secret' in k.lower():
            d[k] = '***'
    for k, v in d.items():
        if v not in (None, '', 0, False):
            print(f'  {k}: {v}')

# --- users ---
print()
print('=== users (backup) ===')
for row in backup.execute('SELECT id, name, email, roles_id FROM users').fetchall():
    print(f'  id={row["id"]} name={row["name"]} email={row["email"]} role={row["roles_id"]}')

print()
print('=== users (current) ===')
for row in current.execute('SELECT id, name, email, roles_id FROM users').fetchall():
    print(f'  id={row["id"]} name={row["name"]} email={row["email"]} role={row["roles_id"]}')

# --- dashboard schema diff ---
print()
print('=== dashboard schema ===')
b_dash = {r[1]: r[2] for r in backup.execute('PRAGMA table_info(dashboard)').fetchall()}
c_dash = {r[1]: r[2] for r in current.execute('PRAGMA table_info(dashboard)').fetchall()}
added = set(c_dash) - set(b_dash)
removed = set(b_dash) - set(c_dash)
same = set(b_dash) & set(c_dash)
print(f'  shared cols: {sorted(same)}')
if added:   print(f'  + new in current: {sorted(added)}')
if removed: print(f'  - only in backup: {sorted(removed)}')

# --- widget schema ---
print()
print('=== widget schema ===')
b_wid = {r[1]: r[2] for r in backup.execute('PRAGMA table_info(widget)').fetchall()}
c_wid = {r[1]: r[2] for r in current.execute('PRAGMA table_info(widget)').fetchall()}
added = set(c_wid) - set(b_wid)
removed = set(b_wid) - set(c_wid)
print(f'  shared cols: {sorted(set(b_wid) & set(c_wid))}')
if added:   print(f'  + new in current: {sorted(added)}')
if removed: print(f'  - only in backup: {sorted(removed)}')

# --- input sample ---
print()
print('=== input (backup sample) ===')
for row in backup.execute('SELECT unique_id, name, device, is_activated FROM input LIMIT 5').fetchall():
    print(f'  [{row["unique_id"][:8]}...] {row["name"]} ({row["device"]}) active={row["is_activated"]}')

# --- custom_controller sample ---
print()
print('=== custom_controller (backup sample) ===')
for row in backup.execute('SELECT unique_id, name, device FROM custom_controller LIMIT 5').fetchall():
    print(f'  [{row["unique_id"][:8]}...] {row["name"]} ({row["device"]})')

# --- output sample ---
print()
print('=== output (backup sample) ===')
for row in backup.execute('SELECT unique_id, name, output_type FROM output LIMIT 5').fetchall():
    print(f'  [{row["unique_id"][:8]}...] {row["name"]} ({row["output_type"]})')
