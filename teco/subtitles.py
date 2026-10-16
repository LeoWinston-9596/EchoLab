"""English HTML subtitle tracks, with cue-based (approximate word) timing."""
import html
from html.parser import HTMLParser
import re
import urllib.parse
import requests

from .ingest import TIMEOUT, _session

MAX_CAPTION_BYTES = 2 * 1024 * 1024
TIMESTAMP = r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})"
CUE = re.compile(TIMESTAMP + r"\s*-->\s*" + TIMESTAMP)


def extract_tracks(page, base_url, media_url=None):
    """Keep tracks attached to the selected media element, not unrelated videos."""
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.groups = []
            self.current = None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag in ("video", "audio"):
                self.current = {"sources": [], "tracks": []}
                self.groups.append(self.current)
            if self.current is None:
                return
            src = urllib.parse.urljoin(base_url, attrs.get("src", ""))
            if urllib.parse.urlsplit(src).scheme not in ("http", "https") or not attrs.get("src"):
                return
            if tag in ("video", "audio", "source"):
                self.current["sources"].append(src)
            if tag == "track" and attrs.get("kind", "subtitles").lower() in ("captions", "subtitles"):
                lang = attrs.get("srclang", "").lower()
                if lang == "en" or lang.startswith("en-") or (
                        not lang and attrs.get("label", "").lower().startswith("english")):
                    self.current["tracks"].append({"url": src, "language": lang or "en"})

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

        def handle_endtag(self, tag):
            if tag in ("video", "audio"):
                self.current = None

    parser = Parser()
    parser.feed(page)
    tracks, seen = [], set()
    for group in parser.groups:
        if media_url and media_url not in group["sources"]:
            if len(parser.groups) != 1 or group["sources"]:
                continue
        for track in group["tracks"]:
            if track["url"] not in seen:
                tracks.append(track)
                seen.add(track["url"])
    return tracks


def parse_subtitles(text):
    """Read VTT/SRT; retain genuine repeated sentences at different times."""
    def seconds(parts):
        hours, minutes, secs, millis = parts
        if int(minutes) >= 60 or int(secs) >= 60:
            raise ValueError("Invalid subtitle timestamp")
        return int(hours or 0)*3600 + int(minutes)*60 + int(secs) + int(millis)/1000

    cues, seen = [], set()
    for block in re.split(r"\n\s*\n", text.lstrip("\ufeff").replace("\r", "")):
        lines = block.strip().splitlines()
        if not lines or lines[0].startswith(("NOTE", "STYLE", "REGION")):
            continue
        for i, line in enumerate(lines):
            match = CUE.search(line)
            if not match:
                continue
            try:
                start, end = seconds(match.groups()[:4]), seconds(match.groups()[4:])
            except ValueError:
                break
            body = html.unescape(re.sub(r"<[^>]*>", "", " ".join(lines[i+1:])))
            key = (start, end, body)
            if end > start and body.strip() and key not in seen:
                cues.append(key)
                seen.add(key)
            break
    words = []
    for start, end, body in sorted(cues):
        # Overlapping cue boundaries are clamped to keep a monotonic word sequence.
        start = max(start, words[-1]["end"] if words else 0)
        if end <= start:
            continue
        tokens = body.split()
        weight = sum(map(len, tokens))
        cursor = start
        for token in tokens:
            finish = cursor + (end-start)*len(token)/weight
            words.append({"i": len(words), "w": token, "start": round(cursor, 3),
                          "end": round(finish, 3), "p": 1.0})
            cursor = finish
    return words


def fetch_track_captions(tracks, session=None, verbose=True):
    """Try English tracks in document order. Fail softly so ASR remains available."""
    session = session or _session()
    for track in tracks:
        try:
            with session.get(track["url"], stream=True, timeout=TIMEOUT) as response:
                response.raise_for_status()
                payload = bytearray()
                for chunk in response.iter_content(1 << 15):
                    payload.extend(chunk)
                    if len(payload) > MAX_CAPTION_BYTES:
                        raise ValueError("Subtitle file exceeds size limit")
                words = parse_subtitles(payload.decode("utf-8-sig"))
                if words:
                    return words, {"url": track["url"], "timing": "cue-interpolated"}
                raise ValueError("No usable subtitle cues")
        except (ValueError, UnicodeError, requests.RequestException) as exc:
            if verbose:
                print(f"  Subtitle track unavailable; trying next source: {exc}")
    return None, {}
