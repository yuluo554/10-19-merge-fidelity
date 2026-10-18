# AUDIT-M0-M2 · M0–M2 全面审计记录（2026-10-18）

> 目的：对话本意只做 M0，实际推进到 M2；本轮**逐项复核 M0–M2 是否完整且正确**，
> 并把复核中发现的问题**当场修掉 + 锁进测试 + 回写口径**。
> 结论：M0–M2 的承诺项全部达成；复核抓出 **2 个真缺陷**、**5 处文档/留档不一致**、**2 处覆盖缺口**，均已修复并复验。

## 一、审计方法

1. 从 `plan/00` 里程碑表、`plan/05` 出口门、`plan/HANDOFF-M1/M2` 的 DoD 逐项列出承诺；
2. 每条承诺**用命令取实证**（不引用记忆、不引用计划文档里的"应做"）；
3. 对"判定类"承诺额外做**环境敏感性检查**（同一输入换环境结论会不会变）；
4. 抓到的问题当场修，修完重跑全量验证，并把口径写回唯一权威文件。

## 二、M0 复核（计划 + 骨架）

| 承诺 | 实证 | 结论 |
|---|---|---|
| `plan/00`–`06` 齐备 | 7 个文件存在；索引/决策/台账/里程碑表可读 | ✅ |
| 可安装 CLI + 入口 | `pyproject.toml` 有 `mergefidelity = "mergefidelity.cli:main"`；干净 venv `pip install -e ".[dev]"` 后裸 console script 与 `python -m mergefidelity` 双形态可跑 | ✅ |
| 五子命令注册 | `build_parser()` 反射：`['fidelity','gate','ledger','parity','report']` | ✅ |
| 退出码契约锁进测试 | `tests/test_cli.py`（19 项）覆盖 0/2 分支与 `GitEnvError→3` 映射 | ✅ |
| 未实现模块不伪造结果 | 骨架登记测试断言 parity/ledger/report/gate 抛 `NotReadyError`（exit 2 + 中文提示）且 stdout 为空 | ✅ |
| LICENSE / `.gitattributes` / CI | MIT 文件和 `pyproject` 一致；CI 7 个 step 本地 `yaml.safe_load` 通过 | ✅ |
| 仓内无本机路径/身份泄漏 | 全 tracked 文件扫描：仅 `yusu554` 的 GitHub **noreply** 邮箱与署名（有意公开） | ✅ |

## 三、M1 复核（数据先行）

| 承诺 | 实证 | 结论 |
|---|---|---|
| 生成器可重建 fixture | `py -3.8 tools/gen_fixtures.py --out data/fixtures --check` → `--check 通过：21 个 fixture 与冻结产物逐字节一致`（exit 0） | ✅ |
| 规模与分布 | fidelity 12（题面 10 + 2 守护）· parity 6 · ledger 3 = 21；`manifest.json` 与目录双向一致（有测试） | ✅ |
| 植入器自证 | 每个 fidelity fixture 的 `declared_counts` 与 oracle 复算在**生成期**对账，不符即 `GenError` | ✅ |
| 反例在列 | `clean-resolution-a/b`、`drop-then-readd`、`custom-driver` 断言零 SMUGGLED / 零 DROPPED | ✅ |
| 仓库本体不入仓 | `git check-ignore` 命中 `data/fixtures/**/repo/`（测试断言）；`git ls-files` 下无 `.git`/`repo/` | ✅ |
| golden 规范 JSON + LF | 测试断言无 CRLF、无 BOM、结尾换行 | ✅ |

**M1 的诚实缺口（保留）**：跨机器位级一致**尚未实测**（本机双解释器 + 双跑已验）。
第一份跨平台证据将在 CI 首推时由 `slow` 层（`--check`）给出。

## 四、M2 复核（fidelity）

| 承诺 | 实证 | 结论 |
|---|---|---|
| 12 个 fixture 的 payload 与 golden 逐项一致 | `tests/test_fidelity.py`（43 项）逐 fixture、逐字段；含 `blob_fidelity` 五字段 | ✅ |
| 三类 hunk 分类 | 4 个夹带 / 3 个吞掉 fixture 各只报 1 处；反例零报 | ✅ |
| SKIPPED 语义 | octopus 与 custom_driver 均 `skipped[].reason` 命中、不进分母、**退出码 0** | ✅ |
| 确定性 | 同仓双跑逐字节一致；`digest` 可复算；报告 0 绝对路径；`as_of` 来自提交时间 | ✅ |
| 退出码 | `--fail-on` 命中 1 / 不命中 0 / 坏 kind 2 / 非仓库 3 | ✅ |
| 骨架态退役 | `fidelity.py` 无 `NotReadyError`；登记测试只剩 4 个模块 | ✅ |
| 基准 | `bench/fidelity.json`：8-merge 合成仓批量 0.061 s vs 逐 merge 0.463 s（≈7.6×） | ✅ |
| CI 冒烟 | 新增 step 断言 `fidelity scan --fail-on=smuggled` 退出码 1；workflow 本地解析通过 | ✅ |

## 五、复核发现的问题与处置

### F1（真缺陷，已修）判定相关 git 配置未钉死 → 同一仓库在不同机器上结论不同

- **实测**：在 `smuggle-extra-line` fixture 上设 `merge.conflictStyle=zdiff3`，
  机械树 OID 由 `51683564511b1d935ddc0160f2ec776f5ec43045` 变为 `0f5a5d03ff9a1ad4c82c3e4148e6dad5d09950ca`。
  机械树是 finding 的判定输入，因此"任何机器结果一致"原先**不成立**。
- **修**：生成侧 `GIT_BASE` 与生产侧 `gitobj.CONFIG_OVERRIDES` 同钉 7 项
  （`core.quotepath` / `core.pager` / `core.autocrlf` / `core.eol` / `diff.algorithm=myers` /
  `diff.noprefix=false` / `merge.conflictStyle=merge`），并登记进报告头 `config_overrides`。
- **验证**：重生成后 `--check` 仍**逐字节一致**（说明钉的是当前默认行为，未改结论）；
  新增回归测试用 `GIT_CONFIG_*` 注入 `zdiff3` → 结果与 golden 相同。
  变异验证：删掉 `merge.conflictStyle=merge` 这一项，该测试必红。
- **留档**：`data/README.md` §4.1、`README.md`「已知边界」。

### F2（真缺陷，已修）非法 rev 返回退出码 3（环境）而非 2（用法）

- **实测**：`fidelity scan <repo> --since=no-such-rev` → rc=3。按 `plan/03` §0 契约，
  3 = 环境不满足（git 版本 / 仓库不存在 / 超时），而"参数写错"是用法错误 → 应 2。
  混在一处会把"我参数写错了"读成"这台机器做不了"。
- **修**：`fidelity.require_ref()` / `validate_range_spec()` 在扫描前校验 `--since/--until/--range`
  的每一侧，解不出来即 `UsageError`（→ 2）。
- **验证**：CLI rc=2；新增 2 条测试（API 层 `pytest.raises(UsageError)` + CLI 层 rc=2 且提示含"不是有效引用"）。
- **留档**：`plan/HANDOFF-M3.md` 追加 K31（parity 的 `--from/--to` 照此办理）。

### F3（文档与实现不一致，已修）`plan/03` §1.2 把 remerge payload 写成"主路径"

- 实际实现（与 `data/README.md` §4.3、golden）以**树 diff 定义式**为判定依据，
  remerge payload 用于**交叉校验与降噪**（不一致记 `CROSSCHECK_MISMATCH`，进 `warnings`，不改判定）。
- **修**：改写该段为"判定以本式为准；payload 交叉校验"。实测 12/12 fixture 无 `CROSSCHECK_MISMATCH`。

### F4（文档陈旧，已修）5 处数字/状态与实际不符

| 位置 | 旧 | 新 |
|---|---|---|
| `plan/00` 文档索引 | `19 个 fixture 设计`；`data/fixtures/fidelity … ⬜ 待 M1` | 21 个；`{fidelity,parity,ledger}` ✅ M1/M2 |
| `plan/00` 承诺台账「测试覆盖」 | `⬜ 待 M2–M5` | 三类 hunk ✅ M2；其余按 M3/M4/M5 分列 |
| `plan/05` M1 出口门与演示行 | `19 个 fixture`、`10 fidelity` | 21 个、`12 fidelity` |
| `README` 状态表 | M1/M2 仍写"⬜ 计划中" | M0–M2 ✅ 已完成（含数字） |
| `data/README` §三 | `10 个 fidelity fixture` | 12 个（题面 10 + 2 守护），并补"钉死配置"的必要性 |

### F5（留档一致性，已补）`HANDOFF-M2` 的"custom-driver 顺延"缺闭环

- 按"补记是追加事实、不改原文"的纪律，在该条下追加 `M2 收尾补记` 指向 `HANDOFF-M3` §1。

### F6（覆盖缺口，已补）两条测试缺位

- `--range=A..B` 路径无测试 → 补 `test_range_spec_is_honoured`；
- `tools/bench_fidelity.py` 无冒烟 → 补 `test_bench_tool_runs_and_writes_json`（小参数、产物落 tmp）。

### F7（边界未如实标注，已补）`.gitattributes` 匹配是有意简化

- 实现只支持 `*.ext` / 顶层文件名 / `dir/**` / `/精确路径`，**不支持** `!` 取反、字符组、`**/` 中缀。
  → 写进 `README.md`「已知边界」（宁少命中不近似）。

## 六、复验证据（修复后重跑）

| 项 | 结果 |
|---|---|
| `py -3.8 -m pytest -q -m "not slow"` | 130 passed |
| `py -3.12 -m pytest -q -m "not slow"` | 130 passed |
| `py -3.8 -m pytest -q -m slow` | 1 passed（重生成 21 个仓库并逐字节比对） |
| `tools/gen_fixtures.py --check` | `21 个 fixture 与冻结产物逐字节一致`（exit 0） |
| 测试规模（collect） | 131 项 = canonical 11 · cli 19 · diffparse 7 · fidelity 43 · gen_fixtures 22 · gitobj 16 · readme_gate 8 · workflow 5 |
| CI workflow 本地解析 | jobs=['test']、steps=7 |
| 干净 venv | 裸 `mergefidelity` 与 `python -m mergefidelity` 双形态实跑通过 |

## 七、仍然存在的缺口（如实列出，未做）

| # | 缺口 | 归属 |
|---|---|---|
| 1 | **无远端**：仓库未推送 GitHub，"CI 绿"未发生（DoD 一律写"本地等价校验，待首推验证"） | M6 |
| 2 | **跨机器位级一致未实测**（本机双解释器已验），首份跨平台证据由 CI 首推的 `slow` 层给出 | M6 |
| 3 | `parity` / `ledger` / `report` / `gate` 仍为骨架态（exit 2 + 中文提示，不伪造结果） | M3–M5 |
| 4 | 大仓库（>10 万提交）无样本；bench 的 `--repo` 为可选入口 | 首期不承诺 |
| 5 | `.gitattributes` 高级模式（取反/字符组）不支持 | 已标注为有意简化 |
| 6 | `custom-driver` 判定依赖 repo 内 `.gitattributes`；全局 `core.attributesFile` 不在扫描面内 | 已标注（简化） |
