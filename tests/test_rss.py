"""Regression cases inspired by public podcast feeds; no external requests."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from teco.ingest import IngestError, parse_rss, safe_name


class FeedTest(unittest.TestCase):
    def test_declared_encoding_and_bad_length(self):
        xml = ('<?xml version="1.0" encoding="iso-8859-1"?>'
               '<rss><channel><item><title>Café &amp; conversation</title>'
               '<enclosure url="https://example.com/a.mp3" length="unknown"/>'
               '</item></channel></rss>').encode("iso-8859-1")
        ep = parse_rss(xml)[0]
        self.assertEqual(ep["title"], "Café & conversation")
        self.assertEqual(ep["length"], 0)

    def test_namespaces_nested_title_and_bom(self):
        xml = ('\ufeff<?xml version="1.0" encoding="utf-8"?>'
               '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
               '<title>Read <b>this</b> first</title>'
               '<link rel="enclosure" href="https://example.com/a.mp3"/>'
               '</entry></feed>').encode("utf-8")
        self.assertEqual(parse_rss(xml)[0]["title"], "Read this first")

    def test_long_titles_unicode_and_collisions(self):
        for title in ("🎧" * 200, "Learning " * 200, "中" * 200):
            name = safe_name(title)
            self.assertLessEqual(len(name), 80)
            self.assertLessEqual(len(name.encode("utf-8")), 180)
            self.assertNotEqual(name, safe_name(title + "different"))
            self.assertEqual(name, safe_name(title))
        self.assertEqual(safe_name("CON"), "_CON")
        self.assertEqual(safe_name("LPT1.txt"), "_LPT1.txt")

    def test_invalid_feed(self):
        for xml in (b"not xml", b"<rss><channel/></rss>"):
            with self.assertRaises(IngestError):
                parse_rss(xml)


if __name__ == "__main__":
    unittest.main()
