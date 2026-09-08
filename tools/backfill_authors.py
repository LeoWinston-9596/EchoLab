# -*- coding: utf-8 -*-
"""给存量素材回填作者(频道名),供素材库的「按作者排序 / 按作者看合集」使用。

为什么需要这个脚本:
  · 早期入库的素材没记作者,素材库的作者筛选就成了空壳;
  · 作者字段现在有两个名字在打架 —— 老数据和 index.json 用 author,
    process.py 写的、library.html 读的是 uploader。字段统一还没定下来,
    所以这里【两个都写、值相同】,等定了再删掉多余的那个。

怎么找作者:
  绝大多数素材是 YouTube 视频,data.json 里有 source_url。
  直接用 teco/captions.py 里现成的 fetch_uploader() —— 它用 yt-dlp
  只问一句「这是谁发的」,--skip-download,不产生任何本地文件。

关于限流(这个项目被 YouTube 429 过):
  · 每次请求之间随机停 2-4 秒,不连着撞;
  · 认出 429 就指数退避重试,不硬来;
  · 可断点续跑 —— 已经填好的期数直接跳过,中途挂了再跑一次接着做。

用法:
    python tools/backfill_authors.py              # 回填缺作者的期数
    python tools/backfill_authors.py --dry-run    # 只看会改什么,不落盘
    python tools/backfill_authors.py --verify     # 重新问一遍,核对存量作者对不对
    python tools/backfill_authors.py --verify --fix   # 核对并用线上结果纠正
    python tools/backfill_authors.py --limit 5    # 这一轮最多发 5 个请求
"""
import argparse
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from teco.captions import fetch_uploader, has_ytdlp   # noqa: E402  路径插好才能导

LIB = ROOT / "library"

MIN_GAP, MAX_GAP = 2.0, 4.0     # 两次请求之间的间隔(秒),带抖动
MAX_RETRY = 4                   # 撞上 429 最多退避重试几次
BACKOFF_BASE = 20               # 退避起点(秒),之后翻倍:20 / 40 / 80 / 160

# yt-dlp 把限流写在 stderr 里,措辞换过好几版,认宽一点
RATE_LIMIT_HINTS = ("429", "too many requests", "rate-limit", "rate limit")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, data):
    """原子写:先写同目录的 .tmp 再 replace,中途挂了也不会留半个残文件。

    格式跟 process.py 保持一致(ensure_ascii=False, indent=1, 结尾不加换行),
    这样即使这份文件之后被 process.py 重写,diff 里也只有作者那一行。
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def backup(path):
    """留一份 .bak。已经有了就不动 —— 别让第二次跑把干净的原件覆盖掉。"""
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(path, bak)


def set_author(data, name):
    """把 author / uploader 两个字段都写成 name,并尽量不打乱原有字段顺序。

    author 已经在的话,uploader 就紧跟其后插进去;两个都没有就一起追加到末尾。
    """
    out, done = {}, False
    for k, v in data.items():
        if k == "uploader":                 # 旧位置先丢掉,统一按下面的规则重新落位
            continue
        out[k] = v
        if k == "author":
            out[k] = name
            out["uploader"] = name
            done = True
    if not done:
        out["author"] = name
        out["uploader"] = name
    return out


def current_author(data):
    """两个字段里哪个有值就算有值 —— 别管当前仓库用的是哪个名字。"""
    for k in ("author", "uploader"):
        v = (data.get(k) or "").strip()
        if v:
            return v
    return ""


def looks_rate_limited(url):
    """作者取空之后再问一次,专门看 yt-dlp 的 stderr 是不是在喊限流。

    fetch_uploader() 把所有异常都咽掉、只返回空字符串,分不出
    「真没有作者」和「被 YouTube 挡了」。多花一个请求换一个准确判断,
    只在失败时才走这条路,不影响正常流程的请求数。
    """
    exe = has_ytdlp()
    if not exe:
        return False, "没装 yt-dlp"
    try:
        r = subprocess.run([exe, "--skip-download", "--no-playlist",
                            "--print", "%(id)s", url],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=90)
    except Exception as e:
        return False, f"探测失败:{e}"
    err = ((r.stderr or "") + (r.stdout or "")).lower()
    hit = any(h in err for h in RATE_LIMIT_HINTS)
    return hit, (r.stderr or "").strip()[-300:] or "yt-dlp 没给出错误信息"


def ask_uploader(url, tag):
    """问一次作者,撞限流就退避重试。返回 (作者名, 失败原因)。"""
    for attempt in range(1, MAX_RETRY + 2):
        name = fetch_uploader(url)
        if name:
            return name, ""
        limited, detail = looks_rate_limited(url)
        if not limited:
            return "", detail
        if attempt > MAX_RETRY:
            return "", f"连着 {MAX_RETRY} 次退避仍被限流:{detail}"
        wait = BACKOFF_BASE * (2 ** (attempt - 1))
        print(f"    ! {tag} 被限流,等 {wait} 秒后第 {attempt} 次重试")
        time.sleep(wait)
    return "", "未知"


def episodes():
    """按目录名排序列出所有期数的 data.json。空目录(入库失败的残留)直接跳过。"""
    for d in sorted(LIB.iterdir()):
        f = d / "data.json"
        if d.is_dir() and f.exists():
            yield d.name, f


def main():
    ap = argparse.ArgumentParser(description="回填素材库的作者字段")
    ap.add_argument("--dry-run", action="store_true", help="只报告,不写文件")
    ap.add_argument("--verify", action="store_true",
                    help="连已有作者的期数也重新问一遍,核对是否一致")
    ap.add_argument("--fix", action="store_true",
                    help="配合 --verify:核对不一致时用线上结果纠正")
    ap.add_argument("--limit", type=int, default=0,
                    help="这一轮最多发多少个请求(0 = 不限)")
    args = ap.parse_args()

    if not has_ytdlp():
        print("! 没找到 yt-dlp,装一下:pip install -U yt-dlp")
        return 1

    todo, skipped, filled = [], [], []
    for name, f in episodes():
        data = load(f)
        author = current_author(data)
        url = (data.get("source_url") or "").strip()
        if author and not args.verify:
            # 已有作者。只要两个字段没写齐,就顺手补齐 —— 这一步不用联网
            if (data.get("author") or "") != author or (data.get("uploader") or "") != author:
                filled.append((name, f, data, author))
            else:
                skipped.append((name, "作者已齐备"))
            continue
        if not url:
            # demo 是演示内容、1st 是本地导入的 mp3,本来就没有来源链接,不算失败
            skipped.append((name, "没有 source_url(本地素材),无从查作者"))
            continue
        todo.append((name, f, data, url, author))

    print(f"素材库共 {len(todo) + len(skipped) + len(filled)} 期:"
          f"待联网 {len(todo)} 期,本地补齐 {len(filled)} 期,跳过 {len(skipped)} 期")

    # 第一步:不用联网就能补齐的(已有 author,只差 uploader,或反过来)
    for name, f, data, author in filled:
        print(f"  · {name} —— 本地补齐 author/uploader = {author}")
        if not args.dry_run:
            backup(f)
            dump(f, set_author(data, author))

    # 第二步:联网问作者。请求之间留间隔,遇到 429 退避
    ok, fail = [], []
    for i, (name, f, data, url, author) in enumerate(todo, 1):
        if args.limit and len(ok) + len(fail) >= args.limit:
            print(f"  · 已达本轮上限 {args.limit} 个请求,剩下的下次再跑")
            break
        if i > 1:
            gap = random.uniform(MIN_GAP, MAX_GAP)
            time.sleep(gap)
        print(f"  [{i}/{len(todo)}] {name}")
        name_online, why = ask_uploader(url, name)
        if not name_online:
            print(f"    × 取不到作者:{why}")
            fail.append((name, why))
            continue
        if args.verify and author:
            if name_online == author:
                print(f"    √ 一致:{author}")
                ok.append((name, author))
                continue
            print(f"    ! 不一致:本地 {author!r} / 线上 {name_online!r}"
                  f"{'(按线上纠正)' if args.fix else '(保留本地,加 --fix 才改)'}")
            if not args.fix:
                ok.append((name, author))
                continue
        else:
            print(f"    √ {name_online}")
        ok.append((name, name_online))
        if not args.dry_run:
            backup(f)
            dump(f, set_author(data, name_online))

    print("\n—— 小结 ——")
    print(f"联网取到 {len(ok)} 期,失败 {len(fail)} 期,本地补齐 {len(filled)} 期,"
          f"跳过 {len(skipped)} 期")
    for name, why in fail:
        print(f"  失败 · {name}:{why}")
    for name, why in skipped:
        print(f"  跳过 · {name}:{why}")
    if args.dry_run:
        print("(--dry-run:一个字节都没写)")
    else:
        print("提醒:各期 data.json 已更新,但 library/index.json 需要重建才会生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
