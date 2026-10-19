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

> 以下由 tag/Release 落地后据实填写。

| 项 | 值 |
|---|---|
| tag OID | `______`（`git rev-parse v0.1.0`） |
| Release URL | `______` |
| 源码包名 | `mergefidelity-0.1.0.tar.gz` |
| 源码包 sha256 | `______` |
| `SHA256SUMS` 附件 | `______` |
| CI run id（首推 + 发布后） | `______` |
| 首个绿 CI run | `39199785754`（commit `cc00c47`，4 job 全绿，2026-10-19T04:30–04:36Z） |

## 四、M6 抓出的真缺陷（CI 首推实测）

> CI 在本项目**从未跑过**（此前所有"CI 绿"都是"本地等价校验，待首推验证"）。首次推送后
> 四个 job 全红，暴露出 3 个真缺陷——这条证据链正是"待首推验证"这一措辞的意义所在。

| # | 缺陷 | 症状 | 修法 | 变异验证 |
|---|---|---|---|---|
| 1 | **生成器部分运行会改写入仓的 `manifest.json`** | `gen_fixtures --only/--suite` 时 `if not only` 判断不覆盖 `--suite`，把 21 条记录覆盖成该套件的 12/6/3 条 → `test_manifest_matches_directory_contents` 变红；测试的 autouse fixture 用 `--suite fidelity` 现生成仓库，**一次普通 `pytest` 就静默改坏入仓文件** | 部分生成（`--only` 或 `--suite`）时**不写** `manifest.json`（`if not only and not suites`） | 去掉 `and not suites` → 该测试变红 |
| 2 | **干净 clone 没有合成仓库，CI 直接 pytest 全挂** | `data/fixtures/**/repo/` 被 `.gitignore` 排除，CI 检出后无仓库 → 所有依赖仓库的测试与 CLI 冒烟全红 | CI 新增 `generate synthetic fixtures` step（step 数 11→12），置于 `pytest` 之前；同步更新 `test_workflow.py` 的 step 断言 | 删掉该 step → CI 复现全红（首推实测） |
| 3 | **报告样例的 `git_version` 指纹跨机不同 → `--verify` 必然非 0** | 样例在本机 `2.54.0.windows.1` 生成，CI runner 是 `2.55.0` / `2.56.0.windows.2`；`git_version` 参与 digest，故逐字节比较命中 `fidelity.git_version`，rc=1 | 定案：`git_version` 是**环境指纹**（`data/README.md` §4.6），跨机不同**是设计如此**。测试改两段——同版本强断言 rc=0；跨版本要求差异**恰好只落在指纹字段**（其余逐字节一致） | 伪造 `git_version` → 断言仍要求 rc=1 且 `json_path=fidelity.git_version`（两分支均已实测） |

**结论**：3 个缺陷都已修复并在 CI 上复验为绿（run `39199785754`，4 job 全绿）。
