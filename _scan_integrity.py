# -*- coding: utf-8 -*-
"""一次性的数据体检:合并过段落之后,逐期核对 data.json 还自洽不自洽。用完即删。"""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def main():
    from teco.segment import MIN_WORDS, MIN_SECS

    problems = []
    rows = []
    lib = pathlib.Path("library")
    if not lib.exists():
        print("没有 library/ 目录。")
        return 0

    for d in sorted(lib.iterdir()):
        f = d / "data.json"
        if not f.is_file():
            continue
        j = json.loads(f.read_text(encoding="utf-8"))
        segs = j.get("segments") or []
        cards = j.get("cards") or []
        name = d.name[:38]

        def bad(msg, n=name):
            problems.append(f"{n}: {msg}")

        for i, s in enumerate(segs):
            if s.get("start") is None or s.get("end") is None or s["start"] >= s["end"]:
                bad(f"第 {i} 段起止不合法 {s.get('start')}~{s.get('end')}"); break
            if i and s["start"] < segs[i - 1]["start"] - 1e-6:
                bad(f"第 {i} 段起点倒退"); break

        if [s.get("id") for s in segs] != list(range(len(segs))):
            bad("段号不连续")
        if any(not isinstance(s.get("words"), list) or not s["words"] for s in segs):
            bad("有段缺 words")

        holes = sum(1 for a, b in zip(segs, segs[1:])
                    if a.get("w1") is not None and b.get("w0") is not None
                    and b["w0"] != a["w1"] + 1)
        if holes:
            bad(f"{holes} 处词下标断裂(合并可能丢词)")

        ids = {s["id"] for s in segs}
        miss = [c for c in cards if c.get("seg") not in ids]
        if miss:
            bad(f"{len(miss)} 张卡片指向不存在的段号")
        by_id = {s["id"]: s for s in segs}
        mismatch = [c for c in cards
                    if c.get("seg") in by_id and c.get("quote")
                    and c["quote"] != by_id[c["seg"]].get("en")]
        if mismatch:
            bad(f"{len(mismatch)} 张卡片的 quote 与所指段落正文不符")

        wrong = [c for c in cards if c.get("ipa") is not None and not isinstance(c["ipa"], dict)]
        if wrong:
            bad(f"{len(wrong)} 张卡片的 ipa 不是 {{us,uk}} 字典")

        short = sum(1 for s in segs
                    if len(s.get("words") or []) < MIN_WORDS
                    or (s.get("end", 0) - s.get("start", 0)) < MIN_SECS)
        rows.append((name, len(segs), short, len(cards)))

    print(f"{'期数':40s} {'段数':>6s} {'过短':>6s} {'卡片':>6s}")
    for n, a, b, c in rows:
        flag = "  <<" if a and b / a > 0.25 else ""
        print(f"{n:40s} {a:6d} {b:6d} {c:6d}{flag}")

    tot_s = sum(r[1] for r in rows)
    tot_short = sum(r[2] for r in rows)
    print(f"\n合计 {len(rows)} 期 · {tot_s} 段 · 其中过短 {tot_short} 段"
          f" ({tot_short / max(tot_s, 1) * 100:.1f}%)")

    print(f"\n{'=' * 60}")
    if problems:
        print(f"发现 {len(problems)} 个问题:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("✓ 数据自洽,没有发现问题。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
