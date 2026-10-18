"""`parity` 模块守门：6 个 fixture 的双向 golden 逐项一致 + 三态/basis/worktree 纪律。

golden 是 M1 由**独立 oracle**（生成器内 `parity_expect`）算出的期望；本测试把生产实现
与它对齐。合成仓库本体不入仓，因此这里用一个 session 级夹具确保它们已生成。

覆盖：
* 双向 golden 逐项（标量 + 每个候选的 7 个字段）；
* 三态齐全（PRESENT/MISSING/MODIFIED）且 `basis` 必填；
* `-U0` 行号等价（context-shift）与空白等价（whitespace）；
* `note` 只提示不改判定（path-remap）；
* 临时 worktree **成功与异常两条路径**后 `git worktree list` 无残留；
* `--no-apply-fallback` 不创建任何 worktree；
* 报告无绝对路径、双跑逐字节一致、`digest` 可复算。
"""

import io
import json
import os
import subprocess
import sys

import pytest

from mergefidelity import canonical, cli, gitobj, parity

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_ROOT = os.path.join(ROOT, "data", "fixtures", "parity")
GENERATOR = os.path.join(ROOT, "tools", "gen_fixtures.py")

ALL_FIXTURES = [
    "bidirectional-basic", "context-shift", "whitespace",
    "partial-apply", "true-missing", "path-remap",
]
ROW_KEYS = ("commit", "subject", "u0_patchid", "status", "basis", "note",
            "equivalent_source", "paths")
SCALAR_KEYS = ("from", "to", "from_oid", "to_oid", "candidates",
               "present", "missing", "modified", "patch_parity")


def _names():
    if not os.path.isdir(FIXTURE_ROOT):
        return []
    return sorted(name for name in os.listdir(FIXTURE_ROOT)
                  if os.path.isfile(os.path.join(FIXTURE_ROOT, name, "expect.json")))


@pytest.fixture(scope="session", autouse=True)
def parity_repos():
    """确保 6 个合成仓库已生成（缺失则现跑生成器，只生成 parity 套件）。"""
    missing = [name for name in _names()
               if not os.path.isdir(os.path.join(FIXTURE_ROOT, name, "repo"))]
    if missing:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", GENERATOR, "--out", "data/fixtures",
             "--suite", "parity"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
    return True


def _golden(name):
    with io.open(os.path.join(FIXTURE_ROOT, name, "expect.json"), encoding="utf-8") as handle:
        return json.load(handle)


def _repo(name):
    return os.path.join(FIXTURE_ROOT, name, "repo")


def _scan(name, side="expect", **kwargs):
    """跑一个 fixture 的一个方向（`side` ∈ {"expect","expect_reverse"}）。"""
    scenario = _golden(name)[side]
    kwargs.setdefault("apply_fallback", True)
    return parity.parity_scan(_repo(name), scenario["from"], scenario["to"], **kwargs)


def _row_diff(record, expect):
    return dict((key, (record.get(key), expect.get(key)))
                for key in ROW_KEYS if record.get(key) != expect.get(key))


# ------------------------------------------------------------------ golden 对账

@pytest.mark.parametrize("name", ALL_FIXTURES)
@pytest.mark.parametrize("side", ["expect", "expect_reverse"])
def test_parity_matches_golden(name, side):
    """双侧（A→B 与 B→A）与 golden 逐项一致：标量 + 每个候选 7 个字段。"""
    golden = _golden(name)[side]
    report = _scan(name, side)
    for key in SCALAR_KEYS:
        assert report[key] == golden[key], key
    assert len(report["commits"]) == len(golden["commits"])
    for record, expect in zip(report["commits"], golden["commits"]):
        assert _row_diff(record, expect) == {}


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_candidate_order_follows_rev_list(name):
    """候选集与顺序 = `git rev-list --cherry-pick --right-only A...B`（golden 同源）。"""
    golden = _golden(name)
    scenario = golden["expect"]
    expected = gitobj.rev_list(
        _repo(name),
        ["--cherry-pick", "--right-only",
         "%s...%s" % (scenario["from"], scenario["to"])],
    )
    report = _scan(name)
    assert [row["commit"] for row in report["commits"]] == expected
    assert report["candidates"] == len(expected)


# ------------------------------------------------------------------ 三态与 basis

def test_three_states_all_present_with_basis():
    """bidirectional-basic 一个方向就三态齐备，且每行都有 `basis`。"""
    report = _scan("bidirectional-basic")
    statuses = dict((row["status"], row) for row in report["commits"])
    assert set(statuses) == {"PRESENT", "MISSING", "MODIFIED"}
    for row in report["commits"]:
        assert row["basis"] in ("patchid", "apply")
    assert statuses["PRESENT"]["basis"] == "patchid"
    assert statuses["PRESENT"]["equivalent_source"]
    assert statuses["MISSING"]["basis"] == "apply"
    assert statuses["MODIFIED"]["basis"] == "apply"


def test_patch_parity_counts_and_denominator():
    """`patch_parity = present / total`；分母 0 → `null`。"""
    report = _scan("bidirectional-basic")
    assert report["patch_parity"] == round(
        float(report["present"]) / report["candidates"], 12)
    assert report["present"] + report["missing"] + report["modified"] == report["candidates"]

    # 反向（release/1.0 侧无候选）→ 分母 0 → null
    reverse = _scan("true-missing", "expect_reverse")
    assert reverse["candidates"] == 1
    empty = parity.parity_scan(_repo("true-missing"), "release/1.0", "release/1.0")
    assert empty["candidates"] == 0
    assert empty["patch_parity"] is None


def test_u0_patchid_equivalence_across_line_numbers():
    """同一改动落在不同行号（默认上下文不同）→ `-U0` patch-id 相同 → PRESENT。"""
    report = _scan("context-shift")
    present = [row for row in report["commits"] if row["status"] == "PRESENT"]
    assert len(present) == 1
    assert present[0]["basis"] == "patchid"
    assert present[0]["subject"] == "fix at line 6"
    # 候选里确实有它：默认上下文的 cherry 判定没有把它筛掉（这正是 -U0 要补的一类）
    assert present[0]["commit"] in [row["commit"] for row in report["commits"]]


def test_u0_patchid_equivalence_across_whitespace_forms():
    """空白形态不同（`value=1` vs `value =    1`）→ `-U0` patch-id 相同 → PRESENT。"""
    report = _scan("whitespace")
    present = [row for row in report["commits"] if row["status"] == "PRESENT"]
    assert len(present) == 1
    assert present[0]["basis"] == "patchid"
    assert present[0]["subject"] == "fix loose spacing"


def test_u0_and_u3_contexts_have_distinct_roles():
    """K26 直接锁定：`-U0` 判等价（对行号免疫），默认 3 行上下文判**不**等价。

    `context-shift` 的同一改动落在第 2 行（release）vs 第 6 行（main）：
    `-U0` patch-id 相同（→ `PRESENT`），默认上下文不同（→ 若只用默认上下文就会漏判）。
    同时证明 apply 检查必须用 `-U3`：`-U0` 补丁没有上下文，apply 会过于宽松。
    """
    repo = _repo("context-shift")
    row = _golden("context-shift")["expect"]["commits"][0]
    assert row["status"] == "PRESENT" and row["basis"] == "patchid"
    commit, source = row["commit"], row["equivalent_source"]
    assert commit and source

    u0 = gitobj.patch_id(repo, gitobj.commit_diff(repo, commit, context=0))
    u3 = gitobj.patch_id(repo, gitobj.commit_diff(repo, commit, context=3))
    assert u0 == row["u0_patchid"]
    assert u0 != u3, "-U0 与默认上下文必须给出不同 patch-id（否则本口径无意义）"

    # A 侧那条同改动的提交（第 2 行）与它的 -U0 patch-id 相同 → 判 PRESENT 的依据
    source_u0 = gitobj.patch_id(repo, gitobj.commit_diff(repo, source, context=0))
    source_u3 = gitobj.patch_id(repo, gitobj.commit_diff(repo, source, context=3))
    assert source_u0 == u0, "-U0 下跨行号等价：这是 PRESENT 的判定依据"
    assert source_u3 != u3, "默认上下文下两者不等价：跨行号差异确实换掉了上下文"


def test_apply_check_uses_u3_not_u0(monkeypatch):
    """K26 直接锁定：apply 检查拿到的是 **`-U3`** 补丁（等价判定才用 `-U0`）。

    做法：截获 `apply --check` / `apply --reverse --check` 的 stdin，断言补丁**带上下文行**
    （hunk 头是 `@@ -1,5 +1,5 @@` 这种 3 行上下文形态，而不是 `-U0` 的 `@@ -2 +2 @@`）。
    口径理由：`-U0` 补丁没有上下文，`git apply` 会过于宽松（把"其实没有"判成"能套用"）。
    """
    seen = []
    original = parity._worktree_applies

    def spy(worktree, patch_text, *, reverse):
        seen.append(patch_text)
        return original(worktree, patch_text, reverse=reverse)

    monkeypatch.setattr(parity, "_worktree_applies", spy)
    parity.parity_scan(_repo("path-remap"), "release/1.0", "main")
    monkeypatch.undo()

    assert seen, "apply 兜底必须真的被调用（否则本测试没在测东西）"
    patch = seen[0]
    context_lines = [line for line in patch.split("\n") if line[:1] == " "]
    assert context_lines, "apply 检查拿到的补丁必须带上下文行（-U3），不能是 -U0"
    headers = [line for line in patch.split("\n") if line.startswith("@@")]
    assert headers, "补丁必须含 hunk 头"
    assert all("," in header for header in headers), \
        "hunk 头应体现多行上下文（-U3 形态，如 `@@ -1,5 +1,5 @@`），不是 `-U0` 的 `@@ -2 +2 @@`"



def test_partial_apply_is_modified():
    """目标侧只含一半改动 → 两个方向的 apply 检查都失败 → MODIFIED。"""
    report = _scan("partial-apply")
    modified = [row for row in report["commits"] if row["status"] == "MODIFIED"]
    assert len(modified) == 1
    assert modified[0]["basis"] == "apply"
    assert modified[0]["note"] == "partial_or_context_conflict"
    assert modified[0]["subject"] == "whole fix"


def test_true_missing_is_missing_via_apply():
    """目标侧完全没有该改动 → `apply --check` 成功 → MISSING(basis=apply)。"""
    report = _scan("true-missing")
    row = report["commits"][0]
    assert row["status"] == "MISSING"
    assert row["basis"] == "apply"
    assert row["note"] is None
    assert row["u0_patchid"]


def test_note_does_not_change_status_for_other_path():
    """同内容换到另一个路径：`note` 只提示，状态仍是 MISSING（path 参与 patch-id）。"""
    report = _scan("path-remap")
    row = [item for item in report["commits"] if item["subject"] == "same fix elsewhere"][0]
    assert row["status"] == "MISSING", "别处有同内容不得改判 PRESENT"
    assert row["basis"] == "apply"
    assert row["note"] == "content_equivalent_at_other_path"
    assert row["equivalent_source"], "note 应指向 A 侧那条同内容提交"


# ------------------------------------------------------------------ --no-apply-fallback

def test_no_apply_fallback_creates_no_worktree():
    """`--no-apply-fallback`：不创建任何 worktree；patch-id 不等 → MODIFIED(basis=patchid)。"""
    repo = _repo("bidirectional-basic")
    before = gitobj.worktree_list(repo)
    report = parity.parity_scan(repo, "release/1.0", "main", apply_fallback=False)
    assert report["worktree"] == {"created": False, "reason": None}
    assert report["apply_fallback"] is False
    assert gitobj.worktree_list(repo) == before
    # 无兜底时 `basis` 只有 patchid（PRESENT 与 MODIFIED 都是 patch-id 口径）
    for row in report["commits"]:
        assert row["basis"] == "patchid"
    # patch-id 命中仍是 PRESENT；未命中不再声称"存在性"结论
    statuses = sorted(row["status"] for row in report["commits"])
    assert statuses == ["MODIFIED", "MODIFIED", "MODIFIED", "PRESENT"]


# ------------------------------------------------------------------ worktree 纪律

def test_worktree_is_removed_after_success():
    repo = _repo("bidirectional-basic")
    before = gitobj.worktree_list(repo)
    parity.parity_scan(repo, "release/1.0", "main")
    assert gitobj.worktree_list(repo) == before, "成功路径后不得残留临时 worktree"


def test_worktree_is_removed_after_exception(monkeypatch):
    """异常路径也必须清理（remove --force → prune → rmtree 三连）。"""
    repo = _repo("bidirectional-basic")
    before = gitobj.worktree_list(repo)

    def boom(*_args, **_kwargs):
        raise RuntimeError("模拟判定中途异常")

    monkeypatch.setattr(parity, "_worktree_applies", boom)
    with pytest.raises(RuntimeError):
        parity.parity_scan(repo, "release/1.0", "main")
    monkeypatch.undo()
    assert gitobj.worktree_list(repo) == before, "异常路径后不得残留临时 worktree"


def test_report_contains_no_absolute_path():
    repo = _repo("bidirectional-basic")
    text = canonical.dumps(canonical.with_digest(parity.parity_scan(repo, "release/1.0", "main")))
    assert os.path.abspath(repo).replace("\\", "/") not in text
    assert "C:" not in text and "/Users/" not in text and "/tmp/" not in text


# ------------------------------------------------------------------ 确定性与报告头

def test_same_input_twice_is_byte_identical_and_digest_verifies():
    first = canonical.with_digest(parity.parity_scan(_repo("whitespace"), "release/1.0", "main"))
    second = canonical.with_digest(parity.parity_scan(_repo("whitespace"), "release/1.0", "main"))
    assert canonical.dumps(first) == canonical.dumps(second)
    assert canonical.verify_digest(first) is True


def test_report_header_is_deterministic():
    report = _scan("bidirectional-basic")
    assert report["tool_version"]
    assert report["git_version"].startswith("git version")
    assert report["object_format"] in ("sha1", "sha256")
    assert "merge.conflictStyle=merge" in report["config_overrides"]
    assert report["as_of"] == "2026-01-01"          # 来自提交时间，不读系统时钟
    assert report["gitattributes_oid"] is None      # fixture 无 .gitattributes


def test_as_of_must_be_iso_date():
    from mergefidelity.errors import UsageError

    with pytest.raises(UsageError):
        parity.parity_scan(_repo("whitespace"), "release/1.0", "main", as_of="2026/01/01")


# ------------------------------------------------------------------ 输入类错误归 2

def test_bad_ref_is_usage_error_not_environment():
    """解不出来的引用是**用法错误**（K31）：`--from/--to` 照 fidelity 办理。"""
    from mergefidelity.errors import UsageError

    repo = _repo("whitespace")
    for kwargs in ({"from_ref": "no-such-ref", "to_ref": "main"},
                   {"from_ref": "main", "to_ref": "no-such-ref"}):
        with pytest.raises(UsageError):
            parity.parity_scan(repo, **kwargs)


def test_bad_ref_cli_exit_code_is_2(capsys):
    code = cli.main(["parity", _repo("whitespace"), "--from=no-such-ref", "--to=main"])
    assert code == 2
    assert "不是有效引用" in capsys.readouterr().err


# ------------------------------------------------------------------ CLI 契约

def test_cli_parity_prints_canonical_json(capsys):
    code = cli.main(["parity", _repo("bidirectional-basic"), "--from=release/1.0", "--to=main"])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["candidates"] == 4
    assert payload["present"] == 1
    assert canonical.verify_digest(payload) is True


def test_cli_parity_no_apply_fallback_flag(capsys):
    code = cli.main(["parity", _repo("bidirectional-basic"), "--from=release/1.0",
                     "--to=main", "--no-apply-fallback"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["apply_fallback"] is False
    assert payload["worktree"]["created"] is False


def test_cli_parity_markdown_and_out(tmp_path, capsys):
    md = tmp_path / "parity.md"
    code = cli.main(["parity", _repo("true-missing"), "--from=release/1.0", "--to=main",
                     "--format=md", "--out", str(md)])
    assert code == 0
    text = md.read_text(encoding="utf-8")
    assert "MISSING" in text and "patch_parity" in text
    raw = md.read_bytes()
    assert raw.endswith(b"\n") and b"\r\n" not in raw


# ------------------------------------------------------------------ 基准工具

def test_bench_parity_tool_runs_and_writes_json(tmp_path):
    out = tmp_path / "parity-bench.json"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "bench_parity.py"),
         "--out", str(out), "--only", "bidirectional-basic", "--repeats", "1"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["git_version"].startswith("git version")
    assert payload["fixtures"][0]["fixture"] == "bidirectional-basic"
    assert payload["fixtures"][0]["candidates"] > 0
