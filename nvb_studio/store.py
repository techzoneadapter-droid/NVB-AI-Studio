import json
import re
import sqlite3
from contextlib import contextmanager
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .config import data_dir


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(text, limit=72):
    cleaned = re.sub(r"[^\w\-.]+", "_", str(text), flags=re.UNICODE).strip("._")
    return cleaned[:limit] or "untitled"


class Store:
    def __init__(self, path=None):
        self.path = Path(path or data_dir() / "studio.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def conn(self):
        db = sqlite3.connect(str(self.path), timeout=30)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=30000")
            db.execute("PRAGMA foreign_keys=ON")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self):
        with self.conn() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                created_at TEXT NOT NULL, description TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS characters (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                refs_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                kind TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'text',
                sequence INTEGER NOT NULL, prompt TEXT NOT NULL,
                model TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                refs_json TEXT NOT NULL DEFAULT '[]',
                remote_id TEXT DEFAULT '', output TEXT DEFAULT '',
                error TEXT DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS jobs_state_idx ON jobs(status,created_at);
            CREATE INDEX IF NOT EXISTS jobs_project_idx ON jobs(project_id,sequence);
            """)

    def _all(self, query, args=()):
        with self.conn() as db:
            return [dict(row) for row in db.execute(query, args).fetchall()]

    def create_project(self, name, description=""):
        identifier = uuid.uuid4().hex
        with self.conn() as db:
            db.execute("INSERT INTO projects VALUES(?,?,?,?)", (identifier, name.strip(), now(), description))
        return identifier

    def projects(self):
        return self._all("SELECT * FROM projects ORDER BY created_at DESC")

    def project(self, project_id):
        return next(iter(self._all("SELECT * FROM projects WHERE id=?", (project_id,))), None)

    def create_character(self, project_id, name, description, refs):
        identifier = uuid.uuid4().hex
        with self.conn() as db:
            db.execute("INSERT INTO characters VALUES(?,?,?,?,?,?)",
                       (identifier, project_id, name.strip(), description, json.dumps(refs), now()))
        return identifier

    def characters(self, project_id):
        return self._all("SELECT * FROM characters WHERE project_id=? ORDER BY created_at", (project_id,))

    def delete_character(self, char_id):
        with self.conn() as db:
            db.execute("DELETE FROM characters WHERE id=?", (char_id,))

    def add_jobs(self, project_id, kind, mode, model, prompts, refs=()):
        if not prompts:
            return 0
        with self.conn() as db:
            seq = db.execute("SELECT COALESCE(MAX(sequence),0) FROM jobs WHERE project_id=?", (project_id,)).fetchone()[0]
            for i, prompt in enumerate(prompts, seq + 1):
                timestamp = now()
                db.execute("""INSERT INTO jobs
                    (id,project_id,kind,mode,sequence,prompt,model,status,refs_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (uuid.uuid4().hex, project_id, kind, mode, i, prompt.strip(),
                     model, "queued", json.dumps(list(refs)), timestamp, timestamp))
        return len(prompts)

    def jobs(self, project_id=None, status=None):
        query = "SELECT j.*,p.name AS project_name FROM jobs j JOIN projects p ON p.id=j.project_id WHERE 1=1"
        args = []
        if project_id:
            query += " AND j.project_id=?"
            args.append(project_id)
        if status:
            query += " AND j.status=?"
            args.append(status)
        query += " ORDER BY j.created_at,j.sequence"
        return self._all(query, args)

    def job(self, job_id):
        return next(iter(self._all("SELECT * FROM jobs WHERE id=?", (job_id,))), None)

    def set_job(self, job_id, **changes):
        allowed = {"status", "remote_id", "output", "error", "attempts"}
        changes = {k: v for k, v in changes.items() if k in allowed}
        if not changes:
            return
        changes["updated_at"] = now()
        cols = ", ".join(f"{k}=?" for k in changes)
        with self.conn() as db:
            db.execute(f"UPDATE jobs SET {cols} WHERE id=?", [*changes.values(), job_id])

    def requeue(self, job_id):
        with self.conn() as db:
            db.execute("""UPDATE jobs SET status='queued', error='', remote_id='', updated_at=?
            WHERE id=? AND status IN ('failed','cancelled','uncertain')""", (now(), job_id))

    def recover(self):
        # Reconcile remote IDs by polling first; no duplicate requests on restart.
        with self.conn() as db:
            db.execute("UPDATE jobs SET status='queued', updated_at=? WHERE status='running'", (now(),))

    def delete_job(self, job_id):
        with self.conn() as db:
            db.execute("DELETE FROM jobs WHERE id=? AND status!='running'", (job_id,))
