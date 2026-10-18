"""`report` —— 确定性报告 + 可复现摘要（模块④），计划 M5 落地）。

实现口径见 `data/README.md` §四 与 `plan/03-模块详设.md`。
本文件在骨架期只保留入口契约；落地时**同轮删除** `NotReadyError`。

实现要点（待落地）：规范 JSON + digest + --verify 重推逐字节比较；报告头写死 git_version/object_format/gitattributes_oid。
"""

from .errors import NotReadyError

MODULE = "report"
PLANNED = "M5"


def run(args):
    """执行 `mergefidelity report ...` → 退出码。"""
    raise NotReadyError(MODULE, PLANNED)
