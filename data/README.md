# data · 依据查证、数据源可获取性与数值口径

> 本文件是**数值口径的唯一权威**。plan/01 与代码里的公式均为便于阅读的摘录；若与 §四 冲突，以 §四 为准，并在同一提交内修正摘录。
> 基准日：**2026-10-17**。GitHub 检索实测窗口：**2026-10-18 10:33–11:12 UTC**。本地 git 实测环境：**git 2.54.0.windows.1**。性能与 payload 数字均为**基准日实测快照**，只用于架构决策与文档说明，**不得写进代码常量或断言阈值**。

## 一、依据查证记录（三态：✅ 已核对原文 / ⬜ 软论据）

### 1.1 需求侧原话（✅ 逐条打开链接核对，基准日 2026-10-17）

| 编号 | 类别 | 原话（节选，未改写） | 来源 |
|---|---|---|---|
| HN-20879546 | 夹带 / 评审盲区 | "Indeed, this is called an 'evil merge' … I'm surprised the blog post doesn't mention evil merges by name" | https://news.ycombinator.com/item?id=20879546 |
| HN-38890889 | 夹带是常态 | "the tongue-in-cheek name is 'evil merge' but it's honestly pretty common precisely because … the mere textual merge could be a broken result" | https://news.ycombinator.com/item?id=38890889 |
| HN-47843787 | 工具跳过 merge | "'Evil' merges are only evil if your tooling skips over merge commits as 'unimportant'" | https://news.ycombinator.com/item?id=47843787 |
| HN-33266448 | 补丁漏搬（流程治不了） | "we often forgot to backport fixes. So I added a question to the PR template: 'Does this PR need to be backported?' … They just always typed 'No'"（2022-10-19） | https://news.ycombinator.com/item?id=33266448 |
| HN-41102956 | hotfix 未回流 | "this sounds like code introduced in a hotfix that wasn't merged back to feature branches" | https://news.ycombinator.com/item?id=41102956 |
| HN-2505629 | forward-port 丢修复 | "we only had two branches, and we did 'lose' fixes done on one branch (as in forgetting to forward-port them to the other one) a few times" | https://news.ycombinator.com/item?id=2505629 |
| V2EX-207999 | 中文：cherry-pick 追踪 | "Cherry-Pick 到哪了，哪些遗漏了哪些是重复的，log 也看的稀里糊涂的。所以每次从 master 往 sdk 分支拖代码时都小心翼翼" | https://www.v2ex.com/t/207999 |
| V2EX-491319 | 中文：多选 / 遗漏 | "cherry-pick 需要选择的 commit 数目很多，容易出现遗漏或者多选" | https://www.v2ex.com/t/491319 |

### 1.2 开源空白检索（⬜ 软论据：`gh api` 检索式 + total_count + 头部，窗口 2026-10-18 10:33–11:12 UTC）

| 检索式 | total_count | 头部 / 有效头部 |
|---|---|---|
| `evil merge in:name,description` | 24 | 头部 3274★ 为政治垃圾仓；有效头部 **fimskiy/Evil-merge-detector 8★**（Go，2026-03 建，2026-10-02 仍在推送） |
| `evil merge in:name,description stars:>2` | 9 | 同上 8★ |
| `remerge-diff in:name,description` | **1** | 0★ trygveaa/git-log-remerge-diff（Shell，2018 停更） |
| `"merge commit" audit in:name,description` | **1** | 0★ BenMalaga/casualty（JS，2026-07-05 建当天停更） |
| `"merge conflict" resolution analysis` | 5 | 头部 1★ |
| `cherry-pick tracking in:name,description stars:>2` | 4 | 14★ rgs/cherrymaint（2012 停更）；8★ kergoth/git-origin（2013 停更） |
| `missing backport in:name,description` | 11 | 37★ 无关；有效 9★ GitHub-PR-only 追踪器 |
| `backport checker in:name,description` | 3 | 14★ hardenedlinux（CVE 专用） |
| `branch drift in:name,description stars:>1` | 12 | 261★ 无关；有效 oahshtsua/git-drift 0★（需 commit-msg hook 打 CHANGE-ID、要改历史） |

**结论（⬜）**：evil merge 有 1 个 8★ 竞品；静默丢代码有 1 个 0★ 单日项目；跨分支对齐只有 2012/2013 停更工具与必须改历史的 hook 方案。三者合并为"可复算账本 + 内容寻址证据 + CI 门禁"未检索到。这是检索推断，不是市场调查；题面与 README 不得写成"首创/无人做过"。

### 1.3 与 8★ 竞品的差异（⬜ 基于公开 README/仓库信息）

| 维度 | fimskiy/Evil-merge-detector 8★ | 本题 |
|---|---|---|
| 语言 / 分发 | Go 单二进制 | Python 标准库零依赖，`pip install` 即用 |
| 写入面 | 未逐行审计，不宣称 | 只读 `.git`；临时 worktree 用完即删，不改引用 |
| 事故类型 | evil merge | 夹带 + 静默吞掉 + 跨分支漏搬，同一份账本 |
| 证据形态 | 未逐行审计，不宣称 | 内容寻址 finding ID + `--verify` 可复算 digest + 过期基线 |

> 表中"未逐行审计"是**如实留白**，不得改写成"竞品没有该能力"。

## 二、数据源可获取性记录

| 数据源 | 三态 | 获取方式 | 备注 / 阻断原因 |
|---|---|---|---|
| 需求侧原话（HN / V2EX 共 8 条） | ✅ 已获取 | 直接打开链接核对，原话照抄 | 基准日 2026-10-17；链接若失效，按"原话已存档于本文件"处理，不重新编造 |
| GitHub 检索 total_count 与头部 | ✅ 已获取（一次性快照） | `gh api` 检索接口 | 窗口 2026-10-18 10:33–11:12 UTC；数字会随时间漂移，属 ⬜ 软论据 |
| 竞品仓库元信息（星数/语言/建仓时间/最后推送） | ✅ 已获取（快照） | GitHub 仓库页 / API | 星数与推送时间会漂移，报告中引用须带基准日 |
| 真实仓库性能样本 | ✅ 已获取（快照） | 本地仓库：2252 commits / 357 merges / pack 52.19 MiB | 环境 git 2.54.0.windows.1；仅作架构依据，不作阈值 |
| `merge-tree --write-tree` 语义 | ✅ 已本地复算 | git 2.54.0.windows.1 | 干净 exit 0 + tree OID；冲突 exit 1 + 带冲突标记的 tree（`git show <tree>:file` 可读） |
| `--remerge-diff` 行为 | ✅ 已本地复算 | git 2.54.0.windows.1 | 忠实 merge payload 为空；改掉 merge 树后只输出被吞/被加的行 |
| `-U0` patch-id 跨行号等价 | ✅ 已本地复算 | git 2.54.0.windows.1 | 同一 hunk 在第 2 行 vs 第 5 行，`-U0` 下同 id；默认 3 行上下文下不同 |
| 空白噪声免疫 | ✅ 已本地复算 | git 2.54.0.windows.1 | `b b` / `b    b` / `b<TAB>b` / `b  b  ` 四种形态同 id |
| `apply --check` / `--reverse --check` 三态 | ✅ 已本地复算 | git 2.54.0.windows.1 | 缺失：fwd=0, rev=1；已应用：rev=0, fwd=1 |
| revert 与重放 | ✅ 已本地复算 | git 2.54.0.windows.1 | revert 的 patch-id == 原始 diff 反向 patch-id；重放用 `--find-object=<blob> --all` |
| octopus merge 限制 | ✅ 已本地复算 | git 2.54.0.windows.1 | `remerge-diff` 打印 `Skipping remerge-diff for octopus merges`；`merge-tree` 只接受 2 个分支 |
| 自定义 merge driver 影响 | ✅ 已本地复算 | git 2.54.0.windows.1 | `.gitattributes` 指定的 driver 会被 `merge-tree` 采用；必须把 attributes blob hash 写进报告头 |
| 多平台行为一致性 | ⬜ 待获取 | 尚未在 Linux/macOS 实测 | 首期只在 Windows 上实测；跨平台差异作为已知风险写入 README，不写"已全平台验证" |
| 大型仓库（>10 万提交）表现 | ⬜ 待获取 | 尚无样本 | 首期不承诺规模上限；bench 只报告实测环境 |
| GitHub 星数之外的采用度（下载/引用） | ⬜ 待获取 | 无公开可靠口径 | 不引用 |

## 三、合成数据纪律

- **全部 fixture 为本地合成的假仓库**，不包含任何真实公司、产品、人员或内部代码。
- **命名白名单**：项目名固定使用 `synthapp`；路径固定使用 `src/synthapp/`、`tests/synthapp/`、`docs/`；分支名固定使用 `main`、`release/1.0`、`feature/synth-a`、`feature/synth-b`；作者固定 `Fixture Bot <fixture@example.invalid>`；提交时间固定为脚本内写死的 UTC 时间戳（通过 `GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE` 设置）。不得出现真实人名、真实邮箱、真实域名。
- **不得引入真实文号、真实日期事件、真实数值指标**：fixture 里的版本号、错误码、配置值均为合成常量，且在 `expect.json` 中登记。
- **10 个 fidelity fixture，每个只注入 1 个已知缺陷**，缺陷类型分布：夹带 4、静默吞掉 3、正确冲突解决 2、octopus 1。每个 fixture 目录含：
  - `build.sh`（或 `tools/gen_fixtures.py` 中的同名函数）：重建仓库，固定全部可变输入；
  - `expect.json`：golden 输出，含 `blob_fidelity`、hunk 列表（path + old_range + new_range + kind）、`skipped` 记录；
  - `README.md`：一句话说明注入了什么缺陷、期望工具报什么。
- **可重建性判据**：两台机器（不同路径、不同时区）重建同一 fixture 后，`git rev-parse HEAD` 与全部 tree/blob OID 必须一致；golden 输出逐字节一致。
- **反例也要有**：正确冲突解决的 2 个 fixture 必须断言"不报 SMUGGLED / DROPPED"，防止工具靠"见 merge 就报"骗过验收。
- **不合成无法验证的缺陷**：每个注入缺陷都必须能被一条独立命令手工复现（写进 fixture README），不能只依赖工具自己的输出。

## 四、数值口径（单点定义，全项目唯一权威）

### 4.1 merge 的机械结果

对 merge commit `M`，父提交为 `P1`、`P2`，`B = merge-base(P1, P2)`：

- `mechanical_tree(M)` = `git merge-tree --write-tree --merge-base=B P1 P2` 输出的 tree OID（exit 0 或 exit 1 均视为有效结果；exit 1 表示冲突，树内含冲突标记）。
- `recorded_tree(M)` = `M^{tree}`。
- 逐 path 比较 `recorded_tree` 与 `mechanical_tree` 中同名 blob 的 OID。路径集合取两者并集，仅存在于一侧的路径按"缺失"处理。

### 4.2 `blob_fidelity`

```
blob_fidelity(merge) = |{path : recorded_oid == mechanical_oid}| / |{path}|
```

- 分母 = `recorded_tree` 与 `mechanical_tree` 路径并集中，**两边都存在的 path** 数量。
- 仅在一侧存在的 path 不计入分母，单独计入 `path_only_in_recorded` / `path_only_in_mechanical` 列表。
- 分母为 0 时（空树 merge），`blob_fidelity` 记为 `null`，不记为 1.0。
- octopus merge 与命中自定义 merge driver 的 path **不进分母**，进入 `skipped`。

### 4.3 三类 hunk

以 hunk 为粒度（`git diff --no-renames -U0` 的 hunk，行号为旧文件/新文件区间）：

| 类别 | 定义 | 默认是否报告 |
|---|---|---|
| `SMUGGLED` | 属于 `recorded_tree - mechanical_tree`，且 hunk 内容中**不含** `<<<<<<<` / `=======` / `>>>>>>>` 冲突标记 | 报告 |
| `DROPPED` | 属于 `mechanical_tree - recorded_tree`，且该 hunk 的等价内容（同 `U0_patchid`）未在 `M` 之后的任何提交中被重新引入 | 报告 |
| `RESOLUTION` | 属于上述任一方向，但 hunk 含冲突标记，或位于冲突区域内的手工解决 | 默认不报告，`--show-resolution` 输出 |

- `smuggled_hunks` = `SMUGGLED` 类 hunk 的数量。
- `dropped_hunks` = `DROPPED` 类 hunk 的数量。
- 一个 hunk 同时满足两类条件时，按 `SMUGGLED` > `DROPPED` > `RESOLUTION` 的优先级归类，只计一次。
- "重新引入"判定使用 `U0_patchid` 相等，不比较行号；检测范围默认到 `HEAD`，可用 `--until` 收窄。

### 4.4 `patch_parity`

```
patch_parity(A,B) = |{c in B\A : U0_patchid(c) in U0_patchid(A)}| / |B\A|
```

- `B\A` 由 `git rev-list --cherry-pick --right-only A...B` 得到。
- `U0_patchid(c)` = `git diff-tree -p -U0 <c>^ <c> | git patch-id --stable` 的第一列。
- 分母为 0 时记为 `null`。
- 三态判定优先级：`U0_patchid` 相等 → `PRESENT`；`apply --reverse --check` 成功 → `PRESENT`（内容已存在但来源不同）；`apply --check` 成功 → `MISSING`；两者皆失败 → `MODIFIED`。
- 临时 worktree 上的判定只用于**兜底**，报告中必须注明 `basis=patchid|apply`。

### 4.5 finding ID

```
Finding ID = sha1(merge_oid ‖ path ‖ old_range ‖ new_range ‖ kind)
```

- 拼接顺序固定为上述五项，分隔符固定为单个 `\x1f`（Unit Separator），编码 UTF-8，`kind` 取 `SMUGGLED` / `DROPPED` / `REVERTED_NO_SUCCESSOR` / `REVERTED_THEN_REDONE` / `REVERT_UNVERIFIED` / `PARITY_MISSING` / `PARITY_MODIFIED`。
- `old_range` / `new_range` 格式固定为 `<start>,<count>`，**行号 0 基**：`count > 0` 时
  `start = git hunk 头行号 - 1`；`count == 0`（纯增/纯删的插入点）时 `start` 直接取 git 行号。
  无对应侧时写 `-`。
- ID 不包含提交时间、扫描时刻、主机名、绝对路径；同一 finding 在任何机器上重算必须相同。

### 4.6 报告 digest 与 `--verify`

- 报告为规范 JSON：键按字典序、无多余空白、`ensure_ascii=false`、行尾 `\n`、文件编码 UTF-8（无 BOM）。
- `digest = sha256(规范 JSON 去掉 digest 字段自身后的字节)`。
- 报告头固定字段：`git_version`、`object_format`、`gitattributes_oid`（无则 `null`）、`config_overrides`（排序后的 `-c` 项）、`range`、`tool_version`。
- `--verify` = 用同一对象库重新推导全部 finding 与 digest，逐字节比较；不一致时以退出码 1 结束并输出首个差异（JSON path + 期望 + 实际）。

### 4.7 基线过期语义

`audit-baseline.toml` 每条：

```toml
[[finding]]
id = "<finding id>"
expires = "YYYY-MM-DD"      # 必填，按报告内 as_of 日期比较
justification = "非空字符串"  # 必填，缺省视为语法错误（退出码 2）
```

- 命中基线且 `as_of <= expires` → 不计失败，计入 `baselined`。
- 命中基线且 `as_of > expires` → 标记 `expired`，参与失败计数。
- 基线条目的 `id` 在本次扫描中不存在 → 标记 `stale`，只提示，不计失败。
- `id` 精确匹配，不做前缀/模糊匹配。
- 退出码：0 = 无新增且无过期；1 = 有新增或过期；2 = 用法/基线语法错误；3 = 环境不满足（git 版本低于门槛）。

### 4.8 版本门槛

| 能力 | 最低 git 版本 | 低于门槛时 |
|---|---|---|
| `--remerge-diff` | 2.36 | 退出码 3，提示升级；不降级为"只看 diff" |
| `merge-tree --write-tree` | 2.38 | 退出码 3 |
| `--find-object` | 2.16（仅影响 ledger 重放检测） | ledger 输出 `UNAVAILABLE(reason=git_too_old)`，其余模块不受影响 |
