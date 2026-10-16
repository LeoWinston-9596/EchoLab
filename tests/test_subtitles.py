"""HTML track association, subtitle parsing and graceful fallback."""
import pathlib
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from teco.subtitles import extract_tracks, parse_subtitles, fetch_track_captions

VTT = """WEBVTT

one
00:01.000 --> 00:03.000 align:start
<v Speaker>Hello &amp; welcome.</v>

two
00:04.000 --> 00:06.000
Hello &amp; welcome.
"""


class SubtitleTest(unittest.TestCase):
    def test_track_language_and_media_association(self):
        page = '''<video src="a.mp4"><track kind="captions" srclang="fr" src="fr.vtt">
          <track src="en.vtt" srclang="en-GB" kind="subtitles" /></video>
          <video><source src="b.mp4"><track src="other.vtt" srclang="en"></video>'''
        tracks = extract_tracks(page, "https://example.com/path/page", "https://example.com/path/a.mp4")
        self.assertEqual(tracks, [{"url": "https://example.com/path/en.vtt", "language": "en-gb"}])
        self.assertEqual(extract_tracks(page, "https://example.com/", "https://example.com/c.mp4"), [])
        self.assertEqual(extract_tracks('<video><track src="javascript:bad" srclang="en"></video>',
                                        "https://example.com/"), [])

    def test_vtt_entities_timing_and_real_repetition(self):
        words = parse_subtitles(VTT)
        self.assertEqual([w["w"] for w in words], ["Hello", "&", "welcome."]*2)
        self.assertEqual(words[0]["start"], 1)
        self.assertEqual(words[-1]["end"], 6)
        self.assertEqual([w["i"] for w in words], list(range(6)))
        self.assertEqual(parse_subtitles("WEBVTT\n\nNOTE ignored\n00:01.000 --> 00:02.000\nbad"), [])

    def test_srt_invalid_and_duplicate_cues(self):
        cue = "1\n00:00:01,000 --> 00:00:02,000\nRead this."
        self.assertEqual(len(parse_subtitles(cue+"\n\n"+cue)), 2)
        self.assertEqual(parse_subtitles("00:00:03,000 --> 00:00:01,000\nInvalid"), [])
        self.assertEqual(parse_subtitles("00:70:01.000 --> 00:70:03.000\nInvalid"), [])

    def test_bad_track_falls_back_to_next(self):
        session = Mock()
        bad, good = Mock(), Mock()
        bad.iter_content.return_value = [b"not captions"]
        good.iter_content.return_value = [VTT.encode()]
        session.get.return_value.__enter__ = Mock(side_effect=[bad, good])
        session.get.return_value.__exit__ = Mock(return_value=False)
        words, meta = fetch_track_captions([{"url": "bad"}, {"url": "good"}], session, verbose=False)
        self.assertEqual(len(words), 6)
        self.assertEqual(meta["url"], "good")


if __name__ == "__main__":
    unittest.main()
