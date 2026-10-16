"""Real local HTTP regressions for interruption, Range and atomic publishing."""
import hashlib
import http.server
import json
import pathlib
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from teco import ingest

PAYLOAD = bytes(range(256)) * 1024


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.mode = "resume"
        self.calls = []
        self.drop = True
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                owner.calls.append(dict(self.headers))
                requested = self.headers.get("Range")
                offset = int(requested.split("=")[1].split("-")[0]) if requested else 0
                etag = '"v2"' if owner.mode == "changed" and requested else '"v1"'
                body = PAYLOAD
                status = 200
                extra = {}
                if requested and owner.mode in ("resume", "invalid", "complete"):
                    if offset == len(PAYLOAD):
                        status, body = 416, b""
                        extra["Content-Range"] = f"bytes */{len(PAYLOAD)}"
                    else:
                        status, body = 206, PAYLOAD[offset:]
                        start = offset + 1 if owner.mode == "invalid" else offset
                        extra["Content-Range"] = f"bytes {start}-{len(PAYLOAD)-1}/{len(PAYLOAD)}"
                self.send_response(status)
                self.send_header("Content-Type", "audio/mpeg")
                if owner.mode != "no-validator":
                    self.send_header("ETag", etag)
                self.send_header("Content-Length", str(len(body)))
                for key, value in extra.items():
                    self.send_header(key, value)
                self.end_headers()
                if owner.drop:
                    owner.drop = False
                    self.wfile.write(body[:65536])
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                else:
                    try:
                        self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}/episode.mp3"

    def interrupt(self):
        with self.assertRaises(ingest.IngestError):
            ingest.download(self.url, self.root)
        partials = list(self.root.glob("*.part"))
        self.assertEqual(len(partials), 1)
        self.assertEqual(partials[0].stat().st_size, 65536)

    def test_resume_and_atomic_publish(self):
        dest = self.root / "episode.mp3"
        dest.write_bytes(b"previous complete version")
        self.interrupt()
        self.assertEqual(dest.read_bytes(), b"previous complete version")
        progress = []
        path = ingest.download(self.url, self.root, on_progress=lambda n, total: progress.append((n, total)))
        self.assertEqual(path.read_bytes(), PAYLOAD)
        self.assertEqual(self.calls[-1]["Range"], "bytes=65536-")
        self.assertEqual(self.calls[-1]["If-Range"], '"v1"')
        self.assertEqual(progress[-1], (len(PAYLOAD), len(PAYLOAD)))
        self.assertFalse(list(self.root.glob("*.part")))
        self.assertFalse(list(self.root.glob("*.json")))

    def test_changed_or_ignored_range_restarts_without_append(self):
        for mode in ("changed", "ignore", "invalid"):
            with self.subTest(mode=mode):
                self.drop, self.mode = True, mode
                self.interrupt()
                path = ingest.download(self.url, self.root)
                self.assertEqual(path.read_bytes(), PAYLOAD)

    def test_no_validator_restarts_safely(self):
        self.mode = "no-validator"
        self.interrupt()
        self.assertEqual(ingest.download(self.url, self.root).read_bytes(), PAYLOAD)
        self.assertNotIn("Range", self.calls[-1])

    def test_complete_partial_416_is_promoted(self):
        self.drop, self.mode = False, "complete"
        key = hashlib.sha256(self.url.encode()).hexdigest()[:24]
        (self.root/f".download-{key}.part").write_bytes(PAYLOAD)
        (self.root/f".download-{key}.json").write_text(json.dumps({
            "url": self.url, "validator_header": "ETag", "validator": '"v1"',
            "content_type": "audio/mpeg"}), encoding="utf-8")
        self.assertEqual(ingest.download(self.url, self.root).read_bytes(), PAYLOAD)

    def test_size_limit_removes_partial_not_finished_file(self):
        self.drop = False
        dest = self.root/"episode.mp3"
        dest.write_bytes(b"keep me")
        with patch.object(ingest, "MAX_BYTES", 100), self.assertRaises(ingest.IngestError):
            ingest.download(self.url, self.root)
        self.assertEqual(dest.read_bytes(), b"keep me")
        self.assertFalse(list(self.root.glob("*.part")))


if __name__ == "__main__":
    unittest.main()
