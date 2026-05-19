"""
fix_mqtt_host.py — Update MQTT inputs to use 'mosquitto' instead of 'localhost'.

The imported inputs were configured for the old Debian installation where MQTT
ran on localhost.  In Docker, the MQTT broker is the 'mosquitto' container.
"""
import sqlite3, json

CURRENT = '/app/aot/databases/aot.db'
OLD_HOST = 'localhost'
NEW_HOST = 'mosquitto'

c = sqlite3.connect(CURRENT)
rows = c.execute(
    "SELECT unique_id, name, custom_options FROM input WHERE device='MQTT_PAHO_JSON'"
).fetchall()

updated = 0
for uid, name, opts_raw in rows:
    try:
        opts = json.loads(opts_raw) if opts_raw else {}
    except Exception:
        opts = {}

    changed = False
    for key in ('mqtt_hostname', 'host', 'broker'):
        if opts.get(key) == OLD_HOST:
            opts[key] = NEW_HOST
            changed = True

    if changed:
        c.execute(
            'UPDATE input SET custom_options=? WHERE unique_id=?',
            (json.dumps(opts), uid)
        )
        print(f'  Updated: {name}')
        updated += 1
    else:
        # Show current mqtt-related keys so we can diagnose if needed
        mqtt_keys = {k: v for k, v in opts.items() if 'host' in k.lower() or 'broker' in k.lower() or 'mqtt' in k.lower()}
        print(f'  {name}: {mqtt_keys}')

c.commit()
c.close()
print(f'\n{updated} inputs updated (localhost → mosquitto)')
