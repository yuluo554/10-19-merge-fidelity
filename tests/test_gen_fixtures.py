"""合成 fixture 与 golden 的守门（M1）。

分两层：

* **快层**：直接读已冻结的 `data/fixtures/**/expect.json`，断言结构、注入意图与反例；
* **慢层**（`slow`）：真跑生成器 `--check`（重生成 20 个仓库并与冻结产物逐字节比对）——
  这一层才真正测"生成器确定性"，快层测不到它。
"""

import io
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "data", "fixtures")
GENERATOR = os.path.join(ROOT, "tools", "gen_fixtures.py")

SUITES = {
    "fidelity": 12,   # 题面 10 + 反例守护 1（drop-then-readd）+ custom-driver 1
    "parity": 6,
    "ledger": 3,
}


def _load(path):
    with io.open(path, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def golden():
    """读全部冻结 golden（不重生成，快）。"""
    out = {}
    for suite in SUITES:
        suite_dir = os.path.join(FIXTURES, suite)
        out[suite] = {}
        for name in sorted(os.listdir(suite_dir)):
            path = os.path.join(suite_dir, name, "expect.json")
            if os.path.isfile(path):
                out[suite][name] = _load(path)
    return out


# ------------------------------------------------------------------ 结构

@pytest.mark.parametrize("suite,count", sorted(SUITES.items()))
def test_fixture_counts_match_plan(suite, count, golden):
    assert len(golden[suite]) == count


def test_manifest_matches_directory_contents(golden):
    manifest = _load(os.path.join(FIXTURES, "manifest.json"))
    listed = sorted((item["suite"], item["name"]) for item in manifest["fixtures"])
    actual = sorted((suite, name) for suite in SUITES for name in golden[suite])
    assert listed == actual, "manifest.json 是生成物，必须与目录实际内容一致"
    assert manifest["counts"]["total"] == sum(SUITES.values())


def test_golden_files_are_canonical_lf_json():
    offenders = []
    for suite in SUITES:
        suite_dir = os.path.join(FIXTURES, suite)
        for name in sorted(os.listdir(suite_dir)):
            path = os.path.join(suite_dir, name, "expect.json")
            if not os.path.isfile(path):
                continue
            with io.open(path, "rb") as handle:
                raw = handle.read()
            if b"\r\n" in raw or not raw.endswith(b"\n") or raw.startswith(b"\xef\xbb\xbf"):
                offenders.append(path)
    assert offenders == []


def test_synthetic_repos_are_not_tracked_and_are_ignored():
    """合成仓库本体是生成物：既不入仓，也确实被 .gitignore 挡住。"""
    out = subprocess.run(["git", "ls-files", "data/fixtures"], cwd=ROOT,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tracked = out.stdout.decode("utf-8", "replace").splitlines()
    assert not [p for p in tracked if "/repo/" in p or p.endswith(".git")], tracked
    sample = os.path.join("data", "fixtures", "fidelity", "smuggle-extra-line", "repo")
    rc = subprocess.run(["git", "check-ignore", "-q", sample], cwd=ROOT).returncode
    assert rc == 0, "合成仓库目录必须被 .gitignore 排除：%s" % sample


# ------------------------------------------------------------------ fidelity

def test_each_fidelity_fixture_matches_its_declared_injection(golden):
    for name, record in golden["fidelity"].items():
        declared = record["declared_counts"]
        if declared is None:      # octopus：不进 hunk 分类
            assert record["skipped"], name
            continue
        counts = record["expect_counts"]
        assert counts["smuggled"] == declared["smuggled"], name
        assert counts["dropped"] == declared["dropped"], name
        hunks = record["merges"][0]["hunks"]
        assert len(hunks) == counts["smuggled"] + counts["dropped"], name


def test_fidelity_injection_distribution_matches_plan(golden):
    """题面分布：夹带 4 / 吞掉 3 / 正确解冲突 2 / octopus 1 = 10 个（各注入 1 处）。"""
    required = {
        "smuggle-extra-line", "smuggle-unrelated-file", "smuggle-function-body",
        "smuggle-new-file", "drop-guard-check", "drop-one-side", "drop-partial-hunk",
        "clean-resolution-a", "clean-resolution-b", "octopus",
    }
    assert required <= set(golden["fidelity"]), "题面要求的 10 个 fixture 必须都在"
    defect = [name for name, record in golden["fidelity"].items()
              if record["expect_counts"]
              and record["expect_counts"]["smuggled"] + record["expect_counts"]["dropped"] == 1]
    assert len([n for n in defect if n.startswith("smuggle")]) == 4, defect
    assert len([n for n in defect if n.startswith("drop")]) == 3, defect
    assert len(defect) == 7, defect


def test_extra_fixtures_are_guards_not_defects(golden):
    """额外两个 fixture 是守护（反例 / SKIPPED），不冒充"注入缺陷"。"""
    for name in ("drop-then-readd", "custom-driver"):
        counts = golden["fidelity"][name]["expect_counts"]
        assert counts["smuggled"] == 0 and counts["dropped"] == 0, name


def test_negative_control_fixtures_report_nothing(golden):
    for name in ("clean-resolution-a", "clean-resolution-b", "drop-then-readd"):
        counts = golden["fidelity"][name]["expect_counts"]
        assert counts["smuggled"] == 0 and counts["dropped"] == 0, name


def test_octopus_fixture_is_skipped_with_reason(golden):
    record = golden["fidelity"]["octopus"]
    assert record["skipped"] == [{"merge_oid": record["merge_oid"], "reason": "octopus"}]
    assert record["blob_fidelity_model"] is None, "octopus 不进 blob_fidelity 分母"


def test_clean_resolution_fixtures_have_resolution_hunks(golden):
    for name in ("clean-resolution-a", "clean-resolution-b"):
        assert golden["fidelity"][name]["expect_counts"]["resolution"] >= 1, name


def test_fidelity_refs_are_recorded_for_reproducibility(golden):
    for name, record in golden["fidelity"].items():
        assert record["refs"], name
        assert all(len(oid) in (40, 64) for oid in record["refs"].values()), name


# ------------------------------------------------------------------ parity

def test_parity_patchid_basis_fixtures_are_present(golden):
    """跨行号、空白差异必须走 `basis=patchid` 判 PRESENT（`-U0` 口径的核心断言）。"""
    for name in ("context-shift", "whitespace"):
        rows = golden["parity"][name]["expect"]["commits"]
        patchid_rows = [r for r in rows if r["status"] == "PRESENT" and r["basis"] == "patchid"]
        assert patchid_rows, name
        assert rows[0]["u0_patchid"], name


def test_parity_three_states_all_covered(golden):
    statuses = set()
    for record in golden["parity"].values():
        for key in ("expect", "expect_reverse"):
            statuses.update(row["status"] for row in record[key]["commits"])
    assert statuses == {"PRESENT", "MISSING", "MODIFIED"}


def test_parity_true_missing_is_missing(golden):
    rows = golden["parity"]["true-missing"]["expect"]["commits"]
    assert [r["status"] for r in rows] == ["MISSING"]


def test_parity_path_remap_is_flagged_but_not_present(golden):
    rows = golden["parity"]["path-remap"]["expect"]["commits"]
    assert rows[0]["note"] == "content_equivalent_at_other_path"
    assert rows[0]["status"] == "MISSING", "该路径上没有这个改动，不能因为别处有同内容就判 PRESENT"


def test_parity_patch_parity_arithmetic(golden):
    for name, record in golden["parity"].items():
        for key in ("expect", "expect_reverse"):
            section = record[key]
            total = section["candidates"]
            assert section["present"] + section["missing"] + section["modified"] == total, name
            expected = None if total == 0 else round(float(section["present"]) / total, 12)
            assert section["patch_parity"] == expected, name


# ------------------------------------------------------------------ ledger

def test_ledger_three_states_each_covered_once(golden):
    seen = {}
    for name, record in golden["ledger"].items():
        for entry in record["entries"]:
            seen.setdefault(entry["status"], []).append(name)
    assert set(seen) == {"REVERTED_NO_SUCCESSOR", "REVERTED_THEN_REDONE", "REVERT_UNVERIFIED"}


def test_ledger_unverified_is_not_a_successor_verdict(golden):
    record = golden["ledger"]["patchid-mismatch"]
    entry = record["entries"][0]
    assert entry["verified"] is False
    assert entry["status"] == "REVERT_UNVERIFIED"
    assert entry["successor_oid"] is None


def test_ledger_then_redone_has_successor(golden):
    entry = golden["ledger"]["then-redone"]["entries"][0]
    assert entry["status"] == "REVERTED_THEN_REDONE"
    assert entry["successor_oid"]
    assert entry["verified"] is True


# ------------------------------------------------------------------ 慢层：生成器确定性

@pytest.mark.slow
def test_check_regenerates_byte_identical_from_frozen():
    """真跑生成器 `--check`：重生成 20 个合成仓库并与冻结产物逐字节比对。

    这是"生成器确定性"的唯一硬证据——快层读的是盘上产物，生成器被改坏时快层照样绿。
    """
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", GENERATOR, "--out", "data/fixtures", "--check"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    text = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, text
    assert "逐字节一致" in text
