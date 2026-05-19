import sqlite3

c = sqlite3.connect('/app/aot/databases/aot.db')

def q(sql):
    return c.execute(sql).fetchall()

print('=== Inputs ===')
for r in q('SELECT name, device, is_activated FROM input'):
    print(f'  {r[0]} | {r[1]} | active={r[2]}')

print()
print('=== Outputs ===')
for r in q('SELECT name, output_type FROM output'):
    print(f'  {r[0]} | {r[1]}')

print()
print('=== Custom Controllers ===')
for r in q('SELECT name, device FROM custom_controller LIMIT 8'):
    print(f'  {r[0]} | {r[1]}')

print()
print('=== Tabs (from dashboards) ===')
for r in q('SELECT name, page_type, position FROM tab ORDER BY position LIMIT 10'):
    print(f'  [{r[2]}] {r[0]} ({r[1]})')

print()
print('=== Widgets per tab (top 10) ===')
for r in q('''
    SELECT t.name, COUNT(w.id) as cnt
    FROM tab t LEFT JOIN widget w ON w.tab_id = t.unique_id
    GROUP BY t.id ORDER BY t.position LIMIT 10
'''):
    print(f'  {r[0]}: {r[1]} widgets')

print()
print('=== misc InfluxDB settings ===')
for r in q('SELECT measurement_db_host, measurement_db_port, measurement_db_user, measurement_db_dbname FROM misc'):
    print(f'  host={r[0]} port={r[1]} user={r[2]} db={r[3]}')

print()
print('=== Summary counts ===')
for tbl in ['input', 'output', 'custom_controller', 'conditional', 'trigger',
            'device_measurements', 'tab', 'widget', 'input_channel', 'output_channel']:
    cnt = c.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
    print(f'  {tbl}: {cnt}')
