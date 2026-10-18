"""README / pyproject / 包布局 / 测试依赖 的对账门（M0 版，M5–M6 扩充）。

四个面：

1. README 提到的每个子命令都真的注册在 CLI 里（方向：README → parser）。
2. README 用的安装 extras 在 `pyproject.toml` 里声明（方向：README ↔ pyproject）。
3. `tests/` 真 import 的顶层模块都有落点：冻结 stdlib 名单 / dev extra / 本包 / 同目录测试助手。
4. `packages.find` 的声明与真实包布局一致（本包在 `src/` 下且可被装上）。

外加一条**骨架态登记**：当前抛 `NotReadyError` 的模块集合固定——模块落地时同轮缩小它。
"""

import ast
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
TESTS = os.path.join(ROOT, "tests")

# 冻结 stdlib 名单（不用 sys.stdlib_module_names：那是 3.10+，3.8 上取空集会全量假红）
STDLIB = frozenset("""
argparse ast binascii bisect calendar collections collections.abc contextlib copy csv dataclasses
datetime decimal difflib enum errno fnmatch fractions functools getpass glob gzip hashlib heapq hmac
html http importlib inspect io ipaddress itertools json keyword linecache locale logging marshal
math mimetypes numbers operator os os.path pathlib pickle platform plistlib posixpath pprint
queue random re secrets shlex shutil signal socket sqlite3 stat statistics string struct subprocess
sys tarfile tempfile textwrap threading time tokenize tomllib traceback types typing unicodedata
unittest urllib urllib.parse urllib.request uuid warnings weakref xml zipfile zlib
""".split())

# dev extra 的 import 名（分发名 → import 名要走别名表）
DEV_EXTRA_IMPORTS = {"pytest", "yaml"}


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _pyproject():
    text = _read(os.path.join(ROOT, "pyproject.toml"))
    where_match = re.search(r"where\s*=\s*\[([^\]]*)\]", text)
    doc = {
        "_text": text,
        "_where": re.findall(r"[\"']([^\"']+)[\"']", where_match.group(1)) if where_match else [],
    }
    try:
        import tomllib  # py3.11+，底线 3.8 上没有
    except ImportError:
        tomllib = None
    if tomllib is not None:
        doc.update(tomllib.loads(text))
    else:
        extras = {}
        match = re.search(r"\[project\.optional-dependencies\](.*?)(\n\[|\Z)", text, re.S)
        if match:
            for line in match.group(1).splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    extras[key.strip()] = re.findall(r"[\"']([^\"']+)[\"']", value)
        doc["project"] = {"optional-dependencies": extras}
    return doc


def _readme():
    return _read(os.path.join(ROOT, "README.md"))


def _import_top_level(path):
    """AST 从严收集顶层 import 名（含函数体内 import）。"""
    tree = ast.parse(_read(path), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue  # 相对导入属于本包
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def test_readme_mentions_every_subcommand():
    from mergefidelity import cli

    readme = _readme()
    for name in cli.SUBCOMMANDS:
        assert name in readme, "README 未提及子命令 %s" % name


def test_readme_install_line_uses_declared_extras():
    extras = set(_pyproject()["project"]["optional-dependencies"])
    readme = _readme()
    used = set(re.findall(r'pip install -e "\.\[([^"\]]+)\]"', readme))
    assert used, 'README 缺少 `pip install -e ".[...]"` 安装行'
    for group in used:
        for name in group.split(","):
            assert name.strip() in extras, "README 用了未声明的 extra：%s" % name


def test_tests_only_import_declared_dependencies():
    own_package = "mergefidelity"
    local_helpers = {
        os.path.splitext(name)[0]
        for name in os.listdir(TESTS)
        if name.endswith(".py") and not name.startswith("test_")
    }
    offenders = {}
    for name in sorted(os.listdir(TESTS)):
        if not name.endswith(".py"):
            continue
        for top in _import_top_level(os.path.join(TESTS, name)):
            if top in STDLIB or top == own_package or top in DEV_EXTRA_IMPORTS:
                continue
            if top in local_helpers:
                continue
            offenders.setdefault(top, []).append(name)
    assert not offenders, "tests 引入了未登记的顶层模块：%r" % offenders


def test_package_layout_matches_pyproject():
    pyproject = _pyproject()
    src_pkg = os.path.join(SRC, "mergefidelity", "__init__.py")
    assert os.path.isfile(src_pkg), "缺少 src/mergefidelity/__init__.py"
    text = pyproject.get("_text") or _read(os.path.join(ROOT, "pyproject.toml"))
    assert 'package-dir = { "" = "src" }' in text
    where = pyproject.get("_where")
    if where is None:
        assert 'where = ["src"]' in text
    else:
        assert where == ["src"]


def test_readme_declared_license_file_exists():
    assert "MIT" in _readme()
    license_text = _read(os.path.join(ROOT, "LICENSE"))
    assert "MIT License" in license_text
    assert "MIT" in _read(os.path.join(ROOT, "pyproject.toml"))


def test_every_registered_subcommand_has_a_dispatch_path():
    from mergefidelity import cli

    for name in cli.SUBCOMMANDS:
        if name == "fidelity":
            continue
        assert name in cli._DISPATCH


def test_skeleton_not_ready_registry_is_explicit():
    """骨架态登记：这些模块当前抛 NotReadyError；每落地一个就同轮删一行。"""
    from mergefidelity import gate, report
    from mergefidelity.errors import NotReadyError

    modules = {
        "report": report.run,
        "gate": gate.run,
    }
    for name, func in modules.items():
        with pytest.raises(NotReadyError) as excinfo:
            func(_Args())
        assert excinfo.value.module == name
        assert excinfo.value.exit_code == 2


class _Args(object):
    def __getattr__(self, item):
        return None


def test_no_shared_layer_raises_not_ready():
    """共享层（gitobj/canonical/diffparse/cli/errors）不得有"未实现"占位。"""
    for name in ("cli.py", "canonical.py", "diffparse.py", "gitobj.py", "errors.py"):
        text = _read(os.path.join(SRC, "mergefidelity", name))
        assert "NotReadyError(" not in text or name == "errors.py", name
        assert "NotImplementedError" not in text, name
        assert "TODO" not in text, name
