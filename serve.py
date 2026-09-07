#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地播放器服务:python3 serve.py

必须支持 HTTP Range 请求,否则浏览器无法在视频里拖动进度、
单句循环也会失效(每次跳转都要重新下载整个文件)。
Python 自带的 SimpleHTTPRequestHandler 不支持,所以这里自己实现。
"""
import http.server, socketserver, os, re, sys, json, webbrowser, pathlib, mimetypes
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
PORT = int(os.environ.get("PORT", 8777))
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def lan_ips():
    """本机在局域网里的地址。

    手机上的 localhost 指的是手机自己,所以必须给出电脑的局域网 IP。
    做法是向外发一个不实际发送的 UDP 连接,让系统告诉我们用哪张网卡出去。
    """
    import socket
    ips = []
    for probe in ("8.8.8.8", "114.114.114.114"):
        try:
            s_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s_.settimeout(0.4)
            s_.connect((probe, 80))
            ip = s_.getsockname()[0]
            s_.close()
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
        except Exception:
            pass
    try:                                    # 兜底:再取一遍主机名解析出的地址
        import socket as sk
        for info in sk.getaddrinfo(sk.gethostname(), None, sk.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips
from teco import inbox


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # ---------- 书签栏一键:接收网址 ----------
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # 书签是在 youtube.com 等页面上运行的,必须允许跨域读取响应
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _api(self, parsed):
        q = urllib.parse.parse_qs(parsed.query)
        token = (q.get("token") or [""])[0]
        if token != inbox.get_token():
            self._json({"ok": False, "message": "令牌不对,请到 /setup 重新拖一次书签"}, 403)
            return True
        if parsed.path == "/api/add":
            url = (q.get("url") or [""])[0]
            if not url.startswith("http"):
                self._json({"ok": False, "message": "这不是一个网址"}, 400)
                return True
            self._json(inbox.add(url, (q.get("title") or [""])[0]))
            return True
        if parsed.path == "/api/queue":
            self._json({"ok": True, "items": inbox.list_all()})
            return True
        return False

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if self._api(parsed):
                return
        if parsed.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/library.html")
            self.end_headers()
            return
        if parsed.path == "/setup":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(setup_page(self.headers.get("Host")).encode())
            return
        path = self.translate_path(self.path)
        rng = self.headers.get("Range")
        if not rng or not os.path.isfile(path):
            return super().do_GET()

        m = RANGE_RE.match(rng)
        if not m:
            return super().do_GET()
        size = os.path.getsize(path)
        start = int(m.group(1)) if m.group(1) else 0
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        if start > end:
            self.send_error(416)
            return
        length = end - start + 1
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"

        self.send_response(206)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return          # 浏览器换片段了,正常现象
                remaining -= len(chunk)

    def log_message(self, *a):
        pass                        # 保持输出干净


def setup_page(host=None):
    """一页说明:把书签拖到书签栏,以后在视频页点一下就入队。

    书签里的地址取自你访问本页时用的主机名——在手机上用局域网 IP 打开这一页,
    生成的书签就指向那个 IP,而不是写死的 localhost。
    """
    token = inbox.get_token()
    host = host or f"localhost:{PORT}"
    js = ("javascript:(function(){var t=document.createElement('div');"
          "t.style.cssText='position:fixed;z-index:2147483647;left:50%;top:24px;"
          "transform:translateX(-50%);background:#161b24;color:#e8edf5;padding:12px 18px;"
          "border-radius:10px;font:14px system-ui;box-shadow:0 6px 24px rgba(0,0,0,.35)';"
          "t.textContent='EchoLab 接收中…';document.body.appendChild(t);"
          "var go=function(m){t.textContent=m;setTimeout(function(){t.remove()},2600)};"
          "var u='http://HOSTVAL/api/add?token=TOKENVAL&url='+"
          "encodeURIComponent(location.href)+'&title='+encodeURIComponent(document.title);"
          "fetch(u).then(function(r){return r.json()}).then(function(j){go('EchoLab:'+j.message)})"
          ".catch(function(){go('连不上 EchoLab,请确认 serve.py 正在运行');"
          "window.open(u,'_blank')})})()"
          ).replace("HOSTVAL", host).replace("TOKENVAL", token)
    import html as H
    return f"""<!doctype html><meta charset=utf-8><title>EchoLab · 安装书签</title>
<style>body{{font:15px/1.7 system-ui,-apple-system,"PingFang SC","Microsoft YaHei";
max-width:720px;margin:48px auto;padding:0 20px;color:#1a2130}}
a.bm{{display:inline-block;background:#1f3864;color:#fff;padding:11px 22px;border-radius:9px;
text-decoration:none;font-weight:600;font-size:16px}}
code,pre{{background:#f0f2f6;padding:2px 6px;border-radius:5px;font-size:13px}}
pre{{padding:12px;overflow-x:auto;white-space:pre-wrap;word-break:break-all}}
h2{{margin-top:34px;font-size:17px}} .tip{{color:#5b6779;font-size:13.5px}}</style>
<h1>把这个拖到书签栏</h1>
<p>拖一次就好。以后在 YouTube / TikTok / 抖音的视频页面点它一下,链接就进了本地队列。</p>
<p><a class="bm" href="{H.escape(js, quote=True)}">📥 存进 EchoLab</a></p>
<p class="tip">拖不动的话:右键书签栏 → 添加网页 → 名称随便填,网址粘贴下面这段。</p>
<pre>{H.escape(js)}</pre>
<h2>然后怎么处理</h2>
<p>队列里的东西不会自动开跑——处理一个视频要几十秒到几分钟,
所以点书签只负责入队,你想跑的时候再开:</p>
<pre>python worker.py            # 处理完队列里所有待处理的
python worker.py --watch    # 一直守着,来一个处理一个</pre>
<h2>几个前提</h2>
<ul>
<li>这个服务(<code>python serve.py</code>)得开着,书签才有地方送。</li>
<li>浏览器建议用 Chrome 或 Edge。它们把 <code>localhost</code> 当作可信来源,
HTTPS 页面也能访问本地服务;Safari 会拦,拦了会自动改为新开标签页兜底。</li>
<li>YouTube 走取字幕 + 嵌入播放,不下载;TikTok / 抖音需要你自行安装
<code>yt-dlp</code>,并自行判断是否符合对应平台的条款。</li>
</ul>
<h2>手机 / 平板怎么打开</h2>
<p><b>不能用 localhost</b> —— 在手机上 localhost 指的是手机自己。要用这台电脑的
局域网地址:</p>
<pre>{"".join(f"http://{ip}:{PORT}/player.html" + chr(10) for ip in lan_ips()) or "（暂时探测不到局域网地址）"}</pre>
<p class="tip">连不上的话多半是 Windows 防火墙拦了入站。用管理员身份打开 PowerShell 执行一次:</p>
<pre>New-NetFirewallRule -DisplayName "EchoLab" -Direction Inbound -LocalPort {PORT} -Protocol TCP -Action Allow</pre>
<p class="tip">另外确认手机和电脑连的是同一个 Wi-Fi,且路由器没有开「AP 隔离 / 访客网络」——
那个功能会禁止同网设备互访。</p>
<p class="tip">令牌只在你本机,换了机器要重新拖一次书签。</p>"""


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    if not (ROOT / "library" / "index.json").exists():
        print("素材库还是空的。先运行 python3 demo.py 生成一期演示内容。\n")
    url = f"http://localhost:{PORT}/player.html"
    print(f"\n  素材库       http://localhost:{PORT}/library.html")
    print(f"  播放器       {url}")
    print(f"  安装书签     http://localhost:{PORT}/setup")
    ips = lan_ips()
    if ips:
        print("\n  手机 / 平板(同一 Wi-Fi,不能用 localhost):")
        for ip in ips:
            print(f"    http://{ip}:{PORT}/library.html")
        print("\n  连不上多半是 Windows 防火墙拦了入站。管理员 PowerShell 执行一次:")
        print(f'    New-NetFirewallRule -DisplayName "EchoLab" -Direction Inbound '
              f"-LocalPort {PORT} -Protocol TCP -Action Allow")
    else:
        print("\n  (探测不到局域网地址,可能没连 Wi-Fi)")
    print("\n  Ctrl+C 停止。\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        Server(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        sys.exit(0)
