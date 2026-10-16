# -*- coding: utf-8 -*-
"""收件箱:入队时把链接收干净、崩溃后把卡住的条目领回来。不联网。"""
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from teco import inbox

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else:    fail += 1; print(f"  ✗ {name}  {extra}")


def isolate(tmp):
    inbox.DIR = tmp
    inbox.QUEUE = tmp / "queue.json"
    inbox.TOKEN = tmp / "token.txt"
    inbox.LOCK = tmp / "runner.lock"


with tempfile.TemporaryDirectory() as td:
    isolate(pathlib.Path(td))
    r = inbox.add("https://youtu.be/ZZZZZZZZZZZ?list=PLdeadbeef&t=30", "单元测试")
    items = inbox.list_all()
    check("入队成功", r.get("ok") is True, str(r))
    check("存进去的是干净的 watch?v= 链接",
          items and items[0]["url"] == "https://www.youtube.com/watch?v=ZZZZZZZZZZZ",
          items[0]["url"] if items else "空")
    check("source_key 按视频 ID",
          items and items[0]["key"] == "youtube:ZZZZZZZZZZZ")

    r2 = inbox.add("https://www.youtube.com/watch?v=ZZZZZZZZZZZ&si=abc", "再点一次")
    check("同视频不同链接算重复", r2.get("duplicate") is True, str(r2))

    item = inbox.take_next()
    check("取出后变成处理中", item and item["status"] == "处理中")
    check("再取就空了", inbox.take_next() is None)
    n = inbox.recover_orphans()
    check("崩溃后领回处理中的条目", n == 1)
    check("领回来是待处理", inbox.take_next()["status"] == "处理中")

    inbox.update(item["id"], status="失败", error="退出码 1")
    check("单条重试", inbox.requeue_one(item["id"]) is True)
    check("重试后能再取到", inbox.take_next() is not None)

print(f"\n通过 {ok} / {ok+fail}")
sys.exit(1 if fail else 0)
