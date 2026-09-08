# -*- coding: utf-8 -*-
"""语义群切分 + 翻译 —— 整条流水线技术含量最高的一环。

参考产品里作者是【手工截取对齐】,让每段字幕都是一个完整语义群。
这一步就是用来替代那件手工活的:让 LLM 按语义切,再用词级时间戳映射回时间轴。

关键工程决策:让模型输出【词的下标区间】而不是重写文本。
理由是模型改写文本后就无法可靠对回时间轴了(会漏词、改标点、合并缩写);
输出下标则可以被程序严格校验和修复,时间轴永远准确。
"""
import json

# 「多短算太短」的标准。词数和时长都要过——只看词数的话,240 词/分的素材里
# 8 个词只有 2 秒,一闪就过去了;只看时长的话,慢速素材里 3 个词拖到 3 秒
# 也会被当成合格。
MIN_WORDS = 8
MIN_SECS = 2.2
# 合并的上限:超出一次工作记忆能装下的量,跟读就变成了念稿
MAX_WORDS = 26
MAX_SECS = 9.5
# 两段之间的静音超过这个秒数,说明那里本来就该断开,再短也不合并
MAX_GAP = 0.65

SYSTEM = """你是英语教学材料的编辑,专长是为「影子跟读/回音练习法」切分字幕。

你会收到一段带下标的英文口语转写(每个词形如 12:word)。
你的任务:把它切成若干【完整语义群】,并翻译成自然的中文。

切分标准(按重要性排序):
1. 每一段必须是一个能独立复述的完整意思——学习者要能听完一段就凭记忆说出来;
2. 长度按每次请求给出的【目标词数】来,那个范围是按这段素材的语速算的。
   **少于 8 个词的段一律不合格**——学习者要能复述一个完整意思,
   四五个词的碎片既复述不出内容,视线还要反复跳。
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


def _join_zh(a, b):
    """两段译文接起来。前一段的句末标点要去掉,否则会读到「……。,……」。"""
    a = (a or "").rstrip("。,,、 ")
    b = (b or "").strip()
    if not a:
        return b
    return (a + ("," + b if b else "")).strip(",")


def merge_short(segs, by_i, min_words=MIN_WORDS, min_secs=MIN_SECS,
                max_words=MAX_WORDS, max_secs=MAX_SECS, max_gap=MAX_GAP):
    """把太短的段并进后一段,直到词数和时长都达到可读长度。

    实测发现:模型即使被要求 8 词以上,在自动字幕这种碎片化输入上仍会切得很碎,
    出现大量 4-5 词的段。这种长度对影子跟读毫无意义——一句话被劈成三段,
    既复述不出完整意思,视线还要在屏幕上反复跳。

    词数和时长两个门槛都要过,原因见文件开头 MIN_WORDS/MIN_SECS 的说明。
    合并时尊重真实停顿:两段之间若有超过 max_gap 秒的静音,说明那里本来
    就该断开,再短也不合并。

    by_i 是 {词下标: 词},要有 start/end。segments 只给下标区间,不碰文本——
    文本和时间轴由调用方按最终的下标区间重新拼,这样时间轴永远是准的。
    """
    if len(segs) < 2:
        return segs

    def n(seg):
        return seg["e"] - seg["s"] + 1

    def dur(lo, hi):
        a, b = by_i.get(lo), by_i.get(hi)
        return (b["end"] - a["start"]) if (a and b) else 99.0

    def gap_after(seg, nxt):
        a, b = by_i.get(seg["e"]), by_i.get(nxt["s"])
        return (b["start"] - a["end"]) if (a and b) else 99.0

    def short(seg):
        return n(seg) < min_words or dur(seg["s"], seg["e"]) < min_secs

    out = [dict(segs[0])]
    for nxt in segs[1:]:
        prev = out[-1]
        fits = (n(prev) + n(nxt) <= max_words
                and dur(prev["s"], nxt["e"]) <= max_secs)
        if short(prev) and fits and gap_after(prev, nxt) <= max_gap:
            prev["e"] = nxt["e"]
            prev["zh"] = _join_zh(prev["zh"], nxt["zh"])
            continue
        out.append(dict(nxt))
    # 末段没有「后一段」可并,只能往前并。这里放宽词数上限:留一个孤零零的
    # 尾巴比让倒数第二段长几个词更难受
    if len(out) > 1 and short(out[-1]) and n(out[-2]) + n(out[-1]) <= max_words + 6:
        out[-2]["e"] = out[-1]["e"]
        out[-2]["zh"] = _join_zh(out[-2]["zh"], out[-1]["zh"])
        out.pop()
    return out


def _target_words(chunk):
    """按这一批的语速算出给模型的目标词数。返回 (语速, 下限, 上限)。

    这是用户那条「语速快的句子更应该一句话多一些单词」的落点:固定词数
    在快素材上等于固定不了时长——8 个词在 120 词/分是 4 秒,在 240 词/分
    只有 2 秒。所以按目标【时长】4.5-7 秒反推词数,让每段的跟读难度大致一致。
    """
    span = (chunk[-1]["end"] - chunk[0]["start"]) if chunk else 0
    wpm = (len(chunk) * 60.0 / span) if span > 0 else 150.0
    lo = max(MIN_WORDS, round(wpm * 4.5 / 60))
    hi = min(MAX_WORDS, max(lo + 6, round(wpm * 7.0 / 60)))
    return round(wpm), lo, hi


def segment_and_translate(llm, words, chunk_size=220, min_words=8, verbose=True):
    """返回 segments: [{id, start, end, en, zh, w0, w1}]"""
    chunks = _chunk(words, chunk_size)
    all_segs = []
    for ci, ch in enumerate(chunks, 1):
        lo, hi = ch[0]["i"], ch[-1]["i"]
        listing = " ".join(f'{w["i"]}:{w["w"]}' for w in ch)
        wpm, tlo, thi = _target_words(ch)
        tlo = max(tlo, min_words)
        if verbose:
            print(f"  · 切分+翻译 第 {ci}/{len(chunks)} 批(词 {lo}-{hi},"
                  f"语速 {wpm} 词/分,目标每段 {tlo}-{thi} 词)")
        data = llm.chat_json(
            SYSTEM,
            f"这段素材的语速是 {wpm} 词/分,【目标词数】每段 {tlo}-{thi} 个词。\n"
            f"请切分并翻译下面这段转写(词下标 {lo} 到 {hi}):\n\n{listing}",
        )
        all_segs += _repair(data.get("segments", []), lo, hi)

    before = len(all_segs)
    by_i = {w["i"]: w for w in words}
    all_segs = merge_short(_merge_tiny(all_segs), by_i, min_words=min_words)
    if verbose and before != len(all_segs):
        print(f"  · 合并过短片段:{before} 段 -> {len(all_segs)} 段"
              f"(最短 {min_words} 词 / {MIN_SECS} 秒)")

    # 拼装:用词级时间戳还原每段的起止时间和原文
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
