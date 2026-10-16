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


def yt_cmd(exe, *args):
    """所有取 YouTube 字幕/元信息的调用都带 --no-playlist。

    分享链接经常带着 &list=。不加这个开关,yt-dlp 会按播放列表把每一集的
    字幕都抓回来,时长却只记第一集——库里就出现过 18 分钟视频配 112 分钟字幕。
    """
    return [exe, "--no-playlist", *args]


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
    return drop_rolling_repeats(words)


MIN_ECHO = 6          # 多少个词以上的紧邻重复才判定为字幕重播,见下面说明


def drop_rolling_repeats(words, flat=0.02, min_run=MIN_ECHO, max_run=15):
    """去掉自动字幕「滚动重播」产生的重复词。

    YouTube 的自动字幕是一屏一屏往上滚的,同一句话会被重复发好几次:
    一次是把当前这屏原样快照(所有词挤在同一时刻,逐词时长只有一两毫秒),
    一次是带真实时间戳的正片。结果正文里同一句连着出现两三遍。

    危害不只是正文重复。那些零时长词会把时间轴搅碎,语义群于是被切得又短又乱,
    跟读时字幕和人声完全对不上——实测有的短视频 66% 的词都是这么来的。

    两道处理:
      1. 快照那一份判据很硬(一毫秒的词 + 后面紧跟字字相同的正常版本),直接删;
      2. 剩下的重播两份时间戳都正常,只能靠「紧邻逐字重复」来认。
         门槛定在 6 个词:拿本地 26 期真实素材试过,3-5 个词会误伤
         连续的 [music] 标记和口语里真实的重复,6 个词以上则一例误伤都没有,
         同时该清的一个不落。
    """
    words = _drop_flat_echo(words, flat)
    words = _collapse_repeats(words, min_run, max_run)
    for idx, w in enumerate(words):
        w["i"] = idx                            # 下标要重排,后面全靠它对时间轴
    return words


def _drop_flat_echo(words, flat):
    """删掉「一毫秒快照」:整串词挤在同一时刻,后面紧跟着同样内容的正常版本。"""
    n = len(words)
    keep = [True] * n
    i = 0
    while i < n:
        if words[i]["end"] - words[i]["start"] >= flat:
            i += 1
            continue
        j = i                                   # [i, j) 是这一串零时长词
        while j < n and words[j]["end"] - words[j]["start"] < flat:
            j += 1
        span = j - i
        if (j + span <= n
                and words[j]["end"] - words[j]["start"] >= flat   # 后面那份是真的
                and [w["w"] for w in words[i:j]] == [w["w"] for w in words[j:j + span]]):
            for k in range(i, j):
                keep[k] = False
        i = j
    return words if all(keep) else [w for w, k in zip(words, keep) if k]


def _collapse_repeats(words, min_run, max_run):
    """紧邻的两份逐字相同的长片段,只留时间跨度更大(没被压扁)的那一份。"""
    out = list(words)
    i = 0
    while i < len(out):
        hit = 0
        for L in range(min(max_run, (len(out) - i) // 2), min_run - 1, -1):
            if all(out[i + k]["w"] == out[i + L + k]["w"] for k in range(L)):
                hit = L
                break
        if not hit:
            i += 1
            continue
        first = out[i + hit - 1]["end"] - out[i]["start"]
        second = out[i + 2 * hit - 1]["end"] - out[i + hit]["start"]
        drop = i if first <= second else i + hit
        del out[drop:drop + hit]
        # 不推进 i:同一处可能连着重播三遍
    return out


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


def fetch_uploader(url, timeout=90):
    """只问「这是谁发的」,给素材库按作者归类用。取不到就空着,不影响任何事。"""
    exe = has_ytdlp()
    if not exe:
        return ""
    from .platforms import canonical_url
    url = canonical_url(url) or url
    try:
        r = _run(yt_cmd(exe, "--skip-download", "--no-warnings",
                        "--print", "%(uploader,channel,uploader_id)s", url),
                 timeout=timeout)
    except Exception:
        return ""
    name = ((r.stdout or "").strip().splitlines() or [""])[0].strip()
    return "" if name in ("", "NA", "None") else name[:60]


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

    from .platforms import canonical_url
    url = canonical_url(url) or url

    errors = []
    with tempfile.TemporaryDirectory() as td:
        base = str(pathlib.Path(td) / "cap")
        meta = {}
        try:
            r = _run(yt_cmd(exe, "--skip-download", "--no-warnings", "--print",
                            "%(title)s\n%(duration)s\n%(uploader)s", url), timeout=90)
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
            r = _run(yt_cmd(exe, flag, "--skip-download", "--sub-format", fmt,
                            "--sub-langs", langspec, "-o", base, "--no-warnings", url))
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
            r = _run(yt_cmd(exe, "--list-subs", "--skip-download", "--no-warnings", url),
                     timeout=90)
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
