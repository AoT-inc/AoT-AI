import sys
import os

# Add projects paths dynamically
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "env", "lib", "python3.9", "site-packages"))
sys.path.append(BASE_DIR)

print("Importing create_app...")
try:
    from aot.aot_flask.app import create_app
    print("create_app imported.")
    app = create_app()
    print("App created.")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Starting app.run...")
try:
    app.run(host='0.0.0.0', port=8084, debug=True)
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("App exited naturally.")
