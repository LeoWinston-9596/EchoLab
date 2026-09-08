# -*- coding: utf-8 -*-
"""IPA 音标:先查本地语料库,查不到才现算,算完存回去。

一个词的音标是事实而不是生成结果——take off 在第 1 期和第 28 期里就该是
同一串符号。所以这里把算过的音标全部沉淀到 wordlists/ipa.json 并进版本库:
28 期攒下来的几千条以后一次都不必重算,新素材只为真正的新词付代价,
顺带也保证了跨期的一致性(以前同一个词换台机器跑就可能换个写法)。

取值顺序:本地语料库 → espeak-ng(本机、零成本)→ 大模型(可选兜底,
只在 espeak-ng 缺失时用,且一次问一批)。任一环失败只是少一条音标,
不会让流水线中断。
"""
import atexit, functools, json, os, pathlib, re, subprocess
from .tools import find_espeak

_CLEAN = re.compile(r"[\(\)\[\]]")
_CJK = re.compile(r"[一-鿿぀-ヿ]")

CORPUS_PATH = pathlib.Path(__file__).resolve().parent.parent / "wordlists" / "ipa.json"

# 文件头写死在代码里:语料库是给人看也给 git 看的,得自带说明。
# entries 按键排序,这样每次新增在 diff 里只有新增那几行。
_VERSION = 1
_NOTE = ("EchoLab 本地 IPA 语料库。键是归一化后的词条,值是英美两版音标。"
         "由 teco/ipa.py 自动增长,请随代码一起提交——攒得越多越省。")

_corpus_path = CORPUS_PATH
_corpus = None          # {归一化词条: {"us":…, "uk":…}},None 表示还没读盘
_pending = {}           # 本批新算出来的,攒到 flush() 一次落盘


# ------------------------------------------------------------------ 归一化

def norm_term(term: str) -> str:
    """语料库的键。大小写、标点、多余空格的差异不该造成两条记录。

    刻意不做 cards.py 里的词干还原:run/ran、leaf/leaves 的读音本来就不同,
    还原了会让它们共用一条音标。词条本身可能是多词短语("take off"),
    所以键里保留单个空格。
    """
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (term or "").lower())).strip()


def usable(entry) -> bool:
    """只有真正算出东西来才值得存。

    espeak-ng 缺失时会返回空串,含中文说明是模型答歪了。这两种都不能进库——
    一次在坏环境上的运行会把空音标永久固化下来,后面全库都查不到。
    """
    if not isinstance(entry, dict):
        return False
    us, uk = (entry.get("us") or "").strip(), (entry.get("uk") or "").strip()
    if not (us and uk):
        return False
    return not (_CJK.search(us) or _CJK.search(uk))


# ------------------------------------------------------------------ 语料库读写

def set_corpus_path(path):
    """换一个语料库文件(测试用)。顺手清掉内存缓存与未落盘的暂存。"""
    global _corpus_path, _corpus, _pending
    _corpus_path, _corpus, _pending = pathlib.Path(path), None, {}


def _read_entries(path) -> dict:
    """读语料库。文件不存在或读坏了都按空库处理——缺音标只是少个注音,
    不该让整条流水线停在这儿。"""
    try:
        raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    entries = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(entries, dict):
        return {}
    return {k: {"us": v.get("us", ""), "uk": v.get("uk", "")}
            for k, v in entries.items() if usable(v)}


def load_corpus(reload=False) -> dict:
    """内存里的语料库。整个进程只读盘一次。"""
    global _corpus
    if _corpus is None or reload:
        _corpus = _read_entries(_corpus_path)
    return _corpus


def corpus_size() -> int:
    return len(load_corpus()) + len(_pending)


def lookup(term: str):
    """查一个词条的音标,没有返回 None。"""
    key = norm_term(term)
    if not key:
        return None
    hit = load_corpus().get(key) or _pending.get(key)
    return dict(hit) if hit else None


def stage(term: str, entry: dict) -> bool:
    """把一条音标记到暂存里,等 flush() 统一落盘。已有的不覆盖。"""
    key = norm_term(term)
    if not key or not usable(entry):
        return False
    if key in load_corpus() or key in _pending:
        return False
    _pending[key] = {"us": entry["us"].strip(), "uk": entry["uk"].strip()}
    return True


def flush() -> int:
    """把本批新算的音标一次写盘,返回真正写入的条数。

    两件事必须做对,因为 worker.py --watch 可能正在后台跑另一期,
    多个进程会同时写这一个文件:
    1) 写前重读磁盘并以磁盘上已有的为准。音标是事实,谁先写的都够用,
       抢着覆盖只会让文件在两个值之间反复横跳;
    2) 临时文件名带进程号再原子改名。共用一个 .tmp 会互相截断,
       这个仓库刚因为这个坏过文件。
    """
    global _corpus, _pending
    if not _pending:
        return 0
    on_disk = _read_entries(_corpus_path)
    added = {k: v for k, v in _pending.items() if k not in on_disk}
    merged = dict(on_disk)
    merged.update(added)
    if added:
        p = pathlib.Path(_corpus_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(
            {"version": _VERSION, "note": _NOTE, "count": len(merged),
             "entries": {k: merged[k] for k in sorted(merged)}},
            ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
    _corpus, _pending = merged, {}
    return len(added)


# 逐个调 word_ipa() 的老代码(repair.py、demo.py)不会自己收尾,
# 靠退出时兜一次,免得算了半天一条也没存下来。
atexit.register(lambda: flush())


# ------------------------------------------------------------------ espeak 生成

@functools.lru_cache(maxsize=20000)
def to_ipa(text: str, accent="en-us") -> str:
    """把一段英文转成 IPA。espeak-ng 不可用时返回空串(不影响其它功能)。

    整句音标不进语料库:句子几乎不重复,存了只是把文件撑大。
    """
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


def word_ipa_local(word: str) -> dict:
    """现算一个词条的英美两版音标,不查库、不存库。"""
    return {"us": to_ipa(word, "en-us"), "uk": to_ipa(word, "en-gb")}


# ------------------------------------------------------------------ 大模型兜底

_LLM_SYSTEM = """你是英语发音词典的编者。给出每个词条的国际音标(IPA)。

要求:
- us 用美音(General American),uk 用英音(Received Pronunciation)
- 只输出音标符号本身,不要斜杠、方括号、不要任何中文或说明
- 多词短语按连读的自然读法整体注音,词之间用一个空格分开
- 词条原样回抄到 term 字段,不要改写

输出严格 JSON:{"items":[{"term":"…","us":"…","uk":"…"}]}。只输出 JSON。"""


def llm_ipa_batch(llm, terms, size=40, verbose=False) -> dict:
    """用大模型补一批音标,返回 {归一化词条: {"us","uk"}}。

    一次问一批而不是一个词一次:请求头、system 提示这些固定开销占比很高,
    40 个词一起问比分 40 次问省一个数量级的 token。
    某一批失败只丢这一批(上层会退回 espeak),不抛异常。
    """
    out = {}
    terms = [t for t in dict.fromkeys(terms) if t]
    for i in range(0, len(terms), size):
        part = terms[i:i + size]
        try:
            data = llm.chat_json(_LLM_SYSTEM,
                                 "词条:\n" + "\n".join(f"- {t}" for t in part))
            for it in (data.get("items") or []):
                key = norm_term(it.get("term", ""))
                entry = {"us": str(it.get("us") or ""), "uk": str(it.get("uk") or "")}
                if key and usable(entry):
                    out[key] = entry
        except Exception as e:
            if verbose:
                print(f"    [IPA] 大模型补音标失败({e}),这批退回本机生成")
    return out


# ------------------------------------------------------------------ 对外主入口

def fill_missing(terms, llm=None, gen=None, verbose=False):
    """一次备齐一批词条的音标。返回 ({归一化词条: 音标}, 统计)。

    这是流水线该用的入口:先把整批词条按语料库过一遍,只对没见过的词
    调用一次生成,末尾统一落盘。逐个 word_ipa() 的写法会让同一个词在
    28 期里被算 28 遍,还要写 28 次盘。
    """
    gen = gen or word_ipa_local
    corpus, out = load_corpus(), {}
    stats = {"total": 0, "hit": 0, "new": 0, "llm": 0, "fail": 0}

    keys = list(dict.fromkeys(norm_term(t) for t in terms))
    keys = [k for k in keys if k]
    stats["total"] = len(keys)
    # 生成时用原词条而不是归一化后的键:espeak 认得 "take off" 也认得
    # "don't",归一化把撇号变成了空格,拿去注音会读成两个词
    origin = {}
    for t in terms:
        origin.setdefault(norm_term(t), t)

    miss = []
    for k in keys:
        hit = corpus.get(k) or _pending.get(k)
        if hit:
            out[k] = dict(hit)
            stats["hit"] += 1
        else:
            miss.append(k)

    for k in miss:
        entry = gen(origin.get(k, k))
        if usable(entry):
            out[k] = entry
            stage(origin.get(k, k), entry)
            stats["new"] += 1

    # espeak 没装(或整批都没算出东西)才动用模型,这样默认路径永远是零成本的
    still = [k for k in miss if k not in out]
    if still and llm is not None:
        got = llm_ipa_batch(llm, [origin.get(k, k) for k in still], verbose=verbose)
        # 只认问过的词:模型偶尔会自己改写或多送几个词条,照收会往语料库里
        # 掺进没人要的条目,而语料库是要进版本库长期留着的
        for k in still:
            entry = got.get(k)
            if entry:
                out[k] = entry
                stage(origin.get(k, k), entry)
                stats["llm"] += 1

    stats["fail"] = stats["total"] - len(out)
    flush()
    return out, stats


def word_ipa(word: str, llm=None) -> dict:
    """单词给出英美两版音标——学习者常需要对照。

    命中语料库就直接返回,否则现算并记入暂存(进程退出时统一落盘)。
    """
    hit = lookup(word)
    if hit:
        return hit
    entry = word_ipa_local(word)
    if not usable(entry) and llm is not None:
        entry = llm_ipa_batch(llm, [word]).get(norm_term(word)) or entry
    stage(word, entry)
    return entry
