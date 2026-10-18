# 00 · README 总览 — 10-19-merge-fidelity（Merge 保真度审计）

- 性质：不参赛项目题 · 发布 GitHub **公开仓库** · 署名 yuluo554
- 定位宣言："对每一次 merge，用 git 自己的合并引擎复算'机械合并应该得到什么'，再与仓库里实际记录的树逐 blob 对比，挖出评审看不见的三类代码事故：**夹带（evil merge）、静默吞掉（conflict 解决时丢掉一侧 hunk）、跨分支漏搬（hotfix 没 forward-port / 补丁没 backport）**。每条发现都有内容寻址的 ID 与可复现 digest——git 自己就是裁判。"
- 交付形态：**纯本地 Python CLI（只读 .git，零网络、无模型）**。单一形态，不设备选。
- 发布：GitHub 公开仓库，v0.1.0（tag + Release 附产物 + 发布留档 `plan/RELEASE-M6.md`）。
- 查证基准日：2026-10-17；GitHub 检索实测窗口：2026-10-18 10:33–11:12 UTC；本地性能实测环境：git 2.54.0.windows.1。

## 文档索引表

| 文档 | 内容 | 状态 |
|---|---|---|
| plan/00-README总览.md | 本文档：索引 / 决策记录 / 弃选项 / 承诺-证据台账 / 里程碑 | ✅ v1 |
| plan/01-题目文档.md | 十段式题目定稿（含招牌动词表、含金量锚点、边界与非目标） | ✅ v1 |
| data/README.md | 依据查证记录（三态）/ 数据源可获取性 / 合成数据纪律 / 数值口径 | ✅ v1 |
| .gitignore | Python 标准模板（含临时 worktree、`*.db`） | ✅ v1 |
| pyproject.toml / src/ / tests/ / tools/ | 可安装骨架、CLI 契约、fixture 生成器与基准（M1 起逐模块落地） | ⬜ 待 M1 |
| data/fixtures/fidelity/ + expect.json | 10 个注入缺陷的合成仓库 + golden JSON（M1） | ⬜ 待 M1 |
| data/fixtures/parity/ · ledger/ | 跨分支三态矩阵、revert 三状态 fixture（M3/M4） | ⬜ 待 M3 |
| bench/*.json | 单进程批量 vs 逐进程基准（M2） | ⬜ 待 M2 |
| audit-baseline.toml | 基线样例（`expires` + `justification`，M5） | ⬜ 待 M5 |
| .github/workflows/ci.yml | 门禁接入示例（M5） | ⬜ 待 M5 |
| plan/RELEASE-M6.md | 发布留档（tag 时点事实 / tag 后追加事实分栏） | ⬜ 待 M6 |

## 决策记录表

> 本表同时登记已定案决策与**弃选项**（含弃选理由），后续里程碑不再重复论证。

| 日期 | 决策 | 结论与理由 |
|---|---|---|
| 2026-10-17 | **如实记录：本题不是无人区** | evil merge 已有 **fimskiy/Evil-merge-detector 8★**（Go，2026-03 建，2026-10-02 仍在推送）；静默丢代码已有 **BenMalaga/casualty 0★**（JS，2026-07-05 建当天停更）；跨分支对齐只有 2012/2013 停更工具（rgs/cherrymaint 14★、kergoth/git-origin 8★）与必须改历史的 hook 方案（oahshtsua/git-drift 0★，需 commit-msg 打 CHANGE-ID）。**本题的差异化只有四条：Python 标准库零依赖且只读 `.git`、三类事故合一本账、内容寻址 finding ID + 可复现 digest、带过期时间的基线门禁。** 题面、README、data/README 一律不得写"首创/空白/无人做过"。 |
| 2026-10-17 | **git 版本会让结论漂移，报告必须自带版本指纹** | `--remerge-diff` 需 ≥2.36，`merge-tree --write-tree` 需 ≥2.38；不同版本对 rename、冲突标记、merge driver 的处理不同，同一仓库可能得出不同的 `mechanical_tree`。因此报告头写死 `git_version`、`object_format`、`.gitattributes` blob OID、生效的 `-c` 覆盖项；低于门槛时退出码 3，不降级猜测。 |
| 2026-10-17 | **octopus merge 真不支持，必须显式 SKIPPED** | `remerge-diff` 对 octopus 直接打印 `Skipping remerge-diff for octopus merges`；`merge-tree` 只接受 2 个分支。处理方式：父提交数 >2 的 merge 输出 `SKIPPED(reason=octopus)`，计入报告但不计入 `blob_fidelity` 分母，**不影响退出码**。绝不静默跳过——静默跳过正是本题要审计的毛病。 |
| 2026-10-17 | **忠实 merge 也可能有 payload：降噪是首期最大工作量** | 真实仓库实测（2252 commits / 357 merges）：34 个 merge 有 remerge payload，但其中相当一部分是合法的冲突解决（带 CONFLICT 标记）或机械合并无法复现的上下文（rename、merge driver）。因此 hunk 必须三分（SMUGGLED / DROPPED / RESOLUTION），默认只报前两类，`RESOLUTION` 需 `--show-resolution` 才输出；降噪规则的每一条都要有 fixture 覆盖。 |
| 2026-10-17 | **架构必须单进程批量，不能 per-merge fork** | 实测：单进程 `git log --merges --remerge-diff` 全量 1.3s；逐 commit 起子进程 `merge-tree` 100 次 9.4s（Windows 进程开销 ≈94ms/次）。`merge-tree` 只用于对 payload 非空的 merge 做交叉校验，不做全量逐 merge 调用。性能数字是基准日实测快照，只写进文档，**不进代码常量**。 |
| 2026-10-17 | **patch-id 必须用 `-U0`** | 默认 3 行上下文会让"同一 hunk 出现在第 2 行 vs 第 5 行"的 patch-id 不同（已实测）；`-U0` 下相同，且对空白噪声（`b b` / `b    b` / `b<TAB>b` / 行尾空格）免疫。所有跨分支等价判定统一用 `git diff-tree -p -U0 | git patch-id --stable`，口径只在 `data/README.md` §四定义一次。 |
| 2026-10-17 | **finding ID 内容寻址** | `id = sha1(merge_oid ‖ path ‖ old_range ‖ new_range ‖ kind)`，分隔符固定。ID 不依赖提交时间、扫描时刻、主机名，因此可跨机器复算、可写进基线、可被 `--verify` 重推。 |
| 2026-10-17 | **基线过期语义** | `audit-baseline.toml` 每条含 `id`、`expires`、`justification`；未过期旧账不计失败，过期条目自动重新报警并参与退出码；指向不存在 finding 的条目标 `stale` 只提示。语义只在 `data/README.md` §四定义一次。 |
| 2026-10-17 | 弃选："仓库健康度大礼包" | 与 git-sizer（体积/大文件）、gitleaks/trufflehog（密钥）正面重叠，评分上无法证明增量，且会把"只读 merge 保真度"这一窄缝冲淡。 |
| 2026-10-17 | 弃选："行级考古（谁在哪行改了什么）" | git-blameall 35★ 已占，且需要相似度阈值与启发式判断，与"全部结论由 git 对象复算"的确定性纪律冲突。 |
| 2026-10-17 | 弃选："测试侵蚀分析" | 2026-08 之后至少 8 个竞品，且与"AI 生成代码返工"赛道贴脸，判定口径主观（什么算"侵蚀"），无法做成可复算指标。 |
| 2026-10-17 | 弃选："提交原子性检查" | 没有客观可复算口径——"一个提交是否只做一件事"必须靠语义判断，违反零模型的硬约束。 |
| 2026-10-17 | 弃选："bus factor / 贡献分布" | hercules、gitinspector 已占，且与 merge 保真度无关。 |
| 2026-10-17 | 弃选："自动修复 / 自动重放 merge" | 会写对象、改引用，违反只读红线；且自动修复的错误代价远高于报告一条 finding。 |
| 2026-10-17 | 形态定案：纯 CLI，单一形态 | 输出是规范 JSON + 可选 Markdown 摘要，接入 CI 与本地终端；不做 GUI/桌面/Web 服务，避免空壳形态与额外分发负担。 |

## 承诺-证据台账

> 全项目只此一份；其他文档只可引用，不得复制。状态列随里程碑同步翻转。

| 承诺项 | 素材来源 | 交付物内可达性 | 核验方式 | 状态 |
|---|---|---|---|---|
| 机械合并复算（`mechanical_tree`） | git ≥2.38 `merge-tree --write-tree`（✅ 本地复算） | `fidelity` 子命令内置调用 | 10 个 fixture 的 `expect.json` 逐字节 | ⬜ 待 M2 |
| blob 保真度 `blob_fidelity` | 机械树 vs 记录树逐 path 比对（✅ 口径已定） | 报告字段 `blob_fidelity` | fixture 注入偏差值 + `--verify` 重算 | ⬜ 待 M2 |
| 夹带检出（SMUGGLED） | `remerge-diff` payload + 无 CONFLICT 标记（✅ 本地复算） | `fidelity --show-kind=smuggled` | 4 个夹带 fixture 的 golden hunk | ⬜ 待 M2 |
| 静默吞掉检出（DROPPED） | 机械树有、记录树无、且未被后续重引入（✅ 本地复算） | `fidelity --show-kind=dropped` | 3 个吞掉 fixture 的 golden hunk | ⬜ 待 M2 |
| octopus 显式 SKIPPED | `Skipping remerge-diff for octopus merges`（✅ 本地复算） | 报告 `skipped[*]` | octopus fixture 断言 `reason=octopus` 且退出码 0 | ⬜ 待 M2 |
| 跨分支补丁对齐（PRESENT/MISSING/MODIFIED） | `--cherry-pick --right-only` + `-U0` patch-id + `apply --check`（✅ 本地复算） | `parity` 子命令 | 双向 release/main 三态矩阵 fixture | ⬜ 待 M3 |
| 空白免疫与跨行号等价 | `-U0` + `patch-id --stable`（✅ 本地复算） | `parity` 的 `u0_patchid` | 第 2 行 vs 第 5 行、四种空白形态同 id 断言 | ⬜ 待 M3 |
| revert 账本（REVERTED_NO_SUCCESSOR / THEN_REDONE / UNVERIFIED） | `--grep='^This reverts commit'` + patch-id 反向校验 + `--find-object`（✅ 本地复算） | `ledger` 子命令 | 三种状态 fixture | ⬜ 待 M4 |
| 内容寻址 finding ID | `sha1(merge_oid‖path‖old_range‖new_range‖kind)`（✅ 口径已定） | 报告 `findings[*].id` | 独立实现重算 sha1 + 改一字节 `--verify` 非 0 | ⬜ 待 M5 |
| 可复现 digest | 规范 JSON（固定键序/排序，无时间/路径/主机名） | 报告 `digest` + `--verify` | 两台机器不同时区/`core.quotepath` 同 digest | ⬜ 待 M5 |
| 过期基线门禁 | `audit-baseline.toml` 的 `expires`/`justification` | `gate` 子命令退出码 | 新增/旧账/过期/语法错误四组 | ⬜ 待 M5 |
| 单进程批量架构 | 性能实测快照（✅ 基准日） | `fidelity` 默认路径 | `bench/fidelity.json` 与逐进程对比 | ⬜ 待 M2 |
| 合成 fixture 可重建 | `tools/gen_fixtures.py`（固定作者/时间/树） | `data/fixtures/` | 两台机器重建后 `git rev-parse` 一致 | ⬜ 待 M1 |
| 报告样例与基线样例 | 规范 JSON + TOML | `docs/report-sample.json`、`audit-baseline.toml` | 文件存在 + `--verify` 通过 | ⬜ 待 M5 |
| README 三场景复现 | 场景命令 | `README.md` | 干净 clone 按 README 跑通 | ⬜ 待 M6 |
| 测试覆盖 | `tests/` | `pytest` | 三类 hunk/patch-id/三态/revert/verify/退出码 | ⬜ 待 M2–M5 |

## 里程碑

| 里程碑 | 内容 | DoD |
|---|---|---|
| M0 | 出题定稿 + 骨架 | plan/00、plan/01、data/README、.gitignore 齐；中文首提交已验证 |
| M1 | 数据先行 | `tools/gen_fixtures.py` 可重建 10 个注入缺陷的合成仓库（夹带 4 / 吞掉 3 / 正确冲突解决 2 / octopus 1）+ 各自 `expect.json` golden；两台机器重建后 commit OID 一致 |
| M2 | fidelity | `fidelity` 子命令可用；10 个 fixture 输出与 golden 逐字节一致；连跑两次一致；octopus 输出 `SKIPPED` 且退出码 0；`bench/fidelity.json` 产出 |
| M3 | parity | `parity` 子命令可用；双向 release/main 三态矩阵全对；`-U0` 跨行号/空白等价断言通过；临时 worktree 成功与异常路径均无残留 |
| M4 | ledger | `ledger` 子命令可用；三种 revert 状态识别正确；`REVERT_UNVERIFIED` 与"无 successor"分开输出 |
| M5 | report / gate | 规范 JSON + `--verify`；两台机器 digest 一致；`gate` 四组退出码语义全对；`audit-baseline.toml` 样例与 CI 示例落地 |
| M6 | 发布 | **git tag** + **GitHub Release 附产物**（本地留 release zip 副本 + sha256，Release 至少 1 个手工上传附件）+ **发布留档 `plan/RELEASE-M6.md`**（tag 时点事实 / tag 后追加事实分栏）；发布 GitHub 公开仓库；干净环境按 README 跑通三场景 |

## 承诺-证据台账使用说明

- 台账状态列在对应里程碑完成的**同一次提交**里翻转，不得滞后。
- 任何一条承诺若在开发中被砍，必须在决策记录表新增一行说明理由，并同步删除题面对应措辞；不得只改台账不改题面。
