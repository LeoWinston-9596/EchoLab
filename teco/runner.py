# -*- coding: utf-8 -*-
"""队列解析循环。serve.py 启动时默认带着它跑,worker.py 也可以单独开。

单独拆出来是因为网页服务和解析必须能同生共死:
家人只双击「启动」,不会再记得开第二条命令。解析本身仍是子进程,
崩了不会把网页服务带走。
"""
import os, pathlib, subprocess, sys, threading
from types import SimpleNamespace

from . import inbox
from . import library as lib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 素材库页轮询时能看见「正在解析哪一条」
_current = None
_watching = False
_thread = None


def current():
    return _current


def watching():
    return _watching


def status():
    return inbox.snapshot(watching=_watching, current=_current)


def _opts(args):
    """把 argparse.Namespace 或普通对象收成统一形状。"""
    return SimpleNamespace(
        llm=getattr(args, "llm", None),
        no_cards=getattr(args, "no_cards", False),
        asr_model=getattr(args, "asr_model", None),
        interval=getattr(args, "interval", 2),
    )


def run_one(item, args):
    url, kind = item["url"], item["platform"]
    title = item.get("title") or ""
    print(f"\n▶ [{kind}] {title[:50] or url[:60]}")

    cmd = [sys.executable, "process.py", "--url", url]
    if title:
        cmd += ["--title", title[:60]]
    if args.llm:
        cmd += ["--llm", args.llm]
    if args.no_cards:
        cmd.append("--no-cards")
    if args.asr_model:
        cmd += ["--asr-model", args.asr_model]

    env = dict(os.environ, ECHOLAB_INSIDE="1")
    r = subprocess.run(cmd, cwd=str(ROOT), env=env)
    if r.returncode == 0:
        ep = lib.find_by_source(item.get("key") or "") or ""
        inbox.update(item["id"], status="已完成", error="", episode=ep)
        print("  ✓ 完成" + (f" → {ep}" if ep else ""))
        return True
    inbox.update(item["id"], status="失败", error=f"退出码 {r.returncode}")
    print("  ✗ 失败(上面的输出里有原因)")
    return False


def loop(args, once=False):
    """once=True 时清完当前待处理就退出;False 则一直守着。"""
    global _current, _watching
    args = _opts(args)
    _watching = not once
    try:
        while True:
            item = inbox.take_next()
            if item:
                _current = {"id": item["id"], "title": item.get("title") or "",
                            "url": item["url"], "platform": item.get("platform")}
                try:
                    run_one(item, args)
                finally:
                    _current = None
                continue
            if once:
                break
            inbox.wait(args.interval)
    finally:
        _watching = False


def start_background(args=None):
    """给 serve.py 用:占住解析锁,在后台线程里守着队列。

    锁被别人占着时返回 False,serve 仍然提供网页,只是不再重复开解析。
    """
    global _thread
    args = args or SimpleNamespace()
    if not inbox.claim_runner():
        print("  解析循环已在另一个进程里跑,这里只提供网页。")
        return False
    _thread = threading.Thread(target=loop, args=(args,),
                               daemon=True, name="echolab-worker")
    _thread.start()
    print("  队列解析已启动:书签入队后会自动开跑。")
    return True
