import json
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal
from .gateway import Gateway, GatewayError
from .store import slug


class BatchWorker(QThread):
    changed = pyqtSignal()
    message = pyqtSignal(str)

    def __init__(self, store, settings, api_key, parent=None):
        super().__init__(parent)
        self.store = store
        self.settings = dict(settings)
        self.api_key = api_key
        self.pause_flag = threading.Event()
        self.stop_flag = threading.Event()

    def pause(self, yes):
        if yes:
            self.pause_flag.set()
        else:
            self.pause_flag.clear()

    def stop(self):
        self.stop_flag.set()

    def _process(self, job):
        remote_id = job.get("remote_id") or ""
        gateway = Gateway(self.settings["gateway_url"], self.api_key)
        try:
            self.store.set_job(job["id"], status="running", error="")
            self.changed.emit()
            if not remote_id:
                self.message.emit(f"Gửi {job['kind']} #{job['sequence']} vào sub2gen")
                remote_id = gateway.submit(job)
                self.store.set_job(job["id"], remote_id=remote_id, attempts=job["attempts"] + 1)
            self.message.emit(f"Đang theo dõi #{job['sequence']} · job {remote_id}")
            response = gateway.wait(remote_id, self.stop_flag.is_set, lambda _: None)
            base_dir = Path(self.settings["output_dir"]) / slug(job["project_name"]) / (
                "Images" if job["kind"] == "image" else "Videos")
            ext = ".png" if job["kind"] == "image" else ".mp4"
            filename = f"{job['sequence']:05d}_{slug(job['prompt'], 35)}_{job['id'][:8]}{ext}"
            path = base_dir / filename
            saved = gateway.save_result(response, path)
            # Keep machine-readable generation provenance alongside every artifact.
            sidecar = Path(saved + ".json")
            safe_meta = {k: job[k] for k in ("id", "project_id", "kind", "mode", "sequence", "prompt", "model")}
            safe_meta["remote_id"] = remote_id
            sidecar.write_text(json.dumps(safe_meta, ensure_ascii=False, indent=2), encoding="utf-8")
            self.store.set_job(job["id"], status="completed", output=saved, error="")
            self.message.emit("Đã lưu: " + str(saved))
        except Exception as error:
            # A remote job may still be executing. Preserve its ID; no blind retry.
            status = "queued" if self.stop_flag.is_set() and remote_id else "uncertain" if remote_id else "failed"
            self.store.set_job(job["id"], status=status, error=str(error)[:500],
                               remote_id=remote_id)
            self.message.emit(f"#{job['sequence']}: {error}")
        finally:
            self.changed.emit()

    def run(self):
        limit = max(1, min(4, int(self.settings.get("concurrency", 1))))
        try:
            with ThreadPoolExecutor(max_workers=limit) as pool:
                running = {}
                seen = set()
                while not self.stop_flag.is_set():
                    if not self.pause_flag.is_set():
                        jobs = self.store.jobs(status="queued")
                        for job in jobs:
                            if len(running) >= limit:
                                break
                            if job["id"] in seen:
                                continue
                            seen.add(job["id"])
                            future = pool.submit(self._process, job)
                            running[future] = job["id"]
                    if not running:
                        if self.pause_flag.is_set():
                            self.msleep(200)
                            continue
                        break
                    done, _ = wait(list(running), timeout=0.4, return_when=FIRST_COMPLETED)
                    for future in done:
                        running.pop(future, None)
                        try:
                            future.result()
                        except Exception as e:
                            self.message.emit("Worker: " + str(e))
        finally:
            self.changed.emit()
