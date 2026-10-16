# Live podcast validation

Checked on **2026-10-16**. Only feed XML was requested; audio was not downloaded and no model API was called.

| Public feed | HTTP | Downloadable entries | Longest title |
| --- | --- | --- | --- |
| [BBC 6 Minute English](https://podcasts.files.bbci.co.uk/p02pc9tn.rss) | 200 | 345 | 57 characters |
| [NPR Planet Money](https://feeds.npr.org/510289/podcast.xml) | 200 | 355 | 82 characters |

Both feeds parsed successfully and all derived filenames fit the configured character and UTF-8 byte limits. The NPR feed provides a real case exceeding the old 80-character truncation threshold. Long names now receive a stable hash suffix to distinguish otherwise identical prefixes. Windows device names are protected.

Raw XML bytes now reach the XML parser, allowing its declared encoding to take precedence over HTTP text guesses. Invalid enclosure lengths are treated as unknown. `tests/test_rss.py` covers declared Latin-1, UTF-8 BOMs, namespaces, nested title markup, malformed feeds, Unicode byte limits and filename collisions without live network access.

Feed counts and titles change over time. These results establish retrieval and parsing on the date above, not permanent platform compatibility or transcription quality.
