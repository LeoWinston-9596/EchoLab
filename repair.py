#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修已经生成好的 data.json —— 只做不花 API 钱的部分,不重跑整条流水线。

    python repair.py library/1st/data.json   重算音标(本机 espeak)
    python repair.py --merge                 重新合并过短的语义群(纯本地)
    python repair.py --authors               回填作者(问一次 yt-dlp,不下载)

存在的意义是省钱:改了切分规则或补了新字段之后,已有的几十期不必重新
调用一次模型——凡是本机算得出来的,就地改掉。
"""
import argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from teco import library as lib

CJK = re.compile(r"[一-鿿぀-ヿ]")


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ 音标

def cmd_ipa(path):
    from teco.ipa import to_ipa, word_ipa
    from teco.tools import find_espeak
    if not find_espeak():
        sys.exit("找不到 espeak-ng,无法重算音标。")
    p = pathlib.Path(path)
    if not p.exists():
        sys.exit(f"找不到文件:{p}")
    d = json.loads(p.read_text(encoding="utf-8"))

    bad_before = sum(1 for s in d.get("segments", []) if CJK.search(s.get("ipa", "")))
    print(f"检查 {p}")
    print(f"  音标含乱码的段:{bad_before}/{len(d.get('segments', []))}")

    for s in d.get("segments", []):
        s["ipa"] = to_ipa(s["en"])
    for c in d.get("cards", []):
        c["ipa"] = word_ipa(c["term"])

    bad_after = sum(1 for s in d["segments"] if CJK.search(s.get("ipa", "")))
    backup = p.with_suffix(".json.bak")
    if not backup.exists():
        backup.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    _write(p, d)
    print(f"  已重算 {len(d['segments'])} 段 + {len(d.get('cards', []))} 张卡片的音标")
    print(f"  修复后仍含乱码:{bad_after}\n")


# ------------------------------------------------------------------ 重新合并语义群

def remerge(d):
    """按当前的合并规则重切一遍这一期。返回 (新段数, 原段数)。

    只做合并、不重新切分——切分要调模型。合并纯粹是本机计算,
    所以改了「多短算太短」的标准之后,老素材可以免费跟上。
    """
    from teco.segment import merge_short
    segs = d.get("segments") or []
    if len(segs) < 2:
        return len(segs), len(segs)

    # data.json 里没有全局词下标,用每段的 w0 还原出来
    by_i, ok = {}, True
    for s in segs:
        w0 = s.get("w0")
        if w0 is None or not s.get("words"):
            ok = False
            break
        for k, w in enumerate(s["words"]):
            by_i[w0 + k] = w
    if not ok:
        return len(segs), len(segs)

    merged = merge_short([{"s": s["w0"], "e": s["w1"], "zh": s.get("zh") or ""}
                          for s in segs], by_i)
    if len(merged) == len(segs):
        return len(segs), len(segs)

    remap, out = {}, []
    for sid, m in enumerate(merged):
        parts = [s for s in segs if m["s"] <= s["w0"] <= m["e"]]
        for s in parts:
            remap[s["id"]] = sid
        words = [w for s in parts for w in s["words"]]
        out.append({
            "id": sid, "w0": m["s"], "w1": m["e"],
            "start": words[0]["start"], "end": words[-1]["end"],
            "en": " ".join(s["en"] for s in parts).strip(),
            "zh": m["zh"],
            # 整段音标就是各段音标接起来,不必再跑一次 espeak
            "ipa": " ".join(s.get("ipa", "") for s in parts).strip(),
            "words": words,
        })
    d["segments"] = out
    d["n_segments"] = len(out)
    for c in d.get("cards", []):        # 词卡指向的段号跟着挪,否则「▶ 原句」会跳错
        if c.get("seg") in remap:
            c["seg"] = remap[c["seg"]]
    for dc in (d.get("review") or {}).get("dropped_cards") or []:
        if isinstance(dc, dict) and dc.get("seg") in remap:
            dc["seg"] = remap[dc["seg"]]
    return len(out), len(segs)


def cmd_merge(dry):
    from teco.segment import MIN_WORDS, MIN_SECS
    print(f"重新合并过短的语义群(标准:少于 {MIN_WORDS} 词 或 短于 {MIN_SECS} 秒)\n")
    total_before = total_after = touched = 0
    for ep_id, d in lib.episodes():
        before_short = _short_count(d)
        new, old = remerge(d)
        if new == old:
            print(f"  · {ep_id[:44]:46} {old:4} 段,无需改动")
            continue
        touched += 1
        total_before += old
        total_after += new
        after_short = _short_count(d)
        print(f"  ✓ {ep_id[:44]:46} {old:4} → {new:4} 段 · "
              f"过短段 {before_short} → {after_short}")
        if not dry:
            f = lib.LIB / ep_id / "data.json"
            bak = f.with_suffix(".json.bak")     # 段号会变,留一份好退回去
            if not bak.exists():
                bak.write_bytes(f.read_bytes())
            _write(f, d)
    print()
    if dry:
        print("  这是预演(--dry-run),没有写任何文件。\n")
        return
    if touched:
        n = lib.update_index()
        print(f"  改动了 {touched} 期,{total_before} → {total_after} 段,索引已重建({n} 期)")
        print("  注意:段号变了,之前收藏的句子和播放进度会对不上,重新收藏即可。\n")
    else:
        print("  全库都不需要改动。\n")


def _short_count(d):
    from teco.segment import MIN_WORDS, MIN_SECS
    n = 0
    for s in d.get("segments") or []:
        ws = s.get("words") or []
        dur = (ws[-1]["end"] - ws[0]["start"]) if ws else 0
        if len(ws) < MIN_WORDS or dur < MIN_SECS:
            n += 1
    return n


# ------------------------------------------------------------------ 回填作者

def _url_of(d):
    if d.get("source_url"):
        return d["source_url"]
    media = str(d.get("media") or "")
    if media.startswith("youtube:"):
        return "https://www.youtube.com/watch?v=" + media.split(":", 1)[1]
    return ""


def cmd_authors(dry):
    from teco.captions import fetch_uploader, has_ytdlp
    from teco.platforms import source_key
    if not has_ytdlp():
        sys.exit("回填作者需要 yt-dlp:pip install -U yt-dlp")
    todo = [(i, d) for i, d in lib.episodes() if not (d.get("author") or "").strip()]
    print(f"需要回填作者的:{len(todo)} 期\n")
    got = 0
    for ep_id, d in todo:
        url = _url_of(d)
        if not url:
            print(f"  - {ep_id[:44]:46} 没有来源网址,跳过")
            continue
        name = fetch_uploader(url)
        if not name:
            print(f"  - {ep_id[:44]:46} 查不到作者")
            continue
        d["author"] = name
        d.setdefault("source_url", url)
        d["source_key"] = d.get("source_key") or source_key(url)
        got += 1
        print(f"  ✓ {ep_id[:44]:46} {name}")
        if not dry:
            _write(lib.LIB / ep_id / "data.json", d)
    print()
    if dry:
        print("  这是预演(--dry-run),没有写任何文件。\n")
    elif got:
        n = lib.update_index()
        print(f"  回填了 {got} 期,索引已重建({n} 期)。刷新素材库页即可按作者筛选。\n")


def main():
    ap = argparse.ArgumentParser(description="修已生成的 data.json(不花 API 钱)")
    ap.add_argument("path", nargs="?", help="要重算音标的 data.json")
    ap.add_argument("--merge", action="store_true", help="全库重新合并过短的语义群")
    ap.add_argument("--authors", action="store_true", help="全库回填作者(用 yt-dlp 查)")
    ap.add_argument("--reindex", action="store_true", help="只重建 library/index.json")
    ap.add_argument("--dry-run", action="store_true", help="只看会改什么,不写文件")
    args = ap.parse_args()

    if args.merge:
        cmd_merge(args.dry_run)
    if args.authors:
        cmd_authors(args.dry_run)
    if args.reindex:
        print(f"索引已重建:{lib.update_index()} 期\n")
    if args.path:
        cmd_ipa(args.path)
    if not any((args.merge, args.authors, args.reindex, args.path)):
        ap.print_help()


if __name__ == "__main__":
    main()
