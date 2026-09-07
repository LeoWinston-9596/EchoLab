#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EchoLab 学习材料流水线 —— 一条命令,把任意英文视频变成精读级学习材料。

    python3 process.py 视频文件 --title "第1期"

产出:library/<编号>/data.json + 视频 + 封面,播放器直接可读。
"""
import argparse, json, os, pathlib, shutil, subprocess, sys, time, re

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
LIB = ROOT / "library"


def load_env():
    """读取同目录下的 .env(不依赖任何第三方库)。"""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def slugify(name):
    s = re.sub(r"[^\w一-鿿-]+", "-", name).strip("-")
    return s[:40] or "episode"


def make_poster(video, out_png, at=3.0):
    """封面图,失败就算了——没有封面不影响学习。"""
    from teco.tools import find_ffmpeg
    ff = find_ffmpeg()
    if not ff:
        return ""
    try:
        subprocess.run(
            [ff, "-y", "-ss", str(at), "-i", str(video), "-vframes", "1",
             "-vf", "scale=480:-1", str(out_png)],
            check=True, capture_output=True,
        )
        return out_png.name
    except Exception:
        return ""


def update_index():
    """重建 library/index.json —— 播放器靠它列出所有期数。"""
    eps = []
    for d in sorted(LIB.iterdir()):
        f = d / "data.json" if d.is_dir() else None
        if f and f.exists():
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
                eps.append({k: j.get(k) for k in
                            ("id", "title", "media", "poster", "duration", "topics",
                             "difficulty", "suggested_minutes", "wpm", "summary",
                             "n_segments", "n_cards", "created")})
            except Exception as e:
                print(f"  ! 跳过损坏的 {f}: {e}")
    eps.sort(key=lambda e: e.get("created") or "")
    (LIB / "index.json").write_text(
        json.dumps({"episodes": eps}, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(eps)


def main():
    ap = argparse.ArgumentParser(description="把英文视频转成精读级学习材料")
    ap.add_argument("video", nargs="?", help="视频或音频文件路径")
    ap.add_argument("--url", help="改从网址获取素材(先用 fetch.py 分析更稳妥)")
    ap.add_argument("--rss-index", type=int, default=0, help="订阅源里第几期")
    ap.add_argument("--force-download", action="store_true",
                    help="YouTube 也强制下载并跑语音识别(默认取字幕更快)")
    ap.add_argument("--no-fallback", action="store_true",
                    help="YouTube 取不到字幕时直接失败,不自动转为下载识别")
    ap.add_argument("--title", default=None, help="这一期的标题")
    ap.add_argument("--id", default=None, help="编号(默认由标题生成)")
    ap.add_argument("--llm", default="deepseek", choices=["deepseek", "kimi"],
                    help="用哪家的模型(默认 deepseek,单价更低)")
    ap.add_argument("--llm-model", default=None, help="指定具体模型名")
    ap.add_argument("--asr-model", default="small.en",
                    help="识别模型:tiny.en/base.en/small.en/medium.en。越大越准越慢")
    ap.add_argument("--chunk", type=int, default=220, help="每批送给模型的词数")
    ap.add_argument("--no-cache", action="store_true", help="不使用 LLM 缓存")
    ap.add_argument("--no-cards", action="store_true", help="只做字幕,跳过知识点卡片")
    ap.add_argument("--keep-media", action="store_true",
                    help="不复制视频,只在 data.json 里记录原路径(省磁盘)")
    args = ap.parse_args()

    load_env()
    from teco import asr, segment, cards as cards_mod, meta as meta_mod
    from teco.llm import LLM
    from teco.tools import report as env_report

    yt_id = None          # 非空表示走 YouTube 嵌入模式:不下载、不跑语音识别
    src = None
    if args.url:
        from teco.platforms import detect
        kind, info = detect(args.url)
        if kind == "youtube" and not args.force_download:
            yt_id = info["video_id"]
            print(f"YouTube 视频 {yt_id}:取官方字幕,不下载、不跑语音识别")
        else:
            from teco.ingest import ingest, IngestError
            print(f"从网址获取素材({kind}):{args.url}")
            try:
                src = pathlib.Path(ingest(args.url, ROOT / "downloads",
                                          rss_index=args.rss_index)).resolve()
            except IngestError as e:
                sys.exit(f"  {e}")
            print(f"  已下载:{src.name}\n")
    elif args.video:
        src = pathlib.Path(args.video).expanduser().resolve()
    else:
        sys.exit("请给一个文件路径,或用 --url 指定网址。")
    if src is not None and not src.exists():
        sys.exit(f"找不到文件:{src}")

    title = args.title or (src.stem if src else f"youtube-{yt_id}")
    ep_id = args.id or slugify(title)
    out_dir = LIB / ep_id
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print(f"\n=== 处理《{title}》 ===")
    wav = out_dir / "_audio.wav"

    if yt_id:
        # --- YouTube:取字幕代替语音识别,整条最慢的路直接跳过 ---
        from teco import captions
        print("\n[1/5] 获取官方字幕")
        words, cap_meta = None, {}
        try:
            words, cap_meta = captions.fetch_youtube(args.url)
        except RuntimeError as e:
            print(f"\n  {e}\n")
            if args.no_fallback:
                sys.exit("  已按 --no-fallback 停止。")
            # 取不到字幕不等于这个视频不能用:自动转为下载音频跑识别。
            # 慢一些、要花点钱,但用户的意图是「把这个视频做成学习材料」,
            # 不该因为一条路不通就整个失败。
            print("  自动改用下载音频 + 语音识别(会慢一些,并产生少量 API 费用)")
            print("  若不想要这个回退,下次加 --no-fallback\n")
            from teco.ingest import ingest, IngestError
            try:
                src = pathlib.Path(ingest(args.url, ROOT / "downloads",
                                          prefer_audio=True)).resolve()
            except IngestError as e2:
                sys.exit(f"  下载也失败了:{e2}")
            print(f"  已下载:{src.name}")
            yt_id = None
            out_dir = LIB / ep_id
            out_dir.mkdir(parents=True, exist_ok=True)
            print("\n环境自检:")
            print(env_report())
            print("\n[1/6] 提取音频")
            audio_in = asr.extract_audio(src, wav) or src
            print(f"[2/6] 语音识别({args.asr_model})")
            words, raw_segs, info = asr.transcribe(audio_in, model_size=args.asr_model)
            if not words:
                sys.exit("没有识别到任何语音。")
            print(f"      {len(words)} 个词 · 时长 {info['duration']}s")
        if yt_id and args.title is None and cap_meta.get("title"):
            title = cap_meta["title"][:60]
        if yt_id:
            info = {"language": "en",
                    "duration": round(cap_meta.get("duration")
                                      or (words[-1]["end"] if words else 0), 2)}
            print(f"      {len(words)} 个词 · 时长 {info['duration']}s"
                  f" · {'人工字幕' if cap_meta.get('kind')=='manual' else '自动字幕'}"
                  f"({cap_meta.get('format','')})")
    else:
        print("环境自检:")
        print(env_report())
        print("\n[1/6] 提取音频")
        audio_in = asr.extract_audio(src, wav) or src
        if audio_in is src:
            print("      未用 ffmpeg,改由内置解码器直接读取原文件")
        print(f"[2/6] 语音识别({args.asr_model})")
        words, raw_segs, info = asr.transcribe(audio_in, model_size=args.asr_model)
        if not words:
            sys.exit("没有识别到任何语音,请检查文件是否有英文人声。")
        print(f"      {len(words)} 个词 · 时长 {info['duration']}s")

    llm = LLM(args.llm, args.llm_model, use_cache=not args.no_cache)

    # 3) 语义群切分 + 翻译
    print("[3/6] 语义群切分 + 翻译")
    segs = segment.segment_and_translate(llm, words, chunk_size=args.chunk)
    print(f"      切成 {len(segs)} 个语义群")

    # 4) 整句 IPA(本地生成,零成本)
    print("[4/6] 生成 IPA 音标")
    from teco.ipa import to_ipa
    for s in segs:
        s["ipa"] = to_ipa(s["en"])

    # 5) 知识点卡片
    kept, dropped = [], []
    if not args.no_cards:
        print("[5/6] 抽取知识点卡片")
        raw_cards, mat_notes = cards_mod.extract_cards(llm, segs)
        wl = cards_mod.load_wordlists(ROOT / "wordlists")
        kept, dropped = cards_mod.verify_and_enrich(raw_cards, segs, wl)
        cover = len({c["seg"] for c in kept})
        nwords = sum(len(s["words"]) for s in segs)
        print(f"      {len(kept)} 张卡片 · 覆盖 {cover}/{len(segs)} 段"
              f"({cover*100//max(len(segs),1)}%) · 密度 {len(kept)/(nwords/100):.1f} 张/百词" +
              (f" · 剔除 {len(dropped)} 个原文中不存在的词条" if dropped else "") +
              (f" · 考级标签使用词表 {list(wl)}" if wl else ""))
        if cover * 3 < len(segs):
            print("      提示:覆盖率偏低。多半是素材本身口语特征少"
                  "(教学英语/念稿播报),换成自然对话类素材会明显改善")
        for n in dict.fromkeys(mat_notes):
            print(f"      素材说明:{n}")
    else:
        print("[5/6] 跳过知识点卡片")

    # 6) 元数据 + 落盘
    print("[6/6] 生成元数据并保存")
    m = meta_mod.build(llm, segs, words, info["duration"], kept)

    if yt_id:
        # 不落任何媒体文件,播放时嵌入官方播放器
        media_ref, poster = f"youtube:{yt_id}", ""
    elif args.keep_media:
        media_ref = src.as_uri()
        poster = ""
    else:
        media_name = "media" + src.suffix.lower()
        if not (out_dir / media_name).exists() or \
           (out_dir / media_name).stat().st_size != src.stat().st_size:
            shutil.copy2(src, out_dir / media_name)
        media_ref = media_name
        poster = make_poster(src, out_dir / "poster.jpg")

    low = asr.low_confidence_words(words) if not yt_id else []
    data = {
        "id": ep_id, "title": title,
        "media": media_ref, "poster": poster,
        "duration": info["duration"], "language": info["language"],
        "created": time.strftime("%Y-%m-%d"),
        "source_url": args.url or "",
        "n_segments": len(segs), "n_cards": len(kept),
        **m,
        "segments": segs,
        "cards": kept,
        "review": {                     # 给人工校对用的线索,不用通读全文
            "low_confidence_words": low[:200],
            "dropped_cards": dropped,
        },
    }
    (out_dir / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    wav.unlink(missing_ok=True)
    n = update_index()

    print(f"\n✓ 完成:library/{ep_id}/data.json")
    print(f"  难度 {'★'*m['difficulty']}{'☆'*(5-m['difficulty'])} · 语速 {m['wpm']} 词/分"
          f" · 建议学习 {m['suggested_minutes']} 分钟 · 主题 {'/'.join(m['topics']) or '—'}")
    print(f"  素材库现有 {n} 期 · 耗时 {time.time()-t0:.0f}s")
    print(f"  {llm.cost_report()}")
    if low:
        print(f"  提示:{len(low)} 个词识别把握较低,已列在 data.json 的 review 里供校对")
    print("\n  运行 python3 serve.py 打开播放器\n")


if __name__ == "__main__":
    main()
