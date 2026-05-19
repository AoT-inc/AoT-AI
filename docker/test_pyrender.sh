#!/bin/bash
set -e
apt-get update -qq
echo "=== searching xrender packages ==="
apt-cache search xrender
echo ""
echo "=== installing libxrender1 ==="
apt-get install -y --no-install-recommends libxrender1
echo ""
echo "=== testing pyrender ==="
python3 -c "
import os
os.environ.setdefault('PYOPENGL_PLATFORM', 'osmesa')
import pyrender
r = pyrender.OffscreenRenderer(64, 64)
r.delete()
print('pyrender OffscreenRenderer: OK (osmesa)')
"
