"""`ledger` 模块守门：3 个 fixture 与 golden 逐项一致 + 三状态/校验/重放纪律。

golden 是 M1 由**独立 oracle**（生成器内 `ledger_expect`）算出的期望；本测试把生产实现
与它对齐。合成仓库本体不入仓，因此这里用一个 session 级夹具确保它们已生成。

覆盖：
* 3 个 fixture 与 `expect.json` 的 `entries` / `counts` / `unavailable` **逐项一致**
  （条目字段集合也逐项锁定，防止悄悄多/少一个字段）；
* `patchid-mismatch` → `REVERT_UNVERIFIED(verified=false)`；
* `UNAVAILABLE` 与"无 successor"是**不同输出**（能力缺失时不降级猜）；
* 同一 revert 只入账一次；
* 报告无绝对路径、双跑逐字节一致、`digest` 可复算、不创建任何 worktree。
"""

import io
import json
import os
import subprocess
import sys

import pytest

from mergefidelity import canonical, cli, gitobj, ledger

import synthrepo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_ROOT = os.path.join(ROOT, "data", "fixtures", "ledger")
GENERATOR = os.path.join(ROOT, "tools", "gen_fixtures.py")

ALL_FIXTURES = ["no-successor", "then-redone", "patchid-mismatch"]
ENTRY_KEYS = ("revert_oid", "reverted_oid", "reverted_subject", "reverted_commit_time",
              "status", "verified", "successor_oid", "paths")


def _names():
    if not os.path.isdir(FIXTURE_ROOT):
        return []
    return sorted(name for name in os.listdir(FIXTURE_ROOT)
                  if os.path.isfile(os.path.join(FIXTURE_ROOT, name, "expect.json")))


@pytest.fixture(scope="session", autouse=True)
def ledger_repos():
    """确保 3 个合成仓库已生成（缺失则现跑生成器，只生成 ledger 套件）。"""
    missing = [name for name in _names()
               if not os.path.isdir(os.path.join(FIXTURE_ROOT, name, "repo"))]
    if missing:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", GENERATOR, "--out", "data/fixtures",
             "--suite", "ledger"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
    return True


def _golden(name):
    with io.open(os.path.join(FIXTURE_ROOT, name, "expect.json"), encoding="utf-8") as handle:
        return json.load(handle)


def _repo(name):
    return os.path.join(FIXTURE_ROOT, name, "repo")


def _scan(name, **kwargs):
    return ledger.ledger_scan(_repo(name), **kwargs)


# ------------------------------------------------------------------ golden 对账

@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_ledger_matches_golden(name):
    """`entries` / `counts` / `unavailable` 与 golden 逐项一致。"""
    golden = _golden(name)
    report = _scan(name)
    assert report["entries"] == golden["entries"], name
    assert report["counts"] == golden["counts"], name
    assert report["unavailable"] == golden["unavailable"], name


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_entry_field_set_is_exactly_golden(name):
    """条目字段集合逐项锁定：多一个（如 `evidence`）或少一个都算口径漂移。"""
    for entry in _scan(name)["entries"]:
        assert tuple(sorted(entry)) == tuple(sorted(ENTRY_KEYS))


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_same_revert_is_recorded_once(name):
    report = _scan(name)
    oids = [entry["revert_oid"] for entry in report["entries"]]
    assert len(oids) == len(set(oids))


# ------------------------------------------------------------------ 三状态与校验

def test_no_successor_status_and_verified():
    report = _scan("no-successor")
    (entry,) = report["entries"]
    assert entry["status"] == "REVERTED_NO_SUCCESSOR"
    assert entry["verified"] is True
    assert entry["successor_oid"] is None
    assert report["counts"] == {"no_successor": 1, "then_redone": 0, "unverified": 0}


def test_then_redone_reports_successor():
    report = _scan("then-redone")
    (entry,) = report["entries"]
    assert entry["status"] == "REVERTED_THEN_REDONE"
    assert entry["verified"] is True
    assert entry["successor_oid"] == "7146239cea5c4187ef11c8e73ccaf6a1a25d809a"
    # successor 确实在 revert 之后（不是 revert 自身或它的祖先）
    assert entry["successor_oid"] not in gitobj.rev_list(_repo("then-redone"), [entry["revert_oid"]])


def test_patchid_mismatch_is_unverified_not_guessed():
    """正文声称回滚 X、实际 diff 回滚 Y → 不认这条 revert：`verified=false` 且不算 successor。"""
    report = _scan("patchid-mismatch")
    (entry,) = report["entries"]
    assert entry["status"] == "REVERT_UNVERIFIED"
    assert entry["verified"] is False
    assert entry["successor_oid"] is None
    assert report["counts"] == {"no_successor": 0, "then_redone": 0, "unverified": 1}


def test_reverse_patchid_is_the_verification_basis():
    """校验依据直接复算一遍：revert 的 `-U0` patch-id == 被回滚提交 diff **取反**后的 id。"""
    repo = _repo("then-redone")
    (entry,) = ledger.ledger_scan(repo)["entries"]
    revert_pid = gitobj.patch_id(repo, gitobj.commit_diff(repo, entry["revert_oid"], context=0))
    reversed_pid = gitobj.patch_id(
        repo, gitobj.commit_diff(repo, entry["reverted_oid"], context=0, reverse=True))
    assert revert_pid == reversed_pid, "反向 patch-id 相等才是 `verified=true` 的依据"


# ------------------------------------------------------------------ UNAVAILABLE ≠ 无 successor

def test_unavailable_is_distinct_from_no_successor(monkeypatch):
    """`--find-object` 不可用时**不下**"没有 successor"的结论——两条输出必须不同。"""
    repo = _repo("no-successor")

    normal = ledger.ledger_scan(repo)
    assert normal["entries"][0]["status"] == "REVERTED_NO_SUCCESSOR"
    assert normal["unavailable"] == []

    monkeypatch.setattr(ledger, "_find_object_supported", lambda _repo: False)
    degraded = ledger.ledger_scan(repo)
    monkeypatch.undo()

    assert degraded["unavailable"] == [{"reason": "git_too_old", "capability": "find-object"}]
    assert degraded["entries"][0]["status"] == "REVERT_UNVERIFIED"
    assert degraded["entries"][0]["successor_oid"] is None
    assert degraded["entries"][0] != normal["entries"][0], "能力缺失必须是不同输出"
    assert degraded["counts"] == {"no_successor": 0, "then_redone": 0, "unverified": 1}
    # `verified` 与 `status` 是两件事：反向校验仍通过（这条 revert 确是真的），
    # 只是"是否被重做"判不了——两者的区别写在 `unavailable` 里
    assert degraded["entries"][0]["verified"] is True
    assert normal["entries"][0]["verified"] is True
    assert degraded["unavailable"] != normal["unavailable"]


def test_mismatch_and_unavailable_are_two_kinds_of_unverified(monkeypatch):
    """两种 `REVERT_UNVERIFIED` 必须可区分：`unavailable` 非空 = 重放判不了；空 = 正文对不上。"""
    mismatch = ledger.ledger_scan(_repo("patchid-mismatch"))
    assert mismatch["entries"][0]["status"] == "REVERT_UNVERIFIED"
    assert mismatch["entries"][0]["verified"] is False
    assert mismatch["unavailable"] == []

    monkeypatch.setattr(ledger, "_find_object_supported", lambda _repo: False)
    degraded = ledger.ledger_scan(_repo("no-successor"))
    monkeypatch.undo()
    assert degraded["entries"][0]["status"] == "REVERT_UNVERIFIED"
    assert degraded["entries"][0]["verified"] is True
    assert degraded["unavailable"], "能力缺失必须留下痕迹，否则两种 UNVERIFIED 无法区分"


# ------------------------------------------------------------------ 范围与确定性

def test_range_limits_enumeration():
    """`--range` 收窄枚举：只给被回滚的那个提交 → 范围内没有 revert → 空账本。"""
    repo = _repo("no-successor")
    (entry,) = ledger.ledger_scan(repo)["entries"]
    report = ledger.ledger_scan(repo, range_spec=entry["reverted_oid"])
    assert report["entries"] == []
    assert report["counts"] == {"no_successor": 0, "then_redone": 0, "unverified": 0}
    assert report["range"] == {"kind": "range", "spec": entry["reverted_oid"]}


def test_bad_range_is_usage_error():
    from mergefidelity.errors import UsageError

    with pytest.raises(UsageError):
        ledger.ledger_scan(_repo("no-successor"), range_spec="no-such-ref..main")


def test_bad_range_cli_exit_code_is_2(capsys):
    code = cli.main(["ledger", _repo("no-successor"), "--range=no-such-ref..main"])
    assert code == 2
    assert "不是有效引用" in capsys.readouterr().err


def test_as_of_must_be_iso_date():
    from mergefidelity.errors import UsageError

    with pytest.raises(UsageError):
        ledger.ledger_scan(_repo("no-successor"), as_of="2026/01/01")


def test_reland_invisible_to_find_object_is_still_then_redone(tmp_path):
    """**筛选不能当结论**：`--find-object` 只认 blob，看不见"只差空白 + 文件别处已变"的重新落地。

    构造（实测 2026-10-19）：原始修复只改第 2 行（`b` → `X=1`），revert 后又有一个提交改了
    **文件别处**（第 5 行 `e` → `E`），最后重新落地同一处改动但写成 `X =   1`。
    于是 re-land 的 old/new blob 都不等于原始提交的 old/new blob，`--find-object` 完全看不见它；
    而两侧 `-U0` patch-id 相等（patch-id 对空白免疫）。若把筛选集落空直接当"没有 successor"，
    就会**静默漏报**——正是本工具要审计的那类毛病。
    """
    repo = str(tmp_path / "repo")
    synthrepo.init_repo(repo)
    synthrepo.commit(repo, "seed", {"src/synthapp/core.py": ["a", "b", "c", "d", "e"]})
    synthrepo.commit(repo, "fix", {"src/synthapp/core.py": ["a", "X=1", "c", "d", "e"]})

    reverted = synthrepo.git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    synthrepo.git(repo, "revert", "--no-edit", reverted)
    revert_oid = synthrepo.git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    synthrepo.commit(repo, "unrelated edit elsewhere",
                     {"src/synthapp/core.py": ["a", "b", "c", "d", "E"]})
    re_landed = synthrepo.commit(
        repo, "re-land with spacing", {"src/synthapp/core.py": ["a", "X =   1", "c", "d", "E"]})

    # 先确认本场景真的构成漏报条件（否则本测试没在测东西）
    assert re_landed not in set(gitobj.rev_list(repo, [reverted])), "re-land 必须在 revert 之后"
    original_pid = gitobj.patch_id(repo, gitobj.commit_diff(repo, reverted, context=0))
    relanded_pid = gitobj.patch_id(repo, gitobj.commit_diff(repo, re_landed, context=0))
    assert original_pid == relanded_pid, "-U0 下跨空白等价（这正是漏报的来源）"

    touched = ledger._find_object_commits(repo, gitobj.changed_blob_oids(repo, reverted))
    assert re_landed not in touched, "该 re-land 的 old/new blob 都不在筛选集里（漏报场景成立）"

    (entry,) = ledger.ledger_scan(repo)["entries"]
    assert entry["status"] == "REVERTED_THEN_REDONE", "筛选集落空必须回到全量复扫，不能静默漏报"
    assert entry["successor_oid"] == re_landed
    assert entry["verified"] is True
    assert entry["revert_oid"] == revert_oid


def test_no_worktree_is_created():
    """ledger 只读对象库，不建任何 worktree。"""
    repo = _repo("then-redone")
    before = gitobj.worktree_list(repo)
    ledger.ledger_scan(repo)
    assert gitobj.worktree_list(repo) == before


def test_same_input_twice_is_byte_identical_and_digest_verifies():
    first = canonical.with_digest(ledger.ledger_scan(_repo("then-redone")))
    second = canonical.with_digest(ledger.ledger_scan(_repo("then-redone")))
    assert canonical.dumps(first) == canonical.dumps(second)
    assert canonical.verify_digest(first) is True


def test_report_header_is_deterministic_and_has_no_absolute_path():
    repo = _repo("no-successor")
    report = ledger.ledger_scan(repo)
    assert report["tool_version"]
    assert report["git_version"].startswith("git version")
    assert report["object_format"] in ("sha1", "sha256")
    assert report["as_of"] == "2026-01-01"          # 来自提交时间，不读系统时钟
    text = canonical.dumps(canonical.with_digest(report))
    assert os.path.abspath(repo).replace("\\", "/") not in text
    assert "C:" not in text and "/tmp/" not in text


# ------------------------------------------------------------------ CLI 契约

def test_cli_ledger_prints_canonical_json(capsys):
    code = cli.main(["ledger", _repo("then-redone")])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["counts"]["then_redone"] == 1
    assert canonical.verify_digest(payload) is True


def test_cli_ledger_markdown_and_out(tmp_path, capsys):
    md = tmp_path / "ledger.md"
    code = cli.main(["ledger", _repo("patchid-mismatch"), "--format=md", "--out", str(md)])
    assert code == 0
    text = md.read_text(encoding="utf-8")
    assert "REVERT_UNVERIFIED" in text and "账本" in text
    raw = md.read_bytes()
    assert raw.endswith(b"\n") and b"\r\n" not in raw


# ------------------------------------------------------------------ 基准工具

def test_bench_ledger_tool_runs_and_writes_json(tmp_path):
    out = tmp_path / "ledger-bench.json"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "bench_ledger.py"),
         "--out", str(out), "--only", "then-redone", "--repeats", "1"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["git_version"].startswith("git version")
    assert payload["fixtures"][0]["fixture"] == "then-redone"
    assert payload["fixtures"][0]["entries"] == 1
