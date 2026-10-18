# Merge 保真度审计（MergeFidelity）

对每一次 merge，用 **git 自己的合并引擎**复算"机械合并应该得到什么"，再与仓库里实际记录的树
逐 blob 对比，挖出评审看不见的三类代码事故：

| 类别 | 含义 |
|---|---|
| **夹带（SMUGGLED）** | 解冲突时顺手塞进与冲突无关的改动（"evil merge"） |
| **静默吞掉（DROPPED）** | 解冲突时选错一侧、或手工删掉本应保留的 hunk |
| **跨分支漏搬（MISSING / MODIFIED）** | hotfix 没 forward-port、补丁没 backport、cherry-pick 漏选 |

每条发现都有内容寻址的 ID 与可复现 digest——**git 自己就是裁判**。

- 纯本地 Python CLI：**只读 `.git`、零网络、零第三方运行时依赖、不加载任何模型**
- 判定全部来自 git 对象与 patch-id 复算；不猜代码意图
- 报告是规范 JSON，可 `--verify` 逐字节重算；基线支持 `expires` 过期重新报警

## 当前状态

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 计划文档（`plan/00`–`06`）+ 可安装骨架 + CLI 契约 | ✅ 已完成 |
| M1 | 数据先行：`tools/gen_fixtures.py` + 21 个合成 fixture 与 golden（`--check` 位级一致） | ✅ 已完成 |
| M2 | `fidelity scan`：机械树复算 + `blob_fidelity` + 三类 hunk（12/12 fixture 与 golden 逐项一致） | ✅ 已完成 |
| M3 | `parity`：跨分支三态（`-U0` patch-id + apply 兜底）；6 个 fixture 双向与 golden 逐项一致 | ✅ 已完成 |
| M4 | `ledger`：revert / 复活账本 | ⬜ 未开工 |
| M5 | `report`（digest + `--verify`）/ `gate`（过期基线门禁） | ⬜ 未开工 |
| M6 | 发布：公开仓库 + v0.1.0 tag + Release 附件 | ⬜ 未开工 |

> `fidelity` 与 `parity` 已可用；`ledger` / `report` / `gate` **已注册并可 `--help`**，但尚未实现的
> 模块以**退出码 2 + 中文提示**收场，**不输出伪造的空结果**（每个模块落地时同轮退役该提示）。
>
> 开发进度与逐项证据见 `plan/00-README总览.md`（承诺-证据台账 + 里程碑表）与各 `plan/HANDOFF-*.md`。

## 安装

```bash
py -3.8 -m pip install -e ".[dev]"      # 运行时零依赖；dev 只为跑测试
mergefidelity --version
mergefidelity --help
```

Windows 上 `python` 可能是应用商店占位符，用 `py -3.8` / `py -3.12`；跑脚本加 `-X utf8`。

## 用法（最小复现命令）

> `fidelity` 与 `parity` 已按下列形态可用；`gate` 的参数契约自 M0 起固定，功能里程碑落地后即可用。

```bash
# 场景一：扫描一个仓库的全部 merge，看有哪些夹带/吞掉
mergefidelity fidelity scan /path/to/repo --show-kind=smuggled,dropped
mergefidelity fidelity scan /path/to/repo --since=v0.1.0 --fail-on=smuggled   # CI 用：命中即退出码 1

# 场景二：release 分支上的修复有没有回流到 main
mergefidelity parity /path/to/repo --from=release/1.0 --to=main
mergefidelity parity /path/to/repo --from=release/1.0 --to=main --no-apply-fallback   # 不建临时 worktree

# 场景三：CI 门禁——只扫增量，基线内旧账不失败，过期旧账重新报警
mergefidelity gate /path/to/repo --since=v0.1.0 --baseline=audit-baseline.toml --fail-on=smuggled
```

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功且无"需失败"的发现 |
| 1 | 成功执行，但存在需失败的发现（`gate` 新增/过期；`--fail-on` 命中） |
| 2 | 用法错误：未知子命令、缺必填参数、坏基线语法、坏报告文件 |
| 3 | 环境不满足：git 版本低于门槛、路径不是 git 仓库、git 调用超时 |

> 判据：`0` 与 `1` 是"跑完了"，`2` 与 `3` 是"没跑成"。CI 里别把 `1` 当故障——它是检出。

## 报告字段（规范 JSON）

| 字段 | 说明 |
|---|---|
| `git_version` / `object_format` / `gitattributes_oid` | 环境指纹：git 版本、对象格式（sha1/sha256）、`.gitattributes` blob OID |
| `config_overrides` | 生效的 `-c` 覆盖项（固定注入，参与 digest） |
| `range` / `as_of` | 扫描范围与日期（`as_of` 显式给出，**不读系统时钟**） |
| `merges[*].mechanical_tree` / `recorded_tree` | 机械合并复算的树 vs 实际记录的树 |
| `merges[*].blob_fidelity` | `|{path: recorded_oid == mechanical_oid}| / |{path}|`，分母为 0 时记 `null` |
| `merges[*].hunks[*].kind` | `SMUGGLED` / `DROPPED` / `RESOLUTION` |
| `skipped[*].reason` | `octopus` / `custom_driver` / `binary`——**显式记录，不静默漏报** |
| `findings[*].id` | `sha1(merge_oid ‖ path ‖ old_range ‖ new_range ‖ kind)` |
| `digest` | 去掉该字段自身后的规范 JSON sha256，可 `--verify` 重算 |

`parity` 报告（`--from=A --to=B`）另含：

| 字段 | 说明 |
|---|---|
| `from_oid` / `to_oid` | 两侧引用的 commit OID（`A^{commit}` / `B^{commit}`） |
| `candidates` | `git rev-list --cherry-pick --right-only A...B`；报告按该顺序逐条列出 |
| `patch_parity` | `present / candidates`；候选为 0 时记 `null`（不记 1.0） |
| `commits[*].status` | `PRESENT` / `MISSING` / `MODIFIED` |
| `commits[*].basis` | `patchid`（`-U0` patch-id 相等）或 `apply`（临时 worktree 上的 `apply --check`）——**必填** |
| `commits[*].note` | 只提示不改判定：`content_already_present` / `partial_or_context_conflict` / `content_equivalent_at_other_path` |
| `commits[*].equivalent_source` | 判 `PRESENT` 时指向 A 侧同 patch-id 的提交；`note` 为跨路径提示时指向 A 侧同内容提交 |
| `worktree` | `{"created":bool,"reason":"apply_fallback"}`——临时 worktree 是否启用（报告落绝对路径**禁止**） |
| `warnings[*]` | `CHERRY_COUNT_MISMATCH`：`rev-list` 与 `git cherry` 候选数不一致（只提示，不失败） |

## 已知边界（如实标注）

- **octopus merge（父提交 >2）与自定义 merge driver 命中的路径**统一输出 `SKIPPED(reason=...)`：
  显式记录、不静默漏报、不影响退出码；首期不做近似分析。
- **`.gitattributes` 模式匹配是有意简化**：支持 `*.ext`、顶层文件名、`dir/**`、`/精确路径`，
  **不支持** `!` 取反、`[abc]` 字符组与 `**/` 中缀。命中即 `SKIPPED(custom_driver)`，
  宁可少命中（保守）也不做近似分析；简化范围写在此处以便复核。
- **git 版本会让结论漂移**：`--remerge-diff` 需 ≥2.36、`merge-tree --write-tree` 需 ≥2.38；
  低于门槛退出码 3，不降级猜测。
- **判定相关配置被钉死**：`core.quotepath` / `diff.algorithm` / `diff.noprefix` /
  `merge.conflictStyle` 等由工具固定注入，并登记在报告头的 `config_overrides`。
  理由：实测 `merge.conflictStyle=zdiff3` 会改变机械树 OID（`51683564511b…` → `0f5a5d03ff9a…`），
  不钉死则同一仓库在不同机器上得出不同结论。**你的仓库/用户级配置不会影响判定**。
- **跨平台**：首期只在 Windows（git 2.54.0.windows.1）实测；Linux/macOS 由 CI 矩阵覆盖。
- **规模**：>10 万提交的仓库无样本，首期不承诺上限。
- **结论语义**：`blob_fidelity` 与 finding 是"机械合并 vs 实际记录"的**差异证据**，
  **不等于"这段代码错了"**；报告同时给出两侧树的可复算入口，由人判断业务影响。
- **`parity` 的两种 patch 上下文各有用途**：`-U0` patch-id 判**等价**（对行号与空白免疫），
  `apply --check` 用 `-U3` 判**是否存在**（`-U0` 补丁没有上下文，apply 会过于宽松）。
  `--no-apply-fallback` 下不创建任何 worktree，patch-id 不等一律记 `MODIFIED(basis=patchid)`
  ——没有 apply 证据就**不声称**"缺失"。
- **`parity` 的判定 worktree 挂在源侧 A**：问的是"这个改动在 A 里了吗"；挂 B 侧会因候选本就
  来自 B 而恒成功、三态退化成恒 `PRESENT`。
- 临时 worktree 只用于 `parity` 的 apply 兜底，落在系统临时目录，每次调用只创建一次，
  成功/异常两条路径都清理。

## 开发

```bash
py -3.8 -m pytest -q          # 另一条通道：py -3.12 -m pytest -q
```

- 计划与口径：`plan/00`–`06`、`data/README.md`（数值口径唯一权威）
- 许可：MIT，见 [LICENSE](LICENSE)
