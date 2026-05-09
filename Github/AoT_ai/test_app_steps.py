import sys
import os
import time

# Add paths dynamically
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "env", "lib", "python3.9", "site-packages"))
sys.path.append(BASE_DIR)

print("1. Importing Flask...")
from flask import Flask
print("2. Importing aot.config...")
from aot.config import ProdConfig
print("3. Creating Flask app object...")
app = Flask(__name__)
app.config.from_object(ProdConfig)

print("4. Importing register_extensions...")
from aot.aot_flask.app import register_extensions, register_blueprints, register_widget_endpoints

print("5. Running register_extensions...")
try:
    register_extensions(app)
    print("register_extensions completed.")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("6. Running register_blueprints...")
try:
    register_blueprints(app)
    print("register_blueprints completed.")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("7. Success! All initialization steps passed.")
