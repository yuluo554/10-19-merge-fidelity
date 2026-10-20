"""测试计数自指守门（B1，迭代路线 1.1）。

问题背景（诊断 D7）：plan/ 多处登记「快层 257 passed」，而实测早已是 258+；
文档里的测试计数没有任何门禁覆盖，加一条测试就漂移一次。

守门口径（不硬编码具体数字——硬编码会让每加一条测试都改本文件）：

1. 实跑 `pytest --collect-only -q` 两次：快层（`-m "not slow"`）得 F、慢层（`-m slow`）得 S，
   全量 = F + S。
2. 只盯**当前状态**的登记位（README.md + plan/00 + plan/04 + plan/06 +
   plan/HANDOFF-M6:35 + plan/RELEASE-M6:56），要求登记数与实测一致。
   历史里程碑文档（HANDOFF-M2..M5 等）登记的是当时事实，不在本门禁范围；
   RELEASE-M6:56 / HANDOFF-M6:35 的登记行已注明「发布时点事实，当前实测见 plan/00:119」。
3. 全仓 plan/ + README 不得再出现陈旧的「257 passed」（HANDOFF-M6:72 的历史命令
   留档 `257 passed + 1 slow` 是 257 与「慢层另有 1 条」，不属于此形态）。

新增/删除测试后本守门变红，迫使同步更新文档登记数。
"""

import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLAN = os.path.join(ROOT, "plan")

# 当前状态登记位（相对 ROOT）：这些文件里登记的计数必须与实测一致。
# RELEASE-M6:56 / HANDOFF-M6:35 的「258」已注明是 M6 发布时点事实并指向 plan/00:119
# 的当前实测位，故按历史留档处理，不进行级盯守。
CURRENT_DOCS = [
    "README.md",
    os.path.join(PLAN, "00-README总览.md"),
    os.path.join(PLAN, "04-数据计划.md"),
    os.path.join(PLAN, "06-交付对标.md"),
]

# 全文禁形（陈旧基线）
STALE_SNIPPET = "257 passed"


def _collect(marker_args):
    """实跑 collect-only 拿收集数（-o addopts= 抵消 pyproject 的 -q 叠加）。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-o", "addopts=", "-p", "no:cacheprovider"] + marker_args,
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    # 输出形如「1/264 tests collected (263 deselected)」；取斜杠前被选中的数
    match = re.search(r"(\d+)(?:/\d+)? tests? collected", proc.stdout)
    assert match, "pytest --collect-only -q 未输出 collected 计数，无法守门：\n" + proc.stdout[-2000:]
    return int(match.group(1))


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def test_registered_fast_layer_counts_match_collection():
    fast = _collect(["-m", "not slow"])
    slow = _collect(["-m", "slow"])
    offenders = []
    for rel in CURRENT_DOCS:
        text = _read(os.path.join(ROOT, rel))
        for m in re.finditer(r"快层 \*{0,2}(\d+) passed\*{0,2}", text):
            if int(m.group(1)) != fast:
                offenders.append("%s: 登记快层 %s != 实测 %d" % (rel, m.group(1), fast))
        for m in re.finditer(r"慢层[^0-9\n]{0,120}?(\d+) passed", text):
            if int(m.group(1)) != slow:
                offenders.append("%s: 登记慢层 %s != 实测 %d" % (rel, m.group(1), slow))
        # 全量登记（「全量 <n>）」或「全量 <n>；」；排除「全量 1.3s」这类性能数字）
        for m in re.finditer(r"全量 (\d+)(?=[；）;\s])", text):
            if int(m.group(1)) != fast + slow:
                offenders.append("%s: 登记全量 %s != 实测 %d" % (rel, m.group(1), fast + slow))
    assert not offenders, "文档登记的测试计数与实测 collected 不一致（加/删测试后必须回填文档）：\n" + "\n".join(offenders)


def test_no_stale_257_passed():
    """「257 passed」是 M6 前的陈旧基线（实测 258 起）；HIST-M6:72 的「257 passed + 1 slow」
    形态是 257 快层 + 慢层另有 1 条，也按陈旧处理——历史命令留档已更新或注明。"""
    offenders = []
    for name in sorted(os.listdir(PLAN)):
        if name.endswith(".md"):
            text = _read(os.path.join(PLAN, name))
            if STALE_SNIPPET in text:
                offenders.append("plan/%s" % name)
    if STALE_SNIPPET in _read(os.path.join(ROOT, "README.md")):
        offenders.append("README.md")
    assert not offenders, "文档仍登记陈旧的「257 passed」：%r" % offenders
