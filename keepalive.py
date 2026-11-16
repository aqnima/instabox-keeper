import os
import sys
import json
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone

API_KEY = os.environ.get("INSTABOX_API_KEY")
MACHINE_ID = os.environ.get("INSTABOX_MACHINE_ID", "m_agqx762r6grw3y3pg66lu5zqei")
API_BASE = "https://api.instabox.sh/v1"

if not API_KEY:
    print("Error: INSTABOX_API_KEY tidak ditemukan")
    sys.exit(1)

def req(path, method="GET", body=None):
    url = f"{API_BASE}{path}"
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Idempotency-Key": str(uuid.uuid4())
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"API Error [{e.code}] {method} {path}: {err_body}")
        raise

info = req(f"/machines/{MACHINE_ID}")
state = info.get("state")
max_run = int(info.get("maxRunMinutes") or 120)
threshold = max(30, max_run - 20)

elapsed = -1
rs = info.get("runStartedAt")
if rs:
    try:
        st = datetime.fromisoformat(rs.replace("Z", "+00:00"))
        elapsed = int((datetime.now(timezone.utc) - st).total_seconds() // 60)
    except Exception:
        pass

cd = info.get("cooldownUntil")
if cd:
    try:
        cdt = datetime.fromisoformat(cd.replace("Z", "+00:00"))
        if cdt > datetime.now(timezone.utc):
            print(f"Mesin lagi cooldown sampai {cd}. Skip...")
            sys.exit(0)
    except Exception:
        pass

print(f"Status Mesin: {state}, Umur: {elapsed}m / Max: {max_run}m (Batas flip: {threshold}m)")

if state == "running":
    if elapsed >= threshold and elapsed > 0:
        print(f"Umur mesin ({elapsed}m) >= {threshold}m. Melakukan fresh-run flip...")
        req(f"/machines/{MACHINE_ID}/suspend", method="POST", body={})
        for _ in range(30):
            time.sleep(2)
            chk = req(f"/machines/{MACHINE_ID}")
            if chk.get("state") in ["suspended", "paused"]:
                if chk.get("storage", {}).get("synced", True):
                    break
        req(f"/machines/{MACHINE_ID}/resume", method="POST", body={})
        print("Fresh-run flip selesai! Mesin hidup lagi dengan timer baru.")
    else:
        req(f"/machines/{MACHINE_ID}/exec", method="POST", body={"cmd": "true"})
        print("Ping berhasil! Timer idle 30 menit ter-reset.")
elif state in ["suspended", "paused"]:
    print("Mesin dalam status suspended/paused. Mencoba resume...")
    req(f"/machines/{MACHINE_ID}/resume", method="POST", body={})
    print("Mesin berhasil di-resume!")
elif state == "stopped":
    print("Mesin mati (stopped). Mencoba start...")
    req(f"/machines/{MACHINE_ID}/start", method="POST", body={})
    print("Mesin berhasil di-start!")
else:
    print(f"Status '{state}' tidak dikenal, mencoba resume...")
    try:
        req(f"/machines/{MACHINE_ID}/resume", method="POST", body={})
        print("Mesin berhasil di-resume!")
    except Exception as e:
        print(f"Gagal resume: {e}")
