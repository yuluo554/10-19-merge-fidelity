"""CI workflow 的本地守门。

skill 教训：workflow 里 step 的 `name` 若是不带引号的纯量且值里含 `: `，
GitHub 会直接不建 job（run 显示 failure 而 jobs=0），本地却看不出任何异样。
这里用 `yaml.safe_load` 解析并断言 job/step 数与关键字段形状。
"""

import os

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "ci.yml")


def _load():
    with open(WORKFLOW, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_workflow_parses_and_has_expected_shape():
    doc = _load()
    assert isinstance(doc, dict), "workflow 顶层必须是 mapping"
    # YAML 1.1 会把裸 `on` 解析成布尔 True；两种形态都接受，但必须有且仅有其一
    triggers = doc.get("on", doc.get(True))
    assert triggers is not None, "缺少 on 触发配置"
    jobs = doc.get("jobs")
    assert isinstance(jobs, dict) and set(jobs) == {"test"}
    assert jobs["test"]["runs-on"] == "${{ matrix.os }}"


def test_workflow_matrix_covers_both_axes():
    doc = _load()
    matrix = doc["jobs"]["test"]["strategy"]["matrix"]
    assert matrix["os"] == ["ubuntu-22.04", "windows-latest"]
    assert matrix["python"] == ["3.8", "3.12"]
    assert doc["jobs"]["test"]["strategy"]["fail-fast"] is False


def test_workflow_steps_are_named_and_counted():
    doc = _load()
    steps = doc["jobs"]["test"]["steps"]
    expected = [
        "checkout",
        "setup python ${{ matrix.python }}",
        "install (README path)",
        "pytest",
        "CLI smoke (console script)",
        "CLI smoke (module form)",
    ]
    names = [step.get("name") for step in steps]
    assert names == expected, "step 数量/顺序变化须同步本断言与 README"


def test_workflow_uses_readme_install_path_and_bare_console_script():
    doc = _load()
    runs = [step.get("run", "") for step in doc["jobs"]["test"]["steps"] if "run" in step]
    joined = "\n".join(runs)
    assert 'pip install -e ".[dev]"' in joined, "CI 必须走 README 的安装通路"
    assert "mergefidelity --version" in joined, "必须冒烟裸 console script（不是只有 python -m）"
    assert "python -m mergefidelity --version" in joined, "module 形态也要冒烟"


def test_workflow_sets_utf8_env():
    doc = _load()
    assert doc.get("env", {}).get("PYTHONUTF8") == "1"
