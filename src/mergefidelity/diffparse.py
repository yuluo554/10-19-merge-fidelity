"""unified diff / remerge-diff 解析 —— 自写，不引第三方。

输入是 `git diff` / `git log --remerge-diff` 的 stdout 文本（UTF-8 解码后）。
本模块只做**结构解析**，不做任何判定。

实测格式（git 2.54.0.windows.1，见 plan/02 §3.1）：

* `git log --merges --remerge-diff -p --no-renames --format=%H%x00%P` 的每条记录是
  一行 ``<oid>\\x00<p1> <p2>``，紧接一个空行，然后（若有 payload）是 diff。
  忠实 merge 只有头行。
* 冲突解决后的 remerge payload 里会出现 ``remerge CONFLICT (content): ...`` 行，
  位于 ``diff --git`` 与 ``index`` 之间；该行**不是 diff 内容**。
* `merge-tree` 的冲突树的文件内容含 ``<<<<<<<`` / ``=======`` / ``>>>>>>>`` 标记。
"""

from collections import namedtuple

LF = chr(10)  # 显式换行：避免源码里嵌真实换行带来的转义歧义
CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")

Hunk = namedtuple(
    "Hunk",
    [
        "path",
        "old_start",
        "old_count",
        "new_start",
        "new_count",
        "lines",
        "has_conflict_marker",
        "in_conflict_region",
        "binary",
    ],
)

RemergeEntry = namedtuple("RemergeEntry", ["commit_oid", "parents", "hunks", "conflict_notes"])

_CONFLICT_NOTE_PREFIX = "remerge CONFLICT"


def _parse_hunk_header(line):
    """解析 ``@@ -a[,b] +c[,d] @@ [funcname]``。

    返回 **0 基** ``(old_start, old_count, new_start, new_count)``（口径见
    `data/README.md` §4.5）：``count > 0`` 时 ``start = git 行号 - 1``；
    ``count == 0``（纯增/纯删的插入点）时 ``start`` 直接取 git 行号。
    """
    if not line.startswith("@@"):
        raise ValueError("不是 hunk 头：%r" % line)
    body = line[2:]
    marker = body.find("@@")
    if marker < 0:
        raise ValueError("hunk 头缺少第二个 @@：%r" % line)
    spec = body[:marker].strip()
    old_part, _, new_part = spec.partition(" ")
    if not new_part:
        raise ValueError("hunk 头缺少新侧区间：%r" % line)

    def _pair(token, sign):
        if not token.startswith(sign):
            raise ValueError("hunk 头区间缺少前缀 %s：%r" % (sign, line))
        raw = token[1:]
        start, _, count = raw.partition(",")
        start = int(start)
        count = int(count) if count else 1
        return (start - 1 if count > 0 else start), count

    old_start, old_count = _pair(old_part, "-")
    new_start, new_count = _pair(new_part.strip(), "+")
    return old_start, old_count, new_start, new_count


def _has_conflict_marker(lines):
    for line in lines:
        stripped = line[1:] if line[:1] in "+- " else line
        if stripped.startswith(CONFLICT_MARKERS):
            return True
    return False


def parse_unified_diff(text):
    """解析一段 unified diff，返回 ``Hunk`` 列表。

    * 只认 ``diff --git`` / ``@@`` / ``+`` / ``-`` / `` `` / ``\\ No newline ...``。
    * ``Binary files ... differ`` → 一个 ``binary=True`` 的 Hunk（不算增删行）。
    * 非 diff 的散行（例如 ``remerge CONFLICT ...``）跳过，但会标记后续 hunk 处于冲突区。
    """
    hunks = []
    path = None
    old_range = None
    new_range = None
    buf = []
    in_conflict_region = False
    pending_conflict_region = False

    def flush():
        if path is None or old_range is None or new_range is None:
            return
        hunks.append(
            Hunk(
                path=path,
                old_start=old_range[0],
                old_count=old_range[1],
                new_start=new_range[0],
                new_count=new_range[1],
                lines=tuple(buf),
                has_conflict_marker=_has_conflict_marker(buf),
                in_conflict_region=in_conflict_region,
                binary=False,
            )
        )

    for raw in text.split("\n"):
        line = raw
        if line.startswith("diff --git "):
            flush()
            buf = []
            old_range = new_range = None
            in_conflict_region = False
            pending_conflict_region = False
            path = _path_from_diff_git(line)
            continue
        if path is None:
            continue
        if line.startswith(_CONFLICT_NOTE_PREFIX):
            # `remerge CONFLICT ...` 出现在 hunk 头之前：标记本文件的 hunk 位于冲突区
            pending_conflict_region = True
            continue
        if line.startswith("@@"):
            flush()
            buf = []
            old_range = new_range = None
            in_conflict_region = pending_conflict_region
            try:
                parsed = _parse_hunk_header(line)
            except ValueError:
                continue
            old_range = parsed[:2]
            new_range = parsed[2:]
            continue
        if line.startswith("Binary files ") and line.endswith(" differ"):
            flush()
            buf = []
            old_range = (0, 1)
            new_range = (0, 1)
            hunks.append(
                Hunk(
                    path=path,
                    old_start=0,
                    old_count=1,
                    new_start=0,
                    new_count=1,
                    lines=(),
                    has_conflict_marker=False,
                    in_conflict_region=in_conflict_region,
                    binary=True,
                )
            )
            old_range = new_range = None
            continue
        if line[:1] in ("+", "-", " ") and old_range is not None:
            buf.append(line)
            continue
        if line.startswith("\\ No newline at end of file"):
            continue
        if line.startswith(("index ", "--- ", "+++ ", "old mode", "new mode",
                            "similarity index", "rename ", "copy ", "deleted file mode",
                            "new file mode")):
            continue
        # 其余散行（例如 merge 冲突提示）不参与内容解析
    flush()
    return hunks


def _path_from_diff_git(line):
    # "diff --git a/<path> b/<path>"：路径可能含空格，按 " b/" 右侧切
    rest = line[len("diff --git "):]
    idx = rest.find(" b/")
    if idx < 0:
        return rest
    left = rest[:idx]
    right = rest[idx + 3:]
    if left.startswith("a/"):
        left = left[2:]
    if left == right:
        return left
    return left


def parse_remerge_log(text):
    """解析 ``--format=%H%x00%P`` + ``--remerge-diff`` 的整段输出。

    返回 ``RemergeEntry`` 列表，按输出顺序。忠实 merge 的 ``hunks`` 为空元组。
    """
    entries = []
    oid = None
    parents = ()
    body = []
    notes = []

    def flush():
        if oid is None:
            return
        entries.append(
            RemergeEntry(
                commit_oid=oid,
                parents=tuple(parents),
                hunks=tuple(parse_unified_diff("\n".join(body))),
                conflict_notes=tuple(notes),
            )
        )

    for line in text.split("\n"):
        if "\x00" in line:
            flush()
            head, _, rest = line.partition("\x00")
            oid = head.strip()
            parents = tuple(rest.split())
            body = []
            notes = []
            continue
        if oid is None:
            continue
        if line.startswith(_CONFLICT_NOTE_PREFIX):
            notes.append(line)
        body.append(line)
    flush()
    return entries


def hunk_patch_text(path, lines, reverse=False):
    """把一个 hunk 的内容拼成可喂给 `git patch-id` 的最小 diff 文本。

    `git patch-id` 忽略行号与 hunk 头后缀，因此合成的 `@@ -1 +1 @@` 不影响结果；
    这样"某个被丢掉的 hunk 是否在后续提交里被重新引入"可以用同一个 patch-id 口径比较。
    ``reverse=True`` 用于把"删除"翻转成"新增"（DROPPED 的重引入判定按新增方向比）。
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
    return LF.join(header + body) + LF
