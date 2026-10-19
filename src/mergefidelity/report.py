"""`report` —— 确定性报告 + 可复现摘要（模块④，M5）。

口径唯一权威：`data/README.md` §4.6 与 `plan/03-模块详设.md` §4。要点：

* **输入 = 前三个模块的原始结果**，在同一对象库上现跑一次（不读缓存文件）：
  `fidelity` 与 `ledger` **恒计入**；`parity` 需要两个显式引用，未给时该节为 `null`
  并在 `notes` 写 `parity_not_requested`——**不伪造空结果**（K23）。
* **报告头写死、参与 digest**：`tool_version` / `git_version` / `object_format` /
  `gitattributes_oid` / `config_overrides` / `range` / `as_of` /
  `findings_digest_algorithm:"sha256"`。**禁止**：扫描时刻、绝对路径、主机名、用户名、
  locale、Python 版本。
* **`findings`**：把三个模块的结论统一成**内容寻址 finding**（`sha1(commit_oid ‖ path ‖
  old_range ‖ new_range ‖ kind)`，口径见 §4.5），按 `(commit_time, commit_oid, path, old_range)`
  排序——ID 因此可跨机器复算、可写进基线。展开逻辑住在各自模块（`findings_of`）。
* **`--verify=PATH`**：读回报告 → 用**同一对象库**重跑模块 → 与报告**去掉 `digest` 后**逐字节
  比较（首个差异用 JSON path 表达，如 `fidelity.merges[3].hunks[1].new_range`）→ 内容一致再
  校验 `digest` 自身 → 全过则退出码 0，stdout 打 `verified: N merges, M findings`。
  **定位顺序是"先内容、后 digest"**：先查 digest 会把"哪一处被改了"的答案盖成 `digest`。
* **坏 JSON / 缺 `digest` 字段 → 退出码 2**（缺字段 = 坏报告，不是"内容不一致"）。
"""

import datetime
import json

from . import __version__
from . import canonical, fidelity, gitobj, ledger, parity
from .errors import EXIT_FINDINGS, EXIT_OK, UsageError

MODULE = "report"

DIGEST_ALGORITHM = canonical.DIGEST_ALGORITHM

NOTE_PARITY_NOT_REQUESTED = "parity_not_requested"


# --------------------------------------------------------------------------- findings

def collect_findings(fidelity_report, ledger_report, parity_report=None, *, repo=None):
    """合并三源 finding 并按规范序排序（`(commit_time, commit_oid, path, old_range)`）。

    展开逻辑住在各自模块里（`fidelity.findings_of` / `parity.findings_of` /
    `ledger.findings_of`）——它们才是 ID 口径的产出方，`report` 只负责汇总与排序。
    `parity` 未请求时（`None`）不入账，**不伪造空结果**。
    """
    items = fidelity.findings_of(fidelity_report) + ledger.findings_of(ledger_report)
    if parity_report is not None:
        items += parity.findings_of(parity_report, repo=repo)
    return canonical.sort_findings(items)


# --------------------------------------------------------------------------- 报告主体

def _default_as_of(repo, end_rev, *dates):
    """报告 `as_of` = 三源 `as_of` 里最大的日期（`YYYY-MM-DD` 按字典序即按时间序）。

    为什么用各源的 `as_of` 而不是自己重算时间戳：`fidelity` / `ledger` / `parity`
    各自都已把"本模块输入里的最新提交时间"算成日期，且**空输入都回落 `end_rev`（默认
    `HEAD`）**。直接取最大值最省口径、也不会漏掉 parity（它只给日期，不给时间戳）。

    全部为 `None`（例如空仓库、无提交）时才回落到 `end_rev` 的提交时间；
    这样同一仓库的三个模块给出同一个 `as_of`，不会出现"report 落成 1970-01-01"。
    """
    values = [value for value in dates if value]
    if values:
        return max(values)
    stamp = gitobj.commit_time(repo, end_rev)
    return datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).strftime("%Y-%m-%d")


def _report_range(range_spec, since=None, until=None):
    return {"kind": "range" if range_spec else ("since" if since else "all"),
            "spec": range_spec, "since": since, "until": until}


def build_report(repo, *, range_spec=None, parity_from=None, parity_to=None,
                 as_of=None, since=None, until=None):
    """跑三个模块并组装报告（**未填 digest**）。"""
    gitobj.require_git_repo(repo)
    git_version = gitobj.require_version(repo, gitobj.GIT_MIN_FIDELITY)
    object_format = gitobj.object_format(repo)

    # 输入类错误（坏 rev / 坏 as_of）一律先拦成用法错误（2），再谈环境（3）
    if as_of is not None:
        fidelity.validate_as_of(as_of)
    if (parity_from is None) != (parity_to is None):
        raise UsageError("--parity-from 与 --parity-to 必须成对给出")

    end_rev = fidelity.range_end(range_spec)
    fidelity_report = fidelity.scan(repo, range_spec=range_spec, since=since,
                                    until=until, as_of=as_of)
    ledger_report = ledger.ledger_scan(repo, range_spec=range_spec, as_of=as_of)

    notes = []
    parity_report = None
    if parity_from is not None and parity_to is not None:
        parity_report = parity.parity_scan(repo, parity_from, parity_to, as_of=as_of)
    else:
        notes.append(NOTE_PARITY_NOT_REQUESTED)

    findings = collect_findings(fidelity_report, ledger_report, parity_report, repo=repo)
    if as_of is None:
        # 报告头 `as_of`：取三源 `as_of` 的最大值（各源空输入都回落 end_rev，口径一致）
        as_of = _default_as_of(repo, end_rev, fidelity_report["as_of"],
                               ledger_report["as_of"],
                               parity_report["as_of"] if parity_report else None)

    return {
        "tool_version": __version__,
        "git_version": git_version,
        "object_format": object_format,
        "gitattributes_oid": gitobj.attributes_oid(repo, end_rev),
        "config_overrides": list(gitobj.CONFIG_OVERRIDES),
        "range": _report_range(range_spec, since=since, until=until),
        "as_of": as_of,
        "findings_digest_algorithm": DIGEST_ALGORITHM,
        "module": MODULE,
        "parity_requested": parity_report is not None,
        "fidelity": fidelity_report,
        "parity": parity_report,
        "ledger": ledger_report,
        "findings": findings,
        "notes": notes,
    }


# --------------------------------------------------------------------------- --verify

def _json_path_parts(value, prefix=""):
    """把嵌套对象摊平成 ``[(json_path, value)]``，用于逐字节差异定位。"""
    out = []
    if isinstance(value, dict):
        for key in sorted(value):
            out.extend(_json_path_parts(value[key], "%s.%s" % (prefix, key) if prefix else key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            out.extend(_json_path_parts(item, "%s[%d]" % (prefix, index)))
    else:
        out.append((prefix, value))
    return out


def first_difference(expected, actual):
    """首个差异的 JSON path + 期望/实际；完全相同返回 ``None``。

    逐字节比较的落点：两侧先各自规范化成 JSON 文本，再逐字符定位——
    这样"值相同但键序不同"不会误报，而"少一个键/多一个键"必被抓住。
    """
    expected_text = canonical.dumps(expected)
    actual_text = canonical.dumps(actual)
    if expected_text == actual_text:
        return None

    expected_flat = _json_path_parts(expected)
    actual_flat = _json_path_parts(actual)
    actual_map = dict(actual_flat)
    for path, value in expected_flat:
        if path not in actual_map:
            return {"json_path": path, "expected": value, "actual": None}
        if actual_map[path] != value:
            return {"json_path": path, "expected": value, "actual": actual_map[path]}
    expected_map = dict(expected_flat)
    for path, value in actual_flat:
        if path not in expected_map:
            return {"json_path": path, "expected": None, "actual": value}
    # 摊平后无差异 → 差异在键序/重复键上；退化为整树比较
    return {"json_path": "", "expected": expected, "actual": actual}


def read_report(path):
    """读回报告文件；坏 JSON / 缺 `digest` 字段 → 用法错误（2）。"""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise UsageError("无法读取报告文件：%s（%s）" % (path, exc))
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise UsageError("报告文件不是合法 JSON：%s（%s）" % (path, exc))
    if not isinstance(payload, dict):
        raise UsageError("报告文件顶层不是对象：%s" % path)
    if not isinstance(payload.get(canonical.DIGEST_FIELD), str):
        raise UsageError("报告文件缺少 digest 字段（缺字段 = 坏报告）：%s" % path)
    return payload


def _without_digest(payload):
    return dict((key, value) for key, value in payload.items()
                if key != canonical.DIGEST_FIELD)


def verify_report(repo, path, *, out=None):
    """`--verify`：digest 校验 + 同一对象库重推逐字节比较。返回 ``(code, text)``。

    定位顺序（先内容、后 digest）：
    1. 用同一对象库重推，与读回报告**去掉 `digest` 字段后**逐字节比较；
       有差异 → 退出码 1，`json_path` 指向**被改的那个字段**（这是"篡改一个字节"要的答案）；
    2. 内容一致但 `digest` 自校验不过（只改了 `digest` 自身）→ 退出码 1，定位到 `digest`；
    3. 两者都过 → 退出码 0，stdout 打 `verified: N merges, M findings`。

    为什么内容比较排在 digest 之前：若先查 digest，任何内容篡改都会先命中 `digest` 字段，
    把"哪一处被改了"这个真正有用的答案盖掉。digest 的职责是**发现**不一致，JSON path 的
    职责是**定位**，定位必须落在真实差异上。
    """
    payload = read_report(path)

    # 1) 用同一对象库重推：同一 range / since / until / as_of / parity 引用
    range_section = payload.get("range") or {}
    rebuilt = canonical.with_digest(build_report(
        repo,
        range_spec=range_section.get("spec"),
        since=range_section.get("since"),
        until=range_section.get("until"),
        parity_from=_parity_ref(payload, "from"),
        parity_to=_parity_ref(payload, "to"),
        as_of=payload.get("as_of"),
    ))

    difference = first_difference(_without_digest(rebuilt), _without_digest(payload))
    if difference is not None:
        return EXIT_FINDINGS, canonical.dumps({"status": "content_mismatch",
                                                "difference": difference})

    # 2) 内容一致 → 剩下的不一致只可能出在 `digest` 自身
    if not canonical.verify_digest(payload):
        difference = {"json_path": canonical.DIGEST_FIELD,
                      "expected": canonical.digest_of(payload),
                      "actual": payload.get(canonical.DIGEST_FIELD)}
        return EXIT_FINDINGS, canonical.dumps({"status": "digest_mismatch",
                                                "difference": difference})

    merges = len(rebuilt["fidelity"]["merges"])
    return EXIT_OK, "verified: %d merges, %d findings\n" % (merges, len(rebuilt["findings"]))


def _parity_ref(payload, key):
    section = payload.get("parity")
    if not isinstance(section, dict):
        return None
    return section.get(key)


# --------------------------------------------------------------------------- 渲染

def render_markdown(report):
    lines = [
        "# Merge 保真度审计报告（report）",
        "",
        "- 工具版本：%s（%s / %s）" % (report["tool_version"], report["git_version"],
                                      report["object_format"]),
        "- 范围：%s · as_of：%s" % (report["range"], report["as_of"]),
        "- digest 算法：%s" % report["findings_digest_algorithm"],
        "- 输入：fidelity（%d merge）· parity（%s）· ledger（%d 条 revert）"
        % (len(report["fidelity"]["merges"]),
           "未请求" if report["parity"] is None else "%d 候选" % report["parity"]["candidates"],
           len(report["ledger"]["entries"])),
        "",
        "| finding id | kind | merge/revert | path | old | new |",
        "|---|---|---|---|---|---|",
    ]
    for finding in report["findings"]:
        lines.append("| `%s` | %s | `%s` | %s | %s | %s |" % (
            finding["id"][:12], finding["kind"], finding["commit_oid"][:12],
            finding["path"], finding["old_range"], finding["new_range"]))
    if report["notes"]:
        lines += ["", "## 说明", ""]
        for note in report["notes"]:
            lines.append("- `%s`" % note)
    lines.append("")
    return "\n".join(lines)


def run(args):
    """执行 `mergefidelity report <repo> [...]` → 退出码。"""
    verify_path = getattr(args, "verify", None)
    if verify_path:
        code, text = verify_report(args.repo, verify_path)
        print(text, end="" if text.endswith("\n") else "\n")
        return code

    report = build_report(
        args.repo,
        range_spec=getattr(args, "range", None),
        parity_from=getattr(args, "parity_from", None),
        parity_to=getattr(args, "parity_to", None),
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
