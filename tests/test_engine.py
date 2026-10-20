import unittest
from pathlib import Path
from unittest.mock import patch
from nvb_studio.engine import engine_root, chrome_executable, BASE_URL


class EngineTests(unittest.TestCase):
    def test_loopback_gateway(self):
        self.assertEqual(BASE_URL, "http://127.0.0.1:8000")

    def test_engine_directory(self):
        self.assertEqual(engine_root().name, "engine")

    def test_missing_chrome(self):
        with patch("pathlib.Path.is_file", return_value=False):
            self.assertIsNone(chrome_executable())


    def test_unpacked_extension_is_prepared_from_installer_without_backend(self):
        import json
        import tempfile
        import zipfile
        from unittest.mock import patch
        from nvb_studio.engine import EngineManager
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            payload = base / "engine-payload"
            payload.mkdir()
            manifest = {
                "name": "sub2gen Worker", "manifest_version": 3,
                "background": {"service_worker": "background.js"},
                "action": {"default_popup": "popup.html"},
            }
            names = ["manifest.json", "background.js", "popup.html", "popup.js",
                     "options.html", "options.js", "content.js", "stealth.js"]
            with zipfile.ZipFile(payload / "sub2gen.zip", "w") as zf:
                for name in names:
                    zf.writestr("apps/captcha-extension/dist/" + name,
                                json.dumps(manifest) if name == "manifest.json" else "test")
            with patch("nvb_studio.engine.engine_root", return_value=base / "user-data"), \
                 patch("nvb_studio.engine.bundled_path", return_value=payload):
                manager = EngineManager()
                folder = manager.extension_folder()
                self.assertTrue((folder / "manifest.json").is_file())
                self.assertTrue((folder / "background.js").is_file())
                self.assertEqual(folder, manager.extension_folder())
                self.assertIn("chrome-extension", str(folder))
