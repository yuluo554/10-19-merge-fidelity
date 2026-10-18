# HANDOFF-M1 · 下一棒：数据先行（fixture 生成器与 golden）

> 本文件由 M0 收尾时写入。上游：`plan/05-里程碑.md` 的 M1 行。
> 用法：新对话 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M1.md" 继续完成任务`。

## 1. 当前进度与证据（M0 已完成）

| 项 | 状态 | 证据 |
|---|---|---|
| 计划文档 00–06 | ✅ | `plan/00`–`06` 六份 + `data/README.md`（口径权威） |
| 可安装骨架 | ✅ | `pyproject.toml`（`[project.scripts] mergefidelity`）；干净 venv `pip install -e .` 成功，裸 `mergefidelity --version` 输出 `mergefidelity 0.1.0.dev0` |
| 共享层实现 | ✅ | `src/mergefidelity/{errors,canonical,diffparse,gitobj,cli,__main__}.py` 真实实现（非空壳） |
| 五子命令注册 | ✅ | `fidelity scan` / `parity` / `ledger` / `report` / `gate` 全部 `--help` 可跑 |
| 骨架态未实现拦截 | ✅ | 五模块 `run()` 抛 `NotReadyError` → 退出码 2 + 中文提示；**不输出伪造空 JSON**（测试 `test_not_ready_modules_return_usage_with_chinese_hint`） |
| 退出码契约锁进测试 | ✅ | `tests/test_cli.py`：0/2 分支 + `GitEnvError→3` 映射 |
| 双解释器测试 | ✅ | `py -3.8 -m pytest -q` = 67 passed；`py -3.12 -m pytest -q` = 67 passed |
| CI workflow | ✅（未推送） | `.github/workflows/ci.yml`，四矩阵 `{ubuntu-22.04, windows-latest} × {3.8, 3.12}`；**未接远端，CI 待首推验证** |
| workflow 本地解析门 | ✅ | `tests/test_workflow.py` 用 `yaml.safe_load` 断言 job/step 数与顺序 |
| 许可证 | ✅ | `LICENSE`（MIT）+ `pyproject` 一致 |

**本机的"本地等价校验"清单（替代 CI 的部分，逐条实跑过）**：`py -3.8 -m pytest -q`、
`py -3.12 -m pytest -q`、干净 venv（`build/venv38`）`pip install -e ".[dev]"` 后 `pytest -q`、
裸 console script 与 `python -m mergefidelity` 双形态冒烟、`yaml.safe_load` 解析 workflow。
**不可本机实跑的通路**：Linux/macOS 行为差异、GitHub runner 的编码与路径形态——**待首推验证**。

## 2. 下一棒待办（M1 = 数据先行）

1. 写 `tools/gen_fixtures.py`：按 `plan/04-数据计划.md` §2 的确定性纪律生成
   **10 个 fidelity + 6 个 parity + 3 个 ledger** 合成仓库与 `expect.json`。
   - `--out` 指定输出目录；`--check` 重生成到临时目录与冻结产物比对（退出码 0/1/2）。
   - 生成器**不依赖** `mergefidelity` 包（真值独立于被测实现）。
   - 生成到 `data/fixtures/_repos/`（已在 `.gitignore` 排除 `data/fixtures/**/repo/` 与 `**/.git/`）
     或系统临时目录；**仓库本体不入仓**，入仓的是生成器 + `expect.json` + 每例 `README.md` + `manifest.json`。
2. 写 `tests/test_gen_fixtures.py`：`--check` 位级一致（两层：冻结产物形态 + 重生成逐字节/OID 一致）。
3. 补齐 `plan/00` 的承诺-证据台账中"合成 fixture 可重建"一行为 ✅，并回写 M1 状态。
4. 收尾：DoD 验证 → 回写 `plan/00`/`plan/05` → 写 `plan/HANDOFF-M2.md` → commit。

**M1 的验收（`plan/05`）**：`py tools/gen_fixtures.py --check` 退出码 0；
反向样例（f08/f09 正确解冲突）断言"不报 SMUGGLED/DROPPED"；两台机器重建 OID 一致。

## 3. 既定口径清单（K 编号 —— 动了会打挂测试）

| # | 口径 | 落点 |
|---|---|---|
| K1 | 退出码 0/1/2/3 语义（0 无发现 / 1 有需失败的发现 / 2 用法 / 3 环境） | `errors.py`、`cli.main`、`tests/test_cli.py` |
| K2 | 规范 JSON 参数冻结：`ensure_ascii=False` + `sort_keys=True` + `separators=(",",":")` + 结尾一个 `\n` + UTF-8 无 BOM | `canonical.CANONICAL_KWARGS`、`tests/test_canonical.py` |
| K3 | **唯一写盘出口** `canonical.write_atomic`（临时文件 + `os.replace`，失败不留残件）；各模块不得自行 `json.dump` | `tests/test_canonical.py` |
| K4 | finding ID = `sha1(merge_oid ‖ path ‖ old_range ‖ new_range ‖ kind)`，分隔符固定 `\x1f` | `data/README.md` §4.5、`canonical.finding_id` |
| K5 | hunk 行号 **0 基**：`count>0` 时 `start = git 行号-1`；`count==0` 时取 git 行号 | `data/README.md` §4.5、`diffparse._parse_hunk_header` |
| K6 | `merge-tree` 必须走 `gitobj.TempObjectDir`（临时对象目录 + alternates），**且对象目录要预先存在** | `gitobj.merge_tree`、`tests/test_gitobj.py::test_merge_tree_does_not_write_repository_objects` |
| K7 | 只读纪律：gitobj 不调用写引用/写工作树的命令；`parity` 的临时 worktree 落系统临时目录且**成功/异常两条路径都清理** | `gitobj.temporary_worktree`、`tests/test_gitobj.py` |
| K8 | 子进程一律**显式** `encoding="utf-8"`（禁 `text=True`，它走 locale） | `gitobj._decode`/`run_git` |
| K9 | 报告不写扫描时刻/绝对路径/主机名/用户名；`as_of` 只来自 `--as-of` 或提交时间 | `plan/02` §四、`plan/03` §4.2 |
| K10 | README ↔ CLI ↔ pyproject 三面对账门（子命令名、extras、包布局、测试依赖落点） | `tests/test_readme_gate.py` |
| K11 | workflow 本地 `yaml.safe_load` 解析门；step 名含 `: ` 必须加引号 | `tests/test_workflow.py` |
| K12 | **骨架态登记**：五模块抛 `NotReadyError`；每落地一个模块**同轮**从该测试与模块里删掉 | `tests/test_readme_gate.py::test_skeleton_not_ready_registry_is_explicit` |
| K13 | 合成 fixture 仓库本体是生成物、**不入仓**；生成器与 golden 入仓 | `.gitignore`、`plan/04` |
| K14 | git 版本门槛：`--remerge-diff` ≥2.36、`merge-tree --write-tree` ≥2.38，低于门槛退出码 3（不降级） | `gitobj.require_version` |
| K15 | octopus 判定用**父提交数 >2**，不解析 stderr | `plan/02` §3.1、M2 实现 |

## 4. 本机环境坑（2026-10-18 实测，引用前先复测）

- `py -0p` → **3.8.8-64** 与 **3.12.10** 两条通道都在；`python` 是商店占位符，一律用 `py`。
- pytest：3.8 通道 **7.4.4**、3.12 通道 **8.4.2**；PyYAML **6.0.3**。
- **`py -3.8 -m venv` 产出的 venv 自带 pip 20.2.3 → `pip install -e .` 报
  "editable mode currently requires a setup.py based build"**（PEP 660 要 pip ≥21.3）。
  处置：先 `python -m pip install -U pip`（**CI 的第一条 pip 步骤正是干这个**），升级到 pip 25.0.1 后 `-e .` 成功。
  setuptools 在 3.8 通道可用版本为 **75.3.4**。
- pip 走注册表系统代理会 `ProxyError`：`NO_PROXY="*" no_proxy="*" ... -i https://pypi.tuna.tsinghua.edu.cn/simple`。
- Git Bash 控制台是 cp936：跑脚本加 `py -X utf8`；CI 侧靠 workflow 的 `PYTHONUTF8=1`。
- 本机 git **2.54.0.windows.1**；`git worktree list` 报长路径形态（CI 上可能报 8.3 短名，比较路径要先 `realpath`）。
- 探针实测（写进 `plan/02` §3.1，M1/M2 实现时直接引用）：
  - `merge-tree --write-tree` 会写对象；**目标 `GIT_OBJECT_DIRECTORY` 必须已存在**，否则 git 报
    `fatal: not a git repository`（这是"环境不满足"里最容易误判成"仓库坏了"的一条）。
  - 冲突时 `merge-tree` exit 1，stdout 首行仍是 tree OID，随后 `100644 <oid> <stage>\t<path>`。
  - octopus：`remerge-diff` 只在 **stderr** 打 `Skipping remerge-diff for octopus merges.`，payload 为空。
  - `-U0` patch-id：跨行号同 id、四种空白形态同 id、**对文件路径敏感**（同内容不同文件 → 不同 id）。
- **探针命令的 `&&` 链会"在错的目录里执行"（本轮实测踩到，已零成本修正）**：
  `cd <不存在或删不掉的目录> && git init ... && git checkout -b X` 这种链在 Git Bash 上
  可能**不中断**（`rm -rf` 对"目录被占用"仍可能返回 0），于是命令落在**上一个成功的 cd**
  （最坏情况 = 项目仓库根目录）里执行——本轮因此在本项目仓库里凭空多了一个 `other` 分支、
  把 M0 提交落到了它上面（`git reflog` 一眼可见 `checkout: moving from main to other`）。
  处置：探针**用 `set -e` + 绝对路径 + 每步单独 `cd`**，事后来一次
  `git branch -v` / `git reflog` / `git log --all --oneline` 三连核对（无远端时是零成本修正窗口：
  `git branch -f main <sha>` + `git branch -d <误建分支>`）。
- `build/` 目录（探针与测试 venv）已在 `.gitignore` 中，不入仓。

## 5. M0 的 DoD 逐项 checklist

- [x] `plan/00`–`06` 齐备，`data/README.md` 口径唯一权威
- [x] 可安装：干净 venv `pip install -e .` → 裸 `mergefidelity --version` / `python -m mergefidelity --version`
- [x] 五子命令可 `--help`；未实现模块退出码 2 + 中文提示，无伪造输出
- [x] 退出码契约锁进测试（0/2 + `GitEnvError→3`）
- [x] `LICENSE`（MIT）与 `pyproject` 一致；README 声明可核对
- [x] `.gitattributes` 定 EOL；新增文本 0 CRLF / 0 BOM（实测扫描）
- [x] 双解释器 `pytest -q` 全绿（67 passed × 2）
- [x] workflow 本地可解析，矩阵与 step 数符合预期
- [x] `git status` 干净可提交（无 `build/`、无生成物）
- [ ] **CI 绿** —— 未接远端，**写"本地等价校验（待首推验证）"**，M6 首推后据实补记 run id

## 6. 关键命令速查

```bash
# 测试（两条解释器通道）
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.8 -X utf8 -m pytest -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.12 -X utf8 -m pytest -q

# 干净 venv 验证（README 通路；首次必须先升 pip）
py -3.8 -m venv build/venv38
./build/venv38/Scripts/python.exe -m pip install -U pip
NO_PROXY="*" no_proxy="*" ./build/venv38/Scripts/python.exe -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
./build/venv38/Scripts/python.exe -m pytest -q
./build/venv38/Scripts/mergefidelity.exe --version

# CLI 冒烟
mergefidelity --help
mergefidelity fidelity scan --help
mergefidelity gate . --baseline audit-baseline.toml   # 骨架期 → 退出码 2 + 中文提示

# 提交前自查
git status --short
py -3.8 -c "import yaml,io;yaml.safe_load(io.open('.github/workflows/ci.yml',encoding='utf-8'))"
```
