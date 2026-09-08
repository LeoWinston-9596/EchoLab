# -*- coding: utf-8 -*-
"""收件箱:书签栏一键丢进来的网址,先排队,再逐个处理。

刻意做成「先入队、后处理」而不是「点一下就开始跑」:
处理一个视频要几十秒到几分钟,浏览器那一下必须立刻返回,
否则你在刷视频的手感就断了。
"""
import json, pathlib, secrets, time, threading

DIR = pathlib.Path(__file__).resolve().parent.parent / ".queue"
QUEUE = DIR / "queue.json"
TOKEN = DIR / "token.txt"
_lock = threading.Lock()


def get_token():
    """本机令牌。书签里带着它,防止任意网页都能往你的队列里塞东西。"""
    DIR.mkdir(exist_ok=True)
    if not TOKEN.exists():
        TOKEN.write_text(secrets.token_urlsafe(18), encoding="utf-8")
    return TOKEN.read_text(encoding="utf-8").strip()


def _load():
    if not QUEUE.exists():
        return []
    try:
        return json.loads(QUEUE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items):
    DIR.mkdir(exist_ok=True)
    QUEUE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def add(url, title=""):
    """入队。

    判重按「是哪个视频」而不是按链接字符串:同一期在 YouTube 上可能是
    youtu.be 短链、/shorts/、或带 &t=100s 的分享链接,字符串各不相同。
    已经在库里的更要当场拦下——否则要等到 worker 跑起来才发现白花了钱。
    """
    from .platforms import describe, source_key
    from . import library
    key = source_key(url)
    with _lock:
        items = _load()
        for it in items:
            if (it.get("key") or source_key(it.get("url", ""))) == key \
               and it["status"] in ("待处理", "处理中", "已完成"):
                return {"ok": True, "duplicate": True,
                        "message": f"已经在队列里了({it['status']})"}
        done = library.find_by_source(key)
        if done:
            return {"ok": True, "duplicate": True,
                    "message": f"这个视频已经做过了,直接在播放器里看「{done}」"}
        kind, _, plan = describe(url)
        items.append({
            "id": f"q{int(time.time()*1000)%100000000}",
            "url": url, "key": key, "title": title, "platform": kind, "plan": plan,
            "status": "待处理", "added": time.strftime("%Y-%m-%d %H:%M"),
            "error": "", "episode": "",
        })
        _save(items)
        n = sum(1 for i in items if i["status"] == "待处理")
        return {"ok": True, "platform": kind, "plan": plan,
                "message": f"已加入队列(第 {n} 个待处理)"}


def list_all():
    return _load()


def take_next():
    """取一个待处理的,标记为处理中。"""
    with _lock:
        items = _load()
        for it in items:
            if it["status"] == "待处理":
                it["status"] = "处理中"
                _save(items)
                return it
    return None


def update(qid, **fields):
    with _lock:
        items = _load()
        for it in items:
            if it["id"] == qid:
                it.update(fields)
        _save(items)


def summary():
    """各状态各有多少。启动时打印,让队列状态一眼可见。"""
    from collections import Counter
    return Counter(i["status"] for i in _load())


def requeue_failed():
    """把失败的重新放回待处理。改了代码之后想重试,不必再去浏览器点一次书签。"""
    with _lock:
        items = _load()
        n = 0
        for it in items:
            if it["status"] == "失败":
                it["status"], it["error"] = "待处理", ""
                n += 1
        _save(items)
        return n


def clear_done():
    with _lock:
        items = [i for i in _load() if i["status"] not in ("已完成", "已跳过")]
        _save(items)
        return len(items)
