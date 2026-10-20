#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`ledger` 性能基准（M4）。

测量并落 `bench/ledger.json`：

1. **端到端**：对每个 ledger fixture 跑一次 `ledger.ledger_scan`（含反向 patch-id 校验
   与 `--find-object` 候选筛选），记录耗时、**条目数**与三状态分布。
2. 同一 fixture 重复 `--repeats` 次，取 min/median——性能数字是快照，不是门槛。

纪律：产物含环境指纹与样本量（**如实标注**），**不含阈值断言**，不含绝对路径
（仓库用 fixture 名标识）。
"""

import argparse
import io
import json
import os
import platform
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "src"))

from gen_fixtures import LEDGER_FIXTURES, REPO_DIR_NAME  # noqa: E402  (同目录工具模块)
from mergefidelity import __version__, gitobj, ledger  # noqa: E402

CANONICAL = {"ensure_ascii": False, "sort_keys": True, "separators": (",", ":")}


def _time(fn, repeats=3):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        samples.append(round(time.perf_counter() - started, 6))
    return {"min": min(samples), "median": round(statistics.median(samples), 6),
            "samples": samples}


def bench_fixture(name, repeats=3):
    repo = os.path.join(ROOT, "data", "fixtures", "ledger", name, REPO_DIR_NAME)
    if not os.path.isdir(repo):
        return None

    def scan():
        return ledger.ledger_scan(repo)

    report = scan()
    return {
        "fixture": name,
        "entries": len(report["entries"]),
        "counts": report["counts"],
        "unavailable": report["unavailable"],
        "scan": _time(scan, repeats=repeats),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bench_ledger.py",
                                     description="ledger 性能基准（产物入仓，不含阈值断言）")
    parser.add_argument("--out", default=os.path.join("bench", "ledger.local.json"),
                    help="产物输出路径（默认写 .local.json，不碰入仓快照）")
    parser.add_argument("--commit-snapshot", action="store_true", default=False,
                        help="显式给出才覆盖入仓快照 bench/ledger.json")
    parser.add_argument("--only", action="append", default=None)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)

    names = args.only or LEDGER_FIXTURES
    entries = [entry for entry in (bench_fixture(name, args.repeats) for name in names)
               if entry]
    if not entries:
        print("没有可测的 fixture：先生成 data/fixtures（tools/gen_fixtures.py）", file=sys.stderr)
        return 2

    document = {
        "tool_version": __version__,
        "git_version": gitobj.version(ROOT)[1],
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "repeats": args.repeats,
        "note": ("性能数字是实测快照，不是门槛；每条 revert 都会做一次反向 patch-id 校验，"
                 "并用 `git log --find-object` 收窄 successor 候选"),
        "fixtures": entries,
    }

    if args.commit_snapshot:
        args.out = os.path.join("bench", "ledger.json")
        print("正在覆盖入仓快照 bench/ledger.json")
    out = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(document, **CANONICAL) + "\n")
    print("已写入 %s（%d 个样本）" % (args.out, len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
