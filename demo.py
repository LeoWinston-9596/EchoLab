#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成一期演示内容 —— 不需要 API key,也不需要下载识别模型。

用途:在花任何钱之前,先打开播放器看看学习体验长什么样。
音频用本机 espeak-ng 合成(机器音,仅供演示);字幕时间轴是逐句合成后
实测出来的,所以同步是准的。文本与翻译为内置的演示脚本。
"""
import json, pathlib, subprocess, sys, time, shutil, wave, contextlib

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from teco.ipa import to_ipa
from teco.tools import find_ffmpeg, find_espeak
from teco import cards as cards_mod, meta as meta_mod

OUT = ROOT / "library" / "demo"

SENTENCES = [
    ("Now I want to talk about some other things I learned after spending some more time with her.",
     "现在我想聊聊和她相处久了之后,我学到的另外一些事。"),
    ("When I first got her, I actually had a collar on her with a bell,",
     "刚把她带回家的时候,我给她戴了一个带铃铛的项圈,"),
    ("and I thought that was such a great idea, right?",
     "我当时觉得这主意特别棒,对吧?"),
    ("Because she was just so tiny.",
     "因为她实在太小只了。"),
    ("She was just like a little rat that I was nervous that I would step on her.",
     "她小得就像一只小老鼠,我总担心自己会踩到她。"),
    ("But actually, having bells on collars can be really bad for their hearing.",
     "但其实,项圈上挂铃铛对猫的听力伤害很大。"),
    ("So right when I found that out, I took it off.",
     "所以我一发现这件事,就马上把它摘掉了。"),
    ("I would recommend using a fluffy cone instead.",
     "我更推荐用那种毛茸茸的伊丽莎白圈来代替。"),
    ("I feel like that's just really uncomfortable for them.",
     "我觉得那种硬的对它们来说真的很不舒服。"),
]

DEMO_CARDS = [
    dict(term="spend time with", type="collocation", seg=0, pos="phrase",
         def_en="to pass time in someone's company",
         def_zh="和……相处;花时间陪……", ex_en="I want to spend more time with my family.",
         ex_zh="我想多花点时间陪家人。", exam=["四级", "六级", "雅思"],
         note="spend + 时间 + doing 是固定结构,注意用动名词。"),
    dict(term="collar", type="word", seg=1, pos="noun",
         def_en="a band put around an animal's neck", def_zh="项圈;衣领",
         ex_en="The dog's collar has a name tag on it.", ex_zh="这只狗的项圈上挂着名牌。",
         exam=["四级"], note="给宠物戴的和衬衫领子是同一个词。"),
    dict(term="such a great idea", type="phrase", seg=2, pos="phrase",
         def_en="a very good idea", def_zh="一个特别棒的主意",
         ex_en="Bringing an umbrella was such a great idea.", ex_zh="带伞真是个明智的决定。",
         exam=[], note="such a + 形容词 + 名词,口语里表强调的常用结构。"),
    dict(term="right?", type="discourse_marker", seg=2, pos="",
         def_en="tag used to seek agreement from the listener",
         def_zh="对吧?(寻求认同的口头语)",
         ex_en="That sounds reasonable, right?", ex_zh="这听起来挺合理的,对吧?",
         exam=[], note="vlog 里极高频,句尾上扬,用来拉近与观众距离。"),
    dict(term="just like", type="pattern", seg=4, pos="",
         def_en="used to introduce a comparison, roughly 'exactly like'",
         def_zh="就像……一样", ex_en="He talks just like his dad.", ex_zh="他说话跟他爸一模一样。",
         exam=[], note="口语中也常用作填充语,可弱化为“就……”。"),
    dict(term="be nervous that", type="collocation", seg=4, pos="phrase",
         def_en="to worry that something bad might happen",
         def_zh="担心会……", ex_en="I was nervous that I would forget my lines.",
         ex_zh="我当时很担心自己会忘词。", exam=["四级", "六级", "雅思"],
         note="后接从句;若接动词要用 nervous about doing。"),
    dict(term="step on", type="phrasal_verb", seg=4, pos="verb",
         def_en="to put your foot on something", def_zh="踩到;踏上",
         ex_en="Careful not to step on the cat's tail.", ex_zh="小心别踩到猫尾巴。",
         exam=["四级"], note=""),
    dict(term="be bad for", type="collocation", seg=5, pos="phrase",
         def_en="to be harmful to", def_zh="对……有害",
         ex_en="Staying up late is bad for your skin.", ex_zh="熬夜对皮肤不好。",
         exam=["四级", "六级"], note="反义表达是 be good for。"),
    dict(term="find out", type="phrasal_verb", seg=6, pos="verb",
         def_en="to learn a fact for the first time", def_zh="发现;查明",
         ex_en="I found out that the shop had already closed.", ex_zh="我才发现那家店已经关门了。",
         exam=["四级", "六级", "考研"], note="强调“得知”这个瞬间,与 discover 语气更口语。"),
    dict(term="take off", type="phrasal_verb", seg=6, pos="verb",
         def_en="to remove something you are wearing", def_zh="摘下;脱掉",
         ex_en="Please take off your shoes at the door.", ex_zh="请在门口把鞋脱掉。",
         exam=["四级", "六级"], note="一词多义:也表示“(飞机)起飞”“(事业)腾飞”。"),
    dict(term="I would recommend", type="pattern", seg=7, pos="",
         def_en="a polite way to give advice", def_zh="我建议……(礼貌给建议)",
         ex_en="I would recommend booking the ticket early.", ex_zh="我建议早点订票。",
         exam=["雅思", "托福"], note="比 you should 委婉得多,写作口语都好用。"),
    dict(term="instead", type="word", seg=7, pos="adverb",
         def_en="in place of something else", def_zh="作为替代;反而",
         ex_en="The café was closed, so we went to the park instead.",
         ex_zh="咖啡馆关门了,我们就改去公园了。", exam=["四级"], note="放句末最自然。"),
    dict(term="I feel like", type="pattern", seg=8, pos="",
         def_en="used to give a softened personal opinion", def_zh="我觉得……(语气较软的表达观点)",
         ex_en="I feel like we should leave earlier.", ex_zh="我觉得我们应该早点走。",
         exam=[], note="比 I think 更随意,是当代口语的高频开场。"),
]


def dur(p):
    """读 wav 头算时长——用 Python 标准库,不依赖 ffprobe。"""
    with contextlib.closing(wave.open(str(p), "rb")) as w:
        return w.getnframes() / float(w.getframerate())


def concat_wavs(paths, out):
    """纯 Python 拼接 wav,同样不依赖 ffmpeg。"""
    with contextlib.closing(wave.open(str(paths[0]), "rb")) as first:
        params = first.getparams()
    with contextlib.closing(wave.open(str(out), "wb")) as w:
        w.setparams(params)
        for p in paths:
            with contextlib.closing(wave.open(str(p), "rb")) as r:
                w.writeframes(r.readframes(r.getnframes()))
    return out


def main():
    if not find_espeak():
        sys.exit("需要 espeak-ng 才能合成演示音频。装好后重新运行即可"
                 "(Windows: winget install eSpeak-NG.eSpeak-NG)。")
    espeak = find_espeak()
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "_parts"
    tmp.mkdir(exist_ok=True)

    print("生成演示音频(逐句合成,以便得到准确的时间轴)...")
    segments, words, t = [], [], 0.0
    listing = []
    for i, (en, zh) in enumerate(SENTENCES):
        wav = tmp / f"{i:02d}.wav"
        subprocess.run([espeak, "-v", "en-us", "-s", "150", "-w", str(wav), en],
                       check=True, capture_output=True)
        d = dur(wav)
        listing.append(str(wav))
        # 句内按词长比例分配时间——句子边界是实测的,所以整体同步准确
        toks = en.split()
        total = sum(len(x) for x in toks)
        ws, acc = [], t
        for tok in toks:
            span = d * len(tok) / total
            ws.append({"i": len(words), "w": tok, "start": round(acc, 3),
                       "end": round(acc + span, 3), "p": 0.99})
            words.append(ws[-1])
            acc += span
        segments.append({
            "id": i, "w0": ws[0]["i"], "w1": ws[-1]["i"],
            "start": round(t, 3), "end": round(t + d, 3),
            "en": en, "zh": zh, "ipa": to_ipa(en),
            "words": [{"w": w["w"], "start": w["start"], "end": w["end"]} for w in ws],
        })
        t += d

    audio = concat_wavs(listing, tmp / "all.wav")

    # 有 ffmpeg 就做成带画面的 mp4;没有就直接用音频,播放器一样能放
    ff, media, poster = find_ffmpeg(), "media.wav", ""
    if ff:
        try:
            subprocess.run([ff, "-y", "-f", "lavfi", "-i",
                            f"color=c=0x141922:s=960x540:d={t:.2f}", "-i", str(audio),
                            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", str(OUT / "media.mp4")],
                           check=True, capture_output=True)
            subprocess.run([ff, "-y", "-ss", "1", "-i", str(OUT / "media.mp4"),
                            "-vframes", "1", "-vf", "scale=480:-1", str(OUT / "poster.jpg")],
                           check=True, capture_output=True)
            media, poster = "media.mp4", "poster.jpg"
        except subprocess.CalledProcessError:
            ff = None
    if not ff:
        shutil.copy2(audio, OUT / "media.wav")
        print("  (没有 ffmpeg,演示改用纯音频,不影响功能)")

    print("走真实的卡片校验流程(剔除原文不存在的词条、补音标)...")
    kept, dropped = cards_mod.verify_and_enrich([dict(c) for c in DEMO_CARDS], segments,
                                                cards_mod.load_wordlists(ROOT / "wordlists"))
    m = meta_mod.build(None, segments, words, t, kept)
    m["topics"] = ["宠物", "生活", "日常"]
    m["summary"] = "养猫新手分享:项圈铃铛其实伤听力"

    data = {"id": "demo", "title": "演示 · 养猫踩过的坑", "media": media,
            "poster": poster, "duration": round(t, 2), "language": "en",
            "created": time.strftime("%Y-%m-%d"), "n_segments": len(segments),
            "n_cards": len(kept), **m, "segments": segments, "cards": kept,
            "demo": True,
            "review": {"low_confidence_words": [], "dropped_cards": dropped}}
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)

    from process import update_index
    n = update_index()
    print(f"\n✓ 演示内容已生成:library/demo/  ({len(segments)} 句 · {len(kept)} 张卡片"
          f" · 难度 {'★'*m['difficulty']}{'☆'*(5-m['difficulty'])} · 素材库 {n} 期)")
    if dropped:
        print(f"  校验剔除:{dropped}")
    print("  运行 python3 serve.py 打开播放器\n")


if __name__ == "__main__":
    main()
