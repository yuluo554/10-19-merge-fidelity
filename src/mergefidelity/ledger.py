"""`ledger` —— Revert / 复活账本（模块③，M4）。

口径唯一权威：`data/README.md` §四 与 `plan/03-模块详设.md` §3。要点：

* **枚举**：`git log --grep='^This reverts commit' --format=%H<US>%B <range>`——
  从**正文**里提取被回滚 OID（不解析 subject：`Revert "…"` 这种标题是 `git revert`
  自动生成的，可能被改写）。
* **被回滚 OID**：正则 `^This reverts commit ([0-9a-f]{7,64})`（`re.MULTILINE`），
  再 `rev-parse --verify <oid>^{commit}` 落成完整 OID。
* **校验（这是本模块与"看正文就信"的分界线）**：拿 revert commit 的 `-U0` patch-id
  与**被回滚提交的 diff 取反**后的 `-U0` patch-id 比对。不等 → `REVERT_UNVERIFIED`
  （`verified=false`，**不猜意图**，也不算 successor）。
* **重放**：patch-id 相等时，在 revert **之后**的提交里找与原始 `-U0` patch-id 相等的
  successor（`git log --find-object` 只作更省的候选筛选，**结论口径以 patch-id 相等为准**）。
  找到 → `REVERTED_THEN_REDONE(successor_oid=…)`；找不到 → `REVERTED_NO_SUCCESSOR`。
* **`--find-object` 不可用**（git < 2.16）：`unavailable` 记 `git_too_old`，状态给
  `REVERT_UNVERIFIED`，**不降级猜**（"没 successor"是一个断言，缺证不能下）。
* 排序 `(被回滚 commit_time, revert_oid)`；同一 revert 只入账一次。

**`verified` 与 `status` 是两件事**（别混读）：

* `verified` = **这条 revert 本身属实吗**（反向 patch-id 校验通过与否）；
* `status` = **重放结论**（被回滚的改动后来有没有被重新落地）。

因此"反向校验通过、但 `--find-object` 不可用导致重放判不了"这一格是
`verified=true` + `status=REVERT_UNVERIFIED`——**我们确知这条 revert 是真的，
但无法判定它是否被重做**。两种 `REVERT_UNVERIFIED` 的区别写在 `unavailable` 里：
它非空 = 重放判不了（能力缺失）；它为空 = 正文声称的回滚与实际 diff 对不上。
"""

import datetime
import re

from . import __version__
from . import canonical, gitobj
from .errors import EXIT_OK, UsageError
from .fidelity import validate_range_spec

MODULE = "ledger"

STATUS_NO_SUCCESSOR = "REVERTED_NO_SUCCESSOR"
STATUS_THEN_REDONE = "REVERTED_THEN_REDONE"
STATUS_UNVERIFIED = "REVERT_UNVERIFIED"

REASON_GIT_TOO_OLD = "git_too_old"
CAPABILITY_FIND_OBJECT = "find-object"

# 只认正文里 git revert 生成的那一行；7–64 位十六进制（短 OID / sha1 / sha256 都覆盖）
REVERT_MARKER_RE = re.compile(r"^This reverts commit ([0-9a-f]{7,64})", re.MULTILINE)

# 枚举用的记录分隔：`\x1e` 分隔提交、`\x1f` 分隔 OID 与正文（正文里不会出现这两个控制符）
RECORD_SEP = "\x1e"
FIELD_SEP = "\x1f"


# --------------------------------------------------------------------------- 枚举

def _enumerate_reverts(repo, range_spec):
    """返回 ``[(revert_oid, body)]``（正文提取；同一 revert 只出现一次）。"""
    rev_args = [range_spec] if range_spec else ["--all"]
    text = gitobj.run_git(
        repo,
        ["log", "--grep=^This reverts commit",
         "--format=%H" + FIELD_SEP + "%B" + RECORD_SEP] + rev_args,
    ).stdout

    seen = set()
    records = []
    for chunk in text.split(RECORD_SEP):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        oid, _, body = chunk.partition(FIELD_SEP)
        oid = oid.strip()
        if not oid or oid in seen:
            continue
        seen.add(oid)
        records.append((oid, body))
    return records


def _resolve_commit(repo, rev):
    """``rev^{commit}`` 的完整 OID；解不出来返回 ``None``。"""
    result = gitobj.run_git(repo, ["rev-parse", "--verify", "--quiet", "%s^{commit}" % rev],
                            check=False)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


# --------------------------------------------------------------------------- 校验与重放

def _u0_patchid(repo, commit):
    return gitobj.patch_id(repo, gitobj.commit_diff(repo, commit, context=0))


def _reversed_patchid(repo, commit):
    """被回滚提交的 diff **取反**后的 `-U0` patch-id；根提交不可取反 → ``None``。"""
    text = gitobj.commit_diff(repo, commit, context=0, reverse=True)
    if text is None:
        return None
    return gitobj.patch_id(repo, text)


def _find_object_supported(repo):
    """`--find-object` 需 git ≥ 2.16（`GIT_MIN_LEDGER`）；低于门槛交给 `unavailable`。

    独立成函数是为了让"打了补丁的旧 git"这条路径可被测试直接触发（monkeypatch）。
    """
    return gitobj.version(repo)[0] >= gitobj.GIT_MIN_LEDGER


def _find_object_commits(repo, blobs):
    """触及这些 blob 的提交集合（候选筛选）；命令不可用返回 ``None``。"""
    found = set()
    for blob in blobs:
        result = gitobj.run_git(
            repo, ["log", "--find-object=%s" % blob, "--all", "--format=%H"], check=False)
        if result.returncode != 0:
            return None
        found.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return found


def _find_successor(repo, revert_oid, original_pid, blobs):
    """在 revert 之后的提交里找同 `-U0` patch-id 的 successor。返回 ``(successor, skipped)``。

    ``skipped`` 为真表示 `--find-object` 不可用（候选无法确定），调用方据此写
    `unavailable` 并**不下**"没有 successor"的结论。

    **筛选只用于加速命中，不足以支撑"没有"这个结论**：`-U0` patch-id 对空白免疫，
    而 `--find-object` 认的是 blob 内容——一次"只差空白"的重新落地写出的是**另一个 blob**，
    于是它不在筛选集里。因此在筛选集里没命中时，必须**回到全量 later 提交再扫一遍**
    才能下 `REVERTED_NO_SUCCESSOR`（否则会静默漏报，正是本工具要审计的那类毛病）。
    """
    supported = _find_object_supported(repo)
    if not supported:
        return None, True

    later = gitobj.commits_not_reachable(repo, revert_oid)
    touched = _find_object_commits(repo, blobs) if blobs else set()
    if touched is None:
        return None, True

    narrowed = [oid for oid in later if oid in touched]
    hit = _scan_for_patchid(repo, narrowed, revert_oid, original_pid)
    if hit:
        return hit, False
    # 筛选集落空：全量复扫（结论口径是 patch-id 相等，不是"碰过同一个 blob"）
    return _scan_for_patchid(repo, later, revert_oid, original_pid), False


def _scan_for_patchid(repo, candidates, revert_oid, original_pid):
    """在候选里找第一个同 `-U0` patch-id 的提交（候选已按 `(commit_time, oid)` 排序）。"""
    if not original_pid:
        return None
    for commit in candidates:
        if commit == revert_oid:
            continue
        if _u0_patchid(repo, commit) == original_pid:
            return commit
    return None


# --------------------------------------------------------------------------- 主流程

def _entry(repo, revert_oid, body, *, unavailable):
    """单个 revert → 一条账本（未排序）。``unavailable`` 是可变列表，用于追加能力缺失记录。"""
    match = REVERT_MARKER_RE.search(body)
    if not match:
        return None
    reverted_oid = _resolve_commit(repo, match.group(1))
    if not reverted_oid:
        # 正文声称的提交在当前对象库里不存在：无法校验也无法重放，跳过（不猜）
        return None

    revert_pid = _u0_patchid(repo, revert_oid)
    reversed_pid = _reversed_patchid(repo, reverted_oid)
    verified = bool(revert_pid and reversed_pid and revert_pid == reversed_pid)

    successor = None
    if not verified:
        status = STATUS_UNVERIFIED
    else:
        original_pid = _u0_patchid(repo, reverted_oid)
        blobs = gitobj.changed_blob_oids(repo, reverted_oid)
        successor, skipped = _find_successor(repo, revert_oid, original_pid, blobs)
        if skipped:
            status = STATUS_UNVERIFIED
            if not unavailable:
                unavailable.append({"reason": REASON_GIT_TOO_OLD,
                                    "capability": CAPABILITY_FIND_OBJECT})
        else:
            status = STATUS_THEN_REDONE if successor else STATUS_NO_SUCCESSOR

    _oid, _parents, reverted_time, reverted_subject = gitobj.commit_meta(repo, reverted_oid)
    return {
        "revert_oid": revert_oid,
        "reverted_oid": reverted_oid,
        "reverted_subject": reverted_subject,
        "reverted_commit_time": reverted_time,
        "status": status,
        "verified": verified,
        "successor_oid": successor,
        "paths": gitobj.paths_of_commit(repo, revert_oid),
    }


def ledger_scan(repo, *, range_spec=None, as_of=None):
    """跑一次 revert 账本，返回**未填 digest** 的报告对象。"""
    gitobj.require_git_repo(repo)
    git_version = gitobj.require_version(repo, gitobj.GIT_MIN_LEDGER)
    object_format = gitobj.object_format(repo)

    # 先拦"用户输入解不出来的引用"（用法错误 2），再谈环境（3）
    validate_range_spec(repo, range_spec)
    # 报告头指纹取范围的右端（与 fidelity 的 end_rev 同口径）；无范围则 HEAD
    end_rev = _range_end(range_spec)

    unavailable = []
    entries = []
    for revert_oid, body in _enumerate_reverts(repo, range_spec):
        entry = _entry(repo, revert_oid, body, unavailable=unavailable)
        if entry is not None:
            entries.append(entry)

    entries.sort(key=lambda item: (item["reverted_commit_time"], item["revert_oid"]))

    if as_of is None:
        as_of = _default_as_of(repo, entries)
    else:
        _validate_as_of(as_of)

    return {
        "tool_version": __version__,
        "git_version": git_version,
        "object_format": object_format,
        "gitattributes_oid": gitobj.attributes_oid(repo, end_rev),
        "config_overrides": list(gitobj.CONFIG_OVERRIDES),
        "range": {"kind": "range" if range_spec else "all", "spec": range_spec},
        "as_of": as_of,
        "module": MODULE,
        "entries": entries,
        "counts": {
            "no_successor": len([e for e in entries if e["status"] == STATUS_NO_SUCCESSOR]),
            "then_redone": len([e for e in entries if e["status"] == STATUS_THEN_REDONE]),
            "unverified": len([e for e in entries if e["status"] == STATUS_UNVERIFIED]),
        },
        "unavailable": unavailable,
    }


def _range_end(range_spec):
    """报告头指纹用的"范围右端"：`A..B` → `B`；单个 REV → 它自己；无范围 → `HEAD`。

    与 `fidelity` 的 `end_rev` 同口径——`.gitattributes` 会改变 merge driver 的判定，
    因此它的 blob OID 必须进报告头；取范围右端而不是恒取 HEAD，才能让"扫历史某个区间"
    的报告也如实反映**那个时点**的 attributes。
    """
    if not range_spec:
        return "HEAD"
    separator = "..." if "..." in range_spec else ".."
    if separator not in range_spec:
        return range_spec
    _left, _, right = range_spec.partition(separator)
    return right or "HEAD"


def _default_as_of(repo, entries):
    """账本内最新提交时间的 UTC 日期（**不读系统时钟**，因此可逐字节复现）。"""
    stamps = []
    for entry in entries:
        stamps.append(entry["reverted_commit_time"])
        stamps.append(gitobj.commit_time(repo, entry["revert_oid"]))
    if not stamps:
        head = _resolve_commit(repo, "HEAD")
        if not head:
            return None
        stamps.append(gitobj.commit_time(repo, head))
    moment = datetime.datetime.fromtimestamp(max(stamps), datetime.timezone.utc)
    return moment.strftime("%Y-%m-%d")


def _validate_as_of(value):
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise UsageError("--as-of 必须是 YYYY-MM-DD：%r" % (value,))


# --------------------------------------------------------------------------- 渲染

def render_markdown(report):
    lines = [
        "# Revert / 复活账本（ledger）",
        "",
        "- 工具版本：%s（%s / %s）" % (report["tool_version"], report["git_version"],
                                      report["object_format"]),
        "- 范围：%s · as_of：%s" % (report["range"], report["as_of"]),
        "- 条目 %d：无 successor %d / 已复活 %d / 未核实 %d"
        % (len(report["entries"]), report["counts"]["no_successor"],
           report["counts"]["then_redone"], report["counts"]["unverified"]),
        "",
        "| revert | status | reverted | successor | subject |",
        "|---|---|---|---|---|",
    ]
    for entry in report["entries"]:
        lines.append("| `%s` | %s | `%s` | %s | %s |" % (
            entry["revert_oid"][:12], entry["status"], entry["reverted_oid"][:12],
            "`%s`" % entry["successor_oid"][:12] if entry["successor_oid"] else "-",
            entry["reverted_subject"]))
    if report["unavailable"]:
        lines += ["", "## 不可用能力（不降级猜）", ""]
        for item in report["unavailable"]:
            lines.append("- `%s` %s" % (item["capability"], item["reason"]))
    lines.append("")
    return "\n".join(lines)


def run(args):
    """执行 `mergefidelity ledger <repo> [--range=…] [...]` → 退出码。"""
    report = ledger_scan(
        args.repo,
        range_spec=getattr(args, "range", None),
        as_of=getattr(args, "as_of", None),
    )
    if args.format == "md":
        text = render_markdown(report)
    else:
        text = canonical.dumps(canonical.with_digest(report))
    if args.out:
        canonical.write_atomic(args.out, text)
    else:
        print(text, end="" if text.endswith("\n") else "\n")
    return EXIT_OK
