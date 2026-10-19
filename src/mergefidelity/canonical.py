"""规范 JSON、digest、finding ID 与原子写盘 —— 全项目唯一的写盘出口。

口径来源：`data/README.md` §4.5 / §4.6。任何模块都不得自行 `json.dump`。

不变量（每条都有测试）：

1. ``dumps`` 幂等：``dumps(json.loads(dumps(x))) == dumps(x)``。
2. ``digest_of`` 对键插入顺序不敏感、对值敏感；不含 ``digest`` 字段自身。
3. ``finding_id`` 与提交时间、主机、绝对路径无关；同参数两次相同，改任一字段即不同。
4. ``write_atomic`` 中途异常不留半个文件。
"""

import hashlib
import json
import os
import tempfile

# 规范 JSON 的冻结参数（改动即"会打挂基准"的口径变更，须同步 plan/03 与测试）
CANONICAL_KWARGS = {
    "ensure_ascii": False,
    "sort_keys": True,
    "separators": (",", ":"),
    "allow_nan": False,
}

DIGEST_FIELD = "digest"
DIGEST_ALGORITHM = "sha256"
ID_SEPARATOR = "\x1f"  # Unit Separator，见 data/README.md §4.5


def dumps(obj):
    """把对象序列化为规范 JSON 文本（末尾恰好一个 ``\\n``）。"""
    return json.dumps(obj, **CANONICAL_KWARGS) + "\n"


def dumps_bytes(obj):
    """规范 JSON 的 UTF-8 字节（无 BOM）。"""
    return dumps(obj).encode("utf-8")


def digest_of(report):
    """报告 digest = sha256(规范 JSON 去掉 ``digest`` 字段自身后的字节)。"""
    if not isinstance(report, dict):
        raise TypeError("digest_of 只接受 dict（规范报告对象）")
    body = {k: v for k, v in report.items() if k != DIGEST_FIELD}
    return hashlib.sha256(dumps_bytes(body)).hexdigest()


def with_digest(report):
    """返回填好 ``digest`` 的新报告对象（不修改入参）。"""
    body = {k: v for k, v in report.items() if k != DIGEST_FIELD}
    out = dict(body)
    out[DIGEST_FIELD] = digest_of(body)
    return out


def verify_digest(report):
    """校验报告内 ``digest`` 是否与重算值一致；缺字段/不合法返回 False。"""
    if not isinstance(report, dict):
        return False
    actual = report.get(DIGEST_FIELD)
    if not isinstance(actual, str):
        return False
    return actual == digest_of(report)


def finding_id(merge_oid, path, old_range, new_range, kind):
    """内容寻址 finding ID = sha1(merge_oid ‖ path ‖ old_range ‖ new_range ‖ kind)。

    分隔符固定为单个 ``\\x1f``，UTF-8 编码。ID 不含提交时间、扫描时刻、主机名、
    绝对路径——同一 finding 在任何机器上重算必须相同。
    """
    parts = [merge_oid, path, old_range, new_range, kind]
    for part in parts:
        if not isinstance(part, str):
            raise TypeError("finding_id 的五个组成部分都必须是 str")
        if ID_SEPARATOR in part:
            raise ValueError("组成部分不得包含分隔符 U+001F")
    joined = ID_SEPARATOR.join(parts).encode("utf-8")
    return hashlib.sha1(joined).hexdigest()


def range_str(start, count, side_present=True):
    """hunk 区间字符串 ``<start>,<count>``（0 基）。

    该侧**一行都没有**（``count == 0``，纯插入/纯删除）或该侧根本不存在时，写 ``-``
    （`data/README.md` §4.5："无对应侧时写 ``-``"）。
    """
    if not side_present or int(count) <= 0:
        return "-"
    return "%d,%d" % (int(start), int(count))


def sort_key_finding(finding):
    """finding 的规范排序键：``(commit_time, commit_oid, path, old_range)``。

    `commit_oid` 是"该 finding 挂在哪个提交上"（fidelity 的 merge / ledger 的 revert /
    parity 的候选提交）。全项目只有这一处排序口径。
    """
    return (
        int(finding.get("commit_time", 0)),
        str(finding.get("commit_oid", "")),
        str(finding.get("path", "")),
        str(finding.get("old_range", "")),
    )


def sort_findings(findings):
    """返回按规范序排序的新列表（不改入参）。"""
    return sorted(findings, key=sort_key_finding)


def write_atomic(path, text):
    """原子写盘：同目录临时文件 + ``os.replace``；失败时不留残件。

    行尾固定 LF、编码 UTF-8 无 BOM、结尾恰好一个换行由 ``dumps`` 保证。
    """
    path = os.fspath(path)
    directory = os.path.dirname(os.path.abspath(path)) or "."
    if not os.path.isdir(directory):
        raise FileNotFoundError("输出目录不存在：%s" % directory)
    data = text.encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=".mf-tmp-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path
