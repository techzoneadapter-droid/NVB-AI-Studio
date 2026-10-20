"""End-user simulation: unpack the ACTUAL shipped ZIP into a clean location,
and start sub2gen with ONLY production dependencies, exactly like the desktop.
This catches imports that were accidentally classified as dev dependencies.
"""
import os
import secrets
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import requests

archive = Path("engine-payload/sub2gen.zip").resolve()
if not archive.is_file():
    raise SystemExit("Missing installer engine archive")

with tempfile.TemporaryDirectory(prefix="nvb-studio-smoke-", ignore_cleanup_errors=True) as dirname:
    temp = Path(dirname)
    project = temp / "sub2gen"
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(project)

    password = secrets.token_urlsafe(24)
    env = os.environ.copy()
    env.update({
        "SUB2GEN_ROOT": str(project),
        "SUB2GEN_ADMIN_USERNAME": "nvb-studio",
        "SUB2GEN_ADMIN_PASSWORD": password,
        "SUB2GEN_API_KEY": secrets.token_urlsafe(24),
        "SUB2GEN_CAPTCHA_METHOD": "extension",
        "SUB2GEN_REDIS_MODE": "off",
        "RAILWAY_VOLUME_MOUNT_PATH": str(temp / "persistent"),
        "UV_PROJECT_ENVIRONMENT": str(temp / "isolated-production-env"),
    })
    runtime = ["uv", "run", "--frozen", "--no-dev", "--project", str(project)]
    flags = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

    import_check = subprocess.run(
        runtime + ["python", "-c",
                   "import sub2gen_provider_chatgpt; "
                   "import sub2gen_image_worker; "
                   "from sub2gen.main import app; "
                   "print('PRODUCTION_IMPORT_OK')"],
        cwd=str(project), env=env, capture_output=True,
        text=True, errors="replace", timeout=210, **flags
    )
    if import_check.returncode or "PRODUCTION_IMPORT_OK" not in import_check.stdout:
        raise RuntimeError("Clean production install missing modules: " +
                           (import_check.stderr + import_check.stdout)[-3000:])

    log_path = temp / "engine-smoke.log"
    client = requests.Session()
    client.trust_env = False
    with open(log_path, "w", encoding="utf-8") as logfile:
        process = subprocess.Popen(runtime + ["sub2gen"],
            cwd=str(project), env=env, stdin=subprocess.DEVNULL,
            stdout=logfile, stderr=subprocess.STDOUT, **flags)
        try:
            for attempt in range(45):
                if process.poll() is not None:
                    raise RuntimeError("Sub2gen process exited: " +
                                       log_path.read_text(encoding="utf-8", errors="replace")[-3000:])
                try:
                    response = client.get("http://127.0.0.1:8000/health", timeout=2)
                    if response.ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(2)
            else:
                raise RuntimeError("Sub2gen health check timeout")

            login = client.post("http://127.0.0.1:8000/api/admin/login",
                json={"username": "nvb-studio", "password": password,
                      "remember_me": False}, timeout=20)
            login.raise_for_status()
            token = login.json()["token"]
            created = client.post("http://127.0.0.1:8000/api/admin/managed-apikeys",
                json={"client_name": "NVB AI Studio", "label": "Chrome",
                      "scopes": "*", "account_ids": [], "endpoint_limits": {}},
                headers={"Authorization": "Bearer " + token}, timeout=20)
            created.raise_for_status()
            if not (created.json().get("key") or {}).get("api_key"):
                raise RuntimeError("Managed API key was not created")
            print("PASS: clean production installation from packaged ZIP, "
                  "startup, admin login, API key provisioning")
        finally:
            # uv run spawns a child Python/Uvicorn process on Windows. Terminating
            # uv alone leaves its child holding engine-smoke.log open (WinError 32).
            # Kill the PROCESS TREE before removing the temporary directory.
            if os.name == "nt":
                try:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True, timeout=20, check=False)
                except (OSError, subprocess.SubprocessError):
                    pass
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            client.close()
