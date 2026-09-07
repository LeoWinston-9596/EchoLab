# -*- coding: utf-8 -*-
"""语音识别:输出带【词级时间戳】的转写结果。

词级时间戳是整个产品的地基——点击某一句播放对应片段、单句精准循环、
把 LLM 切好的语义群映射回时间轴,全都依赖它。所以这里必须开 word_timestamps。
"""
import os, subprocess, pathlib
from .tools import find_ffmpeg

_MODEL_CACHE = {}


def extract_audio(video_path: str, out_wav: str):
    """抽出 16k 单声道 wav。

    没有 ffmpeg 也不要紧:返回 None,调用方直接把原文件交给 faster-whisper,
    它内部用 PyAV 解码,多数格式都能读。这样 ffmpeg 就是"锦上添花"而非必需品。
    """
    ff = find_ffmpeg()
    if not ff:
        return None
    pathlib.Path(out_wav).parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [ff, "-y", "-i", str(video_path), "-vn",
             "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_wav)],
            check=True, capture_output=True,
        )
        return out_wav
    except subprocess.CalledProcessError:
        return None


def transcribe(wav_path: str, model_size="small.en", compute_type="int8", verbose=True):
    """返回 (words, whisper_segments, info)。

    words: [{i, w, start, end}]  —— 全片扁平的词序列,i 是全局序号,后面 LLM 靠它切分。
    """
    from faster_whisper import WhisperModel

    if model_size not in _MODEL_CACHE:
        if verbose:
            print(f"  · 加载识别模型 {model_size}(首次会自动下载,几百 MB,只下一次)...")
        try:
            _MODEL_CACHE[model_size] = WhisperModel(
                model_size, device="cpu", compute_type=compute_type
            )
        except Exception as e:
            # 模型托管在 HuggingFace,国内直连经常失败。给出可直接照做的解决办法,
            # 而不是把一串英文堆栈丢给用户。
            if os.environ.get("HF_ENDPOINT"):
                raise
            raise RuntimeError(
                "识别模型下载失败,通常是连不上 HuggingFace。请换镜像后重试:\n\n"
                "  Windows(PowerShell):\n"
                "    $env:HF_ENDPOINT=\"https://hf-mirror.com\"\n"
                "    python process.py 你的视频.mp4\n\n"
                "  Windows(CMD):\n"
                "    set HF_ENDPOINT=https://hf-mirror.com\n\n"
                "  Mac / Linux:\n"
                "    export HF_ENDPOINT=https://hf-mirror.com\n\n"
                "想一劳永逸,就把 HF_ENDPOINT=https://hf-mirror.com 写进 .env 文件。\n"
                f"原始错误:{type(e).__name__}: {str(e)[:200]}"
            ) from e
    model = _MODEL_CACHE[model_size]

    segments, info = model.transcribe(
        str(wav_path),
        word_timestamps=True,       # 关键
        vad_filter=True,            # 过滤静音,vlog 里空镜很多
        vad_parameters={"min_silence_duration_ms": 400},
        beam_size=5,
        condition_on_previous_text=False,  # 防止口语场景下的重复幻觉
    )

    words, raw_segments = [], []
    for seg in segments:
        raw_segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        for w in (seg.words or []):
            token = w.word.strip()
            if not token:
                continue
            words.append({
                "i": len(words),
                "w": token,
                "start": round(w.start, 3),
                "end": round(w.end, 3),
                "p": round(getattr(w, "probability", 1.0), 3),
            })
        if verbose and len(raw_segments) % 10 == 0:
            print(f"    已识别 {seg.end:.0f}s ...")

    return words, raw_segments, {
        "language": info.language,
        "duration": round(info.duration, 2),
    }


def low_confidence_words(words, threshold=0.5):
    """挑出识别把握低的词,供人工校对时优先检查(而不是通读全文)。"""
    return [w for w in words if w.get("p", 1.0) < threshold]
