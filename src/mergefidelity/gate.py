"""`gate` —— CI 门禁 + 带过期时间的基线（模块⑤，M5）。

口径唯一权威：`data/README.md` §4.7 与 `plan/03-模块详设.md` §5。要点：

* **受限 TOML 子集**（Python 3.8 无 `tomllib`）：只支持 `[[finding]]` + 字符串值 + 注释。
  数组 / 嵌套表 / 多行字符串 / 非字符串值 → `toml_unsupported`（退出码 2，**明示行号**）。
  语法错误 / 缺 `justification` / 坏日期 → 退出码 2，且**零副作用**（不写任何产物）。
* **判定**：跑 `fidelity`（`--since` 增量；未给则全量）→ 把 finding 与基线逐 ID 对照：
  命中且 `as_of <= expires` → `baselined`（不计失败）；命中且 `as_of > expires` → `expired`
  （参与失败）；未命中 → `new`（按 `--fail-on` 过滤 kind）；基线条目无对应 finding →
  `stale`（只提示，不失败）。
* **退出码**：`new` 或 `expired` 非空 → 1；否则 0；用法/基线坏 → 2；环境 → 3。
* **ID 精确匹配**，不做前缀/模糊匹配（§4.7）；`expires` 按报告内 `as_of` 比较，
  **不读系统时钟**。
"""

import datetime
import re

from . import __version__
from . import canonical, fidelity, gitobj
from .errors import EXIT_FINDINGS, EXIT_OK, UsageError

MODULE = "gate"

DEFAULT_FAIL_ON = "any"

# 参与失败的 finding kind（基线只对"事故类"起作用）
FAIL_ON_KINDS = {
    "smuggled": ("SMUGGLED",),
    "dropped": ("DROPPED",),
    "any": ("SMUGGLED", "DROPPED"),
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 受限子集只认这三种形态；其余（数组/嵌套表/多行字符串/非字符串值）显式报不支持
_TABLE_HEADER_RE = re.compile(r"^\[\[\s*([A-Za-z_][A-Za-z0-9_-]*)\s*\]\]$")
_KEY_VALUE_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(.*)$')
_BASIC_STRING_RE = re.compile(r'^"([^"\\]*)"$')


# --------------------------------------------------------------------------- 基线解析

class BaselineError(UsageError):
    """基线文件本身有问题 → 退出码 2（用法/输入错误，不是环境）。"""


def _unsupported(line_no, detail):
    raise BaselineError("toml_unsupported：第 %d 行 %s（本构建只支持受限 TOML 子集："
                        "`[[finding]]` + 字符串值 + 注释）" % (line_no, detail))


def _parse_string(line_no, raw):
    """只接受单行基本字符串 `"..."`（不含转义）；其它形态一律 `toml_unsupported`。"""
    raw = raw.strip()
    if raw.startswith("'''") or raw.startswith('"""'):
        _unsupported(line_no, "多行字符串不受支持")
    if raw.startswith("["):
        _unsupported(line_no, "数组不受支持")
    if raw.startswith("{"):
        _unsupported(line_no, "内联表不受支持")
    match = _BASIC_STRING_RE.match(raw)
    if not match:
        if raw.startswith('"') and "\\" in raw:
            _unsupported(line_no, "带转义的字符串不受支持")
        _unsupported(line_no, "值必须是单行基本字符串（%r）" % raw)
    return match.group(1)


def _strip_comment(line):
    """去掉字符串外的尾部注释（字符串内的 `#` 是数据，不是注释）。"""
    in_string = False
    for index, char in enumerate(line):
        if char == '"':
            in_string = not in_string
        elif char == "#" and not in_string:
            return line[:index]
    return line


def parse_baseline(text):
    """解析受限 TOML 子集 → ``[{id, expires, justification, line}]``。

    只认 `[[finding]]` 段落与其中的 `id` / `expires` / `justification` 三个字符串键；
    段落之外的键值、未知键、缺键、坏日期、重复 id 一律报错（退出码 2）。
    """
    entries = []
    current = None
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw_line).strip()
        if not line or line.startswith("#"):
            continue

        header = _TABLE_HEADER_RE.match(line)
        if header:
            if header.group(1) != "finding":
                _unsupported(line_no, "只支持 `[[finding]]` 表（遇到 `[[%s]]`）"
                             % header.group(1))
            current = {"id": None, "expires": None, "justification": None, "line": line_no}
            entries.append(current)
            continue

        if line.startswith("["):
            _unsupported(line_no, "嵌套表不受支持（只支持 `[[finding]]`）")

        key_value = _KEY_VALUE_RE.match(line)
        if not key_value:
            raise BaselineError("基线语法错误：第 %d 行无法解析（%r）" % (line_no, raw_line))
        if current is None:
            raise BaselineError("基线语法错误：第 %d 行的键值不在任何 `[[finding]]` 段落内"
                                % line_no)

        key, raw_value = key_value.group(1), key_value.group(2)
        if key not in ("id", "expires", "justification"):
            _unsupported(line_no, "未知键 `%s`（只支持 id / expires / justification）" % key)
        if current[key] is not None:
            raise BaselineError("基线语法错误：第 %d 行重复设置 `%s`" % (line_no, key))
        current[key] = _parse_string(line_no, raw_value)

    _validate_entries(entries)
    return entries


def _validate_entries(entries):
    if not entries:
        raise BaselineError("基线为空：至少需要一条 `[[finding]]`（空基线等于没有门禁）")
    seen = set()
    for entry in entries:
        line_no = entry["line"]
        for key in ("id", "expires", "justification"):
            value = entry[key]
            if value is None:
                raise BaselineError("基线语法错误：第 %d 行的 `[[finding]]` 缺少 `%s`"
                                    % (line_no, key))
            if not value.strip():
                raise BaselineError("基线语法错误：第 %d 行的 `%s` 不能为空字符串"
                                    % (line_no, key))
        if not _DATE_RE.match(entry["expires"]):
            raise BaselineError("基线语法错误：第 %d 行的 `expires` 必须是 YYYY-MM-DD：%r"
                                % (line_no, entry["expires"]))
        try:
            datetime.datetime.strptime(entry["expires"], "%Y-%m-%d")
        except ValueError:
            raise BaselineError("基线语法错误：第 %d 行的 `expires` 不是合法日期：%r"
                                % (line_no, entry["expires"]))
        if entry["id"] in seen:
            raise BaselineError("基线语法错误：第 %d 行的 `id` 与前面的条目重复：%s"
                                % (line_no, entry["id"]))
        seen.add(entry["id"])


def read_baseline(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise BaselineError("无法读取基线文件：%s（%s）" % (path, exc))
    return parse_baseline(text)


# --------------------------------------------------------------------------- 分类

def classify(findings, baseline, *, as_of, fail_on=DEFAULT_FAIL_ON):
    """把 finding 与基线对照 → ``(buckets, summary)``。

    `buckets` 的键固定为 `baselined` / `expired` / `new` / `stale`，值是 finding 或
    基线条目列表；`new` 只保留 `--fail-on` 指定的 kind（其余 kind 不是门禁的管辖范围）。
    """
    wanted = FAIL_ON_KINDS[fail_on]
    by_id = dict((entry["id"], entry) for entry in baseline)
    baselined, expired, new = [], [], []
    hit_ids = set()

    for finding in findings:
        entry = by_id.get(finding["id"])
        if entry is None:
            if finding["kind"] in wanted:
                new.append(finding)
            continue
        hit_ids.add(entry["id"])
        if as_of <= entry["expires"]:
            baselined.append({"finding": finding, "expires": entry["expires"],
                              "justification": entry["justification"]})
        else:
            expired.append({"finding": finding, "expires": entry["expires"],
                            "justification": entry["justification"]})

    stale = [{"id": entry["id"], "expires": entry["expires"],
              "justification": entry["justification"]}
             for entry in baseline if entry["id"] not in hit_ids]

    return {"baselined": baselined, "expired": expired, "new": new, "stale": stale}


def _scan_kinds():
    """门禁扫的是**全部事故类** kind（`SMUGGLED` + `DROPPED`），不是只扫 `--fail-on` 那一类。

    理由：`expired` 与 `baselined` 是对"基线条目是否仍然命中"的回答，必须覆盖全部事故类；
    若只扫 `--fail-on` 那一类，另一类的基线条目会凭空变成 `stale`（假"已修复"）。
    `--fail-on` 只过滤 **`new`**（新增）是否参与失败。
    """
    return fidelity.DEFAULT_KINDS


# --------------------------------------------------------------------------- 主流程

def gate_scan(repo, baseline, *, since=None, as_of=None, fail_on=DEFAULT_FAIL_ON):
    """跑一次门禁，返回 ``(报告对象未填 digest, 退出码)``。"""
    gitobj.require_git_repo(repo)
    git_version = gitobj.require_version(repo, gitobj.GIT_MIN_FIDELITY)
    object_format = gitobj.object_format(repo)

    if fail_on not in FAIL_ON_KINDS:
        raise UsageError("--fail-on 只接受 smuggled/dropped/any：%r" % (fail_on,))
    if as_of is not None:
        fidelity.validate_as_of(as_of)

    report = fidelity.scan(repo, since=since, as_of=as_of, kinds=_scan_kinds())
    findings = fidelity.findings_of(report)
    buckets = classify(findings, baseline, as_of=report["as_of"], fail_on=fail_on)

    counts = {key: len(value) for key, value in buckets.items()}
    failing = counts["new"] + counts["expired"]

    document = {
        "tool_version": __version__,
        "git_version": git_version,
        "object_format": object_format,
        # 报告头指纹口径与 fidelity 一致：范围右端即被扫时点的 HEAD
        "gitattributes_oid": gitobj.attributes_oid(repo, fidelity.range_end(None)),
        "config_overrides": list(gitobj.CONFIG_OVERRIDES),
        "range": report["range"],
        "as_of": report["as_of"],
        "module": MODULE,
        "baseline_entries": len(baseline),
        "fail_on": fail_on,
        "counts": counts,
        "baselined": buckets["baselined"],
        "expired": buckets["expired"],
        "new": buckets["new"],
        "stale": buckets["stale"],
        "scan": report["summary"],
    }
    return document, (EXIT_FINDINGS if failing else EXIT_OK)


# --------------------------------------------------------------------------- 渲染

def render_markdown(report):
    lines = [
        "# CI 门禁（gate）",
        "",
        "- 工具版本：%s（%s / %s）" % (report["tool_version"], report["git_version"],
                                      report["object_format"]),
        "- 范围：%s · as_of：%s · fail-on：%s"
        % (report["range"], report["as_of"], report["fail_on"]),
        "- 基线 %d 条：未过期 %d / 已过期 %d / 新增 %d / 失效 %d"
        % (report["baseline_entries"], report["counts"]["baselined"],
           report["counts"]["expired"], report["counts"]["new"], report["counts"]["stale"]),
        "",
    ]
    for key, title in (("new", "新增（参与失败）"), ("expired", "过期（参与失败）"),
                       ("baselined", "基线内（不失败）"), ("stale", "失效条目（只提示）")):
        items = report[key]
        if not items:
            continue
        lines += ["## %s" % title, "",
                  "| finding id | kind | path | 说明 |", "|---|---|---|---|"]
        for item in items:
            finding = item.get("finding", item)
            lines.append("| `%s` | %s | %s | %s |" % (
                finding["id"][:12], finding.get("kind", "-"), finding.get("path", "-"),
                item.get("expires", "")))
        lines.append("")
    return "\n".join(lines)


def run(args):
    """执行 `mergefidelity gate <repo> --baseline=PATH [...]` → 退出码。"""
    # 基线先解析：语法错误必须**零副作用**（此时还没跑任何扫描、也没写任何产物）
    baseline = read_baseline(args.baseline)
    report, code = gate_scan(
        args.repo,
        baseline,
        since=getattr(args, "since", None),
        as_of=getattr(args, "as_of", None),
        fail_on=getattr(args, "fail_on", None) or DEFAULT_FAIL_ON,
    )
    if args.format == "md":
        text = render_markdown(report)
    else:
        text = canonical.dumps(canonical.with_digest(report))
    if args.out:
        canonical.write_atomic(args.out, text)
    else:
        print(text, end="" if text.endswith("\n") else "\n")
    return code
