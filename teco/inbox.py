# -*- coding: utf-8 -*-
"""收件箱:书签栏一键丢进来的网址,先排队,再逐个处理。

点书签那一下必须立刻返回——处理一个视频要几十秒到几分钟,
浏览器那一下如果等解析跑完,刷视频的手感就断了。
真正开跑由 serve.py 里的后台循环负责,入队时会叫醒它,通常下一秒就开始。
"""
import json, os, pathlib, secrets, time, threading, atexit

DIR = pathlib.Path(__file__).resolve().parent.parent / ".queue"
QUEUE = DIR / "queue.json"
TOKEN = DIR / "token.txt"
LOCK = DIR / "runner.lock"
_lock = threading.Lock()
_wake = threading.Event()


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


def notify():
    """叫醒正在 wait() 的解析循环。入队后立刻跑,不必干等到下一个轮询点。"""
    _wake.set()


def wait(timeout):
    _wake.wait(timeout)
    _wake.clear()


def add(url, title=""):
    """入队。

    判重按「是哪个视频」而不是按链接字符串:同一期在 YouTube 上可能是
    youtu.be 短链、/shorts/、或带 &t=100s 的分享链接,字符串各不相同。
    已经在库里的更要当场拦下——否则要等到 worker 跑起来才发现白花了钱。
    """
    from .platforms import describe, source_key, canonical_url
    from . import library
    url = canonical_url(url) or url
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
    notify()
    return {"ok": True, "platform": kind, "plan": plan,
            "message": f"已加入队列,即将自动解析(第 {n} 个)"}


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
    if n:
        notify()
    return n


def requeue_one(qid):
    """素材库页上点「重试」用。只动这一条,别把别的失败项也带上。"""
    with _lock:
        items = _load()
        for it in items:
            if it["id"] == qid and it["status"] in ("失败", "已跳过"):
                it["status"], it["error"] = "待处理", ""
                _save(items)
                notify()
                return True
    return False


def dismiss(qid):
    """从队列里拿掉一条(失败或已完成)。素材本身还在库里。"""
    with _lock:
        items = [i for i in _load() if i["id"] != qid]
        _save(items)
    return True


def clear_done():
    with _lock:
        items = [i for i in _load() if i["status"] not in ("已完成", "已跳过")]
        _save(items)
        return len(items)


def recover_orphans():
    """上次进程被杀掉时,条目会卡在「处理中」永远没人理。启动时领回来。"""
    with _lock:
        items = _load()
        n = 0
        for it in items:
            if it["status"] == "处理中":
                it["status"] = "待处理"
                n += 1
        if n:
            _save(items)
        return n


def _pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def claim_runner():
    """同一时刻只该有一个解析循环。第二个启动的让位,避免把同一条解析两遍。"""
    DIR.mkdir(exist_ok=True)
    if LOCK.exists():
        try:
            old = int(LOCK.read_text(encoding="utf-8").strip())
        except ValueError:
            old = 0
        if _pid_alive(old) and old != os.getpid():
            return False
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(release_runner)
    recover_orphans()
    return True


def release_runner():
    try:
        if LOCK.exists() and LOCK.read_text(encoding="utf-8").strip() == str(os.getpid()):
            LOCK.unlink()
    except Exception:
        pass


def snapshot(watching=False, current=None):
    """给素材库页轮询的完整状态。"""
    items = _load()
    from collections import Counter
    return {
        "watching": watching,
        "current": current,
        "summary": dict(Counter(i["status"] for i in items)),
        "items": items,
    }
