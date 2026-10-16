# -*- coding: utf-8 -*-
"""来源判重的离线测试:同一个视频的各种链接形态必须归成同一个标识。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from teco.platforms import source_key, detect, canonical_url

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else:    fail += 1; print(f"  ✗ {name}  {extra}")


VID = "youtube:pPdAmlUcx7s"
same = [
    "https://www.youtube.com/watch?v=pPdAmlUcx7s",
    "https://www.youtube.com/watch?v=pPdAmlUcx7s&t=100s",
    "https://youtu.be/pPdAmlUcx7s",
    "https://youtu.be/pPdAmlUcx7s?si=AbCdEf",
    "https://m.youtube.com/watch?v=pPdAmlUcx7s&feature=share",
    "https://www.youtube.com/shorts/pPdAmlUcx7s",
    "https://www.youtube.com/embed/pPdAmlUcx7s",
]

print("【YouTube 的各种链接形态】")
for u in same:
    check(u[:58], source_key(u) == VID, source_key(u))
check("与 data.json 的 media 同形", source_key(same[0]) == VID)
check("不同视频不会撞", source_key("https://youtu.be/oY-xyQUEVcs") != VID)

print("\n【普通网址归一】")
a = source_key("https://Example.com/videos/7/?utm_source=weixin&utm_medium=x")
b = source_key("https://www.example.com/videos/7")
check("去掉 www、末尾斜杠与 utm 参数", a == b, f"{a} vs {b}")
check("保留真正有意义的参数",
      source_key("https://x.com/v?id=9") != source_key("https://x.com/v?id=8"))
check("参数顺序不影响结果",
      source_key("https://x.com/v?a=1&b=2") == source_key("https://x.com/v?b=2&a=1"))
check("空网址返回空", source_key("") == "" and source_key(None) == "")

print("\n【存库用的干净链接】")
check("剥掉 list 和起始时间",
      canonical_url("https://www.youtube.com/watch?v=pPdAmlUcx7s&list=PLxxxx&t=90")
      == "https://www.youtube.com/watch?v=pPdAmlUcx7s")
check("youtu.be 也收成 watch?v=",
      canonical_url("https://youtu.be/pPdAmlUcx7s?si=abc")
      == "https://www.youtube.com/watch?v=pPdAmlUcx7s")
check("shorts 同样",
      canonical_url("https://www.youtube.com/shorts/pPdAmlUcx7s")
      == "https://www.youtube.com/watch?v=pPdAmlUcx7s")
check("空网址返回空", canonical_url("") == "" and canonical_url(None) == "")

print("\n【平台识别没被改坏】")
check("youtube", detect("https://youtu.be/pPdAmlUcx7s")[0] == "youtube")
check("tiktok", detect("https://www.tiktok.com/@a/video/123")[0] == "tiktok")
check("douyin", detect("https://www.douyin.com/video/123")[0] == "douyin")
check("其它走通用", detect("https://anchor.fm/x/ep.mp3")[0] == "generic")

print(f"\n通过 {ok} / {ok+fail}")
sys.exit(1 if fail else 0)
