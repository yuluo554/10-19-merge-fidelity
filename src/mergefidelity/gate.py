"""`gate` —— CI 门禁 + 带过期时间的基线（模块⑤），计划 M5 落地）。

实现口径见 `data/README.md` §四 与 `plan/03-模块详设.md`。
本文件在骨架期只保留入口契约；落地时**同轮删除** `NotReadyError`。

实现要点（待落地）：基线解析（受限 TOML 子集）+ expires/justification/stale 语义 + 退出码 0/1/2/3。
"""

from .errors import NotReadyError

MODULE = "gate"
PLANNED = "M5"


def run(args):
    """执行 `mergefidelity gate ...` → 退出码。"""
    raise NotReadyError(MODULE, PLANNED)
