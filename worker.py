#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""处理收件箱里的队列。

    python worker.py            处理完当前所有待处理项
    python worker.py --watch    守着队列,来一个处理一个

日常不用单独开它:python serve.py(或双击「启动」)已经带着解析循环。
这条命令留给「只要解析、不要网页」的场合,比如挂在另一台机器上。

YouTube 走「取字幕 + 嵌入播放」,不下载任何文件;
TikTok / 抖音 / 其它站点走下载 + 语音识别的完整流水线。
"""
import argparse, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from teco import inbox
from teco import runner


def main():
    ap = argparse.ArgumentParser(description="处理 EchoLab 收件箱队列")
    ap.add_argument("--watch", action="store_true", help="持续守候,来一个处理一个")
    ap.add_argument("--interval", type=int, default=2, help="守候模式的轮询间隔(秒)")
    ap.add_argument("--llm", default=None)
    ap.add_argument("--asr-model", default=None)
    ap.add_argument("--no-cards", action="store_true")
    ap.add_argument("--retry-failed", action="store_true",
                    help="把之前失败的重新排队(改了代码后重试用)")
    args = ap.parse_args()

    if args.retry_failed:
        n = inbox.requeue_failed()
        print(f"已把 {n} 个失败项重新排队。")

    if args.watch:
        if not inbox.claim_runner():
            print("已有解析循环在跑(多半是 serve.py 带着的),不必再开一条。")
            sys.exit(0)
        print("守候中,按 Ctrl+C 停止。在浏览器点书签即可投递。\n")
        try:
            runner.loop(args, once=False)
        except KeyboardInterrupt:
            print("\n已停止。")
        return

    st = inbox.summary()
    if st:
        print("队列:" + " · ".join(f"{k} {v}" for k, v in st.items()))
    if not st.get("待处理"):
        print("\n没有待处理的条目。")
        if st.get("失败"):
            print(f"有 {st['失败']} 个之前失败的。想重试:python worker.py --retry-failed")
        else:
            print("去浏览器点一下书签把视频存进来,或直接:")
            print('  python process.py --url "视频网址" --title "第1期"')
        print()
        return

    if not inbox.claim_runner():
        print("已有解析循环在跑(多半是 serve.py 带着的),队列会在那边自动消化。")
        sys.exit(0)
    try:
        runner.loop(args, once=True)
    finally:
        inbox.release_runner()
    print("\n跑完了。素材库页会自动出现新内容。\n")


if __name__ == "__main__":
    main()
