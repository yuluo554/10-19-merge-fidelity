"""`ledger` —— Revert / 复活账本（模块③），计划 M4 落地）。

实现口径见 `data/README.md` §四 与 `plan/03-模块详设.md`。
本文件在骨架期只保留入口契约；落地时**同轮删除** `NotReadyError`。

实现要点（待落地）：--grep 枚举 revert；反向 patch-id 校验；--find-object 找重放；UNVERIFIED 与无 successor 分开。
"""

from .errors import NotReadyError

MODULE = "ledger"
PLANNED = "M4"


def run(args):
    """执行 `mergefidelity ledger ...` → 退出码。"""
    raise NotReadyError(MODULE, PLANNED)
