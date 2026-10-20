#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`parity` 性能基准（M3）。

测量并落 `bench/parity.json`：

1. **端到端**：对每个 parity fixture 跑一次 `parity.parity_scan`（含临时 worktree 的
   apply 兜底），记录耗时与**候选数**。
2. **无兜底对比**：同一 fixture 跑 `--no-apply-fallback`，量出"临时 worktree 的固定开销"
   ——这是 K25/K30 的现场证据（worktree 只创建一次，开销与候选数无关）。

纪律：产物含环境指纹与样本量（**如实标注**），**不含阈值断言**（性能数字是快照不是门槛），
不含绝对路径（仓库用 fixture 名标识）。
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

from gen_fixtures import PARITY_FIXTURES, REPO_DIR_NAME  # noqa: E402  (同目录工具模块)
from mergefidelity import __version__, gitobj, parity  # noqa: E402

CANONICAL = {"ensure_ascii": False, "sort_keys": True, "separators": (",", ":")}
SCENARIO_FILE = "expect.json"


def _time(fn, repeats=3):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        samples.append(round(time.perf_counter() - started, 6))
    return {"min": min(samples), "median": round(statistics.median(samples), 6),
            "samples": samples}


def _fixture_repo(name):
    return os.path.join(ROOT, "data", "fixtures", "parity", name, REPO_DIR_NAME)


def _scenario(name):
    with io.open(os.path.join(ROOT, "data", "fixtures", "parity", name, SCENARIO_FILE),
                 encoding="utf-8") as handle:
        return json.load(handle)


def bench_fixture(name, repeats=3):
    repo = _fixture_repo(name)
    if not os.path.isdir(repo):
        return None
    scenario = _scenario(name)["expect"]
    from_ref, to_ref = scenario["from"], scenario["to"]

    def with_fallback():
        return parity.parity_scan(repo, from_ref, to_ref)

    def without_fallback():
        return parity.parity_scan(repo, from_ref, to_ref, apply_fallback=False)

    report = with_fallback()
    return {
        "fixture": name,
        "from": from_ref,
        "to": to_ref,
        "candidates": report["candidates"],
        "patch_parity": report["patch_parity"],
        "scan_with_apply_fallback": _time(with_fallback, repeats=repeats),
        "scan_no_apply_fallback": _time(without_fallback, repeats=repeats),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bench_parity.py",
                                     description="parity 性能基准（产物入仓，不含阈值断言）")
    parser.add_argument("--out", default=os.path.join("bench", "parity.local.json"),
                    help="产物输出路径（默认写 .local.json，不碰入仓快照）")
    parser.add_argument("--commit-snapshot", action="store_true", default=False,
                        help="显式给出才覆盖入仓快照 bench/parity.json")
    parser.add_argument("--only", action="append", default=None)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)

    names = args.only or PARITY_FIXTURES
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
        "note": ("性能数字是实测快照，不是门槛；apply 兜底的临时 worktree 每次调用只创建一次，"
                 "开销与候选数无关（对比 scan_no_apply_fallback）"),
        "fixtures": entries,
    }

    if args.commit_snapshot:
        args.out = os.path.join("bench", "parity.json")
        print("正在覆盖入仓快照 bench/parity.json")
    out = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(document, **CANONICAL) + "\n")
    print("已写入 %s（%d 个样本）" % (args.out, len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
