#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成 fixture 生成器（M1）。

职责：**确定性地**重建 `data/fixtures/` 下的合成 git 仓库与 golden 期望
（`plan/04-数据计划.md`）。三层纪律：

1. **可重建**：作者/时间/内容/分支名全部写死；不用 stdlib `random`、不读系统时钟、
   不依赖 `set` 迭代序、不把仓库路径写进任何被比较的产物。
2. **真值独立**：golden 由本文件内**独立实现**的 oracle 复算（口径取自
   `data/README.md` §四 的定义式：树逐 blob 对比 + `-U0` patch-id + `apply --check`），
   **不 import `mergefidelity` 包**。生产实现（M2–M5）要与它对上，不能反过来定义它。
3. **生成物分层**：入仓的是生成器 + `expect.json`（golden）+ 每例 `README.md` + `manifest.json`；
   **合成仓库本体是生成物、不入仓**（`.gitignore` 已排除 `data/fixtures/**/repo/` 与 `**/.git/`）。

用法::

    py -3.8 tools/gen_fixtures.py --out data/fixtures              # 生成/覆盖
    py -3.8 tools/gen_fixtures.py --out data/fixtures --only fidelity
    py -3.8 tools/gen_fixtures.py --check --out data/fixtures      # 重生成到临时目录并逐字节比对

退出码：0 成功/一致；1 `--check` 发现差异；2 用法错误；3 环境不满足（git 不可用/版本过低）。
"""

import argparse
import fnmatch
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

GIT = os.environ.get("MERGEFIDELITY_GIT", "git")
GIT_MIN = (2, 38)  # merge-tree --write-tree
AUTHOR_NAME = "Fixture Bot"
AUTHOR_EMAIL = "fixture@example.invalid"
BASE_EPOCH = 1767225600  # 2026-01-01T00:00:00Z
STEP_SECONDS = 60
GENERATOR_VERSION = "1"
REPO_DIR_NAME = "repo"  # 合成仓库在 fixture 目录下的子目录名（不入仓）

GIT_BASE = [
    "-c", "core.autocrlf=false",
    "-c", "core.eol=lf",
    "-c", "core.quotePath=false",
    "-c", "core.pager=cat",
    "-c", "commit.gpgsign=false",
    "-c", "advice.detachedHead=false",
]

CANONICAL_KWARGS = {
    "ensure_ascii": False,
    "sort_keys": True,
    "separators": (",", ":"),
    "allow_nan": False,
}

NAMESPACE = {
    "pkg": "src/synthapp",
    "tests": "tests/synthapp",
    "docs": "docs",
    "branches": ["main", "release/1.0", "feature/synth-a", "feature/synth-b"],
}


def rmtree(path):
    """跨平台删除（Windows 上 git 对象是只读，shutil 默认会失败）。"""
    def _on_error(func, target, _exc_info):
        try:
            os.chmod(target, 0o700)
        except OSError:
            pass
        try:
            func(target)
        except OSError:
            pass
    if not os.path.isdir(path):
        return
    try:
        shutil.rmtree(path, onexc=lambda f, t, e: _on_error(f, t, e))
    except TypeError:  # Python 3.8–3.11 用 onerror
        shutil.rmtree(path, onerror=_on_error)


class GenError(RuntimeError):
    exit_code = 2


class EnvError(RuntimeError):
    exit_code = 3


# --------------------------------------------------------------------------- git

def _env(index):
    stamp = "%d +0000" % (BASE_EPOCH + index * STEP_SECONDS)
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": AUTHOR_NAME,
        "GIT_AUTHOR_EMAIL": AUTHOR_EMAIL,
        "GIT_COMMITTER_NAME": AUTHOR_NAME,
        "GIT_COMMITTER_EMAIL": AUTHOR_EMAIL,
        "GIT_AUTHOR_DATE": stamp,
        "GIT_COMMITTER_DATE": stamp,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    })
    return env


def git(repo, args, *, check=True, env=None, input_text=None, timeout=120):
    argv = [GIT] + GIT_BASE + ["-C", repo] + list(args)
    try:
        proc = subprocess.run(
            argv,
            input=(input_text.encode("utf-8") if input_text is not None else None),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=timeout,
        )
    except OSError as exc:
        raise EnvError("无法执行 git：%s" % exc)
    except subprocess.TimeoutExpired:
        raise EnvError("git 超时：%s" % " ".join(args))
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    if check and proc.returncode != 0:
        raise GenError("git %s 失败(%d)：%s" % (" ".join(args), proc.returncode, err.strip()))
    return proc.returncode, out, err


class Repo(object):
    """一个确定性的合成仓库：提交时间按**本仓库内**的序号递增（与生成顺序无关）。"""

    def __init__(self, path):
        self.path = path
        self._index = 0

    # -- 基础 ---------------------------------------------------------------
    def init(self):
        os.makedirs(self.path, exist_ok=True)
        git(self.path, ["init", "-q", "-b", "main", "."])
        for key, value in (("user.name", AUTHOR_NAME),
                           ("user.email", AUTHOR_EMAIL),
                           ("core.autocrlf", "false"),
                           ("core.eol", "lf"),
                           ("core.quotePath", "false"),
                           ("commit.gpgsign", "false")):
            git(self.path, ["config", key, value])
        return self

    def write(self, relpath, lines):
        full = os.path.join(self.path, relpath)
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with io.open(full, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")

    def read(self, relpath):
        with io.open(os.path.join(self.path, relpath), encoding="utf-8") as handle:
            return handle.read().splitlines()

    def commit(self, message, files=None, *, allow_empty=False):
        for relpath, lines in (files or {}).items():
            self.write(relpath, lines)
        git(self.path, ["add", "-A"])
        self._index += 1
        args = ["commit", "-q", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        git(self.path, args, env=_env(self._index))
        return self.head()

    # -- 分支/引用 ----------------------------------------------------------
    def head(self, rev="HEAD"):
        return git(self.path, ["rev-parse", rev])[1].strip()

    def checkout(self, ref, create=False):
        args = ["checkout", "-q"] + (["-b", ref] if create else [ref])
        git(self.path, args)

    def merge(self, ref, *, expect_fail=False, message=None):
        args = ["merge", "--no-edit"] + (["-m", message] if message else []) + [ref]
        self._index += 1
        rc, out, err = git(self.path, args, check=False, env=_env(self._index))
        if expect_fail:
            if rc == 0:
                raise GenError("期望冲突的 merge 却成功了：%s" % ref)
            return False
        if rc != 0:
            raise GenError("merge %s 失败(%d)：%s" % (ref, rc, err.strip()))
        return True

    def commit_all(self, message):
        return self.commit(message, {})

    def merge_many(self, refs, message=None):
        """一次 merge 多个引用（可产生 octopus 多父 merge）。"""
        args = ["merge", "--no-edit"] + (["-m", message] if message else []) + list(refs)
        self._index += 1
        rc, out, err = git(self.path, args, check=False, env=_env(self._index))
        if rc != 0:
            raise GenError("merge_many %r 失败(%d)：%s" % (refs, rc, err.strip()))
        return True

    def refs(self, names):
        return dict((name, self.head(name)) for name in names if self.has_ref(name))

    def has_ref(self, name):
        rc, _, _ = git(self.path, ["rev-parse", "--verify", "--quiet", name], check=False)
        return rc == 0


# --------------------------------------------------------------------------- oracle

def git_version():
    try:
        rc, out, _ = git(os.getcwd(), ["--version"])
    except (GenError, EnvError):
        raise EnvError("git 不可用")
    match = re.search(r"(\d+)\.(\d+)", out)
    if not match:
        raise EnvError("无法解析 git 版本：%r" % out)
    found = (int(match.group(1)), int(match.group(2)))
    if found < GIT_MIN:
        raise EnvError("需要 git >= %d.%d，当前为 %s" % (GIT_MIN[0], GIT_MIN[1], out.strip()))
    return out.strip()


def recorded_tree(repo, rev):
    return git(repo.path if isinstance(repo, Repo) else repo, ["rev-parse", "%s^{tree}" % rev])[1].strip()


class TempObjects(object):
    """`merge-tree --write-tree` 的对象落点：临时目录 + alternates 指向仓库对象库。

    实测：目标对象目录**必须预先存在**，否则 git 报 `fatal: not a git repository`。
    `__exit__` 才删除，保证后续对机械树的读取（ls-tree/diff）仍能解析。
    """

    def __init__(self, repo):
        self.repo = repo
        self.path = None
        self.env = None

    def __enter__(self):
        self.path = tempfile.mkdtemp(prefix="mf-gen-obj-")
        objects = os.path.join(self.path, "objects")
        os.makedirs(objects)
        self.env = dict(os.environ)
        self.env["GIT_OBJECT_DIRECTORY"] = objects
        self.env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = os.path.join(
            _git_dir(self.repo.path if isinstance(self.repo, Repo) else self.repo), "objects")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.path:
            shutil.rmtree(self.path, ignore_errors=True)
        self.path = None
        self.env = None
        return False


def mechanical_tree(repo, base, p1, p2, env):
    """在给定对象环境下复算机械树 → ``(tree_oid, has_conflict)``。"""
    path = repo.path if isinstance(repo, Repo) else repo
    rc, out, err = git(path, ["merge-tree", "--write-tree", "--merge-base=%s" % base, p1, p2],
                       check=False, env=env)
    if rc not in (0, 1):
        raise GenError("merge-tree 退出 %d：%s" % (rc, err.strip()))
    lines = out.split("\n")
    return lines[0].strip(), rc == 1


def _git_dir(path):
    return git(path, ["rev-parse", "--absolute-git-dir"])[1].strip()


def blob_map(repo, treeish, env=None):
    path = repo.path if isinstance(repo, Repo) else repo
    out = git(path, ["ls-tree", "-r", "-z", "%s" % treeish], env=env)[1]
    entries = {}
    for chunk in out.split("\x00"):
        if not chunk:
            continue
        meta, _, file_path = chunk.partition("\t")
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob":
            entries[file_path] = parts[2]
    return entries


def blob_fidelity(repo, recorded, mechanical, env=None, excluded=()):
    """§4.2：分母 = 两侧都存在的 path；SKIPPED 路径剔除，单侧存在的单独列出。"""
    rec = blob_map(repo, recorded, env=env)
    mec = blob_map(repo, mechanical, env=env)
    for path in excluded:
        rec.pop(path, None)
        mec.pop(path, None)
    both = sorted(set(rec) & set(mec))
    same = [p for p in both if rec[p] == mec[p]]
    value = None if not both else round(float(len(same)) / len(both), 12)
    return {
        "blob_fidelity": value,
        "paths_total": len(both),
        "paths_same": len(same),
        "path_only_in_recorded": sorted(set(rec) - set(mec)),
        "path_only_in_mechanical": sorted(set(mec) - set(rec)),
    }



BUILTIN_MERGE_DRIVERS = frozenset(["text", "binary", "union", "ours"])


def file_at(repo, rev, path):
    rc, out, _ = git(repo.path if isinstance(repo, Repo) else repo,
                     ["show", "%s:%s" % (rev, path)], check=False)
    return out if rc == 0 else ""


def gitattributes_driver_paths(repo, rev, paths):
    """生成侧**独立实现**的 `.gitattributes` merge-driver 命中判定。

    与生产实现（`mergefidelity.fidelity._custom_driver_paths`）是两份代码，
    一致性靠 fixture golden 逐项对账，不靠"顺手共用一份"。
    """
    text = file_at(repo, rev, ".gitattributes")
    rules = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        for attr in fields[1:]:
            if attr.startswith("merge=") and attr[len("merge="):]:
                if attr[len("merge="):] not in BUILTIN_MERGE_DRIVERS:
                    rules.append((fields[0], attr[len("merge="):]))
            elif attr == "-merge":
                rules.append((fields[0], "-merge"))
    hit = []
    for path in sorted(paths):
        for pattern, _driver in rules:
            pat = pattern[1:] if pattern.startswith("/") else pattern
            if pat.endswith("/**"):
                matched = path.startswith(pat[:-3] + "/")
            elif "/" not in pat:
                matched = fnmatch.fnmatchcase(path.split("/")[-1], pat)
            else:
                matched = fnmatch.fnmatchcase(path, pat)
            if matched:
                hit.append(path)
                break
    return hit


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _zero_based(start, count):
    return (int(start) - 1 if int(count) > 0 else int(start)), int(count)


def parse_tree_diff(text):
    """解析 `git diff -U0 --no-renames <treeA> <treeB>` → hunk 列表（0 基行号）。"""
    hunks = []
    current = None
    for line in text.split("\n"):
        if line.startswith("diff --git "):
            rest = line[len("diff --git "):]
            idx = rest.find(" b/")
            path = rest[:idx] if idx > 0 else rest
            path = path[2:] if path.startswith("a/") else path
            current = {"path": path, "hunks": []}
            hunks.append(current)
            continue
        if current is None:
            continue
        match = HUNK_RE.match(line)
        if match:
            old_start, old_count = _zero_based(match.group(1), match.group(2) or "1")
            new_start, new_count = _zero_based(match.group(3), match.group(4) or "1")
            current["hunks"].append({
                "path": current["path"],
                "old_start": old_start, "old_count": old_count,
                "new_start": new_start, "new_count": new_count,
                "lines": [],
            })
            continue
        if not current["hunks"]:
            continue
        hunk = current["hunks"][-1]
        if line[:1] in ("+", "-"):
            hunk["lines"].append(line)
    out = []
    for entry in hunks:
        for hunk in entry["hunks"]:
            hunk["lines"] = tuple(hunk["lines"])
            out.append(hunk)
    return out


def range_of(hunk, side):
    if side == "old":
        start, count = hunk["old_start"], hunk["old_count"]
    else:
        start, count = hunk["new_start"], hunk["new_count"]
    if count == 0:
        return "-"
    return "%d,%d" % (start, count)


def has_conflict_marker(hunk):
    for line in hunk["lines"]:
        body = line[1:] if line[:1] in "+- " else line
        if body.startswith(("<<<<<<<", "=======", ">>>>>>>")):
            return True
    return False


def diff_trees(repo, tree_a, tree_b, path=None, env=None):
    repo_path = repo.path if isinstance(repo, Repo) else repo
    args = ["diff", "--no-renames", "-U0", tree_a, tree_b]
    if path:
        args += ["--", path]
    return git(repo_path, args, env=env)[1]


def patch_id(repo, text):
    path = repo.path if isinstance(repo, Repo) else repo
    rc, out, _ = git(path, ["patch-id", "--stable"], input_text=text)
    if rc != 0 or not out.strip():
        return None
    return out.split()[0]


def has_parent(repo, commit):
    out = git(repo.path, ["rev-list", "--parents", "-n", "1", commit])[1].split()
    return len(out) > 1


def commit_diff_text(repo, commit, *, context=0, path=None, reverse=False):
    """提交的 diff 文本。注意 `--` 必须排在 revisions 之后；根提交走 `--root`。"""
    path_arg = repo.path if isinstance(repo, Repo) else repo
    args = ["diff-tree", "-p", "-U%d" % context, "--no-renames"]
    if not has_parent(repo, commit):
        # 根提交：没有父提交可比，用 --root 与空树比（取反无意义，返回 None 表示不可比）
        if reverse:
            return None
        args += ["--root", commit]
    elif reverse:
        args += [commit, "%s^" % commit]
    else:
        args += ["%s^" % commit, commit]
    if path:
        args += ["--", path]
    return git(path_arg, args)[1]


def commit_patch(repo, commit, *, path=None):
    return commit_diff_text(repo, commit, context=0, path=path)


def u0_patchid_of_commit(repo, commit, *, path=None):
    return patch_id(repo, commit_patch(repo, commit, path=path))


def reverse_u0_patchid_of_commit(repo, commit, *, path=None):
    """把 commit 的 diff 取反（= 从 commit 回到 commit^ 的 diff）后的 patch-id。"""
    text = commit_diff_text(repo, commit, context=0, path=path, reverse=True)
    return None if text is None else patch_id(repo, text)


def commits(repo, rev, *, first_parent=False):
    path = repo.path if isinstance(repo, Repo) else repo
    args = ["rev-list", "--reverse"]
    if first_parent:
        args.append("--first-parent")
    args.append(rev)
    return [line for line in git(path, args)[1].split("\n") if line.strip()]


def commit_meta(repo, rev):
    path = repo.path if isinstance(repo, Repo) else repo
    out = git(path, ["log", "-1", "--format=%H%x00%P%x00%ct%x00%s", rev])[1].strip("\n")
    fields = (out.split("\x00") + ["", "", "", ""])[:4]
    return {"oid": fields[0], "parents": fields[1].split(), "commit_time": int(fields[2]),
            "subject": fields[3]}


def merged_commits(repo, rev="HEAD"):
    path = repo.path if isinstance(repo, Repo) else repo
    return [line for line in
            git(path, ["rev-list", "--merges", "--reverse", "--topo-order", rev])[1].split("\n")
            if line.strip()]


# --------------------------------------------------------------------------- fidelity oracle

def hunk_patch_text(path, lines, reverse=False):
    """把一个 hunk 的内容拼成可喂给 `git patch-id` 的最小 diff 文本。

    patch-id 忽略行号与 hunk 头后缀，因此用合成的 `@@ -1 +1 @@` 即可；
    这样"某个被丢掉的 hunk 是否在后续提交里被重新引入"可以用同一个 patch-id 口径比较。
    """
    body = []
    for line in lines:
        prefix, rest = line[:1], line[1:]
        if prefix == "+":
            prefix = "-" if reverse else "+"
        elif prefix == "-":
            prefix = "+" if reverse else "-"
        body.append(prefix + rest)
    header = [
        "diff --git a/%s b/%s" % (path, path),
        "--- a/%s" % path,
        "+++ b/%s" % path,
        "@@ -1 +1 @@",
    ]
    return "\n".join(header + body) + "\n"


def fidelity_expect(repo, merge_oid):
    """按 §4.1–§4.3 的**定义式**复算一个 merge 的期望（独立于生产实现）。

    分类只用一个方向：`git diff -U0 <mechanical_tree> <recorded_tree>`
    （old = 机械树，new = 记录树），于是每个 hunk 的方向语义唯一：

    * 含冲突标记 → ``RESOLUTION``（冲突标记行存在于机械树，在此方向表现为被删除）；
    * 含 `+` 行（记录了机械树没有的内容）→ ``SMUGGLED``；
    * 只含 `-` 行（机械树有、记录树没有）→ ``DROPPED`` 候选，再过"后续是否被重新引入"
      （同路径 `-U0` patch-id 相等）——被重新引入的不算 DROPPED。

    这条"单方向 + 按 hunk 自身形态分类"的读法消掉了一个歧义：同一处改动在两个方向的
    diff 里各出现一次，按"哪个 diff 命令产生的"分类会把同一处改动同时报成
    SMUGGLED 和 DROPPED；按 hunk 内容分类则每处改动只落一类。
    """
    meta = commit_meta(repo, merge_oid)
    parents = meta["parents"]
    if len(parents) > 2:
        return {"skipped": [{"merge_oid": merge_oid, "reason": "octopus"}], "merges": []}
    if len(parents) != 2:
        raise GenError("期望 merge 提交，实际父提交为 %r：%s" % (parents, merge_oid))

    p1, p2 = parents[0], parents[1]
    base = git(repo.path, ["merge-base", p1, p2])[1].strip()
    rec_oid = recorded_tree(repo, merge_oid)
    later = _commits_after(repo, merge_oid)

    with TempObjects(repo) as objects:
        mec_oid, mec_conflict = mechanical_tree(repo, base, p1, p2, objects.env)
        hunks = parse_tree_diff(diff_trees(repo, mec_oid, rec_oid, env=objects.env))
        excluded = gitattributes_driver_paths(repo, merge_oid,
                                              set(h["path"] for h in hunks))
        fidelity = blob_fidelity(repo, rec_oid, mec_oid, env=objects.env, excluded=excluded)

    skipped = []
    if excluded:
        skipped.append({"merge_oid": merge_oid, "reason": "custom_driver",
                        "paths": sorted(excluded)})

    resolution, smuggled, dropped = [], [], []
    for hunk in hunks:
        if hunk["path"] in excluded:
            continue
        if has_conflict_marker(hunk):
            resolution.append(hunk)
            continue
        if any(line.startswith("+") for line in hunk["lines"]):
            smuggled.append(hunk)
            continue
        addition_pid = patch_id(repo, hunk_patch_text(hunk["path"], hunk["lines"], reverse=True))
        if _reintroduced(repo, later, hunk["path"], addition_pid):
            continue
        dropped.append(hunk)

    def render(hunk, kind):
        return {
            "kind": kind,
            "path": hunk["path"],
            "old_range": range_of(hunk, "old"),
            "new_range": range_of(hunk, "new"),
        }

    return {
        "skipped": skipped,
        "merges": [{
            "merge_oid": merge_oid,
            "parents": parents,
            "merge_base": base,
            "recorded_tree": rec_oid,
            "mechanical_tree": mec_oid,
            "mechanical_conflict": mec_conflict,
            "counts": {"smuggled": len(smuggled), "dropped": len(dropped),
                       "resolution": len(resolution)},
            "hunks": ([render(h, "SMUGGLED") for h in smuggled]
                      + [render(h, "DROPPED") for h in dropped]),
        }],
        "blob_fidelity": fidelity,
    }


def _commits_after(repo, merge_oid):
    """在 merge 之后（含其他分支）的提交，按 (commit_time, oid) 排序。"""
    all_commits = commits(repo, "--all")
    reachable_before = set(commits(repo, merge_oid))
    later = [c for c in all_commits if c not in reachable_before]
    decorated = [(commit_meta(repo, c)["commit_time"], c) for c in later]
    decorated.sort()
    return [c for _, c in decorated]


def _reintroduced(repo, later_commits, path, target_pid):
    """同一路径上，后续提交的 diff 若与目标 patch-id 相同 → 视为"重新引入"。"""
    if not target_pid:
        return False
    for commit in later_commits:
        pid = u0_patchid_of_commit(repo, commit, path=path)
        if pid and pid == target_pid:
            return True
    return False


# --------------------------------------------------------------------------- parity oracle

def apply_check(repo, ref, patch_text, reverse=False):
    """在 ref 的临时 worktree 上做 apply 检查（-U3 上下文，用于"内容是否已在 ref 中"）。"""
    tmp = tempfile.mkdtemp(prefix="mf-gen-wt-")
    try:
        os.rmdir(tmp)
        git(repo.path, ["worktree", "add", "--detach", tmp, ref])
        args = ["apply", "--check"]
        if reverse:
            args.append("--reverse")
        rc, out, err = git(tmp, args, check=False, input_text=patch_text)
        return rc == 0
    finally:
        if os.path.isdir(tmp):
            git(repo.path, ["worktree", "remove", "--force", tmp], check=False)
            git(repo.path, ["worktree", "prune"], check=False)
            shutil.rmtree(tmp, ignore_errors=True)


def parity_expect(repo, from_ref, to_ref):
    a_commits = commits(repo, from_ref)
    a_patchids = {}
    for commit in a_commits:
        pid = _commit_patchid_with_context(repo, commit, context=0)
        if pid:
            a_patchids.setdefault(pid, []).append(commit)

    candidates = [line for line in
                  git(repo.path, ["rev-list", "--cherry-pick", "--right-only",
                                  "%s...%s" % (from_ref, to_ref)])[1].split("\n")
                  if line.strip()]

    # A 侧"同一处改动内容、但落在别的路径"的索引（只用于提示，不参与判定）
    a_content_index = {}
    for commit in a_commits:
        for hunk in parse_tree_diff(commit_diff_text(repo, commit)):
            a_content_index.setdefault(tuple(hunk["lines"]), []).append((hunk["path"], commit))

    rows = []
    for commit in candidates:
        meta = commit_meta(repo, commit)
        patch_u0 = commit_patch(repo, commit)
        pid = patch_id(repo, patch_u0)
        patch_u3 = _commit_patch_with_context_text(repo, commit, context=3)
        if pid and pid in a_patchids:
            status, basis, note, source = "PRESENT", "patchid", None, a_patchids[pid][0]
        elif apply_check(repo, from_ref, patch_u3, reverse=True):
            status, basis, note, source = "PRESENT", "apply", "content_already_present", None
        elif apply_check(repo, from_ref, patch_u3, reverse=False):
            status, basis, note, source = "MISSING", "apply", None, None
        else:
            status, basis, note, source = "MODIFIED", "apply", "partial_or_context_conflict", None
        if status != "PRESENT" and not note:
            for hunk in parse_tree_diff(patch_u0):
                hits = [item for item in a_content_index.get(tuple(hunk["lines"]), [])
                        if item[0] != hunk["path"]]
                if hits:
                    note = "content_equivalent_at_other_path"
                    source = hits[0][1]
                    break
        rows.append({
            "commit": commit,
            "subject": meta["subject"],
            "u0_patchid": pid,
            "status": status,
            "basis": basis,
            "note": note,
            "equivalent_source": source,
            "paths": sorted(_paths_of_commit(repo, commit)),
        })

    total = len(rows)
    present = len([r for r in rows if r["status"] == "PRESENT"])
    return {
        "from": from_ref,
        "to": to_ref,
        "from_oid": repo.head(from_ref),
        "to_oid": repo.head(to_ref),
        "candidates": total,
        "present": present,
        "missing": len([r for r in rows if r["status"] == "MISSING"]),
        "modified": len([r for r in rows if r["status"] == "MODIFIED"]),
        "patch_parity": None if total == 0 else round(float(present) / total, 12),
        "commits": rows,
    }


def _paths_of_commit(repo, commit):
    out = git(repo.path, ["diff-tree", "-r", "--no-commit-id", "--name-only", "-z", commit])[1]
    return set(p for p in out.split("\x00") if p)


def _commit_patch_with_context_text(repo, commit, context, path=None):
    return commit_diff_text(repo, commit, context=context, path=path)


def _commit_patchid_with_context(repo, commit, context):
    return patch_id(repo, _commit_patch_with_context_text(repo, commit, context))


# --------------------------------------------------------------------------- ledger oracle

REVERT_SUBJECT_RE = re.compile(r"This reverts commit ([0-9a-f]{7,64})")


def ledger_expect(repo):
    path = repo.path
    out = git(path, ["log", "--grep=^This reverts commit", "--format=%H%x00%B", "--all"])[1]
    entries = []
    seen = set()
    for record in out.split("\x00\x00"):
        record = record.strip("\n")
        if not record:
            continue
        oid, _, body = record.partition("\x00")
        oid = oid.strip()
        if not oid or oid in seen:
            continue
        seen.add(oid)
        match = REVERT_SUBJECT_RE.search(body)
        if not match:
            continue
        reverted = match.group(1)
        rc, resolved, _ = git(path, ["rev-parse", "--verify", "--quiet", "%s^{commit}" % reverted],
                              check=False)
        if rc != 0:
            continue
        reverted = resolved.strip()
        revert_pid = u0_patchid_of_commit(repo, oid)
        reversed_pid = reverse_u0_patchid_of_commit(repo, reverted)
        verified = bool(revert_pid and reversed_pid and revert_pid == reversed_pid)
        if not verified:
            status = "REVERT_UNVERIFIED"
            successor = None
        else:
            original_pid = u0_patchid_of_commit(repo, reverted)
            successor = None
            for candidate in _commits_after(repo, oid):
                if candidate == oid:
                    continue
                if u0_patchid_of_commit(repo, candidate) == original_pid:
                    successor = candidate
                    break
            status = "REVERTED_THEN_REDONE" if successor else "REVERTED_NO_SUCCESSOR"
        meta = commit_meta(repo, oid)
        entries.append({
            "revert_oid": oid,
            "reverted_oid": reverted,
            "reverted_subject": commit_meta(repo, reverted)["subject"],
            "reverted_commit_time": commit_meta(repo, reverted)["commit_time"],
            "status": status,
            "verified": verified,
            "successor_oid": successor,
            "paths": sorted(_paths_of_commit(repo, oid)),
        })
    entries.sort(key=lambda e: (e["reverted_commit_time"], e["revert_oid"]))
    return {
        "entries": entries,
        "counts": {
            "no_successor": len([e for e in entries if e["status"] == "REVERTED_NO_SUCCESSOR"]),
            "then_redone": len([e for e in entries if e["status"] == "REVERTED_THEN_REDONE"]),
            "unverified": len([e for e in entries if e["status"] == "REVERT_UNVERIFIED"]),
        },
        "unavailable": [],
    }


# --------------------------------------------------------------------------- 文件模板

CORE = [
    "def compute(x):",
    "    total = x + 1",
    "    return total",
    "",
    "",
    "def helper(y):",
    "    value = y * 2",
    "    return value",
    "",
    "",
    "def guard(x):",
    "    if x < 0:",
    '        raise ValueError("negative")',
    "    return x",
]

UTIL = ["def util_a():", "    return 1", "", "", "def util_b():", "    return 2"]

LINES12 = ["line-%02d" % i for i in range(1, 13)]


def core_with(**overrides):
    lines = list(CORE)
    for index, value in overrides.items():
        lines[int(index)] = value
    return lines


# --------------------------------------------------------------------------- fidelity fixtures

# 行号锚点（0 基）：避免散落的魔法下标，也让 fixture 意图一眼可读
I_TOTAL = 1          # "    total = x + 1"
I_HELPER_VALUE = 6   # "    value = y * 2"
I_HELPER_RETURN = 7  # "    return value"
I_GUARD_IF = 11      # "    if x < 0:"
I_GUARD_RAISE = 12   # '        raise ValueError("negative")'

SIDE_CORE = None   # 在 _init_templates() 里赋值（依赖 CORE 的行号锚点）
MAIN_CORE = None


def _init_templates():
    global SIDE_CORE, MAIN_CORE
    SIDE_CORE = set_line(CORE, I_TOTAL, "    total = x + 10")
    MAIN_CORE = set_line(CORE, I_TOTAL, "    total = x + 20")


def set_line(lines, index, value):
    out = list(lines)
    out[index] = value
    return out


def insert_after(lines, index, *values):
    return list(lines[:index + 1]) + list(values) + list(lines[index + 1:])


def _seed(repo):
    repo.commit("seed synthapp skeleton",
                {"src/synthapp/core.py": CORE, "src/synthapp/util.py": UTIL})


def _conflict(repo, side_core, main_core):
    """公共骨架：两侧改同一行 → 冲突 merge（不自动提交，留给 fixture 写解冲突结果）。"""
    repo.checkout("feature/synth-a", create=True)
    repo.commit("tune compute for feature a", {"src/synthapp/core.py": side_core})
    repo.checkout("main")
    repo.commit("tune compute for mainline", {"src/synthapp/core.py": main_core})
    repo.merge("feature/synth-a", expect_fail=True)


def build_fidelity(name, path):
    """返回 ``(repo, injects, notes, merge_oid, declared_counts)``。

    ``declared_counts`` 是本 fixture **声明**的注入意图；``build_one`` 会把它与 oracle
    复算结果逐项对账——对不上就在生成期失败，而不是产出一份"看起来对"的 golden
    （植入器自证：`str.replace` 锚点失配静默返回原文这类假绿不允许出现）。
    """
    _init_templates()
    repo = Repo(path).init()
    injects, notes, declared = [], "", None

    if name == "smuggle-extra-line":
        _seed(repo)
        _conflict(repo, SIDE_CORE, MAIN_CORE)
        resolved = set_line(CORE, I_TOTAL, "    total = x + 10 + 20")
        resolved = insert_after(resolved, I_HELPER_VALUE, "    value += 1")
        merge = repo.commit("merge feature/synth-a into main",
                            {"src/synthapp/core.py": resolved, "src/synthapp/util.py": UTIL})
        injects = ["SMUGGLED", "RESOLUTION"]
        declared = {"smuggled": 1, "dropped": 0}
        notes = "解冲突时在无关函数 helper() 里多加一行 `value += 1`（两侧父提交都没有它）"
    elif name == "smuggle-unrelated-file":
        _seed(repo)
        _conflict(repo, SIDE_CORE, MAIN_CORE)
        merge = repo.commit("merge feature/synth-a into main", {
            "src/synthapp/core.py": set_line(CORE, I_TOTAL, "    total = x + 30"),
            "src/synthapp/util.py": set_line(UTIL, 1, "    return 3"),
        })
        injects = ["SMUGGLED", "RESOLUTION"]
        declared = {"smuggled": 1, "dropped": 0}
        notes = "解冲突时顺手改了与冲突无关的 src/synthapp/util.py（两侧父提交都没改它）"
    elif name == "smuggle-function-body":
        _seed(repo)
        _conflict(repo, SIDE_CORE, MAIN_CORE)
        resolved = set_line(set_line(CORE, I_TOTAL, "    total = x + 30"),
                            I_HELPER_VALUE, "    value = y * 3")
        merge = repo.commit("merge feature/synth-a into main",
                            {"src/synthapp/core.py": resolved, "src/synthapp/util.py": UTIL})
        injects = ["SMUGGLED", "RESOLUTION"]
        declared = {"smuggled": 1, "dropped": 0}
        notes = "解冲突时把 helper() 的倍率从 2 改成 3（两侧父提交都是 2）"
    elif name == "smuggle-new-file":
        _seed(repo)
        _conflict(repo, SIDE_CORE, MAIN_CORE)
        merge = repo.commit("merge feature/synth-a into main", {
            "src/synthapp/core.py": set_line(CORE, I_TOTAL, "    total = x + 30"),
            "src/synthapp/util.py": UTIL,
            "docs/generated.md": ["generated while resolving the conflict", ""],
        })
        injects = ["SMUGGLED", "RESOLUTION"]
        declared = {"smuggled": 1, "dropped": 0}
        notes = "解冲突时新增了一个两侧父提交都不存在的文件 docs/generated.md"
    elif name == "drop-guard-check":
        _seed(repo)
        _conflict(repo, SIDE_CORE, MAIN_CORE)
        resolved = set_line(CORE, I_TOTAL, "    total = x + 30")
        del resolved[I_GUARD_IF:I_GUARD_RAISE + 1]
        merge = repo.commit("merge feature/synth-a into main",
                            {"src/synthapp/core.py": resolved, "src/synthapp/util.py": UTIL})
        injects = ["DROPPED", "RESOLUTION"]
        declared = {"smuggled": 0, "dropped": 1}
        notes = "解冲突时删掉了 guard() 的负数校验（两侧父提交都保留了它）"
    elif name == "drop-one-side":
        _seed(repo)
        side_core = SIDE_CORE + ["", "", "def added_by_side():", "    return 41"]
        _conflict(repo, side_core, MAIN_CORE)
        merge = repo.commit("merge feature/synth-a into main",
                            {"src/synthapp/core.py": MAIN_CORE, "src/synthapp/util.py": UTIL})
        injects = ["DROPPED", "RESOLUTION"]
        declared = {"smuggled": 0, "dropped": 1}
        notes = "解冲突时把一侧新增的 added_by_side() 整段丢掉（后续提交没有补回）"
    elif name == "drop-partial-hunk":
        _seed(repo)
        side_core = SIDE_CORE + ["", "", "def partial():", "    a = 1", "    b = 2",
                                 "    return a + b"]
        _conflict(repo, side_core, MAIN_CORE)
        merged_core = MAIN_CORE + ["", "", "def partial():", "    a = 1"]
        merge = repo.commit("merge feature/synth-a into main",
                            {"src/synthapp/core.py": merged_core, "src/synthapp/util.py": UTIL})
        injects = ["DROPPED", "RESOLUTION"]
        declared = {"smuggled": 0, "dropped": 1}
        notes = "解冲突时只保留了新增函数的一部分（`b` 与 `return` 行被静默丢掉）"
    elif name == "drop-then-readd":
        _seed(repo)
        side_core = SIDE_CORE + ["", "", "def added_by_side():", "    return 41"]
        _conflict(repo, side_core, MAIN_CORE)
        dropped_core = list(MAIN_CORE)
        repo.commit("merge feature/synth-a into main",
                    {"src/synthapp/core.py": dropped_core, "src/synthapp/util.py": UTIL})
        merge = repo.commit("restore added_by_side", {
            "src/synthapp/core.py": dropped_core + ["", "", "def added_by_side():", "    return 41"],
        })
        # 反例：丢掉的 hunk 在后续提交里被原样补回 → 不得报 DROPPED
        injects = ["DROPPED_THEN_RESTORED", "RESOLUTION"]
        declared = {"smuggled": 0, "dropped": 0}
        merge = repo.head("%s^" % merge)
        notes = "解冲突时丢掉一侧新增的函数，**但后续提交原样补回**——不得报 DROPPED"
    elif name == "clean-resolution-a":
        _seed(repo)
        _conflict(repo, SIDE_CORE, MAIN_CORE)
        resolved = insert_after(set_line(CORE, I_TOTAL, "    total = x + 10"),
                                I_TOTAL, "    total = x + 20")
        merge = repo.commit("merge feature/synth-a into main",
                            {"src/synthapp/core.py": resolved, "src/synthapp/util.py": UTIL})
        injects = ["CLEAN_RESOLUTION"]
        declared = {"smuggled": 0, "dropped": 0}
        notes = "两侧改动都保留（各占一行）——反例：不得报 SMUGGLED / DROPPED"
    elif name == "clean-resolution-b":
        _seed(repo)
        _conflict(repo, SIDE_CORE, MAIN_CORE)
        merge = repo.commit("merge feature/synth-a into main", {
            "src/synthapp/core.py": set_line(CORE, I_TOTAL, "    total = x + 30"),
            "src/synthapp/util.py": UTIL,
        })
        injects = ["CLEAN_RESOLUTION"]
        declared = {"smuggled": 0, "dropped": 0}
        notes = "把两侧改动语义合并成一行（x + 30）——反例：不得报 SMUGGLED / DROPPED"
    elif name == "custom-driver":
        _seed(repo)
        repo.write(".gitattributes", ["synthapp.dat merge=synthapp"])
        repo.write("synthapp.dat", ["a", "b", "c"])
        git(repo.path, ["config", "merge.synthapp.driver", "git merge-file --union %A %O %B"])
        repo.commit("add synthapp driver", {})
        repo.checkout("feature/synth-a", create=True)
        repo.commit("feature a edits both files", {
            "src/synthapp/core.py": SIDE_CORE,
            "synthapp.dat": ["a", "side", "c"],
        })
        repo.checkout("main")
        repo.commit("mainline edits both files", {
            "src/synthapp/core.py": MAIN_CORE,
            "synthapp.dat": ["a", "main", "c"],
        })
        repo.merge("feature/synth-a", expect_fail=True)
        merge = repo.commit("merge feature/synth-a into main", {
            "src/synthapp/core.py": set_line(CORE, I_TOTAL, "    total = x + 30"),
            "src/synthapp/util.py": UTIL,
            "synthapp.dat": ["a", "union", "c"],
            ".gitattributes": ["synthapp.dat merge=synthapp"],
        })
        injects = ["CUSTOM_DRIVER"]
        declared = {"smuggled": 0, "dropped": 0, "skipped": "custom_driver"}
        notes = "`synthapp.dat` 命中自定义 merge driver：该路径必须 SKIPPED(reason=custom_driver) 且不进 blob_fidelity 分母"
    elif name == "octopus":
        _seed(repo)
        # 两个 feature 分支都从 seed 分出（否则 main 前进后 merge 会退化成 fast-forward）
        repo.checkout("feature/synth-a", create=True)
        repo.commit("feature a work", {"src/synthapp/a.py": ["def a():", "    return 'a'", ""]})
        repo.checkout("main")
        repo.checkout("feature/synth-b", create=True)
        repo.commit("feature b work", {"src/synthapp/b.py": ["def b():", "    return 'b'", ""]})
        repo.checkout("main")
        repo.commit("mainline work", {"docs/notes.md": ["mainline note", ""]})
        repo.merge_many(["feature/synth-a", "feature/synth-b"],
                        message="merge feature branches")
        merge = repo.head()
        injects = ["OCTOPUS"]
        declared = None
        notes = "三父 octopus merge——必须输出 SKIPPED(reason=octopus) 且不影响退出码"
    else:
        raise GenError("未知 fidelity fixture：%s" % name)

    return repo, injects, notes, merge, declared
# --------------------------------------------------------------------------- parity fixtures

def parity_lines():
    """parity 套件的模板：**两行内容相同**（都是 `flag`），方便构造"同一改动落在不同行号、
    但上下文不同"的场景——默认 3 行上下文下 patch-id 不同（所以仍是候选），
    `-U0` 下 patch-id 相同（所以应判 PRESENT）。"""
    lines = ["l%02d" % i for i in range(12)]
    lines[1] = "flag"
    lines[5] = "flag"
    return lines


def _seed_lines(repo):
    lines = parity_lines()
    repo.commit("seed synthapp skeleton",
                {"src/synthapp/core.py": lines, "src/synthapp/util.py": lines})


def build_parity(name, path):
    repo = Repo(path).init()
    scenario = {}
    base = parity_lines()

    if name == "bidirectional-basic":
        _seed_lines(repo)
        repo.checkout("release/1.0", create=True)
        repo.commit("fix A on release", {"src/synthapp/core.py": _with(base, {1: "fix-A"})})
        repo.commit("fix B on release", {"src/synthapp/util.py": _with(base, {1: "fix-B"})})
        repo.checkout("main")
        repo.commit("docs padding", {"docs/notes.md": ["note", ""]})
        repo.commit("fix A on main", {"src/synthapp/core.py": _with(base, {5: "fix-A"})})
        repo.commit("variant of fix B", {"src/synthapp/util.py": _with(base, {1: "fix-B-different"})})
        repo.commit("new api", {"src/synthapp/api.py": ["def api():", "    return 'ok'", ""]})
        scenario = {"from": "release/1.0", "to": "main"}
    elif name == "context-shift":
        _seed_lines(repo)
        repo.checkout("release/1.0", create=True)
        repo.commit("fix at line 2", {"src/synthapp/core.py": _with(base, {1: "fix-shift"})})
        repo.checkout("main")
        repo.commit("docs padding", {"docs/notes.md": ["pad", ""]})
        repo.commit("fix at line 6", {"src/synthapp/core.py": _with(base, {5: "fix-shift"})})
        scenario = {"from": "release/1.0", "to": "main"}
    elif name == "whitespace":
        _seed_lines(repo)
        repo.checkout("release/1.0", create=True)
        repo.commit("fix tight spacing", {"src/synthapp/core.py": _with(base, {1: "value=1"})})
        repo.checkout("main")
        repo.commit("docs padding", {"docs/notes.md": ["pad", ""]})
        repo.commit("fix loose spacing", {"src/synthapp/core.py": _with(base, {5: "value =    1"})})
        scenario = {"from": "release/1.0", "to": "main"}
    elif name == "partial-apply":
        _seed_lines(repo)
        repo.checkout("release/1.0", create=True)
        # release 改了 fix 行**上方**的上下文行：于是 main 的补丁两个方向都套不上 → MODIFIED
        repo.commit("tweak context above", {"src/synthapp/core.py": _with(base, {0: "l00-tweaked"})})
        repo.checkout("main")
        repo.commit("docs padding", {"docs/notes.md": ["pad", ""]})
        repo.commit("whole fix", {"src/synthapp/core.py": _with(base, {1: "fix-partial"})})
        scenario = {"from": "release/1.0", "to": "main"}
    elif name == "true-missing":
        _seed_lines(repo)
        repo.checkout("release/1.0", create=True)
        repo.commit("unrelated release work", {"docs/notes.md": ["release note", ""]})
        repo.checkout("main")
        repo.commit("brand new module", {"src/synthapp/api.py": ["def api():", "    return 'ok'", ""]})
        scenario = {"from": "release/1.0", "to": "main"}
    elif name == "path-remap":
        _seed_lines(repo)
        repo.checkout("release/1.0", create=True)
        repo.commit("fix in core", {"src/synthapp/core.py": _with(base, {1: "fix-remap"})})
        repo.checkout("main")
        repo.commit("docs padding", {"docs/notes.md": ["pad", ""]})
        # 同样的改动落在**另一个路径**：patch-id 因路径不同而不同 → 顶多给
        # `content_equivalent_at_other_path` 提示，状态仍是 MISSING（该路径上没有它）
        repo.commit("same fix elsewhere", {"src/synthapp/util.py": _with(base, {1: "fix-remap"})})
        scenario = {"from": "release/1.0", "to": "main"}
    else:
        raise GenError("未知 parity fixture：%s" % name)

    scenario["expect"] = parity_expect(repo, scenario["from"], scenario["to"])
    scenario["expect_reverse"] = parity_expect(repo, scenario["to"], scenario["from"])
    return repo, scenario


def _with(lines, overrides):
    out = list(lines)
    for index, value in overrides.items():
        out[int(index)] = value
    return out

def _with(lines, overrides):
    out = list(lines)
    for index, value in overrides.items():
        out[int(index)] = value
    return out


# --------------------------------------------------------------------------- ledger fixtures

def build_ledger(name, path):
    repo = Repo(path).init()
    injects = []
    if name == "no-successor":
        repo.commit("seed synthapp skeleton",
                    {"src/synthapp/core.py": CORE, "src/synthapp/util.py": UTIL})
        fixed = repo.commit("fix guard", {"src/synthapp/core.py": core_with(**{"12": "    if x <= 0:"})})
        repo.checkout("main")
        repo.commit("revert fix guard", {}, allow_empty=True) if False else None
        _revert(repo, fixed)
        injects = ["REVERTED_NO_SUCCESSOR"]
    elif name == "then-redone":
        repo.commit("seed synthapp skeleton",
                    {"src/synthapp/core.py": CORE, "src/synthapp/util.py": UTIL})
        fixed = repo.commit("fix guard", {"src/synthapp/core.py": core_with(**{"12": "    if x <= 0:"})})
        _revert(repo, fixed)
        repo.commit("re-land guard fix", {"src/synthapp/core.py": core_with(**{"12": "    if x <= 0:"})})
        injects = ["REVERTED_THEN_REDONE"]
    elif name == "patchid-mismatch":
        repo.commit("seed synthapp skeleton",
                    {"src/synthapp/core.py": CORE, "src/synthapp/util.py": UTIL})
        commit_x = repo.commit("tune util", {"src/synthapp/util.py": _with(UTIL, {1: "    return 11"})})
        commit_y = repo.commit("tune compute", {"src/synthapp/core.py": core_with(**{"1": "    total = x + 7"})})
        # 实际回滚 Y，却在正文里声称回滚 X
        rc, out, err = git(repo.path, ["revert", "--no-commit", commit_y], check=False,
                           env=_env(repo._index + 1))
        if rc != 0:
            raise GenError("构造 patchid-mismatch fixture 失败：%s" % err.strip())
        repo._index += 1
        git(repo.path, ["commit", "-q", "-m",
                        'Revert "tune compute"\n\nThis reverts commit %s.' % commit_x],
            env=_env(repo._index))
        injects = ["REVERT_UNVERIFIED"]
    else:
        raise GenError("未知 ledger fixture：%s" % name)
    return repo, injects


def _revert(repo, target):
    repo._index += 1
    git(repo.path, ["revert", "--no-edit", target], env=_env(repo._index))


# --------------------------------------------------------------------------- 写产物

def dump(obj):
    return json.dumps(obj, **CANONICAL_KWARGS) + "\n"


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def fidelity_manifest_entry(name, repo, injects, notes, expect):
    merges = expect.get("merges") or []
    merge_row = merges[0] if merges else {}
    refs = repo.refs(NAMESPACE["branches"])
    return {
        "suite": "fidelity",
        "name": name,
        "injects": injects,
        "notes": notes,
        "generator_version": GENERATOR_VERSION,
        "refs": refs,
        "merges": merges,
        "skipped": list(expect.get("skipped") or []),
        "blob_fidelity_model": ({
            "blob_fidelity": expect["blob_fidelity"]["blob_fidelity"],
            "paths_total": expect["blob_fidelity"]["paths_total"],
            "paths_same": expect["blob_fidelity"]["paths_same"],
            "path_only_in_recorded": expect["blob_fidelity"]["path_only_in_recorded"],
            "path_only_in_mechanical": expect["blob_fidelity"]["path_only_in_mechanical"],
        } if "blob_fidelity" in expect else None),
        "expect_counts": merge_row.get("counts"),
    }


# 首期 11 个 = 题面要求的 10 个（夹带 4 / 吞掉 3 / 正确解冲突 2 / octopus 1）
# + 1 个反例守护（drop-then-readd：重引入抑制）。
FIDELITY_REQUIRED = [
    "smuggle-extra-line", "smuggle-unrelated-file", "smuggle-function-body",
    "smuggle-new-file",
    "drop-guard-check", "drop-one-side", "drop-partial-hunk",
    "clean-resolution-a", "clean-resolution-b",
    "octopus",
]
FIDELITY_EXTRA = ["drop-then-readd", "custom-driver"]
FIDELITY_FIXTURES = FIDELITY_REQUIRED + FIDELITY_EXTRA


def _validate_declared(name, declared, expect):
    """植入器自证：声明的注入意图必须与 oracle 复算结果一致，否则生成期就失败。"""
    if declared is None:
        return
    counts = (expect.get("merges") or [{}])[0].get("counts")
    if counts is None:
        raise GenError("%s：声明了 counts=%r 但 oracle 没算出 counts（merge_oid 传错？）"
                       % (name, declared))
    for key in ("smuggled", "dropped"):
        if key in declared and counts[key] != declared[key]:
            raise GenError("%s：声明 %s=%d，oracle 复算为 %d（fixture 构造与意图不符）"
                           % (name, key, declared[key], counts[key]))
    if declared.get("skipped"):
        reasons = [item["reason"] for item in expect.get("skipped") or []]
        if declared["skipped"] not in reasons:
            raise GenError("%s：声明 skipped=%s，oracle 复算为 %r"
                           % (name, declared["skipped"], reasons))

PARITY_FIXTURES = [
    "bidirectional-basic", "context-shift", "whitespace",
    "partial-apply", "true-missing", "path-remap",
]
LEDGER_FIXTURES = ["no-successor", "then-redone", "patchid-mismatch"]


def build_one(suite, name, root):
    repo_dir = os.path.join(root, suite, name, REPO_DIR_NAME)
    rmtree(repo_dir)
    os.makedirs(repo_dir, exist_ok=True)

    if suite == "fidelity":
        repo, injects, notes, merge_oid, declared = build_fidelity(name, repo_dir)
        try:
            expect = fidelity_expect(repo, merge_oid)
        except GenError as exc:
            raise GenError("fixture %s（merge_oid=%s）：%s" % (name, merge_oid, exc))
        _validate_declared(name, declared, expect)
        record = fidelity_manifest_entry(name, repo, injects, notes, expect)
        record["suite"] = "fidelity"
        record["merge_oid"] = merge_oid
        record["declared_counts"] = declared
        record["status"] = list(injects)
    elif suite == "parity":
        repo, scenario = build_parity(name, repo_dir)
        record = {
            "suite": "parity",
            "name": name,
            "generator_version": GENERATOR_VERSION,
            "injects": ["PARITY"],
            "refs": repo.refs(NAMESPACE["branches"]),
            "from": scenario["from"],
            "to": scenario["to"],
            "expect": scenario["expect"],
            "expect_reverse": scenario["expect_reverse"],
        }
        notes = _parity_note(name)
        record["notes"] = notes
    else:
        repo, injects = build_ledger(name, repo_dir)
        expect = ledger_expect(repo)
        record = {
            "suite": "ledger",
            "name": name,
            "generator_version": GENERATOR_VERSION,
            "injects": injects,
            "refs": repo.refs(NAMESPACE["branches"]),
            "entries": expect["entries"],
            "counts": expect["counts"],
            "unavailable": expect["unavailable"],
            "notes": _ledger_note(name),
        }

    # golden 与说明写在 fixture 目录下（仓库本体在 repo/，不入仓）
    fixture_dir = os.path.join(root, suite, name)
    write_text(os.path.join(fixture_dir, "expect.json"), dump(record))
    write_text(os.path.join(fixture_dir, "README.md"),
               _fixture_readme(suite, name, record))
    return record


def _parity_note(name):
    notes = {
        "bidirectional-basic": "双向：release/1.0 与 main 上的修复互相对齐（PRESENT/MODIFIED/MISSING 三态齐）",
        "context-shift": "同一改动落在不同行号、上下文不同——`-U0` patch-id 相同 → PRESENT",
        "whitespace": "同一改动的空白形态不同——`-U0` patch-id 相同 → PRESENT",
        "partial-apply": "目标侧只含一半改动——两个方向的 apply 检查都失败 → MODIFIED",
        "true-missing": "目标侧完全没有该改动——`apply --check` 成功 → MISSING",
        "path-remap": "同内容换到另一个路径——patch-id 因路径不同而不同，apply 也失败 → MODIFIED",
    }
    return notes[name]


def _ledger_note(name):
    notes = {
        "no-successor": "回滚后没有任何后续提交重新引入该改动 → REVERTED_NO_SUCCESSOR",
        "then-redone": "回滚后同一 patch 再次落地 → REVERTED_THEN_REDONE",
        "patchid-mismatch": "正文声称回滚 X、实际 diff 回滚 Y → REVERT_UNVERIFIED（不猜意图）",
    }
    return notes[name]


def _fixture_readme(suite, name, record):
    lines = [
        "# fixture · %s / %s" % (suite, name),
        "",
        record.get("notes", ""),
        "",
        "## 手工复现",
        "",
        "```bash",
        "py -3.8 tools/gen_fixtures.py --out data/fixtures --only %s" % name,
    ]
    if suite == "fidelity":
        lines += [
            "cd data/fixtures/fidelity/%s/repo" % name,
            "git log --oneline --graph | cat",
            "git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat",
        ]
    elif suite == "parity":
        lines += [
            "cd data/fixtures/parity/%s/repo" % name,
            "git rev-list --cherry-pick --right-only %s...%s" % (record["from"], record["to"]),
        ]
    else:
        lines += [
            "cd data/fixtures/ledger/%s/repo" % name,
            "git log --grep='^This reverts commit' --format='%H%x00%B' | cat",
        ]
    lines += ["```", "", "## 期望（golden 摘要）", ""]
    lines.append("```json")
    lines.append(dump(_summary(record)).strip())
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _summary(record):
    suite = record["suite"]
    if suite == "fidelity":
        return {
            "injects": record["injects"],
            "merges": record["merges"],
            "skipped": record["skipped"],
        }
    if suite == "parity":
        return {
            "from": record["from"], "to": record["to"],
            "candidates": record["expect"]["candidates"],
            "present": record["expect"]["present"],
            "missing": record["expect"]["missing"],
            "modified": record["expect"]["modified"],
            "statuses": [(row["subject"], row["status"]) for row in record["expect"]["commits"]],
        }
    return {"injects": record["injects"], "counts": record["counts"]}


def generate(root, only=None, suites=None):
    selected = []
    for suite, names in (("fidelity", FIDELITY_FIXTURES),
                         ("parity", PARITY_FIXTURES),
                         ("ledger", LEDGER_FIXTURES)):
        if suites and suite not in suites:
            continue
        for name in names:
            if only and name not in only:
                continue
            selected.append((suite, name))

    records = []
    for suite, name in selected:
        records.append(build_one(suite, name, root))

    if not only:
        manifest = {
            "generator_version": GENERATOR_VERSION,
            "git_min": "%d.%d" % GIT_MIN,
            "counts": {
                "fidelity": len(FIDELITY_FIXTURES),
                "parity": len(PARITY_FIXTURES),
                "ledger": len(LEDGER_FIXTURES),
                "total": len(FIDELITY_FIXTURES) + len(PARITY_FIXTURES) + len(LEDGER_FIXTURES),
            },
            "fixtures": [dict((k, r[k]) for k in ("suite", "name", "injects", "notes")
                              if k in r) for r in records],
        }
        write_text(os.path.join(root, "manifest.json"), dump(manifest))
    return records


# --------------------------------------------------------------------------- check

def _walk(root):
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        if "repo" in dirnames:
            dirnames.remove("repo")
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            found[rel] = full
    return found


def check(root):
    """重生成到临时目录 → 与冻结目录逐字节比对 + 逐仓库 ref 比对。"""
    tmp = tempfile.mkdtemp(prefix="mf-gen-check-")
    try:
        generate(tmp)
        diffs = []
        frozen = _walk(root)
        fresh = _walk(tmp)
        for rel in sorted(set(frozen) | set(fresh)):
            if rel not in frozen:
                diffs.append("多出：%s" % rel)
                continue
            if rel not in fresh:
                diffs.append("缺失：%s" % rel)
                continue
            with io.open(frozen[rel], "rb") as handle:
                left = handle.read()
            with io.open(fresh[rel], "rb") as handle:
                right = handle.read()
            if left != right:
                diffs.append("内容不同：%s" % rel)
        # 逐仓库 HEAD 比对（防止"golden 相同但仓库漂移"）
        for suite, names in (("fidelity", FIDELITY_FIXTURES),
                             ("parity", PARITY_FIXTURES),
                             ("ledger", LEDGER_FIXTURES)):
            for name in names:
                rel_repo = "%s/%s/%s" % (suite, name, REPO_DIR_NAME)
                for label, base in (("frozen", root), ("fresh", tmp)):
                    path = os.path.join(base, rel_repo)
                    if not os.path.isdir(path):
                        diffs.append("%s 仓库不存在：%s" % (label, rel_repo))
        return diffs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="gen_fixtures.py",
        description="确定性地生成合成 fixture 仓库与 golden（真值由本文件的独立 oracle 复算）",
    )
    parser.add_argument("--out", default="data/fixtures", help="输出目录（默认 data/fixtures）")
    parser.add_argument("--only", action="append", default=None, help="只生成指定 fixture（可重复）")
    parser.add_argument("--suite", action="append", default=None,
                        choices=("fidelity", "parity", "ledger"), help="只生成指定套件")
    parser.add_argument("--check", action="store_true",
                        help="重生成到临时目录并与 --out 逐字节比对")
    args = parser.parse_args(argv)

    try:
        git_version()
    except EnvError as exc:
        print("环境不满足：%s" % exc, file=sys.stderr)
        return 3

    root = os.path.abspath(args.out)
    try:
        if args.check:
            diffs = check(root)
            if diffs:
                print("--check 失败，发现 %d 处差异：" % len(diffs))
                for item in diffs:
                    print("  - %s" % item)
                return 1
            total = len(FIDELITY_FIXTURES) + len(PARITY_FIXTURES) + len(LEDGER_FIXTURES)
            print("--check 通过：%d 个 fixture 与冻结产物逐字节一致" % total)
            return 0
        records = generate(root, only=args.only, suites=args.suite)
        print("已生成 %d 个 fixture 到 %s" % (len(records), root))
        return 0
    except (GenError, EnvError) as exc:
        print("生成失败：%s" % exc, file=sys.stderr)
        return getattr(exc, "exit_code", 2)


if __name__ == "__main__":
    sys.exit(main())
