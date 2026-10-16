# -*- coding: utf-8 -*-
"""补救那次已经跑完的 `repair.py --merge`:重建段号映射表,并修好过时的 quote。

为什么需要这个脚本:
  重新合并语义群会重新编号段落(段号就是 0..n-1 的下标)。当时的 repair.py
  只把词卡的 seg 挪了,漏了两件事 ——
    · 词卡的 quote 还停在合并前那半句,和点「▶ 原句」听到的对不上;
    · 没留下「老段号 → 新段号」的表,浏览器里按段号存的收藏和播放进度全对不上。
  repair.py 现在两件都做了,但那一轮已经跑完了,只能事后补。

怎么把映射还原出来:
  合并只是把相邻的老段并起来,不会拆段,也不会丢词。每段都记着词下标区间
  [w0, w1],所以「老段落在哪个新段里」是唯一确定的:找到那个包住它的新段即可。
  老数据在 repair.py --merge 留下的 library/<期>/data.json.bak 里。

用法:
    python tools/rescue_after_merge.py              # 预演,不写任何文件
    python tools/rescue_after_merge.py --apply      # 真的写
"""
import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from teco import library as lib   # noqa: E402  路径插好才能导


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, data):
    """原子写:先写同目录的 .tmp 再 replace,中途挂了也不会留半个残文件。

    格式与 process.py / repair.py 一致,免得整份文件在 diff 里全变。
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def build_map(old_segs, new_segs):
    """{老段号: 新段号}。对不上就返回 (None, 原因) —— 宁可不迁移,也不能迁错。"""
    if not old_segs or not new_segs:
        return None, "段落是空的"
    for s in old_segs + new_segs:
        if s.get("w0") is None or s.get("w1") is None:
            return None, "有段缺 w0/w1,无从对齐"

    remap = {}
    for o in old_segs:
        # 合并只并不拆,所以老段必须【整段】落在某个新段里。只要 w0 落进去、
        # w1 却越了界,就说明这两份数据不是同一次合并的前后,不能硬对
        hit = [n for n in new_segs if n["w0"] <= o["w0"] <= n["w1"]]
        if len(hit) != 1:
            return None, f"老段 {o['id']} 的词下标 {o['w0']} 匹配到 {len(hit)} 个新段"
        n = hit[0]
        if o["w1"] > n["w1"]:
            return None, f"老段 {o['id']} 跨了新段 {n['id']} 的边界(w1 {o['w1']} > {n['w1']})"
        remap[o["id"]] = n["id"]

    missing = [s["id"] for s in old_segs if s["id"] not in remap]
    if missing:
        return None, f"{len(missing)} 个老段号映射不上"
    return remap, ""


def fix_quotes(data):
    """把词卡的 quote 刷成所指段落的正文。返回 (修的卡片数, 修的丢弃卡片数)。"""
    by_id = {s["id"]: s for s in data.get("segments") or []}

    def walk(cards):
        n = 0
        for c in cards:
            if not isinstance(c, dict) or not c.get("quote"):
                continue
            s = by_id.get(c.get("seg"))
            if s and c["quote"] != s.get("en"):
                c["quote"] = s["en"]
                n += 1
        return n

    return (walk(data.get("cards") or []),
            walk((data.get("review") or {}).get("dropped_cards") or []))


def main():
    ap = argparse.ArgumentParser(description="补救已跑过的 --merge:重建段号映射、修 quote")
    ap.add_argument("--apply", action="store_true", help="真的写文件(默认只预演)")
    ap.add_argument("--dry-run", action="store_true", help="只预演(默认行为,写出来更明确)")
    args = ap.parse_args()
    apply = args.apply and not args.dry_run

    print("补救 repair.py --merge:从 data.json.bak 还原段号映射,并刷新过时的 quote")
    print(f"模式:{'真的写文件(--apply)' if apply else '预演(不写任何文件)'}\n")

    maps, skipped = {}, []
    tot_q = tot_d = tot_pairs = tot_moved = 0
    if not lib.LIB.exists():
        print("没有 library/ 目录。\n")
        return 0
    for d in sorted(lib.LIB.iterdir()):
        f, bak = d / "data.json", d / "data.json.bak"
        if not (d.is_dir() and f.exists() and bak.exists()):
            continue
        try:
            new, old = load(f), load(bak)
        except Exception as e:
            skipped.append((d.name, f"读不出来:{e}"))
            continue

        remap, why = build_map(old.get("segments") or [], new.get("segments") or [])
        if remap is None:
            skipped.append((d.name, why))
            continue

        moved = sum(1 for k, v in remap.items() if k != v)
        n_seg_old, n_seg_new = len(old.get("segments") or []), len(new.get("segments") or [])
        if n_seg_old == n_seg_new and not moved:
            # 这一期的 .bak 是别的命令留下的(比如重算音标),段号根本没动过。
            # 记一条恒等映射只会让 segmap 变大、让播放器白跑一趟
            print(f"  · {d.name[:44]:46} {n_seg_new:4} 段,段号没变过,跳过")
            continue

        nq, nd = fix_quotes(new)
        maps[d.name] = remap
        tot_q += nq
        tot_d += nd
        tot_pairs += len(remap)
        tot_moved += moved
        extra = f",另修丢弃卡片 {nd} 条" if nd else ""
        print(f"  ✓ {d.name[:44]:46} {n_seg_old:4} → {n_seg_new:4} 段 · "
              f"映射 {len(remap)} 个段号(其中 {moved} 个真的变了) · 修 quote {nq} 条{extra}")
        if apply and (nq or nd):
            dump(f, new)                 # .bak 是合并前的原件,绝对不能碰

    print()
    for name, why in skipped:
        print(f"  ! 跳过 {name[:44]}:{why}")
    if skipped:
        print()

    print(f"合计 {len(maps)} 期:修 quote {tot_q} 条(丢弃卡片 {tot_d} 条)· "
          f"映射 {tot_pairs} 个段号,其中 {tot_moved} 个段号真的变了")
    if not apply:
        print("\n这是预演,一个字节都没写。确认无误后加 --apply 再跑一次。\n")
        return 0
    if maps:
        pairs = lib.write_segmap(maps)
        print(f"已写入 {lib.SEGMAP}({pairs} 条映射)")
        print("下次打开播放器,收藏的句子和播放进度会自动迁到新段号,不用重新收藏。\n")
    else:
        print("没有需要迁移的期数,没写 segmap。\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
