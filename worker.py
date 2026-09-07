#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""处理收件箱里的队列。

    python worker.py            处理完当前所有待处理项
    python worker.py --watch    守着队列,来一个处理一个

YouTube 走「取字幕 + 嵌入播放」,不下载任何文件;
TikTok / 抖音 / 其它站点走下载 + 语音识别的完整流水线。
"""
import argparse, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from teco import inbox
from teco.platforms import detect


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

    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode == 0:
        inbox.update(item["id"], status="已完成", error="")
        print("  ✓ 完成")
        return True
    inbox.update(item["id"], status="失败", error=f"退出码 {r.returncode}")
    print("  ✗ 失败(上面的输出里有原因)")
    return False


def main():
    ap = argparse.ArgumentParser(description="处理 EchoLab 收件箱队列")
    ap.add_argument("--watch", action="store_true", help="持续守候,来一个处理一个")
    ap.add_argument("--interval", type=int, default=8, help="守候模式的轮询间隔(秒)")
    ap.add_argument("--llm", default=None)
    ap.add_argument("--asr-model", default=None)
    ap.add_argument("--no-cards", action="store_true")
    ap.add_argument("--retry-failed", action="store_true",
                    help="把之前失败的重新排队(改了代码后重试用)")
    args = ap.parse_args()

    if args.retry_failed:
        n = inbox.requeue_failed()
        print(f"已把 {n} 个失败项重新排队。")

    st = inbox.summary()
    if st:
        print("队列:" + " · ".join(f"{k} {v}" for k, v in st.items()))
    if not st.get("待处理") and not args.watch:
        # 队列里没活干时必须说清楚,否则用户会以为程序卡住了
        print("\n没有待处理的条目。")
        if st.get("失败"):
            print(f"有 {st['失败']} 个之前失败的。想重试:python worker.py --retry-failed")
        else:
            print("去浏览器点一下书签把视频存进来,或直接:")
            print('  python process.py --url "视频网址" --title "第1期"')
        print()
        return

    if args.watch:
        print("守候中,按 Ctrl+C 停止。在浏览器点书签即可投递。\n")
    done = 0
    try:
        while True:
            item = inbox.take_next()
            if item:
                run_one(item, args)
                done += 1
                continue
            if not args.watch:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n已停止。")
    print(f"\n本次处理 {done} 个。运行 python serve.py 打开播放器查看。\n")


if __name__ == "__main__":
    main()
