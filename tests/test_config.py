"""Settings: allowed origins for phone access, and the files the Home Screen app needs."""

import json
import os
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from season.config import _origins, load_settings
from season.interfaces.http.server import STATIC, WEB


class OriginsTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(_origins(""), ())
        self.assertEqual(_origins(" https://mac.tail1.ts.net/ , http://10.0.0.2:8765 "),
                         ("https://mac.tail1.ts.net", "http://10.0.0.2:8765"))

    def test_rejects_paths_and_bare_hosts(self):
        for bad in ("mac.tail1.ts.net", "https://mac.tail1.ts.net/board", "ftp://x"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _origins(bad)

    def test_extra_origins_are_allowed(self):
        old = os.environ.get("SEASON_ALLOWED_ORIGINS")
        os.environ["SEASON_ALLOWED_ORIGINS"] = "https://mac.tail1.ts.net"
        try:
            s = load_settings(Path("/nonexistent-season-home"))
        finally:
            if old is None:
                os.environ.pop("SEASON_ALLOWED_ORIGINS")
            else:
                os.environ["SEASON_ALLOWED_ORIGINS"] = old
        self.assertIn("https://mac.tail1.ts.net", s.allowed_origins)
        self.assertIn(s.base_url, s.allowed_origins)


class HomeScreenFilesTest(unittest.TestCase):
    def test_files_exist_and_manifest_points_at_them(self):
        for name, _ in STATIC.values():
            self.assertTrue((WEB / name).is_file(), name)
        manifest = json.loads((WEB / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["display"], "standalone")
        for icon in manifest["icons"]:
            self.assertIn(icon["src"], STATIC)

    def test_page_links_icon_and_manifest(self):
        html = (WEB / "board.html").read_text(encoding="utf-8")
        for needle in ('name="viewport"', 'rel="apple-touch-icon" href="/apple-touch-icon.png"',
                       'rel="manifest" href="/manifest.webmanifest"', "viewport-fit=cover"):
            self.assertIn(needle, html)


class ServedTest(unittest.TestCase):
    def test_static_routes(self):
        import socket
        import threading
        from http.server import ThreadingHTTPServer

        from season.interfaces.http.server import make_handler
        from tests.support import make_app

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        app, tmp = make_app(port=port)
        server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for path, (_, content_type) in STATIC.items():
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
                    self.assertEqual((r.status, r.headers["Content-Type"]), (200, content_type))
                    self.assertGreater(len(r.read()), 100)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/../.env")
            ctx.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
