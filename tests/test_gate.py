"""`gate` 模块守门：四组退出码语义 + 受限 TOML 子集 + 零副作用。

覆盖（对应 `plan/03` §5.4 与 `plan/HANDOFF-M5.md` §2.2）：

* 新增 1 个夹带 → 退出码 1 且**只报新增**；
* 旧账未过期 → 退出码 0 且 `baselined == 1`；
* `expires` 改到过去 → 退出码 1 且 `expired == 1`；
* 基线语法错误 / 数组 / 嵌套表 / 多行字符串 / 非字符串值 → 退出码 2 + **行号** + **不写任何产物**；
* 基线指向不存在 finding → `stale == 1` 且退出码仍 0；
* 同一输入两次运行退出码一致。
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

from mergefidelity import canonical, cli, fidelity, gate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_ROOT = os.path.join(ROOT, "data", "fixtures", "fidelity")
GENERATOR = os.path.join(ROOT, "tools", "gen_fixtures.py")

SMUGGLE_REPO = os.path.join(FIXTURE_ROOT, "smuggle-extra-line", "repo")
CLEAN_REPO = os.path.join(FIXTURE_ROOT, "octopus", "repo")   # 无任何 hunk → 空 findings

sys.path.insert(0, os.path.join(ROOT, "tests"))
import synthrepo  # noqa: E402  (同目录测试助手)


@pytest.fixture(scope="session", autouse=True)
def gate_repos():
    """确保用到的两个合成仓库已生成（缺失则现跑生成器，只生成 fidelity 套件）。"""
    if not os.path.isdir(SMUGGLE_REPO):
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", GENERATOR, "--out", "data/fixtures",
             "--suite", "fidelity"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
    return True


# ------------------------------------------------------------------ 构造夹具

@pytest.fixture(scope="session")
def two_smuggles(tmp_path_factory):
    """合成仓库：一个 merge 里**夹带 2 处**（两个不同路径）——用于"只报新增"。

    `smuggle-extra-line` 只有一个 finding，没法验证"新增 1 个"；这里现造一个 2 finding
    仓库，把其中一个写进基线，断言新增恰好是另一个。
    """
    root = str(tmp_path_factory.mktemp("gate-repo"))
    repo = os.path.join(root, "repo")
    synthrepo.init_repo(repo)
    synthrepo.commit(repo, "seed",
                     {"src/synthapp/core.py": ["a", "b", "c", "d", "e"],
                      "docs/notes.md": ["n1", "n2"]})
    synthrepo.git(repo, "checkout", "-q", "-b", "feature")
    synthrepo.commit(repo, "feature edit", {"src/synthapp/core.py": ["a", "B1", "c", "d", "e"]})
    synthrepo.git(repo, "checkout", "-q", "main")
    synthrepo.commit(repo, "main edit", {"src/synthapp/core.py": ["a", "b", "c", "D1", "e"]})
    synthrepo.git(repo, "merge", "--no-commit", "feature", check=False)
    synthrepo.write(repo, "src/synthapp/core.py", ["a", "B1", "c", "D1", "e", "SMUGGLED1"])
    synthrepo.write(repo, "docs/notes.md", ["n1", "n2", "SMUGGLED2"])
    synthrepo.git(repo, "add", "-A")
    synthrepo.git(repo, "commit", "-q", "-m", "merge feature (with smuggled extras)")

    report = fidelity.scan(repo)
    findings = fidelity.findings_of(report)
    assert len(findings) == 2, "本夹具必须恰好夹带 2 处（否则本测试没在测东西）"
    by_path = dict((f["path"], f["id"]) for f in findings)
    yield {"repo": repo, "ids": by_path, "as_of": report["as_of"]}


def _baseline_file(tmp_path, entries, name="audit-baseline.toml"):
    lines = []
    for entry in entries:
        lines += ['[[finding]]',
                  'id = "%s"' % entry["id"],
                  'expires = "%s"' % entry["expires"],
                  'justification = "%s"' % entry["justification"]]
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _all_ids(repo):
    return [f["id"] for f in fidelity.findings_of(fidelity.scan(repo))]


# ------------------------------------------------------------------ 四组退出码

def test_new_finding_fails_and_reports_only_the_new_one(two_smuggles, tmp_path, capsys):
    """新增 1 个夹带 → 退出码 1，且 `new` 里**只有**那一个（另一个在基线内不失败）。"""
    ids = two_smuggles["ids"]
    baselined_id = ids["src/synthapp/core.py"]
    baseline = _baseline_file(tmp_path, [{
        "id": baselined_id, "expires": "2099-12-31", "justification": "已知机械合并差异，见 #12",
    }])

    code = cli.main(["gate", two_smuggles["repo"], "--baseline", baseline])
    captured = capsys.readouterr()
    assert code == 1
    payload = json.loads(captured.out)
    assert payload["counts"] == {"baselined": 1, "expired": 0, "new": 1, "stale": 0}
    assert [f["id"] for f in payload["new"]] == [ids["docs/notes.md"]]
    assert canonical.verify_digest(payload) is True


def test_baselined_old_debt_passes(two_smuggles, tmp_path, capsys):
    """两处夹带都写进基线且未过期 → 退出码 0 且 `baselined == 2`。"""
    baseline = _baseline_file(tmp_path, [
        {"id": finding_id, "expires": "2099-12-31", "justification": "已知，见 #12"}
        for finding_id in two_smuggles["ids"].values()
    ])
    code = cli.main(["gate", two_smuggles["repo"], "--baseline", baseline])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["counts"] == {"baselined": 2, "expired": 0, "new": 0, "stale": 0}


def test_expired_baseline_fails_again(two_smuggles, tmp_path, capsys):
    """`expires` 改到过去 → 退出码 1 且 `expired == 1`（旧账自动重新报警）。"""
    ids = two_smuggles["ids"]
    baseline = _baseline_file(tmp_path, [
        {"id": ids["src/synthapp/core.py"], "expires": "2000-01-01",
         "justification": "早就该修了"},
        {"id": ids["docs/notes.md"], "expires": "2099-12-31", "justification": "已知"},
    ])
    code = cli.main(["gate", two_smuggles["repo"], "--baseline", baseline])
    captured = capsys.readouterr()
    assert code == 1
    payload = json.loads(captured.out)
    assert payload["counts"] == {"baselined": 1, "expired": 1, "new": 0, "stale": 0}
    assert payload["expired"][0]["finding"]["id"] == ids["src/synthapp/core.py"]
    assert payload["expired"][0]["expires"] == "2000-01-01"


def test_expires_boundary_is_inclusive_on_as_of(two_smuggles, tmp_path):
    """`as_of <= expires` 算未过期：边界当天仍不失败（口径写进 data/README §4.7）。"""
    as_of = two_smuggles["as_of"]
    baseline = _baseline_file(tmp_path, [
        {"id": finding_id, "expires": as_of, "justification": "边界当天"}
        for finding_id in two_smuggles["ids"].values()
    ])
    doc, code = gate.gate_scan(two_smuggles["repo"], gate.read_baseline(baseline))
    assert code == 0
    assert doc["counts"]["baselined"] == 2


def test_stale_entry_only_warns_and_still_passes(two_smuggles, tmp_path, capsys):
    """基线指向不存在的 finding → `stale == 1`，退出码仍 0（只提示不失败）。"""
    ids = two_smuggles["ids"]
    baseline = _baseline_file(tmp_path, [
        {"id": finding_id, "expires": "2099-12-31", "justification": "已知"}
        for finding_id in ids.values()
    ] + [{"id": "f" * 40, "expires": "2099-12-31", "justification": "早已修复的旧账"}])

    code = cli.main(["gate", two_smuggles["repo"], "--baseline", baseline])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["counts"] == {"baselined": 2, "expired": 0, "new": 0, "stale": 1}
    assert payload["stale"][0]["id"] == "f" * 40


def test_clean_repo_with_stale_only_passes():
    """无 finding 的仓库 + 只含幽灵条目的基线 → `stale` 有值、退出码 0。"""
    baseline = gate.parse_baseline(
        '[[finding]]\nid = "%s"\nexpires = "2099-12-31"\njustification = "ghost"\n' % ("0" * 40))
    document, code = gate.gate_scan(CLEAN_REPO, baseline)
    assert code == 0
    assert document["counts"] == {"baselined": 0, "expired": 0, "new": 0, "stale": 1}


def test_fail_on_filters_which_new_kinds_fail(two_smuggles, tmp_path):
    """`--fail-on=dropped` 下，新增的 SMUGGLED 不计失败（门禁只管它管辖的那一类）。"""
    baseline = _baseline_file(tmp_path, [{"id": "0" * 40, "expires": "2099-12-31",
                                          "justification": "ghost"}])
    document, code = gate.gate_scan(two_smuggles["repo"], gate.read_baseline(baseline),
                                    fail_on="dropped")
    assert code == 0, "SMUGGLED 新增不在 `--fail-on=dropped` 的管辖范围"
    assert document["counts"]["new"] == 0
    assert document["counts"]["stale"] == 1

    # 同一输入改用 --fail-on=any → 新增计入失败
    document, code = gate.gate_scan(two_smuggles["repo"], gate.read_baseline(baseline),
                                    fail_on="any")
    assert code == 1
    assert document["counts"]["new"] == 2


def test_baseline_coverage_is_not_filtered_by_fail_on(two_smuggles, tmp_path):
    """**门禁全量收集两类，`--fail-on` 只过滤 `new`**——变异验证的靶子。

    若把"扫描时只收 `--fail-on` 那一类"当成优化（看起来很省），`--fail-on=dropped` 下
    被基线覆盖的 SMUGGLED 就会因为"没扫到"而变成 `stale`——一条已登记在案的旧账被
    误报成"已修复"。本测试断言那条仍是 `baselined`。
    """
    smuggled_id = two_smuggles["ids"]["src/synthapp/core.py"]
    baseline = _baseline_file(tmp_path, [{
        "id": smuggled_id, "expires": "2099-12-31", "justification": "已知夹带",
    }])
    document, code = gate.gate_scan(two_smuggles["repo"], gate.read_baseline(baseline),
                                    fail_on="dropped")
    assert code == 0
    assert document["counts"]["baselined"] == 1, "SMUGGLED 基线条目必须仍被扫到并命中"
    assert document["counts"]["stale"] == 0, "不得把已覆盖的旧账误报成 stale"
    assert [item["finding"]["id"] for item in document["baselined"]] == [smuggled_id]


def test_same_input_twice_gives_the_same_exit_code(two_smuggles, tmp_path):
    """同一输入两次运行退出码一致（基线解析纯数据、不读时钟）。"""
    baseline = _baseline_file(tmp_path, [{
        "id": two_smuggles["ids"]["src/synthapp/core.py"],
        "expires": "2099-12-31", "justification": "已知",
    }])
    codes = [gate.gate_scan(two_smuggles["repo"], gate.read_baseline(baseline))[1]
             for _ in range(2)]
    assert codes == [1, 1]


# ------------------------------------------------------------------ 受限 TOML 子集

def test_comments_and_blank_lines_are_accepted():
    text = ("# 顶部注释\n"
            "\n"
            "[[finding]]\n"
            'id = "%s"\n' % ("a" * 40) +
            "# 行内注释\n"
            'expires = "2099-12-31"  # 尾注释\n'
            'justification = "已知的机械合并上下文差异"\n')
    entries = gate.parse_baseline(text)
    assert len(entries) == 1
    assert entries[0]["id"] == "a" * 40
    assert entries[0]["justification"] == "已知的机械合并上下文差异"


@pytest.mark.parametrize("text,needle", [
    ('[[finding]]\nid = "x"\nexpires = "2099-12-31"\n', "缺少 `justification`"),
    ('[[finding]]\nid = "x"\njustification = "j"\n', "缺少 `expires`"),
    ('[[finding]]\nexpires = "2099-12-31"\njustification = "j"\n', "缺少 `id`"),
    ('[[finding]]\nid = "x"\nexpires = "2026-13-01"\njustification = "j"\n', "不是合法日期"),
    ('[[finding]]\nid = "x"\nexpires = "2026/01/01"\njustification = "j"\n', "YYYY-MM-DD"),
    ('[[finding]]\nid = "x"\nexpires = "2099-12-31"\njustification = ""\n', "不能为空"),
    ('[[finding]]\nid = "x"\nexpires = "2099-12-31"\njustification = "j"\n'
     '[[finding]]\nid = "x"\nexpires = "2099-12-31"\njustification = "j"\n', "重复"),
    ('id = "x"\nexpires = "2099-12-31"\njustification = "j"\n', "不在任何 `[[finding]]`"),
    ('this is not toml\n', "无法解析"),
])
def test_baseline_syntax_errors_are_usage_errors(text, needle):
    from mergefidelity.errors import UsageError

    with pytest.raises(UsageError) as excinfo:
        gate.parse_baseline(text)
    assert needle in str(excinfo.value)


@pytest.mark.parametrize("text,line_no", [
    ('[[finding]]\nid = "x"\nexpires = ["2099-12-31"]\njustification = "j"\n', 3),
    ('[[finding]]\nid = "x"\nexpires = "2099-12-31"\njustification = "j"\n'
     '[[nested]]\nid = "y"\n', 5),
    ('[[finding]]\nid = "x"\nexpires = "2099-12-31"\n'
     'justification = """multi\nline"""\n', 4),
        ('[[finding]]\nid = "x"\nexpires = "2099-12-31"\n'
         'justification = { why = "k" }\n', 4),
    ('[[finding]]\nid = "x"\nexpires = 20991231\njustification = "j"\n', 3),
    ('[[finding]]\nid = "x"\nexpires = "2099-12-31"\nunknown = "j"\n', 4),
])
def test_unsupported_toml_shapes_are_flagged_with_a_line_number(text, line_no):
    """数组/嵌套表/多行字符串/非字符串值 → `toml_unsupported` + **明示行号**。"""
    from mergefidelity.errors import UsageError

    with pytest.raises(UsageError) as excinfo:
        gate.parse_baseline(text)
    message = str(excinfo.value)
    assert "toml_unsupported" in message
    assert "第 %d 行" % line_no in message


def test_empty_baseline_is_rejected():
    """空基线等于没有门禁 → 归用法错误，不静默放行。"""
    from mergefidelity.errors import UsageError

    with pytest.raises(UsageError):
        gate.parse_baseline("# 只有注释\n\n")


# ------------------------------------------------------------------ 零副作用与 CLI

def test_bad_baseline_writes_nothing(tmp_path, capsys):
    """基线语法错误 → 退出码 2 + 行号 + **不写任何产物**。"""
    out = tmp_path / "gate-report.json"
    bad = tmp_path / "bad.toml"
    bad.write_text('[[finding]]\nid = "x"\nexpires = ["2099-12-31"]\njustification = "j"\n',
                   encoding="utf-8")

    code = cli.main(["gate", SMUGGLE_REPO, "--baseline", str(bad), "--out", str(out)])
    captured = capsys.readouterr()
    assert code == 2
    assert "toml_unsupported" in captured.err and "第 3 行" in captured.err
    assert not out.exists(), "基线坏掉时不得留下任何产物（零副作用）"
    assert captured.out == ""


def test_missing_baseline_file_is_usage_error(capsys):
    code = cli.main(["gate", SMUGGLE_REPO, "--baseline", "no-such-baseline.toml"])
    captured = capsys.readouterr()
    assert code == 2
    assert "无法读取基线文件" in captured.err
    assert captured.out == ""


def test_bad_as_of_is_usage_error(tmp_path, capsys):
    baseline = _baseline_file(tmp_path, [{"id": "a" * 40, "expires": "2099-12-31",
                                          "justification": "j"}])
    code = cli.main(["gate", SMUGGLE_REPO, "--baseline", baseline, "--as-of=2026/01/01"])
    assert code == 2
    assert "--as-of" in capsys.readouterr().err


def test_gate_markdown_renders_all_buckets(tmp_path, capsys):
    ids = _all_ids(SMUGGLE_REPO)
    baseline = _baseline_file(tmp_path, [
        {"id": ids[0], "expires": "2099-12-31", "justification": "已知"},
        {"id": "e" * 40, "expires": "2099-12-31", "justification": "幽灵"},
    ])
    md = tmp_path / "gate.md"
    code = cli.main(["gate", SMUGGLE_REPO, "--baseline", baseline,
                     "--format=md", "--out", str(md)])
    assert code == 0
    text = md.read_text(encoding="utf-8")
    assert "CI 门禁" in text and "基线内（不失败）" in text and "失效条目（只提示）" in text
    assert md.read_bytes().endswith(b"\n")


def test_gate_report_has_no_absolute_path(two_smuggles, tmp_path):
    baseline = _baseline_file(tmp_path, [
        {"id": finding_id, "expires": "2099-12-31", "justification": "已知"}
        for finding_id in two_smuggles["ids"].values()
    ])
    document, _code = gate.gate_scan(two_smuggles["repo"], gate.read_baseline(baseline))
    text = canonical.dumps(canonical.with_digest(document))
    assert os.path.abspath(two_smuggles["repo"]).replace("\\", "/") not in text
    assert "C:" not in text and "/tmp/" not in text


def test_since_limits_the_scan(two_smuggles, tmp_path):
    """`--since` 收窄到 merge 之前的提交 → 增量里没有 merge → 新增为空。"""
    baseline = _baseline_file(tmp_path, [{"id": "0" * 40, "expires": "2099-12-31",
                                          "justification": "ghost"}])
    document, code = gate.gate_scan(two_smuggles["repo"], gate.read_baseline(baseline),
                                    since="HEAD")
    assert code == 0
    assert document["counts"]["new"] == 0
    assert document["scan"]["merges_scanned"] == 0


def test_bench_gate_tool_runs_and_writes_json(tmp_path):
    out = tmp_path / "gate-bench.json"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "tools", "bench_gate.py"),
         "--out", str(out), "--only", "smuggle-extra-line", "--repeats", "1"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["git_version"].startswith("git version")
    assert payload["fixtures"][0]["fixture"] == "smuggle-extra-line"
    assert payload["fixtures"][0]["scanned_findings"] >= 1


def test_repo_baseline_sample_is_accepted_by_current_tool(tmp_path):
    """入仓的 `audit-baseline.toml` 必须能被当前构建解析并跑出稳定退出码。"""
    sample = os.path.join(ROOT, "audit-baseline.toml")
    if not os.path.isfile(sample):
        pytest.skip("audit-baseline.toml 尚未生成")
    entries = gate.read_baseline(sample)
    assert entries, "样例基线不能是空的"
    document, code = gate.gate_scan(SMUGGLE_REPO, entries)
    assert code in (0, 1)
    assert document["counts"]["stale"] + document["counts"]["baselined"] + \
        document["counts"]["expired"] == len(entries)
