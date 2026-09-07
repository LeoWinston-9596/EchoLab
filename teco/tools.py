# -*- coding: utf-8 -*-
"""外部程序定位:让用户不必折腾 PATH。

顺序:PATH → pip 装的 imageio-ffmpeg → 各系统常见安装目录。
找不到也不报错,由调用方决定降级方案(ffmpeg 缺失时用 PyAV 直接解码)。
"""
import os, shutil, functools, pathlib

WIN = os.name == "nt"

FFMPEG_GUESSES = [
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
    os.path.expandvars(r"%USERPROFILE%\scoop\shims\ffmpeg.exe"),
    "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg",
]
ESPEAK_GUESSES = [
    r"C:\Program Files\eSpeak NG\espeak-ng.exe",
    r"C:\Program Files (x86)\eSpeak NG\espeak-ng.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\espeak-ng.exe"),
    os.path.expandvars(r"%USERPROFILE%\scoop\shims\espeak-ng.exe"),
    "/opt/homebrew/bin/espeak-ng", "/usr/local/bin/espeak-ng", "/usr/bin/espeak-ng",
]


def _first_existing(paths):
    for p in paths:
        if p and pathlib.Path(p).is_file():
            return str(p)
    return None


@functools.lru_cache(maxsize=1)
def find_ffmpeg():
    """返回 ffmpeg 可执行文件路径,找不到返回 None(此时会走 PyAV 解码)。"""
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:                                   # pip install imageio-ffmpeg 自带一个二进制
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and pathlib.Path(p).is_file():
            return p
    except Exception:
        pass
    return _first_existing(FFMPEG_GUESSES)


@functools.lru_cache(maxsize=1)
def find_espeak():
    """返回 espeak-ng 可执行文件路径,找不到返回 None(此时没有 IPA 音标)。"""
    return shutil.which("espeak-ng") or shutil.which("espeak") or _first_existing(ESPEAK_GUESSES)


def report():
    """启动时打印一次,让用户立刻知道缺什么、缺了会怎样。"""
    f, e = find_ffmpeg(), find_espeak()
    lines = []
    lines.append(f"  ffmpeg    : {f or '未找到(将改用内置解码器,通常也能正常工作)'}")
    lines.append(f"  espeak-ng : {e or '未找到(本次不会生成 IPA 音标,其它功能不受影响)'}")
    return "\n".join(lines)
