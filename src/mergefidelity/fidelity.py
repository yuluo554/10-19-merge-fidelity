"""`fidelity` —— Merge 保真度扫描（模块①）。

口径唯一权威：`data/README.md` §4.1–§4.3。要点：

* **比较方向唯一**：`git diff -U0 <mechanical_tree> <recorded_tree>`（old = 机械树，new = 记录树），
  每个 hunk 按其**自身形态**归类：含冲突标记 → `RESOLUTION`；含 `+` 行 → `SMUGGLED`；
  只含 `-` 行 → `DROPPED` 候选（再过"后续是否被重新引入"）。按"哪个 diff 命令产生的"分类
  会把同一处改动同时报成两类（实测踩到，见 plan/00 决策记录）。
* **octopus 用父提交数 >2 判定**，不解析 stderr；不进 `blob_fidelity` 分母，不影响退出码。
* **自定义 merge driver 命中的路径**输出 `SKIPPED(reason=custom_driver)`，同样不进分母。
* **不读工作区、不读 index、不读时钟**；`as_of` 来自 `--as-of` 或范围内最新提交时间。
"""

import datetime
import fnmatch

from . import __version__
from . import canonical, diffparse, gitobj
from .errors import EXIT_FINDINGS, EXIT_OK, UsageError

MODULE = "fidelity"

# git 支持的"自带" merge driver；其余视为自定义 driver
BUILTIN_MERGE_DRIVERS = frozenset(["text", "binary", "union", "ours"])

DEFAULT_KINDS = ("SMUGGLED", "DROPPED")


def _parse_gitattributes(text):
    """解析 `.gitattributes` 里的 ``merge=`` 属性 → ``[(pattern, driver)]``。

    只关心 merge 属性；其它属性一律忽略（不在本模块判定范围内）。
    """
    found = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        pattern = fields[0]
        for attr in fields[1:]:
            if attr.startswith("merge="):
                driver = attr[len("merge="):]
                if driver and driver not in BUILTIN_MERGE_DRIVERS:
                    found.append((pattern, driver))
            elif attr == "-merge":
                found.append((pattern, "-merge"))
    return found


def _pattern_matches(pattern, path):
    """gitattributes 模式的**简化**匹配（口径与边界写进 README）。

    支持：``*.ext`` / 顶层文件名 / ``dir/**`` / ``/精确路径``。
    宁可比 git 更保守（少命中 → 少 SKIPPED），也不做近似分析。
    """
    if pattern.startswith("/"):
        pattern = pattern[1:]
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3] + "/")
    if "/" not in pattern:
        return fnmatch.fnmatchcase(path.split("/")[-1], pattern)
    return fnmatch.fnmatchcase(path, pattern)


def _custom_driver_paths(repo, rev, paths):
    """命中自定义 merge driver 的路径集合（空集 = 无命中）。"""
    rules = _parse_gitattributes(gitobj.file_at(repo, rev, ".gitattributes"))
    if not rules:
        return set()
    hit = set()
    for path in sorted(paths):
        for pattern, _driver in rules:
            if _pattern_matches(pattern, path):
                hit.add(path)
                break
    return hit


def _blob_fidelity(repo, recorded_tree, mechanical_tree, *, env, excluded):
    """§4.2：分母 = 两侧都存在的 path（剔除 SKIPPED 路径）。"""
    recorded = gitobj.blob_map(repo, recorded_tree, env=env)
    mechanical = gitobj.blob_map(repo, mechanical_tree, env=env)
    for path in excluded:
        recorded.pop(path, None)
        mechanical.pop(path, None)
    both = sorted(set(recorded) & set(mechanical))
    same = [path for path in both if recorded[path] == mechanical[path]]
    value = None if not both else round(float(len(same)) / len(both), 12)
    return {
        "blob_fidelity": value,
        "paths_total": len(both),
        "paths_same": len(same),
        "path_only_in_recorded": sorted(set(recorded) - set(mechanical)),
        "path_only_in_mechanical": sorted(set(mechanical) - set(recorded)),
    }


def _reintroduced(repo, later_commits, path, addition_patch_id):
    """同一路径上，后续提交的 diff 若与目标 patch-id 相同 → 视为"重新引入"。"""
    if not addition_patch_id:
        return False
    for commit in later_commits:
        candidate = gitobj.patch_id(repo, gitobj.commit_diff(repo, commit, context=0, path=path))
        if candidate and candidate == addition_patch_id:
            return True
    return False


def classify_hunks(hunks, *, repo, later_commits, excluded_paths):
    """按 §4.3 把 tree diff 的 hunk 三分 → ``(smuggled, dropped, resolution)``。

    `hunks` 来自 ``git diff -U0 <mechanical_tree> <recorded_tree>`` —— 方向已定，
    因此"只含 ``-`` 行"即"机械树有、记录树没有" = 内容被吞掉。
    """
    smuggled, dropped, resolution = [], [], []
    for hunk in hunks:
        if hunk.path in excluded_paths or hunk.binary:
            continue
        if hunk.has_conflict_marker:
            resolution.append(hunk)
            continue
        if any(line.startswith("+") for line in hunk.lines):
            smuggled.append(hunk)
            continue
        addition = diffparse.hunk_patch_text(hunk.path, hunk.lines, reverse=True)
        if _reintroduced(repo, later_commits, hunk.path, gitobj.patch_id(repo, addition)):
            continue
        dropped.append(hunk)
    return smuggled, dropped, resolution


def _render_hunk(hunk, kind):
    return {
        "kind": kind,
        "path": hunk.path,
        "old_range": canonical.range_str(hunk.old_start, hunk.old_count),
        "new_range": canonical.range_str(hunk.new_start, hunk.new_count),
    }


def _payload_paths(entry):
    return set(hunk.path for hunk in entry.hunks) if entry is not None else set()


def scan(repo, *, since=None, until=None, range_spec=None, as_of=None,
         kinds=DEFAULT_KINDS, show_resolution=False):
    """扫描范围内的 merge，返回**未填 digest** 的报告对象。"""
    gitobj.require_git_repo(repo)
    git_version = gitobj.require_version(repo, gitobj.GIT_MIN_FIDELITY)
    object_format = gitobj.object_format(repo)

    end_rev = until or "HEAD"
    if range_spec:
        rev_args = [range_spec]
    else:
        rev_args = [end_rev]
        if since:
            rev_args.append("^%s" % since)

    merge_oids = gitobj.rev_list(repo, ["--merges", "--reverse", "--topo-order"] + rev_args)

    payload_text = gitobj.run_git(
        repo,
        ["log", "--merges", "--remerge-diff", "-p", "--no-renames",
         "--format=%H%x00%P"] + rev_args,
    ).stdout
    payload = dict((entry.commit_oid, entry)
                   for entry in diffparse.parse_remerge_log(payload_text))

    wanted = set(kinds)
    if show_resolution:
        wanted.add("RESOLUTION")

    merges, skipped, warnings = [], [], []
    failing = 0

    for merge_oid in merge_oids:
        entry = payload.get(merge_oid)
        parents = list(entry.parents) if entry is not None else []
        if not parents:
            _oid, parents_tuple, _when, _subject = gitobj.commit_meta(repo, merge_oid)
            parents = list(parents_tuple)
        if len(parents) > 2:
            # 只输出题面口径要求的字段（reason），父提交数可由对象库自查，不进 golden
            skipped.append({"merge_oid": merge_oid, "reason": "octopus"})
            continue

        base = gitobj.merge_base(repo, parents[0], parents[1])
        recorded_tree = gitobj.tree_of(repo, merge_oid)

        with gitobj.MechanicalMerge(repo, base, parents[0], parents[1]) as mechanical:
            diff_text = gitobj.tree_diff(repo, mechanical.tree_oid, recorded_tree,
                                         env=mechanical.env)
            hunks = diffparse.parse_unified_diff(diff_text)
            touched = set(hunk.path for hunk in hunks) | _payload_paths(entry)
            excluded = _custom_driver_paths(repo, merge_oid, touched)
            fidelity = _blob_fidelity(repo, recorded_tree, mechanical.tree_oid,
                                      env=mechanical.env, excluded=excluded)

            later = gitobj.commits_not_reachable(repo, merge_oid)
            smuggled, dropped, resolution = classify_hunks(
                hunks, repo=repo, later_commits=later, excluded_paths=excluded)

            tree_paths = set(hunk.path for hunk in hunks)
            orphan = sorted(_payload_paths(entry) - tree_paths - excluded)
            if orphan:
                warnings.append({"merge_oid": merge_oid, "code": "CROSSCHECK_MISMATCH",
                                 "payload_paths_not_in_tree_diff": orphan})
            if excluded:
                skipped.append({"merge_oid": merge_oid, "reason": "custom_driver",
                                "paths": sorted(excluded)})

        listed = []
        for kind, group in (("SMUGGLED", smuggled), ("DROPPED", dropped),
                            ("RESOLUTION", resolution)):
            if kind in wanted:
                listed.extend(_render_hunk(hunk, kind) for hunk in group)

        counts = {"smuggled": len(smuggled), "dropped": len(dropped),
                  "resolution": len(resolution)}
        record = {
            "merge_oid": merge_oid,
            "parents": parents,
            "merge_base": base,
            "commit_time": gitobj.commit_time(repo, merge_oid),
            "recorded_tree": recorded_tree,
            "mechanical_tree": mechanical.tree_oid,
            "mechanical_conflict": mechanical.has_conflict,
            "counts": counts,
            "hunks": listed,
            "blob_fidelity": fidelity["blob_fidelity"],
            "paths_total": fidelity["paths_total"],
            "paths_same": fidelity["paths_same"],
            "path_only_in_recorded": fidelity["path_only_in_recorded"],
            "path_only_in_mechanical": fidelity["path_only_in_mechanical"],
        }
        merges.append(record)
        if "SMUGGLED" in wanted:
            failing += counts["smuggled"]
        if "DROPPED" in wanted:
            failing += counts["dropped"]

    merges.sort(key=lambda item: (item["commit_time"], item["merge_oid"]))
    skipped.sort(key=lambda item: (item.get("reason", ""), item["merge_oid"]))
    warnings.sort(key=lambda item: item["merge_oid"])

    if as_of is None:
        as_of = _default_as_of(repo, end_rev, merge_oids)
    else:
        _validate_as_of(as_of)

    octopus = len([item for item in skipped if item["reason"] == "octopus"])
    report = {
        "tool_version": __version__,
        "git_version": git_version,
        "object_format": object_format,
        "gitattributes_oid": gitobj.attributes_oid(repo, end_rev),
        "config_overrides": list(gitobj.CONFIG_OVERRIDES),
        "range": {"kind": "range" if range_spec else ("since" if since else "all"),
                  "spec": range_spec, "since": since,
                  "until": None if end_rev == "HEAD" else end_rev},
        "as_of": as_of,
        "module": MODULE,
        "kinds": sorted(wanted),
        "merges": merges,
        "skipped": skipped,
        "warnings": warnings,
        "summary": {
            "merges_total": len(merges) + octopus,
            "merges_scanned": len(merges),
            "smuggled": sum(m["counts"]["smuggled"] for m in merges),
            "dropped": sum(m["counts"]["dropped"] for m in merges),
            "resolution": sum(m["counts"]["resolution"] for m in merges),
            "skipped": len(skipped),
            "fail_on_hits": failing,
        },
    }
    return report


def _validate_as_of(value):
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise UsageError("--as-of 必须是 YYYY-MM-DD：%r" % (value,))


def _default_as_of(repo, end_rev, merge_oids):
    """范围内最新提交的 UTC 日期（**不读系统时钟**，因此可逐字节复现）。"""
    if merge_oids:
        newest = max(merge_oids, key=lambda oid: (gitobj.commit_time(repo, oid), oid))
        stamp = gitobj.commit_time(repo, newest)
    else:
        stamp = gitobj.commit_time(repo, end_rev)
    # 不用 utcfromtimestamp：它在 3.12 起被弃用（本仓把 DeprecationWarning 升为错误）
    moment = datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc)
    return moment.strftime("%Y-%m-%d")


def render_markdown(report):
    lines = [
        "# Merge 保真度扫描",
        "",
        "- 工具版本：%s（git %s / %s）" % (report["tool_version"], report["git_version"],
                                          report["object_format"]),
        "- 范围：%s · as_of：%s" % (report["range"], report["as_of"]),
        "- 扫描 merge：%d（跳过 %d）" % (report["summary"]["merges_scanned"],
                                        report["summary"]["skipped"]),
        "",
        "| merge | blob_fidelity | SMUGGLED | DROPPED | RESOLUTION |",
        "|---|---|---|---|---|",
    ]
    for merge in report["merges"]:
        value = merge["blob_fidelity"]
        lines.append("| `%s` | %s | %d | %d | %d |" % (
            merge["merge_oid"][:12],
            "null" if value is None else "%.4f" % value,
            merge["counts"]["smuggled"], merge["counts"]["dropped"],
            merge["counts"]["resolution"]))
    if report["skipped"]:
        lines += ["", "## 跳过（显式记录，不计入分母）", ""]
        for item in report["skipped"]:
            detail = item.get("paths") or item.get("parents") or ""
            lines.append("- `%s` `%s` %s" % (item["merge_oid"][:12], item["reason"], detail))
    if report["warnings"]:
        lines += ["", "## 警告", ""]
        for item in report["warnings"]:
            lines.append("- `%s` %s" % (item["merge_oid"][:12], item["code"]))
    lines.append("")
    return "\n".join(lines)


def _kinds_from_args(args):
    raw = getattr(args, "show_kind", None)
    wanted = []
    if raw:
        for item in str(raw).split(","):
            item = item.strip().lower()
            if not item:
                continue
            if item == "all":
                return ("SMUGGLED", "DROPPED", "RESOLUTION")
            if item not in ("smuggled", "dropped", "resolution"):
                raise UsageError("--show-kind 只接受 smuggled/dropped/resolution/all：%r" % raw)
            wanted.append(item.upper())
    if getattr(args, "show_resolution", False) and "RESOLUTION" not in wanted:
        wanted.append("RESOLUTION")
    return tuple(dict.fromkeys(wanted)) or DEFAULT_KINDS


def _fail_on_hits(report, fail_on):
    if fail_on == "smuggled":
        return report["summary"]["smuggled"]
    if fail_on == "dropped":
        return report["summary"]["dropped"]
    return report["summary"]["smuggled"] + report["summary"]["dropped"]


def run(args):
    """执行 `mergefidelity fidelity scan <repo> [...]` → 退出码。"""
    report = scan(
        args.repo,
        since=getattr(args, "since", None),
        until=getattr(args, "until", None),
        range_spec=getattr(args, "range", None),
        as_of=getattr(args, "as_of", None),
        kinds=_kinds_from_args(args),
        show_resolution=bool(getattr(args, "show_resolution", False)),
    )
    if args.format == "md":
        text = render_markdown(report)
    else:
        text = canonical.dumps(canonical.with_digest(report))
    if args.out:
        canonical.write_atomic(args.out, text)
    else:
        print(text, end="" if text.endswith("\n") else "\n")

    fail_on = getattr(args, "fail_on", None)
    if fail_on and _fail_on_hits(report, fail_on):
        return EXIT_FINDINGS
    return EXIT_OK
