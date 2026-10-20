"""bench 快照保护守门（B2，迭代路线 2.3；诊断 D5 的修复验证）。

问题背景：bench/*.json 是入仓快照，但直接跑 tools/bench_*.py 会就地改写它们
（python_version 随本机环境漂移）。修复后默认写 `bench/<name>.local.json`
（.gitignore 排除），只有显式 `--commit-snapshot` 才覆盖入仓快照并打印提示。
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# （工具名, fixture 的 --only 参数, 产物关键字段断言）
CASES = [
    ("fidelity", "smuggle-extra-line", lambda p: p["fixtures"][0]["fixture"] == "smuggle-extra-line"),
    ("parity", "bidirectional-basic", lambda p: p["fixtures"][0]["fixture"] == "bidirectional-basic"),
    ("ledger", "then-redone", lambda p: p["fixtures"][0]["fixture"] == "then-redone"),
    ("gate", "smuggle-extra-line", lambda p: p["fixtures"][0]["fixture"] == "smuggle-extra-line"),
]


def _run_tool(name, extra_args):
    return subprocess.run(
        [sys.executable, "-X", "utf8",
         os.path.join(ROOT, "tools", "bench_%s.py" % name)] + extra_args,
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _git_status():
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.stdout.decode("utf-8", "replace")


def test_bench_default_output_is_local_and_leaves_tree_clean(tmp_path):
    """四个 bench 默认写 bench/<name>.local.json；跑完 git status 相对跑前零新增
    （入仓快照零改动——比较跑前/跑后，避免把本文件之外未提交改动误判为 bench 污染）。"""
    before = _git_status()
    for name, only, check in CASES:
        proc = _run_tool(name, ["--only", only, "--repeats", "1"])
        assert proc.returncode == 0, (name, proc.stdout.decode("utf-8", "replace"))
        local = os.path.join(ROOT, "bench", "%s.local.json" % name)
        assert os.path.isfile(local), "%s 未产生 %s" % (name, local)
        with open(local, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        assert payload["git_version"].startswith("git version")
        assert check(payload)
        os.remove(local)
    after = _git_status()
    assert after == before, "跑 bench 后工作树出现新改动（入仓快照被覆盖）：\n跑前：%r\n跑后：%r" % (before, after)


def test_bench_commit_snapshot_requires_explicit_flag(tmp_path):
    """只有显式 --commit-snapshot 才会碰入仓快照，且必须打印「正在覆盖入仓快照」。

    负控口径：先读入仓快照字节，--commit-snapshot 跑完后比对——写回的内容
    必然与本次重算一致才可能相等；随后**立即还原**快照字节，保证工作树干净。
    """
    name, only = "fidelity", "smuggle-extra-line"
    snapshot = os.path.join(ROOT, "bench", "%s.json" % name)
    with open(snapshot, "rb") as handle:
        original = handle.read()
    before = _git_status()
    try:
        proc = _run_tool(name, ["--only", only, "--repeats", "1", "--commit-snapshot"])
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
        stdout = proc.stdout.decode("utf-8", "replace")
        assert "正在覆盖入仓快照" in stdout, "覆盖入仓快照时未打印提示：" + stdout
    finally:
        # 无论断言成败，还原入仓快照——本测试不改变仓库状态
        with open(snapshot, "wb") as handle:
            handle.write(original)
    after = _git_status()
    assert after == before, "--commit-snapshot 测试还原后工作树不干净：\n跑前：%r\n跑后：%r" % (before, after)
