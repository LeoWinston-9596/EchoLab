# -*- coding: utf-8 -*-
"""语义群切分 + 翻译 —— 整条流水线技术含量最高的一环。

参考产品里作者是【手工截取对齐】,让每段字幕都是一个完整语义群。
这一步就是用来替代那件手工活的:让 LLM 按语义切,再用词级时间戳映射回时间轴。

关键工程决策:让模型输出【词的下标区间】而不是重写文本。
理由是模型改写文本后就无法可靠对回时间轴了(会漏词、改标点、合并缩写);
输出下标则可以被程序严格校验和修复,时间轴永远准确。
"""
import json

SYSTEM = """你是英语教学材料的编辑,专长是为「影子跟读/回音练习法」切分字幕。

你会收到一段带下标的英文口语转写(每个词形如 12:word)。
你的任务:把它切成若干【完整语义群】,并翻译成自然的中文。

切分标准(按重要性排序):
1. 每一段必须是一个能独立复述的完整意思——学习者要能听完一段就凭记忆说出来;
2. 长度必须在 8-22 个词之间。**少于 8 个词的段是不合格的**——学习者要能
   复述一个完整意思,四五个词的碎片既复述不出内容,视线还要反复跳。
   宁可稍长而完整,绝不为了短而把一个意思劈成两半;
3. 在自然的口语停顿处切:从句边界、并列连词前、话题转换处;
4. 绝不在这些位置切开:冠词与名词之间、助动词与主动词之间、短语动词内部、
   固定搭配内部、介词与其宾语之间;
5. 口语里的填充词(um、like、you know)保留在所在段落内,不单独成段。

翻译标准:
- 口语化、自然的中文,不要翻译腔;
- 与英文语义群一一对应,不做跨段意译、不合并、不拆分;
- 保留说话人的语气(犹豫、强调、玩笑)。

输出严格的 JSON:
{"segments":[{"s":起始词下标,"e":结束词下标(含),"zh":"中文翻译"}]}

硬性要求:
- 下标必须完整覆盖从第一个词到最后一个词,不重叠、不遗漏;
- 每段的 s 必须等于上一段的 e + 1;
- 只输出 JSON,不要任何解释文字。"""


def _chunk(words, size=220, flex=45):
    """长视频要分批送。关键是【别在句子中间切批】。

    早期版本按固定词数硬切,结果每个批次边界都可能把一句话拦腰截断——
    模型看不到下文,只能在那里强行结束一段,产出「But」这种一个词的碎片。
    改成:在目标词数附近 ±flex 的范围里,找说话停顿最长的地方下刀。
    """
    out, i, n = [], 0, len(words)
    while i < n:
        if i + size + flex >= n:                  # 剩下的不多了,一次带走
            out.append(words[i:])
            break
        lo, hi = i + size - flex, min(i + size + flex, n - 1)
        # 词间停顿 = 下一个词的开始 - 当前词的结束
        best, best_gap = hi, -1.0
        for j in range(lo, hi):
            gap = words[j + 1]["start"] - words[j]["end"]
            if gap > best_gap:
                best_gap, best = gap, j
        out.append(words[i:best + 1])
        i = best + 1
    return out


def _repair(segs, lo, hi):
    """校验并修复模型给的下标区间,保证严格连续覆盖 [lo, hi]。

    模型偶尔会跳号或重叠,与其重试(费钱),不如程序修好——
    因为切分点即使偏一两个词,也远好过整批重来。
    """
    segs = [s for s in segs if isinstance(s.get("s"), int) and isinstance(s.get("e"), int)]
    segs.sort(key=lambda s: s["s"])
    fixed, cur = [], lo
    for s in segs:
        e = max(cur, min(int(s["e"]), hi))
        if cur > hi:
            break
        fixed.append({"s": cur, "e": e, "zh": (s.get("zh") or "").strip()})
        cur = e + 1
    if not fixed:                       # 模型完全失败时的兜底:整块作为一段
        return [{"s": lo, "e": hi, "zh": ""}]
    if fixed[-1]["e"] < hi:             # 尾部漏了就并进最后一段
        fixed[-1]["e"] = hi
    return fixed


def _merge_tiny(segs, min_words=3):
    """把过短的碎片并进相邻段。

    一两个词的字幕对影子跟读毫无意义——复述「But」学不到任何东西。
    并进相邻段(优先并入后一段,因为碎片通常是下一句的开头)。
    """
    if len(segs) < 2:
        return segs
    out = []
    for s in segs:
        n = s["e"] - s["s"] + 1
        if n < min_words and out and (out[-1]["e"] - out[-1]["s"] + 1) < 25:
            prev = out[-1]
            prev["e"] = s["e"]
            prev["zh"] = (prev["zh"] + s["zh"]).strip()
            continue
        out.append(s)
    # 若首段仍过短,与第二段合并
    if len(out) > 1 and (out[0]["e"] - out[0]["s"] + 1) < min_words:
        out[1]["s"] = out[0]["s"]
        out[1]["zh"] = (out[0]["zh"] + out[1]["zh"]).strip()
        out.pop(0)
    return out


def _enforce_min(segs, words, min_words=8, max_words=26, max_gap=0.65):
    """把太短的字幕并进邻居,直到达到可读长度。

    实测发现:模型即使被要求 5-20 词,在自动字幕这种碎片化输入上仍会切得很碎,
    出现大量 4-5 词的段。这种长度对影子跟读毫无意义——一句话被劈成三段,
    既复述不出完整意思,视线还要在屏幕上反复跳。

    合并时尊重真实停顿:两段之间若有超过 max_gap 秒的静音,说明那里本来
    就该断开,再短也不合并。
    """
    if len(segs) < 2:
        return segs
    by_i = {w["i"]: w for w in words}

    def n(seg):
        return seg["e"] - seg["s"] + 1

    def gap_after(seg, nxt):
        a, b = by_i.get(seg["e"]), by_i.get(nxt["s"])
        return (b["start"] - a["end"]) if (a and b) else 99.0

    out = [dict(segs[0])]
    for nxt in segs[1:]:
        prev = out[-1]
        too_short = n(prev) < min_words
        fits = n(prev) + n(nxt) <= max_words
        pause = gap_after(prev, nxt)
        if too_short and fits and pause <= max_gap:
            prev["e"] = nxt["e"]
            prev["zh"] = (prev["zh"].rstrip("。,,") + ("," if prev["zh"] else "") + nxt["zh"]).strip(",")
            continue
        out.append(dict(nxt))
    # 末段仍过短就并回前一段
    if len(out) > 1 and n(out[-1]) < min_words and n(out[-2]) + n(out[-1]) <= max_words + 6:
        out[-2]["e"] = out[-1]["e"]
        out[-2]["zh"] = (out[-2]["zh"] + out[-1]["zh"]).strip()
        out.pop()
    return out


def segment_and_translate(llm, words, chunk_size=220, min_words=8, verbose=True):
    """返回 segments: [{id, start, end, en, zh, w0, w1}]"""
    chunks = _chunk(words, chunk_size)
    all_segs = []
    for ci, ch in enumerate(chunks, 1):
        lo, hi = ch[0]["i"], ch[-1]["i"]
        listing = " ".join(f'{w["i"]}:{w["w"]}' for w in ch)
        if verbose:
            print(f"  · 切分+翻译 第 {ci}/{len(chunks)} 批(词 {lo}-{hi})")
        data = llm.chat_json(
            SYSTEM,
            f"请切分并翻译下面这段转写(词下标 {lo} 到 {hi}):\n\n{listing}",
        )
        all_segs += _repair(data.get("segments", []), lo, hi)

    before = len(all_segs)
    all_segs = _enforce_min(_merge_tiny(all_segs), words, min_words=min_words)
    if verbose and before != len(all_segs):
        print(f"  · 合并过短片段:{before} 段 -> {len(all_segs)} 段(最短 {min_words} 词)")

    # 拼装:用词级时间戳还原每段的起止时间和原文
    by_i = {w["i"]: w for w in words}
    out = []
    for sid, s in enumerate(all_segs):
        ws = [by_i[i] for i in range(s["s"], s["e"] + 1) if i in by_i]
        if not ws:
            continue
        out.append({
            "id": sid,
            "w0": s["s"], "w1": s["e"],
            "start": ws[0]["start"],
            "end": ws[-1]["end"],
            "en": " ".join(w["w"] for w in ws),
            "zh": s["zh"],
            "words": [{"w": w["w"], "start": w["start"], "end": w["end"]} for w in ws],
        })
    return out
