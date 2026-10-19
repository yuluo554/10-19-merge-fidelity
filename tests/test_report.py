"""`report` 模块守门：digest 确定性、`--verify` 篡改检测、parity 未请求不伪造结果。

覆盖（对应 `plan/03` §4.4 与 `plan/HANDOFF-M5.md` §2.1）：

* 同 fixture 两次生成逐字节一致；`TZ=America/New_York` 与 `TZ=Asia/Shanghai` 下 digest 相同；
* `core.quotepath=true/false` 下 digest 相同（路径按原样读出）；
* 篡改一个字节 → 退出码 1 且 `json_path` 指向被改字段；
* 手工删 `digest` → 退出码 2（缺字段 = 坏报告）；
* `parity` 未请求时该节为 `null` 且 `notes` 写 `parity_not_requested`（不伪造空结果）；
* finding ID 与 `canonical.finding_id` 独立复算一致（内容寻址）。
"""

import io
import json
import os
import subprocess
import sys

import pytest

from mergefidelity import canonical, cli, fidelity, gitobj, ledger, report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIDELITY_ROOT = os.path.join(ROOT, "data", "fixtures", "fidelity")
LEDGER_ROOT = os.path.join(ROOT, "data", "fixtures", "ledger")
GENERATOR = os.path.join(ROOT, "tools", "gen_fixtures.py")

sys.path.insert(0, os.path.join(ROOT, "tests"))
import synthrepo  # noqa: E402  (同目录测试助手)

SMUGGLE_REPO = os.path.join(FIDELITY_ROOT, "smuggle-extra-line", "repo")
LEDGER_REPO = os.path.join(LEDGER_ROOT, "then-redone", "repo")


@pytest.fixture(scope="session", autouse=True)
def report_repos():
    """确保用到的两个合成仓库已生成（缺失则现跑生成器）。"""
    needed = [
        (SMUGGLE_REPO, "fidelity"),
        (LEDGER_REPO, "ledger"),
    ]
    for repo, suite in needed:
        if os.path.isdir(repo):
            continue
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", GENERATOR, "--out", "data/fixtures",
             "--suite", suite],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
    return True


def _text(repo, **kwargs):
    return canonical.dumps(canonical.with_digest(report.build_report(repo, **kwargs)))


# ------------------------------------------------------------------ 确定性

def test_same_input_twice_is_byte_identical():
    first = _text(SMUGGLE_REPO)
    second = _text(SMUGGLE_REPO)
    assert first == second


@pytest.mark.parametrize("timezone", ["America/New_York", "Asia/Shanghai"])
def test_digest_is_timezone_independent(timezone):
    """`as_of` 来自提交时间（UTC），因此换时区不得改变 digest。"""
    env = dict(os.environ)
    env["TZ"] = timezone
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c",
         "import sys;sys.path.insert(0,'src');"
         "from mergefidelity import report,canonical;"
         "print(canonical.digest_of(report.build_report(%r)))" % SMUGGLE_REPO],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
    other = proc.stdout.decode("utf-8").strip()
    assert other == canonical.digest_of(report.build_report(SMUGGLE_REPO))


def test_digest_is_quotepath_independent(monkeypatch):
    """`core.quotepath=true` 下路径仍按 UTF-8 读出 → digest 不变。

    实测依据：`gitobj.ls_tree` / `blob_map` 用 `-z`，路径不受 `core.quotePath` 影响。
    变异验证：把 `-z` 去掉，本测试必须变红。
    """
    baseline = canonical.digest_of(report.build_report(SMUGGLE_REPO))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.quotepath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    assert canonical.digest_of(report.build_report(SMUGGLE_REPO)) == baseline


def test_report_has_no_forbidden_header_fields():
    """报告头**禁止**出现：扫描时刻、绝对路径、主机名、用户名、locale、Python 版本。"""
    payload = report.build_report(SMUGGLE_REPO)
    text = canonical.dumps(payload)
    assert os.path.abspath(SMUGGLE_REPO).replace("\\", "/") not in text
    assert "C:" not in text and "/Users/" not in text and "/tmp/" not in text
    assert "python_version" not in text and "scan_time" not in text
    assert "hostname" not in text and "locale" not in text
    # 报告头字段写死且齐备
    for key in ("tool_version", "git_version", "object_format", "gitattributes_oid",
                "config_overrides", "range", "as_of", "findings_digest_algorithm"):
        assert key in payload, key
    assert payload["findings_digest_algorithm"] == "sha256"


def test_as_of_falls_back_to_head_on_empty_input(tmp_path):
    """空输入（无 merge、无 revert）时 `as_of` 必须回落到 HEAD 的提交时间。

    回归靶子（M5 实测抓出）：初版用 `max([] or [0])` → 空输入落成 **1970-01-01**，
    与同一仓库的 `fidelity` / `ledger` 给出不同 `as_of`（它们都回落 HEAD）。
    变异验证：把回落去掉（`stamp = max(values) if values else 0`）→ 本测试变红。
    """
    repo = str(tmp_path / "repo")
    synthrepo.init_repo(repo)
    synthrepo.commit(repo, "only linear commit", {"src/synthapp/core.py": ["a", "b"]})

    fidelity_report = fidelity.scan(repo)
    ledger_report = ledger.ledger_scan(repo)
    payload = report.build_report(repo)
    assert fidelity_report["merges"] == [] and ledger_report["entries"] == []
    assert payload["as_of"] == fidelity_report["as_of"] == ledger_report["as_of"]
    assert payload["as_of"] != "1970-01-01"


def test_as_of_agrees_with_every_input_module(tmp_path):
    """`report` 的 `as_of` 必须等于三源 `as_of` 的最大值（口径一致，不另算一份时间戳）。"""
    payload = report.build_report(SMUGGLE_REPO, parity_from="feature/synth-a",
                                  parity_to="main")
    sources = [payload["fidelity"]["as_of"], payload["ledger"]["as_of"],
               payload["parity"]["as_of"]]
    assert payload["as_of"] == max(sources)


def test_as_of_comes_from_commit_times_not_the_clock():
    payload = report.build_report(SMUGGLE_REPO)
    assert payload["as_of"] == "2026-01-01"
    assert report.build_report(LEDGER_REPO)["as_of"] == "2026-01-01"


# ------------------------------------------------------------------ findings

def test_findings_ids_are_content_addressed():
    """finding ID 与 `canonical.finding_id` 独立复算一致，且与提交时间无关。"""
    payload = report.build_report(SMUGGLE_REPO)
    assert payload["findings"], "该 fixture 至少应有一条 SMUGGLED finding"
    for finding in payload["findings"]:
        expected = canonical.finding_id(finding["commit_oid"], finding["path"],
                                        finding["old_range"], finding["new_range"],
                                        finding["kind"])
        assert finding["id"] == expected
    kinds = sorted(f["kind"] for f in payload["findings"])
    assert kinds == ["SMUGGLED"]


def test_findings_cover_fidelity_and_ledger():
    """`fidelity` 与 `ledger` **恒计入**：同一仓库的 revert 账目也进 findings。"""
    payload = report.build_report(LEDGER_REPO)
    kinds = [f["kind"] for f in payload["findings"]]
    assert kinds == ["REVERTED_THEN_REDONE"]
    assert payload["ledger"]["counts"]["then_redone"] == 1


def test_findings_are_sorted_by_declared_key():
    payload = report.build_report(LEDGER_REPO)
    keys = [(f["commit_time"], f["commit_oid"], f["path"], f["old_range"])
            for f in payload["findings"]]
    assert keys == sorted(keys)


def test_parity_section_is_null_when_not_requested():
    """未给 `--parity-from/--parity-to` → 该节 `null` + `notes` 写明未请求（**不伪造空结果**）。"""
    payload = report.build_report(SMUGGLE_REPO)
    assert payload["parity"] is None
    assert payload["parity_requested"] is False
    assert "parity_not_requested" in payload["notes"]


def test_parity_section_is_populated_when_requested():
    payload = report.build_report(SMUGGLE_REPO, parity_from="feature/synth-a", parity_to="main")
    assert payload["parity_requested"] is True
    assert payload["notes"] == []
    assert payload["parity"]["from"] == "feature/synth-a"
    assert payload["parity"]["to"] == "main"
    assert payload["parity"]["candidates"] >= 1
    # parity 的 MISSING/MODIFIED 也进 findings（`PARITY_*` kind）
    kinds = set(f["kind"] for f in payload["findings"])
    assert kinds & {"PARITY_MISSING", "PARITY_MODIFIED"}


def test_parity_refs_must_be_given_as_a_pair():
    from mergefidelity.errors import UsageError

    with pytest.raises(UsageError):
        report.build_report(SMUGGLE_REPO, parity_from="feature/synth-a")
    with pytest.raises(UsageError):
        report.build_report(SMUGGLE_REPO, parity_to="main")


# ------------------------------------------------------------------ --verify

def test_verify_accepts_a_faithful_report(tmp_path, capsys):
    path = tmp_path / "report.json"
    code = cli.main(["report", SMUGGLE_REPO, "--out", str(path)])
    assert code == 0
    code = cli.main(["report", SMUGGLE_REPO, "--verify", str(path)])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.startswith("verified: ")
    assert "findings" in captured.out


def test_verify_detects_a_single_byte_tamper(tmp_path, capsys):
    """改一个字节 → 退出码 1，且 `json_path` 指向被改字段。"""
    path = tmp_path / "report.json"
    assert cli.main(["report", SMUGGLE_REPO, "--out", str(path)]) == 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["findings"][0]["kind"] = "TAMPERED"
    path.write_text(canonical.dumps(payload), encoding="utf-8")

    code = cli.main(["report", SMUGGLE_REPO, "--verify", str(path)])
    captured = capsys.readouterr()
    assert code == 1
    difference = json.loads(captured.out)["difference"]
    assert difference["json_path"] == "findings[0].kind"
    assert difference["expected"] == "SMUGGLED"
    assert difference["actual"] == "TAMPERED"


def test_verify_detects_a_tampered_nested_field(tmp_path, capsys):
    """深一层也要定位到（`merges[0].hunks[0].new_range` 形态）。"""
    path = tmp_path / "report.json"
    assert cli.main(["report", SMUGGLE_REPO, "--out", str(path)]) == 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["fidelity"]["merges"][0]["hunks"][0]["new_range"] = "99,99"
    path.write_text(canonical.dumps(payload), encoding="utf-8")

    code = cli.main(["report", SMUGGLE_REPO, "--verify", str(path)])
    captured = capsys.readouterr()
    assert code == 1
    difference = json.loads(captured.out)["difference"]
    assert difference["json_path"] == "fidelity.merges[0].hunks[0].new_range"
    assert difference["actual"] == "99,99"


def test_verify_reports_digest_mismatch_before_content(tmp_path, capsys):
    """只改 `digest` 自身 → 定位到 `digest`（先做 digest 自校验）。"""
    path = tmp_path / "report.json"
    assert cli.main(["report", SMUGGLE_REPO, "--out", str(path)]) == 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["digest"] = "0" * 64
    path.write_text(canonical.dumps(payload), encoding="utf-8")

    code = cli.main(["report", SMUGGLE_REPO, "--verify", str(path)])
    captured = capsys.readouterr()
    assert code == 1
    body = json.loads(captured.out)
    assert body["status"] == "digest_mismatch"
    assert body["difference"]["json_path"] == "digest"


def test_verify_rejects_a_report_without_digest(tmp_path, capsys):
    """手工删掉 `digest` 字段 → 退出码 2（缺字段 = 坏报告，不是"内容不一致"）。"""
    path = tmp_path / "report.json"
    assert cli.main(["report", SMUGGLE_REPO, "--out", str(path)]) == 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["digest"]
    path.write_text(canonical.dumps(payload), encoding="utf-8")

    code = cli.main(["report", SMUGGLE_REPO, "--verify", str(path)])
    captured = capsys.readouterr()
    assert code == 2
    assert "digest" in captured.err


def test_verify_rejects_bad_json(tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text("{not json", encoding="utf-8")
    code = cli.main(["report", SMUGGLE_REPO, "--verify", str(path)])
    assert code == 2
    assert "JSON" in capsys.readouterr().err


def test_verify_rejects_a_missing_file(capsys):
    code = cli.main(["report", SMUGGLE_REPO, "--verify", "no-such-report.json"])
    assert code == 2
    assert "无法读取报告文件" in capsys.readouterr().err


# ------------------------------------------------------------------ CLI 契约

def test_cli_report_prints_canonical_json_with_digest(capsys):
    code = cli.main(["report", SMUGGLE_REPO])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert canonical.verify_digest(payload) is True
    assert payload["findings"][0]["id"]


def test_cli_report_markdown_and_out(tmp_path, capsys):
    md = tmp_path / "report.md"
    code = cli.main(["report", SMUGGLE_REPO, "--format=md", "--out", str(md)])
    assert code == 0
    text = md.read_text(encoding="utf-8")
    assert "SMUGGLED" in text and "审计报告" in text
    raw = md.read_bytes()
    assert raw.endswith(b"\n") and b"\r\n" not in raw


def test_cli_report_bad_as_of_is_usage_error(capsys):
    code = cli.main(["report", SMUGGLE_REPO, "--as-of=2026/01/01"])
    assert code == 2
    assert "--as-of" in capsys.readouterr().err


def test_cli_report_bad_range_is_usage_error(capsys):
    code = cli.main(["report", SMUGGLE_REPO, "--range=no-such-ref..HEAD"])
    assert code == 2
    assert "不是有效引用" in capsys.readouterr().err


# ------------------------------------------------------------------ 报告样例

def test_repo_report_sample_matches_current_tool(tmp_path):
    """入仓的 `docs/report-sample.json` 必须能被当前构建 `--verify` 通过。

    样例是对**同一个合成仓库**生成的报告；fixture 仓库可重建（OID 固定），
    因此样例不会随时间漂移。样例缺失时本测试自动跳过（发布前由 CI 断言存在）。
    """
    sample = os.path.join(ROOT, "docs", "report-sample.json")
    if not os.path.isfile(sample):
        pytest.skip("docs/report-sample.json 尚未生成")
    code = cli.main(["report", SMUGGLE_REPO, "--verify", sample])
    assert code == 0
