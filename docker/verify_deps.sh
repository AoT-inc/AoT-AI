#!/bin/bash
# Compare installed packages inside the aot-app container against setup.sh requirements.
# Run via: docker exec aot_local-aot-app-1 bash /app/docker/verify_deps.sh

set +e

APT_PKGS="gcc g++ git jq libatlas-base-dev libffi-dev libgeos-dev libheif-dev libi2c-dev logrotate mawk moreutils netcat-openbsd nginx python3 python3-dev python3-pip python3-setuptools python3-venv rng-tools sqlite3 unzip wget mosquitto-clients"

MISSING_APT=()
PRESENT_APT=()

echo "=== APT packages (setup.sh APT_PKGS + mosquitto-clients) ==="
for pkg in $APT_PKGS; do
  if dpkg -s "$pkg" >/dev/null 2>&1; then
    PRESENT_APT+=("$pkg")
    printf "  [OK]      %s\n" "$pkg"
  else
    MISSING_APT+=("$pkg")
    printf "  [MISSING] %s\n" "$pkg"
  fi
done

echo
echo "=== Node.js ==="
if command -v node >/dev/null 2>&1; then
  echo "  [OK] $(node -v)"
else
  echo "  [MISSING] node"
fi

echo
echo "=== Python runtime imports for libs needing native deps ==="
python3 - <<'PY'
import importlib, sys
checks = [
    ("shapely", "needs libgeos"),
    ("pyrender", "needs libgl1, libosmesa6"),
    ("trimesh", "pure python"),
    ("pillow_heif", "needs libheif"),
    ("PIL", "pillow"),
    ("cv2", "opencv-python-headless"),
    ("numpy", "BLAS bundled in wheel"),
    ("scipy", "BLAS bundled in wheel"),
    ("paho.mqtt.client", "MQTT client"),
    ("influxdb_client", "InfluxDB 2.x"),
    ("influxdb", "InfluxDB 1.x"),
    ("flask", "web framework"),
    ("gunicorn", "WSGI"),
    ("alembic", "DB migrations"),
    ("Pyro5", "RPC daemon<->app"),
    ("apscheduler", "scheduler"),
]
fail = 0
for mod, note in checks:
    try:
        importlib.import_module(mod)
        print(f"  [OK]   {mod:<22} ({note})")
    except Exception as e:
        fail += 1
        print(f"  [FAIL] {mod:<22} ({note}) -- {type(e).__name__}: {e}")
print()
print(f"Failed imports: {fail}")
sys.exit(0 if fail == 0 else 1)
PY
PY_RC=$?

echo
echo "=== requirements.txt vs pip freeze ==="
python3 - <<'PY'
import subprocess, re, sys
req = open('/app/requirements.txt').read().splitlines()
required = {}
for line in req:
    line = line.strip()
    if not line or line.startswith('#'): continue
    m = re.match(r'([A-Za-z0-9_\-\.]+)\s*([<>=!~]+\s*[\d\.A-Za-z\-\+]+)?', line)
    if m:
        name = m.group(1).lower().replace('_','-')
        required[name] = (line, m.group(2) or '')

freeze = subprocess.check_output(['pip', 'freeze'], text=True).splitlines()
installed = {}
for line in freeze:
    if '==' in line:
        n, v = line.split('==', 1)
        installed[n.lower().replace('_','-')] = v

missing, mismatch = [], []
for name, (raw, spec) in required.items():
    if name not in installed:
        missing.append(raw)
        continue
    if '==' in spec:
        want = spec.replace('=','').strip()
        got = installed[name]
        if want != got:
            mismatch.append(f"{name}: required {raw}, installed {got}")
print(f"requirements.txt entries: {len(required)}")
print(f"  installed:  {len(required) - len(missing)}")
print(f"  missing:    {len(missing)}")
print(f"  mismatched: {len(mismatch)}")
if missing:
    print('  MISSING:')
    for m in missing[:20]: print(f'    - {m}')
if mismatch:
    print('  MISMATCH:')
    for m in mismatch[:20]: print(f'    - {m}')
sys.exit(0 if not missing else 1)
PY
PIP_RC=$?

echo
echo "=== SUMMARY ==="
printf "APT present:  %d / %d\n" "${#PRESENT_APT[@]}" "$(echo "$APT_PKGS" | wc -w)"
printf "APT missing:  %d\n" "${#MISSING_APT[@]}"
if [ ${#MISSING_APT[@]} -gt 0 ]; then
  printf "  -> %s\n" "${MISSING_APT[*]}"
fi
echo "Python import: exit $PY_RC"
echo "pip freeze:    exit $PIP_RC"
