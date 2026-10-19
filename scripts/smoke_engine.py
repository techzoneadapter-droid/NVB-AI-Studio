"""Smoke test sub2gen backend and managed key API on Windows CI."""
import os
import secrets
import subprocess
import time
from pathlib import Path
import requests

root = Path("upstream-sub2gen").resolve()
password = secrets.token_urlsafe(24)
env = os.environ.copy()
env.update({
    "SUB2GEN_ROOT": str(root),
    "SUB2GEN_ADMIN_USERNAME": "nvb-studio",
    "SUB2GEN_ADMIN_PASSWORD": password,
    "SUB2GEN_API_KEY": secrets.token_urlsafe(24),
    "SUB2GEN_CAPTCHA_METHOD": "extension",
    "SUB2GEN_REDIS_MODE": "off",
})
log = root / "smoke.log"
client = requests.Session()
client.trust_env = False
with open(log, "w", encoding="utf-8") as logfile:
    process = subprocess.Popen(["uv", "run", "--no-dev", "--frozen", "sub2gen"],
        cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=logfile, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        for attempt in range(45):
            if process.poll() is not None:
                raise RuntimeError("Engine exited: " + log.read_text(encoding="utf-8", errors="replace")[-1500:])
            try:
                res = client.get("http://127.0.0.1:8000/health", timeout=2)
                if res.ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("Engine did not become healthy within 90 seconds")
        r = client.post("http://127.0.0.1:8000/api/admin/login", json={
            "username": "nvb-studio", "password": password, "remember_me": False}, timeout=20)
        if not r.ok:
            raise RuntimeError("Admin login HTTP " + str(r.status_code))
        token = r.json()["token"]
        r = client.post("http://127.0.0.1:8000/api/admin/managed-apikeys",
            json={"client_name": "NVB AI Studio", "label": "Chrome", "scopes": "*",
                  "account_ids": [], "endpoint_limits": {}},
            headers={"Authorization": "Bearer " + token}, timeout=20)
        if not r.ok or not (r.json().get("key") or {}).get("api_key"):
            raise RuntimeError("API key creation failed HTTP " + str(r.status_code))
        print("Engine / health / admin auth / managed key: OK")
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
        client.close()
