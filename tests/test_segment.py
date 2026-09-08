# -*- coding: utf-8 -*-
"""语义群合并的离线测试:不调模型,只验证「多短算太短」这条规则。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from teco.segment import merge_short, _target_words, MIN_WORDS, MIN_SECS

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else:    fail += 1; print(f"  ✗ {name}  {extra}")


def words_at(n, wpm):
    """造 n 个词,按给定语速均匀铺在时间轴上。"""
    step = 60.0 / wpm
    return {i: {"w": f"w{i}", "start": i * step, "end": (i + 1) * step}
            for i in range(n)}


def cut(n, size):
    """把 n 个词按每段 size 个切开。"""
    return [{"s": i, "e": min(i + size - 1, n - 1), "zh": "译"}
            for i in range(0, n, size)]


def sizes(segs):
    return [s["e"] - s["s"] + 1 for s in segs]


print("【词数过短要合并】")
by_i = words_at(60, 90)                       # 慢速,每词 0.67 秒
out = merge_short(cut(60, 4), by_i)           # 4 个词一段,明显太碎
check("4 词的碎段被合并", min(sizes(out)) >= MIN_WORDS, str(sizes(out)))
check("合并后段数变少", len(out) < 15, str(len(out)))
check("没有丢词", out[0]["s"] == 0 and out[-1]["e"] == 59,
      f'{out[0]["s"]}..{out[-1]["e"]}')
check("译文被拼接保留", all(s["zh"] for s in out))

print("\n【同样的词数,语速快的要并得更长】")
fast = merge_short(cut(120, 8), words_at(120, 240))   # 8 词只有 2.0 秒
slow = merge_short(cut(120, 8), words_at(120, 90))    # 8 词有 5.3 秒
check("慢速素材 8 词一段就够了", sizes(slow)[0] == 8, str(sizes(slow)[:3]))
check("快速素材会并成更多词", sizes(fast)[0] > 8, str(sizes(fast)[:3]))
check("快速素材段数更少", len(fast) < len(slow), f"{len(fast)} vs {len(slow)}")

print("\n【不该动的别动】")
by_i = words_at(120, 120)                     # 12 词 = 6 秒,正常长度
keep = cut(120, 12)
check("正常长度原样保留", sizes(merge_short(keep, by_i)) == sizes(keep))
check("只有一段时原样返回", merge_short([{"s": 0, "e": 2, "zh": "x"}], by_i) ==
      [{"s": 0, "e": 2, "zh": "x"}])

print("\n【合并有上限,不会并成一堵墙】")
out = merge_short(cut(300, 3), words_at(300, 300))    # 极快 + 极碎
check("不超过 26 词的上限", max(sizes(out)) <= 26, str(max(sizes(out))))
longest = max((s["e"] - s["s"] + 1) * 60.0 / 300 for s in out)
check("不超过 9.5 秒的上限", longest <= 9.5 + 1e-6, f"{longest:.1f}s")

print("\n【末段过短要往前并】")
segs = cut(24, 12) + [{"s": 24, "e": 25, "zh": "尾"}]
out = merge_short(segs, words_at(26, 120))
check("尾巴不会孤零零留着", out[-1]["e"] - out[-1]["s"] + 1 >= MIN_WORDS,
      str(sizes(out)))

print("\n【给模型的目标词数随语速上浮】")
def chunk_at(n, wpm):
    step = 60.0 / wpm
    return [{"start": i * step, "end": (i + 1) * step} for i in range(n)]

wpm_slow, lo_s, hi_s = _target_words(chunk_at(100, 100))
wpm_fast, lo_f, hi_f = _target_words(chunk_at(100, 200))
check("语速估算大致正确", 95 <= wpm_slow <= 105 and 190 <= wpm_fast <= 210,
      f"{wpm_slow} / {wpm_fast}")
check("快素材的目标词数更高", hi_f > hi_s, f"{lo_s}-{hi_s} vs {lo_f}-{hi_f}")
check("下限不低于合并门槛", lo_s > MIN_WORDS - 1 and lo_f > MIN_WORDS - 1)

print(f"\n通过 {ok} / {ok+fail}")
sys.exit(1 if fail else 0)
