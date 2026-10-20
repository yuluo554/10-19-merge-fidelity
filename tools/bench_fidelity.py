#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`fidelity` 性能基准（M2）。

测量两件事，产物落 `bench/fidelity.json`：

1. **单进程批量 vs 逐 merge 起进程**：同一范围内取 remerge payload，
   一次 `git log --merges --remerge-diff` 对比"每个 merge 各起一次 `git log -1`"。
   这是 plan/02 §三 架构决策的现场证据（Windows 进程开销 ≈94 ms/次）。
2. **端到端**：对每个 fidelity fixture 跑一遍 `fidelity.scan`，记录耗时。

纪律：产物含环境指纹与样本量（**如实标注**），**不含阈值断言**（性能数字是快照不是门槛），
不含绝对路径（仓库用 fixture 名标识）。
"""

import argparse
import io
import json
import os
import platform
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "src"))

from gen_fixtures import FIDELITY_FIXTURES, REPO_DIR_NAME, Repo  # noqa: E402  (同目录工具模块)
from mergefidelity import __version__, fidelity, gitobj  # noqa: E402

CANONICAL = {"ensure_ascii": False, "sort_keys": True, "separators": (",", ":")}


def _time(fn, repeats=3):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        samples.append(round(time.perf_counter() - started, 6))
    return {"min": min(samples), "median": round(statistics.median(samples), 6),
            "samples": samples}


def _fixture_repo(name):
    return os.path.join(ROOT, "data", "fixtures", "fidelity", name, REPO_DIR_NAME)


def _payload_batch(repo):
    return gitobj.run_git(
        repo, ["log", "--merges", "--remerge-diff", "-p", "--no-renames",
               "--format=%H%x00%P", "HEAD"]).stdout


def _payload_per_merge(repo):
    merges = gitobj.rev_list(repo, ["--merges", "--topo-order", "HEAD"])
    for merge in merges:
        gitobj.run_git(repo, ["log", "-1", "--merges", "--remerge-diff", "-p",
                              "--no-renames", "--format=%H%x00%P", merge])


def bench_fixture(name, repeats=3):
    repo = _fixture_repo(name)
    if not os.path.isdir(repo):
        return None
    merges = gitobj.rev_list(repo, ["--merges", "HEAD"])
    entry = {
        "fixture": name,
        "merges": len(merges),
        "scan": _time(lambda: fidelity.scan(repo), repeats=repeats),
    }
    if merges:
        entry["payload_batch"] = _time(lambda: _payload_batch(repo), repeats=repeats)
        entry["payload_per_merge"] = _time(lambda: _payload_per_merge(repo), repeats=repeats)
    return entry


def build_merge_rich_repo(path, merges=8):
    """造一个"有 N 个 merge"的合成仓库，用来量出批量的斜率（fixture 只有 1 个 merge）。"""
    repo = Repo(path).init()
    repo.commit("seed", {"src/synthapp/core.py": ["line-%02d" % i for i in range(10)]})
    for index in range(merges):
        branch = "feature/synth-%02d" % index
        repo.checkout("main")
        repo.checkout(branch, create=True)
        repo.commit("feature %d edit" % index,
                    {"src/synthapp/f%02d.py" % index: ["def f%02d():" % index, "    return %d" % index]})
        repo.checkout("main")
        repo.commit("mainline %d" % index, {"docs/notes-%02d.md" % index: ["note %d" % index]})
        repo.merge(branch, message="merge %d" % index)
    return repo.path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bench_fidelity.py",
                                     description="fidelity 性能基准（产物入仓，不含阈值断言）")
    parser.add_argument("--out", default=os.path.join("bench", "fidelity.local.json"),
                    help="产物输出路径（默认写 .local.json，不碰入仓快照）")
    parser.add_argument("--commit-snapshot", action="store_true", default=False,
                        help="显式给出才覆盖入仓快照 bench/fidelity.json")
    parser.add_argument("--only", action="append", default=None)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--merges", type=int, default=8,
                        help="额外造一个含 N 个 merge 的合成仓库，量批量 vs 逐 merge 的斜率")
    parser.add_argument("--repo", default=None,
                        help="额外测一个真实仓库（可选；路径不入产物，只记 basename）")
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
        "note": "性能数字是实测快照，不是门槛；逐 merge 起进程与单进程批量的对比用于架构决策",
        "fixtures": entries,
    }

    if args.merges > 1:
        import tempfile
        from gen_fixtures import rmtree  # 只读对象也能删（Windows）
        tmp = tempfile.mkdtemp(prefix="mf-bench-")
        try:
            repo = build_merge_rich_repo(os.path.join(tmp, "many"), args.merges)
            merges = gitobj.rev_list(repo, ["--merges", "HEAD"])
            document["synthetic_many_merges"] = {
                "merges": len(merges),
                "note": "同一仓库内：一次 git log 取全量 payload vs 每个 merge 各起一次进程",
                "payload_batch": _time(lambda: _payload_batch(repo), repeats=args.repeats),
                "payload_per_merge": _time(lambda: _payload_per_merge(repo), repeats=args.repeats),
            }
        finally:
            rmtree(tmp)

    if args.repo:
        repo = args.repo
        merges = gitobj.rev_list(repo, ["--merges", "HEAD"])
        extra = {
            "repo": os.path.basename(os.path.abspath(repo)),
            "merges": len(merges),
            "scan": _time(lambda: fidelity.scan(repo), repeats=1),
            "payload_batch": _time(lambda: _payload_batch(repo), repeats=1),
            "payload_per_merge": _time(lambda: _payload_per_merge(repo), repeats=1),
        }
        document["external_repo"] = extra

    if args.commit_snapshot:
        args.out = os.path.join("bench", "fidelity.json")
        print("正在覆盖入仓快照 bench/fidelity.json")
    out = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(document, **CANONICAL) + "\n")
    print("已写入 %s（%d 个样本）" % (args.out, len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
