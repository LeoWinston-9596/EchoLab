# -*- coding: utf-8 -*-
"""YouTube 自动字幕滚动重播的去重测试:不联网,用构造的 json3 与词序列。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from teco.captions import parse_json3, drop_rolling_repeats, parse_vtt, yt_cmd

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else:    fail += 1; print(f"  ✗ {name}  {extra}")


def ev(t0, text, step):
    """造一个 json3 事件:step 是词间隔(毫秒),1 毫秒即「快照重播」。"""
    return {"tStartMs": t0,
            "segs": [{"utf8": w, "tOffsetMs": i * step}
                     for i, w in enumerate(text.split())]}


def words(ws):
    return [w["w"] for w in ws]


print("【一毫秒快照会被删掉】")
LINE = "As all New Yorkers know you can walk"
got = parse_json3({"events": [ev(2070, LINE, 1),        # 快照,逐词 1 毫秒
                              ev(2080, LINE, 120)]})    # 正片,逐词 120 毫秒
check("同一句只留一份", words(got) == LINE.split(), str(words(got)))
check("留下的是有真实时长的那份", got[1]["end"] - got[1]["start"] > 0.05,
      f'{got[1]["end"] - got[1]["start"]:.3f}')
check("下标重排过", [w["i"] for w in got] == list(range(len(got))))

print("\n【时间戳都正常的重播也要合并】")
A = "your dog is running in Central Park today"
got = parse_json3({"events": [ev(3000, A, 100), ev(3900, A, 130)]})
check("两份正常时间戳只留一份", words(got) == A.split(), str(len(got)))
check("留的是时间跨度大的那份", got[0]["start"] >= 3.9 - 1e-6, str(got[0]["start"]))

print("\n【短的重复不许动】")
keep = [{"i": i, "w": w, "start": i * 0.4, "end": i * 0.4 + 0.35, "p": 1.0}
        for i, w in enumerate("[music] [music] [music] [music] [music] "
                              "[music] [music] [music]".split())]
check("连续的 [music] 标记原样保留",
      len(drop_rolling_repeats([dict(w) for w in keep])) == len(keep))

five = "Hey buddy how are you Hey buddy how are you and then we left".split()
ws = [{"i": i, "w": w, "start": i * 0.4, "end": i * 0.4 + 0.35, "p": 1.0}
      for i, w in enumerate(five)]
check("5 个词的真实重复不算重播",
      words(drop_rolling_repeats([dict(w) for w in ws])) == five,
      str(len(drop_rolling_repeats([dict(w) for w in ws]))))

print("\n【正常字幕一个词都不该改】")
clean = ("I usually start by sifting the powder then pouring hot water over it "
         "and whisking until it turns foamy").split()
ws = [{"i": i, "w": w, "start": i * 0.35, "end": i * 0.35 + 0.3, "p": 1.0}
      for i, w in enumerate(clean)]
out = drop_rolling_repeats([dict(w) for w in ws])
check("原样返回", words(out) == clean, str(len(out)))

print("\n【去重后时间轴仍然可用】")
got = parse_json3({"events": [ev(2070, LINE, 1), ev(2080, LINE, 120),
                              ev(3000, A, 100), ev(3900, A, 130)]})
check("起点不倒退", all(a["start"] <= b["start"] for a, b in zip(got, got[1:])))
check("每个词 start < end", all(w["start"] < w["end"] for w in got))
check("下标连续", [w["i"] for w in got] == list(range(len(got))))

print("\n【vtt 那条路没被改坏】")
VTT = """WEBVTT

00:00:01.000 --> 00:00:03.000
Hello there friends

00:00:03.000 --> 00:00:05.000
this is a test
"""
vw = parse_vtt(VTT)
check("vtt 仍能解析", words(vw) == "Hello there friends this is a test".split(),
      str(words(vw)))

print("\n【yt-dlp 命令一律带 --no-playlist】")
cmd = yt_cmd("yt-dlp", "--skip-download", "https://youtu.be/x")
check("开关在可执行文件之后、其它参数之前",
      cmd[:3] == ["yt-dlp", "--no-playlist", "--skip-download"], str(cmd))
check("即使调用方忘了写,结果里也只有一次", cmd.count("--no-playlist") == 1)

print(f"\n通过 {ok} / {ok+fail}")
sys.exit(1 if fail else 0)
