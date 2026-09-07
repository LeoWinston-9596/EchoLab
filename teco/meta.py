# -*- coding: utf-8 -*-
"""每期的元数据:主题标签、难度、建议学习时长、一句话简介。

参考产品里这些是作者手工填的;这里全部自动生成——
难度和时长用纯计算(零成本),只有主题和简介走一次很短的 LLM 调用。
"""

SYSTEM = """你在为英语学习素材库标注一期 vlog。根据字幕内容输出 JSON:
{"topics":["主题标签,2-4个,用中文,从 生活/日常/美食/旅行/健身/宠物/美妆/购物/住房/职场/情感/人文/科技/教育/户外/服饰 中选,不够用可自拟"],
 "summary":"一句话中文简介,20字以内,说清这期在讲什么"}
只输出 JSON。"""


def speech_rate(words, duration):
    """语速(词/分钟)——判断听力难度最直接的指标。"""
    return round(len(words) / (duration / 60.0), 1) if duration else 0.0


def estimate_difficulty(words, duration, cards):
    """1-5 星难度。用语速和知识点密度计算,不花钱、结果稳定可复现。

    参考区间:母语者日常口语约 140-170 wpm,150 以上对中国学习者已偏快。
    """
    wpm = speech_rate(words, duration)
    density = len(cards) / max(len(words) / 100.0, 1)   # 每百词的知识点数
    score = 0
    for th in (120, 145, 165, 185):                      # 语速档
        score += wpm > th
    for th in (2.5, 4.0, 6.0):                           # 知识点密度档
        score += density > th
    return max(1, min(5, round(score * 5 / 7) or 1)), wpm, round(density, 2)


def suggested_minutes(duration):
    """建议学习时长:影子跟读法的经验值约为视频时长的 4 倍,向 5 分钟取整。"""
    m = max(10, round(duration / 60.0 * 4))
    return int(round(m / 5.0) * 5)


def build(llm, segments, words, duration, cards, verbose=True):
    diff, wpm, density = estimate_difficulty(words, duration, cards)
    topics, summary = [], ""
    if llm is not None:
        try:
            body = "\n".join(s["en"] for s in segments[:40])
            data = llm.chat_json(SYSTEM, f"字幕内容:\n{body}")
            topics = [t for t in data.get("topics", []) if isinstance(t, str)][:4]
            summary = (data.get("summary") or "").strip()
        except Exception as e:
            if verbose:
                print(f"    [meta] 生成主题失败,跳过({e})")
    return {
        "topics": topics,
        "summary": summary,
        "difficulty": diff,
        "wpm": wpm,
        "card_density": density,
        "suggested_minutes": suggested_minutes(duration),
    }
