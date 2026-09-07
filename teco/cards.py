# -*- coding: utf-8 -*-
"""知识点卡片:按六类抽取,并生成中英释义/例句/考级标签。

六类沿用参考产品的分法:单词、短语、短语动词、搭配、口语句式、话语标记。
其中【口语句式】和【话语标记】是 vlog 学习真正的价值所在——
课本里学不到 "I was just like...""you know what I mean" 这种东西。
"""
import json, re

TYPES = ["word", "phrase", "phrasal_verb", "collocation", "pattern", "discourse_marker"]
TYPE_ZH = {
    "word": "单词", "phrase": "短语", "phrasal_verb": "短语动词",
    "collocation": "搭配", "pattern": "口语句式", "discourse_marker": "话语标记",
}

SYSTEM = """你是英语精读教材的编者,为中国学习者从真实 vlog 口语里提炼知识点。

从给定的字幕片段中抽取值得学的知识点,分为六类:
- word 单词:有学习价值的实词(跳过 the/is/and 这类无需讲解的词)
- phrase 短语:固定的名词/形容词短语,如 a good way, first impression
- phrasal_verb 短语动词:动词+副词/介词,如 put on, get away from, take off
- collocation 搭配:地道的词语组合,如 impulse decision, sprain ankle
- pattern 口语句式:可直接套用的说话框架,如 "I was just like...", "there's no way..."
- discourse_marker 话语标记:组织话语的口语标记,如 you know, I mean, actually, right?

抽取原则:
1. 只选【真实出现在文本中】的表达,严禁编造原文没有的内容;
2. 优先选对口语输出有用的:能让学习者下次自己说出来的表达;
3. 一段字幕通常出 0-3 个知识点,宁精勿滥,不要为凑数收录简单词;
4. quote 必须是原文中的【原句片段,逐字照抄】,用于回放定位。

每个知识点输出:
{
 "term": "词条本身(原形,如 put on 而非 put it on)",
 "type": "六类之一的英文标识",
 "seg": 所在字幕段的编号,
 "quote": "原文中包含它的那句话(逐字照抄)",
 "pos": "词性,如 verb / noun / phrase,没有就空串",
 "def_en": "简明英文释义",
 "def_zh": "中文释义",
 "ex_en": "一个新造的例句(不要重复原文)",
 "ex_zh": "例句中文翻译",
 "exam": ["考级标签,从 四级/六级/考研/雅思/托福/专四/专八 中选,不确定就给空数组"],
 "note": "用法提示或语境备注,一句话,没有就空串"
}

输出严格 JSON:{"cards":[...]}。只输出 JSON,不要解释。"""


# 常见不规则变位。短语动词在真实口语里几乎总是被拆开且变位
# ("took it off"、"found that out"),不做还原就会把最有价值的卡片全误杀。
IRREGULAR = {
    "was": "be", "were": "be", "is": "be", "are": "be", "am": "be", "been": "be", "being": "be",
    "took": "take", "taken": "take", "found": "find", "went": "go", "gone": "go",
    "got": "get", "gotten": "get", "had": "have", "has": "have", "having": "have",
    "did": "do", "done": "do", "said": "say", "made": "make", "came": "come",
    "saw": "see", "seen": "see", "knew": "know", "known": "know", "thought": "think",
    "felt": "feel", "kept": "keep", "left": "leave", "meant": "mean", "told": "tell",
    "gave": "give", "given": "give", "brought": "bring", "bought": "buy", "caught": "catch",
    "held": "hold", "ran": "run", "sat": "sit", "spent": "spend", "stood": "stand",
    "wore": "wear", "worn": "wear", "wrote": "write", "written": "write",
}
# 词条里的占位成分,不参与匹配
PLACEHOLDERS = {"sb", "sth", "someone", "something", "ones", "oneself",
                "your", "yours", "his", "her", "their", "my", "its"}


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).strip()


def _stem(w):
    """极简词干还原。目标不是语言学正确,而是让词条与原文能对上。"""
    w = w.lower()
    if w in IRREGULAR:
        return IRREGULAR[w]
    for suf, repl in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            return w[: -len(suf)] + repl
    return w


def _tokens(text):
    return [_stem(t) for t in _norm(text).split() if t]


def locate(term, segments, max_gap=4):
    """在字幕里找这个词条真实出现的位置。

    判定标准:词条的各成分(还原词干后)在某一段里【按顺序出现】,
    允许中间插入少量词——这样 "take off" 能匹配 "took it off",
    "be bad for" 能匹配 "was really bad for",而 "break the ice" 这种
    原文根本没有的幻觉词条仍然会被挡住。
    返回 (段id, 命中跨度) 或 None。
    """
    need = [t for t in _tokens(term) if t not in PLACEHOLDERS]
    if not need:
        return None
    best = None
    for seg in segments:
        toks = _tokens(seg["en"])
        for start in range(len(toks)):
            if toks[start] != need[0]:
                continue
            pos, ok = start, True
            for nxt in need[1:]:
                found = None
                for j in range(pos + 1, min(pos + 1 + max_gap + 1, len(toks))):
                    if toks[j] == nxt:
                        found = j
                        break
                if found is None:
                    ok = False
                    break
                pos = found
            if ok:
                span = pos - start
                if best is None or span < best[1]:
                    best = (seg["id"], span)
                break
        if best and best[1] == len(need) - 1:      # 完全连续匹配,不必再找
            break
    return best

def extract_cards(llm, segments, batch=12, verbose=True):
    """按批处理字幕段,抽取知识点。返回卡片列表。"""
    cards = []
    for bi in range(0, len(segments), batch):
        part = segments[bi:bi + batch]
        if verbose:
            print(f"  · 抽取知识点 第 {bi//batch + 1}/{(len(segments)-1)//batch + 1} 批")
        body = "\n".join(f'[{s["id"]}] {s["en"]}' for s in part)
        data = llm.chat_json(SYSTEM, f"字幕片段:\n\n{body}")
        for c in data.get("cards", []):
            if not c.get("term"):
                continue
            c["type"] = c.get("type") if c.get("type") in TYPES else "word"
            c["type_zh"] = TYPE_ZH[c["type"]]
            try:
                c["seg"] = int(c.get("seg", part[0]["id"]))
            except (TypeError, ValueError):
                c["seg"] = part[0]["id"]
            cards.append(c)
    return cards


def verify_and_enrich(cards, segments, wordlists=None):
    """三件事:剔除原文里查无此处的幻觉词条、补 IPA、用权威词表覆盖考级标签。

    第一件最重要——一个学习工具里出现凭空捏造的知识点是不可接受的。
    """
    from .ipa import word_ipa

    by_id = {s["id"]: s for s in segments}
    kept, dropped = [], []

    for c in cards:
        hit = locate(c["term"], segments)
        if hit is None:
            dropped.append(c["term"])            # 原文中确实找不到 → 丢弃
            continue
        seg_id = hit[0]
        # 若模型给的 seg 也命中同一词条,尊重模型的选择(它见过上下文)
        if c.get("seg") in by_id and locate(c["term"], [by_id[c["seg"]]]) is not None:
            seg_id = c["seg"]
        seg = by_id[seg_id]
        c["seg"] = seg_id
        c["quote"] = seg["en"]
        c["start"], c["end"] = seg["start"], seg["end"]
        c["ipa"] = word_ipa(c["term"])
        # 有权威词表就以词表为准,LLM 的考级标签只作兜底
        if wordlists:
            key = " ".join(_tokens(c["term"]))
            tags = sorted({n for n, ws in wordlists.items()
                           if key in ws or _norm(c["term"]) in ws})
            if tags:
                c["exam"] = tags
        c["exam"] = c.get("exam") or []
        c.setdefault("type_zh", TYPE_ZH.get(c.get("type", "word"), "单词"))
        kept.append(c)

    seen, uniq = set(), []
    for c in kept:
        k = (" ".join(_tokens(c["term"])), c["type"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq, dropped


def load_wordlists(folder):
    """可选:把权威考纲词表放进 wordlists/ 目录(每行一个词,文件名即标签)。

    有词表时考级标签 100% 准确且零成本;没有就用 LLM 的判断兜底。
    """
    import pathlib
    d = pathlib.Path(folder)
    if not d.exists():
        return {}
    out = {}
    for f in d.glob("*.txt"):
        words = {_norm(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()}
        if words:
            out[f.stem] = words
    return out
