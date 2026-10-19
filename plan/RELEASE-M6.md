# RELEASE-M6 · v0.1.0 发布留档

> 两栏结构：**tag 前事实**（打 tag 之前就已确定、可复核的）/ **tag 后追加事实**（打 tag 之后才产生，如 CI run id、附件 sha256）。
> 本文件在 M6 收尾时写入；tag 后追加栏由同一棒据实补记。

## 一、发布标识

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/yuluo554/10-19-merge-fidelity （public） |
| 包名 / 分发名 | `mergefidelity` |
| 版本 | `0.1.0` |
| tag | `v0.1.0`（annotated） |
| 署名 | `yuluo554 <282769740+yuluo554@users.noreply.github.com>` |
| 许可证 | MIT（`LICENSE` 与 `pyproject.toml` 的 `license` 一致） |
| 发布形态 | 手工源码包（D3 定案）：`git archive v0.1.0 \| gzip -9n` + `SHA256SUMS` |

## 二、tag 前事实（可复核）

### 2.1 版本号四处一致

| 位置 | 值 | 证据 |
|---|---|---|
| `pyproject.toml` `version` | `0.1.0` | `git show v0.1.0:pyproject.toml` |
| `src/mergefidelity/__init__.py` `__version__` | `0.1.0` | `mergefidelity --version` → `mergefidelity 0.1.0` |
| tag 名 | `v0.1.0` | `git tag -l` |
| Release 标题 | `v0.1.0` | 见 §三 |

**连带重算**：`tool_version` 与 `git_version` 参与报告 digest，版本号从 `0.1.0.dev0` 改成 `0.1.0` 后，
`docs/report-sample.json` 的 digest 由 `1ff58a3c…` 变为 **`eb65704e058fbdcfeb9226be00b974963b8b780fb5720432a3aa13a774b383f4`**，
样例已同轮重生成并被 `test_report.py::test_repo_report_sample_matches_current_tool` 复算；
四份 `bench/*.json` 的 `tool_version` 同步改为 `0.1.0`。

### 2.2 脱敏四步（逐条复核）

1. **文本 0 命中**（本机用户名 / 家目录 / 盘符绝对路径 / 非 noreply 邮箱）：
   `git grep -e 'C:\' -e '/Users/' -e "$(git config user.name)"` → 仅 `LICENSE`/`plan`/`pyproject.toml` 的**署名**命中（刻意公开）；
   邮箱扫描仅命中 `yuluo554` 的 GitHub noreply 与合成 fixture 的 `fixture@example.invalid`（白名单）。
2. **产物脱敏**：`bench/*.json` 只含 fixture 名（无绝对路径）；`docs/report-sample.json` 由测试断言无绝对路径/主机名/locale/Python 版本。
3. **git 历史脱敏**：`git log --format=%an <%ae>` 全列 = `yuluo554 <282769740+yuluo554@users.noreply.github.com>`（作者与提交者两列均同）。
4. **`.gitignore` 复核**：`data/fixtures/**/repo/` 与 `data/fixtures/**/.git/` 仍被排除（`git check-ignore` 命中，`git ls-files` 无 `repo/` 路径）。

### 2.3 干净环境验证（CI 矩阵 + 本机 fresh-clone 等价复现）

> **本机无法 `git clone` 远端**（本机到 github.com 的 443 不通），故"干净 clone"由
> **CI 矩阵**（ubuntu-22.04 / windows-latest × py3.8 / py3.12）给出跨平台证据，
> 本机另用 `git clone <本地路径>` 做等价复现（同一条 clone→install→generate→pytest 通路）。

| 检查 | 结果 | 证据 |
|---|---|---|
| 干净 clone 无 `data/fixtures/**/repo/` | ✅ | `find data/fixtures -maxdepth 3 -name repo \| wc -l` → `0` |
| `pip install -e ".[dev]"` | ✅ | CI `install (README path)` step |
| `mergefidelity --version` | ✅ | `mergefidelity 0.1.0` |
| `mergefidelity --help` | ✅ | 五子命令 |
| `tools/gen_fixtures.py --out data/fixtures` | ✅ | `已生成 21 个 fixture`；生成后 `git status` **干净**（不改动入仓文件） |
| `pytest -q`（快层 + 慢层） | ✅ | CI 四 job 全绿；本机 3.8/3.12 各 `257 passed`，慢层 `1 passed` |
| `report --verify docs/report-sample.json` | ✅ | 本机同 git 版本 → `verified: 1 merges, 1 findings`，rc=0 |
| `gate --baseline audit-baseline.toml` | ✅ | rc=0，`counts={'baselined':1,'expired':0,'new':0,'stale':0}` |

### 2.4 手工源码包（tag 前先验证可复现性）

`git archive --format=tar --prefix=mergefidelity-0.1.0/ v0.1.0 | gzip -9n` **两次构建逐字节一致**
（`cmp` 通过）。`sha256` **只写 Release 正文，不写进包内**。

## 三、tag 后追加事实

| 项 | 值 |
|---|---|
| tag（annotated 对象） | `7f82fac`（`git rev-parse v0.1.0`） |
| tag 指向的 commit | `33e1ca4`（`git rev-parse v0.1.0^{commit}`） |
| Release URL | <https://github.com/yuluo554/10-19-merge-fidelity/releases/tag/v0.1.0> |
| Release 状态 | 非草稿、非预发布（`isDraft=false`、`isPrerelease=false`） |
| 源码包名 | `mergefidelity-0.1.0.tar.gz`（194710 字节） |
| 源码包 sha256 | `ef8e9d1659a6f367b78767f410bb547e7cf310ce7908076710e30f9429c3f55e` |
| `SHA256SUMS` 附件 | 同上一行（93 字节，`sha256sum -c` 通过） |
| 构建可复现性 | 3 次 `git archive v0.1.0 \| gzip -9n` 逐字节一致（`cmp` 通过） |
| CI run（首推，修复 3 缺陷） | `39197159675`（红）→ `39199785754`（绿，commit `cc00c47`） |
| CI run（文档收尾） | `39202465908`（绿，commit `fbb0ab6`） |
| CI run（修第 4 缺陷） | `39205421988`（绿，commit `d9ea34a`） |
| CI run（修第 5/6 缺陷） | `39212350631`（绿，commit `55dfea9`） |
| CI run（**最终发布提交**） | `39214226318`（**绿**，commit `33e1ca4`，四 job 全绿） |

### 3.1 tag 移动记录（如实留档）

| 时点 | tag → commit | 源码包 sha256 | 原因 |
|---|---|---|---|
| 首次发布 | `e6ddce8` → `fbb0ab6` | `a064e105…` | 按当时 CI 绿（`39202465908`）发布 |
| 第 1 次修正 | `097ae82` → `f23438e` | `b8f3e411…` | **发布包实测**发现 README 场景一的 `--show-kind=smuggled,dropped` 退出码 2（缺陷 4）；修复提交 `d9ea34a` 后 CI 绿（`39206716739`），tag 移至 `f23438e` |
| 第 2 次修正 | `3f6ca2c` → `55dfea9` | `662679f2…` | 继续在发布包里按 README 跑 `pytest`，又发现缺陷 5/6（无 `.git` 时 `git ls-files` 128、慢层 `--check` 冻结仓库不存在）；修复后 CI 绿（`39212350631`），tag 移至 `55dfea9` |
| 第 3 次修正（定稿） | `7f82fac` → `33e1ca4` | `ef8e9d16…` | 发布包实测发现 README 未说明"合成仓库需先生成"（按文档直接跑场景 → 退出码 3）；补齐前置命令与"开发"说明后 CI 绿（`39214226318`），tag 定为 `33e1ca4` |

**为什么允许移动**：`v0.1.0` 发布仅数十分钟、无真实下游（附件下载数均为本轮自校验），
而留在任一旧 tag 都会直接违反 M6 的 DoD（"干净 clone 按 README 跑通三场景"）。
这是**刻意的取舍**，不是疏漏；若将来已有人依赖该 tag，则应按"另发 v0.1.1"处理而非移动。
每一轮移动都重建附件、重写 Release 正文，并把旧 sha256 留在本表——不掩盖历史。

### 3.2 发布后干净环境实测（最终附件）

从 Release 重新下载 → `sha256sum -c` 通过 → 解包 → `py -3.8 -m venv` 新建 → `pip install -e ".[dev]"`：

| 检查 | 结果 |
|---|---|
| `mergefidelity --version` | `mergefidelity 0.1.0` |
| `tools/gen_fixtures.py --out data/fixtures --check` | `--check 通过：21 个 fixture 与冻结产物逐字节一致` |
| 场景一 `fidelity scan --show-kind=smuggled,dropped` | rc=0；`--fail-on=smuggled` → rc=1 |
| 场景二 `parity --from=release/1.0 --to=main`（含 `--no-apply-fallback`） | rc=0 / rc=0 |
| 场景三 `gate --baseline=audit-baseline.toml --fail-on=smuggled` | rc=0（旧账未过期） |
| `ledger`（含 `--range`） | rc=0 / rc=0 |
| `report --out` → `report --verify` | rc=0，`verified: 1 merges, 1 findings` |
| `report --verify docs/report-sample.json` | rc=0，`verified: 1 merges, 1 findings` |
| 发布包内 `pytest -q` | **258 passed, 1 skipped**（skip = 无 `.git`，忽略规则生效与否不可判） |
| README 代码块内全部命令 | 12 条**全部可被当前 parser 解析**（脚本逐条 `parse_args` 复验） |

## 四、M6 抓出的真缺陷（CI 首推 + 发布包实测）

> CI 在本项目**从未跑过**（此前所有"CI 绿"都是"本地等价校验，待首推验证"）。首次推送后
> 四个 job 全红，暴露出 3 个真缺陷——这条证据链正是"待首推验证"这一措辞的意义所在。

| # | 缺陷 | 症状 | 修法 | 变异验证 |
|---|---|---|---|---|
| 1 | **生成器部分运行会改写入仓的 `manifest.json`** | `gen_fixtures --only/--suite` 时 `if not only` 判断不覆盖 `--suite`，把 21 条记录覆盖成该套件的 12/6/3 条 → `test_manifest_matches_directory_contents` 变红；测试的 autouse fixture 用 `--suite fidelity` 现生成仓库，**一次普通 `pytest` 就静默改坏入仓文件** | 部分生成（`--only` 或 `--suite`）时**不写** `manifest.json`（`if not only and not suites`） | 去掉 `and not suites` → 该测试变红 |
| 2 | **干净 clone 没有合成仓库，CI 直接 pytest 全挂** | `data/fixtures/**/repo/` 被 `.gitignore` 排除，CI 检出后无仓库 → 所有依赖仓库的测试与 CLI 冒烟全红 | CI 新增 `generate synthetic fixtures` step（step 数 11→12），置于 `pytest` 之前；同步更新 `test_workflow.py` 的 step 断言 | 删掉该 step → CI 复现全红（首推实测） |
| 3 | **报告样例的 `git_version` 指纹跨机不同 → `--verify` 必然非 0** | 样例在本机 `2.54.0.windows.1` 生成，CI runner 是 `2.55.0` / `2.56.0.windows.2`；`git_version` 参与 digest，故逐字节比较命中 `fidelity.git_version`，rc=1 | 定案：`git_version` 是**环境指纹**（`data/README.md` §4.6），跨机不同**是设计如此**。测试改两段——同版本强断言 rc=0；跨版本要求差异**恰好只落在指纹字段**（其余逐字节一致） | 伪造 `git_version` → 断言仍要求 rc=1 且 `json_path=fidelity.git_version`（两分支均已实测） |
| 4 | **`--show-kind` 的 argparse `choices=` 拒绝文档化的逗号列表**（**发布包实测**抓出，比前三个更晚） | `plan/03` §1.1 与 README 场景一的口径是 `--show-kind=smuggled,dropped`，`fidelity._kinds_from_args` 也实现了逗号拆分，但 `cli.py` 给该选项加了 `choices=("smuggled","dropped","resolution","all")` → argparse 把整串当一个值拒绝。**干净环境按 README 跑场景一 → 退出码 2**，"陌生人 30 秒"直接卡在第一条命令 | 去掉 `choices=`，逗号拆分与非法值报错交给 `_kinds_from_args`（`UsageError` → 退出码 2）；`--help` 的 metavar 改为 `KINDS` | 新增 2 条测试：`--show-kind=smuggled,dropped` / `=all` / `=dropped,resolution` 必须被接受（rc=0）；`=weird` 仍 rc=2 |
| 5 | **发布包里 `pytest` 必挂：`git ls-files`/`git check-ignore` 在无 `.git` 目录直接 128** | 手工源码包（`git archive`）**不含 `.git`**，而 README 的"开发"一节让人在解包目录跑 `pytest`。`test_synthetic_repos_are_not_tracked_and_are_ignored` 无条件调 git → `fatal: not a git repository`（128），测试失败 | 分两种环境：git 工作树里照旧强断言；非 git（发布包）退化为**断言 `.gitignore` 规则文本存在**并 `skip`（不伪造"已忽略"结论） | 在解包目录实跑：该测试 `skip`，其余全绿 |
| 6 | **发布包慢层的 `--check` 因"冻结仓库不存在"必挂** | 同上：`repo/` 是生成物不入包，`--check` 拿"冻结目录（无仓库）"与"临时重生成目录（有仓库）"比对 → 21 处 `frozen 仓库不存在`。README 让人直接 `pytest` 会踩到 | `test_gen_fixtures.py` 加 session 级 autouse fixture：缺仓库则先跑生成器（不传 `--suite`，写出的 manifest 与入仓版本同内容）；与 test_fidelity/parity/ledger 的既有 fixture 口径一致 | 清空 `data/fixtures/*/*/repo` 后实跑：自动生成、`--check` 通过 |

**结论**：6 个缺陷都已修复。缺陷 1–3 由 CI 首推实测抓出（run `39197159675` 红 → 修复后 `39199785754` 四 job 全绿）；
缺陷 4–6 由**发布包干净环境实测**抓出（从 Release 下载 tar.gz → 解包 → 新建 venv → 按 README 跑三场景与 `pytest` 时命中），
修复后 CI run `39206716739` 四 job 全绿，发布包内 `pytest` 实跑 **258 passed, 1 skipped**。
