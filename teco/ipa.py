# -*- coding: utf-8 -*-
"""IPA 音标:本地用 espeak-ng 生成,零 API 成本。

支持整句和单词。espeak-ng 覆盖任意词(包括人名、生造词),
比查 CMUdict 词典的方案更稳,不会出现查不到就空着的情况。
"""
import subprocess, re, functools
from .tools import find_espeak
_CLEAN = re.compile(r"[\(\)\[\]]")


@functools.lru_cache(maxsize=20000)
def to_ipa(text: str, accent="en-us") -> str:
    """把一段英文转成 IPA。espeak-ng 不可用时返回空串(不影响其它功能)。"""
    text = (text or "").strip()
    exe = find_espeak()
    if not text or not exe:
        return ""
    try:
        # 必须显式指定 utf-8:espeak-ng 输出的是 UTF-8,而 text=True 默认用系统
        # 编码解码。中文 Windows 的系统编码是 GBK,不指定就会把音标解成乱码。
        out = subprocess.run(
            [exe, "--ipa", "-q", "-v", accent, text],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )
        ipa = out.stdout.strip().replace("\n", " ")
        ipa = _CLEAN.sub("", ipa)
        return re.sub(r"\s+", " ", ipa).strip()
    except Exception:
        return ""


def word_ipa(word: str) -> dict:
    """单词给出英美两版音标——学习者常需要对照。"""
    return {"us": to_ipa(word, "en-us"), "uk": to_ipa(word, "en-gb")}
