#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给一个网址,看看里面有什么可用的媒体 —— 先看后下,不盲目抓。

    python fetch.py <网址>              只分析,列出找到的东西
    python fetch.py <网址> --download   确认无误后再下载
    python fetch.py <订阅源> --index 2  下载订阅源里的第 3 期

合规提示:本工具只取回公开可访问的媒体地址,不绕过付费墙、登录态或 DRM。
目标网站的服务条款与内容版权由使用者自行负责。
"""
import argparse, pathlib, sys, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from teco.ingest import (parse_rss, extract_from_page, looks_like_media,
                         head_content_type, download, download_hls, via_ytdlp,
                         has_ytdlp, _session, IngestError, TIMEOUT)


def human(n):
    return f"{n/1e6:.1f} MB" if n else "未知大小"


def youtube_report(url):
    """YouTube 专用诊断:这个视频到底有哪些字幕、yt-dlp 说了什么。"""
    from teco.captions import has_ytdlp, _run
    exe = has_ytdlp()
    if not exe:
        print("  未安装 yt-dlp。YouTube 取字幕需要它:pip install -U yt-dlp")
        return
    r = _run([exe, "--version"], timeout=30)
    print(f"  yt-dlp 版本:{(r.stdout or '').strip() or '未知'}")
    print("  查询可用字幕中…\n")
    r = _run([exe, "--list-subs", "--skip-download", "--no-warnings", url], timeout=120)
    out = (r.stdout or "").strip()
    print("\n".join("  " + l for l in out.split("\n")[:40]) if out else "  (无输出)")
    if r.returncode != 0 and r.stderr:
        print("\n  yt-dlp 报错:")
        print("\n".join("    " + l for l in r.stderr.strip().split("\n")[-6:]))
        print("\n  版本旧是最常见的原因,先试:pip install -U yt-dlp")
        print("  若提示 Sign in to confirm you're not a bot,")
        print("  可加 --cookies-from-browser chrome(需自行判断是否合适)")


def analyze(url, verbose=True):
    """返回 (类型, 详情)。只读不写。"""
    s = _session()
    if looks_like_media(url):
        return "direct", [{"url": url, "source": "地址后缀即媒体格式"}]

    ctype, final = head_content_type(url, s)
    if ctype.startswith(("audio/", "video/")):
        return "direct", [{"url": final, "source": f"响应头 {ctype}"}]

    if "xml" in ctype or url.rstrip("/").endswith((".xml", "/rss", "/feed")):
        return "rss", parse_rss(s.get(url, timeout=TIMEOUT).text)

    try:
        page = s.get(url, timeout=TIMEOUT).text
    except Exception as e:
        raise IngestError(f"打不开这个网址:{e}")
    cands = extract_from_page(page, url)
    return ("page" if cands else "opaque"), cands


def main():
    ap = argparse.ArgumentParser(description="解析网址里的媒体")
    ap.add_argument("url")
    ap.add_argument("--download", action="store_true", help="确认后下载")
    ap.add_argument("--index", type=int, default=0, help="订阅源里第几期(从 0 开始)")
    ap.add_argument("--out", default="downloads", help="下载到哪个目录")
    ap.add_argument("--video", action="store_true", help="yt-dlp 兜底时保留画面(默认只要音频)")
    a = ap.parse_args()

    print(f"\n分析:{a.url}\n")
    from teco.platforms import describe
    kind0, info0, plan0 = describe(a.url)
    if kind0 in ("youtube", "youtube_unknown"):
        print(f"  平台:YouTube · {plan0}")
        if info0.get("video_id"):
            print(f"  视频 ID:{info0['video_id']}\n")
        youtube_report(a.url)
        print("\n  取字幕并加工:python process.py --url <网址> --title \"第N期\"")
        print("  没有字幕时会自动改用下载识别;想禁用加 --no-fallback\n")
        return
    try:
        kind, items = analyze(a.url)
    except IngestError as e:
        sys.exit(f"  {e}")

    if kind == "direct":
        print(f"  类型:媒体直链({items[0]['source']})")
        print(f"  地址:{items[0]['url']}")
    elif kind == "rss":
        print(f"  类型:播客订阅源,共 {len(items)} 期(播客的 enclosure 本就供下载)\n")
        for i, e in enumerate(items[:12]):
            mark = "→" if i == a.index else " "
            print(f"  {mark} [{i}] {e['title'][:46]:48s} {human(e['length'])}  {e['published'][:16]}")
        if len(items) > 12:
            print(f"     …… 还有 {len(items)-12} 期")
        print(f"\n  用 --index N 选择,默认第 {a.index} 期")
    elif kind == "page":
        print(f"  类型:网页,找到 {len(items)} 个候选地址(按可靠度排序)\n")
        for i, c in enumerate(items[:8]):
            print(f"   [{i}] {c['source']}")
            print(f"       {c['url'][:100]}")
    else:
        print("  类型:无法直接解析")
        print("  页面里没有暴露媒体地址,通常是播放器在运行时动态拿的。")
        print(f"  兜底方案 yt-dlp:{'已安装,可用 --download 尝试' if has_ytdlp() else '未安装'}")
        if not has_ytdlp():
            print("  如你确认有权获取该内容,可自行 pip install yt-dlp 后重试。")

    if not a.download:
        print("\n  (只做了分析,没有下载。加 --download 才会真的下)\n")
        return

    print("\n开始下载…")
    try:
        if kind == "direct":
            p = download(items[0]["url"], a.out)
        elif kind == "rss":
            ep = items[a.index]
            from teco.ingest import safe_name
            p = download(ep["url"], a.out, name=safe_name(ep["title"]))
        elif kind == "page":
            p = None
            for c in items[:4]:
                try:
                    p = (download_hls(c["url"], a.out) if ".m3u8" in c["url"].lower()
                         else download(c["url"], a.out))
                    break
                except Exception as e:
                    print(f"  候选失败({c['source']}):{e}")
            if p is None:
                raise IngestError("所有候选都下载失败")
        else:
            p = via_ytdlp(a.url, a.out, audio_only=not a.video)
    except IngestError as e:
        sys.exit(f"  {e}")
    except Exception as e:
        sys.exit(f"  下载失败:{type(e).__name__}: {e}")

    size = pathlib.Path(p).stat().st_size
    print(f"\n✓ 已保存:{p}  ({human(size)})")
    print(f"\n  接着处理成学习材料:")
    print(f'    python process.py "{p}" --title "第N期"\n')


if __name__ == "__main__":
    main()
