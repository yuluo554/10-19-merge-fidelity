"""`parity` —— 跨分支补丁对齐（模块②），计划 M3 落地）。

实现口径见 `data/README.md` §四 与 `plan/03-模块详设.md`。
本文件在骨架期只保留入口契约；落地时**同轮删除** `NotReadyError`。

实现要点（待落地）：两个分支/引用 A=源、B=目标；候选集 --cherry-pick --right-only；等价判定 -U0 patch-id；apply 三态兜底用临时 worktree。
"""

from .errors import NotReadyError

MODULE = "parity"
PLANNED = "M3"


def run(args):
    """执行 `mergefidelity parity ...` → 退出码。"""
    raise NotReadyError(MODULE, PLANNED)
