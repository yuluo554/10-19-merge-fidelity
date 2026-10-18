# HANDOFF-M5 · 下一棒：`report` / `gate`（确定性报告 + CI 门禁）

> 本文件由 M4 收尾时写入。上游：`plan/05-里程碑.md` 的 M5 行、`plan/03-模块详设.md` §4/§5、`data/README.md` §4.6/§4.7。
> 用法：新对话 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M5.md" 继续完成任务`。

## 1. 当前进度与证据（M4 已完成）

| 项 | 状态 | 证据（2026-10-19 实测） |
|---|---|---|
| `ledger` 实现 | ✅ | `src/mergefidelity/ledger.py`：`--grep='^This reverts commit'` 枚举 → 正文正则提 OID → **反向 patch-id 校验** → `--find-object` 收窄候选后按 patch-id 判重放 → `REVERTED_THEN_REDONE` / `REVERTED_NO_SUCCESSOR` / `REVERT_UNVERIFIED` |
| golden 逐项一致 | ✅ | **3/3** ledger fixture 的 `entries` / `counts` / `unavailable` 与 `expect.json` 逐项一致（`tests/test_ledger.py`，逐 fixture 比对整条 entries） |
| 条目字段锁 | ✅ | 每条 entry 字段集合恰为 8 项（`revert_oid`/`reverted_oid`/`reverted_subject`/`reverted_commit_time`/`status`/`verified`/`successor_oid`/`paths`）——`evidence` 字段已删（killed，见 K39） |
| 反向校验 | ✅ | `then-redone` 复算：revert 的 `-U0` patch-id == 被回滚提交 diff **取反**后的 patch-id（两侧均 `42c614e3…`） |
| 不猜意图 | ✅ | `patchid-mismatch`（正文称回滚 X、实际回滚 Y）→ `REVERT_UNVERIFIED(verified=false)`，无 successor |
| `UNAVAILABLE` ≠ 无 successor | ✅ | 关掉 `--find-object` 能力探针 → 同一 `no-successor` 仓库输出 `REVERT_UNVERIFIED` + `unavailable=[git_too_old/find-object]`，与 `REVERTED_NO_SUCCESSOR` **是两条不同输出** |
| 筛选不能当结论（实测抓出的真缺陷） | ✅ | `--find-object` 认 blob、`-U0` patch-id 对空白免疫 → "只差空白 + 文件别处已变"的重新落地两个 blob 都不在筛选集里。只做筛选会静默漏报；修法：**筛选集落空即回全量复扫**。复现 `test_reland_invisible_to_find_object_is_still_then_redone`；变异验证：删掉复扫 → 该测试变红 |
| 去重/排序/只读 | ✅ | 同一 revert 只入账一次；按 `(被回滚 commit_time, revert_oid)` 排序；`ledger` 不建任何 worktree（跑前后 `git worktree list` 不变） |
| 骨架态退役（ledger） | ✅ | `ledger.py` 的 `NotReadyError` 已删；骨架登记测试只剩 **report / gate**；`test_cli.py` 的 not-ready 参数同步缩小 |
| 基准 | ✅ | `bench/ledger.json`：3 fixture 端到端耗时 + 条目数/三状态分布（单次 ≈0.9–1.6s） |
| CI 接线 | ✅ | 新增 step `CLI smoke (ledger on generated fixtures)`（`set +e` + 断言退出码 0 + 断言 `counts.then_redone==1`）；workflow 本地 `yaml.safe_load` 通过（**9 step**） |
| 输入类错误归 2 | ✅ | 解不出来的 `--range` → `UsageError`（退出码 2），不是 3 |
| 报告头指纹口径统一 | ✅ | `gitattributes_oid` 取**范围右端**（`_range_end`：`A..B`→`B`、单 REV→它自己、无范围→`HEAD`），与 `fidelity` 的 `end_rev` 同口径；不再是"恒取 HEAD"的临时写法 |
| 测试规模 | ✅ | 快层 **196 passed** ×（3.8 / 3.12）；慢层（`--check` 重生成 21 个仓库）1 passed |

**本地等价校验（未接远端，CI 待首推验证）**：双解释器快层、3.8 慢层、`gen_fixtures.py --check` 实跑、workflow 本地解析、ledger CLI 冒烟。
**不可本机实跑**：Linux/macOS 上 `git log --find-object` / `worktree` 行为差异（首份跨平台证据仍由 CI 首推给出）。

## 2. 下一棒待办（M5 = report + gate）

### 2.1 `report`（`src/mergefidelity/report.py`）

1. **实现 `mergefidelity report <repo> [--range=…] [--format=json|md] [--out=PATH]
   [--verify=PATH] [--as-of=YYYY-MM-DD] [--parity-from=REF --parity-to=REF]`**：
   - 输入 = **前三个模块**的原始结果：`fidelity` 与 `ledger` **恒计入**；`parity` 需两个显式引用，
     未给时该节为 `null` 并在 `notes` 写明 `parity_not_requested`（**不伪造空结果**，K23）。
   - 报告头（写死、参与 digest）：`tool_version` / `git_version` / `object_format` /
     `gitattributes_oid` / `config_overrides` / `range` / `as_of` / `findings_digest_algorithm:"sha256"`。
     **禁止**：扫描时刻、绝对路径、主机名、用户名、locale、Python 版本。
   - `--verify=PATH`：读回 JSON → 重算 `digest_of(rest)` 校验（不匹配 → 退出码 1，定位到 `digest`）
     → 用**同一对象库**重跑模块、逐字节比较 → 首个差异用 JSON path 表达
     （`merges[3].hunks[1].new_range`）→ 相等则退出码 0，stdout 打 `verified: N merges, M findings`。
   - 坏 JSON / 缺 `digest` 字段 → 退出码 2（缺字段 = 坏报告）。
2. `tests/test_report.py`：digest 跨时区一致（`TZ=America/New_York` vs `TZ=Asia/Shanghai`）；
   `core.quotepath=true/false` 下 digest 相同；篡改一个字节 → 1 且 `json_path` 指向被改字段；
   手工删 `digest` → 2；`parity` 未请求时 `null` + `notes`。
3. `docs/report-sample.json`（报告样例，入仓）+ README 引用。

### 2.2 `gate`（`src/mergefidelity/gate.py`）

1. **实现 `mergefidelity gate <repo> --baseline=PATH [--since=REV] [--fail-on=smuggled|dropped|any]
   [--as-of] [--format] [--out]`**：
   - **受限 TOML 子集**（3.8 无 `tomllib`）：只支持 `[[finding]]` + 字符串值 + 注释；
     语法错误 / 缺 `justification` / 坏日期 → **退出码 2，零副作用**；数组/嵌套表/多行字符串 →
     `toml_unsupported`（2，明示行号）。
   - 跑 `fidelity`（`--since` 增量；未给则全量）→ 分类：命中且 `as_of <= expires` → `baselined`；
     命中且 `as_of > expires` → `expired`（参与失败）；未命中 → `new`（按 `--fail-on` 过滤）；
     基线条目无对应 finding → `stale`（只提示）。
   - 退出码：`new` 或 `expired` 非空 → 1；否则 0；用法/基线坏 → 2；环境 → 3。
2. `tests/test_gate.py`：新增 1 个夹带 → 1 且只报新增；旧账未过期 → 0 且 `baselined==1`；
   `expires` 改到过去 → 1 且 `expired==1`；语法错误 → 2 + 行号 + **不写任何产物**；
   基线指向不存在 finding → `stale==1` 且退出码 0；同一输入两次退出码一致。
3. `audit-baseline.toml`（基线样例，入仓）+ README 场景三引用。
4. `tools/bench_gate.py` → `bench/gate.json`（扫描耗时 / 基线命中数）。

### 2.3 收尾

1. 退役 `report` / `gate` 骨架态（各自 `*.py` + `test_readme_gate.py` 登记测试 + `test_cli.py` 的
   not-ready 参数 —— **三处同步**；两模块一起退，登记表清空后该测试要么删要么改成"空集"）。
2. CI 新增 report/gate 冒烟 step；同步 `tests/test_workflow.py` 的 step 名单与断言。
3. DoD 验证 → 回写 `plan/00`/`03`/`04`/`05`/`06`/README → 写 `plan/HANDOFF-M6.md` → commit。

## 3. 既定口径清单（K1–K37 见前几份 HANDOFF，本棒新增 K38–K43）

| # | 口径 | 落点 |
|---|---|---|
| K38 | **反向 patch-id 校验是 `ledger` "回滚属实"的唯一判据**：revert 的 `-U0` patch-id == 被回滚提交 diff 取反后的 patch-id；不等 → `REVERT_UNVERIFIED`，不猜意图 | `ledger._entry`、`test_ledger.py`、`plan/00` 决策记录表 |
| K39 | **`ledger` 条目不输出 `evidence` 字段**（对齐 golden）：`verified` + `successor_oid` 已承载结论；`plan/03` §3.3 初稿的 `evidence` 已删 | `plan/03` §3.3、`plan/04` §五、`test_ledger.py::test_entry_field_set_is_exactly_golden` |
| K40 | **`--find-object` 只收窄候选，结论口径以 patch-id 相等为准**；不可用（git <2.16 或命令失败）→ `unavailable=[{reason:git_too_old,capability:find-object}]` 且状态给 `REVERT_UNVERIFIED`（**不降级猜**："没 successor"是一个断言，缺证不能下）。注意此时 `verified` 仍可能是 `true`——`verified` 说的是"这条 revert 属实吗"，`status` 说的是"重放结论"，两者是两件事；两种 `REVERT_UNVERIFIED` 靠 `unavailable` 是否为空区分 | `ledger._find_successor` / `_find_object_supported`、`test_ledger.py::test_unavailable_is_distinct_from_no_successor` / `test_mismatch_and_unavailable_are_two_kinds_of_unverified` |
| K41 | **`gitobj.commit_diff` 增加 `reverse=True`**（取反 diff = `diff-tree <c> <c>^`）；根提交取反无意义 → 返回 `None`；diff 参数构造仍只在 `gitobj` 一处 | `gitobj.commit_diff` |
| K42 | **`ledger` 的 `paths` 取 revert 提交改动的路径；`reverted_*` 取正文**声称**的提交**（即使实际回滚别人）；正文声称的 OID 在当前对象库解不出来 → 跳过该条（无 fixture 覆盖，如实留白） | `ledger._entry`、`data/README.md` §4.5 相关字段 |
| K43 | **`ledger` 的 `as_of`** = 账本内最新提交时间（revert 与 reverted commit_time 取最大）的 UTC 日期；空账本回落 HEAD；**不读系统时钟** | `ledger._default_as_of`、`test_ledger.py` |
| K44 | **`--find-object` 只用于加速命中，不足以支撑"没有"这个结论**：`-U0` patch-id 对空白免疫，而 `--find-object` 认 blob 内容——"只差空白 + 文件别处已变"的重新落地，其 old/new blob 都不在筛选集里。因此**筛选集落空时必须回到全量 later 提交复扫**，才能下 `REVERTED_NO_SUCCESSOR`（否则静默漏报）。实测复现：`test_ledger.py::test_reland_invisible_to_find_object_is_still_then_redone`；变异验证：把复扫那一步删掉 → 该测试变红 | `ledger._find_successor`、`test_ledger.py`、`plan/03` §3.2、`plan/00` 决策记录表 |
| K45 | **`ledger` 的 `gitattributes_oid` 取范围右端**（`_range_end`），与 `fidelity` 的 `end_rev` 同口径；无范围 → `HEAD`。理由同 K21：`.gitattributes` 会改变 merge driver 判定，指纹必须反映**被扫那个时点**，而不是恒取 HEAD | `ledger._range_end`、`ledger.ledger_scan` |

## 4. 本机环境坑（2026-10-19 实测；引用前先复测）

- **`git log --grep=<re>` 匹配的是整条提交信息（含正文）**，不是只匹配标题：`^This reverts commit`
  用 `re` 语义、`^` 锚到正文每一行的行首（`--format=%B` 提取正文，不解析 subject）。
- **枚举时用控制符作记录分隔**：`--format=%H\x1f%B\x1e`，按 `\x1e` 切记录、`\x1f` 切 OID/正文
  （正文里不会出现这两个控制符）。不要用 `%H%x00%B` 再按 `\x00\x00` 切——单条 revert 能过、
  多条会粘成一条（本轮 oracle 的旧写法即如此，只覆盖单 revert fixture 才没暴露）。
- **`git patch-id` 对取反 diff 稳定**：`diff-tree -p -U0 --no-renames <c> <c>^` 的 patch-id 与
  `git revert` 生成的 revert 补丁的 patch-id 相等（实测）。
- **`git log --find-object=<blob> --all` 需 git ≥2.16**；`diff-tree -r -z --raw <c>` 的格式是
  `:<mode> <mode> <old> <new> <status>\0<path>\0`——按 `\0` 切后每两个 token 一组。
- **`--find-object` 不能用来下"没有"的结论**：它认 blob 内容，而 `-U0` patch-id 对空白免疫，
  两者在"只差空白 + 文件别处已变"时**同时失配**（实测踩到，见 K44）。
- **`git revert` 对已 revert 过的提交会失败**（`nothing to commit`）：造多 revert 仓库时别连着
  `revert HEAD` / `revert HEAD~1`，会指向同一条；用显式的目标 OID。
- **不要用 `python`**：本机 `python` 可能是商店占位符，一律 `py -3.8` / `py -3.12` 并加 `-X utf8`。
- **bench 与测试并发会打架**：慢层会重生成 `data/fixtures/**/repo/`，跑慢层时不要同时跑读 fixture 的东西。
- 本机 pip 走系统代理 → `NO_PROXY="*"` + 清华镜像；`py -3.8 -m venv` 的 pip 20.2.3 不支持 `-e .`，先升 pip。

## 5. M4 的 DoD 逐项 checklist

- [x] `mergefidelity ledger <repo>` 可用；3 个 fixture 的 `entries` / `counts` / `unavailable` 与 golden **逐项一致**
- [x] 反向 patch-id 校验：revert 的 `-U0` patch-id == 被回滚提交 diff 取反后的 patch-id
- [x] `patchid-mismatch` → `REVERT_UNVERIFIED(verified=false)`，不猜意图、不算 successor
- [x] 重放用 `--find-object` 收窄候选，**结论以 patch-id 相等为准**；找到 → `REVERTED_THEN_REDONE(successor_oid=…)`
- [x] **筛选集落空必须回全量复扫**（否则"只差空白"的重新落地会被静默漏报）——变异验证已做
- [x] `UNAVAILABLE`（`find-object` 不可用）与"无 successor"是**不同输出**（`unavailable` + `REVERT_UNVERIFIED`）
- [x] 同一 revert 只入账一次；排序 `(被回滚 commit_time, revert_oid)`
- [x] 同机双跑逐字节一致；`digest` 可复算；报告 0 绝对路径；`as_of` 不读时钟；不建 worktree
- [x] 输入类错误（坏 `--range`）→ 退出码 2
- [x] `bench/ledger.json` 产出（条目数 / 三状态分布 / 耗时）
- [x] 骨架态退役同轮完成（代码 + 登记测试 + CLI 参数三处同步）
- [x] CI 新增 ledger 冒烟（断言退出码 0 + `counts.then_redone==1`），workflow 本地解析通过
- [ ] **CI 绿** —— 未接远端，**写"本地等价校验（待首推验证）"**，M6 首推后据实补记 run id

## 6. 关键命令速查

```bash
# ledger 冒烟（fixture 仓库由生成器产出，不入仓）
py -3.8 tools/gen_fixtures.py --out data/fixtures --suite ledger
PYTHONPATH=src py -3.8 -m mergefidelity ledger data/fixtures/ledger/then-redone/repo
    # rc=0；counts.then_redone=1，条目 successor_oid=7146239c…
PYTHONPATH=src py -3.8 -m mergefidelity ledger data/fixtures/ledger/patchid-mismatch/repo
    # rc=0；counts.unverified=1，条目 verified=false

# 测试
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.8 -X utf8 -m pytest -q -m "not slow"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.8 -X utf8 -m pytest -q -m slow
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.12 -X utf8 -m pytest -q -m "not slow"

# 基准
py -3.8 tools/bench_ledger.py --out bench/ledger.json --repeats 3
py -3.8 tools/gen_fixtures.py --out data/fixtures --check   # 21/21 逐字节一致
```
