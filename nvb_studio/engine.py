"""Manage a bundled, version-pinned sub2gen engine without user Git/Bun/uv setup.

The installer ships upstream source + built Chrome extension + the uv executable.
The first launch automatically prepares Python and locked dependencies in LocalAppData.
Chrome does not permit silent access to an existing signed-in profile; Chrome's
extension must be explicitly loaded and authorized by its owner once.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import requests
from .config import data_dir, SecretStore

BASE_URL = "http://127.0.0.1:8000"
ENGINE_SERVICE = "NVB-AI-Studio-Engine"


class EngineError(RuntimeError):
    pass


def bundled_path(name):
    """PyInstaller --onedir places add-data in sys._MEIPASS."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / name


def engine_root():
    return data_dir() / "engine"


def get_uv():
    candidates = [bundled_path("uv.exe"), bundled_path("engine-payload") / "uv.exe"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class EngineManager:
    def __init__(self):
        self.root = engine_root()
        self.source = self.root / "sub2gen"
        self.secrets = None
        self.process = None

    def _secret(self, key):
        try:
            import keyring
            value = keyring.get_password(ENGINE_SERVICE, key)
            if value:
                return value
            value = secrets.token_urlsafe(48)
            keyring.set_password(ENGINE_SERVICE, key, value)
            if keyring.get_password(ENGINE_SERVICE, key) != value:
                raise EngineError("Không xác nhận được lưu thông tin vào Windows Credential Manager.")
            return value
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError("Không truy cập được Windows Credential Manager để lưu khóa quản trị an toàn: " + str(exc)) from exc

    def install_source(self):
        archive = bundled_path("engine-payload") / "sub2gen.zip"
        if not archive.is_file():
            raise EngineError(
                "Bộ cài này chưa chứa sub2gen tích hợp. Hãy tải Setup mới "
                "được build từ GitHub Actions. Không cần tự tải repo."
            )
        stamp = self.source / ".nvb-engine-ready"
        if stamp.is_file():
            return
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.root / "unpacking"
        if temp.exists():
            shutil.rmtree(temp)
        temp.mkdir()
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                relative = Path(member.filename.replace("\\", "/"))
                if member.is_dir():
                    continue
                if relative.is_absolute() or ".." in relative.parts:
                    raise EngineError("Gói engine có đường dẫn không an toàn.")
                target = (temp / relative).resolve()
                if not target.is_relative_to(temp.resolve()):
                    raise EngineError("Gói engine có đường dẫn không an toàn.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        required = (temp / "pyproject.toml", temp / "uv.lock",
                    temp / "config" / "setting_example.toml",
                    temp / "apps" / "captcha-extension" / "dist" / "manifest.json")
        if not all(p.is_file() for p in required):
            raise EngineError("Gói backend/Chrome extension không đầy đủ; dừng quá trình cài.")
        if self.source.exists():
            shutil.rmtree(self.source)
        temp.rename(self.source)
        stamp.write_text("bundled\n", encoding="utf-8")

    def _admin_password(self):
        return self._secret("admin-password")

    def _env(self):
        env = os.environ.copy()
        env["SUB2GEN_ROOT"] = str(self.source)
        env["SUB2GEN_ADMIN_USERNAME"] = "nvb-studio"
        env["SUB2GEN_ADMIN_PASSWORD"] = self._admin_password()
        env["SUB2GEN_API_KEY"] = self._secret("global-local-api-key")
        env["SUB2GEN_CAPTCHA_METHOD"] = "extension"
        env["SUB2GEN_REDIS_MODE"] = "off"
        env["UV_PYTHON_INSTALL_DIR"] = str(self.root / "python")
        env["UV_CACHE_DIR"] = str(self.root / "uv-cache")
        env["UV_PROJECT_ENVIRONMENT"] = str(self.root / ".venv")
        env["UV_NO_PROGRESS"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _health(self):
        try:
            r = requests.get(BASE_URL + "/health", timeout=2, proxies={"http": "", "https": ""})
            return r.ok and r.json().get("backend_running") is not False
        except (requests.RequestException, ValueError):
            return False

    def _owned(self):
        return (self.root / "engine-started.marker").exists()

    def start(self, report=None, timeout=900):
        progress = report or (lambda x: None)
        uv = get_uv()
        if self._health():
            if not self._owned():
                raise EngineError("Cổng 8000 đang có dịch vụ khác. Không thể xác nhận đây là engine do NVB AI Studio quản lý.")
            progress("Đã tìm thấy sub2gen đang chạy.")
            return BASE_URL
        if not uv:
            raise EngineError("Bộ cài chưa có uv.exe tích hợp. Hãy tải bản Setup mới.")
        progress("Chuẩn bị sub2gen tích hợp (lần đầu có thể mất vài phút)...")
        self.install_source()
        progress("Đang cài Python và phụ thuộc tự động, không cần chạy lệnh...")
        # No shell, no remote scripts, uv.lock is pinned by the installer build.
        log_file = self.root / "engine-start.log"
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        env = self._env()
        with open(log_file, "ab") as log:
            process = subprocess.Popen(
                [str(uv), "run", "--frozen", "--no-dev", "--project", str(self.source),
                 "sub2gen"],
                cwd=str(self.source),
                env=env,
                stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, **kwargs)
        self.process = process
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self._health():
                (self.root / "engine-started.marker").write_text("locally managed", encoding="utf-8")
                progress("sub2gen đã khởi động.")
                return BASE_URL
            if process.poll() is not None:
                tail = log_file.read_text(encoding="utf-8", errors="replace")[-1200:]
                raise EngineError("sub2gen không khởi động được. Nhật ký: " + tail)
            time.sleep(2)
        raise EngineError("Cài engine quá thời gian 15 phút. Kiểm tra mạng và nhật ký: " + str(log_file))

    def extension_folder(self):
        folder = self.source / "apps" / "captcha-extension" / "dist"
        if not (folder / "manifest.json").is_file():
            raise EngineError("Chưa có extension. Bấm Kết nối Chrome trước.")
        return folder

    def _admin(self):
        password = self._admin_password()
        session = requests.Session()
        session.trust_env = False
        response = session.post(BASE_URL + "/api/admin/login",
                 json={"username": "nvb-studio", "password": password, "remember_me": False}, timeout=18)
        if not response.ok:
            raise EngineError(f"Không đăng nhập được quản trị engine (HTTP {response.status_code}).")
        token = response.json().get("token")
        if not token:
            raise EngineError("Engine không trả về phiên quản trị.")
        session.headers["Authorization"] = "Bearer " + token
        return session

    def managed_key(self):
        """Provision one local managed key. No Google cookies leave the Chrome worker."""
        secret_store = SecretStore()
        if secret_store.get():
            return secret_store.get()
        session = self._admin()
        try:
            response = session.post(BASE_URL + "/api/admin/managed-apikeys",
                json={
                    "client_name": "NVB AI Studio",
                    "label": "Desktop + own Chrome worker",
                    "scopes": "*",
                    "account_ids": [],
                    "endpoint_limits": {},
                }, timeout=25)
            if not response.ok:
                raise EngineError(f"Không tạo được khóa nội bộ: HTTP {response.status_code}: {response.text[:180]}")
            key = (response.json().get("key") or {}).get("api_key")
            if not key:
                raise EngineError("Không nhận được API key từ engine.")
            secret_store.set(key, remember=True)
            if SecretStore().get() != key:
                raise EngineError("Không lưu được khóa vào Windows Credential Manager.")
            return key
        finally:
            session.close()

    def bind_available_accounts(self):
        """Associate only locally imported accounts with our managed key."""
        key = SecretStore().get()
        if not key:
            return 0
        session = self._admin()
        try:
            accounts_resp = session.get(BASE_URL + "/api/tokens", timeout=20)
            accounts_resp.raise_for_status()
            payload = accounts_resp.json()
            rows = payload if isinstance(payload, list) else payload.get("tokens", [])
            account_ids = sorted({int(row["id"]) for row in rows if isinstance(row, dict) and row.get("id")})
            if not account_ids:
                return 0
            resp = session.get(BASE_URL + "/api/admin/managed-apikeys", timeout=20)
            resp.raise_for_status()
            keys = resp.json().get("keys", [])
            owned = next((item for item in keys if item.get("client_name") == "NVB AI Studio"), None)
            if owned:
                assign = session.put(BASE_URL + "/api/admin/managed-apikeys/" + str(owned["id"]),
                              json={"account_ids": account_ids}, timeout=20)
                assign.raise_for_status()
            return len(account_ids)
        finally:
            session.close()


def chrome_executable():
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    return next((p for p in candidates if p.is_file()), None)


def open_chrome_page(url):
    chrome = chrome_executable()
    if not chrome:
        raise EngineError("Không tìm thấy Chrome. Hãy mở Chrome đã đăng nhập Flow trên máy.")
    subprocess.Popen([str(chrome), url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
