import sys
import os

# Add paths
sys.path.append("/Volumes/AoT26_dev/2603_AoT_ai/Build/1_dev/env/lib/python3.9/site-packages")
sys.path.append("/Volumes/AoT26_dev/2603_AoT_ai/Build/1_dev")

print(f"DEBUG sys.path: {sys.path}")
sys.stdout.flush()

print("DEBUG: Importing werkzeug...")
sys.stdout.flush()
import werkzeug
print(f"DEBUG: werkzeug imported from {werkzeug.__file__}")
sys.stdout.flush()

print("DEBUG: Importing flask...")
sys.stdout.flush()
import flask
print(f"DEBUG: flask imported from {flask.__file__}")
sys.stdout.flush()

print("DEBUG: Importing from flask import Flask...")
sys.stdout.flush()
from flask import Flask
print("DEBUG: Flask imported successfully.")
sys.stdout.flush()
