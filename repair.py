#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复已生成的 data.json —— 只做本机能免费重算的部分,不重新调用 API。

    python repair.py library/1st/data.json

目前会重算:整句 IPA、词条 IPA。
用途:早期版本在中文 Windows 上把 espeak 的 UTF-8 输出按 GBK 解码,
音标全是乱码。这个脚本可以就地修好,不必重跑整条流水线、不必再花钱。
"""
import json, sys, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from teco.ipa import to_ipa, word_ipa
from teco.tools import find_espeak

CJK = re.compile(r"[一-鿿぀-ヿ]")


def main():
    if len(sys.argv) < 2:
        sys.exit("用法:python repair.py library/<期数>/data.json")
    if not find_espeak():
        sys.exit("找不到 espeak-ng,无法重算音标。")

    p = pathlib.Path(sys.argv[1])
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
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"  已重算 {len(d['segments'])} 段 + {len(d.get('cards', []))} 张卡片的音标")
    print(f"  修复后仍含乱码:{bad_after}")
    if d.get("segments"):
        print(f"\n  示例:{d['segments'][0]['en'][:40]}")
        print(f"        {d['segments'][0]['ipa'][:60]}")
    print("\n  完成。刷新播放器即可看到。\n")


if __name__ == "__main__":
    main()
