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

# 固定注入的 -c 覆盖项（会登记进报告头的 config_overrides）
CONFIG_OVERRIDES = ("core.quotepath=false", "core.pager=cat")

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


def blob_map(repo, treeish):
    """``{path: blob_oid}``（blob 与 gitlink/子模块按 type 过滤，只留 blob）。"""
    out = run_git(repo, ["ls-tree", "-r", "-z", "--full-tree", str(treeish)]).stdout
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


def merge_tree(repo, base, p1, p2, *, timeout=120):
    """机械合并复算 → ``MechanicalTree``。

    干净退出 0；冲突退出 1（首行仍是 tree OID，随后是 stage 1/2/3 条目）。
    其他退出码抛 ``GitEnvError``。
    """
    with TempObjectDir(repo) as tod:
        result = run_git(
            repo,
            ["merge-tree", "--write-tree", "--merge-base=%s" % base, str(p1), str(p2)],
            check=False,
            timeout=timeout,
            env=tod.env,
        )
    if result.returncode not in (0, 1):
        raise GitEnvError("merge-tree 退出 %d：%s" % (result.returncode, result.stderr.strip()))

    lines = result.stdout.split("\n")
    tree_oid = lines[0].strip() if lines else ""
    if len(tree_oid) not in (40, 64):
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
    return MechanicalTree(
        tree_oid=tree_oid,
        has_conflict=(result.returncode == 1),
        entries=tuple(entries),
        raw=result.stdout,
    )


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
