import sys
import os
import faulthandler

faulthandler.enable()

# Add paths
sys.path.append("/Volumes/AoT26_dev/2603_AoT_ai/Build/1_dev/env/lib/python3.9/site-packages")
sys.path.append("/Volumes/AoT26_dev/2603_AoT_ai/Build/1_dev")

def log(msg):
    print(msg)
    sys.stdout.flush()

log("STARTING TEST...")

log("Importing Flask...")
from flask import Flask
log("Flask imported.")

log("Importing create_app from aot.aot_flask.app...")
try:
    from aot.aot_flask.app import create_app
    log("create_app imported.")
except:
    import traceback
    traceback.print_exc()
    log("FAILED IMPORT")
    sys.exit(1)

log("Calling create_app()...")
try:
    app = create_app()
    log("App created.")
except:
    import traceback
    traceback.print_exc()
    log("FAILED CREATE")
    sys.exit(1)

log("TEST FINISHED SUCCESSFULLY.")
