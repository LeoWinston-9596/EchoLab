# -*- coding: utf-8 -*-
"""本地 IPA 语料库的离线测试:不联网、不调模型、不跑 espeak,音标全部是假的。

关注三件事:同一个词永远拿到同一条音标、算过的词不会再算第二遍、
两个进程同时写不会把语料库写坏。
"""
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from teco import ipa as M
import seed_ipa

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else:    fail += 1; print(f"  ✗ {name}  {extra}")


TMP = pathlib.Path(tempfile.mkdtemp(prefix="echolab_ipa_"))

def fresh(entries=None):
    """给每个用例一个干净的语料库文件,免得用例之间互相污染。"""
    p = TMP / f"ipa_{fresh.n}.json"
    fresh.n += 1
    if entries is not None:
        write(p, entries)
    M.set_corpus_path(p)
    return p
fresh.n = 0


def write(p, entries):
    p.write_text(json.dumps({"version": 1, "entries": entries},
                            ensure_ascii=False), encoding="utf-8")


def ipa(tag):
    return {"us": f"{tag}-us", "uk": f"{tag}-uk"}


class Counting:
    """假的生成器:记录被问过哪些词,替代 espeak。"""
    def __init__(self):
        self.asked = []
    def __call__(self, term):
        self.asked.append(term)
        return ipa(term)


class FakeLLM:
    """假的模型:一次请求答一整批,顺便记下被调用了几次。

    extra 用来模拟模型多送了没人要的词条,junk 模拟它答出中文说明。
    """
    def __init__(self, boom=False, extra=None, junk=False):
        self.calls, self.boom, self.extra, self.junk = 0, boom, extra, junk
    def chat_json(self, system, user):
        self.calls += 1
        if self.boom:
            raise RuntimeError("网络不通")
        terms = [l[2:] for l in user.splitlines() if l.startswith("- ")]
        items = [{"term": t,
                  "us": f"读作 {t}" if self.junk else f"L-{t}",
                  "uk": f"L-{t}"} for t in terms]
        if self.extra:
            items.append({"term": self.extra, "us": "L-x", "uk": "L-x"})
        return {"items": items}


print("【词条归一化】")
check("大小写不算两条", M.norm_term("Take Off") == M.norm_term("take off"))
check("标点被去掉", M.norm_term("well-being!") == "well being")
check("多余空格被压掉", M.norm_term("  take   off  ") == "take off")
check("多词短语保留一个空格", M.norm_term("no matter where") == "no matter where")
check("空词条返回空串", M.norm_term("") == "" and M.norm_term(None) == "")
# 词干还原会让读音不同的词共用一条音标,这条是刻意不做的
check("不做词干还原", M.norm_term("leaves") != M.norm_term("leaf"))

print("\n【只有算出东西来才进库】")
check("空音标不可用", not M.usable({"us": "", "uk": ""}))
check("只有一半也不可用", not M.usable({"us": "t", "uk": ""}))
check("含中文的不可用", not M.usable({"us": "读作 tuk", "uk": "tuk"}))
check("正常的可用", M.usable(ipa("take off")))

print("\n【查得到就不再算】")
fresh({"take off": ipa("hit")})
gen = Counting()
got, st = M.fill_missing(["Take off", "take   off"], gen=gen)
check("命中语料库", got["take off"] == ipa("hit"), str(got))
check("一次都没调生成器", gen.asked == [], str(gen.asked))
check("统计:2 个写法算 1 个词条", st["total"] == 1 and st["hit"] == 1, str(st))

print("\n【没查到才算,而且同一批里只算一次】")
p = fresh({})
gen = Counting()
got, st = M.fill_missing(["spotlight", "Spotlight", "pitcher"], gen=gen)
check("重复词条只问一次生成器", sorted(gen.asked) == ["pitcher", "spotlight"],
      str(gen.asked))
check("两个词条都有音标了", len(got) == 2, str(got))
check("统计:新增 2 条", st["new"] == 2 and st["hit"] == 0, str(st))
check("批次末尾已落盘",
      set(json.loads(p.read_text(encoding="utf-8"))["entries"])
      == {"pitcher", "spotlight"})

print("\n【第二次跑同一批素材是零成本的】")
gen2 = Counting()
got2, st2 = M.fill_missing(["spotlight", "pitcher"], gen=gen2)
check("全部命中", st2["hit"] == 2 and st2["new"] == 0, str(st2))
check("生成器没被碰", gen2.asked == [])
check("两次拿到的音标一致", got2["spotlight"] == got["spotlight"])

print("\n【注音用原词条,不用归一化后的键】")
fresh({})
gen = Counting()
M.fill_missing(["don't"], gen=gen)
# 归一化把撇号变成空格,拿 "don t" 去注音会读成两个词
check("传给生成器的是 don't", gen.asked == ["don't"], str(gen.asked))
check("存进去的键是归一化的", "don t" in M.load_corpus(), str(list(M.load_corpus())))

print("\n【写盘是原子的,并发也不会写坏】")
p = fresh({"alpha": ipa("a")})
M.fill_missing(["beta"], gen=Counting())
# 另一个进程(worker.py --watch)在这中间也写了一条。它自己也是先读盘再写,
# 所以盘上是「原有 + beta + 它的 gamma」;我们接着写 delta 时不能把 gamma 抹掉
write(p, {"alpha": ipa("a"), "beta": ipa("beta"), "gamma": ipa("g")})
M.fill_missing(["delta"], gen=Counting())
on_disk = json.loads(p.read_text(encoding="utf-8"))["entries"]
check("别的进程写的那条还在", "gamma" in on_disk, str(list(on_disk)))
check("自己写的两条也在", {"beta", "delta"} <= set(on_disk), str(list(on_disk)))
check("没留下临时文件", list(p.parent.glob(f"{p.name}.*.tmp")) == [])
check("落盘的 JSON 完整可读", isinstance(on_disk, dict) and len(on_disk) == 4)
check("键是排好序的", list(on_disk) == sorted(on_disk), str(list(on_disk)))

print("\n【已有的音标不被覆盖】")
p = fresh({"take off": ipa("old")})
M.stage("take off", ipa("new"))
M.flush()
check("先写的那版说话", json.loads(p.read_text(encoding="utf-8"))
      ["entries"]["take off"] == ipa("old"))

print("\n【坏文件当空库,不能让流水线挂掉】")
p = fresh()
p.write_text("{这不是 JSON", encoding="utf-8")
check("读坏文件返回空库", M.load_corpus(reload=True) == {})
M.set_corpus_path(TMP / "不存在的目录" / "ipa.json")
check("文件不存在也不报错", M.load_corpus(reload=True) == {})
got, st = M.fill_missing(["hello"], gen=Counting())
check("目录会自动建出来", got["hello"] == ipa("hello") and st["new"] == 1)

print("\n【生成器算不出来时的降级】")
fresh({})
got, st = M.fill_missing(["ghost"], gen=lambda t: {"us": "", "uk": ""})
check("算不出来就空着,不抛异常", got == {} and st["fail"] == 1, str(st))
check("空音标没被存进语料库", M.load_corpus() == {}, str(M.load_corpus()))

print("\n【大模型兜底:批量问 + 失败回退】")
fresh({})
llm = FakeLLM()
got, st = M.fill_missing(["a", "b", "c"], llm=llm,
                         gen=lambda t: {"us": "", "uk": ""})
check("3 个词只发 1 次请求", llm.calls == 1, f"calls={llm.calls}")
check("模型给的音标被采用", got["a"]["us"] == "L-a", str(got))
check("统计记在 llm 上", st["llm"] == 3 and st["new"] == 0, str(st))
check("模型给的也存进了语料库", "a" in M.load_corpus())

fresh({})
llm = FakeLLM(extra="没人问的词")
got, st = M.fill_missing(["a"], llm=llm, gen=lambda t: {"us": "", "uk": ""})
check("模型多送的词条不收", list(got) == ["a"], str(got))
check("语料库里也没混进来", list(M.load_corpus()) == ["a"], str(list(M.load_corpus())))

fresh({})
llm = FakeLLM(junk=True)
got, st = M.fill_missing(["a"], llm=llm, gen=lambda t: {"us": "", "uk": ""})
check("模型答出中文的一律不要", got == {} and st["fail"] == 1, str(got))

fresh({})
llm = FakeLLM(boom=True)
got, st = M.fill_missing(["x"], llm=llm, gen=Counting())
check("espeak 算出来了就不问模型", llm.calls == 0 and got["x"] == ipa("x"), str(st))

fresh({})
llm = FakeLLM(boom=True)
got, st = M.fill_missing(["y"], llm=llm, gen=lambda t: {"us": "", "uk": ""})
check("模型挂了也只是少条音标", got == {} and st["fail"] == 1, str(st))

print("\n【word_ipa 仍然照旧能用(repair.py 走这条)】")
fresh({"take off": ipa("hit")})
check("命中语料库", M.word_ipa("Take Off") == ipa("hit"))
check("返回的仍是 us/uk 两个键", set(M.word_ipa("Take Off")) == {"us", "uk"})

print("\n【种子导入的多数表决】")
import collections
c = collections.Counter({("a-us", "a-uk"): 3, ("b-us", "b-uk"): 5})
check("取出现次数最多的那版", seed_ipa.pick(c) == ("b-us", "b-uk"))
c = collections.Counter({("z-us", "z-uk"): 2, ("a-us", "a-uk"): 2})
check("票数相同时结果可复现", seed_ipa.pick(c) == seed_ipa.pick(
    collections.Counter({("a-us", "a-uk"): 2, ("z-us", "z-uk"): 2})))
check("票数相同取排序第一个", seed_ipa.pick(c) == ("a-us", "a-uk"))

print("\n【真语料库文件本身是好的】")
real = M.CORPUS_PATH
if real.exists():
    M.set_corpus_path(real)
    ent = M.load_corpus(reload=True)
    check("能读出词条", len(ent) > 0, f"{len(ent)} 条")
    check("每条都有英美两版", all(M.usable(v) for v in ent.values()))
    check("键都是归一化过的",
          all(k == M.norm_term(k) for k in ent), "有键没归一化")
else:
    print("  - 还没跑过 seed_ipa.py,跳过(不算失败)")

M.set_corpus_path(TMP / "收尾用的空库.json")     # 别让退出时的自动落盘碰到真文件
print(f"\n通过 {ok} / {ok+fail}")
sys.exit(1 if fail else 0)
