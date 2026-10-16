# -*- coding: utf-8 -*-
"""平台识别:决定一个网址该走哪条路。

三个平台的最优解完全不同,这个判断决定了后面所有事:

  youtube  → 不下载。取官方字幕 + 嵌入官方播放器。
             省掉最慢的语音识别,不占磁盘,且嵌入是平台官方支持的用法。
  tiktok   → 必须下载。嵌入播放器不给程序化控制,做不了单句循环。
  douyin   → 同上,且适配最不稳定。
  其它     → 交给 ingest.py 的通用四策略。
"""
import re, urllib.parse

YT_ID = re.compile(r"(?:v=|/shorts/|/embed/|youtu\.be/|/live/)([A-Za-z0-9_-]{11})")


def youtube_id(url):
    """从各种形态的 YouTube 链接里取出 11 位视频 ID。"""
    m = YT_ID.search(url or "")
    return m.group(1) if m else None


def detect(url):
    """返回 (平台标识, 附加信息)。"""
    if not url:
        return "unknown", {}
    host = (urllib.parse.urlparse(url).hostname or "").lower().lstrip("www.")
    if "youtube.com" in host or "youtu.be" in host:
        vid = youtube_id(url)
        return ("youtube", {"video_id": vid}) if vid else ("youtube_unknown", {})
    if "tiktok.com" in host:
        return "tiktok", {}
    if "douyin.com" in host or "iesdouyin.com" in host:
        return "douyin", {}
    if "bilibili.com" in host or "b23.tv" in host:
        return "bilibili", {}
    return "generic", {}


PLAN = {
    "youtube":   "取官方字幕 + 嵌入官方播放器(不下载,跳过语音识别)",
    "youtube_unknown": "是 YouTube 链接但取不到视频 ID,请用带 v= 或 /shorts/ 的完整链接",
    "tiktok":    "下载音频后走完整流水线(需要 yt-dlp)",
    "douyin":    "下载音频后走完整流水线(需要 yt-dlp;抖音适配不稳定,可能失败)",
    "bilibili":  "下载音频后走完整流水线(需要 yt-dlp)",
    "generic":   "通用解析:直链 / 订阅源 / 页面内地址 / HLS",
    "unknown":   "无法识别",
}


def describe(url):
    kind, info = detect(url)
    return kind, info, PLAN.get(kind, "")


# 分享链接上挂的这些参数不改变「是哪个视频」,去重时必须先剥掉
JUNK_PARAMS = {
    "t", "start", "time_continue", "si", "feature", "app", "ab_channel",
    "fbclid", "gclid", "igshid", "spm", "share_token", "share_id", "vd_source",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
}


def canonical_url(url):
    """存进队列和 data.json 的干净链接。

    分享链接常带着 &list= 播放列表、&t= 起始时间、si= 分享追踪。
    这些不影响「是哪个视频」,但原样交给 yt-dlp 取字幕时,&list= 会让它
    把整个播放列表的字幕都抓回来——库里就出现过一期 18 分钟视频配了
    112 分钟字幕。YouTube 一律收成 watch?v=ID;其它网站只剥追踪参数。
    """
    if not url:
        return ""
    vid = youtube_id(url)
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    p = urllib.parse.urlsplit(url.strip())
    if not p.scheme or not p.netloc:
        return url.strip()
    host = (p.hostname or "").lower()
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
            if k.lower() not in JUNK_PARAMS]
    q = urllib.parse.urlencode(keep)
    path = p.path or "/"
    return urllib.parse.urlunsplit((p.scheme, host, path, q, ""))


def source_key(url):
    """把一个网址归一成「这是哪个视频」的稳定标识,用于判重。

    同一个视频会以很多种形态出现:youtu.be 短链、/shorts/、带 &t=100s 的
    分享链接、末尾多一个斜杠……直接比字符串会把它们当成不同的视频,
    于是同一期被反复解析、反复花钱。
    """
    if not url:
        return ""
    vid = youtube_id(url)
    if vid:
        return f"youtube:{vid}"        # 与 data.json 里 YouTube 期的 media 字段同形
    p = urllib.parse.urlsplit(url.strip())
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(p.query)
            if k.lower() not in JUNK_PARAMS]
    keep.sort()
    path = p.path.rstrip("/") or "/"
    q = urllib.parse.urlencode(keep)
    return f"url:{host}{path}" + (f"?{q}" if q else "")
