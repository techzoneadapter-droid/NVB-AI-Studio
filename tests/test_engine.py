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
