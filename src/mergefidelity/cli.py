"""命令行入口 —— 参数解析与退出码映射，不做任何判定。

`build_parser()` 是 README 与测试反射的唯一事实源（`tests/test_readme_gate.py`）。

退出码契约见 `plan/03-模块详设.md` §0 与 `mergefidelity.errors`。
"""

import argparse
import sys

from . import __version__
from .errors import EXIT_ENV, EXIT_OK, EXIT_USAGE, GitEnvError, MergeFidelityError, UsageError
from . import fidelity, gate, ledger, parity, report

PROG = "mergefidelity"

SUBCOMMANDS = {
    "fidelity": "Merge 保真度扫描：复算机械合并，逐 blob 对比实际记录的树",
    "parity": "跨分支补丁对齐：PRESENT / MISSING / MODIFIED 三态",
    "ledger": "Revert / 复活账本：REVERTED_NO_SUCCESSOR / REVERTED_THEN_REDONE",
    "report": "确定性报告：规范 JSON + digest + --verify 复算",
    "gate": "CI 门禁：带过期时间的基线，退出码 0/1/2/3",
}


def _ensure_utf8_stdio():
    """入口编码守卫：仅在 stdio 编码非 UTF-8 且可重配置时切换为 UTF-8。

    中文控制台（cp936）保持原样——那是用户终端的本意；这里救的是
    CI 管道等以 cp1252/ANSI 打开 stdio 的环境（否则中文输出必然
    ``UnicodeEncodeError``）。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding in ("utf8", "utf_8"):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def _add_output_options(parser):
    parser.add_argument("--format", choices=("json", "md"), default="json",
                        help="输出格式：json（规范 JSON，默认）或 md（人读摘要）")
    parser.add_argument("--out", metavar="PATH", default=None,
                        help="写入文件（默认输出到 stdout）；写盘走原子替换")
    parser.add_argument("--as-of", metavar="YYYY-MM-DD", default=None,
                        help="报告 as_of 日期（默认为范围内的最新提交时间；不读系统时钟）")


def build_parser():
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Merge 保真度审计：用 git 自己的合并引擎复算机械合并，"
                    "再与仓库里实际记录的树逐 blob 对比。",
        epilog="退出码：0 无发现 / 1 有需失败的发现 / 2 用法错误 / 3 环境不满足",
    )
    parser.add_argument("--version", action="version", version="%s %s" % (PROG, __version__))
    sub = parser.add_subparsers(dest="command", metavar="<子命令>")

    # ---- fidelity scan ----
    fid = sub.add_parser("fidelity", help=SUBCOMMANDS["fidelity"])
    fid_sub = fid.add_subparsers(dest="fidelity_command", metavar="<动作>")
    scan = fid_sub.add_parser("scan", help="扫描 merge 保真度")
    scan.add_argument("repo", help="仓库路径")
    scan.add_argument("--since", metavar="REV", default=None, help="只扫 REV.. 之后的提交")
    scan.add_argument("--until", metavar="REV", default=None, help="只扫 ..REV 之前的提交")
    scan.add_argument("--all", action="store_true", help="全量扫描（默认）")
    scan.add_argument("--range", metavar="A..B", default=None, help="显式提交范围")
    # 注意：**不设 `choices=`**。`plan/03` §1.1 与 README 场景一的口径是逗号列表
    # （`--show-kind=smuggled,dropped`），argparse 的 `choices=` 会把整串当一个值从而拒绝它；
    # 逗号拆分与非法值报错由 `fidelity._kinds_from_args` 负责（抛 `UsageError` → 退出码 2）。
    scan.add_argument("--show-kind", metavar="KINDS", default="smuggled,dropped",
                      help="输出哪些 hunk 类别：smuggled/dropped/resolution/all，可用逗号组合")
    scan.add_argument("--show-resolution", action="store_true",
                      help="同时输出 RESOLUTION 类 hunk（默认不报）")
    scan.add_argument("--fail-on", choices=("smuggled", "dropped", "any"), default=None,
                      help="命中该类别时以退出码 1 结束")
    _add_output_options(scan)

    # ---- parity ----
    par = sub.add_parser("parity", help=SUBCOMMANDS["parity"])
    par.add_argument("repo", help="仓库路径")
    par.add_argument("--from", dest="from_ref", metavar="A", required=True, help="源引用")
    par.add_argument("--to", dest="to_ref", metavar="B", required=True, help="目标引用")
    par.add_argument("--no-apply-fallback", action="store_true",
                     help="不做临时 worktree 的 apply 三态兜底（不创建任何 worktree）")
    _add_output_options(par)

    # ---- ledger ----
    led = sub.add_parser("ledger", help=SUBCOMMANDS["ledger"])
    led.add_argument("repo", help="仓库路径")
    led.add_argument("--range", metavar="A..B", default=None, help="显式提交范围")
    _add_output_options(led)

    # ---- report ----
    rep = sub.add_parser("report", help=SUBCOMMANDS["report"])
    rep.add_argument("repo", help="仓库路径")
    rep.add_argument("--range", metavar="A..B", default=None, help="显式提交范围")
    rep.add_argument("--verify", metavar="PATH", default=None,
                     help="读回已生成的报告并逐字节复算校验（不一致时退出码 1）")
    rep.add_argument("--parity-from", metavar="REF", default=None,
                     help="额外的跨分支对齐：源引用（与 --parity-to 成对使用）")
    rep.add_argument("--parity-to", metavar="REF", default=None,
                     help="额外的跨分支对齐：目标引用")
    _add_output_options(rep)

    # ---- gate ----
    gat = sub.add_parser("gate", help=SUBCOMMANDS["gate"])
    gat.add_argument("repo", help="仓库路径")
    gat.add_argument("--baseline", metavar="PATH", required=True, help="基线文件（TOML）")
    gat.add_argument("--since", metavar="REV", default=None, help="只扫 REV.. 之后的增量")
    gat.add_argument("--fail-on", choices=("smuggled", "dropped", "any"), default="any",
                     help="把哪些类别的**新增** finding 计为失败（基线内/过期条目不受此过滤）")
    _add_output_options(gat)

    return parser


_DISPATCH = {
    "parity": parity.run,
    "ledger": ledger.run,
    "report": report.run,
    "gate": gate.run,
}


def dispatch(args):
    """按子命令分派；返回退出码。"""
    command = args.command
    if command == "fidelity":
        if getattr(args, "fidelity_command", None) != "scan":
            raise UsageError("fidelity 需要动作参数：scan（例：mergefidelity fidelity scan <repo>）")
        return fidelity.run(args)
    handler = _DISPATCH.get(command)
    if handler is None:
        raise UsageError("未知子命令：%s" % command)
    return handler(args)


def main(argv=None):
    """CLI 主入口：返回退出码（不自行 `sys.exit`）。"""
    _ensure_utf8_stdio()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse 对 --help/--version/用法错误走 SystemExit
        return EXIT_OK if exc.code is None else int(exc.code)

    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return EXIT_USAGE

    try:
        code = dispatch(args)
    except GitEnvError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return EXIT_ENV
    except MergeFidelityError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return exc.exit_code
    return int(code or EXIT_OK)
