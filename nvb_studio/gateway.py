"""Adapt the documented sub2gen async completion API, not its internal tables."""
import base64
from contextlib import contextmanager
import ipaddress
import json
import mimetypes
import re
import socket
import time
from pathlib import Path
from urllib.parse import urlparse
import requests


class GatewayError(RuntimeError):
    pass


def image_data_url(path):
    file = Path(path)
    if not file.is_file():
        raise GatewayError(f"Không tìm thấy ảnh tham chiếu: {file}")
    if file.stat().st_size > 12 * 1024 * 1024:
        raise GatewayError("Ảnh tham chiếu vượt 12 MB.")
    mime = mimetypes.guess_type(file.name)[0]
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        raise GatewayError("Chỉ hỗ trợ ảnh PNG, JPEG, WebP.")
    return "data:" + mime + ";base64," + base64.b64encode(file.read_bytes()).decode("ascii")


def build_payload(job):
    refs = json.loads(job.get("refs_json") or "[]")
    mode = job.get("mode", "text")
    if mode == "text":
        refs = []
    if mode == "first-last" and len(refs) != 2:
        raise GatewayError("Video đầu/cuối phải có đúng 2 ảnh.")
    if mode == "image" and len(refs) != 1:
        raise GatewayError("Image-to-video cần đúng 1 ảnh.")
    if mode == "reference" and not 1 <= len(refs) <= 3:
        raise GatewayError("Reference-to-video cần 1–3 ảnh.")
    if len(refs) > 3:
        raise GatewayError("Tối đa 3 ảnh tham chiếu cho tác vụ video.")
    content = [{"type": "text", "text": job["prompt"]}]
    for ref in refs:
        content.append({"type": "image_url", "image_url": {"url": image_data_url(ref)}})
    return {"model": job["model"], "messages": [{"role": "user", "content": content if refs else job["prompt"]}],
            "stream": False}


def _urls_and_blobs(value):
    """Extract only media-like URL/data from a potentially nested OpenAI completion."""
    found = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("url", "image_url", "video_url", "download_url", "b64_json", "inlineData", "inline_data"):
                if isinstance(v, str):
                    found.append(v)
                elif isinstance(v, dict):
                    found.extend(_urls_and_blobs(v))
            else:
                found.extend(_urls_and_blobs(v))
    elif isinstance(value, list):
        for item in value:
            found.extend(_urls_and_blobs(item))
    elif isinstance(value, str):
        found.extend(re.findall(r"https?://[^\s\]\[<>\"']+", value))
        found.extend(re.findall(r"data:(?:image|video)/[\w.+-]+;base64,[A-Za-z0-9+/=]+", value))
    return list(dict.fromkeys(found))


def _is_safe_media_url(url):
    info = urlparse(url)
    if info.scheme not in ("https", "http") or not info.hostname:
        return False
    if info.username or info.password:
        return False
    if info.scheme == "http" and info.hostname not in ("127.0.0.1", "localhost", "::1"):
        return False
    if info.hostname in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        for entry in socket.getaddrinfo(info.hostname, 443):
            ip = ipaddress.ip_address(entry[4][0])
            if not ip.is_global:
                return False
    except (OSError, ValueError):
        return False
    return True


class Gateway:
    def __init__(self, base_url, api_key):
        u = urlparse(base_url.strip().rstrip("/"))
        if u.scheme not in ("http", "https") or not u.hostname:
            raise GatewayError("Địa chỉ Gateway không hợp lệ.")
        if u.scheme != "https" and u.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise GatewayError("Gateway từ xa phải sử dụng HTTPS.")
        self.base = base_url.strip().rstrip("/")
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"Authorization": "Bearer " + api_key,
                                     "Accept": "application/json"})

    def health(self):
        r = self.session.get(self.base + "/health", timeout=8)
        r.raise_for_status()
        return r.json()

    def submit(self, job):
        r = self.session.post(self.base + "/v1/async/chat/completions",
                              json=build_payload(job), timeout=45)
        if not r.ok:
            raise GatewayError(f"Gateway HTTP {r.status_code}: {r.text[:350]}")
        result = r.json()
        job_id = result.get("job_id")
        if not job_id:
            raise GatewayError("Gateway không trả về job_id; không tự thử gửi lại để tránh trừ credits.")
        return job_id

    def poll(self, job_id):
        r = self.session.get(self.base + "/v1/jobs/" + str(job_id), timeout=25)
        if not r.ok:
            raise GatewayError(f"Lỗi truy vấn tác vụ HTTP {r.status_code}: {r.text[:250]}")
        return r.json()

    def wait(self, remote_id, should_stop, on_progress, deadline=1200):
        end = time.monotonic() + deadline
        while time.monotonic() < end:
            if should_stop():
                raise GatewayError("Ngừng theo dõi cục bộ; ID tác vụ đã được lưu để tiếp tục.")
            response = self.poll(remote_id)
            state = str(response.get("status") or response.get("state") or "").lower()
            on_progress(state)
            if state in ("completed", "success", "succeeded", "done"):
                return response
            if state in ("failed", "error", "cancelled", "canceled"):
                raise GatewayError(str(response.get("error_message") or response.get("error") or response.get("message") or state)[:500])
            time.sleep(5)
        raise GatewayError("Quá thời gian chờ; ID tác vụ được giữ lại để kiểm tra tiếp.")

    @contextmanager
    def _media_response(self, url):
        # Never disclose the managed API key to a third-party CDN.
        # Only send Authorization to exactly the configured sub2gen origin.
        anonymous = requests.Session()
        anonymous.trust_env = False
        target = urlparse(self.base)
        source = urlparse(url)
        client = self.session if (
            source.scheme == target.scheme and source.netloc == target.netloc
        ) else anonymous
        try:
            with client.get(url, timeout=90, stream=True, allow_redirects=False) as result:
                yield result
        finally:
            anonymous.close()

    def save_result(self, response, destination):
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        candidates = _urls_and_blobs(response)
        for raw in candidates:
            raw = raw.rstrip(".,)")
            if raw.startswith("data:"):
                try:
                    info, data = raw.split(",", 1)
                    payload = base64.b64decode(data, validate=True)
                except Exception:
                    continue
            elif raw.startswith("http"):
                if not _is_safe_media_url(raw):
                    continue
                try:
                    with self._media_response(raw) as r:
                        if not r.ok:
                            continue
                        chunks, total = [], 0
                        for chunk in r.iter_content(1024 * 1024):
                            if chunk:
                                total += len(chunk)
                                if total > 800 * 1024 * 1024:
                                    raise GatewayError("Kết quả vượt dung lượng giới hạn.")
                                chunks.append(chunk)
                        payload = b"".join(chunks)
                except requests.RequestException:
                    continue
            else:
                continue
            is_video = dest.suffix.lower() == ".mp4"
            if (is_video and payload[4:8] != b"ftyp") or (
                not is_video and not (
                    payload.startswith(b"\x89PNG") or payload.startswith(b"\xff\xd8") or
                    payload.startswith(b"RIFF") or payload.startswith(b"\x00\x00\x00\x0cJXL")
                )):
                continue
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(payload)
            tmp.replace(dest)
            return str(dest)
        raise GatewayError("Job đã hoàn tất nhưng chưa lấy được media hợp lệ. Kiểm tra kết quả trong sub2gen.")
