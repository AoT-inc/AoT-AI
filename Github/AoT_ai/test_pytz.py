import time
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "env", "lib", "python3.9", "site-packages"))

print("Testing pytz import...")
start = time.time()
import pytz
print(f"pytz imported in {time.time() - start:.2f}s")

print("Testing pytz.all_timezones access (expensive on SMB)...")
start = time.time()
_ = pytz.all_timezones
print(f"pytz.all_timezones accessed in {time.time() - start:.2f}s")

print("Testing babel import...")
start = time.time()
import babel
print(f"babel imported in {time.time() - start:.2f}s")
