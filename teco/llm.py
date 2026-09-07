# -*- coding: utf-8 -*-
"""统一的 LLM 客户端:兼容 DeepSeek / Kimi(Moonshot),自带磁盘缓存与用量统计。

设计目标是省钱:
1) 所有请求按内容哈希缓存到 .cache/,重跑同一个视频不会二次付费;
2) 默认使用 deepseek-chat(目前单价最低的一档),可用 --llm 切换到 kimi;
3) 每次运行结束打印 token 用量与估算费用。
"""
import os, json, time, hashlib, pathlib
import requests

# 各家的接入点与默认模型。两家都兼容 OpenAI 的 /chat/completions 协议。
PROVIDERS = {
    "deepseek": {
        "base": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "keys": ["DEEPSEEK_API_KEY"],
        # 估算用单价(元 / 百万 token)。仅用于打印参考成本,可能过时,以官网为准。
        "price_in": 2.0, "price_out": 3.0,
    },
    "kimi": {
        "base": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "keys": ["MOONSHOT_API_KEY", "KIMI_API_KEY"],
        "price_in": 12.0, "price_out": 12.0,
    },
}

CACHE_DIR = pathlib.Path(__file__).resolve().parent.parent / ".cache"


class LLM:
    def __init__(self, provider="deepseek", model=None, use_cache=True, verbose=True):
        if provider not in PROVIDERS:
            raise ValueError(f"未知的 provider: {provider}(可选:{list(PROVIDERS)})")
        cfg = PROVIDERS[provider]
        key = next((os.environ[k] for k in cfg["keys"] if os.environ.get(k)), None)
        if not key:
            raise RuntimeError(
                f"没有找到 {provider} 的 API Key。请在 .env 里设置 {cfg['keys'][0]}=你的key"
            )
        self.provider, self.cfg, self.key = provider, cfg, key
        self.model = model or cfg["model"]
        self.use_cache = use_cache
        self.verbose = verbose
        self.tokens_in = self.tokens_out = 0
        self.cache_hits = 0
        CACHE_DIR.mkdir(exist_ok=True)

    # ---------- 缓存 ----------
    def _cache_path(self, payload):
        h = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()[:32]
        return CACHE_DIR / f"{self.provider}_{h}.json"

    # ---------- 主调用 ----------
    def chat(self, system, user, json_mode=True, temperature=0.2, max_retries=4):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        cp = self._cache_path(payload)
        if self.use_cache and cp.exists():
            self.cache_hits += 1
            return json.loads(cp.read_text(encoding="utf-8"))["content"]

        url = f"{self.cfg['base']}/chat/completions"
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        last_err = None
        for attempt in range(max_retries):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=180)
                if r.status_code == 429 or r.status_code >= 500:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                r.raise_for_status()
                data = r.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                self.tokens_in += usage.get("prompt_tokens", 0)
                self.tokens_out += usage.get("completion_tokens", 0)
                if self.use_cache:
                    cp.write_text(
                        json.dumps({"content": content}, ensure_ascii=False), encoding="utf-8"
                    )
                return content
            except Exception as e:  # 网络抖动/限流:退避重试
                last_err = e
                wait = 2 ** attempt
                if self.verbose:
                    print(f"    [LLM] 第 {attempt+1} 次失败({e}),{wait}s 后重试")
                time.sleep(wait)
        raise RuntimeError(f"LLM 调用连续失败:{last_err}")

    def chat_json(self, system, user, **kw):
        """要求返回 JSON,并做一次容错解析(去掉可能的 ```json 包裹)。"""
        txt = self.chat(system, user, json_mode=True, **kw).strip()
        if txt.startswith("```"):
            txt = txt.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            # 极少数情况下模型多输出了尾巴,截取第一个完整 JSON 对象
            start = txt.find("{")
            depth, end = 0, None
            for i, ch in enumerate(txt[start:], start):
                depth += (ch == "{") - (ch == "}")
                if depth == 0:
                    end = i + 1
                    break
            if end is None:
                raise
            return json.loads(txt[start:end])

    # ---------- 成本 ----------
    def cost_report(self):
        c = (self.tokens_in / 1e6) * self.cfg["price_in"] + (
            self.tokens_out / 1e6
        ) * self.cfg["price_out"]
        return (
            f"LLM 用量:输入 {self.tokens_in:,} / 输出 {self.tokens_out:,} token"
            f" · 缓存命中 {self.cache_hits} 次 · 估算费用 ≈ ¥{c:.4f}"
        )
