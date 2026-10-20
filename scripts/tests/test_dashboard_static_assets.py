"""Exercise design assets through the production HTTP handler."""
import http.client
import re
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from scripts.dashboard.handler import DashboardHandler

ROOT = Path(__file__).resolve().parents[2] / "dashboard"


class DashboardStaticAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_design_assets_have_correct_content_and_mime(self):
        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/tokens.css": ("tokens.css", "text/css; charset=utf-8"),
            "/gene-in.css": ("gene-in.css", "text/css; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/gene-in-symbol.png": ("gene-in-symbol.png", "image/png"),
            "/favicon.ico": ("gene-in-symbol.png", "image/png"),
        }
        fonts = re.findall(r'url\("(/vendor/fonts/[^"\)]+)"\)', (ROOT / "tokens.css").read_text(encoding="utf-8"))
        self.assertTrue(fonts)
        assets.update({font: (font.lstrip("/"), "font/woff2") for font in fonts})
        for url, (filename, mime) in assets.items():
            with self.subTest(url=url):
                status, headers, body = self.request(url + "?v=design")
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"], mime)
                self.assertEqual(body, (ROOT / filename).read_bytes())
                if mime.startswith("text/css"):
                    self.assertIn("no-store", headers["Cache-Control"])

    def test_invalid_font_paths_are_not_served(self):
        for suffix in (
            "missing.woff2", "", "../tokens.css", "../../tokens.css",
            "nested/Archivo-Variable-latin.woff2",
            "../fonts/Archivo-Variable-latin.woff2",
            "%2e%2e%2fArchivo-Variable-latin.woff2",
            "..\\Archivo-Variable-latin.woff2",
        ):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.request("/vendor/fonts/" + suffix)[0], 404)
