import tempfile
import unittest
from pathlib import Path
from nvb_studio.store import Store, slug
from nvb_studio.importers import read_prompts


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "test.sqlite3")

    def test_projects_characters_and_tasks(self):
        p = self.store.create_project("Project A")
        c = self.store.create_character(p, "Hero", "Black hair", ["reference.png"])
        self.assertEqual(self.store.characters(p)[0]["id"], c)
        self.assertEqual(self.store.add_jobs(p, "image", "reference", "model", ["prompt 1", "prompt 2"], ["reference.png"]), 2)
        self.assertEqual([x["sequence"] for x in self.store.jobs(p)], [1, 2])
        first = self.store.jobs(p)[0]
        self.store.set_job(first["id"], status="running", remote_id="remote-123")
        self.store.recover()
        current = self.store.job(first["id"])
        self.assertEqual(current["status"], "queued")
        self.assertEqual(current["remote_id"], "remote-123")
        self.store.set_job(first["id"], status="failed")
        self.store.requeue(first["id"])
        self.assertEqual(self.store.job(first["id"])["status"], "queued")
        self.assertFalse(self.store.job(first["id"])["remote_id"])

    def test_prompts(self):
        path = Path(self.tmp.name) / "prompts.csv"
        path.write_text("prompt,description\nHello,hi\nWorld,bye\n", encoding="utf-8")
        self.assertEqual(read_prompts(path), ["Hello", "World"])
        xlsx = Path(self.tmp.name) / "prompts.xlsx"
        from openpyxl import Workbook
        book = Workbook()
        sheet = book.active
        sheet.append(["prompt"])
        sheet.append(["Scene one"])
        sheet.append(["Scene two"])
        book.save(xlsx)
        self.assertEqual(read_prompts(xlsx), ["Scene one", "Scene two"])

    def test_slug(self):
        self.assertTrue(slug("../../?:").strip("._"))
        self.assertNotIn("/", slug("A/B"))
