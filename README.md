# EchoLab

English | [简体中文](README.zh-CN.md)

**Turn English video and audio into material you can listen to, shadow and review sentence by sentence.**

EchoLab is a local Python pipeline and browser-based learning player. It produces English–Chinese semantic subtitles, IPA pronunciation and source-validated vocabulary cards from local media or online links. Speech recognition runs locally; translation and card generation use a configured LLM API.

Originally built for a family member, the project separates learner-facing playback from installation and content processing. The interface supports **English and Chinese**, with a saved language preference shared across the library, player and bookmark setup page. Interface language does not change the bilingual learning content.

## Try it

Requires **Python 3.10+**. Run these commands from the repository root:

```bash
git clone https://github.com/LeoWinston-9596/EchoLab.git
cd EchoLab
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS / Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Optional system tools:

| Tool | Purpose |
| --- | --- |
| `espeak-ng` | Generate demo speech and local IPA |
| `ffmpeg` | Audio extraction, HLS merging and thumbnails; ASR can also decode supported formats through PyAV |
| `yt-dlp` | Retrieve YouTube captions and supported platform media; install separately with `python -m pip install -U yt-dlp` |

With `espeak-ng` installed, try the synthetic demo without an API key or ASR model download:

```bash
python demo.py
python serve.py --no-worker
```

Open [the library](http://localhost:8777/library.html). The demo demonstrates interaction, not real-world transcription quality. For normal use, `python serve.py` also starts the queue processor. Windows and macOS launchers are `start.bat` and `start.command`.

## Process content

Copy `.env.example` to `.env` and configure `DEEPSEEK_API_KEY`, or `MOONSHOT_API_KEY` when using `--llm kimi`. Never commit `.env`.

```bash
python process.py "path/to/video.mp4" --title "Ordering coffee"
python fetch.py "https://example.com/video"  # Inspect before downloading
python process.py --url "https://www.youtube.com/watch?v=VIDEO_ID"
python serve.py
```

The first local-ASR run downloads the selected model (default: `small.en`). Generated episodes live in `library/<episode-id>/`, with `data.json`, media and a thumbnail where applicable.

YouTube prefers existing English captions and embedded playback. If captions fail, processing falls back to media download and ASR; `--no-fallback` stops instead, and `--force-download` explicitly chooses ASR. Other inputs include media URLs, RSS/Atom enclosures, HTML media sources, HLS and separately installed `yt-dlp`.

To queue a link, run the server, open [bookmark setup](http://localhost:8777/setup), and drag the bookmark to your browser's bookmarks bar. Click it on a video page; the server processes the queue automatically. `python worker.py --watch` is an alternative standalone worker; do not start a second processor unnecessarily.

## Learning controls

- Click a subtitle to seek to its source; repeat a sentence or pause after each sentence for recall.
- Adjust speed and subtitle mode: bilingual, English, Chinese or IPA.
- Review words separately from lexical chunks: phrases, phrasal verbs, collocations, patterns and discourse markers.
- Jump from a vocabulary card to the original sentence. Save favourites and resume progress in the same browser.

See the [user guide](USER_GUIDE.md) for learner instructions.

## How it works

```text
Local/online media -> local word-timestamp ASR --+
                                               +-> semantic groups + translation -> IPA -> player
Existing captions -> timed word sequence -------+             |
                                                            cards -> source validation
```

The segmenter asks the model for **word-index ranges**, then reconstructs English text and timing from the original words. It repairs gaps, overlaps and incomplete coverage rather than trusting rewritten model text. Synchronisation still depends on source timing quality.

Cards undergo source checks, including common inflections and separated phrasal verbs. Unsupported entries are dropped and recorded. This validates provenance, not the correctness of every definition or translation. LLM requests are cached locally by provider and request content; different prompts or models can incur new calls. IPA uses local `espeak-ng` and a reusable lexicon.

## Review the code

| Entry | Responsibility |
| --- | --- |
| `process.py` | Download/transcribe, generate, validate and save an episode |
| `fetch.py`, `teco/ingest.py` | Inspect sources and retrieve media |
| `serve.py`, `teco/runner.py`, `worker.py` | HTTP media serving and recoverable processing queue |
| `library.html`, `player.html`, `i18n.js` | Browser UI and shared English/Chinese translations |
| `teco/asr.py`, `teco/captions.py` | Local ASR and YouTube captions |
| `teco/segment.py`, `teco/cards.py` | Segmentation, translation and card validation |
| `teco/llm.py`, `teco/ipa.py` | API calls, caching, usage estimates and pronunciation |

```bash
python tests/run_all.py
python .github/scripts/check_imports.py
python -m ruff check .
```

Offline tests do not call paid APIs or download ASR models. They verify program behaviour rather than translation quality. CI runs tests, selected bug-focused lint rules and import checks. Online ingestion design and the incremental implementation checklist are in [online-ingest.md](docs/online-ingest.md).

Useful options: `--llm deepseek|kimi`, `--llm-model NAME`, `--asr-model base.en`, `--no-cards`, `--no-cache`, `--force`, and `--min-words 8`. See `python process.py --help` for the full list.

## Boundaries and data

ASR is local, but model downloads and LLM processing require a network. Transcripts go to the selected LLM provider. Accuracy varies with audio and source captions; `data.json.review` lists low-confidence words and rejected cards, not every possible error. Runtime cost estimates can lag provider pricing.

Progress and favourites use browser local storage and do not sync across devices. The server binds to `0.0.0.0:8777` for trusted LAN use; it is not designed as a public multi-user service. Use content you are entitled to process; the project does not bypass paywalls or DRM. Platform extraction can break when upstream sites change.
