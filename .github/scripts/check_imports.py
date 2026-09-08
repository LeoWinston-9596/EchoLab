#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导入健全性检查:每个 .py 都能编译、能导入,且跨文件引用的名字真实存在。

为什么不能只靠 `python -m compileall`:
它只看语法。「A 文件 import 了 B 文件里已经删掉的函数」语法完全合法,编译照样通过,
要等到运行到那一行才 ImportError——这个项目刚栽过一次跟头。

为什么也不能只靠「把每个模块 import 一遍」:
本项目大量使用延迟导入(把 import 写在函数体里,避免启动就加载重依赖),
比如 repair.py 的 `def cmd_merge(): ... from teco.segment import merge_short`。
这一行只有真正调用 cmd_merge 才会执行,import 模块的时候根本碰不到。

所以这里分三步查:

  1. 编译:每个 .py 都能解析成 AST(等价于 compileall,顺手把 AST 留着给第 3 步用)
  2. 导入:把所有一方模块真的 import 一遍
     ——能抓循环导入、模块级缺依赖、模块级的名字笔误
  3. 符号:静态扫描所有 `from <一方模块> import a, b`,**不论嵌套多深**,
     逐个核对 a、b 在目标模块里确实存在
     ——这一步才是拦住上面那类事故的关键

只检查一方代码(仓库自己的模块),标准库和第三方的 import 一律跳过。
全程不联网、不调模型、不需要任何密钥。

用法:python .github/scripts/check_imports.py
"""
import ast
import importlib
import pathlib
import sys
import traceback

# Windows 控制台默认不是 UTF-8,中文和 ✓ 会直接把脚本崩掉
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = pathlib.Path(__file__).resolve().parents[2]

# 不参与检查的目录:素材数据、缓存、虚拟环境、工具自身
SKIP_DIRS = {
    ".git", ".github", ".cache", ".queue", ".pytest_cache", "__pycache__",
    ".venv", "venv", "env", "node_modules",
    "library", "downloads", "docs", "wordlists",
}

# 这些目录里的文件只做「编译 + 符号」检查,不真的 import。
# 测试脚本是顶层直跑的,import 它就等于把测试跑了一遍,那是 run_all.py 的活。
NO_IMPORT_DIRS = {"tests"}

OK = "✓"
BAD = "✗"


def iter_py_files():
    """仓库里所有需要检查的 .py,按路径排序。"""
    files = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        files.append(path)
    return sorted(files)


def module_name_of(path):
    """文件路径 → 模块名,teco/segment.py → teco.segment。"""
    parts = list(path.relative_to(ROOT).parts)
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def first_party_roots():
    """一方模块的顶层名字:根目录的 .py,加上任何装着 .py 的子目录。

    子目录不要求有 __init__.py——teco/ 有,tools/ 这类没有的走命名空间包,
    Python 3 一样能导入,不该因为少个空文件就漏检。
    """
    roots = set()
    for path in ROOT.iterdir():
        if path.name in SKIP_DIRS:
            continue
        if path.is_file() and path.suffix == ".py":
            roots.add(path.stem)
        elif path.is_dir() and any(path.glob("*.py")):
            roots.add(path.name)
    return roots


ROOTS = first_party_roots()


def is_first_party(module):
    return bool(module) and module.split(".")[0] in ROOTS


def absolute_target(node, mod_name, is_package):
    """把 ImportFrom 节点解析成绝对模块名,解析不了就返回 None。

    相对导入(`from . import library`、`from .platforms import detect`)要按
    所在文件的包来还原:包自身的 __init__.py 里 level=1 指向包自己,
    普通模块里 level=1 指向它的父包。
    """
    if not node.level:
        return node.module
    base = mod_name if is_package else mod_name.rpartition(".")[0]
    for _ in range(node.level - 1):
        base = base.rpartition(".")[0]
    if not base:
        return None
    return "{}.{}".format(base, node.module) if node.module else base


class Checker:
    def __init__(self):
        self.errors = []
        self.mod_cache = {}

    def fail(self, where, msg):
        self.errors.append((where, msg))
        print("  {} {}\n      {}".format(BAD, where, msg))

    # ---------- 第 1 步:编译 ----------
    def compile_all(self, files):
        print("\n【第 1 步】语法编译:{} 个文件".format(len(files)))
        trees = {}
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            try:
                # utf-8-sig:带 BOM 的文件 Python 自己能正常导入,这里也不该报错
                source = path.read_text(encoding="utf-8-sig")
                trees[path] = ast.parse(source, filename=str(path))
            except SyntaxError as e:
                self.fail(rel, "语法错误(第 {} 行):{}".format(e.lineno, e.msg))
            except UnicodeDecodeError as e:
                self.fail(rel, "不是合法的 UTF-8 源文件:{}".format(e))
        print("  {} 编译通过 {} / {}".format(OK, len(trees), len(files)))
        return trees

    # ---------- 第 2 步:导入 ----------
    def import_all(self, files):
        targets = []
        for path in files:
            rel_parts = path.relative_to(ROOT).parts
            if rel_parts[0] in NO_IMPORT_DIRS:
                continue
            targets.append(module_name_of(path))
        targets.sort()

        print("\n【第 2 步】模块导入:{} 个模块".format(len(targets)))
        for name in targets:
            try:
                self.mod_cache[name] = importlib.import_module(name)
            except BaseException:
                self.mod_cache[name] = None
                detail = traceback.format_exc(limit=6).strip().replace("\n", "\n      ")
                self.fail(name, "导入失败:\n      " + detail)
        good = sum(1 for n in targets if self.mod_cache.get(n) is not None)
        print("  {} 导入成功 {} / {}".format(OK, good, len(targets)))

    def load(self, name):
        """按需拿模块对象(第 3 步可能碰到第 2 步没导过的,比如包本身)。"""
        if name not in self.mod_cache:
            try:
                self.mod_cache[name] = importlib.import_module(name)
            except BaseException:
                self.mod_cache[name] = None
        return self.mod_cache[name]

    # ---------- 第 3 步:符号 ----------
    def check_symbols(self, trees):
        print("\n【第 3 步】跨文件符号核对(含函数体内的延迟导入)")
        checked = 0
        for path, tree in sorted(trees.items()):
            rel = path.relative_to(ROOT).as_posix()
            mod_name = module_name_of(path)
            is_pkg = path.name == "__init__.py"

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if not is_first_party(alias.name):
                            continue
                        checked += 1
                        if self.load(alias.name) is None:
                            self.fail(
                                "{}:{}".format(rel, node.lineno),
                                "import {} —— 模块导入不了".format(alias.name),
                            )
                    continue

                if not isinstance(node, ast.ImportFrom):
                    continue

                target = absolute_target(node, mod_name, is_pkg)
                if not is_first_party(target):
                    continue

                module = self.load(target)
                if module is None:
                    checked += 1
                    self.fail(
                        "{}:{}".format(rel, node.lineno),
                        "from {} import ... —— 目标模块导入不了".format(target),
                    )
                    continue

                for alias in node.names:
                    if alias.name == "*":
                        continue
                    checked += 1
                    if hasattr(module, alias.name):
                        continue
                    # 也可能 import 的是子模块,`from teco import library` 这种
                    if self.load("{}.{}".format(target, alias.name)) is not None:
                        continue
                    self.fail(
                        "{}:{}".format(rel, node.lineno),
                        "from {} import {} —— 「{}」在 {} 里不存在".format(
                            target, alias.name, alias.name, target
                        ),
                    )
        print("  {} 核对了 {} 处一方引用".format(OK, checked))


def main():
    sys.path.insert(0, str(ROOT))
    print("=" * 60)
    print("导入健全性检查  root={}".format(ROOT))
    print("一方模块:{}".format("、".join(sorted(ROOTS))))
    print("=" * 60)

    files = iter_py_files()
    checker = Checker()
    trees = checker.compile_all(files)
    checker.import_all(files)
    checker.check_symbols(trees)

    print("\n" + "=" * 60)
    if checker.errors:
        print("{} 健全性检查未通过,共 {} 个问题:".format(BAD, len(checker.errors)))
        for where, msg in checker.errors:
            print("  - {}:{}".format(where, msg.splitlines()[0]))
        return 1
    print("{} 健全性检查全部通过。".format(OK))
    return 0


if __name__ == "__main__":
    sys.exit(main())
