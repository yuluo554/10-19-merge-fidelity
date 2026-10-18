"""`fidelity` 模块守门：11 个 fixture 的 payload 与 golden 逐项一致 + 退出码语义。

golden 是 M1 由**独立 oracle**（生成器内）算出的期望；本测试把生产实现的结果与它对齐。
合成仓库本体不入仓，因此这里用一个 session 级夹具确保它们已生成（缺失时只跑 fidelity 套件）。
"""

import io
import json
import os
import subprocess
import sys

import pytest

from mergefidelity import canonical, cli, fidelity

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_ROOT = os.path.join(ROOT, "data", "fixtures", "fidelity")
GENERATOR = os.path.join(ROOT, "tools", "gen_fixtures.py")

SINGLE_FINDING = [
    "smuggle-extra-line", "smuggle-unrelated-file", "smuggle-function-body",
    "smuggle-new-file", "drop-guard-check", "drop-one-side", "drop-partial-hunk",
]
NEGATIVE_CONTROLS = ["clean-resolution-a", "clean-resolution-b", "drop-then-readd"]
SKIP_FIXTURES = ["octopus", "custom-driver"]
ALL_FIXTURES = SINGLE_FINDING + NEGATIVE_CONTROLS + SKIP_FIXTURES


def _names():
    if not os.path.isdir(FIXTURE_ROOT):
        return []
    return sorted(name for name in os.listdir(FIXTURE_ROOT)
                  if os.path.isfile(os.path.join(FIXTURE_ROOT, name, "expect.json")))


@pytest.fixture(scope="session", autouse=True)
def fidelity_repos():
    """确保 11 个合成仓库已生成（缺失则现跑生成器，只生成 fidelity 套件）。"""
    missing = [name for name in _names()
               if not os.path.isdir(os.path.join(FIXTURE_ROOT, name, "repo"))]
    if missing:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", GENERATOR, "--out", "data/fixtures", "--suite", "fidelity"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
    return True


def _golden(name):
    with io.open(os.path.join(FIXTURE_ROOT, name, "expect.json"), encoding="utf-8") as handle:
        return json.load(handle)


def _repo(name):
    return os.path.join(FIXTURE_ROOT, name, "repo")


def _compare(record, expect):
    keys = ("merge_oid", "parents", "merge_base", "recorded_tree", "mechanical_tree",
            "mechanical_conflict", "counts", "hunks")
    return dict((key, (record.get(key), expect.get(key)))
                for key in keys if record.get(key) != expect.get(key))


# ------------------------------------------------------------------ golden 对账

@pytest.mark.parametrize("name", SINGLE_FINDING + NEGATIVE_CONTROLS)
def test_merge_record_matches_golden(name):
    golden = _golden(name)
    report = fidelity.scan(_repo(name))
    assert len(report["merges"]) == 1
    record = report["merges"][0]
    assert _compare(record, golden["merges"][0]) == {}
    model = golden["blob_fidelity_model"]
    for key in ("blob_fidelity", "paths_total", "paths_same",
                "path_only_in_recorded", "path_only_in_mechanical"):
        assert record[key] == model[key], key


@pytest.mark.parametrize("name", SINGLE_FINDING)
def test_each_injected_defect_surfaces_once(name):
    golden = _golden(name)
    counts = fidelity.scan(_repo(name))["merges"][0]["counts"]
    assert counts["smuggled"] == golden["declared_counts"]["smuggled"]
    assert counts["dropped"] == golden["declared_counts"]["dropped"]
    assert counts["smuggled"] + counts["dropped"] == 1, "每个 fixture 只注入 1 处缺陷"


@pytest.mark.parametrize("name", NEGATIVE_CONTROLS)
def test_negative_controls_report_nothing(name):
    counts = fidelity.scan(_repo(name))["merges"][0]["counts"]
    assert counts["smuggled"] == 0 and counts["dropped"] == 0, name


def test_custom_driver_paths_are_skipped_and_excluded_from_denominator():
    golden = _golden("custom-driver")
    report = fidelity.scan(_repo("custom-driver"))
    assert report["skipped"] == golden["skipped"]
    assert report["skipped"][0]["reason"] == "custom_driver"
    assert report["skipped"][0]["paths"] == ["synthapp.dat"]
    record = report["merges"][0]
    # 命中 driver 的路径不进分母，也不参与 hunk 分类
    assert "synthapp.dat" not in record["path_only_in_recorded"]
    assert all(h["path"] != "synthapp.dat" for h in record["hunks"])
    assert record["counts"]["smuggled"] == 0 and record["counts"]["dropped"] == 0


def test_octopus_is_skipped_and_not_counted():
    report = fidelity.scan(_repo("octopus"))
    assert report["merges"] == []
    assert [item["reason"] for item in report["skipped"]] == ["octopus"]
    assert report["summary"]["merges_scanned"] == 0
    assert report["summary"]["merges_total"] == 1


def test_report_header_is_deterministic_and_pathless():
    report = fidelity.scan(_repo("smuggle-extra-line"))
    assert report["tool_version"]
    assert report["git_version"].startswith("git version")
    assert report["object_format"] in ("sha1", "sha256")
    assert report["config_overrides"]
    assert report["as_of"] == "2026-01-01"          # 来自提交时间，不读系统时钟
    text = canonical.dumps(report)
    assert ROOT.replace("\\", "/") not in text
    assert "C:" not in text and "/Users/" not in text


def test_same_repo_twice_is_byte_identical():
    first = canonical.dumps(canonical.with_digest(fidelity.scan(_repo("drop-one-side"))))
    second = canonical.dumps(canonical.with_digest(fidelity.scan(_repo("drop-one-side"))))
    assert first == second


def test_digest_verifies():
    filled = canonical.with_digest(fidelity.scan(_repo("smuggle-unrelated-file")))
    assert canonical.verify_digest(filled) is True


# ------------------------------------------------------------------ 选项与范围

def test_show_kind_filters_listed_hunks():
    repo = _repo("drop-one-side")
    only_dropped = fidelity.scan(repo, kinds=("DROPPED",))
    assert [h["kind"] for h in only_dropped["merges"][0]["hunks"]] == ["DROPPED"]
    only_smuggled = fidelity.scan(repo, kinds=("SMUGGLED",))
    assert only_smuggled["merges"][0]["hunks"] == []


def test_show_resolution_adds_resolution_hunks():
    repo = _repo("clean-resolution-a")
    with_res = fidelity.scan(repo, show_resolution=True)
    kinds = set(h["kind"] for h in with_res["merges"][0]["hunks"])
    assert kinds == {"RESOLUTION"}


def test_until_excludes_the_merge():
    repo = _repo("smuggle-extra-line")
    report = fidelity.scan(repo, until="HEAD^1")
    assert report["summary"]["merges_scanned"] == 0


def test_since_range_keeps_the_merge():
    repo = _repo("smuggle-extra-line")
    report = fidelity.scan(repo, since="HEAD^2")
    assert report["summary"]["merges_scanned"] == 1


def test_bad_as_of_is_usage_error():
    from mergefidelity.errors import UsageError

    with pytest.raises(UsageError):
        fidelity.scan(_repo("smuggle-extra-line"), as_of="2026/01/01")


# ------------------------------------------------------------------ CLI 契约

def test_cli_fidelity_scan_prints_canonical_json(capsys):
    code = cli.main(["fidelity", "scan", _repo("smuggle-extra-line")])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["summary"]["smuggled"] == 1
    assert canonical.verify_digest(payload) is True


def test_cli_fail_on_smuggled_returns_1(capsys):
    assert cli.main(["fidelity", "scan", _repo("smuggle-extra-line"),
                     "--fail-on=smuggled"]) == 1


def test_cli_fail_on_dropped_returns_1(capsys):
    assert cli.main(["fidelity", "scan", _repo("drop-one-side"),
                     "--fail-on=dropped"]) == 1


def test_cli_fail_on_in_clean_fixture_returns_0(capsys):
    assert cli.main(["fidelity", "scan", _repo("clean-resolution-b"),
                     "--fail-on=any"]) == 0


def test_cli_octopus_exit_code_is_zero(capsys):
    code = cli.main(["fidelity", "scan", _repo("octopus"), "--fail-on=any"])
    assert code == 0
    assert "octopus" in capsys.readouterr().out


def test_cli_custom_driver_exit_code_is_zero(capsys):
    code = cli.main(["fidelity", "scan", _repo("custom-driver"), "--fail-on=any"])
    assert code == 0
    assert "custom_driver" in capsys.readouterr().out


def test_cli_writes_file_and_markdown(tmp_path, capsys):
    out = tmp_path / "report.json"
    code = cli.main(["fidelity", "scan", _repo("smuggle-new-file"), "--out", str(out)])
    assert code == 0
    raw = out.read_bytes()
    assert raw.endswith(b"\n") and b"\r\n" not in raw
    md = tmp_path / "report.md"
    assert cli.main(["fidelity", "scan", _repo("smuggle-new-file"),
                     "--format=md", "--out", str(md)]) == 0
    assert "SMUGGLED" in md.read_text(encoding="utf-8")


def test_cli_rejects_unknown_kind():
    with pytest.raises(SystemExit) as excinfo:
        cli.build_parser().parse_args(["fidelity", "scan", ".", "--show-kind=weird"])
    assert excinfo.value.code == 2
