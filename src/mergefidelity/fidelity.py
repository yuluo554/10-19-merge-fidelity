"""`fidelity` —— Merge 保真度扫描（模块①，计划 M2 落地）。

实现口径见 `data/README.md` §4.1–§4.3 与 `plan/03-模块详设.md` §1。
本文件在骨架期只保留入口契约；落地时**同轮删除** `NotReadyError`。
"""

from .errors import NotReadyError

MODULE = "fidelity"
PLANNED = "M2"


def run(args):
    """执行 `mergefidelity fidelity <repo> [...]` → 退出码。

    实现要点（待落地）：枚举 merge → 单进程 `--remerge-diff` 拿全量 payload →
    对 payload 非空者用 `merge-tree` 复算机械树 → 逐 blob 比较 → hunk 三分。
    """
    raise NotReadyError(MODULE, PLANNED)
