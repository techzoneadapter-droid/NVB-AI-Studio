import base64
import json
import tempfile
import unittest
from pathlib import Path
from nvb_studio.gateway import Gateway, GatewayError, build_payload


class GatewayTests(unittest.TestCase):
    def test_plain_generation_payload(self):
        job = {"prompt": "A portrait", "model": "model", "mode": "text", "refs_json": "[]"}
        body = build_payload(job)
        self.assertEqual(body["messages"][0]["content"], "A portrait")
        self.assertFalse(body["stream"])

    def test_frame_validation(self):
        job = {"prompt": "moving", "model": "veo", "mode": "first-last", "refs_json": "[]"}
        with self.assertRaises(GatewayError):
            build_payload(job)

    def test_reference_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "hero.png"
            png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            job = {"prompt": "hero", "model": "model", "mode": "reference",
                   "refs_json": json.dumps([str(png)])}
            data = build_payload(job)["messages"][0]["content"]
            self.assertEqual(len(data), 2)
            self.assertTrue(data[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_save_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nTEST").decode()
            response = {"choices": [{"message": {"content": "generated: " + data}}]}
            gateway = Gateway("http://127.0.0.1:8000", "test")
            path = Path(tmp) / "out.png"
            self.assertEqual(gateway.save_result(response, path), str(path))
            self.assertTrue(path.read_bytes().startswith(b"\x89PNG"))

    def test_untrusted_http_gateway(self):
        with self.assertRaises(GatewayError):
            Gateway("http://example.com:8000", "key")
