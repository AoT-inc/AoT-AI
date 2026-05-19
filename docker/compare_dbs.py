import sqlite3

backup = sqlite3.connect('/tmp/backup.db')
current = sqlite3.connect('/app/aot/databases/aot.db')

def get_tables(conn):
    return set(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall())

def get_cols(conn, tbl):
    return {r[1]: r[2] for r in conn.execute(f'PRAGMA table_info({tbl})').fetchall()}

backup_tables = get_tables(backup)
current_tables = get_tables(current)
shared = sorted(backup_tables & current_tables)

print('=== SCHEMA DIFF FOR SHARED TABLES ===')
for tbl in shared:
    b_cols = get_cols(backup, tbl)
    c_cols = get_cols(current, tbl)
    added = set(c_cols) - set(b_cols)
    removed = set(b_cols) - set(c_cols)
    if added or removed:
        print(f'  {tbl}:')
        if added:
            print(f'    + new cols (current only): {sorted(added)}')
        if removed:
            print(f'    - dropped (backup only):  {sorted(removed)}')

print()
print('=== ROW COUNTS IN BACKUP (non-empty tables) ===')
for tbl in shared:
    cnt = backup.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
    if cnt > 0:
        print(f'  {tbl}: {cnt} rows')

print()
print('=== ROW COUNTS IN CURRENT (non-empty tables) ===')
for tbl in shared:
    cnt = current.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
    if cnt > 0:
        print(f'  {tbl}: {cnt} rows')
