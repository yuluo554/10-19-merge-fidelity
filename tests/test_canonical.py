"""规范 JSON / digest / finding ID / 原子写盘的守门测试。"""

import hashlib
import json
import os

import pytest

from mergefidelity import canonical


def test_dumps_is_canonical_and_idempotent():
    obj = {"b": 1, "a": {"y": [1, 2], "x": "中文"}, "c": None}
    text = canonical.dumps(obj)
    assert text.endswith("\n")
    assert text.count("\n") == 1
    # 无多余空白：分隔符是 "," 与 ":"，不出现 ", " / ": "
    assert '": ' not in text and ', "' not in text and ", " not in text
    assert "\\u4e2d" not in text  # ensure_ascii=False
    assert json.loads(text) == obj
    assert canonical.dumps(json.loads(text)) == text


def test_key_order_does_not_change_bytes():
    a = canonical.dumps({"x": 1, "y": 2})
    b = canonical.dumps({"y": 2, "x": 1})
    assert a == b


def test_digest_ignores_key_insertion_order_but_not_values():
    base = {"z": 1, "a": [1, 2, 3]}
    reordered = {"a": [1, 2, 3], "z": 1}
    assert canonical.digest_of(base) == canonical.digest_of(reordered)
    assert canonical.digest_of(base) != canonical.digest_of({"z": 2, "a": [1, 2, 3]})


def test_digest_excludes_its_own_field():
    body = {"a": 1}
    filled = canonical.with_digest(body)
    assert canonical.digest_of(filled) == canonical.digest_of(body)
    assert canonical.verify_digest(filled) is True
    assert canonical.verify_digest(body) is False  # 缺 digest 字段


def test_digest_matches_manual_sha256():
    body = {"hello": "世界"}
    text = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert canonical.digest_of(body) == expected


def test_finding_id_is_content_addressed_and_stable():
    args = ("a" * 40, "src/synthapp/x.py", "-", "4,1", "SMUGGLED")
    first = canonical.finding_id(*args)
    assert first == canonical.finding_id(*args)
    # 手工独立复算
    joined = "\x1f".join(args).encode("utf-8")
    assert first == hashlib.sha1(joined).hexdigest()
    # 任一字段变化 → 不同 ID
    for index in range(5):
        mutated = list(args)
        mutated[index] = mutated[index] + "X"
        assert canonical.finding_id(*mutated) != first


def test_finding_id_rejects_separator_inside_parts():
    with pytest.raises(ValueError):
        canonical.finding_id("a" * 40, "p\x1fq", "-", "1,1", "SMUGGLED")


def test_range_str():
    assert canonical.range_str(2, 1) == "2,1"
    assert canonical.range_str(2, 1, side_present=False) == "-"


def test_sort_findings_uses_declared_key():
    items = [
        {"commit_time": 20, "merge_oid": "b", "path": "p", "old_range": "-"},
        {"commit_time": 10, "merge_oid": "a", "path": "p", "old_range": "-"},
        {"commit_time": 10, "merge_oid": "a", "path": "p", "old_range": "1,1"},
    ]
    ordered = canonical.sort_findings(items)
    assert [i["commit_time"] for i in ordered] == [10, 10, 20]
    assert ordered[-1]["merge_oid"] == "b"


def test_write_atomic_writes_lf_and_replaces(tmp_path):
    target = tmp_path / "out.json"
    canonical.write_atomic(target, canonical.dumps({"a": 1}))
    raw = target.read_bytes()
    assert raw.endswith(b"\n") and b"\r\n" not in raw and not raw.startswith(b"\xef\xbb\xbf")
    canonical.write_atomic(target, canonical.dumps({"a": 2}))
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_write_atomic_leaves_no_debris_on_failure(tmp_path, monkeypatch):
    target = tmp_path / "out.json"

    real_replace = os.replace

    def boom(src, dst):
        raise OSError("simulated failure")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        canonical.write_atomic(target, "{}")
    monkeypatch.setattr(os, "replace", real_replace)
    assert list(tmp_path.iterdir()) == []
