"""Manage a bundled, version-pinned sub2gen engine without user Git/Bun/uv setup.

The installer ships upstream source + built Chrome extension + the uv executable.
The first launch automatically prepares Python and locked dependencies in LocalAppData.
Chrome does not permit silent access to an existing signed-in profile; Chrome's
extension must be explicitly loaded and authorized by its owner once.
"""
from __future__ import annotations

import json
import hashlib
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
        archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == archive_hash:
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
        stamp.write_text(archive_hash, encoding="utf-8")

    def _admin_password(self):
        return self._secret("admin-password")

    def _env(self):
        env = os.environ.copy()
        env["SUB2GEN_ROOT"] = str(self.source)
        env["RAILWAY_VOLUME_MOUNT_PATH"] = str(self.root / "persistent")
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

    @staticmethod
    def _validate_extension(folder):
        """Verify the unpacked Chrome extension, not just manifest existence."""
        try:
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("manifest_version") != 3 or manifest.get("name") != "sub2gen Worker":
                return False
            required = ("manifest.json", "background.js", "popup.html",
                        "popup.js", "options.html", "options.js",
                        "content.js", "stealth.js")
            return all((folder / name).is_file() for name in required)
        except (OSError, ValueError, TypeError):
            return False

    def extension_folder(self):
        """Extract Chrome worker directly from Setup into a stable, discoverable folder.

        No running backend, Git, Bun, manual ZIP extraction, or Google cookies
        are needed to prepare the unpacked extension. Chrome must still obtain
        the user's permission to load it.
        """
        folder = self.root / "chrome-extension"
        if self._validate_extension(folder):
            return folder
        archive = bundled_path("engine-payload") / "sub2gen.zip"
        if not archive.is_file():
            raise EngineError(
                "Bộ cài thiếu sub2gen.zip chứa tiện ích Chrome. "
                "Hãy cài bản Setup mới nhất, không cần tự tải repo."
            )
        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / "chrome-extension.unpacking"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        prefix = "apps/captcha-extension/dist/"
        try:
            with zipfile.ZipFile(archive) as zf:
                copied = 0
                for member in zf.infolist():
                    name = member.filename.replace(chr(92), "/")
                    if not name.startswith(prefix) or member.is_dir():
                        continue
                    relative = Path(name[len(prefix):])
                    if relative.is_absolute() or ".." in relative.parts:
                        raise EngineError("Gói tiện ích Chrome có tên tệp không an toàn.")
                    target = (staging / relative).resolve()
                    if not target.is_relative_to(staging.resolve()):
                        raise EngineError("Gói tiện ích Chrome có đường dẫn không an toàn.")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    copied += 1
            if not copied or not self._validate_extension(staging):
                raise EngineError(
                    "Bộ cài chứa tiện ích Chrome chưa đầy đủ (manifest.js/background). "
                    "Hãy sử dụng Setup mới; không cần tự giải nén hoặc tải GitHub."
                )
            if folder.exists():
                shutil.rmtree(folder)
            staging.rename(folder)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
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
        """Provision one local managed key; extension imports Google cookies to localhost only."""
        try:
            import keyring
            existing = keyring.get_password(ENGINE_SERVICE, "managed-api-key")
            if existing:
                return existing
        except Exception:
            pass
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
            try:
                import keyring
                keyring.set_password(ENGINE_SERVICE, "managed-api-key", key)
                if keyring.get_password(ENGINE_SERVICE, "managed-api-key") != key:
                    raise EngineError("Không lưu được khóa engine vào Windows Credential Manager.")
            except EngineError:
                raise
            except Exception as exc:
                raise EngineError("Không lưu được khóa engine: " + str(exc)) from exc

            return key
        finally:
            session.close()

    def create_worker_pairing_code(self, api_key, ttl_seconds=600):
        """Request a short-lived worker pairing code from the LOCAL engine.

        This is distinct from the persistent managed API key. The code is never
        written to a file or log; Chrome consumes it only once during pairing.
        """
        if not api_key or not str(api_key).strip():
            raise EngineError("Chưa có khóa API nội bộ. Hãy bấm Kết nối Chrome trước.")
        if not self._health():
            raise EngineError("Engine sub2gen chưa chạy. Hãy bấm Kết nối Chrome trước.")
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(
                BASE_URL + "/api/workers/pairing-code",
                headers={"Authorization": "Bearer " + str(api_key).strip()},
                json={"ttl_seconds": max(30, min(int(ttl_seconds), 1800))},
                timeout=20,
            )
            if not response.ok:
                raise EngineError(
                    "Không tạo được mã ghép nối (HTTP " + str(response.status_code) +
                    "). Hãy bấm Kết nối Chrome lại rồi thử."
                )
            result = response.json()
            code = str(result.get("pairing_code") or "").strip()
            expires = int(result.get("expires_in") or ttl_seconds)
            if not code:
                raise EngineError("Engine không trả về Pairing code.")
            return {"pairing_code": code, "expires_in": expires}

    def bind_available_accounts(self):
        """Associate only locally imported accounts with our managed key."""
        try:
            import keyring
            key = keyring.get_password(ENGINE_SERVICE, "managed-api-key")
        except Exception:
            key = None
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
