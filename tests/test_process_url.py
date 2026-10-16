"""URL-to-episode integration: real local HTTP, isolated storage, fake models."""
import contextlib
import functools
import http.server
import io
import json
import pathlib
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import process
from teco import asr, captions, ipa, library, llm, segment


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class URLPipelineTest(unittest.TestCase):
    def test_download_process_save_and_deduplicate(self):
        for mode in ("direct", "html-captions", "html-broken-captions"):
            with self.subTest(mode=mode):
                self.run_pipeline(mode)

    def run_pipeline(self, mode):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "library").mkdir()
            payload = b"fixture media: no decoder is needed for this test"
            (root / "sample.mp3").write_bytes(payload)
            (root / "page.html").write_text('<video src="sample.mp3">'
                '<track src="en.vtt" kind="captions" srclang="en"></video>', encoding="utf-8")
            (root / "en.vtt").write_text("WEBVTT\n\n00:00.000 --> 00:04.000\n"
                "These English captions replace speech recognition for this episode.\n"
                if mode == "html-captions" else "Malformed captions", encoding="utf-8")
            server = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0), functools.partial(QuietHandler, directory=tmp))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            source = "sample.mp3" if mode == "direct" else "page.html"
            url = f"http://127.0.0.1:{server.server_port}/{source}"
            words = [{"i": i, "w": w, "start": i*.4, "end": (i+1)*.4, "p": .99}
                     for i, w in enumerate("This test downloads media and saves a learning episode".split())]
            segs = [{"id": 0, "en": " ".join(w["w"] for w in words),
                     "zh": "Test translation", "start": 0, "end": 3.6, "words": words}]
            with contextlib.ExitStack() as stack:
                for obj, attr, value in [(process, "ROOT", root), (process, "LIB", root/"library"),
                                         (library, "LIB", root/"library")]:
                    stack.enter_context(patch.object(obj, attr, value))
                stack.enter_context(patch.object(sys, "argv", ["process.py", "--url", url,
                                    "--id", "integration", "--title", "URL integration", "--no-cards"]))
                stack.enter_context(patch.object(process, "make_poster", return_value=""))
                stack.enter_context(patch.object(asr, "extract_audio", return_value=None))
                transcribe = stack.enter_context(patch.object(asr, "transcribe", return_value=(
                    words, [], {"language": "en", "duration": 3.6})))
                stack.enter_context(patch.object(segment, "segment_and_translate", return_value=segs))
                stack.enter_context(patch.object(ipa, "to_ipa", return_value="test"))
                stack.enter_context(patch.object(captions, "fetch_uploader", return_value="Fixture author"))
                fake_llm = stack.enter_context(patch.object(llm, "LLM"))
                fake_llm.return_value.chat_json.return_value = {"topics": ["Testing"], "summary": "Fixture"}
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                process.main()
                data = json.loads((root/"library/integration/data.json").read_text(encoding="utf-8"))
                self.assertEqual(data["source_url"], url)
                self.assertEqual(data["transcript_source"], "html-track" if mode == "html-captions" else "asr")
                self.assertEqual(data["segments"], segs)
                self.assertEqual(data["author"], "Fixture author")
                self.assertEqual((root/"library/integration/media.mp3").read_bytes(), payload)
                index = json.loads((root/"library/index.json").read_text(encoding="utf-8"))
                self.assertEqual(index["episodes"][0]["id"], "integration")
                process.main()
                if mode == "html-captions":
                    transcribe.assert_not_called()
                    self.assertTrue(data["caption_track"]["url"].endswith("/en.vtt"))
                else:
                    transcribe.assert_called_once()


if __name__ == "__main__":
    unittest.main()
