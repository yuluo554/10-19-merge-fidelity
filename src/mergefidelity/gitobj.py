"""git 对象访问层 —— 全项目唯一的 git 子进程出口。

设计要点（见 plan/02 §三）：

* **只读**：不调用任何会改引用/改工作树的命令（`commit`/`checkout`/`reset`/`filter-*`…）。
  唯一例外是 `parity` 的临时 worktree（`git worktree add`），它在系统临时目录里，
  且由 `temporary_worktree()` 保证成功/异常两条路径都清理。
* **不写对象库**：`merge-tree --write-tree` 会向对象库写 tree/blob（实测），
  因此 `merge_tree()` 用 `TempObjectDir` 把写入重定向到临时目录，仓库 `.git/objects`
  保持零变化。
* **显式编码**：一律捕获字节后按 UTF-8 解码（`errors="replace"`），不使用
  `text=True`（后者走 locale，CI 会 UnicodeDecodeError）。
"""

import os
import re
import shutil
import subprocess
import tempfile
from collections import namedtuple

from .errors import GitEnvError

GIT_EXECUTABLE = os.environ.get("MERGEFIDELITY_GIT", "git")

# 需要 `--remerge-diff`（2.36）与 `merge-tree --write-tree`（2.38）
GIT_MIN_FIDELITY = (2, 38)
GIT_MIN_LEDGER = (2, 16)

GIT_TIMEOUT_SECONDS = 60

# 固定注入的 -c 覆盖项（会登记进报告头的 config_overrides）。
#
# 为什么要钉死这几项：**用户/仓库级 git 配置会改变判定结果**——实测
# `merge.conflictStyle=zdiff3` 会让同一 merge 的机械树 OID 变化
# （默认 51683564511b… → zdiff3 0f5a5d03ff9a…），而机械树是 finding 的判定输入。
# 因此"同一仓库同一范围在任何机器上结果一致"要求把这些开关固定下来并写进报告头。
CONFIG_OVERRIDES = (
    "core.quotepath=false",      # 路径按原样输出（不用八进制转义）
    "core.pager=cat",            # 不依赖用户分页器
    "core.autocrlf=false",       # 不做事性换行转换
    "core.eol=lf",
    "diff.algorithm=myers",      # hunk 边界由算法决定 → 钉死
    "diff.noprefix=false",       # 解析器依赖 a/ b/ 前缀
    "merge.conflictStyle=merge",  # 冲突标记形态决定 RESOLUTION 判定与机械树 OID
)

_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")

GitResult = namedtuple("GitResult", ["returncode", "stdout", "stderr", "argv"])

MechanicalTree = namedtuple("MechanicalTree", ["tree_oid", "has_conflict", "entries", "raw"])


def _decode(raw):
    return raw.decode("utf-8", errors="replace")


def run_git(repo, args, *, input_text=None, timeout=GIT_TIMEOUT_SECONDS, env=None, check=True):
    """运行一条只读 git 命令，返回 ``GitResult``（stdout/stderr 已按 UTF-8 解码）。

    ``check=True`` 时非零退出码抛 ``GitEnvError``；调用方需要自己解释退出码时
    （例如 `merge-tree` 冲突返回 1、`apply --check` 失败返回 1）传 ``check=False``。
    """
    argv = [GIT_EXECUTABLE, "--no-pager"]
    for item in CONFIG_OVERRIDES:
        argv += ["-c", item]
    argv += ["-C", os.fspath(repo)]
    argv += [str(a) for a in args]

    run_env = None
    if env:
        run_env = dict(os.environ)
        run_env.update(env)

    stdin_bytes = None
    if input_text is not None:
        stdin_bytes = input_text.encode("utf-8")

    try:
        proc = subprocess.run(
            argv,
            input=stdin_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=run_env,
        )
    except FileNotFoundError:
        raise GitEnvError("git executable not found: %s（可设 MERGEFIDELITY_GIT 指定路径）"
                          % GIT_EXECUTABLE)
    except subprocess.TimeoutExpired:
        raise GitEnvError("git timeout after %ss: %s" % (timeout, " ".join(argv[3:])))

    result = GitResult(proc.returncode, _decode(proc.stdout), _decode(proc.stderr), argv)
    if check and proc.returncode != 0:
        raise GitEnvError(
            "git exited %d: %s\n%s" % (proc.returncode, " ".join(argv[3:]), result.stderr.strip())
        )
    return result


def parse_version(text):
    """从 ``git --version`` 输出解析 ``(major, minor, patch)``。"""
    match = _VERSION_RE.search(text or "")
    if not match:
        raise GitEnvError("无法解析 git 版本：%r" % (text,))
    return (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))


def version(repo="."):
    """返回 ``(version_tuple, version_string)``。"""
    result = run_git(repo, ["--version"])
    text = result.stdout.strip()
    return parse_version(text), text


def require_version(repo, minimum):
    """版本低于门槛抛 ``GitEnvError``（→ 退出码 3）。返回版本字符串。"""
    found, text = version(repo)
    if found < tuple(minimum):
        raise GitEnvError(
            "git %d.%d 或更高版本必需，当前为 %s（不降级为近似结果）"
            % (minimum[0], minimum[1], text)
        )
    return text


def is_git_repo(path):
    """判断路径在 git 仓库内（工作树或裸库）。"""
    if not os.path.isdir(path):
        return False
    try:
        result = run_git(path, ["rev-parse", "--git-dir"], check=False)
    except GitEnvError:
        return False
    return result.returncode == 0


def require_git_repo(path):
    if not os.path.exists(path):
        raise GitEnvError("路径不存在：%s" % path)
    if not os.path.isdir(path):
        raise GitEnvError("不是目录：%s" % path)
    if not is_git_repo(path):
        raise GitEnvError("不是 git 仓库：%s" % path)
    return os.path.abspath(path)


def rev_parse(repo, rev):
    return run_git(repo, ["rev-parse", "--verify", str(rev)]).stdout.strip()


def object_format(repo):
    result = run_git(repo, ["rev-parse", "--show-object-format"])
    return result.stdout.strip() or "sha1"


def git_dir(repo):
    return run_git(repo, ["rev-parse", "--absolute-git-dir"]).stdout.strip()


def rev_list(repo, args):
    """返回 OID 列表（`rev-list` 的每个非空行）。"""
    text = run_git(repo, ["rev-list"] + list(args)).stdout
    return [line.strip() for line in text.splitlines() if line.strip()]


def commit_meta(repo, rev):
    """返回 ``(oid, parents, commit_time, subject)``。"""
    text = run_git(
        repo, ["log", "-1", "--format=%H%x00%P%x00%ct%x00%s", str(rev)]
    ).stdout.strip("\n")
    fields = text.split("\x00")
    while len(fields) < 4:
        fields.append("")
    oid, parents, ct, subject = fields[:4]
    return oid, tuple(parents.split()), int(ct), subject


def ls_tree(repo, treeish):
    """返回 ``{path: (mode, oid)}``（递归展开，含子目录内容）。

    使用 ``-z``：路径按原样输出，不受 ``core.quotePath`` 影响。
    """
    out = run_git(repo, ["ls-tree", "-r", "-z", str(treeish)]).stdout
    entries = {}
    for chunk in out.split("\x00"):
        if not chunk:
            continue
        meta, _, path = chunk.partition("\t")
        parts = meta.split()
        if len(parts) < 3:
            raise GitEnvError("无法解析 ls-tree 条目：%r" % chunk)
        entries[path] = (parts[0], parts[2])
    return entries


def blob_map(repo, treeish, env=None):
    """``{path: blob_oid}``（非 blob 的条目——如 gitlink——按 type 过滤掉）。"""
    out = run_git(repo, ["ls-tree", "-r", "-z", "--full-tree", str(treeish)], env=env).stdout
    entries = {}
    for chunk in out.split("\x00"):
        if not chunk:
            continue
        meta, _, path = chunk.partition("\t")
        parts = meta.split()
        if len(parts) < 3:
            raise GitEnvError("无法解析 ls-tree 条目：%r" % chunk)
        mode, obj_type, oid = parts[0], parts[1], parts[2]
        if obj_type != "blob":
            continue
        entries[path] = oid
    return entries


def attributes_oid(repo, treeish):
    """返回 ``.gitattributes`` 的 blob OID；不存在时 ``None``。"""
    for candidate in (".gitattributes",):
        result = run_git(
            repo, ["rev-parse", "--verify", "--quiet", "%s:%s" % (treeish, candidate)],
            check=False,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            if value:
                return value
    return None


class TempObjectDir(object):
    """把 ``merge-tree`` 的对象写入重定向到临时目录。

    仓库对象库通过 ``GIT_ALTERNATE_OBJECT_DIRECTORIES`` 仍可读，因此仓库
    ``.git/objects`` 保持零写入（测试断言前后文件数不变）。

    实测要点（2026-10-18，git 2.54.0.windows.1）：**目标对象目录必须预先存在**，
    否则 git 报 ``fatal: not a git repository``——它把无法校验的对象目录当成
    "这不是一个仓库"。因此 ``__enter__`` 里先 ``makedirs``。
    """

    def __init__(self, repo):
        self.repo = repo
        self.path = None

    def __enter__(self):
        self.path = tempfile.mkdtemp(prefix="mf-obj-")
        os.makedirs(os.path.join(self.path, "objects"), exist_ok=True)
        return self

    @property
    def env(self):
        if not self.path:
            raise RuntimeError("TempObjectDir 尚未进入上下文")
        objects = os.path.join(git_dir(self.repo), "objects")
        return {
            "GIT_OBJECT_DIRECTORY": os.path.join(self.path, "objects"),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": objects,
        }

    def __exit__(self, exc_type, exc, tb):
        if self.path and os.path.isdir(self.path):
            shutil.rmtree(self.path, ignore_errors=True)
        self.path = None
        return False


class MechanicalMerge(object):
    """机械合并复算的上下文管理器：**对象环境在上下文内一直存活**。

    为什么必须是上下文而不是一个函数：`merge-tree --write-tree` 写出的 tree/blob 落在
    `TempObjectDir` 里，上下文退出即删除；调用方要在同一对象环境里继续
    `ls-tree` / `diff` 机械树，所以"复算"与"读机械树"必须共享同一个 env。

    属性：``tree_oid`` / ``has_conflict`` / ``entries`` / ``env``（传给其它 git 调用）。
    """

    def __init__(self, repo, base, p1, p2, *, timeout=120):
        self.repo = repo
        self.base = base
        self.parents = (p1, p2)
        self.timeout = timeout
        self._objects = TempObjectDir(repo)
        self.tree_oid = None
        self.has_conflict = None
        self.entries = ()
        self.env = None
        self.raw = ""

    def __enter__(self):
        self._objects.__enter__()
        self.env = self._objects.env
        result = run_git(
            self.repo,
            ["merge-tree", "--write-tree", "--merge-base=%s" % self.base,
             str(self.parents[0]), str(self.parents[1])],
            check=False,
            timeout=self.timeout,
            env=self.env,
        )
        if result.returncode not in (0, 1):
            self._objects.__exit__(None, None, None)
            raise GitEnvError(
                "merge-tree 退出 %d：%s" % (result.returncode, result.stderr.strip())
            )
        lines = result.stdout.split("\n")
        tree_oid = lines[0].strip() if lines else ""
        if len(tree_oid) not in (40, 64):
            self._objects.__exit__(None, None, None)
            raise GitEnvError("merge-tree 首行不是 tree OID：%r" % result.stdout[:200])

        entries = []
        for line in lines[1:]:
            if not line.strip() or "\t" not in line:
                continue
            meta, _, path = line.partition("\t")
            parts = meta.split()
            if len(parts) >= 3 and parts[2].isdigit():
                entries.append(
                    {"mode": parts[0], "oid": parts[1], "stage": int(parts[2]), "path": path}
                )
        self.tree_oid = tree_oid
        self.has_conflict = (result.returncode == 1)
        self.entries = tuple(entries)
        self.raw = result.stdout
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._objects.__exit__(exc_type, exc, tb)

    def as_tuple(self):
        return MechanicalTree(self.tree_oid, self.has_conflict, self.entries, self.raw)


def merge_tree(repo, base, p1, p2, *, timeout=120):
    """一次性机械合并复算 → ``MechanicalTree``。

    只用于"只要 OID、不需要再读机械树"的场景；需要逐 blob / 逐 hunk 比较时用
    ``MechanicalMerge`` 上下文（临时对象目录会在本次调用结束时被删掉）。
    """
    with MechanicalMerge(repo, base, p1, p2, timeout=timeout) as merge:
        return merge.as_tuple()


def temporary_worktree(repo, rev):
    """parity 兜底判定用的临时 worktree 上下文管理器。

    路径落在系统临时目录；成功与异常两条路径都清理（remove --force → prune → rmtree）。
    报告里不得出现该绝对路径。
    """
    return _TemporaryWorktree(repo, rev)


class _TemporaryWorktree(object):
    def __init__(self, repo, rev):
        self.repo = repo
        self.rev = rev
        self.path = None

    def __enter__(self):
        self.path = tempfile.mkdtemp(prefix="mf-parity-")
        # mkdtemp 建出的目录非空检测会失败，先删掉再让 git 建
        os.rmdir(self.path)
        run_git(self.repo, ["worktree", "add", "--detach", self.path, str(self.rev)])
        return self.path

    def __exit__(self, exc_type, exc, tb):
        if self.path:
            run_git(self.repo, ["worktree", "remove", "--force", self.path], check=False)
            run_git(self.repo, ["worktree", "prune"], check=False)
            if os.path.isdir(self.path):
                shutil.rmtree(self.path, ignore_errors=True)
            self.path = None
        return False


def worktree_list(repo):
    """返回 worktree 路径列表（用于测试断言零残留）。"""
    out = run_git(repo, ["worktree", "list", "--porcelain"]).stdout
    return [line[len("worktree "):] for line in out.splitlines() if line.startswith("worktree ")]


def tree_of(repo, rev):
    return run_git(repo, ["rev-parse", "%s^{tree}" % rev]).stdout.strip()


def merge_base(repo, a, b):
    return run_git(repo, ["merge-base", str(a), str(b)]).stdout.strip()


def commit_time(repo, rev):
    return int(run_git(repo, ["log", "-1", "--format=%ct", str(rev)]).stdout.strip())


def file_at(repo, rev, path):
    """``<rev>:<path>`` 的内容；不存在返回 ``None``。"""
    result = run_git(repo, ["show", "%s:%s" % (rev, path)], check=False)
    if result.returncode != 0:
        return None
    return result.stdout


def tree_diff(repo, tree_a, tree_b, *, path=None, env=None, context=0):
    """``git diff --no-renames -U<context> <a> <b> [-- <path>]`` 的文本。"""
    args = ["diff", "--no-renames", "-U%d" % context, str(tree_a), str(tree_b)]
    if path:
        args += ["--", path]
    return run_git(repo, args, env=env).stdout


def patch_id(repo, diff_text):
    """``git patch-id --stable`` 的第一列；空 diff 返回 ``None``。"""
    result = run_git(repo, ["patch-id", "--stable"], input_text=diff_text, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.split()[0]


def commit_diff(repo, rev, *, context=0, path=None):
    """单个提交的 diff 文本（根提交走 `--root`）。``--`` 必须排在 revisions 之后。"""
    args = ["diff-tree", "-p", "-U%d" % context, "--no-renames"]
    if has_parent(repo, rev):
        args += ["%s^" % rev, str(rev)]
    else:
        args += ["--root", str(rev)]
    if path:
        args += ["--", path]
    return run_git(repo, args).stdout


def has_parent(repo, rev):
    out = run_git(repo, ["rev-list", "--parents", "-n", "1", str(rev)]).stdout.split()
    return len(out) > 1


def commits_not_reachable(repo, rev, *, all_refs=True):
    """``--all`` 中不可从 ``rev`` 到达的提交，按 ``(commit_time, oid)`` 排序。"""
    reachable = set(rev_list(repo, [str(rev)]))
    everything = rev_list(repo, ["--all"]) if all_refs else rev_list(repo, ["HEAD"])
    later = [oid for oid in everything if oid not in reachable]
    return [oid for _time, oid in sorted((commit_time(repo, oid), oid) for oid in later)]


def paths_of_commit(repo, rev):
    out = run_git(repo, ["diff-tree", "-r", "--no-commit-id", "--name-only", "-z", str(rev)]).stdout
    return sorted(p for p in out.split(chr(0)) if p)
