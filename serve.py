#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地播放器服务:python3 serve.py

必须支持 HTTP Range 请求,否则浏览器无法在视频里拖动进度、
单句循环也会失效(每次跳转都要重新下载整个文件)。
Python 自带的 SimpleHTTPRequestHandler 不支持,所以这里自己实现。
"""
import http.server, socketserver, os, re, sys, webbrowser, pathlib, mimetypes

ROOT = pathlib.Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", 8777))
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
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


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    if not (ROOT / "library" / "index.json").exists():
        print("素材库还是空的。先运行 python3 demo.py 生成一期演示内容。\n")
    url = f"http://localhost:{PORT}/player.html"
    print(f"播放器已启动:{url}")
    print("同一个 Wi-Fi 下,手机/平板也可以用本机 IP 打开。按 Ctrl+C 停止。\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        Server(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        sys.exit(0)
