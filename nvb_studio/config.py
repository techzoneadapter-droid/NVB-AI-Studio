import json
import os
from pathlib import Path

APP_NAME = "NVB AI Studio"
REPOSITORY = "techzoneadapter-droid/NVB-AI-Studio"


def data_dir() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or Path.home() / ".local" / "share")
    target = base / "NVB_AI_Studio"
    target.mkdir(parents=True, exist_ok=True)
    return target


def initial_settings():
    return {
        "gateway_url": "http://127.0.0.1:8000",
        "output_dir": str(Path.home() / "Videos" / "NVB_AI_Studio"),
        "image_model": "gemini-3.1-flash-image-landscape",
        "video_model": "veo_3_1_t2v_fast_landscape",
        "concurrency": 1,
        "retries": 0,
        "ffmpeg": "ffmpeg",
    }


def load_settings():
    settings = initial_settings()
    path = data_dir() / "settings.json"
    if path.is_file():
        try:
            incoming = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(incoming, dict):
                settings.update({k: v for k, v in incoming.items() if k in settings})
        except (ValueError, OSError):
            pass
    return settings


def save_settings(settings):
    path = data_dir() / "settings.json"
    temp = path.with_suffix(".tmp")
    safe = {key: settings.get(key, val) for key, val in initial_settings().items()}
    temp.write_text(json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


class SecretStore:
    SERVICE = "NVB-AI-Studio-Sub2Gen"

    def __init__(self):
        self._memory = ""

    def get(self):
        if self._memory:
            return self._memory
        try:
            import keyring
            return keyring.get_password(self.SERVICE, "gateway-api-key") or ""
        except Exception:
            return ""

    def set(self, value, remember=False):
        self._memory = value or ""
        try:
            import keyring
            if remember and value:
                keyring.set_password(self.SERVICE, "gateway-api-key", value)
            elif not remember:
                keyring.delete_password(self.SERVICE, "gateway-api-key")
        except Exception:
            # The key still works for this process; never write secrets in plaintext.
            pass
