#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跑完所有离线测试:python tests/run_all.py

全部不联网、不调模型,几秒钟跑完,改完代码随手跑一遍。
在中文 Windows 上控制台默认是 GBK,打不出 ✓,所以这里强制子进程用 UTF-8。
"""
import os, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
env = dict(os.environ, PYTHONIOENCODING="utf-8")

failed = []
for f in sorted(HERE.glob("test_*.py")):
    print(f"\n{'='*60}\n{f.name}\n{'='*60}")
    r = subprocess.run([sys.executable, "-X", "utf8", str(f)], env=env)
    if r.returncode:
        failed.append(f.name)

print(f"\n{'='*60}")
if failed:
    print("失败:" + "、".join(failed))
    sys.exit(1)
print("全部通过。")
