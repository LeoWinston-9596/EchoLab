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
