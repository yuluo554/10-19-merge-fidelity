#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`gate` 性能基准（M5）。

测量并落 `bench/gate.json`：

1. **端到端**：对每个 fidelity fixture 跑一次"基线解析 + fidelity 扫描 + 分类"的完整
   门禁路径（`gate.gate_scan`），记录耗时、**基线命中数**与四类计数。
2. 同一 fixture 重复 `--repeats` 次，取 min/median——性能数字是快照，不是门槛。

基线用该 fixture 的**真实 finding id** 现造（未过期），因此 `baselined` 命中数是
"该 fixture 全部事故类 finding 都被基线覆盖"时的实测值；另记 `scanned_findings`
（扫描到的 finding 总数）与 `baseline_entries`，样本量如实标注。

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

from gen_fixtures import FIDELITY_FIXTURES, REPO_DIR_NAME  # noqa: E402  (同目录工具模块)
from mergefidelity import __version__, fidelity, gate, gitobj  # noqa: E402

CANONICAL = {"ensure_ascii": False, "sort_keys": True, "separators": (",", ":")}

# 基准用的"永久有效"过期日：只量性能，不制造过期噪声
FAR_FUTURE = "2099-12-31"


def _time(fn, repeats=3):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        samples.append(round(time.perf_counter() - started, 6))
    return {"min": min(samples), "median": round(statistics.median(samples), 6),
            "samples": samples}


def bench_fixture(name, repeats=3):
    repo = os.path.join(ROOT, "data", "fixtures", "fidelity", name, REPO_DIR_NAME)
    if not os.path.isdir(repo):
        return None

    findings = fidelity.findings_of(fidelity.scan(repo))
    baseline = [
        {"id": finding["id"], "expires": FAR_FUTURE,
         "justification": "基准样本：该 fixture 的已知 finding", "line": 0}
        for finding in findings
    ]

    def scan():
        return gate.gate_scan(repo, baseline)

    document, code = scan()
    return {
        "fixture": name,
        "baseline_entries": len(baseline),
        "scanned_findings": len(findings),
        "counts": document["counts"],
        "exit_code": code,
        "scan": _time(scan, repeats=repeats),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bench_gate.py",
                                     description="gate 性能基准（产物入仓，不含阈值断言）")
    parser.add_argument("--out", default=os.path.join("bench", "gate.json"))
    parser.add_argument("--only", action="append", default=None)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)

    names = args.only or FIDELITY_FIXTURES
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
        "note": ("性能数字是实测快照，不是门槛；每个样本都是完整的门禁路径"
                 "（受限 TOML 解析 + fidelity 全量扫描 + 基线分类）。"
                 "基线用该 fixture 的真实 finding id 现造，故 `baselined` 即全部事故类命中数"),
        "fixtures": entries,
    }

    out = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(document, **CANONICAL) + "\n")
    print("已写入 %s（%d 个样本）" % (args.out, len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
