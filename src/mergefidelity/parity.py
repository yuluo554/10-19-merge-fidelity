"""`parity` —— 跨分支补丁对齐（模块②，M3）。

口径唯一权威：`data/README.md` §4.4。要点：

* **候选集**：`git rev-list --cherry-pick --right-only A...B`。它用**默认上下文**的
  cherry 判定，所以"跨行号/空白等价"的提交仍会留在候选里——这正是 `-U0` 口径要补的一类。
* **两种 patch 上下文各有用途**：`-U0` patch-id 判**等价**（对行号与空白免疫）；
  两个 `apply` 检查用 `-U3` 判**是否存在**（`-U0` 补丁没有上下文，apply 会过于宽松）。
* **三态优先级固定**：`U0_patchid` 相等 → `PRESENT(basis=patchid)`；
  在 **A（源侧）** 的临时 worktree 上 `apply --reverse --check`（`-U3`）成功 →
  `PRESENT(basis=apply)`；`apply --check` 成功 → `MISSING`；皆失败 → `MODIFIED`。
  worktree 挂 B 侧是错的：候选提交本身就来自 B，反向检查会恒成功、三态退化。
* **`note` 只提示不改判定**：`content_equivalent_at_other_path`（同内容落在别的路径）
  ——path 参与 patch-id，因此这种候选**仍是 MISSING**。
* **`--no-apply-fallback`**：不创建任何 worktree；patch-id 不等即 `MODIFIED(basis=patchid)`
  （**不猜** MISSING——判"是否存在"需要 apply 检查这个证据）。
* 临时 worktree 只创建**一次**（per invocation）；成功/异常两条路径都清理；
  报告中不得出现该绝对路径。

排序口径：候选按 `git rev-list` 的给定顺序逐条处理（与 `expect.json` golden 一致；
`plan/03` §2.2 的"按 (commit_time, oid) 排序"系笔误，已在 `plan/HANDOFF-M4.md` 与本轮回写中更正）。
"""

import datetime

from . import __version__
from . import canonical, diffparse, gitobj
from .errors import EXIT_OK, UsageError
from .fidelity import require_ref

MODULE = "parity"

STATUS_PRESENT = "PRESENT"
STATUS_MISSING = "MISSING"
STATUS_MODIFIED = "MODIFIED"

BASIS_PATCHID = "patchid"
BASIS_APPLY = "apply"

NOTE_ALREADY_PRESENT = "content_already_present"
NOTE_PARTIAL = "partial_or_context_conflict"
NOTE_OTHER_PATH = "content_equivalent_at_other_path"


# --------------------------------------------------------------------------- A 侧索引

def _side_index(repo, ref):
    """A 侧索引：``patch_id`` → 提交列表（按 rev-list 顺序）+ 内容指纹索引。

    * ``by_patchid``：值取列表首项作为 ``equivalent_source``（与 golden 一致——
      `git rev-list --reverse` 的"最早到达者"）。
    * ``by_content``：``hunk 内容行元组`` → ``[(path, commit)]``，只用于**提示**。
    """
    by_patchid = {}
    by_content = {}
    for commit in gitobj.rev_list(repo, ["--reverse", str(ref)]):
        diff_u0 = gitobj.commit_diff(repo, commit, context=0)
        patch = gitobj.patch_id(repo, diff_u0)
        if patch:
            by_patchid.setdefault(patch, []).append(commit)
        for hunk in diffparse.parse_unified_diff(diff_u0):
            by_content.setdefault(tuple(hunk.lines), []).append((hunk.path, commit))
    return {"by_patchid": by_patchid, "by_content": by_content}


# --------------------------------------------------------------------------- apply 兜底

def _worktree_applies(worktree, patch_text, *, reverse):
    """在临时 worktree 上做一次 `apply --check`（不写文件）。"""
    args = ["apply", "--check"]
    if reverse:
        args.append("--reverse")
    result = gitobj.run_git(worktree, args, input_text=patch_text, check=False)
    return result.returncode == 0


def _classify_with_apply(worktree, patch_u3):
    """apply 三态兜底：返回 ``(status, note)``。"""
    if _worktree_applies(worktree, patch_u3, reverse=True):
        return STATUS_PRESENT, NOTE_ALREADY_PRESENT
    if _worktree_applies(worktree, patch_u3, reverse=False):
        return STATUS_MISSING, None
    return STATUS_MODIFIED, NOTE_PARTIAL


# --------------------------------------------------------------------------- 主流程

def _resolve_refs(repo, from_ref, to_ref):
    """校验并解析两侧引用。解不出来是**用法错误（2）**，不是环境问题（3）。"""
    require_ref(repo, from_ref, "--from")
    require_ref(repo, to_ref, "--to")
    return gitobj.rev_parse(repo, "%s^{commit}" % from_ref), \
        gitobj.rev_parse(repo, "%s^{commit}" % to_ref)


def _candidates(repo, from_ref, to_ref):
    return gitobj.rev_list(
        repo, ["--cherry-pick", "--right-only", "%s...%s" % (from_ref, to_ref)])


def _cherry_count(repo, from_ref, to_ref):
    """`git cherry -v A B` 的候选条数（只用于与 rev-list 交叉核对）；不可用返回 ``None``。"""
    result = gitobj.run_git(repo, ["cherry", "-v", str(from_ref), str(to_ref)], check=False)
    if result.returncode != 0:
        return None
    return len([line for line in result.stdout.splitlines() if line.strip()])


def _evaluate(repo, commit, side, worktree, *, apply_fallback):
    """单个候选 → 判定行（未排序/未渲染）。"""
    subject = gitobj.commit_meta(repo, commit)[3]
    diff_u0 = gitobj.commit_diff(repo, commit, context=0)
    patch_u0 = gitobj.patch_id(repo, diff_u0)

    equivalent_source = None
    if patch_u0 and patch_u0 in side["by_patchid"]:
        status, basis, note = STATUS_PRESENT, BASIS_PATCHID, None
        equivalent_source = side["by_patchid"][patch_u0][0]
    elif not apply_fallback:
        # 没有 apply 证据：patch-id 不等**不能**推出"缺失"，只能记 MODIFIED
        status, basis, note = STATUS_MODIFIED, BASIS_PATCHID, None
    else:
        patch_u3 = gitobj.commit_diff(repo, commit, context=3)
        status, note = _classify_with_apply(worktree, patch_u3)
        basis = BASIS_APPLY

    if status != STATUS_PRESENT and not note:
        note, equivalent_source = _other_path_note(side, diff_u0)

    return {
        "commit": commit,
        "subject": subject,
        "u0_patchid": patch_u0,
        "status": status,
        "basis": basis,
        "note": note,
        "equivalent_source": equivalent_source,
        "paths": gitobj.paths_of_commit(repo, commit),
    }


def _other_path_note(side, diff_u0):
    """同内容落在别的路径 → 只提示（`equivalent_source` 指向 A 侧那条提交）。

    路径参与 patch-id，因此这种候选**仍是 MISSING**，不得因"别处有同内容"判 PRESENT。
    """
    for hunk in diffparse.parse_unified_diff(diff_u0):
        for path, commit in side["by_content"].get(tuple(hunk.lines), []):
            if path != hunk.path:
                return NOTE_OTHER_PATH, commit
    return None, None


def parity_scan(repo, from_ref, to_ref, *, apply_fallback=True, as_of=None):
    """跑一次跨分支对齐，返回**未填 digest** 的报告对象。"""
    gitobj.require_git_repo(repo)
    git_version = gitobj.require_version(repo, gitobj.GIT_MIN_FIDELITY)
    object_format = gitobj.object_format(repo)
    from_oid, to_oid = _resolve_refs(repo, from_ref, to_ref)

    side = _side_index(repo, from_ref)
    candidates = _candidates(repo, from_ref, to_ref)

    worktree_note = {"created": False, "reason": None}
    rows = []
    if apply_fallback and candidates:
        worktree_note["created"] = True
        worktree_note["reason"] = "apply_fallback"
        with gitobj.temporary_worktree(repo, from_ref) as worktree:
            for commit in candidates:
                rows.append(_evaluate(repo, commit, side, worktree, apply_fallback=True))
    else:
        for commit in candidates:
            rows.append(_evaluate(repo, commit, side, None, apply_fallback=False))

    if as_of is None:
        as_of = _default_as_of(repo, from_oid, to_oid)
    else:
        _validate_as_of(as_of)

    warnings = _crosscheck(repo, from_ref, to_ref, len(candidates))

    present = len([row for row in rows if row["status"] == STATUS_PRESENT])
    missing = len([row for row in rows if row["status"] == STATUS_MISSING])
    modified = len([row for row in rows if row["status"] == STATUS_MODIFIED])
    total = len(rows)

    return {
        "tool_version": __version__,
        "git_version": git_version,
        "object_format": object_format,
        "gitattributes_oid": gitobj.attributes_oid(repo, to_oid),
        "config_overrides": list(gitobj.CONFIG_OVERRIDES),
        "range": {"kind": "parity", "from": from_ref, "to": to_ref},
        "as_of": as_of,
        "module": MODULE,
        "apply_fallback": bool(apply_fallback),
        "from": from_ref,
        "to": to_ref,
        "from_oid": from_oid,
        "to_oid": to_oid,
        "candidates": total,
        "present": present,
        "missing": missing,
        "modified": modified,
        "patch_parity": None if total == 0 else round(float(present) / total, 12),
        "commits": rows,
        "worktree": worktree_note,
        "warnings": warnings,
    }


def _crosscheck(repo, from_ref, to_ref, candidate_count):
    """`git cherry -v A B` 与 `rev-list --cherry-pick --right-only` 交叉核对。

    数量不一致 → `warnings` 里记一条（**不改判定、不失败**）——两条命令的
    cherry 判定口径可能因 git 版本不同而分叉，如实暴露比静默取其一好。
    """
    other = _cherry_count(repo, from_ref, to_ref)
    if other is None or other == candidate_count:
        return []
    return [{"code": "CHERRY_COUNT_MISMATCH",
             "rev_list_cherry_pick": candidate_count, "git_cherry": other}]


def _default_as_of(repo, *oids):
    """两侧最新提交时间的 UTC 日期（**不读系统时钟**，因此可逐字节复现）。"""
    stamps = [gitobj.commit_time(repo, oid) for oid in oids if oid]
    stamp = max(stamps) if stamps else 0
    moment = datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc)
    return moment.strftime("%Y-%m-%d")


def _validate_as_of(value):
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise UsageError("--as-of 必须是 YYYY-MM-DD：%r" % (value,))


# --------------------------------------------------------------------------- 渲染

def render_markdown(report):
    lines = [
        "# 跨分支补丁对齐（parity）",
        "",
        "- 工具版本：%s（%s / %s）" % (report["tool_version"], report["git_version"],
                                      report["object_format"]),
        "- 方向：`%s` → `%s`（as_of %s）" % (report["from"], report["to"], report["as_of"]),
        "- 候选 %d：PRESENT %d / MISSING %d / MODIFIED %d · patch_parity %s"
        % (report["candidates"], report["present"], report["missing"], report["modified"],
           "null" if report["patch_parity"] is None else "%.4f" % report["patch_parity"]),
        "- apply 兜底：%s" % ("启用（临时 worktree）" if report["apply_fallback"] else "关闭"),
        "",
        "| commit | status | basis | subject | paths |",
        "|---|---|---|---|---|",
    ]
    for row in report["commits"]:
        lines.append("| `%s` | %s | %s | %s | %s |" % (
            row["commit"][:12], row["status"], row["basis"], row["subject"],
            ", ".join(row["paths"]) or "-"))
    if report["warnings"]:
        lines += ["", "## 警告", ""]
        for item in report["warnings"]:
            lines.append("- %s" % item["code"])
    lines.append("")
    return "\n".join(lines)


def run(args):
    """执行 `mergefidelity parity <repo> --from=A --to=B [...]` → 退出码。"""
    report = parity_scan(
        args.repo,
        args.from_ref,
        args.to_ref,
        apply_fallback=not bool(getattr(args, "no_apply_fallback", False)),
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
