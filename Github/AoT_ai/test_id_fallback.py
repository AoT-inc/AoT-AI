
import os
import sys

# Add application root to sys.path
sys.path.append('/app')

from aot.aot_flask.app import create_app
from aot.ai.services.aot_data_tool_service import AoTDataToolService

app = create_app()
with app.app_context():
    # Test 1: Search for '1포장'
    print("--- Test 1: Search for '1포장' ---")
    search_res = AoTDataToolService.search_devices("1포장")
    print(f"Search Results: {search_res}")

    # Test 2: Get sensor detail using geo_id (fd557487-98a5-4841-8db8-66f9f9747316) and type 'weather'
    print("\n--- Test 2: Get sensor detail using geo_id (fd557487...) and type 'weather' ---")
    geo_id = "fd557487-98a5-4841-8db8-66f9f9747316"
    detail_res = AoTDataToolService.get_sensor_detail(geo_id, sensor_type="weather")
    
    if isinstance(detail_res, dict) and "error" in detail_res:
        print(f"❌ Failed: {detail_res['error']}")
    elif isinstance(detail_res, list):
        print(f"✅ Success: Received {len(detail_res)} measurement results")
        for idx, item in enumerate(detail_res):
            print(f"  [{idx}] {item.get('measurement')} ({item.get('device_name')})")
    else:
        print(f"❓ Unexpected response: {detail_res}")
