from src.portal_manager import PortalManager
import os

pm = PortalManager()
pm.master_db = []
pm.load_cache()

if not pm.master_db:
    print("master_db is empty after load_cache. Please ensure portal_master.sdvxh exists in out/.")

found = False
for m in pm.master_db:
    title = m.get("title", "")
    if "PANIC HOLIC" in title:
        print(f"Found: {title}")
        for c in m.get("charts", []):
            print(f"  Chart: {c.get('difficulty')} Lv.{c.get('level')}")
        found = True

if not found:
    print("PANIC HOLIC not found in master_db")
    print("Sample titles in master_db:")
    for m in pm.master_db[:10]:
        print(f"  - {m.get('title')}")
