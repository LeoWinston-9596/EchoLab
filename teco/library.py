# -*- coding: utf-8 -*-
"""素材库目录与索引 —— 「库里有哪些期、某个视频是不是已经做过」只在这里回答。

判重要放在一处的原因很实际:书签入队时要拦一次(点了才知道白点),
process.py 真正开跑前还要再拦一次(手动 --url、队列里的旧条目都绕得过第一道)。
两处若各写一份判断,迟早会不一致。
"""
import json, pathlib

LIB = pathlib.Path(__file__).resolve().parent.parent / "library"

# 写进 index.json 的字段。播放器和素材库页只读索引,不会去翻每一期的 data.json
INDEX_FIELDS = ("id", "title", "author", "media", "poster", "duration", "topics",
                "difficulty", "suggested_minutes", "wpm", "summary",
                "n_segments", "n_cards", "created", "source_url", "source_key")


def episodes():
    """遍历 library/,产出 (期数目录名, data.json 内容)。"""
    if not LIB.exists():
        return
    for d in sorted(LIB.iterdir()):
        if not d.is_dir():
            continue
        f = d / "data.json"
        if not f.exists():
            continue
        try:
            yield d.name, json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ! 跳过损坏的 {f}: {e}")


def key_of(data):
    """一期素材的来源标识。老数据里没有 source_key,就地从来源反推。"""
    from .platforms import source_key
    if data.get("source_key"):
        return data["source_key"]
    media = str(data.get("media") or "")
    if media.startswith("youtube:"):
        return media
    return source_key(data.get("source_url") or "")


def sources():
    """{来源标识: 期数目录名},只收有来源的(本地文件导入的没有)。

    优先读 index.json:它只有几十 KB,而逐期 data.json 加起来是几十 MB——
    书签每点一次都要判一次重,不能为此把整个库读一遍。
    """
    idx = LIB / "index.json"
    if idx.exists():
        try:
            eps = json.loads(idx.read_text(encoding="utf-8")).get("episodes") or []
            out = {}
            for e in eps:
                k = key_of(e)
                if k:
                    out.setdefault(k, e.get("id"))
            if out:
                return out
        except Exception:
            pass                        # 索引坏了就退回扫描,不让判重变成硬故障
    out = {}
    for ep_id, data in episodes():
        k = key_of(data)
        if k:
            out.setdefault(k, ep_id)
    return out


def find_by_source(key):
    """这个来源是不是已经做过了?做过就返回期数目录名。"""
    return sources().get(key) if key else None


def update_index():
    """重建 library/index.json。

    顺序就是两个页面的显示顺序:新的在前。播放器的「上一个/下一个素材」
    和素材库页的卡片顺序都直接用这个顺序,不再各自排各自的——
    以前素材库倒序、播放器正序,于是点「下一个」跳到的是列表里的上一个。
    """
    eps = [{k: data.get(k) for k in INDEX_FIELDS} for _, data in episodes()]
    eps.sort(key=lambda e: ((e.get("created") or ""), (e.get("id") or "").lower()),
             reverse=True)
    LIB.mkdir(parents=True, exist_ok=True)
    # 先写临时文件再改名。worker.py --watch 可能正好在同一刻重建索引,
    # 直接覆盖会让页面读到写了一半的 JSON
    tmp = LIB / "index.json.tmp"
    tmp.write_text(json.dumps({"episodes": eps}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(LIB / "index.json")
    return len(eps)
