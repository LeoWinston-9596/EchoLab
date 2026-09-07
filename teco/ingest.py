# -*- coding: utf-8 -*-
"""在线素材获取:给一个网址,拿到本地媒体文件。

按「越干净越优先」的顺序尝试四种策略:

  1. 直链      URL 本身就是 mp3/mp4/m4a…,或响应头是 audio/* video/*
  2. 播客 RSS  订阅源里的 enclosure 本就是给人下载的,最正当的来源
  3. 页面解析  从 HTML 里找 <video>/<audio>、og:video、JSON-LD contentUrl
  4. HLS       m3u8 播放列表,交给 ffmpeg 合流
  5. 兜底      委托给系统里已安装的 yt-dlp(需用户自行安装)

关于合规:本模块只做「取回一个公开可访问的媒体地址」这件事,不绕过任何
付费墙、登录态或 DRM。各站点的服务条款与内容版权由使用者自行负责;
若要把成果做成对外产品,内容授权必须先于技术方案解决。
"""
import os, re, json, html, mimetypes, pathlib, shutil, subprocess, urllib.parse
import xml.etree.ElementTree as ET
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MEDIA_EXT = (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus",
             ".mp4", ".m4v", ".mov", ".mkv", ".webm")
MAX_BYTES = 800 * 1024 * 1024          # 单个文件上限,防止误抓一个超大文件
TIMEOUT = 30


class IngestError(RuntimeError):
    pass


# ---------------------------------------------------------------- 工具

def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "*/*"})
    return s


def safe_name(name, fallback="media"):
    name = urllib.parse.unquote(name or "")
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", name).strip(" ._")
    return (name or fallback)[:80]


def _ext_from(url, content_type=""):
    path = urllib.parse.urlparse(url).path
    ext = pathlib.Path(path).suffix.lower()
    if ext in MEDIA_EXT:
        return ext
    guess = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
    return guess or ".bin"


def looks_like_media(url):
    return pathlib.Path(urllib.parse.urlparse(url).path).suffix.lower() in MEDIA_EXT


# ---------------------------------------------------------------- 1. 直链

def download(url, out_dir, name=None, session=None, on_progress=None):
    """流式下载,带体积上限与进度回调。返回落盘路径。"""
    s = session or _session()
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with s.get(url, stream=True, timeout=TIMEOUT, allow_redirects=True) as r:
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "")
        total = int(r.headers.get("Content-Length") or 0)
        if total > MAX_BYTES:
            raise IngestError(f"文件过大({total/1e6:.0f} MB),超过 {MAX_BYTES/1e6:.0f} MB 上限")
        base = name or safe_name(pathlib.Path(urllib.parse.urlparse(url).path).stem)
        dest = out_dir / (base + _ext_from(url, ctype))
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                if not chunk:
                    continue
                done += len(chunk)
                if done > MAX_BYTES:
                    f.close(); dest.unlink(missing_ok=True)
                    raise IngestError("文件超过体积上限,已中止下载")
                f.write(chunk)
                if on_progress and total:
                    on_progress(done, total)
    return dest


def head_content_type(url, session=None):
    """先探一下类型,避免把一个 HTML 页面当成媒体下载下来。"""
    s = session or _session()
    try:
        r = s.head(url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code >= 400:                       # 有些站不支持 HEAD
            r = s.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True)
            r.close()
        return r.headers.get("Content-Type", ""), r.url
    except requests.RequestException:
        return "", url


# ---------------------------------------------------------------- 2. 播客 RSS

def parse_rss(xml_text):
    """解析 RSS/Atom,返回 [{title, url, length, type, published}]。

    播客的 <enclosure> 就是设计给客户端下载的,这是最正当的一类来源。
    """
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError as e:
        raise IngestError(f"不是有效的 RSS/Atom:{e}")
    eps = []
    for item in root.iter():
        tag = item.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title, url, length, mtype, pub = "", "", 0, "", ""
        for ch in item:
            t = ch.tag.split("}")[-1]
            if t == "title":
                title = (ch.text or "").strip()
            elif t == "enclosure":
                url = ch.attrib.get("url", "")
                mtype = ch.attrib.get("type", "")
                length = int(ch.attrib.get("length") or 0)
            elif t == "link" and ch.attrib.get("rel") == "enclosure":
                url = ch.attrib.get("href", "")
                mtype = ch.attrib.get("type", "")
            elif t in ("pubDate", "published", "updated"):
                pub = (ch.text or "").strip()
        if url:
            eps.append({"title": title or "(无标题)", "url": url,
                        "length": length, "type": mtype, "published": pub})
    if not eps:
        raise IngestError("这个订阅源里没有找到可下载的音频条目")
    return eps


# ---------------------------------------------------------------- 3. 页面解析

_OG = re.compile(r'<meta[^>]+(?:property|name)=["\'](og:video(?::secure_url|:url)?|'
                 r'twitter:player:stream)["\'][^>]+content=["\']([^"\']+)', re.I)
_SRC = re.compile(r'<(?:video|audio|source)[^>]+src=["\']([^"\']+)', re.I)
_M3U8 = re.compile(r'https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', re.I)
_MP4 = re.compile(r'https?://[^\s"\'<>\\]+\.(?:mp4|m4a|mp3|webm)[^\s"\'<>\\]*', re.I)


def extract_from_page(html_text, base_url=""):
    """从 HTML 里挖出候选媒体地址,按可靠度排序返回。"""
    found, seen = [], set()

    def add(u, why):
        if not u:
            return
        u = html.unescape(u).strip()
        if u.startswith("//"):
            u = "https:" + u
        elif base_url and not u.startswith("http"):
            u = urllib.parse.urljoin(base_url, u)
        if u.startswith("http") and u not in seen:
            seen.add(u)
            found.append({"url": u, "source": why})

    for m in _OG.finditer(html_text):                       # 最可靠:站点自己声明的
        add(m.group(2), "og:video / twitter:player")
    for m in _SRC.finditer(html_text):                      # 次可靠:媒体标签
        add(m.group(1), "<video>/<audio> src")
    for m in re.finditer(r'"contentUrl"\s*:\s*"([^"]+)"', html_text):   # JSON-LD
        add(m.group(1).replace("\\/", "/"), "JSON-LD contentUrl")
    for m in _MP4.finditer(html_text):                      # 兜底:正文里的直链
        add(m.group(0), "页面内直链")
    for m in _M3U8.finditer(html_text):
        add(m.group(0), "HLS 播放列表")
    return found


# ---------------------------------------------------------------- 4. HLS

def download_hls(m3u8_url, out_dir, name="media"):
    """m3u8 是分片流,必须用 ffmpeg 合成一个文件。"""
    from .tools import find_ffmpeg
    ff = find_ffmpeg()
    if not ff:
        raise IngestError("这是 HLS 流(m3u8),合流需要 ffmpeg。请先安装 ffmpeg 后重试。")
    out_dir = pathlib.Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / (safe_name(name) + ".mp4")
    r = subprocess.run([ff, "-y", "-user_agent", UA, "-i", m3u8_url,
                        "-c", "copy", "-bsf:a", "aac_adtstoasc", str(dest)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        raise IngestError(f"ffmpeg 合流失败:{r.stderr[-300:]}")
    return dest


# ---------------------------------------------------------------- 5. yt-dlp 兜底

def has_ytdlp():
    return shutil.which("yt-dlp") or shutil.which("youtube-dl")


def via_ytdlp(url, out_dir, audio_only=True):
    """委托给系统里已安装的 yt-dlp。

    本项目不捆绑、不自动安装它。是否使用、用在哪些站点,由使用者自行判断并
    承担相应的服务条款与版权责任。
    """
    exe = has_ytdlp()
    if not exe:
        raise IngestError(
            "这个网址无法直接解析。若你确认有权获取该内容,可自行安装 yt-dlp 后重试:\n"
            "    pip install yt-dlp\n"
            "本项目不捆绑它,使用时请遵守目标网站的服务条款与版权规定。")
    out_dir = pathlib.Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = str(out_dir / "%(title).60s.%(ext)s")
    cmd = [exe, "--no-playlist", "-o", tmpl, "--restrict-filenames"]
    if audio_only:
        cmd += ["-f", "bestaudio/best", "-x", "--audio-format", "mp3"]
    else:
        cmd += ["-f", "bestvideo[height<=720]+bestaudio/best"]
    cmd.append(url)
    before = set(out_dir.glob("*"))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise IngestError(f"yt-dlp 失败:{(r.stderr or r.stdout)[-400:]}")
    new = [p for p in out_dir.glob("*") if p not in before and p.is_file()]
    if not new:
        raise IngestError("yt-dlp 执行完成,但没有产生新文件")
    return max(new, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------- 调度

def ingest(url, out_dir="downloads", prefer_audio=True, rss_index=0, verbose=True):
    """主入口:给一个网址,返回本地媒体文件路径。"""
    s = _session()
    log = (lambda m: print(f"  {m}")) if verbose else (lambda m: None)

    # 1) 直链
    if looks_like_media(url):
        log("识别为媒体直链,开始下载")
        return download(url, out_dir, session=s)

    ctype, final_url = head_content_type(url, s)
    if ctype.startswith(("audio/", "video/")):
        log(f"响应头为 {ctype},按直链下载")
        return download(final_url, out_dir, session=s)

    # 2) RSS
    if "xml" in ctype or url.rstrip("/").endswith((".xml", "/rss", "/feed")):
        log("识别为订阅源,解析条目")
        eps = parse_rss(s.get(url, timeout=TIMEOUT).text)
        log(f"共 {len(eps)} 期,取第 {rss_index+1} 期:{eps[rss_index]['title']}")
        return download(eps[rss_index]["url"], out_dir,
                        name=safe_name(eps[rss_index]["title"]), session=s)

    # 3) 页面解析
    log("按网页解析,查找页面内的媒体地址")
    try:
        page = s.get(url, timeout=TIMEOUT).text
    except requests.RequestException as e:
        raise IngestError(f"打不开这个网址:{e}")
    cands = extract_from_page(page, url)
    if cands:
        log(f"找到 {len(cands)} 个候选,优先尝试:{cands[0]['source']}")
    for c in cands[:4]:
        try:
            if ".m3u8" in c["url"].lower():
                return download_hls(c["url"], out_dir)
            return download(c["url"], out_dir, session=s)
        except Exception as e:
            log(f"候选失败({c['source']}):{e}")

    # 4) 兜底
    log("页面里没有可直接取用的地址,尝试 yt-dlp")
    return via_ytdlp(url, out_dir, audio_only=prefer_audio)
