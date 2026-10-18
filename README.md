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
| M0 | 计划文档（`plan/00`–`06`）+ 可安装骨架 + CLI 契约 | ✅ 本提交 |
| M1 | 数据先行：`tools/gen_fixtures.py` + 19 个合成 fixture 与 golden | ⬜ 计划中 |
| M2 | `fidelity scan`：机械树复算 + 三类 hunk 分类 | ⬜ 计划中 |
| M3 | `parity`：跨分支三态（`-U0` patch-id + apply 兜底） | ⬜ 计划中 |
| M4 | `ledger`：revert / 复活账本 | ⬜ 计划中 |
| M5 | `report`（digest + `--verify`）/ `gate`（过期基线门禁） | ⬜ 计划中 |
| M6 | 发布：公开仓库 + v0.1.0 tag + Release 附件 | ⬜ 计划中 |

> 骨架期五个子命令**已注册并可 `--help`**，但未落地的模块以**退出码 2 + 中文提示**收场，
> **不输出伪造的空结果**。每个模块落地时同轮退役该提示。

## 安装

```bash
py -3.8 -m pip install -e ".[dev]"      # 运行时零依赖；dev 只为跑测试
mergefidelity --version
mergefidelity --help
```

Windows 上 `python` 可能是应用商店占位符，用 `py -3.8` / `py -3.12`；跑脚本加 `-X utf8`。

## 用法（最小复现命令）

> 下列命令的**参数契约自 M0 起固定**；功能里程碑落地后即按此形态可用。

```bash
# 场景一：扫描一个仓库的全部 merge，看有哪些夹带/吞掉
mergefidelity fidelity scan /path/to/repo --show-kind=smuggled,dropped

# 场景二：release 分支上的修复有没有回流到 main
mergefidelity parity /path/to/repo --from=release/1.0 --to=main

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

## 已知边界（如实标注）

- **octopus merge（父提交 >2）与自定义 merge driver 命中的路径**统一输出 `SKIPPED(reason=...)`：
  显式记录、不静默漏报、不影响退出码；首期不做近似分析。
- **git 版本会让结论漂移**：`--remerge-diff` 需 ≥2.36、`merge-tree --write-tree` 需 ≥2.38；
  低于门槛退出码 3，不降级猜测。
- **跨平台**：首期只在 Windows（git 2.54.0.windows.1）实测；Linux/macOS 由 CI 矩阵覆盖。
- **规模**：>10 万提交的仓库无样本，首期不承诺上限。
- **结论语义**：`blob_fidelity` 与 finding 是"机械合并 vs 实际记录"的**差异证据**，
  **不等于"这段代码错了"**；报告同时给出两侧树的可复算入口，由人判断业务影响。
- 临时 worktree 只用于 `parity` 的 apply 兜底，落在系统临时目录，成功/异常两条路径都清理。

## 开发

```bash
py -3.8 -m pytest -q          # 另一条通道：py -3.12 -m pytest -q
```

- 计划与口径：`plan/00`–`06`、`data/README.md`（数值口径唯一权威）
- 许可：MIT，见 [LICENSE](LICENSE)
