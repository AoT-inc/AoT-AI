import os
import subprocess
import sys

# BASE is the project root directory
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(BASE, "aot", "scripts")

def run(script):
    print(f"--- [PRESET] Running {script} ---")
    script_path = os.path.join(SCRIPTS, script)
    if not os.path.exists(script_path):
        print(f"  FAILED: Script not found: {script_path}")
        return
    
    # Use the current python executable (the one in the new venv)
    ret = subprocess.call([sys.executable, script_path])
    if ret != 0:
        print(f"  FAILED: {script} (exit code {ret})")
    else:
        print(f"  SUCCESS: {script}")

if __name__ == "__main__":
    print("🚀 Initializing AoT System Presets...")
    
    # 1. Structural Schema Fixes (Manual Migrations not in Alembic)
    run("add_is_ai_enabled_field.py")
    run("add_map_sort_order.py")
    
    # 2. Initial Data Seeding
    run("create_admin_user.py")
    run("seed_agent_mcp_access.py")
    run("sync_agent_prompts.py")
    
    print("\n✅ System Presets Applied Successfully.")
