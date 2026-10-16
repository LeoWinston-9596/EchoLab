# Online ingestion

[Original Chinese notes](online-ingest.zh-CN.md)

## 1. Retrieval strategy

Prefer direct media URLs and RSS/Atom enclosures, then media exposed in HTML (`video`, `audio`, Open Graph and JSON-LD), HLS via ffmpeg, and finally a separately installed yt-dlp. Inspection (`fetch.py`) is separate from processing (`process.py --url`).

## 2. Pipeline contract

Ingestion returns a local media path. The processor creates the same `data.json` schema as local-file processing. YouTube captions are a separate fast path with embedded playback. Website subtitle tracks can provide a timed transcript without local ASR.

## 3. Scope

Only process material you are entitled to access. Dynamic players, authentication, platform restrictions and DRM are not solved by generic HTML extraction. Local tests use small HTTP fixtures instead of paid API calls or full media downloads.

## 4. Verification

Run `python tests/run_all.py`. Live podcast checks are documented separately with their actual dates and outcomes; they are not part of deterministic CI.

## 5. Next steps — easiest first

Each item is delivered in a separate commit with its regression tests.

- [x] Verify the existing one-command URL-to-learning-material path. `tests/test_process_url.py` exercises real local HTTP download, saved media/JSON/index and duplicate avoidance with isolated storage and fake models. Fixed non-default ports being removed from input URLs.
- [x] Validate real podcast feeds and handle encoding and very long titles. See [dated live results](podcast-validation.md) and `tests/test_rss.py`.
- [x] Select podcast episodes by fuzzy title as well as numeric index. Exact, partial, token and typo matches are supported; ambiguous matches list indexes instead of guessing.
- [x] Read English HTML `<track>` captions and bypass ASR when usable. Tracks are matched to the selected media element; VTT/SRT cue timing is interpolated within each cue. Missing/broken tracks fall back to ASR. `--force-download` forces ASR even when HTML captions exist.
- [x] Resume interrupted large HTTP downloads safely. Retry the same command: validated HTTP partials use Range + If-Range, restart if the source changes or ignores Range, and publish atomically. `tests/test_download.py` uses a deliberately interrupted local server.

Caption timing is approximate within each cue, and episode duration uses the last caption boundary on this path. The original English cues are retained; translation still uses the configured LLM. `data.json.transcript_source` and `caption_track` identify the source and timing precision.

Direct HTTP downloads retain hidden `.download-*.part` and `.json` files in the output directory after interruption. A strong ETag or Last-Modified is required to reuse those bytes. Without one, retry starts safely from zero. HLS and yt-dlp retain their own downloader behaviour; this resume implementation applies to the built-in HTTP downloader.

## 6. Usage

```bash
python fetch.py URL
python fetch.py FEED --index 2 --download
python fetch.py FEED --index "coffee conversation" --download
python process.py --url FEED --rss-index "coffee conversation"
python process.py --url URL --title "Episode one"
```
