# HANDOFF-M6 · 下一棒：发布（公开仓库 + v0.1.0 tag + Release 附件）

> **状态：✅ 已完成（2026-10-19）**。发布留档见 `plan/RELEASE-M6.md`（两栏：tag 前事实 / tag 后追加事实）。
> 本棒核心不是写代码，而是把"陌生人 30 秒能装上并看到输出"变成事实——过程中 CI 首推
> 实测抓出并修掉 **3 个真缺陷**（见 §2.6），发布包干净环境实测又抓出**另外 3 个**（同见 §2.6）。
>
> 本文件由 M5 收尾时写入。上游：`plan/05-里程碑.md` 的 M6 行、`plan/06-交付对标.md` §四、`plan/01-题目文档.md` §三。
> 用法：新对话 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M6.md" 继续完成任务`。

## 1. 当前进度与证据（M5 已完成）

| 项 | 状态 | 证据（2026-10-19 实测） |
|---|---|---|
| `report` 实现 | ✅ | `src/mergefidelity/report.py`：`build_report`（三模块同对象库现跑一次）→ `findings` 三源合一 → 规范 JSON + digest；`--verify` 先内容后 digest 定位；坏 JSON/缺 `digest` → 退出码 2 |
| `findings` 三源合一 | ✅ | `fidelity.findings_of`（hunk）/ `parity.findings_of`（`PARITY_MISSING`/`PARITY_MODIFIED`）/ `ledger.findings_of`（`REVERTED_*`）；字段恰 7 项；排序 `(commit_time, commit_oid, path, old_range)` |
| 内容寻址 ID 独立复算 | ✅ | `test_report.py::test_findings_ids_are_content_addressed`：每条 finding 的 `id` 与 `canonical.finding_id` 手算一致 |
| digest 跨时区一致 | ✅ | `TZ=America/New_York` vs `TZ=Asia/Shanghai` 下同 digest（M5 实测 `1ff58a3c7f4cd8146886f6a8112c1f43e3ff118b5208f7286743a671df695ab2`；v0.1.0 版本号一变，digest 同步改为 `eb65704e058fbdcfeb9226be00b974963b8b780fb5720432a3aa13a774b383f4`） |
| digest 对 `core.quotepath` 免疫 | ✅ | 报告头字段在 `core.quotepath=true/false` 下不变（路径经 `-z` 原样读出）；变异验证：去掉 `-z` → 测试变红 |
| 报告头禁止字段 | ✅ | 断言无绝对路径 / `python_version` / `scan_time` / `hostname` / `locale`；`as_of` 取自提交时间（`2026-01-01`） |
| **`as_of` 回落口径（实测抓出的回归）** | ✅ | 初版空输入（无 merge、无 revert）落成 `1970-01-01`，与同一仓库的 `fidelity`/`ledger` 不一致。定案：取**三源 `as_of` 的最大值**，空仓库无提交才回落 `end_rev`。复现 `test_report.py::test_as_of_falls_back_to_head_on_empty_input`；变异验证：去掉回落 → 该测试变红 |
| `--verify` 篡改定位 | ✅ | 改一字节 → 退出码 1，`json_path` = `findings[0].kind`；嵌套 → `fidelity.merges[0].hunks[0].new_range`；只改 `digest` → 定位到 `digest` |
| **定位顺序（实测抓出的设计点）** | ✅ | 必须"先内容、后 digest"：先查 digest 会把"哪一处被改了"的答案盖成 `digest`。变异验证：把 digest 检查挪到前面 → 两条篡改测试变红 |
| `parity` 不伪造空结果 | ✅ | 未给两个引用 → 该节 `null` + `notes=[parity_not_requested]`；只给一个 → 用法错误 2 |
| `gate` 实现 | ✅ | `src/mergefidelity/gate.py`：受限 TOML 子集解析 + 四类分类 + 四组退出码；`--since` 增量 |
| `gate` 四组退出码 | ✅ | 新增 → 1 且只报新增（2-finding 合成仓验证）；旧账未过期 → 0 且 `baselined==2`；`expires` 改到过去 → 1 且 `expired==1`；坏基线 → 2 + 行号 + **零产物** |
| 边界日 | ✅ | `as_of == expires` → `baselined`（口径 `as_of <= expires`） |
| `stale` 只提示 | ✅ | 幽灵条目 → `stale==1` 且退出码 0；无 finding 仓库 + 幽灵基线 → 同样 0 |
| 受限 TOML 六种非法形态 | ✅ | 数组 / 嵌套表 / 多行字符串 / 内联表 / 非字符串值 / 未知键 → `toml_unsupported` + **明示行号**；缺键 / 坏日期 / 重复 id / 段外键值 / 空基线 → 语法错误 |
| **`--fail-on` 只过滤 `new`（实测抓出的设计点）** | ✅ | 门禁**全量收集** `SMUGGLED`+`DROPPED`；若只扫 `--fail-on` 那一类，另一类的基线条目会凭空变 `stale`（已登记旧账被误报成"已修复"）。复现 `test_gate.py::test_baseline_coverage_is_not_filtered_by_fail_on`；变异验证：`_scan_kinds()` 返回 `FAIL_ON_KINDS[fail_on]` → 测试变红 |
| 样例产物入仓 | ✅ | `docs/report-sample.json`（`--verify` 通过）+ `audit-baseline.toml`（覆盖该 fixture 真实 finding → 退出码 0）；两份都被测试复算 |
| 骨架态退役（三处同步） | ✅ | `errors.NotReadyError` 已删；`report.py`/`gate.py` 的 `raise` 已删；`test_readme_gate.py` 的登记测试改成**空集守门**；`test_cli.py` 的 not-ready 参数改成"坏输入文件 → 2" |
| 共享层口径收敛 | ✅ | `fidelity.range_end`（取代 `ledger._range_end`）、`fidelity.validate_as_of`（取代 `ledger`/`parity` 的 `_validate_as_of`） |
| CI 接线 | ✅ | 新增 2 step：`CLI smoke (report digest + --verify on generated fixtures)`、`CLI smoke (gate four exit-code semantics)`；workflow 本地 `yaml.safe_load` 通过（**11 step**） |
| 基准 | ✅ | `bench/gate.json`：12 个 fixture 的完整门禁路径耗时 + 基线命中数/四类计数 |
| 测试规模 | ✅ | 快层 **258 passed** ×（3.8 / 3.12）；慢层（`--check` 重生成 21 个仓库）1 passed（M6 发布时点事实；tag 后迭代新增测试，当前实测见 `plan/00:119`） |

**本地等价校验（未接远端，CI 待首推验证）**：双解释器快层、3.8 慢层、workflow 本地解析、report `--verify` 与 gate 四组退出码 CLI 冒烟、样例产物复算。
**不可本机实跑**：Linux/macOS 上 `git log --find-object` / `worktree` / `merge-tree` 行为差异（首份跨平台证据仍由 CI 首推给出）。

> **M6 已补齐跨平台证据**：CI 首推后，ubuntu-22.04（git 2.55.0）与 windows-latest（git 2.56.0.windows.2）
> 两个平台 × py3.8/3.12 四 job 全绿（run `39218760801` 等）。注意 `git_version` 因此成为
> **跨机天然不同的环境指纹**——`report --verify` 对"别的机器生成的报告"会命中 `fidelity.git_version`，
> 这是设计如此（`data/README.md` §4.6），不是篡改（见 §2.6 缺陷 3）。

## 2. 下一棒待办（M6 = 发布）

> 这一棒的核心不是写代码，而是**把"陌生人 30 秒能装上并看到输出"变成事实**。

### 2.1 脱敏四步（发布前必做，逐条可复核）

1. **文本 0 命中**：本机用户名、家目录、盘符绝对路径、非 noreply 邮箱。
   - 已知风险点：`plan/HANDOFF-*.md` 与 `plan/AUDIT-*.md` 里的实测命令、`data/README.md` 的检索记录。
   - 复核命令（仓库内搜，命中即改；本机用户名用变量取，命令本身不入仓）：
     ```bash
     U="$(git config user.name)"     # 本机用户名，不写进文件
     git grep -n -I -e 'C:\\' -e '/Users/' -e "$U" -- . ':!data/fixtures'
     git grep -n -I -E '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' -- . ':!data/fixtures'
     ```
2. **产物脱敏**：`bench/*.json` 里只应有 fixture 名（无绝对路径）；`docs/report-sample.json` 已断言无绝对路径。
3. **git 历史脱敏**：`git log --format=%an <%ae>` 全列必须是 `yuluo554 <282769740+yuluo554@users.noreply.github.com>`（本机身份已是该值，M0 时确认过）。
4. **`.gitignore` 复核**：确认 `data/fixtures/**/repo/` 与 `data/fixtures/**/.git/` 仍被排除（合成仓库不入仓）。

### 2.2 干净环境验证（M6 的 DoD 核心）

```bash
# 在一个全新的目录里 clone（不是在本仓库里跑）
git clone <公开地址> /tmp/clean-clone && cd /tmp/clean-clone
py -3.8 -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
mergefidelity --version          # → mergefidelity 0.1.0
mergefidelity --help             # → 五子命令
py -3.8 tools/gen_fixtures.py --out data/fixtures --check   # → 21/21 逐字节一致
py -3.8 -m pytest -q             # → 快层 258 passed + 慢层 1 passed（M6 时点）
```

再按 README 的三个场景逐条跑通（`fidelity scan` / `parity --from --to` / `gate --baseline`），
并复算两份样例：

```bash
mergefidelity report data/fixtures/fidelity/smuggle-extra-line/repo --verify docs/report-sample.json
    # → verified: 1 merges, 1 findings，退出码 0
mergefidelity gate data/fixtures/fidelity/smuggle-extra-line/repo --baseline audit-baseline.toml
    # → 退出码 0（baselined=1）
```

### 2.3 版本号（四处一致）

`pyproject.toml` 的 `version` / `src/mergefidelity/__init__.py` 的 `__version__` /
tag `v0.1.0` / Release 标题。**当前是 `0.1.0.dev0`，发布前统一改成 `0.1.0`**。
注意：报告头 `tool_version` 与 `git_version` 参与 digest——版本号一变，
`docs/report-sample.json` 的 digest 就会变，**必须同轮重生成样例并复算**
（`test_report.py::test_repo_report_sample_matches_current_tool` 会抓住这个漂移）。

### 2.4 tag + Release + 附件

- 手工源码包（D3 定案）：`git archive v0.1.0 | gzip -9n` + `SHA256SUMS`；两次构建逐字节一致。
- `sha256` 只写 Release 正文，**不写进包内**。
- 留档 `plan/RELEASE-M6.md` 两栏：tag 前事实 / tag 后追加事实（run id 等）。
- **CI 首推后据实补记 run id**，并把 `plan/00` 台账里的"CI 绿待首推验证"改成真实结论。

### 2.6 本棒实测抓出的 6 个真缺陷（逐条已修 + 变异验证）

> 本项目的 CI 此前**从未跑过**——所有"CI 绿"都是"本地等价校验，待首推验证"。首次推送后
> 四个 job 全红，暴露出前 3 个缺陷；从**发布包**做干净环境实测（下载 tar.gz → 解包 → 新 venv →
> 按 README 跑三场景与 `pytest`）时又抓出后 3 个。**"发布包实测"与"CI 绿"是两个不同的门**，
> 后者查不出前者的问题。

| # | 缺陷 | 症状 | 修法 |
|---|---|---|---|
| 1 | **生成器部分运行会改写入仓的 `manifest.json`** | `generate()` 的 `if not only` 漏判 `--suite`：`--only`/`--suite` 时仍把 21 条记录覆盖成该套件的 12/6/3 条。测试的 autouse fixture 用 `--suite fidelity` 现生成仓库 → **一次普通 `pytest` 就静默改坏一个入仓文件** | 改成 `if not only and not suites`：部分生成不写 manifest |
| 2 | **干净 clone 没有合成仓库，CI 直接 pytest 全挂** | `data/fixtures/**/repo/` 被 `.gitignore` 排除，检出后无仓库 → 依赖仓库的测试与全部 CLI 冒烟 step 全红 | CI 新增 `generate synthetic fixtures` step（**11→12 step**），置于 `pytest` 之前；同步更新 `test_workflow.py` 断言 |
| 3 | **报告样例的 `git_version` 指纹跨机不同 → `--verify` 必然非 0** | 样例在本机 `2.54.0.windows.1` 生成，CI runner 是 `2.55.0` / `2.56.0.windows.2`；`git_version` 参与 digest，逐字节比较命中 `fidelity.git_version`，rc=1 | 定案：`git_version` 是**环境指纹**（`data/README.md` §4.6），跨机不同是设计如此。测试改两段——同版本强断言 rc=0；跨版本要求差异**恰好只落在指纹字段**（其余逐字节一致），两分支均已实测 |
| 4 | **`--show-kind` 的 argparse `choices=` 拒绝文档化的逗号列表**（**发布包实测**抓出） | `plan/03` §1.1 与 README 场景一的口径是 `--show-kind=smuggled,dropped`，`_kinds_from_args` 也实现了逗号拆分，但 `cli.py` 给它加了 `choices=(...)` → argparse 把整串当一个值拒绝。**干净环境按 README 跑场景一 → 退出码 2**，"陌生人 30 秒"直接卡在第一条命令 | 去掉 `choices=`，逗号拆分与非法值报错交给 `_kinds_from_args`（`UsageError` → 2）；补 2 条测试（逗号形态被接受 rc=0 / 非法值仍 2） |
| 5 | **发布包里 `pytest` 必挂：无 `.git` 时 `git ls-files`/`git check-ignore` 直接 128**（**发布包实测**） | 手工源码包不含 `.git`，而 README 的"开发"一节让人在解包目录跑 `pytest`；`test_synthetic_repos_are_not_tracked_and_are_ignored` 无条件调 git → `fatal: not a git repository` | 分两种环境：git 工作树里照旧强断言；非 git（发布包）退化为**断言 `.gitignore` 规则文本存在**并 `skip`（不伪造"已忽略"结论） |
| 6 | **发布包慢层的 `--check` 因"冻结仓库不存在"必挂**（**发布包实测**） | `repo/` 是生成物不入包，`--check` 拿"冻结目录（无仓库）"与"临时重生成目录（有仓库）"比对 → 21 处 `frozen 仓库不存在`；README 让人直接 `pytest` 会踩到 | `test_gen_fixtures.py` 加 session 级 autouse fixture：缺仓库则先跑生成器（不传 `--suite`，写出的 manifest 与入仓版本同内容）；与另三个测试模块的既有 fixture 口径一致 |

- 缺陷 1–3：修复后 CI run `39199785754`（commit `cc00c47`）**四 job 全绿**（ubuntu-22.04 / windows-latest × py3.8 / py3.12）。
- 缺陷 4–6：由**发布包干净环境实测**抓出，修正在 commit `d9ea34a` / 本轮；CI run `39206716739`（commit `f23438e`）**四 job 全绿**；
  发布包内实跑 `pytest` → **258 passed, 1 skipped**（skip 即"无 `.git`，忽略规则生效与否不可判"）。
- tag `v0.1.0` 因此从 `fbb0ab6`（含缺陷 4）移到含全部修复的提交，附件重建并覆盖；移动记录见 `plan/RELEASE-M6.md` §3.1。

### 2.5 收尾

1. 回写 `plan/00`/`05`/`06` 与 `README.md` 的发布状态；`plan/RELEASE-M6.md` 落盘。
2. `plan/HANDOFF-M6.md` 本文件顶部标注"已完成"。
3. 发布后**只允许 `plan/`、`README.md` 面提交**（见 `plan/06` §四最后一条）。

## 3. 既定口径清单（K1–K45 见前几份 HANDOFF，本棒新增 K46–K52）

| # | 口径 | 落点 |
|---|---|---|
| K46 | **`report` 的 `findings` 三源合一，展开逻辑住在各自模块**：`fidelity.findings_of`（hunk）/ `parity.findings_of`（`PARITY_MISSING`/`PARITY_MODIFIED`，`PRESENT` 不入账）/ `ledger.findings_of`（`REVERTED_*`）；`report.collect_findings` 只汇总排序。字段恰 7 项，`commit_time` 不参与 ID | `fidelity.findings_of`、`parity.findings_of`、`ledger.findings_of`、`report.collect_findings`、`test_report.py` |
| K47 | **finding 的"挂在哪个提交"字段叫 `commit_oid`，不叫 `merge_oid`**：三类来源（merge / revert / parity 候选）都不一定是 merge。排序键同步为 `(commit_time, commit_oid, path, old_range)` | `canonical.sort_key_finding`、`test_canonical.py` |
| K48 | **`--verify` 先内容、后 digest**：先用同一对象库重推、与读回报告去掉 `digest` 后逐字节比较（差异定位到被改字段，含嵌套路径）；内容一致再查 `digest` 自身。digest 负责发现，JSON path 负责定位 | `report.verify_report`、`report.first_difference`、`test_report.py` |
| K49 | **`gate` 全量收集 `SMUGGLED`+`DROPPED`，`--fail-on` 只过滤 `new`**：`baselined`/`expired` 必须覆盖全部事故类，否则另一类基线条目凭空变 `stale`（已登记旧账被误报成"已修复"）。变异验证：`_scan_kinds()` 返回 `FAIL_ON_KINDS[fail_on]` → 测试变红 | `gate._scan_kinds`、`test_gate.py::test_baseline_coverage_is_not_filtered_by_fail_on` |
| K50 | **`gate` 先解析基线再跑扫描（零副作用）**：基线坏掉时不得留下任何产物（含 `--out`）。受限 TOML 非法形态（数组/嵌套表/多行字符串/内联表/非字符串值/未知键）→ `toml_unsupported` + **行号**；空基线 → 语法错误（不得静默放行） | `gate.read_baseline`、`gate.parse_baseline`、`test_gate.py::test_bad_baseline_writes_nothing` |
| K51 | **`gate` 的 `expires` 边界含当天**：`as_of <= expires` 算未过期；比较基准是报告内 `as_of`（不读系统时钟） | `gate.classify`、`test_gate.py::test_expires_boundary_is_inclusive_on_as_of`、`data/README.md` §4.7 |
| K52 | **骨架态退役完成：`errors.NotReadyError` 删除**：五子命令全部落地，无模块再抛占位异常。守门测试改成**空集**（断言异常类不存在 + 无模块含 `NotReadyError`/`NotImplementedError`/`TODO`） | `errors.py`、`report.py`、`gate.py`、`test_readme_gate.py`、`test_cli.py` |
| K53 | **报告头指纹与 `--as-of` 校验全项目只留一处**：`fidelity.range_end`（范围右端）与 `fidelity.validate_as_of`；`ledger._range_end` 与 `ledger`/`parity` 的 `_validate_as_of` 已删 | `fidelity.range_end`、`fidelity.validate_as_of`、`plan/03` §8 |
| K54 | **`report` 的 `as_of` 取三源 `as_of` 的最大值**（不另算时间戳）：三源各自都已把"输入内最新提交时间"算成日期，且空输入都回落 `end_rev`；这样同一仓库三个模块给出同一 `as_of`。空仓库无提交才回落 `end_rev`。初版 `max([] or [0])` → `1970-01-01` 是实测抓出的回归 | `report._default_as_of`、`report.build_report`、`test_report.py::test_as_of_falls_back_to_head_on_empty_input` / `test_as_of_agrees_with_every_input_module` |

## 4. 本机环境坑（2026-10-19 实测；引用前先复测）

- **`git log --grep=<re>` 匹配整条提交信息（含正文）**：`^This reverts commit` 用 `re` 语义、`^` 锚到正文每一行行首（`--format=%B` 提取正文，不解析 subject）。
- **枚举时用控制符作记录分隔**：`--format=%H\x1f%B\x1e`，按 `\x1e` 切记录、`\x1f` 切 OID/正文。不要用 `%H%x00%B` 再按 `\x00\x00` 切（多条会粘成一条）。
- **`git patch-id` 对取反 diff 稳定**：`diff-tree -p -U0 --no-renames <c> <c>^` 的 patch-id == `git revert` 生成补丁的 patch-id（实测）。
- **`git log --find-object=<blob> --all` 需 git ≥2.16**；`--find-object` **不能用来下"没有"的结论**（认 blob 内容，而 `-U0` patch-id 对空白免疫，两者在"只差空白 + 文件别处已变"时同时失配，见 K44）。
- **`git revert` 对已 revert 过的提交会失败**（`nothing to commit`）：造多 revert 仓库时用显式目标 OID。
- **不要用 `python`**：本机 `python` 可能是商店占位符，一律 `py -3.8` / `py -3.12` 并加 `-X utf8`。
- **`shutil.rmtree` 对 git 写出的只读对象会静默失败**：一律走 `gitobj._rmtree_force`（逐项 `chmod 0o700` 后重试）。
- **bench 与测试并发会打架**：慢层会重生成 `data/fixtures/**/repo/`，跑慢层时不要同时跑读 fixture 的东西。
- 本机 pip 走系统代理 → `NO_PROXY="*"` + 清华镜像；`py -3.8 -m venv` 的 pip 20.2.3 不支持 `-e .`，先升 pip。

## 5. M5 的 DoD 逐项 checklist

- [x] `mergefidelity report <repo>` 可用；规范 JSON + `digest`（`findings_digest_algorithm:"sha256"` 进报告头）
- [x] 报告头写死且**禁止**扫描时刻/绝对路径/主机名/用户名/locale/Python 版本（测试断言）
- [x] `findings[*].id` 内容寻址、可独立复算（`canonical.finding_id` 手算一致）
- [x] `fidelity` 与 `ledger` **恒计入**；`parity` 需两个显式引用，未给时 `null` + `notes=parity_not_requested`（不伪造空结果）
- [x] 换时区（`America/New_York` vs `Asia/Shanghai`）digest 相同
- [x] `core.quotepath=true/false` 下 digest 相同（变异验证：去掉 `-z` → 测试变红）
- [x] 篡改一个字节 → 退出码 1 且 `json_path` 指向**被改字段**（含嵌套路径）
- [x] 只改 `digest` → 定位到 `digest`；删 `digest` / 坏 JSON / 缺文件 → 退出码 2
- [x] `--verify` 用**同一对象库**重推、逐字节比较；相等打 `verified: N merges, M findings`、退出码 0
- [x] `mergefidelity gate <repo> --baseline=PATH` 可用；受限 TOML 子集（`[[finding]]` + 字符串值 + 注释）
- [x] 非法形态（数组/嵌套表/多行字符串/内联表/非字符串值/未知键）→ 退出码 2 + **行号**；空基线也报错
- [x] 基线语法错误 → 2 且**不写任何产物**（零副作用）
- [x] 新增 1 个夹带 → 1 且只报新增；旧账未过期 → 0 且 `baselined` 有值；`expires` 改到过去 → 1 且 `expired==1`
- [x] 基线指向不存在 finding → `stale==1` 且退出码仍 0
- [x] `as_of <= expires` 边界含当天（`as_of == expires` → `baselined`）
- [x] `--fail-on` 只过滤 `new`（全量收集两类）；变异验证已做
- [x] 同一输入两次运行退出码一致
- [x] `docs/report-sample.json` + `audit-baseline.toml` 入仓且被测试复算（`--verify` 通过）
- [x] `tools/bench_gate.py` → `bench/gate.json`（完整门禁路径耗时 + 基线命中数）
- [x] 骨架态退役三处同步（代码 + 登记测试 + CLI 参数）；`errors.NotReadyError` 已删
- [x] CI 新增 report/gate 冒烟（含 `--verify` 与 gate 四组退出码），workflow 本地解析通过（M6 后为 **12 step**）
- [x] 双解释器快层 258 passed；3.8 慢层 1 passed
- [x] **CI 绿** —— M6 已接远端；最终 run `39218760801`（commit `eb1c4e6`）四 job 全绿；
      发布包内 `pytest` 258 passed / 1 skipped（证据见 `plan/RELEASE-M6.md` §3.3）

## 6. 关键命令速查

```bash
# fixture 仓库由生成器产出（不入仓）
py -3.8 tools/gen_fixtures.py --out data/fixtures

# report 样例复算
PYTHONPATH=src py -3.8 -X utf8 -m mergefidelity report \
    data/fixtures/fidelity/smuggle-extra-line/repo --verify docs/report-sample.json
    # rc=0；stdout: verified: 1 merges, 1 findings

# gate 四组退出码
PYTHONPATH=src py -3.8 -X utf8 -m mergefidelity gate \
    data/fixtures/fidelity/smuggle-extra-line/repo --baseline audit-baseline.toml   # rc=0
sed 's/2099-12-31/2000-01-01/' audit-baseline.toml > /tmp/expired.toml
PYTHONPATH=src py -3.8 -X utf8 -m mergefidelity gate \
    data/fixtures/fidelity/smuggle-extra-line/repo --baseline /tmp/expired.toml      # rc=1

# 测试
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.8 -X utf8 -m pytest -q -m "not slow"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.8 -X utf8 -m pytest -q -m slow
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.12 -X utf8 -m pytest -q -m "not slow"

# 基准与生成器自检
py -3.8 tools/bench_gate.py --out bench/gate.json --repeats 3
py -3.8 tools/gen_fixtures.py --out data/fixtures --check   # 21/21 逐字节一致
```
