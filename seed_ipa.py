#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 library/ 里已有卡片的音标灌进本地 IPA 语料库 —— 一次性的冷启动。

    python seed_ipa.py              导入并落盘
    python seed_ipa.py --dry-run    只看会导入多少,不写文件
    python seed_ipa.py --check      只测命中率:现有卡片有多少能直接查到

已经解析过的几十期里每张卡片都带着音标,这些是白捡的存量:导进语料库
之后,以后任何一期只要出现过的词就不必再算第二遍,新词才需要现算。
"""
import argparse, collections, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from teco import ipa as ipa_mod, library as lib


def collect():
    """扫全库卡片,按归一化词条汇总出现过的音标。

    返回 {词条键: Counter({(us, uk): 次数})} 与原始词条写法(注音要用原文)。
    """
    seen = collections.defaultdict(collections.Counter)
    origin, n_ep, n_card = {}, 0, 0
    for ep_id, data in lib.episodes():
        n_ep += 1
        for c in data.get("cards") or []:
            term = (c.get("term") or "").strip()
            key = ipa_mod.norm_term(term)
            entry = c.get("ipa") or {}
            n_card += 1
            if not key or not ipa_mod.usable(entry):
                continue
            seen[key][(entry["us"].strip(), entry["uk"].strip())] += 1
            origin.setdefault(key, term)
    return seen, origin, n_ep, n_card


def pick(counter):
    """同一个词在不同期里音标不一致时,取出现次数最多的那版。

    不一致基本来自 espeak-ng 版本差异和词条大小写/标点的细微不同,不是
    谁对谁错,所以取多数就够;票数相同时按音标字符串排序取第一个,
    保证换台机器重跑还是同一个结果。
    """
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def cmd_seed(dry):
    seen, origin, n_ep, n_card = collect()
    print(f"扫描 library/:{n_ep} 期 · {n_card} 张卡片 · {len(seen)} 个不同词条\n")

    conflicts = {k: v for k, v in seen.items() if len(v) > 1}
    corpus = ipa_mod.load_corpus()
    fresh = [k for k in seen if k not in corpus]

    print(f"  语料库原有        {len(corpus)} 条")
    print(f"  可新增            {len(fresh)} 条")
    print(f"  已存在跳过        {len(seen) - len(fresh)} 条")
    print(f"  音标不一致的词条  {len(conflicts)} 个(已按出现次数取多数)")
    for key, counter in sorted(conflicts.items(), key=lambda kv: -len(kv[1]))[:8]:
        vs = " | ".join(f"{us}×{n}" for (us, _), n in counter.most_common())
        print(f"      {key[:34]:36} {vs}")
    if len(conflicts) > 8:
        print(f"      …… 还有 {len(conflicts) - 8} 个")

    if dry:
        # 预演一律不 stage:暂存里的东西进程退出时会被 atexit 自动落盘
        print("\n  这是预演(--dry-run),没有写任何文件。\n")
        return
    for key in fresh:
        us, uk = pick(seen[key])
        ipa_mod.stage(origin[key], {"us": us, "uk": uk})
    wrote = ipa_mod.flush()
    print(f"\n  ✓ 已写入 {wrote} 条 → {ipa_mod.CORPUS_PATH.relative_to(ROOT)}"
          f"(现共 {ipa_mod.corpus_size()} 条)")
    print("  记得把它一起提交进版本库,这份存量以后每期都在省时间。\n")


def cmd_check():
    """量一下语料库的命中率。

    直接拿全库卡片去查会得到 100%——语料库本来就是从它们种出来的,
    这个数字没有意义。真正想知道的是「下一期新素材能省多少」,所以再做一次
    留一法:把某一期当成没见过的新素材,语料库只由其余各期构成。
    """
    corpus = ipa_mod.load_corpus()
    seen, _, n_ep, n_card = collect()
    covered = sum(1 for k in seen if k in corpus)
    print(f"语料库 {len(corpus)} 条 · 样本 {n_ep} 期 / {n_card} 张卡片\n")
    print(f"  存量覆盖率(全库词条有多少已在库里)"
          f"  {covered}/{len(seen)}({covered * 100 // max(len(seen), 1)}%)")

    per_ep = []
    for ep_id, data in lib.episodes():
        keys = [k for k in (ipa_mod.norm_term(c.get("term") or "")
                            for c in (data.get("cards") or [])) if k]
        per_ep.append((ep_id, keys))
    hit = tot = 0
    for i, (ep_id, keys) in enumerate(per_ep):
        others = {k for j, (_, ks) in enumerate(per_ep) if j != i for k in ks}
        hit += sum(1 for k in keys if k in others)
        tot += len(keys)
    print(f"  留一法命中率(新素材大致能省多少)  {hit}/{tot}"
          f"({hit * 100 // max(tot, 1)}%)")
    missed = [k for k in seen if k not in corpus]
    if missed:
        print(f"\n  未命中示例  {'、'.join(missed[:6])}")
    print()


def main():
    ap = argparse.ArgumentParser(description="用已有卡片给本地 IPA 语料库做冷启动")
    ap.add_argument("--dry-run", action="store_true", help="只看会导入什么,不写文件")
    ap.add_argument("--check", action="store_true", help="只测命中率,不导入")
    args = ap.parse_args()
    if args.check:
        cmd_check()
    else:
        cmd_seed(args.dry_run)


if __name__ == "__main__":
    main()
