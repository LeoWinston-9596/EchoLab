# -*- coding: utf-8 -*-
"""ingest 的离线测试:不依赖网络,只验证解析与判定逻辑。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from teco.ingest import parse_rss, extract_from_page, looks_like_media, safe_name, IngestError

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else:    fail += 1; print(f"  ✗ {name}  {extra}")

print("【直链判定】")
check("mp3 直链", looks_like_media("https://a.com/ep1.mp3"))
check("带查询串的 mp4", looks_like_media("https://a.com/v.mp4?token=x"))
check("普通网页不算", not looks_like_media("https://a.com/watch?v=abc"))
check("m3u8 不算直链(需合流)", not looks_like_media("https://a.com/p.m3u8"))

print("\n【文件名清洗】")
check("去掉非法字符", safe_name('Ep 7: "Cats" / dogs?') == "Ep 7_ _Cats_ _ dogs", safe_name('Ep 7: "Cats" / dogs?'))
check("空值有兜底", safe_name("") == "media")
check("超长截断", len(safe_name("x"*200)) <= 80)

print("\n【RSS 解析】")
RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Chatty</title>
<item><title>Ep 1 - Coffee</title><pubDate>Mon, 01 Sep 2025 08:00:00 GMT</pubDate>
<enclosure url="https://cdn.x.com/ep1.mp3" length="8123456" type="audio/mpeg"/></item>
<item><title>Ep 2 - Moving house</title>
<enclosure url="https://cdn.x.com/ep2.mp3" length="9000000" type="audio/mpeg"/></item>
</channel></rss>"""
eps = parse_rss(RSS)
check("解析出 2 期", len(eps) == 2, str(len(eps)))
check("标题正确", eps[0]["title"] == "Ep 1 - Coffee")
check("音频地址正确", eps[1]["url"] == "https://cdn.x.com/ep2.mp3")
check("体积字段", eps[0]["length"] == 8123456)

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom Ep</title>
<link rel="enclosure" type="audio/mpeg" href="https://cdn.x.com/a1.mp3"/></entry></feed>"""
check("Atom 格式也支持", parse_rss(ATOM)[0]["url"] == "https://cdn.x.com/a1.mp3")

try:
    parse_rss("<html>not a feed</html>"); check("非订阅源应报错", False)
except IngestError:
    check("非订阅源应报错", True)

print("\n【页面解析】")
PAGE = """<html><head>
<meta property="og:video" content="https://cdn.x.com/og.mp4">
<script type="application/ld+json">{"contentUrl":"https:\\/\\/cdn.x.com\\/ld.mp4"}</script>
</head><body>
<video controls><source src="/media/local.mp4" type="video/mp4"></video>
<script>var hls="https://cdn.x.com/stream/index.m3u8";</script>
</body></html>"""
c = extract_from_page(PAGE, "https://site.com/watch/1")
urls = [x["url"] for x in c]
check("og:video 优先", urls[0] == "https://cdn.x.com/og.mp4", urls[0])
check("相对路径已补全", "https://site.com/media/local.mp4" in urls, str(urls))
check("JSON-LD 反斜杠已还原", "https://cdn.x.com/ld.mp4" in urls, str(urls))
check("抓到 m3u8", any(".m3u8" in u for u in urls))
check("结果去重", len(urls) == len(set(urls)))

c2 = extract_from_page("<html><body>什么都没有</body></html>", "https://site.com")
check("空页面返回空列表", c2 == [])

print(f"\n通过 {ok} / {ok+fail}")
sys.exit(1 if fail else 0)
