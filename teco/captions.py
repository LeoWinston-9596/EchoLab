# -*- coding: utf-8 -*-
"""YouTube 字幕获取与解析 —— 这条路能整个跳过语音识别。

为什么值得单独做:
  · 语音识别是全流程最慢的一步(几分钟),取字幕只要几秒;
  · 自动生成的字幕在 json3 格式下【自带词级时间戳】,
    正是语义群切分需要的东西,精度不输我们自己跑的识别;
  · 不产生任何本地媒体文件。

用 yt-dlp 只取字幕(--skip-download),不下载视频本身。
"""
import json, re, subprocess, shutil, tempfile, pathlib, glob, os


def has_ytdlp():
    return shutil.which("yt-dlp") or shutil.which("youtube-dl")


def parse_json3(data):
    """把 YouTube 的 json3 字幕解析成词序列。

    json3 的结构是:events[] 里每条有 tStartMs,其 segs[] 是一个个词片段,
    各自带 tOffsetMs(相对该 event 起点的偏移)。这就是词级时间戳的来源。
    返回 [{i, w, start, end, p}],与语音识别的输出格式完全一致,
    所以下游的切分、翻译、卡片一行代码都不用改。
    """
    if isinstance(data, (str, bytes)):
        data = json.loads(data)
    words = []
    for ev in data.get("events") or []:
        t0 = ev.get("tStartMs")
        segs = ev.get("segs")
        if t0 is None or not segs:
            continue
        for sg in segs:
            txt = (sg.get("utf8") or "").strip()
            if not txt or txt == "\n":
                continue
            start = (t0 + (sg.get("tOffsetMs") or 0)) / 1000.0
            words.append({"i": len(words), "w": txt,
                          "start": round(start, 3), "end": None, "p": 1.0})
    if not words:
        return []
    # json3 只给起点,结束时间用下一个词的起点回填;最后一个词按经验给 0.4s
    for a, b in zip(words, words[1:]):
        a["end"] = round(min(b["start"], a["start"] + 2.0), 3)
    last = words[-1]
    last["end"] = round(last["start"] + 0.4, 3)
    # 极少数情况下时间戳会乱序,做一次单调修正
    for a, b in zip(words, words[1:]):
        if b["start"] < a["start"]:
            b["start"] = a["start"]
        if a["end"] < a["start"]:
            a["end"] = a["start"] + 0.1
    return words


VTT_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*"
                    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})")
VTT_TAG = re.compile(r"<[^>]+>")


def _secs(h, m, sec, ms):
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000.0


def parse_vtt(text):
    """解析 vtt / srt 字幕。

    这类格式只有句级时间戳,没有词级。做法是:句子的起止时间是真实的,
    句内按词长比例分摊。句子边界准确,词位置近似——对切分和跳转足够用,
    总比因为拿不到 json3 就整个失败要好。
    """
    words, cues = [], []
    lines = text.replace("\r", "").split("\n")
    i = 0
    while i < len(lines):
        m = VTT_TS.search(lines[i])
        if not m:
            i += 1
            continue
        t0 = _secs(*m.groups()[:4]); t1 = _secs(*m.groups()[4:])
        i += 1
        buf = []
        while i < len(lines) and lines[i].strip() and not VTT_TS.search(lines[i]):
            buf.append(VTT_TAG.sub("", lines[i]))
            i += 1
        txt = " ".join(buf).strip()
        if txt and t1 > t0:
            cues.append((t0, t1, txt))

    seen = set()
    for t0, t1, txt in cues:
        if txt in seen:          # 自动字幕的滚动效果会重复上一行,去掉
            continue
        seen.add(txt)
        toks = txt.split()
        if not toks:
            continue
        total = sum(len(x) for x in toks) or 1
        acc = t0
        for tok in toks:
            span = (t1 - t0) * len(tok) / total
            words.append({"i": len(words), "w": tok,
                          "start": round(acc, 3), "end": round(acc + span, 3), "p": 1.0})
            acc += span
    return words


def _run(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def fetch_youtube(url, langs=("en", "en-US", "en-GB"), verbose=True):
    """取 YouTube 字幕。优先人工字幕,再退到自动生成;json3 拿不到就用 vtt。

    返回 (words, meta)。meta 含 title / duration / kind / format。
    """
    exe = has_ytdlp()
    if not exe:
        raise RuntimeError(
            "取 YouTube 字幕需要 yt-dlp。请先安装:\n"
            "    pip install -U yt-dlp\n"
            "这里只取字幕,不下载视频(--skip-download)。")

    errors = []
    with tempfile.TemporaryDirectory() as td:
        base = str(pathlib.Path(td) / "cap")
        meta = {}
        try:
            r = _run([exe, "--skip-download", "--no-warnings", "--print",
                      "%(title)s\n%(duration)s\n%(uploader)s", url], timeout=90)
            parts = (r.stdout or "").strip().split("\n")
            if len(parts) >= 2 and parts[0]:
                meta["title"] = parts[0].strip()
                try:
                    meta["duration"] = float(parts[1])
                except ValueError:
                    pass
                if len(parts) >= 3:
                    meta["uploader"] = parts[2].strip()
            elif r.stderr:
                errors.append(("取视频信息", r.stderr.strip()[-500:]))
        except Exception as e:
            errors.append(("取视频信息", str(e)))

        langspec = ",".join(langs) + ",en.*"
        attempts = [
            ("--write-subs", "json3", "manual"),
            ("--write-auto-subs", "json3", "auto"),
            ("--write-subs", "vtt", "manual"),
            ("--write-auto-subs", "vtt", "auto"),
        ]
        for flag, fmt, kind in attempts:
            label = f"{'人工' if kind=='manual' else '自动'}字幕 · {fmt}"
            if verbose:
                print(f"  · 尝试{label}")
            r = _run([exe, flag, "--skip-download", "--sub-format", fmt,
                      "--sub-langs", langspec, "-o", base, "--no-warnings", url])
            if r.returncode != 0 and r.stderr:
                errors.append((label, r.stderr.strip()[-500:]))
            files = sorted(glob.glob(f"{base}*.{fmt}"))
            for f in files:
                raw = pathlib.Path(f).read_text(encoding="utf-8", errors="replace")
                words = parse_json3(raw) if fmt == "json3" else parse_vtt(raw)
                if words:
                    meta["kind"], meta["format"] = kind, fmt
                    meta["sub_file"] = os.path.basename(f)
                    if verbose:
                        note = ("含词级时间戳" if fmt == "json3"
                                else "句级时间戳,词位置按比例分摊")
                        print(f"    拿到 {len(words)} 个词({label},{note})")
                    return words, meta
                os.remove(f)

        # 全都拿不到:把 yt-dlp 到底说了什么如实呈上,不要笼统地说「没有字幕」
        if verbose:
            print("  · 都没拿到,查一下这个视频到底有哪些字幕")
        listing = ""
        try:
            r = _run([exe, "--list-subs", "--skip-download", "--no-warnings", url], timeout=90)
            listing = (r.stdout or "").strip()[-1200:]
            if r.returncode != 0 and r.stderr:
                errors.append(("--list-subs", r.stderr.strip()[-500:]))
        except Exception as e:
            errors.append(("--list-subs", str(e)))

    msg = ["取不到这个视频的英文字幕。"]
    if listing:
        msg.append("\nyt-dlp 报告的可用字幕:\n" + listing)
    if errors:
        msg.append("\nyt-dlp 的报错(最后 500 字):")
        for where, err in errors[-3:]:
            msg.append(f"  [{where}] {err}")
    msg.append(
        "\n常见原因与对策:\n"
        "  · yt-dlp 版本旧,YouTube 一变就失效  ->  pip install -U yt-dlp\n"
        "  · 提示 Sign in to confirm you're not a bot  ->  加 --cookies-from-browser chrome\n"
        "  · 这个视频确实没有英文字幕(比如只有中文,或作者关了字幕)\n"
        "改用下载音频跑语音识别:process.py 加 --force-download")
    raise RuntimeError("\n".join(msg))
