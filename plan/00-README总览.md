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
| plan/02-架构与技术选型.md | 分层架构、git 访问层、确定性架构、退出码契约、选型与弃选 | ✅ v1 |
| plan/03-模块详设.md | 五子命令 + 共享层的接口、数据结构、处理顺序、失败路径、测试点 | ✅ v1 |
| plan/04-数据计划.md | 生成器确定性纪律、21 个 fixture 设计、golden 纪律、bench | ✅ v1 |
| plan/05-里程碑.md | 每周可演示物、出口门、环境事实、风险预案 | ✅ v1 |
| plan/06-交付对标.md | 题面 §三/§四逐条落位、待定决策表、发布前检查清单 | ✅ v1 |
| plan/HANDOFF-M1.md | 下一棒（数据先行）交接快照 | ✅ M0 收尾（历史） |
| plan/HANDOFF-M2.md | 下一棒（`fidelity scan`）交接快照 | ✅ M1 收尾（历史） |
| plan/HANDOFF-M3.md | 下一棒（`parity`）交接快照 | ✅ M2 收尾（历史） |
| plan/HANDOFF-M4.md | 下一棒（`ledger`）交接快照 | ✅ M3 收尾（历史） |
| plan/HANDOFF-M5.md | 下一棒（`report` / `gate`）交接快照 | ✅ M4 收尾 |
| plan/AUDIT-M0-M2.md | M0–M2 全面审计记录（发现/修复/复验证据/残余缺口） | ✅ 2026-10-18 |
| data/README.md | 依据查证记录（三态）/ 数据源可获取性 / 合成数据纪律 / 数值口径 | ✅ v1 |
| .gitignore / .gitattributes / LICENSE / README.md | 工程基座 | ✅ M0 |
| pyproject.toml / src/ / tests/ / tools/ | 可安装骨架、CLI 契约、fixture 生成器与基准；`fidelity`、`parity`、`ledger` 已实现，其余两模块仍为骨架态 | 🔶 M0 骨架 + M2 fidelity + M3 parity + M4 ledger |
| data/fixtures/{fidelity,parity,ledger}/ | 12 + 6 + 3 个合成仓库的生成脚本 + golden JSON（`--check` 位级一致） | ✅ M1/M2 |
| data/fixtures/ledger/ | revert 三状态 fixture（M4） | ✅ M4 落地（golden 与生产输出逐项一致） |
| bench/fidelity.json · bench/parity.json · bench/ledger.json | 单进程批量 vs 逐进程基准（M2）；parity 端到端与 apply 兜底开销（M3）；ledger 条目数/三状态分布/耗时（M4） | ✅ M2/M3/M4；gate 待 M5 |
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
| 2026-10-18 | **许可证 = MIT**（用户拍板） | 仓库内提供 `LICENSE`；README 与 `pyproject` 的 license 字段三处一致。 |
| 2026-10-18 | **Python 底线 = 3.8**（用户拍板） | 本机有 3.8.8 / 3.12.10；CI 跑 `{windows,ubuntu} × {3.8,3.12}`。代价：无 `tomllib`，基线 TOML 自写受限子集解析器，超集形态显式 `toml_unsupported`（退出码 2）。 |
| 2026-10-18 | **Release 附件 = 手工源码包**（用户拍板） | `git archive <tag>` + `gzip -9n` + `SHA256SUMS`；两次构建逐字节一致，sha256 只写 Release 正文，不写进包内。 |
| 2026-10-18 | **`merge-tree` 必须隔离对象目录**（实测发现） | `merge-tree --write-tree` 会向对象库写 tree/blob（实测 `.git/objects` 文件数增加）。为兑现"只读 `.git`"，调用时设 `GIT_OBJECT_DIRECTORY=<tmp>` + `GIT_ALTERNATE_OBJECT_DIRECTORIES=<repo>/.git/objects`，用完删临时目录；测试断言前后对象数不变。 |
| 2026-10-18 | **octopus 判定不依赖 stderr** | 实测 `remerge-diff` 对 octopus 只在 stderr 打 `Skipping remerge-diff for octopus merges.`、payload 为空。以**父提交数 >2** 为唯一判据，stderr 仅作交叉核对。 |
| 2026-10-18 | **`-U0` patch-id 对路径敏感**（实测发现） | 同内容不同路径 → 不同 patch-id。`parity` 的 `PRESENT` 因此只认"路径也相同"的 patch-id 命中（`basis=patchid`）；"别处有同内容"只落 `note`，**不改判定**（见下一行）。 |
| 2026-10-18 | **`report` 默认不含 parity** | parity 需要两个显式引用，不能从单仓库默认推导；未给 `--parity-from/--parity-to` 时该节为 `null` 并在 `notes` 写 `parity_not_requested`，不伪造空结果。 |
| 2026-10-18 | **hunk 分类只用一个方向**（M1 实测定案） | `git diff -U0 <mechanical_tree> <recorded_tree>`，按 hunk 自身形态分：含冲突标记 → RESOLUTION；含 `+` 行 → SMUGGLED；只含 `-` 行 → DROPPED。按"哪个 diff 命令产生的"分类会让同一处改动同时报成 SMUGGLED 和 DROPPED（实测踩到）。原 §4.3 表述两向歧义已修（`data/README.md` §4.3）。 |
| 2026-10-18 | **"删掉一段内容"归 DROPPED，不归 SMUGGLED**（M1 定案） | 与题面 §一 的语义一致（吞掉 = 手工删掉本应保留的 hunk）。据此把 `smuggle-delete-guard` 改名 `drop-guard-check` 并归入吞掉类，另补 `smuggle-new-file` 保持"夹带 4 / 吞掉 3"的分布。 |
| 2026-10-18 | **parity 的 apply 兜底挂 A（源侧）**（M1 定案，推翻 plan/03 初稿） | 候选提交来自 B，挂 B 侧做反向检查会恒成功、三态退化成恒 PRESENT。挂 A 才有信息量："这个改动在 A 里了吗"。另定：patch-id 用 `-U0`（等价），apply 检查用 `-U3`（存在性，`-U0` 无上下文会过宽）。 |
| 2026-10-18 | **`path-remap` 判 MISSING 而非 PRESENT**（M1 实测推翻设想） | 路径参与 patch-id，apply 也按路径匹配；"别处有同内容"不构成 PRESENT。只加 `note=content_equivalent_at_other_path`（只提示不改判定）。 |
| 2026-10-18 | **fidelity 首期 11 个 fixture（含 1 个反例守护）**（M2 追加第 12 个：`custom-driver`，见下一行） | 题面 10 个 + `drop-then-readd`（重引入抑制反例）。生成器在**生成期**把每个 fixture 的声明计数与 oracle 复算对账，不符即失败（植入器自证）。 |
| 2026-10-18 | **`custom-driver` fixture 推迟到 M2** | 需要一个跨平台可用的 merge driver 命令，与 `SKIPPED(custom_driver)` 判定同步落地更省一轮；已记入 `plan/HANDOFF-M2.md`，不静默漏掉。 |
| 2026-10-18 | **M2 起实现 `fidelity`：分类口径落地为"单方向 + 按形态"** | `git diff -U0 <mechanical_tree> <recorded_tree>`：含冲突标记 → RESOLUTION、含 `+` → SMUGGLED、只含 `-` → DROPPED。实测 12 个 fixture 的 payload 与 M1 独立 oracle 算出的 golden 逐项一致。 |
| 2026-10-18 | **`range_str` 的零计数侧写 `-`** | `count == 0`（纯插入/纯删除）时该侧没有行号区间 → `-`。这是 golden 与生产实现的第一个对不上的点（实测抓出），已把口径写进 `canonical.range_str` 的 docstring 与测试。 |
| 2026-10-18 | **octopus 的 `skipped` 条目只输出 `reason`** | 题面口径只要求 `SKIPPED(reason=octopus)`；父提交数可由对象库自查，不进 golden（多一个字段会让"逐项一致"变成"逐字段猜"）。 |
| 2026-10-18 | **`fidelity` 报告的 `warnings` 不进 golden** | `CROSSCHECK_MISMATCH`（remerge payload 路径 ∉ 树 diff 路径）是**运行时诊断**，不是判定结论；golden 只锁 payload（`merges`/`skipped`/`counts`/`blob_fidelity`）。 |
| 2026-10-18 | **`custom-driver` fixture 用 `git merge-file --union` 作 driver** | 只用 git 自身、跨平台可用（本机实测通过）；判定与 fixture 同轮落地，生成侧 oracle 与生产实现各写一份排除逻辑，一致性靠 golden 对账。 |
| 2026-10-18 | **bench 的"单进程 vs 逐进程"要在多 merge 仓库上量** | fixture 每仓只有 1 个 merge，斜率看不出来；bench 另造 8-merge 合成仓库（实测：批量 0.061s vs 逐 merge 0.463s ≈7.6×），外部真实仓库用可选的 `--repo` 传入，样本量如实标注。 |
| 2026-10-18 | **合成仓库本体不入仓** | 生成到 `data/fixtures/**/repo/` 并由 `.gitignore` 排除；入仓的是生成器 + golden + 每例 README + manifest。理由：嵌套 `.git` 无法逐字节入仓，而"可重建"由 `--check` 位级一致守门保证。 |
| 2026-10-18 | **M0 骨架采用"可运行空壳"而非假结果** | 五子命令在 M0 即注册并可 `--help`；未实现的模块返回**退出码 2 + 明确中文提示**（"本模块将在 M2 落地"），**不输出伪造空 JSON**。每个模块落地时**同轮退役**该提示。 |
| 2026-10-18 | **M3 起实现 `parity`：候选顺序取 `git rev-list` 原序**（`plan/03` §2.2 笔误已更正） | golden（M1 oracle）与 `git rev-list --cherry-pick --right-only` 的输出顺序逐条一致；原 §2.2 写的"按 `(commit_time, oid)` 排序"与 golden 冲突。定案：**以 rev-list 原序为准**（它就是候选集的产生者，且已冻结进 golden），`rev-list` 侧排序不引入额外口径；`--cherry-pick` 的候选条数与 `git cherry -v` 交叉核对（不一致只记 `warnings`，不失败）。 |
| 2026-10-18 | **`parity` 的 `note` 与 `status` 解耦**（M3 定案，细化 K27） | `equivalent_source` 分两种：判 `PRESENT` 时指向 A 侧同 `-U0` patch-id 的提交；`note=content_equivalent_at_other_path` 时指向 A 侧含同内容行的提交（**只提示**，`status` 仍由定义式给出，path-remap 场景仍是 `MISSING`）。 |
| 2026-10-18 | **`parity --no-apply-fallback` 下 patch-id 不等 → `MODIFIED(basis=patchid)`** | 没有 apply 证据就**不声称**"缺失"；MISSING 的判据是 `apply --check` 成功，缺证时不能靠 patch-id 差异反推。`basis` 仍是必填字段（值域 `patchid`/`apply`）。 |
| 2026-10-18 | **临时对象目录的删除必须解只读位**（M3 实测抓出的真缺陷） | `git merge-tree --write-tree` 写出的对象是**只读**的，`shutil.rmtree(ignore_errors=True)` 在 Windows 上**静默失败**——本轮实测系统临时目录里堆积了 **1466 个** `mf-obj-*`。修法：`gitobj._rmtree_force()` 逐项 `chmod 0o700` 后重试、并用"目录是否还在"再兜一轮；`TempObjectDir`、`temporary_worktree`、生成器与 bench 三处全部改用它，并新增 2 条守门测试（成功/异常两路径后临时目录计数不变）。变异验证：退回 `ignore_errors=True` → 新测试变红。 |
| 2026-10-19 | **M4 起实现 `ledger`：反向 patch-id 校验是"回滚属实"的唯一判据** | revert 正文声称回滚谁**不是证据**：`git revert` 生成的 revert 补丁的 `-U0` patch-id 必然等于被回滚提交 diff **取反**后的 patch-id（本轮实测 `then-redone` 两侧相等：`42c614e3…`）。不等即 `REVERT_UNVERIFIED(verified=false)`，**不猜意图**、也不算 successor。 |
| 2026-10-19 | **`ledger` 条目不输出 `evidence` 字段**（对齐 golden） | "用什么方式判的"（`patchid` / `find-object`）是**实现细节**，`verified`（反向校验通过与否）+ `successor_oid` 已承载全部结论信息；多一个字段会让"逐项一致"变成"逐字段猜"（同 M2 `octopus` 只输出 `reason`）。`plan/03` §3.3 初稿的 `evidence` 已删。 |
| 2026-10-19 | **`--find-object` 只收窄候选，结论口径以 patch-id 相等为准；不可用时不降级猜** | git ≥2.16 才有 `--find-object`；低于门槛（或命令失败）时写 `unavailable=[{reason:git_too_old,capability:find-object}]` 并只给 `REVERT_UNVERIFIED`——"这条 revert 没有 successor"是一个**断言**，缺证不能下（与 `parity --no-apply-fallback` 不声称 MISSING 同源）。 |
| 2026-10-19 | **`gitobj.commit_diff` 增加 `reverse=True`** | `ledger` 需要"取反 diff"（`diff-tree <c> <c>^`）算反向 patch-id；根提交没有父提交、取反无意义 → 返回 `None`，调用方据此判该提交不可校验。diff 参数构造仍只在 `gitobj` 一处。 |
| 2026-10-19 | **`--find-object` 只加速命中，不足以支撑"没有"**（M4 实测抓出的真缺陷） | `-U0` patch-id 对空白免疫，而 `--find-object` 认的是 blob 内容：一次"只差空白 + 文件别处已变"的重新落地，其 old/new blob **都不在**筛选集里——只做筛选就会把它报成 `REVERTED_NO_SUCCESSOR`（静默漏报，正是本工具要审计的毛病）。修法：筛选集落空时**回到全量 later 提交复扫**（结论口径始终是 patch-id 相等）。实测复现 `test_reland_invisible_to_find_object_is_still_then_redone`；变异验证：删掉复扫那一步 → 该测试变红。 |

## 承诺-证据台账

> 全项目只此一份；其他文档只可引用，不得复制。状态列随里程碑同步翻转。

| 承诺项 | 素材来源 | 交付物内可达性 | 核验方式 | 状态 |
|---|---|---|---|---|
| 机械合并复算（`mechanical_tree`） | git ≥2.38 `merge-tree --write-tree`（✅ 本地复算） | `fidelity` 子命令内置调用 | 12 个 fixture 的 payload 与 `expect.json` 逐项一致（实测，2026-10-18） | ✅ M2 |
| blob 保真度 `blob_fidelity` | 机械树 vs 记录树逐 path 比对（✅ 口径已定） | 报告字段 `blob_fidelity` | fixture golden 逐项一致（含 SKIPPED 路径剔除，实测 2026-10-18） | ✅ M2 |
| 夹带检出（SMUGGLED） | 树 diff 单方向 + 按 hunk 形态（✅ M1 定稿） | `fidelity scan --show-kind=smuggled` | 4 个夹带 fixture 的 golden hunk（实测一致） | ✅ M2 |
| 静默吞掉检出（DROPPED） | 机械树有、记录树无、且未被后续重引入（✅ 本地复算） | `fidelity scan --show-kind=dropped` | 3 个吞掉 fixture 的 golden hunk（实测一致） | ✅ M2 |
| octopus 显式 SKIPPED | 父提交数 >2（不解析 stderr，✅ M1 定稿） | 报告 `skipped[*]` | octopus fixture 断言 `reason=octopus` 且退出码 0（实测） | ✅ M2 |
| 跨分支补丁对齐（PRESENT/MISSING/MODIFIED） | `--cherry-pick --right-only` + `-U0` patch-id + `apply --check`（✅ 本地复算） | `parity` 子命令 | 6 个 fixture 的双向结果与 `expect.json` 逐项一致（实测，2026-10-18） | ✅ M3 |
| 空白免疫与跨行号等价 | `-U0` + `patch-id --stable`（✅ 本地复算） | `parity` 的 `u0_patchid` | `context-shift`（第 2 行 vs 第 5 行）与 `whitespace`（`value=1` vs `value =    1`）均 `PRESENT(basis=patchid)`（实测） | ✅ M3 |
| 临时 worktree 零残留 | `git worktree add --detach` + 三连清理（✅ 本地复算） | `parity` 的 apply 兜底 | 成功与异常两条路径后 `git worktree list` 只剩主工作树（实测，2026-10-18） | ✅ M3 |
| revert 账本（REVERTED_NO_SUCCESSOR / THEN_REDONE / UNVERIFIED） | `--grep='^This reverts commit'` + patch-id 反向校验 + `--find-object` 重放（✅ 本地复算） | `ledger` 子命令 | 三种状态 fixture 与 golden 逐项一致；`UNAVAILABLE` 与"无 successor"是不同输出（实测，2026-10-19） | ✅ M4 |
| 内容寻址 finding ID | `sha1(merge_oid‖path‖old_range‖new_range‖kind)`（✅ 口径已定） | 报告 `findings[*].id` | 独立实现重算 sha1 + 改一字节 `--verify` 非 0 | ⬜ 待 M5 |
| 可复现 digest | 规范 JSON（固定键序/排序，无时间/路径/主机名） | 报告 `digest` + `--verify` | 两台机器不同时区/`core.quotepath` 同 digest | ⬜ 待 M5 |
| 过期基线门禁 | `audit-baseline.toml` 的 `expires`/`justification` | `gate` 子命令退出码 | 新增/旧账/过期/语法错误四组 | ⬜ 待 M5 |
| 单进程批量架构 | 性能实测快照（✅ 基准日） | `fidelity` 默认路径 | `bench/fidelity.json`：8-merge 仓批量 0.061s vs 逐 merge 0.463s（实测 2026-10-18） | ✅ M2 |
| 合成 fixture 可重建 | `tools/gen_fixtures.py`（固定作者/时间/树） | `data/fixtures/` | `--check` 重生成逐字节一致（实测 21/21，2026-10-18） | ✅ M1 |
| 报告样例与基线样例 | 规范 JSON + TOML | `docs/report-sample.json`、`audit-baseline.toml` | 文件存在 + `--verify` 通过 | ⬜ 待 M5 |
| README 三场景复现 | 场景命令 | `README.md` | 干净 clone 按 README 跑通 | ⬜ 待 M6 |
| 测试覆盖 | `tests/` | `pytest`（含 `slow` 标记的生成器确定性层） | 三类 hunk ✅ M2；patch-id/三态/worktree ✅ M3；revert 三状态/反向校验/unavailable ✅ M4；`--verify`/退出码 ⬜ M5 | 🔶 进行中 |

## 里程碑

| 里程碑 | 内容 | 出口门 | 状态 |
|---|---|---|---|
| M0 | 出题定稿 + 骨架 | plan/00–06 齐；可安装 CLI（五子命令可 `--help`）；`pytest` 双解释器全绿；退出码契约锁进测试；`LICENSE`/`.gitattributes`/README 基座 | ✅ 已完成（2026-10-18） |
| M1 | 数据先行 | `tools/gen_fixtures.py` 可重建 21 个 fixture（fidelity 12 / parity 6 / ledger 3）+ golden；`--check` 逐字节一致；生成期声明自证；反例在列 | ✅ 已完成（2026-10-18；`custom-driver` fixture 顺延 M2） |
| M2 | fidelity | `fidelity scan` 可用；**12 个 fixture 的 payload 与 golden 逐项一致**；同机双跑逐字节一致；octopus 与 custom_driver 均 `SKIPPED` 且退出码 0；`bench/fidelity.json` | ✅ 已完成（2026-10-18） |
| M3 | parity | `parity` 可用；**6 个 fixture 的双向结果与 golden 逐项一致**；三态齐全且 `basis` 必填；`-U0` 跨行号/空白等价（`basis=patchid`）；临时 worktree 成功/异常两路径均无残留；`bench/parity.json` | ✅ 已完成（2026-10-18） |
| M4 | ledger | `ledger` 可用；**三种 revert 状态识别正确且与 golden 逐项一致**；反向 patch-id 校验；`--find-object` 只作候选筛选、结论以 patch-id 为准；`REVERT_UNVERIFIED` 与"无 successor"分开输出；`bench/ledger.json` | ✅ 已完成（2026-10-19） |
| M5 | report / gate | 规范 JSON + `--verify`；两台机器 digest 一致；`gate` 四组退出码语义全对；`audit-baseline.toml` 样例与 CI 示例落地 | ⬜ |
| M6 | 发布 | 干净环境按 README 跑通三场景；脱敏四步；tag + Release 附件；`plan/RELEASE-M6.md` 两栏留档 | ⬜ |

## 承诺-证据台账使用说明

- 台账状态列在对应里程碑完成的**同一次提交**里翻转，不得滞后。
- 任何一条承诺若在开发中被砍，必须在决策记录表新增一行说明理由，并同步删除题面对应措辞；不得只改台账不改题面。
